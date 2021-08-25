#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
A custom function which creates a custom CloudFormation resource.
Implements the 'create' and 'delete' events.
When 'create' is invoked it creates a Greengrass group (and its associated
resources: a thing, a core, group definitions) and a SiteWise dashboard
(and its associated resources: a model, an asset, a portal, a project)
When 'delete' is invoked it handles the deletion of all resources
created by this function.

Copyright 2021 NXP
"""

import json
import logging
import time

import boto3
import cfnresponse

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)


class Utils:
    """
    Functions that transform a dictionary into a string, and vice versa.
    """
    @staticmethod
    def encode_ids(ids_dict):
        """
        Packs dictionary ids into a id string
        :param ids_dict: Dictionary of resource ids
        :type ids_dict: dict
        """
        ids_str = ""

        for key in ids_dict:
            ids_str += key + ":" + ids_dict[key] + "|"

        return ids_str[:-1]

    @staticmethod
    def decode_ids(ids_str):
        """
        Unpacks ids_str into a dictionary of resource ids

        :param ids_str: Id of the custom resource created by this function.
        :type ids_str: string
        """
        key_values = ids_str.split("|")
        ids_dict = {}

        for entry in key_values:
            key, _, value = entry.partition(":")

            ids_dict[key] = value

        return ids_dict


class GreengrassGroupHandler:
    """
    Handles the create and delete events for the Greengrass Group resources.
    """

    CLIENT = boto3.client("greengrass")

    @staticmethod
    def attach_service_role(event):
        """
        Check if a GreenGrass service role is associated to the account,
        if not we associate the service role created by the stack to the account.
        The service role is set to persist after the stack deletion.
        """
        service_role_arn = event['ResourceProperties']['ServiceRoleArn']
        service_role_name = event['ResourceProperties']['ServiceRoleName']
        service_role_policy_name = event['ResourceProperties']['ServiceRolePolicyName']

        # Check if service role is associated
        try:
            GreengrassGroupHandler.CLIENT.get_service_role_for_account()
        except: # pylint: disable=bare-except
            GreengrassGroupHandler.CLIENT.associate_service_role_to_account(
                RoleArn=service_role_arn
            )

            return

        # Deleting the service role when it is not needed.
        iam_client = boto3.client('iam')

        iam_client.delete_role_policy(
            RoleName=service_role_name,
            PolicyName=service_role_policy_name
        )

        iam_client.delete_role(
            RoleName=service_role_name
        )

    @staticmethod
    def create(event, ids, response_data):
        """
        Create Core Thing, Greengrass Group and its definitions.
        :param event: The MQTT message in json dictionary format.
        :param ids: dictionary of resource ids.
        """
        resource_property = event['ResourceProperties']

        certificate_arn = resource_property['CertificateArn']
        stack_name = resource_property['StackName']
        telemetry_topic = resource_property['TelemetryTopic']
        thing_arn = resource_property['ThingArn']
        function_arn = resource_property['TelemetryLambdaArn']

        core = GreengrassGroupHandler.CLIENT.create_core_definition(
            InitialVersion={
                'Cores': [
                    {
                        'CertificateArn': certificate_arn,
                        'Id': stack_name + "_CoreThing",
                        'SyncShadow': False,
                        'ThingArn': thing_arn
                    },
                ]
            },
            Name='CoreDefinition'
        )
        ids["core_id"] = core['Id']

        function = GreengrassGroupHandler.CLIENT.create_function_definition(
            InitialVersion={
                'DefaultConfig': {
                    'Execution': {
                        'IsolationMode': 'NoContainer'
                    }
                },
                'Functions': [
                    {
                        'FunctionArn': function_arn,
                        'FunctionConfiguration': {
                            'EncodingType': 'json',
                            'Environment': {
                                'Execution': {
                                    'IsolationMode': 'NoContainer'
                                },
                                'Variables': {
                                    'telemetryTopic': telemetry_topic
                                }
                            },
                            'Pinned': True,
                            'Timeout': 3000
                        },
                        'Id': stack_name + "_greengrass_function_id"
                    },
                ]
            },
            Name='Telemetry'
        )
        ids["function_id"] = function['Id']

        subscription = GreengrassGroupHandler.CLIENT.create_subscription_definition(
            InitialVersion={
                'Subscriptions': [
                    {
                        'Id': 'lambda2cloud1',
                        'Source': function_arn,
                        'Subject': telemetry_topic,
                        'Target': 'cloud'
                    },
                    {
                        'Id': 'lambda2cloud2',
                        'Source': function_arn,
                        'Subject': telemetry_topic + "/uuid",
                        'Target': 'cloud'
                    },
                    {
                        'Id': 'cloud2lambda',
                        'Source': 'cloud',
                        'Subject': telemetry_topic + "/config",
                        'Target': function_arn
                    }
                ]
            },
            Name='SubscriptionDefinition'
        )
        ids["subscription_id"] = subscription['Id']

        logger = GreengrassGroupHandler.CLIENT.create_logger_definition(
            InitialVersion={
                'Loggers': [
                    {
                        'Component': 'GreengrassSystem',
                        'Id': 'gg_logger',
                        'Level': 'INFO',
                        'Space': 128,
                        'Type': 'FileSystem'
                    },
                    {
                        'Component': 'Lambda',
                        'Id': 'lambda_logger',
                        'Level': 'INFO',
                        'Space': 128,
                        'Type': 'FileSystem'
                    }
                ]
            },
            Name='LoggerDefinition'
        )
        ids["logger_id"] = logger['Id']

        group = GreengrassGroupHandler.CLIENT.create_group(
            InitialVersion={
                'CoreDefinitionVersionArn': core['LatestVersionArn'],
                'FunctionDefinitionVersionArn': function['LatestVersionArn'],
                'LoggerDefinitionVersionArn': logger['LatestVersionArn'],
                'SubscriptionDefinitionVersionArn': subscription['LatestVersionArn']
            },
            Name=stack_name + "_Group"
        )
        ids["group_id"] = group['Id']

        # Save the id of the group to be outputted by the cfn stack.
        response_data["GroupId"] = group['Id']

    @staticmethod
    def delete(ids):
        """
        Deletes Core Thing, Greengrass Group definitions and then the group.
        :param ids: dictionary of resource ids.
        """
        core_id = ids["core_id"]
        function_id = ids["function_id"]
        subscription_id = ids["subscription_id"]
        logger_id = ids["logger_id"]
        group_id = ids["group_id"]

        LOGGER.info("Initiated Greengrass Group deletion.")

        try:
            reset = GreengrassGroupHandler.CLIENT.reset_deployments(
                GroupId=group_id,
                Force=True
            )

            while True:
                time.sleep(1)

                status = GreengrassGroupHandler.CLIENT.get_deployment_status(
                    DeploymentId=reset['DeploymentId'],
                    GroupId=group_id
                )

                if status['DeploymentStatus'] in {'Success', 'Failure'}:
                    break
        # pylint: disable=broad-except
        except Exception as exception:
            LOGGER.error("Group deployment reset failed with exception: %s", exception)

        GreengrassGroupHandler.CLIENT.delete_core_definition(
            CoreDefinitionId=core_id
        )

        GreengrassGroupHandler.CLIENT.delete_function_definition(
            FunctionDefinitionId=function_id
        )

        GreengrassGroupHandler.CLIENT.delete_logger_definition(
            LoggerDefinitionId=logger_id
        )

        GreengrassGroupHandler.CLIENT.delete_subscription_definition(
            SubscriptionDefinitionId=subscription_id
        )

        GreengrassGroupHandler.CLIENT.delete_group(
            GroupId=group_id
        )

        LOGGER.info("Greengrass Group deleted.")


class SitewiseHandler:
    """
    Handles the create and delete events for the sitewise resoruces.
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
        ('Memory Load', 'kb'),
        ('PFE0 RX bps', 'bps'),
        ('PFE0 TX bps', 'bps'),
        ('PFE2 RX bps', 'bps'),
        ('PFE2 TX bps', 'bps'),
        ('m7_0', '%'),
        ('m7_1', '%'),
        ('m7_2', '%'),
        ('Immediate Temperature 0', 'C'),
        ('Immediate Temperature 1', 'C'),
        ('Immediate Temperature 2', 'C'),
    ]

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

    CLIENT = boto3.client('iotsitewise')

    @staticmethod
    def _add_sitewise_header(request, **kwargs):  # pylint: disable=unused-argument
        """
        :param request:
        :param kwargs: placeholder param
        """
        request.headers.add_header('Content-type', 'application/json')

    @staticmethod
    def create_sitewise(event, ids, response_data):  # pylint: disable=too-many-locals
        """
        Create a Model and an Asset.
        :param event: The MQTT message in json format.
        :param ids: dictionary of resource ids.
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
    def create_monitor(event, ids, property_ids, response_data):
        """
        Creates a SiteWise Portal, then a project and a dashboard.
        :param event: The MQTT message in json format.
        :param ids: dictionary of resource ids.
        :param property_id_list: list of asset property ids
        """
        try:
            asset_id = ids["asset_id"]
        except KeyError:
            LOGGER.info("Asset ID not found (create_monitor)")
            return cfnresponse.FAILED

        SitewiseHandler.CLIENT.meta.events.register_first(
            'before-sign.iotsitewise.*',
            SitewiseHandler._add_sitewise_header
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
            (0, 9, 3, 3, "PFE0 Received (Mbps)", [
                ("PFE0 Rx", property_ids['PFE0 RX Mbps']),
                ("PFE0 Tx", property_ids['PFE0 TX Mbps'])],
                "monitor-line-chart"),
            (3, 9, 3, 3, "PFE2 Received (Mbps)", [
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
                ("Immediate temperature in site 0", property_ids["Immediate Temperature 0"]),
                ("Immediate temperature in site 1", property_ids["Immediate Temperature 1"]),
                ("Immediate temperature in site 2", property_ids["Immediate Temperature 2"])],
                "monitor-line-chart"),
        ]

        widgets = []

        for widget_param in widgets_params:
            metrics = []

            for label, property_id in widget_param[5]:
                metrics.append(
                    {
                        "label": label,
                        "type": "iotsitewise",
                        "assetId": "{}".format(asset_id),
                        "propertyId": "{}".format(property_id)
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
            projectId=project['projectId'],
            dashboardName="Dashboard",
            dashboardDefinition=json.dumps({"widgets": widgets})
        )
        ids["dashboard_id"] = dashboard['dashboardId']
        response_data['dashboardId'] = dashboard['dashboardId']

        SitewiseHandler.CLIENT.batch_associate_project_assets(
            projectId=project['projectId'],
            assetIds=[asset_id]
        )

        LOGGER.info('Dashboard Created.')

        return cfnresponse.SUCCESS

    @staticmethod
    def delete_sitewise(ids):
        """
        Deletes the asset then the model.
        :param ids: dictionary of resource ids.
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
        :param ids: dictionary of resource ids.
        """
        asset_id = None
        portal_id = None
        project_id = None
        dashboard_id = None

        try:
            asset_id = ids["asset_id"]
            portal_id = ids["portal_id"]
            project_id = ids["project_id"]
            dashboard_id = ids["dashboard_id"]
        except KeyError as exception:
            LOGGER.error("Sitewise resources not found in delete_monitor: %s", exception)

        if project_id and asset_id:
            SitewiseHandler.CLIENT.batch_disassociate_project_assets(
                projectId=project_id,
                assetIds=[
                    asset_id,
                ]
            )

        if dashboard_id:
            SitewiseHandler.CLIENT.delete_dashboard(
                dashboardId=dashboard_id
            )

        if project_id:
            SitewiseHandler.CLIENT.delete_project(
                projectId=project_id
            )

        if portal_id:
            SitewiseHandler.CLIENT.delete_portal(
                portalId=portal_id
            )

    @staticmethod
    def create(event, ids, response_data):
        """
        :param event: The MQTT message in json dictionary format.
        :param ids: dictionary of resource ids.
        """
        status, property_ids = SitewiseHandler.create_sitewise(event, ids, response_data)

        if status == cfnresponse.FAILED:
            return status

        status = SitewiseHandler.create_monitor(event, ids, property_ids, response_data)

        return status

    @staticmethod
    def delete(ids):
        """
        :param ids: dictionary of resource ids.
        """
        SitewiseHandler.delete_monitor(ids)
        SitewiseHandler.delete_sitewise(ids)


def lambda_handler(event, context):
    """
    Handler function for the custom resource function.
    :param event: The MQTT message in json format.
    :param context: A Lambda context object, it provides information.
    """
    LOGGER.info('got event %s', json.dumps(event))

    try:
        response_data = {}

        if event['RequestType'] == 'Create':
            ids = {}

            GreengrassGroupHandler.attach_service_role(event)

            GreengrassGroupHandler.create(event, ids, response_data)
            status = SitewiseHandler.create(event, ids, response_data)

            cfnresponse.send(
                event, context, status,
                response_data, physical_resource_id=Utils.encode_ids(ids))

        elif event['RequestType'] == 'Update':
            cfnresponse.send(
                event, context, cfnresponse.SUCCESS, response_data)

        elif event['RequestType'] == 'Delete':
            ids = Utils.decode_ids(event['PhysicalResourceId'])

            SitewiseHandler.delete(ids)
            GreengrassGroupHandler.delete(ids)

            cfnresponse.send(
                event, context, cfnresponse.SUCCESS, response_data)

        else:
            LOGGER.info('Unexpected RequestType!')
            cfnresponse.send(
                event, context, cfnresponse.SUCCESS, response_data)

    # pylint: disable=broad-except
    except Exception as err:
        LOGGER.error(err)
        response_data = {"Data": str(err)}
        cfnresponse.send(event, context, cfnresponse.FAILED, response_data)
