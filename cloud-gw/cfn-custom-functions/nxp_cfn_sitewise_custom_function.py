#!/usr/bin/env python3
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

Copyright 2021-2024 NXP
"""
import json
import time

import boto3
import cfnresponse

from cfn_utils import Utils, LOGGER


class SitewiseHandler:
    """
    Handles the create and delete events for the sitewise resources.
    """
    SITEWISE_CLIENT = boto3.client('iotsitewise')
    IOT_CLIENT = boto3.client('iot')
    DATA_TYPE_DICT = {
        'DOUBLE': 'doubleValue',
        'STRING': 'stringValue',
        'INTEGER': 'integerValue',
        'BOOLEAN': 'booleanValue'
    }

    def __init__(self, configs):
        """
        :param configs: sitewise configuration for each platform device
        """
        self.configs = configs

    @staticmethod
    def __create_properties_from_template(templates, properties, p_type):
        """
        Parses templates and creates the asset properties
        themselves by replacing the substitution patterns from the template
        with the given values.
        :param templates: The template for creating asset properties
        :param properties: A dictionary containing the asset properties
        :param p_type: The type of the properties
        """
        rule_property_list = []

        # Get the values for the substitution patterns
        substitution_dict = {}
        for _, subst in templates['substitutions'].items():
            substitution_dict[subst['pattern']] = subst['val_list']

        # Substitute the patterns with the values for each template
        for t_id, template in templates['templates'].items():
            # For each substitution pattern
            for value in substitution_dict.get(template['pattern'], []):
                p_name = template['name'].replace(template['pattern'], str(value))

                properties[p_name] = {
                    'property': {
                        'name': p_name,
                        'dataType': template.get('datatype', 'DOUBLE'),
                        'unit': template['unit'].replace(template['pattern'], str(value))
                    },
                    'alias': t_id.replace(template['pattern'], str(value))
                }

                if p_type == 'measurement':
                    # Set the property type as a measurement
                    properties[p_name]['property']['type'] = {'measurement': {}}
                    # Save the property for the routing rule
                    rule_property_list.append(p_name)
                elif p_type == 'transform':
                    # Set the property type as a transform
                    properties[p_name]['property']['type'] = {
                        'transform': {
                            'expression': template['expression'].replace(
                                template['pattern'], str(value)),
                            'variables': [
                                {
                                    'name': template['var'].replace(
                                        template['pattern'], str(value)),
                                    'value': {
                                        'propertyId': template['var_id'].replace(
                                            template['pattern'], str(value)),
                                    }
                                },
                            ]
                        }
                    }

        return rule_property_list

    def __parse_properties(self, properties, topic_rules):
        """
        Parses all of the sitewise dashboards and saves all of the
        asset's properties in a dictionary.
        :param properties: A dictionary containing the asset properties
        :param topic_rules: A dictionary containing the routing rules
        """
        for _, dashboard in self.configs['dashboards'].items():
            for dashboard_topic_rule in dashboard['topic_rules']:
                # Create entry in the routing rule
                if dashboard_topic_rule['mqtt_topic_suffix'] not in topic_rules:
                    topic_rules[dashboard_topic_rule['mqtt_topic_suffix']] = {
                        'properties': [],
                        'use_cloud_timestamp': dashboard_topic_rule.get('use_cloud_timestamp', True)
                    }

                # Retrieve the Measurements
                for m_id, measurement in dashboard_topic_rule.get('measurements', {}).items():
                    properties[measurement['name']] = {
                        'property': {
                            'name': measurement['name'],
                            'dataType': measurement.get('datatype', 'DOUBLE'),
                            'unit': measurement['unit'],
                            'type': {'measurement': {}}
                        },
                        'alias': m_id
                    }
                    topic_rules[dashboard_topic_rule['mqtt_topic_suffix']]['properties'].append(
                        measurement['name'])
                # Create the measurements from the measurement templates
                if 'measurements_templates' in dashboard_topic_rule:
                    rule_property_list = SitewiseHandler.__create_properties_from_template(
                        templates=dashboard_topic_rule['measurements_templates'],
                        properties=properties,
                        p_type='measurement')

                    topic_rules[dashboard_topic_rule['mqtt_topic_suffix']]['properties'].extend(rule_property_list)

            # Retrieve the Transforms
            for t_id, transform in dashboard.get('transforms', {}).items():
                properties[transform['name']] = {
                    'property': {
                        'name': transform['name'],
                        'dataType': transform.get('datatype', 'DOUBLE'),
                        'unit': transform['unit'],
                        'type': {
                            'transform': {
                                'expression': transform['expression'],
                                'variables': [
                                    {
                                        'name': transform['var'],
                                        'value': {
                                            'propertyId': transform['var_id'],
                                        }
                                    },
                                ]
                            }
                        }
                    },
                    'alias': t_id
                }
            # Create the transforms from the measurement transforms
            if 'transforms_templates' in dashboard:
                SitewiseHandler.__create_properties_from_template(
                    templates=dashboard['transforms_templates'],
                    properties=properties,
                    p_type='transform')

    def __create_asset_model(self, stack_name, ids, response_data, properties):
        """
        Create the asset model.
        :param stack-name: The name of the deployed CloudFormation stack
        :param ids: Dictionary of resource ids
        :param response_data: Dictionary of resource ids to be returned
        :param properties: A dictionary containing the asset properties
        :return: The asset model
        """
        property_list = []
        for prop in properties.values():
            property_list.append(prop['property'])

        model = self.SITEWISE_CLIENT.create_asset_model(
            assetModelName=f"{stack_name}_AssetModel",
            assetModelProperties=property_list
        )
        ids["model_id"] = model['assetModelId']
        response_data["assetModelId"] = model['assetModelId']

        # Check that the create operation was successful
        try:
            self.SITEWISE_CLIENT.get_waiter(
                'asset_model_active').wait(
                    assetModelId=model['assetModelId'],
                    WaiterConfig=self.configs['WAITER_CONFIG'])
        # pylint: disable=broad-exception-caught
        except Exception as exception:
            LOGGER.error(exception)
            return None

        return model

    def __create_asset(self, stack_name, model, ids, response_data):
        """
        Create the asset from the asset model
        :param stack_name: The name of the deployed CloudFormation stack
        :param model: The assset model
        :param ids: Dictionary of resource ids
        :param response_data: Dictionary of resource ids to be returned
        :return: The asset
        """
        asset = self.SITEWISE_CLIENT.create_asset(
            assetName=f"{stack_name}_Asset",
            assetModelId=model['assetModelId'],
        )
        ids["asset_id"] = asset['assetId']
        response_data["assetId"] = asset['assetId']

        # Check that the create operation was successful
        try:
            self.SITEWISE_CLIENT.get_waiter(
                'asset_active').wait(
                    assetId=asset['assetId'],
                    WaiterConfig=self.configs['WAITER_CONFIG'])
        # pylint: disable=broad-exception-caught
        except Exception as exception:
            LOGGER.error(exception)
            return None

        return asset

    def __update_asset_properties(self, stack_name, properties, model, asset):
        """
        Saves the asset property ids to be used when creating the dashboards.
        Sets the alias for each measurement property.
        :param stack_name: The name of the deployed CloudFormation stack.
        :param model: The asset model
        :param properties: A dictionary containing the asset properties
        :param asset: The asset
        """
        property_list = self.SITEWISE_CLIENT.describe_asset_model(
            assetModelId=model['assetModelId']
        )['assetModelProperties']

        for asset_property in property_list:
            properties[asset_property['name']]['property_id'] = asset_property['id']

            if 'measurement' not in asset_property['type']:
                continue

            alias = properties[asset_property['name']]['alias'].lower().replace('.', '_')
            alias = f"/telemetry/{stack_name}/{alias}"

            self.SITEWISE_CLIENT.update_asset_property(
                assetId=asset['assetId'],
                propertyId=asset_property['id'],
                propertyAlias=alias
            )

    @staticmethod
    def __update_widgets_params(widgets, properties):
        """
        The widgets are defined using the property names, but require the property ids.
        Only after the asset model is created do we have the property ids.
        Replaces the property names with the property ids.
        :param widgets: List of widget parameter dictionaries.
        :param property_ids: List of the asset's property ids.
        :return: List of updated widget parameter dictionaries
        """
        for widget in widgets:
            for metric in widget['metrics'].values():
                # Add the property id to the widget metric
                metric['property_ids'] = properties[metric['property_name']]['property_id']
                # Remove the property name from the widget metric
                metric.pop('property_name')

        return widgets

    @staticmethod
    def __create_dashboard(dashboard_name, widgets_params, asset_id, project_id):
        """
        Created a SiteWise dashboard.
        :param dashboard_name: A name for the SiteWise dashboard.
        :param widgets_params: List of widget parameter tuples.
        :param asset_id: Id of the SiteWise asset.
        :param project_id: Id of the SiteWise project.
        :return: The dashboard id
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

    def __create_monitor(self, event, properties, ids, response_data):
        """
        Creates the SiteWise portal, project and all of the dashboards described
        in the configuration  file. Associates the asset to the project.
        :param event: The MQTT message in json format
        :param properties: A dictionary containing the asset properties
        :param ids: Dictionary of resource ids
        :param response_data: Dictionary of resource ids to be returned
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
        # pylint: disable=broad-exception-caught
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

        LOGGER.info('Project created. Creating Dashboards...')

        for d_id, dashboard in self.configs['dashboards'].items():
            widgets_params = SitewiseHandler.__update_widgets_params(
                dashboard['widgets'],
                properties)

            dashboard_id = SitewiseHandler.__create_dashboard(
                dashboard['name'],
                widgets_params,
                asset_id,
                ids["project_id"])

            ids[f"dashboard_{d_id}"] = dashboard_id
            response_data[d_id] = dashboard_id

        LOGGER.info('Dashboards created.')

        # Associate asset to project
        self.SITEWISE_CLIENT.batch_associate_project_assets(
            projectId=project['projectId'],
            assetIds=[asset_id]
        )

        return cfnresponse.SUCCESS

    # pylint: disable=too-many-locals
    def __create_topic_rule(self, **kwargs):
        """
        Creates a SiteWise topic rule given a list of property values and
        their aliases.
        A rule is limited to a maximum of one hundred properties. If more
        than one hundred properties are given the function will create
        multiple rules accordingly.
        """
        # The MQTT message in json format.
        event = kwargs["event"]
        use_cloud_timestamp = kwargs.get("use_cloud_timestamp", True)
        alias_prefix = f"/telemetry/{event['ResourceProperties']['StackName']}/"
        action_list = []
        property_entry_list = []
        topic_rule_idx = 0

        for idx, alias_tuple in enumerate(kwargs["aliases"]):
            alias_suffix, data_type = alias_tuple
            # Append to property list
            property_entry_list.append(
                {
                    'propertyAlias': alias_prefix + alias_suffix.lower().replace('.', '_'),
                    'propertyValues': [
                        {
                            'value': {
                                f'{data_type}': '${' + alias_suffix + '}',
                            },
                            'timestamp': {
                                'timeInSeconds':
                                    '${floor(timestamp() / 1E3)}'
                                    if use_cloud_timestamp else "${Timestamp}"
                            }
                        }
                    ]
                }
            )

            # When the property entry list is full or if this is the last property
            if (len(property_entry_list) == self.configs['MAX_PROPERTIES_PER_ACTION']
                    or idx == len(kwargs["aliases"]) - 1):
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
                    or idx == len(kwargs["aliases"]) - 1):
                topic_rule_idx += 1

                # Create a topic rule with the actions
                self.IOT_CLIENT.create_topic_rule(
                    ruleName=f"{kwargs['topic_rule_name']}_{topic_rule_idx}",
                    topicRulePayload={
                        'sql': kwargs["sql_rule"],
                        'actions': action_list
                    }
                )

                # Clear the action list
                action_list = []

    def __create_topic_rules(self, event, properties, topic_rules):
        """
        Creates the topic rules which will route the incoming data from the
        MQTT client to the SiteWise Asset's measurement properties.
        Creates a rule for each unique topic.
        :param event: The MQTT message in json format
        :param properties: A dictionary containing the asset properties
        :param topic_rules: A dictionary containing the routing rules
        """
        stack_name = event['ResourceProperties']['StackName']
        topic = event['ResourceProperties']['TelemetryTopic']

        for suffix, rule in topic_rules.items():
            rule_sql = f"SELECT * FROM '{topic}{suffix}'"
            rule_name = f"{stack_name.replace('-', '_')}_{suffix.replace('/', '')}"

            alias_list = []

            for asset_property in rule['properties']:
                data_type = self.DATA_TYPE_DICT[
                    properties[asset_property]['property'].get('data_type', 'DOUBLE')
                ]
                alias_list.append((properties[asset_property]['alias'], data_type))

            self.__create_topic_rule(
                event=event, sql_rule=rule_sql,
                aliases=alias_list,
                topic_rule_name=rule_name,
                use_cloud_timestamp=rule['use_cloud_timestamp'])


    def create(self, event, response_data):
        """
        Initiates the creation of the SiteWise resources.
        :param event: The MQTT message in json format.
        :param response_data: Dictionary of resource ids to be returned.
        """
        ids = {'stack_name': event['ResourceProperties']['StackName']}

        properties = {}
        topic_rules = {}

        self.__parse_properties(properties, topic_rules)

        model = self.__create_asset_model(
            event['ResourceProperties']['StackName'],
            ids, response_data, properties
        )

        if not model:
            return cfnresponse.FAILED, {}

        asset = self.__create_asset(
            event['ResourceProperties']['StackName'],
            model, ids, response_data
        )

        if not asset:
            return cfnresponse.FAILED, {}

        self.__update_asset_properties(
            event['ResourceProperties']['StackName'],
            properties, model, asset
        )

        self.__create_monitor(event, properties, ids, response_data)

        self.__create_topic_rules(event, properties, topic_rules)

        return cfnresponse.SUCCESS, ids

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

    def delete_sitewise_asset(self, ids):
        """
        Deletes the asset then the asset model.
        :param ids: Dictionary of resource ids.
        """
        model_id = None
        asset_id = None

        try:
            model_id = ids["model_id"]
            asset_id = ids["asset_id"]
        except KeyError as exception:
            LOGGER.error("Sitewise resources not found in delete_sitewise_asset: %s", exception)

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

    def delete(self, event):
        """
        Initiates the deletion of the SiteWise resources.
        :param event: The MQTT message in json dictionary format.
        """
        ids = Utils.decode_ids(event['PhysicalResourceId'])

        Utils.set_cloudwatch_retention(
            event['ResourceProperties']['StackName'],
            event['ResourceProperties']['Region'])

        SitewiseHandler.delete_monitor(ids)
        self.delete_sitewise_asset(ids)
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
            sitewise_handler.delete(event)
            cfnresponse.send(
                event, context,
                cfnresponse.SUCCESS, response_data)
        else:
            LOGGER.info('Unexpected RequestType!')
            cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data)

    # pylint: disable=broad-exception-caught
    except Exception as err:
        LOGGER.error("Sitewise custom function handler error: %s", err)

        response_data = {"Data": str(err)}
        cfnresponse.send(event, context, cfnresponse.FAILED, response_data)
