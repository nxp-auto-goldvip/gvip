#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
A custom function which creates a custom CloudFormation resource.
Implements the 'create' and 'delete' events.
When 'create' is invoked it creates a Greengrass V2 telemetry component
and, if needed, attaches a Greengrass Service Role to the AWS account.
When 'delete' is invoked it handles the deletion of all resources
created by this function.

Copyright 2021-2023 NXP
"""

import json
import time

import boto3
import cfnresponse

from cfn_utils import Utils, LOGGER


class Greengrassv2Handler:
    """
    Handles the create and delete events for the Greengrass Group resources.
    """

    GGV2_CLIENT = boto3.client("greengrassv2")
    COMPONENT_SUFFIX = ".GoldVIP.Telemetry"
    RETRIES = 10
    WAIT_TIME = 5

    @staticmethod
    def __attach_service_role(event):
        """
        Check if a GreenGrass service role is associated to the account,
        if not we associate the service role created by the stack to the account.
        The service role is set to persist after the stack deletion.
        """
        service_role_arn = event['ResourceProperties']['ServiceRoleArn']
        service_role_name = event['ResourceProperties']['ServiceRoleName']
        service_role_policy_name = event['ResourceProperties']['ServiceRolePolicyName']

        ggv1_client = boto3.client("greengrass")
        iam_client = boto3.client('iam')

        # Check if service role is associated
        try:
            ggv1_client.get_service_role_for_account()
        except: # pylint: disable=bare-except
            ggv1_client.associate_service_role_to_account(
                RoleArn=service_role_arn
            )

            return

        # Deleting the service role when it is not needed.
        iam_client.delete_role_policy(
            RoleName=service_role_name,
            PolicyName=service_role_policy_name
        )

        iam_client.delete_role(
            RoleName=service_role_name
        )

    @staticmethod
    def __create_telemetry_component(event, ids):
        """
        Creates a greengrass v2 component from a lambda function.
        :param event: The MQTT message in json format.
        :param ids: Dictionary of resource ids.
        """

        stack_name = event['ResourceProperties']['StackName']
        telemetry_topic = event['ResourceProperties']['TelemetryTopic']
        lambda_arn = event['ResourceProperties']['TelemetryLambdaArn']

        component = Greengrassv2Handler.GGV2_CLIENT.create_component_version(
            lambdaFunction={
                'lambdaArn': lambda_arn,
                'componentName': stack_name + Greengrassv2Handler.COMPONENT_SUFFIX,
                'componentVersion': '1.0.0',
                'componentLambdaParameters': {
                    'eventSources': [
                        {
                            'topic': telemetry_topic + '/config',
                            'type': 'IOT_CORE'
                        },
                        {
                            'topic': telemetry_topic + '/config',
                            'type': 'PUB_SUB'
                        }
                    ],
                    'pinned': True,
                    'environmentVariables': {
                        'telemetryTopic': telemetry_topic,
                        'AppDataTopicSuffix': "/app_data"
                    },
                    'linuxProcessParams': {
                        'isolationMode': 'NoContainer',
                    }
                }
            }
        )

        ids["telemetry_component"] = component["arn"]

    @staticmethod
    def create(event):
        """
        Initiates the creation of the Greengrass resources.
        :param event: The MQTT message in json dictionary format.
        """
        ids = {'thing_name': event['ResourceProperties']['CoreThingName'], \
                'thing_arn': event['ResourceProperties']['CoreThingArn']}

        Greengrassv2Handler.__attach_service_role(event)
        Greengrassv2Handler.__create_telemetry_component(event, ids)

        return ids

    @staticmethod
    def check_deployment(deployment_id, status):
        """
        Waits for the deployment to have a certain status.
        :param deployment_id: Id of the deployment to check.
        :param status: list of statuses to check the deployment against.
        """
        for _ in range(Greengrassv2Handler.RETRIES):
            time.sleep(Greengrassv2Handler.WAIT_TIME)
            new_deployment_status = Greengrassv2Handler.GGV2_CLIENT.get_deployment(
                deploymentId=deployment_id
            )['deploymentStatus']
            if new_deployment_status in status:
                return True
        return False

    @staticmethod
    def delete(event):
        """
        Initiates the deletion of the Greengrass resources.
        :param event: The MQTT message in json dictionary format.
        """
        ids = Utils.decode_ids(event['PhysicalResourceId'])
        component_arn = ids["telemetry_component"]
        thing_name = ids['thing_name']
        thing_arn = ids['thing_arn']
        deployment_name = f"{event['ResourceProperties']['StackName'].replace('-','_')}_clean_deployment"

        Utils.set_cloudwatch_retention(
            event['ResourceProperties']['StackName'],
            event['ResourceProperties']['Region'])

        # Delete GoldVIP telemetry component
        Greengrassv2Handler.GGV2_CLIENT.delete_component(
            arn=component_arn
        )
        LOGGER.info("Greengrass telemetry component deleted.")

        # Get a list of deployments associated with the core thing.
        # These deployments are created when we provision the board.
        # We are compiling the list of deployments before creating the new one
        # which will uninstall the telemetry component on the board.
        deployment_ids = []
        paginator = Greengrassv2Handler.GGV2_CLIENT.get_paginator('list_deployments')
        for page in paginator.paginate(targetArn=thing_arn):
            for deployment in page['deployments']:
                deployment_ids.append(deployment['deploymentId'])


        # Creates a Greengrass v2 deployment with minimal Greengrass components.
        # This will uninstall unwanted components on the board
        new_deployment_id = Greengrassv2Handler.GGV2_CLIENT.create_deployment(
            targetArn=thing_arn,
            deploymentName=deployment_name,
            components={}
        )['deploymentId']

        # Append the new deployment to the list of deployments pending deletion.
        deployment_ids.append(new_deployment_id)

        # Wait for deployment status
        if Greengrassv2Handler.check_deployment(new_deployment_id, ['COMPLETED']):
            LOGGER.info("Uninstalled components.")
        else:
            LOGGER.error("Failed to uninstall deployed components!")

        for deployment_id in deployment_ids:
            try:
                # Cancel deployment
                Greengrassv2Handler.GGV2_CLIENT.cancel_deployment(
                    deploymentId=deployment_id)

                if Greengrassv2Handler.check_deployment(deployment_id, ['CANCELED', 'INACTIVE']):
                    LOGGER.info("Deleting deployment: with id: %s",
                                deployment_id)
                    # Delete deployment
                    Greengrassv2Handler.GGV2_CLIENT.delete_deployment(
                        deploymentId=deployment_id)
                else:
                    LOGGER.error("Failed to delete deployment with id: %s",
                                 deployment_id)
            except Exception as err:
                LOGGER.error("Failed to delete deployment with id %s, error: %s",
                    deployment_id, err)

        try:
            Greengrassv2Handler.GGV2_CLIENT.delete_core_device(
                coreDeviceThingName=thing_name
            )
            LOGGER.info("Core device deleted.")
        except Greengrassv2Handler.GGV2_CLIENT.exceptions.ResourceNotFoundException:
            LOGGER.info("Core device not found.")

def lambda_handler(event, context):
    """
    Handler function for the custom resource function.
    :param event: The MQTT message in json format.
    :param context: A Lambda context object, it provides information.
    """
    LOGGER.info('Greengrass custom function handler got event %s', json.dumps(event))

    try:
        response_data = {}

        if event['RequestType'] == 'Create':
            ids = Greengrassv2Handler.create(event)

            cfnresponse.send(
                event, context, cfnresponse.SUCCESS,
                response_data, physical_resource_id=Utils.encode_ids(ids))
        elif event['RequestType'] == 'Update':
            cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data)
        elif event['RequestType'] == 'Delete':
            Greengrassv2Handler.delete(event)
            cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data)
        else:
            LOGGER.info('Unexpected Request Type!')
            cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data)
    # pylint: disable=broad-exception-caught
    except Exception as err:
        LOGGER.error("Greengrass custom function handler error: %s", err)
        response_data = {"Data": str(err)}
        cfnresponse.send(event, context, cfnresponse.FAILED, response_data)
