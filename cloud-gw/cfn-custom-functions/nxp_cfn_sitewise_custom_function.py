#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
A custom function which creates a custom CloudFormation resource.
Implements the 'create' and 'delete' events.
When 'create' is invoked it creates SiteWise resources: an asset model,
an asset, a project, a portal and multiple dashboards; and a IoT Topic Rule
which routes the telemetry data from AWS IoT Core to SiteWise.
When 'delete' is invoked it handles the deletion of all resources
created by this function.

Copyright 2021 NXP
"""

import json
import logging
import time

import boto3
import cfnresponse

from cfn_utils import Utils

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

class SitewiseHandler:
    """
    Handles the create and delete events for the sitewise resources.
    """

    # Wait for a maximum of 10 minutes
    WAITER_CONFIG = {
        'Delay': 3,
        'MaxAttempts': 200
    }

    MEASUREMENTS = [
        ('CPU idle', '%'),
        ('CPU0 idle', '%'),
        ('CPU1 idle', '%'),
        ('CPU2 idle', '%'),
        ('CPU3 idle', '%'),
        ('Mem Load', 'kb'),
        ('PFE0 RX bps', 'bps'),
        ('PFE0 TX bps', 'bps'),
        ('PFE2 RX bps', 'bps'),
        ('PFE2 TX bps', 'bps'),
        ('m7_0', '%'),
        ('m7_1', '%'),
        ('m7_2', '%'),
        ('DDR SRAM Temperature', 'C'),
        ('A53 cluster Temperature', 'C'),
        ('HSE LLCE Temperature', 'C'),
    ]

    SJA_NB_PORTS = 11

    # Add measurements for each of the 11 ports.
    for i in range(0, SJA_NB_PORTS):
        MEASUREMENTS.append((f'Drop Delta s0 p{i}', 'Packets'))
        MEASUREMENTS.append((f'Ingress Delta s0 p{i}', 'Packets'))
        MEASUREMENTS.append((f'Egress Delta s0 p{i}', 'Packets'))
        MEASUREMENTS.append((f'Drop Counter s0 p{i}', 'Packets'))
        MEASUREMENTS.append((f'Ingress Counter s0 p{i}', 'Packets'))
        MEASUREMENTS.append((f'Egress Counter s0 p{i}', 'Packets'))

    TRANSFORMS = [
        ('Dom0 vCPU Load', '%', '100 - cpuidle', 'cpuidle', MEASUREMENTS[0][0]),
        ('Dom0 vCPU0 Load', '%', '100 - cpu0idle', 'cpu0idle', MEASUREMENTS[1][0]),
        ('Dom0 vCPU1 Load', '%', '100 - cpu1idle', 'cpu1idle', MEASUREMENTS[2][0]),
        ('Dom0 vCPU2 Load', '%', '100 - cpu2idle', 'cpu2idle', MEASUREMENTS[3][0]),
        ('Dom0 vCPU3 Load', '%', '100 - cpu3idle', 'cpu3idle', MEASUREMENTS[4][0]),
        ('Dom0 Memory Load (MB)', 'MB', 'memload / 1024',
         'memload', MEASUREMENTS[5][0]),
        ('PFE0 RX Mbps', 'Mbps', 'pfe0rx / 1024',
         'pfe0rx', MEASUREMENTS[6][0]),
        ('PFE0 TX Mbps', 'Mbps', 'pfe0tx / 1024',
         'pfe0tx', MEASUREMENTS[7][0]),
        ('PFE2 RX Mbps', 'Mbps', 'pfe2rx / 1024',
         'pfe2rx', MEASUREMENTS[8][0]),
        ('PFE2 TX Mbps', 'Mbps', 'pfe2tx / 1024', 'pfe2tx', MEASUREMENTS[9][0])
    ]


    MAX_PROPERTIES_PER_ACTION = 10
    MAX_ACTIONS_PER_TOPIC = 10

    CLIENT = boto3.client('iotsitewise')

    @staticmethod
    def __add_sitewise_header(request, **kwargs):  # pylint: disable=unused-argument
        """
        :param request:
        :param kwargs: placeholder param
        """
        request.headers.add_header('Content-type', 'application/json')

    @staticmethod
    def __create_sitewise(event, ids, response_data):  # pylint: disable=too-many-locals
        """
        Create a Model and an Asset.
        :param event: The MQTT message in json format.
        :param ids: Dictionary of resource ids.
        """
        stack_name = event['ResourceProperties']['StackName']
        property_list = []

        for name, unit in SitewiseHandler.MEASUREMENTS:
            property_list.append({
                'name': name,
                'dataType': 'DOUBLE',
                'unit': unit,
                'type': {
                    'measurement': {}
                }
            })

        for name, unit, expression, var, var_id in SitewiseHandler.TRANSFORMS:
            property_list.append({
                'name': name,
                'dataType': 'DOUBLE',
                'unit': unit,
                'type': {
                    'transform': {
                        'expression': expression,
                        'variables': [
                            {
                                'name': var,
                                'value': {
                                    'propertyId': var_id,
                                }
                            },
                        ]
                    }
                }
            })

        LOGGER.info('Creating Model...')

        model = SitewiseHandler.CLIENT.create_asset_model(
            assetModelName=stack_name + "_AssetModel",
            assetModelProperties=property_list
        )
        ids["model_id"] = model['assetModelId']
        response_data["assetModelId"] = model['assetModelId']

        try:
            SitewiseHandler.CLIENT.get_waiter(
                'asset_model_active').wait(
                    assetModelId=model['assetModelId'],
                    WaiterConfig=SitewiseHandler.WAITER_CONFIG)
        # pylint: disable=broad-except
        except Exception as exception:
            LOGGER.error(exception)
            return cfnresponse.FAILED, {}

        LOGGER.info('Model Created; Creating Asset...')

        asset = SitewiseHandler.CLIENT.create_asset(
            assetName=stack_name + "_Asset",
            assetModelId=model['assetModelId'],
        )
        ids["asset_id"] = asset['assetId']
        response_data["assetId"] = asset['assetId']

        try:
            SitewiseHandler.CLIENT.get_waiter(
                'asset_active').wait(
                    assetId=asset['assetId'],
                    WaiterConfig=SitewiseHandler.WAITER_CONFIG)
        # pylint: disable=broad-except
        except Exception as exception:
            LOGGER.error(exception)
            return cfnresponse.FAILED, {}

        LOGGER.info('Asset created; Updating Asset Properties...')

        property_list = SitewiseHandler.CLIENT.describe_asset_model(
            assetModelId=model['assetModelId']
        )['assetModelProperties']

        property_ids = {}

        for asset_property in property_list:
            property_ids[asset_property['name']] = asset_property['id']

            if 'measurement' not in asset_property['type']:
                continue

            alias = asset_property['name'].lower().replace(' ', '_')
            alias = '/telemetry/' + stack_name + '/' + alias

            SitewiseHandler.CLIENT.get_waiter(
                'asset_active').wait(
                    assetId=asset['assetId'],
                    WaiterConfig=SitewiseHandler.WAITER_CONFIG)

            SitewiseHandler.CLIENT.update_asset_property(
                assetId=asset['assetId'],
                propertyId=asset_property['id'],
                propertyAlias=alias
            )


        LOGGER.info('Asset Properties Updated.')

        return cfnresponse.SUCCESS, property_ids

    @staticmethod
    def __create_dashboard(
            dashboard_name,
            widgets_params,
            asset_id,
            project_id):
        """
        Created a SiteWise dashboard.
        :param dashboard_name: A name for the SiteWise dashboard.
        :param widgets_params: List of widget parameter touples.
        :param asset_id: Id of the SiteWise asset.
        :param project_id: Id of the SiteWise project.
        """
        widgets = []

        for widget_param in widgets_params:
            metrics = []

            for label, property_id in widget_param[5]:
                metrics.append(
                    {
                        "label": label,
                        "type": "iotsitewise",
                        "assetId": f"{asset_id}",
                        "propertyId": f"{property_id}"
                    }
                )

            widgets.append(
                {
                    "type": widget_param[6],
                    "title": widget_param[4],
                    "x": widget_param[0],
                    "y": widget_param[1],
                    "height": widget_param[2],
                    "width": widget_param[3],
                    "metrics": metrics
                }
            )

        LOGGER.info('Project created. Creating Dashboard...')

        dashboard = SitewiseHandler.CLIENT.create_dashboard(
            projectId=project_id,
            dashboardName=dashboard_name,
            dashboardDefinition=json.dumps({"widgets": widgets})
        )

        return dashboard['dashboardId']

    @staticmethod
    def __configure_main_dashboard(ids, property_ids, response_data, asset_id, project_id):
        """
        Create a dashboard with A53 telemetry data: cpu load, memory and pfe traffic.

        :param ids: Dictionary of resource ids.
        :param property_ids: List of the asset's property ids.
        :param response_data: Dictionary of resource ids to be returned.
        :param asset_id: Id of the SiteWise asset.
        :param project_id: Id of the SiteWise project.
        """

        # Declare the widgets properties from which the dashboard will be created.
        widgets_params = [
            (0, 0, 3, 6, "Dom0 vCPU Load (%)",
             [("Dom0 vCPU Load", property_ids['Dom0 vCPU Load'])],
             "monitor-line-chart"),
            (0, 3, 3, 3, "Dom0 vCPU0 Load (%)", [
                ("Dom0 vCPU0 Load", property_ids['Dom0 vCPU0 Load'])],
             "monitor-line-chart"),
            (3, 3, 3, 3, "Dom0 vCPU1 Load (%)", [
                ("Dom0 vCPU1 Load", property_ids['Dom0 vCPU1 Load'])],
             "monitor-line-chart"),
            (0, 6, 3, 3, "Dom0 vCPU2 Load (%)", [
                ("Dom0 vCPU2 Load", property_ids['Dom0 vCPU2 Load'])],
             "monitor-line-chart"),
            (3, 6, 3, 3, "Dom0 vCPU3 Load (%)", [
                ("Dom0 vCPU3 Load", property_ids['Dom0 vCPU3 Load'])],
             "monitor-line-chart"),
            (0, 9, 3, 3, "PFE0 Traffic (Mbps)", [
                ("PFE0 Rx", property_ids['PFE0 RX Mbps']),
                ("PFE0 Tx", property_ids['PFE0 TX Mbps'])],
             "monitor-line-chart"),
            (3, 9, 3, 3, "PFE2 Traffic (Mbps)", [
                ("PFE2 Rx", property_ids['PFE2 RX Mbps']),
                ("PFE2 Tx", property_ids['PFE2 TX Mbps'])],
             "monitor-line-chart"),
            (0, 12, 3, 6, "Dom0 Memory Load (MB)",
             [("Dom0 Memory Load (MB)", property_ids['Dom0 Memory Load (MB)'])],
             "monitor-line-chart"),
            (0, 15, 3, 6, "M7 Core Load", [
                ("M7 Core0 Load", property_ids["m7_0"]),
                ("M7 Core1 Load", property_ids["m7_1"]),
                ("M7 Core2 Load", property_ids["m7_2"])],
             "monitor-line-chart"),
            (0, 18, 3, 6, "Immediate Temperature", [
                ("DDR SRAM Temperature", property_ids["DDR SRAM Temperature"]),
                ("A53 cluster Temperature", property_ids["A53 cluster Temperature"]),
                ("HSE LLCE Temperature", property_ids["HSE LLCE Temperature"])],
             "monitor-line-chart"),
        ]

        dashboard_id = SitewiseHandler.__create_dashboard(
            "Dashboard",
            widgets_params,
            asset_id,
            project_id)

        ids["dashboard1_id"] = dashboard_id
        response_data['dashboard1Id'] = dashboard_id

    @staticmethod
    def __configure_sja_dashboards(ids, property_ids, response_data, asset_id, project_id):
        """
        Create dashboards with SJA telemetry: drop, ingress and egress packets
        for each switch and port.
        Multiple dashboards need to be created because each one is limited
        to a maximum of 10 widgets.
        :param ids: Dictionary of resource ids.
        :param property_ids: List of the asset's property ids.
        :param response_data: Dictionary of resource ids to be returned.
        :param asset_id: Id of the SiteWise asset.
        :param project_id: Id of the SiteWise project.
        """

        widget_y = None

        # Create multiple dashboards to contain all of the SJA switch ports.
        for sja_dashboard_id in [1, 2, 3]:
            # Create empty widget list.
            widgets_params = []
            for i in range(0, 5):
                # Position on the Y axis of the widget.
                widget_y = i * 3 + i

                # Number of SJA switch port.
                port = i + 5 * (sja_dashboard_id - 1)

                # Stop at the last port
                if port >= SitewiseHandler.SJA_NB_PORTS:
                    break

                # Create line charts to display throughput in packets.
                widgets_params.append(
                    (0, widget_y, 3, 6, f"Switch0 Port{port} Traffic (Pckts)",
                     [("Drop", property_ids[f"Drop Delta s0 p{port}"]),
                      ("Ingress", property_ids[f"Ingress Delta s0 p{port}"]),
                      ("Egress", property_ids[f"Egress Delta s0 p{port}"])],
                     "monitor-line-chart"))

                # Create PKI to display total count.
                widgets_params.append(
                    (0, widget_y + 3, 1, 6, f"Switch0 Port{port} Counter (Pckts)",
                     [("Drop", property_ids[f"Drop Counter s0 p{port}"]),
                      ("Ingress", property_ids[f"Ingress Counter s0 p{port}"]),
                      ("Egress", property_ids[f"Egress Counter s0 p{port}"])],
                     "monitor-kpi"))

            dashboard_id = SitewiseHandler.__create_dashboard(
                f'SJA1110 Dashboard {sja_dashboard_id}',
                widgets_params,
                asset_id,
                project_id)

            # Set the ids of the dashboards as number 2, 3 and 4.
            ids[f'dashboard{(sja_dashboard_id + 1)}_id'] = dashboard_id
            response_data[f'dashboard{(sja_dashboard_id + 1)}Id'] = dashboard_id

    @staticmethod
    def __create_monitor(event, ids, property_ids, response_data):
        """
        Creates a SiteWise Portal, a project and multiple dashboards.
        :param event: The MQTT message in json format.
        :param ids: Dictionary of resource ids.
        :param property_id_list: List of asset property ids.
        :param response_data: Dictionary of resource ids to be returned.
        """
        try:
            asset_id = ids["asset_id"]
        except KeyError:
            LOGGER.info("Asset ID not found (__create_monitor)")
            return cfnresponse.FAILED

        SitewiseHandler.CLIENT.meta.events.register_first(
            'before-sign.iotsitewise.*',
            SitewiseHandler.__add_sitewise_header
        )

        LOGGER.info('Creating Portal...')

        portal = SitewiseHandler.CLIENT.create_portal(
            portalName="SitewisePortal_" +
            event['ResourceProperties']['StackName'],
            portalContactEmail=event['ResourceProperties']['ContactEmail'],
            roleArn=event['ResourceProperties']['PortalRoleArn']
        )
        ids["portal_id"] = portal['portalId']
        response_data['portalId'] = portal['portalId']
        response_data['portalUrl'] = portal['portalStartUrl']

        try:
            SitewiseHandler.CLIENT.get_waiter(
                'portal_active').wait(
                    portalId=portal['portalId'],
                    WaiterConfig=SitewiseHandler.WAITER_CONFIG)
        # pylint: disable=broad-except
        except Exception as exception:
            LOGGER.error(exception)
            return cfnresponse.FAILED

        LOGGER.info('Portal created. Creating Project...')

        project = SitewiseHandler.CLIENT.create_project(
            portalId=portal['portalId'],
            projectName="Project"
        )
        ids["project_id"] = project['projectId']
        response_data['projectId'] = project['projectId']

        # Creating Main Dashboard
        SitewiseHandler.__configure_main_dashboard(
            ids, property_ids,
            response_data,
            asset_id, project['projectId'])

        # Creating Second Dashboard
        SitewiseHandler.__configure_sja_dashboards(
            ids, property_ids,
            response_data,
            asset_id, project['projectId'])

        # Associate asset to project
        SitewiseHandler.CLIENT.batch_associate_project_assets(
            projectId=project['projectId'],
            assetIds=[asset_id]
        )

        LOGGER.info('Dashboards Created.')

        return cfnresponse.SUCCESS

    @staticmethod
    def __create_topic_rules(
            event, sql_rule,
            properties, aliases,
            topic_rule_name):
        """
        Creates one or more SiteWise topic rules given a list of property values and
        their aliases. A rule is limited to a maximum of one hundred properties.
        :param event: The MQTT message in json format.
        :param sql_rule: The sql rule for the rules.
        :param properties: A list of property values.
        :param aliases: A list of property alias prefixes.
        :param topic_rule_name: The name of the topic rule.
        """
        alias_prefix = f"/telemetry/{event['ResourceProperties']['StackName']}/"
        iot_client = boto3.client('iot')
        action_list = []
        property_entry_list = []
        topic_rule_idx = 0

        for idx, property_value in enumerate(properties):
            alias_suffix = aliases[idx]

            # Append to property list
            property_entry_list.append(
                {
                    'propertyAlias': alias_prefix + alias_suffix,
                    'propertyValues': [
                        {
                            'value': {
                                'doubleValue': '${' + property_value + '}',
                            },
                            'timestamp': {
                                'timeInSeconds': '${floor(timestamp() / 1E3)}'
                            }
                        }
                    ]
                }
            )

            # When the property entry list is full or if this is the last property
            if (len(property_entry_list) == SitewiseHandler.MAX_PROPERTIES_PER_ACTION
                    or idx == len(properties) - 1):
                # Create an action with the property entries
                action_list.append(
                    {
                        'iotSiteWise': {
                            'putAssetPropertyValueEntries': property_entry_list,
                            'roleArn': event['ResourceProperties']['SiteWiseRuleRoleArn']
                        }
                    }
                )

                # Reset the property entry list
                property_entry_list = []

            # When the action list is full or if this is the last property
            if (len(action_list) == SitewiseHandler.MAX_ACTIONS_PER_TOPIC
                    or idx == len(properties) - 1):
                topic_rule_idx += 1

                # Create a topic rule with the actions
                iot_client.create_topic_rule(
                    ruleName=topic_rule_name + str(topic_rule_idx),
                    topicRulePayload={
                        'sql': sql_rule,
                        'actions': action_list
                    }
                )

                # Clear the action list
                action_list = []


    @staticmethod
    def __create_sitewise_rule(event):
        """
        Declares all the property values and aliases used in the SiteWise dashboards,
        and invokes the creation of topic rules with them.
        :param event: The MQTT message in json format.
        """
        stack_name = event['ResourceProperties']['StackName']
        sja_sql = "SELECT * FROM 's32g/sja/switch/" + stack_name + "'"
        main_sql = "SELECT * FROM '" + event['ResourceProperties']['TelemetryTopic'] + "'"

        # Properties of the main dashboard.
        main_properties = [
            'cpu_idle',
            'mem_load',
            'ddr_sram_temperature',
            'a53_cluster_temperature',
            'hse_llce_temperature',
            'ddr_sram_average_temperature',
            'a53_cluster_average_temperature',
            'hse_llce_average_temperature'
        ]

        for i in range(4):
            main_properties.append(f"cpu{i}_idle")

        for i in range(3):
            main_properties.append(f"m7_{i}")

        for i in [0, 2]:
            main_properties.append(f"pfe{i}_rx_bps")
            main_properties.append(f"pfe{i}_tx_bps")

        # Properties of the SJA dashboards.
        sja_properties = []
        sja_aliases = []

        sja_properties_suffixes = [
            "DropEventsCounter",
            "IngressPktsCounter",
            "EgressPktsCounter",
            "DropEventsDelta",
            "IngressPktsDelta",
            "EgressPktsDelta"
        ]

        sja_aliases_suffixes = [
            "drop_counter",
            "ingress_counter",
            "egress_counter",
            "drop_delta",
            "ingress_delta",
            "egress_delta"
        ]

        for port in range(11):
            for idx, property_value in enumerate(sja_properties_suffixes):
                sja_properties.append(f"s0.p{port}.{property_value}")
                sja_aliases.append(f"{sja_aliases_suffixes[idx]}_s0_p{port}")

        main_topic_rule_name = 'MainTopicRule_' + stack_name.replace('-', '_')
        sja_topic_rule_name = 'SJATopicRule_' + stack_name.replace('-', '_')

        # Main properties coincide with their aliases.
        SitewiseHandler.__create_topic_rules(
            event, main_sql,
            main_properties, main_properties,
            main_topic_rule_name)

        SitewiseHandler.__create_topic_rules(
            event, sja_sql,
            sja_properties, sja_aliases,
            sja_topic_rule_name)


    @staticmethod
    def delete_sitewise(ids):
        """
        Deletes the asset then the model.
        :param ids: Dictionary of resource ids.
        """
        model_id = None
        asset_id = None

        try:
            model_id = ids["model_id"]
            asset_id = ids["asset_id"]
        except KeyError as exception:
            LOGGER.error("Sitewise resources not found in delete_sitewise: %s", exception)

        SitewiseHandler.CLIENT = boto3.client('iotsitewise')

        if asset_id:
            LOGGER.info('Deleting Asset...')
            SitewiseHandler.CLIENT.delete_asset(
                assetId=asset_id
            )

            SitewiseHandler.CLIENT.get_waiter(
                'asset_not_exists').wait(
                    assetId=asset_id,
                    WaiterConfig=SitewiseHandler.WAITER_CONFIG)

            LOGGER.info('Asset deleted.')

        if model_id:
            LOGGER.info('Deleting Model.')
            SitewiseHandler.CLIENT.delete_asset_model(
                assetModelId=model_id
            )

    @staticmethod
    def delete_monitor(ids):
        """
        Deletes the dashboard, the project and the portal.
        :param ids: Dictionary of resource ids.
        """
        asset_id = None
        portal_id = None
        project_id = None
        dashboard_ids = []

        try:
            asset_id = ids["asset_id"]
            portal_id = ids["portal_id"]
            project_id = ids["project_id"]
            dashboard_ids.extend([val for key, val in ids.items() if key.startswith('dashboard')])
        except KeyError as exception:
            LOGGER.error("Sitewise resource id not found in delete_monitor: %s", exception)

        if project_id and asset_id:
            SitewiseHandler.CLIENT.batch_disassociate_project_assets(
                projectId=project_id,
                assetIds=[
                    asset_id,
                ]
            )

        for dashboard_id in dashboard_ids:
            SitewiseHandler.CLIENT.delete_dashboard(
                dashboardId=dashboard_id
            )
        time.sleep(2)

        if project_id:
            SitewiseHandler.CLIENT.delete_project(
                projectId=project_id
            )

        if portal_id:
            # List and remove access policies before deleting the portal
            access_policies = SitewiseHandler.CLIENT.list_access_policies(
                resourceType='PORTAL',
                resourceId=portal_id
            )
            for access_policy in access_policies['accessPolicySummaries']:
                SitewiseHandler.CLIENT.delete_access_policy(
                    accessPolicyId=access_policy['id']
                )

            SitewiseHandler.CLIENT.delete_portal(
                portalId=portal_id
            )

    @staticmethod
    def delete_topic_rules(ids):
        """
        Searches for all of the topic rules made by this stack and deletes them.
        :param ids: Dictionary of resource ids.
        """
        iot_client = boto3.client("iot")
        stack_name = ids['stack_name']

        response_iterator = iot_client.get_paginator('list_topic_rules').paginate()

        for paginator in response_iterator:
            for rule in paginator['rules']:
                if stack_name.replace('-', '_') in rule['ruleName']:
                    iot_client.delete_topic_rule(
                        ruleName=rule['ruleName']
                    )

    @staticmethod
    def create(event, response_data):
        """
        Initiates the creation of the SiteWise resources.
        :param event: The MQTT message in json dictionary format.
        :param response_data: Dictionary of resource ids to be returned.
        """
        ids = {'stack_name': event['ResourceProperties']['StackName']}

        SitewiseHandler.__create_sitewise_rule(event)

        status, property_ids = SitewiseHandler.__create_sitewise(event, ids, response_data)

        if status == cfnresponse.FAILED:
            return status

        status = SitewiseHandler.__create_monitor(event, ids, property_ids, response_data)

        return status, ids

    @staticmethod
    def delete(ids):
        """
        Initiates the deletion of the SiteWise resources.
        :param ids: dictionary of resource ids.
        """
        SitewiseHandler.delete_monitor(ids)
        SitewiseHandler.delete_sitewise(ids)
        SitewiseHandler.delete_topic_rules(ids)


def lambda_handler(event, context):
    """
    Handler function for the custom resource function.
    :param event: The MQTT message in json format.
    :param context: A Lambda context object, it provides information.
    """
    LOGGER.info('Sitewise custom function handler got event %s', json.dumps(event))

    try:
        response_data = {}

        if event['RequestType'] == 'Create':
            status, ids = SitewiseHandler.create(event, response_data)

            cfnresponse.send(
                event, context, status,
                response_data, physical_resource_id=Utils.encode_ids(ids))
        elif event['RequestType'] == 'Update':
            cfnresponse.send(
                event, context,
                cfnresponse.SUCCESS, response_data)
        elif event['RequestType'] == 'Delete':
            ids = Utils.decode_ids(event['PhysicalResourceId'])
            SitewiseHandler.delete(ids)
            cfnresponse.send(
                event, context,
                cfnresponse.SUCCESS, response_data)
        else:
            LOGGER.info('Unexpected RequestType!')
            cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data)

    # pylint: disable=broad-except
    except Exception as err:
        LOGGER.error("Sitewise custom function handler error: %s", err)
        response_data = {"Data": str(err)}
        cfnresponse.send(event, context, cfnresponse.FAILED, response_data)
