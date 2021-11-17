#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Script used for deploying the Greengrass certificate on the board and
starting a new Greengrass group deployment.

Copyright 2021 NXP
"""

import argparse
import getpass
import json
import tempfile
import time
import subprocess

import boto3

from utils import Utils
from sja_provision import SjaProvisioningClient


class Greengrassv2Deployment():
    """Class containing the Greengrass v2 deployment steps."""

    def __init__(self, region, stack_name, deployment_name, ports):
        """
        :param region: The AWS region where the stack was deployed.
        :param stack_name: The name of the deployed CloudFormation stack.
        :param deployment_name: A Name for the Greengrass v2 deployment.
        :param mqtt_port: Mqtt port used by greengrass.
        """
        self.thing_name = None
        self.thing_arn = None
        self.stack_name = stack_name
        self.region = region
        self.deployment_name = deployment_name
        self.mqtt_port = ports[0]
        self.https_port = ports[1]

    def get_thing_arn(self):
        """
        Retrieves the Core Thing Arn.
        """
        iot_client = boto3.client("iot")
        cfn_client = boto3.client('cloudformation')

        cfn_stack_outputs = Utils.pull_stack_outputs(
            cfn_client,
            self.stack_name)

        self.thing_name = Utils.get_cfn_output_value(cfn_stack_outputs, 'CoreThingName')

        for thing in iot_client.list_things()['things']:
            if thing['thingName'] == self.thing_name:
                self.thing_arn = thing['thingArn']
                break

        if not self.thing_arn:
            raise Exception("Core Thing ARN not found.")

    def create_deployment(self):
        """
        Creates a Greengrass v2 continuous deployment for the stack's core thing.
        It deploys on the board the Telemetry component, the greengrass cli,
        the greengrass nucleus, and four components required to connect to SJA1110's thing.
        """
        ggv2_client = boto3.client("greengrassv2")
        sja_thing_name = self.stack_name + "_SjaThing"

        with open("/home/root/cloud-gw/ggv2_deployment_configurations.json",
                  "r", encoding="utf-8") as config_file:
            configs = json.loads(config_file.read())

        ggv2_client.create_deployment(
            targetArn=self.thing_arn,
            deploymentName=self.deployment_name,
            components={
                'aws.greengrass.Nucleus': {
                    'componentVersion': '2.4.0',
                    'configurationUpdate': {
                        'merge': json.dumps(configs['nucleus']
                                            ).replace("MQTT_PORT", str(self.mqtt_port)
                                                      ).replace("HTTPS_PORT", str(self.https_port))
                    }
                },
                'aws.greengrass.Cli' : {
                    'componentVersion': '2.4.0'
                },
                self.stack_name + ".GoldVIP.Telemetry" : {
                    'componentVersion': '1.0.0',
                    'configurationUpdate': {
                        'merge': json.dumps(configs['telemetry']
                                            ).replace('STACK_NAME', self.stack_name),
                    }
                },
                'aws.greengrass.clientdevices.mqtt.Bridge' : {
                    'componentVersion': '2.0.1',
                    'configurationUpdate': {
                        'merge': json.dumps(configs['bridge']
                                            ).replace('STACK_NAME', self.stack_name),
                    }
                },
                'aws.greengrass.clientdevices.mqtt.Moquette' : {
                    'componentVersion': '2.0.1'
                },
                'aws.greengrass.clientdevices.Auth' : {
                    'componentVersion': '2.0.2',
                    'configurationUpdate': {
                        'merge': json.dumps(configs['auth']).replace(
                            'STACK_NAME', self.stack_name).replace(
                                'GG_THING_NAME', self.thing_name).replace(
                                    'SJA_THING_NAME', sja_thing_name),
                    }
                },
                'aws.greengrass.clientdevices.IPDetector' : {
                    'componentVersion': '2.0.2'
                },
                'aws.greengrass.LambdaManager' : {
                    'componentVersion': '2.1.4'
                }
            }
        )

    def run_installer(self, timeout=180):
        """
        Execute the Greengrass v2 installer command and wait for the Nucleus
        to be launched succesfully. The command will continue to run in the background,
        keeping this Nucleus alive.
        :param timeout: Time in seconds to wait for the installer to report a succesfull launch.
        """
        installer_command = f"java -Droot='/greengrass/v2' -Dlog.store=FILE\
        -jar /greengrass/v2/alts/init/distro/lib/Greengrass.jar\
        --aws-region {self.region} --component-default-user ggc_user:ggc_group\
        --provision true --thing-name {self.thing_name}"

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

        raise Exception(f"Failed to start Greengrass V2: {stderr}")

    def execute(self):
        """
        Execute the steps required to deploy the Greengrass v2 Nucleus.
        """
        self.get_thing_arn()
        self.create_deployment()
        self.run_installer()

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
        installer_command = "/greengrass/v2/alts/current/distro/bin/loader"
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
                        help="Setup only the network; don't deploy the greengrass group.")
    parser.add_argument('--stack-name', dest='cfn_stack_name', type=str,
                        default='serverlessrepo-nxp-goldvip-telemetry',
                        help='The name of the deployed CloudFormation stack.')
    parser.add_argument('--region-name', dest='aws_region_name', type=str, default='us-west-2',
                        help='The AWS region where the CloudFormation stack was deployed.')
    parser.add_argument('--netif', dest='netif', type=str, default='eth0',
                        help='The network interface used to connect to open internet.')
    parser.add_argument('--netip', dest='netip', type=str, default=None,
                        help='The static IP set on the given network interface. If ommited, then' \
                        ' the IP is obtained using a DHCP client.')
    parser.add_argument('--ssid', dest='wlan_ssid', type=str, default=None,
                        help='The SSID of the wireless network to connect to. It may be ommitted' \
                        ' if the wireless network was previously configured or the board should' \
                        ' connect to any available unsecured network.')
    parser.add_argument('--psk', dest='wlan_psk', type=str, default=None,
                        help='The password of the wireless network to connect to. If ommited, ' \
                        'it will be read from standard input. If the SSID does not have ' \
                        'password authentication, provide empty input.')
    parser.add_argument('--mqtt-port', dest='mqtt_port', type=int, default=443, choices=[8883, 443],
                        help='MQTT port used by Greengrass.')
    parser.add_argument('--https-port', dest='https_port', type=int, default=443,
                        choices=[8443, 443], help='HTTP port used by Greengrass.')
    parser.add_argument('--setup-sja', dest='setup_sja', default=False, action='store_true',
                        help="Local ip address of the sja1110 interface.")
    parser.add_argument('--deployment-name', dest='deployment_name', type=str,
                        default='GoldVIP_Telemetry_Deployment',
                        help="Name of the Greengrass V2 continuous deployment.")

    args = parser.parse_args()

    ssid_password = None
    # Ask for password only if the SSID was specified.
    if args.wlan_ssid and not args.wlan_psk:
        ssid_password = getpass.getpass(prompt='Please introduce the passphrase: ')
    else:
        ssid_password = args.wlan_psk

    # Setup the network.
    Utils.setup_network_interface(args.netif, args.netip, args.wlan_ssid, ssid_password)

    # Ensure that the clock is synchronized with the ntp servers
    Utils.sync_system_datetime()

    # Check for AWS credentials
    if not args.no_deploy or args.setup_sja:
        # Check if the AWS credentials were provided
        if boto3.session.Session().get_credentials() is None:
            raise Exception('There are no AWS credentials defined. '
                            'Please define them via environment variables.')

        # Set the AWS region
        if args.aws_region_name:
            boto3.setup_default_session(region_name=args.aws_region_name)

    if args.no_deploy:
        # Start the Greengrass V2 Nucleus.
        Greengrassv2Deployment.restart_greengrass_nucleus()
    else:
        # Deploy Greengrass V2
        Greengrassv2Deployment(
            args.aws_region_name,
            args.cfn_stack_name,
            args.deployment_name,
            (args.mqtt_port,
             args.https_port)).execute()

    # Start the sja provisioning client.
    if args.setup_sja:
        # Network error occurs when publishing without a wait.
        SjaProvisioningClient(
            args.cfn_stack_name,
            args.aws_region_name,
            args.netif,
            args.mqtt_port).execute()

# entry point
if __name__ == '__main__':
    main()
