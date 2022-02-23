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

Copyright 2021-2022 NXP
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
    SITEWISE_CLIENT = boto3.client('iotsitewise')
    IOT_CLIENT = boto3.client('iot')

    def __init__(self, configs):
        """
        :param configs: sitewise configuration for each platform device
        """
        self.configs = configs
        self.measurements = self.configs.get('MEASUREMENTS')

        # Append measurements data to respective sja port items.
        for i in range(0, self.configs['SJA_NB_PORTS']):
            self.measurements.update(dict.fromkeys(
                [
                    f'Drop Delta s0 p{i}',
                    f'Ingress Delta s0 p{i}',
                    f'Egress Delta s0 p{i}',
                    f'Drop Counter s0 p{i}',
                    f'Ingress Counter s0 p{i}',
                    f'Egress Counter s0 p{i}'
                ], 'Packets')
            )
        self.transforms = [tuple(el) for el in self.configs.get('TRANSFORMS')]

    def __create_asset(self, stack_name, model, ids, response_data):
        """
        Create asset from asset model
        :param stack-name: The name of the deployed CloudFormation stack.
        :param model: Asset model
        :param ids: Dictionary of resource ids.
        :param response_data: Dictionary of resource ids to be returned.
        """
        asset = self.SITEWISE_CLIENT.create_asset(
            assetName=f"{stack_name}_Asset",
            assetModelId=model['assetModelId'],
        )
        ids["asset_id"] = asset['assetId']
        response_data["assetId"] = asset['assetId']

        try:
            self.SITEWISE_CLIENT.get_waiter(
                'asset_active').wait(
                    assetId=asset['assetId'],
                    WaiterConfig=self.configs['WAITER_CONFIG'])
            return asset
        # pylint: disable=broad-except
        except Exception as exception:
            LOGGER.error(exception)
            return cfnresponse.FAILED, {}

    def __create_asset_model(self, stack_name, ids, response_data, property_list):
        """
        Create asset model
        :param stack-name: The name of the deployed CloudFormation stack.
        :param ids: Dictionary of resource ids.
        :param response_data: Dictionary of resource ids to be returned.
        :param property_list: Asset properties (Measurements and Transforms)
        """

        model = self.SITEWISE_CLIENT.create_asset_model(
            assetModelName=f"{stack_name}_AssetModel",
            assetModelProperties=property_list
        )
        ids["model_id"] = model['assetModelId']
        response_data["assetModelId"] = model['assetModelId']

        try:
            self.SITEWISE_CLIENT.get_waiter(
                'asset_model_active').wait(
                    assetModelId=model['assetModelId'],
                    WaiterConfig=self.configs['WAITER_CONFIG'])
            return model
        # pylint: disable=broad-except
        except Exception as exception:
            LOGGER.error(exception)
            return cfnresponse.FAILED, {}

    def __create_property_list(self, property_list):
        """
        This wrapper method is used to generate the properties list
        from sitewise configuration data
        :param property_list: Asset properties (Measurements and Transforms)
        """
        for name, unit in self.measurements.items():
            property_list.append({
                'name': name,
                'dataType': 'DOUBLE',
                'unit': unit,
                'type': {
                    'measurement': {}
                }
            })

        for name, unit, expression, var, var_id in self.transforms:
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

    def __update_asset_properties(self, stack_name, model, property_ids, asset):
        """
        Update asset properties
        :param stack-name: The name of the deployed CloudFormation stack.
        :param model: The Sitewise model
        :param property_ids: Dictionary of property ids
        :param asset: The Sitewise asset
        """

        property_list = self.SITEWISE_CLIENT.describe_asset_model(
            assetModelId=model['assetModelId']
        )['assetModelProperties']

        for asset_property in property_list:
            property_ids[asset_property['name']] = asset_property['id']

            if 'measurement' not in asset_property['type']:
                continue

            alias = asset_property['name'].lower().replace(' ', '_')
            alias = f"/telemetry/{stack_name}/{alias}"

            self.SITEWISE_CLIENT.get_waiter(
                'asset_active').wait(
                    assetId=asset['assetId'],
                    WaiterConfig=self.configs['WAITER_CONFIG'])

            self.SITEWISE_CLIENT.update_asset_property(
                assetId=asset['assetId'],
                propertyId=asset_property['id'],
                propertyAlias=alias
            )

    def __create_sitewise(self, event, ids, response_data):
        """
        Create a Model and an Asset.
        :param event: The MQTT message in json format.
        :param ids: Dictionary of resource ids.
        :param response_data: Dictionary of resource ids to be returned.
        """
        property_list = []
        property_ids = {}
        stack_name = event['ResourceProperties']['StackName']

        self.__create_property_list(property_list)

        LOGGER.info('Creating Model...')

        model = self.__create_asset_model(stack_name, ids, response_data, property_list)

        LOGGER.info('Model Created; Creating Asset...')

        asset = self.__create_asset(stack_name, model, ids, response_data)

        LOGGER.info('Asset created; Updating Asset Properties...')

        self.__update_asset_properties(stack_name, model, property_ids, asset)

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
        :param widgets_params: List of widget parameter tuples.
        :param asset_id: Id of the SiteWise asset.
        :param project_id: Id of the SiteWise project.
        """
        widgets = []

        for widget_param in widgets_params:
            metrics = []

            for metric in widget_param['metrics'].values():
                metrics.append(
                    {
                        "label": metric['label'],
                        "type": "iotsitewise",
                        "assetId": asset_id,
                        "propertyId": metric['property_ids']
                    }
                )

            widgets.append(
                {
                    **widget_param,
                    "metrics": metrics
                }
            )

        dashboard = SitewiseHandler.SITEWISE_CLIENT.create_dashboard(
            projectId=project_id,
            dashboardName=dashboard_name,
            dashboardDefinition=json.dumps({"widgets": widgets})
        )

        return dashboard['dashboardId']

    @staticmethod
    def update_widgets_params(widgets, property_ids):
        """
        Update property ids in widgets params
        :param widgets: List of widget parameter dictionaries.
        :param property_ids: List of the asset's property ids.

        return: List of updated widget parameter dictionaries
        """
        for widget in widgets:
            for item in widget['metrics'].values():
                item['property_ids'] = property_ids.get(item['property_ids'])
        return widgets

    def __configure_soc_dashboard(self, **kwargs):
        """
        Create a dashboard with memory loads and pfe traffic widgets.
        """
        # Declare the widgets properties from which the dashboard will be created.
        widgets = self.configs['SOC_WIDGETS_PARAMS'].values()

        widgets_params = SitewiseHandler.update_widgets_params(widgets, kwargs["property_ids"])

        dashboard_id = SitewiseHandler.__create_dashboard(
            self.configs['SOC_DB'],
            widgets_params,
            kwargs["asset_id"],
            kwargs["project_id"])

        # Save the dashboard id in the database
        kwargs["ids"][self.configs['SOC_IDS_KEY']] = dashboard_id
        kwargs["response_data"][self.configs['SOC_RESPONSE_DATA_KEY']] = dashboard_id

    def __configure_core_loads_dashboard(self, **kwargs):
        """
        Create a dashboard with dom0 vcpu and m7 core-load widgets.
        """
        # Declare the widgets properties from which the dashboard will be created.
        widgets = self.configs['CORE_LOAD_WIDGETS_PARAMS'].values()

        widgets_params = SitewiseHandler.update_widgets_params(widgets, kwargs["property_ids"])

        dashboard_id = SitewiseHandler.__create_dashboard(
            self.configs['CORE_LOADS_DB'],
            widgets_params,
            kwargs["asset_id"],
            kwargs["project_id"])

        # Save the dashboard id in the database
        kwargs["ids"][self.configs['CORE_LOADS_IDS_KEY']] = dashboard_id
        kwargs["response_data"][self.configs['CORE_LOADS_RESPONSE_DATA_KEY']] = dashboard_id

    def __configure_sja_dashboards(self, **kwargs):
        """
        Create dashboards with SJA telemetry: drop, ingress and egress packets
        for each switch and port.
        Multiple dashboards need to be created because each one is limited
        to a maximum of 10 widgets.
        """

        widget_y = None

        # List of the asset's property ids.
        property_ids = kwargs["property_ids"]

        # Create multiple dashboards to contain all of the SJA switch ports.
        for sja_dashboard_id in self.configs['SJA_DASHBOARD_IDS']:
            # Create empty widget list.
            widgets_params = []
            for widget_idx in range(0, int(self.configs['MAX_WIDGETS_PER_SJA_DASHBOARD'])):
                # Position on the Y axis of the widget.
                widget_y = widget_idx * 3 + widget_idx

                # Number of SJA switch port.
                port = widget_idx + int(self.configs['MAX_WIDGETS_PER_SJA_DASHBOARD']) * \
                           (sja_dashboard_id - 1)

                # Stop at the last port
                if port >= self.configs['SJA_NB_PORTS']:
                    break

                # Create line charts to display throughput in packets.
                widgets_params.append(
                    {
                        "x": 0,
                        "y": widget_y,
                        "height": 3,
                        "width": 6,
                        "title": f"Switch0 Port{port} Traffic (Pckts)",
                        "metrics": {
                            "Drop": {
                                "label": "Drop",
                                "property_ids": property_ids[f"Drop Delta s0 p{port}"]
                            },
                            "Ingress": {
                                "label": "Ingress",
                                "property_ids": property_ids[f"Ingress Delta s0 p{port}"]
                            },
                            "Egress": {
                                "label": "Egress",
                                "property_ids": property_ids[f"Egress Delta s0 p{port}"]
                            }
                        },
                        "type": "monitor-line-chart"
                    })

                # Create PKI to display total count.
                widgets_params.append(
                    {
                        "x": 0,
                        "y": widget_y+3,
                        "height": 1,
                        "width": 6,
                        "title": f"Switch0 Port{port} Counter (Pckts)",
                        "metrics": {
                            "Drop": {
                                "label": "Drop",
                                "property_ids": property_ids[f"Drop Counter s0 p{port}"]
                            },
                            "Ingress": {
                                "label": "Ingress",
                                "property_ids": property_ids[f"Ingress Counter s0 p{port}"]
                            },
                            "Egress": {
                                "label": "Egress",
                                "property_ids": property_ids[f"Egress Counter s0 p{port}"]
                            }
                        },
                        "type": "monitor-kpi"
                    })

            dashboard_id = SitewiseHandler.__create_dashboard(
                f'SJA1110 Dashboard {sja_dashboard_id}',
                widgets_params,
                kwargs["asset_id"],
                kwargs["project_id"])

            # Save the dashboard id in the database
            idx = sja_dashboard_id - 1 + self.configs['SJA_DASHBOARD_IDX_START']
            kwargs["ids"][f'dashboard{idx}_id'] = dashboard_id
            kwargs["response_data"][f'dashboard{idx}Id'] = dashboard_id

    def __create_monitor(self, event, ids, property_ids, response_data):
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

        LOGGER.info('Creating Portal...')

        portal = self.SITEWISE_CLIENT.create_portal(
            portalName="SiteWisePortal_" +
            event['ResourceProperties']['StackName'],
            portalContactEmail=event['ResourceProperties']['ContactEmail'],
            roleArn=event['ResourceProperties']['PortalRoleArn']
        )
        ids["portal_id"] = portal['portalId']
        response_data['portalId'] = portal['portalId']
        response_data['portalUrl'] = portal['portalStartUrl']

        try:
            self.SITEWISE_CLIENT.get_waiter(
                'portal_active').wait(
                    portalId=portal['portalId'],
                    WaiterConfig=self.configs['WAITER_CONFIG'])
        # pylint: disable=broad-except
        except Exception as exception:
            LOGGER.error(exception)
            return cfnresponse.FAILED

        LOGGER.info('Portal created. Creating Project...')

        project = self.SITEWISE_CLIENT.create_project(
            portalId=portal['portalId'],
            projectName="Project"
        )
        ids["project_id"] = project['projectId']
        response_data['projectId'] = project['projectId']

        LOGGER.info('Creating the Core Loads Dashboard')
        # Creating Core Loads Dashboard
        self.__configure_core_loads_dashboard(
            ids=ids, property_ids=property_ids,
            response_data=response_data,
            asset_id=asset_id, project_id=project['projectId'])

        LOGGER.info('Creating the SOC Dashboard')
        # Creating SOC Dashboard
        self.__configure_soc_dashboard(
            ids=ids, property_ids=property_ids,
            response_data=response_data,
            asset_id=asset_id, project_id=project['projectId'])

        LOGGER.info('Creating the SJA Dashboards')
        # Creating SJA Dashboards
        self.__configure_sja_dashboards(
            ids=ids, property_ids=property_ids,
            response_data=response_data,
            asset_id=asset_id, project_id=project['projectId'])

        # Associate asset to project
        self.SITEWISE_CLIENT.batch_associate_project_assets(
            projectId=project['projectId'],
            assetIds=[asset_id]
        )

        LOGGER.info('Dashboards Created.')

        return cfnresponse.SUCCESS

    def __create_topic_rules(self, **kwargs):
        """
        Creates one or more SiteWise topic rules given a list of property values and
        their aliases. A rule is limited to a maximum of one hundred properties.
        """
        # The MQTT message in json format.
        event = kwargs["event"]

        alias_prefix = f"/telemetry/{event['ResourceProperties']['StackName']}/"
        action_list = []
        property_entry_list = []
        topic_rule_idx = 0

        for idx, property_value in enumerate(kwargs["properties"]):
            alias_suffix = kwargs["aliases"][idx]

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
            if (len(property_entry_list) == self.configs['MAX_PROPERTIES_PER_ACTION']
                    or idx == len(kwargs["properties"]) - 1):
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
            if (len(action_list) == self.configs['MAX_ACTIONS_PER_TOPIC']
                    or idx == len(kwargs["properties"]) - 1):
                topic_rule_idx += 1

                # Create a topic rule with the actions
                self.IOT_CLIENT.create_topic_rule(
                    ruleName=kwargs["topic_rule_name"] + str(topic_rule_idx),
                    topicRulePayload={
                        'sql': kwargs["sql_rule"],
                        'actions': action_list
                    }
                )

                # Clear the action list
                action_list = []

    def __create_sitewise_rule(self, event):
        """
        Declares all the property values and aliases used in the SiteWise dashboards,
        and invokes the creation of topic rules with them.
        :param event: The MQTT message in json format.
        """
        stack_name = event['ResourceProperties']['StackName']
        sja_sql = "SELECT * FROM 's32g/sja/switch/" + stack_name + "'"
        main_sql = "SELECT * FROM '" + \
            event['ResourceProperties']['TelemetryTopic'] + "'"

        # Properties of the SJA dashboards.
        sja_properties = []
        sja_aliases = []

        # Properties of the main dashboard.
        main_properties = self.configs['MAIN_PROPERTIES']

        for i in range(self.configs['CPU_CORES_NUM']):
            main_properties.append(f"dom0_vcpu{i}_idle")

        for i in range(self.configs['M7_CORES_NUM']):
            main_properties.append(f"m7_{i}")

        for i in self.configs['PFE_PORTS']:
            main_properties.append(f"pfe{i}_rx_bps")
            main_properties.append(f"pfe{i}_tx_bps")

        # Update properties of the SJA dashboards.
        for port in range(self.configs['SJA_NB_PORTS']):
            for idx, property_value in enumerate(self.configs['SJA_PROPERTIES_SUFFIXES']):
                sja_properties.append(f"s0.p{port}.{property_value}")
                sja_aliases.append(f"{self.configs['SJA_ALIASES_SUFFIXES'][idx]}_s0_p{port}")

        main_topic_rule_name = 'MainTopicRule_' + stack_name.replace('-', '_')
        sja_topic_rule_name = 'SJATopicRule_' + stack_name.replace('-', '_')

        # Main properties coincide with their aliases.
        self.__create_topic_rules(
            event=event, sql_rule=main_sql,
            properties=main_properties, aliases=main_properties,
            topic_rule_name=main_topic_rule_name)

        self.__create_topic_rules(
            event=event, sql_rule=sja_sql,
            properties=sja_properties, aliases=sja_aliases,
            topic_rule_name=sja_topic_rule_name)

    def delete_sitewise(self, ids):
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

        if asset_id:
            LOGGER.info('Deleting Asset...')
            self.SITEWISE_CLIENT.delete_asset(
                assetId=asset_id
            )

            self.SITEWISE_CLIENT.get_waiter(
                'asset_not_exists').wait(
                    assetId=asset_id,
                    WaiterConfig=self.configs['WAITER_CONFIG'])

            LOGGER.info('Asset deleted.')

        if model_id:
            LOGGER.info('Deleting Model.')
            self.SITEWISE_CLIENT.delete_asset_model(
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
            SitewiseHandler.SITEWISE_CLIENT.batch_disassociate_project_assets(
                projectId=project_id,
                assetIds=[
                    asset_id,
                ]
            )

        for dashboard_id in dashboard_ids:
            SitewiseHandler.SITEWISE_CLIENT.delete_dashboard(
                dashboardId=dashboard_id
            )
        time.sleep(2)

        if project_id:
            SitewiseHandler.SITEWISE_CLIENT.delete_project(
                projectId=project_id
            )

        if portal_id:
            # List and remove access policies before deleting the portal
            access_policies = SitewiseHandler.SITEWISE_CLIENT.list_access_policies(
                resourceType='PORTAL',
                resourceId=portal_id
            )
            for access_policy in access_policies['accessPolicySummaries']:
                SitewiseHandler.SITEWISE_CLIENT.delete_access_policy(
                    accessPolicyId=access_policy['id']
                )

            SitewiseHandler.SITEWISE_CLIENT.delete_portal(
                portalId=portal_id
            )

    @staticmethod
    def delete_topic_rules(ids):
        """
        Searches for all of the topic rules made by this stack and deletes them.
        :param ids: Dictionary of resource ids.
        """
        stack_name = ids['stack_name']

        response_iterator = SitewiseHandler.IOT_CLIENT.get_paginator('list_topic_rules').paginate()

        for paginator in response_iterator:
            for rule in paginator['rules']:
                if stack_name.replace('-', '_') in rule['ruleName']:
                    SitewiseHandler.IOT_CLIENT.delete_topic_rule(
                        ruleName=rule['ruleName']
                    )

    def create(self, event, response_data):
        """
        Initiates the creation of the SiteWise resources.
        :param event: The MQTT message in json dictionary format.
        :param response_data: Dictionary of resource ids to be returned.
        """
        ids = {'stack_name': event['ResourceProperties']['StackName']}

        self.__create_sitewise_rule(event)

        status, property_ids = self.__create_sitewise(event, ids, response_data)

        if status == cfnresponse.FAILED:
            return status

        status = self.__create_monitor(event, ids, property_ids, response_data)

        return status, ids

    def delete(self, ids):
        """
        Initiates the deletion of the SiteWise resources.
        :param ids: dictionary of resource ids.
        """
        SitewiseHandler.delete_monitor(ids)
        self.delete_sitewise(ids)
        SitewiseHandler.delete_topic_rules(ids)


def lambda_handler(event, context):
    """
    Handler function for the custom resource function.
    :param event: The MQTT message in json format.
    :param context: A Lambda context object, it provides information.
    """
    LOGGER.info('Sitewise custom function handler got event %s', json.dumps(event))
    device_type = event['ResourceProperties']['DeviceType']
    configs = Utils.parse_sitewise_config('sitewise_config.json', device_type)
    sitewise_handler = SitewiseHandler(configs)

    try:
        response_data = {}

        if event['RequestType'] == 'Create':
            status, ids = sitewise_handler.create(event, response_data)
            cfnresponse.send(
                event, context, status,
                response_data, physical_resource_id=Utils.encode_ids(ids))
        elif event['RequestType'] == 'Update':
            cfnresponse.send(
                event, context,
                cfnresponse.SUCCESS, response_data)
        elif event['RequestType'] == 'Delete':
            ids = Utils.decode_ids(event['PhysicalResourceId'])
            sitewise_handler.delete(ids)
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
