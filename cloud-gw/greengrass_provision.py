#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Script used for deploying the Greengrass certificate on the board and
starting a new Greengrass group deployment.

Copyright 2021-2024 NXP
"""

import argparse
import json
import tempfile
import time
import subprocess
import traceback

import boto3

from utils import Utils, GREENGRASS_ROOT_PATH
from client_device_provision import ClientDeviceProvisioningClient


# pylint: disable=too-many-instance-attributes
class Greengrassv2Deployment():
    """Class containing the Greengrass v2 deployment steps."""

    DEPLOYMENT_CONFIG_FILE = "/home/root/cloud-gw/ggv2_deployment_configurations.json"

    # pylint: disable=too-many-arguments
    def __init__(self,
                 region, stack_name,
                 deployment_name,
                 mqtt_port, https_port,
                 setup_devices,
                 use_rpmb,
                 no_deploy, clean_device_provision,
                 verbose):
        """
        :param region: The AWS region where the stack was deployed.
        :param stack_name: The name of the deployed CloudFormation stack.
        :param deployment_name: A Name for the Greengrass v2 deployment.
        :param mqtt_port: Mqtt port used by Greengrass.
        :param https_port: Https port used by Greengrass.
        :param setup_devices: Triggers the provisioning of the client devices.
        :param use_rpmb: Use the OP-TEE RPMB secure storage in the client device provisioning steps.
        :param no_deploy: Don't create a deployment.
        :param clean_device_provision: Forces a clean provisioning of the client devices.
        :param verbose: Verbosity flag.
        """
        self.__thing_arn = None
        self.__stack_name = stack_name
        self.__region = region
        self.__deployment_name = deployment_name
        self.__mqtt_port = mqtt_port
        self.__https_port = https_port
        self.__setup_devices = setup_devices
        self.__use_rpmb = use_rpmb
        self.__no_deploy = no_deploy
        self.__clean_device_provision = clean_device_provision
        self.__verbose = verbose

        cfn_stack_outputs = Utils.pull_stack_outputs(
            boto3.client('cloudformation'),
            self.__stack_name)

        self.__thing_name = Utils.get_cfn_output_value(cfn_stack_outputs, 'CoreThingName')
        self.__telemetry_topic = Utils.get_cfn_output_value(cfn_stack_outputs, 'TelemetryTopic')

        self.__configs = None

    def __load_configurations(self):
        """
        Loads the deployment configuration file and replaces the substitution
        templates with the corresponding values.
        """
        with open(self.DEPLOYMENT_CONFIG_FILE,
                  "r", encoding="utf-8") as config_file:
            configs = json.loads(config_file.read())

            configs_str = json.dumps(configs)
            configs_str = configs_str.replace("MQTT_PORT", str(self.__mqtt_port))
            configs_str = configs_str.replace("HTTPS_PORT", str(self.__https_port))
            configs_str = configs_str.replace("STACK_NAME", str(self.__stack_name))
            configs_str = configs_str.replace("TELEMETRY_TOPIC", str(self.__telemetry_topic))
            configs_str = configs_str.replace("GG_THING_NAME", str(self.__thing_name))

            # Create a selection rule to include all of the things
            selection_rule = f"thingName: {self.__thing_name}"
            for client_data in json.loads(configs_str)["devices"].values():
                thing = client_data["thing_name"]
                selection_rule += f" OR thingName: {thing}"
            configs_str = configs_str.replace("SELECTION_RULE", selection_rule)

            # Transform the configurations back into a dictionary
            self.__configs = json.loads(configs_str)

            # Create a mapping entry in the Mqtt Bridge for each device
            for device, device_data in self.__configs["devices"].items():
                self.__configs["bridge"]["mqttTopicMapping"][device] = {
                    "topic": device_data["mqtt_topic"],
                    "source": "LocalMqtt",
                    "target": "IotCore"
                }


    def __get_thing_arn(self):
        """
        Retrieves the Core Thing Arn.
        """
        iot_client = boto3.client("iot")

        for page in iot_client.get_paginator('list_things').paginate():
            for thing in page['things']:
                if thing['thingName'] == self.__thing_name:
                    self.__thing_arn = thing['thingArn']
                    break

        if not self.__thing_arn:
            # pylint: disable=broad-exception-raised
            raise Exception("Core Thing ARN not found.")

    def __create_deployment(self):
        """
        Creates a Greengrass v2 continuous deployment for the stack's core thing.
        It deploys on the board the Telemetry component, the Greengrass cli,
        the Greengrass nucleus, and four components required to connect to SJA1110's thing.
        """
        ggv2_client = boto3.client("greengrassv2")

        ggv2_client.create_deployment(
            targetArn=self.__thing_arn,
            deploymentName=self.__deployment_name,
            components={
                'aws.greengrass.Nucleus': {
                    'componentVersion': '2.9.1',
                    'configurationUpdate': {
                        'merge': json.dumps(self.__configs['nucleus'])
                    }
                },
                'aws.greengrass.Cli' : {
                    'componentVersion': '2.9.1'
                },
                self.__stack_name + ".GoldVIP.Telemetry" : {
                    'componentVersion': '1.0.0',
                    'configurationUpdate': {
                        'merge': json.dumps(self.__configs['telemetry'])
                    }
                },
                'aws.greengrass.clientdevices.mqtt.Bridge' : {
                    'componentVersion': '2.2.4',
                    'configurationUpdate': {
                        'merge': json.dumps(self.__configs['bridge'])
                    }
                },
                'aws.greengrass.clientdevices.mqtt.Moquette' : {
                    'componentVersion': '2.3.0'
                },
                'aws.greengrass.clientdevices.Auth' : {
                    'componentVersion': '2.3.1',
                    'configurationUpdate': {
                        'merge': json.dumps(self.__configs['auth'])
                    }
                },
                'aws.greengrass.clientdevices.IPDetector' : {
                    'componentVersion': '2.1.5'
                },
                'aws.greengrass.LambdaManager' : {
                    'componentVersion': '2.2.7'
                }
            }
        )

    def __run_installer(self, timeout=180):
        """
        Execute the Greengrass v2 installer command and wait for the Nucleus
        to be launched succesfully. The command will continue to run in the background,
        keeping this Nucleus alive.
        :param timeout: Time in seconds to wait for the installer to report a succesfull launch.
        """
        installer_command = f"java -Droot={GREENGRASS_ROOT_PATH} -Dlog.store=FILE "\
                            f"-jar {GREENGRASS_ROOT_PATH}/alts/init/distro/lib/Greengrass.jar "\
                            f"--aws-region {self.__region} "\
                            f"--component-default-user ggc_user:ggc_group "\
                            f"--provision true --thing-name {self.__thing_name} "\
                            f"--thing-policy-name {self.__stack_name}_Cert_Policy"

        Greengrassv2Deployment.stop_greengrass_nucleus()

        # Run the installer command in background, the Greengrass v2 nucleus will continue to run
        # while this process is running.
        with tempfile.TemporaryFile(mode='w+') as stdout_file, \
             tempfile.TemporaryFile(mode='w+') as stderr_file:
            # pylint: disable=consider-using-with
            subprocess.Popen(installer_command, stdout=stdout_file,
                             stderr=stderr_file, shell=True)

            print("Starting Greengrass V2 Nucleus...")

            # Check every 10 seconds if the nucleus launched succesfully.
            while timeout > 0:
                time.sleep(10)
                timeout -= 10

                stdout_file.seek(0)
                stdout = stdout_file.read()

                if 'Launched Nucleus successfully.' in stdout:
                    print("Launched Greengrass V2 Nucleus successfully.")
                    return

            stderr_file.seek(0)
            stderr = stderr_file.read()

        # pylint: disable=broad-exception-raised
        raise Exception(f"Failed to start Greengrass V2: {stderr}")

    def execute(self):
        """
        Execute the steps required to deploy the Greengrass v2 Nucleus.
        """
        self.__load_configurations()

        if self.__no_deploy:
            # Just restart the nucleus
            Greengrassv2Deployment.restart_greengrass_nucleus()
        else:
            # Create the deployment
            self.__get_thing_arn()
            self.__create_deployment()
            self.__run_installer()

        # Provision the client devices
        if self.__setup_devices:
            provision_failed = False
            for device_data in self.__configs["devices"].values():
                # Check whether there is a known destination to the device. If none, skip the
                # provisioning process.
                knwon_device_dest = [device_data.get(key, None)
                                     for key in ["device_ip", "device_hwaddr"]]
                if not any(knwon_device_dest):
                    if self.__verbose:
                        print(f"Provisioning skipped for device {device_data['thing_name']}.")
                    continue

                if self.__verbose:
                    print(f"Provisioning device {device_data['thing_name']}...")

                try:
                    ClientDeviceProvisioningClient(
                        thing_name=device_data["thing_name"],
                        mqtt_topic=device_data["mqtt_topic"],
                        cfn_stack_name=self.__stack_name,
                        aws_region_name=self.__region,
                        device_port=device_data["device_port"],
                        mqtt_port=self.__mqtt_port,
                        device_ip=device_data.get("device_ip", None),
                        device_hwaddr=device_data.get("device_hwaddr", None),
                        clean_provision=self.__clean_device_provision,
                        time_sync=device_data.get("time_sync", False),
                        use_rpmb=self.__use_rpmb,
                        verbose=self.__verbose).execute()
                # pylint: disable=broad-exception-caught
                except Exception:
                    print(f"Provision failed for device {device_data['thing_name']}.")
                    # Printing full traceback
                    traceback.print_exc()
                    provision_failed = True
            if provision_failed:
                # pylint: disable=broad-exception-raised
                raise Exception("Client Device Provisioning failed.")

    @staticmethod
    def stop_greengrass_nucleus():
        """ Stop the Greengrass V2 nucleus running process.
        """
        print("Stopping Greengrass V2 Nucleus...")
        command = "kill -9 $(ps aux | grep '[g]reengrass/v2' | awk '{print $2}') || true"

        Utils.execute_command(command)

    @staticmethod
    def restart_greengrass_nucleus():
        """ Restart the Greengrass V2 Nucleus running process.
        """
        # Stop the Greengrass V2 Nucleus, if it is already running.
        Greengrassv2Deployment.stop_greengrass_nucleus()

        print("Starting Greengrass V2 Nucleus...")
        installer_command = f"{GREENGRASS_ROOT_PATH}/alts/current/distro/bin/loader"
        # pylint: disable=consider-using-with
        subprocess.Popen(installer_command,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         shell=True)

def main():
    """ Parse the arguments and setup Greengrass. """
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                     description='Use the outputs from the deployed '
                                                 'CloudFormation stack to copy the Greengrass '
                                                 'certificate and trigger a group deployment.')
    parser.add_argument('--no-deploy', dest='no_deploy', default=False, action='store_true',
                        help="Setup only the network; don't deploy the Greengrass group.")
    parser.add_argument('--stack-name', dest='cfn_stack_name', type=str,
                        default='serverlessrepo-nxp-goldvip-telemetry',
                        help='The name of the deployed CloudFormation stack.')
    parser.add_argument('--region-name', dest='aws_region_name', type=str, default='us-west-2',
                        help='The AWS region where the CloudFormation stack was deployed.')
    parser.add_argument('--netif', dest='netif', type=str, default='eth0',
                        help='The network interface used to connect to open internet.')
    parser.add_argument('--ntp-netif', dest='ntp_netif', type=str, default='eth0',
                        help='The network interface used to sync the datetime.')
    parser.add_argument('--netip', dest='netip', type=str, default=None,
                        help='The static IP set on the given network interface. If ommited, then' \
                        ' the IP is obtained using a DHCP client.')
    parser.add_argument('--mqtt-port', dest='mqtt_port', type=int, default=443, choices=[8883, 443],
                        help='MQTT port used by Greengrass.')
    parser.add_argument('--https-port', dest='https_port', type=int, default=443,
                        choices=[8443, 443], help='HTTP port used by Greengrass.')
    parser.add_argument('--setup-devices', dest='setup_devices', default=False, action='store_true',
                        help='Provision the client devices with the connection data.')
    parser.add_argument('--use-rpmb', dest='use_rpmb', default=False, action='store_true',
                        help='Use the OP-TEE RPMB secure storage for the certificates used in the '
                        'device provisioning.')
    parser.add_argument('--deployment-name', dest='deployment_name', type=str,
                        default='GoldVIP_Telemetry_Deployment',
                        help='Name of the Greengrass V2 continuous deployment.')
    parser.add_argument('--clean-device-provision', dest='clean_device_provision', default=False,
                        action='store_true',
                        help='If set it will force the device provisioning client to '\
                        'retrieve the provisioning data instead of using the data stored '\
                        'after previous runs.')
    parser.add_argument('--quiet', dest='quiet', default=False, action='store_true',
                        help="Quiet mode. Causes most diagnostic messages to be suppressed.")

    args = parser.parse_args()

    # Setup the network for ntp.
    Utils.setup_network_interface(args.ntp_netif, setup_ifmetric=False)

    # Ensure that the clock is synchronized with the ntp servers
    Utils.sync_system_datetime(args.ntp_netif)

    # Setup the network.
    Utils.setup_network_interface(args.netif, args.netip)

    if not args.no_deploy or args.setup_devices:
        # Check if the AWS credentials were provided
        if boto3.session.Session().get_credentials() is None:
            # pylint: disable=broad-exception-raised
            raise Exception('There are no AWS credentials defined. '
                            'Please define them via environment variables.')

        # Set the AWS region
        if args.aws_region_name:
            boto3.setup_default_session(region_name=args.aws_region_name)

        # Deploy Greengrass V2
        Greengrassv2Deployment(
            args.aws_region_name,
            args.cfn_stack_name,
            args.deployment_name,
            args.mqtt_port,
            args.https_port,
            args.setup_devices,
            args.use_rpmb,
            args.no_deploy,
            args.clean_device_provision,
            not args.quiet).execute()
    else:
        Greengrassv2Deployment.restart_greengrass_nucleus()

# entry point
if __name__ == '__main__':
    main()
