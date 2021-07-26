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
import os
import tarfile
import time

from io import BytesIO

import boto3

from utils import Utils
from sja_provision import SjaProvisioningClient


class GreengrassGroupDeployment():
    """ Class containing the Greengrass group deployment steps. """

    def __init__(self, group_id=None, status_retries=50):
        """
        :param group_name: the name of the Greengrass group
        :param status_retries: the number of retries used to wait for deployment finish
        """
        self.group_id = group_id
        self.status_retries = status_retries

        self.__deployment_id = None
        self.__gg_client = boto3.client('greengrass')

    def prepare_deployment(self):
        """
        Initiate a new deployment for the Greengrass group.
        """
        group_version_id = self.__gg_client.get_group(GroupId=self.group_id)['LatestVersion']

        print("Creating deployment for group ID: '{0}'.".format(self.group_id))
        response = self.__gg_client.create_deployment(
            DeploymentType='NewDeployment',
            GroupId=self.group_id,
            GroupVersionId=group_version_id,
        )

        self.__deployment_id = response['DeploymentId']
        print("Triggered a new deployment with ID: '{0}'.".format(self.__deployment_id))

    def check_deployment_status(self):
        """
        Query the Greengrass group deployment status.
        :return: the deployment status as string or exception
        """
        print('Checking the deployment status...')

        response = self.__gg_client.get_deployment_status(
            DeploymentId=self.__deployment_id,
            GroupId=self.group_id
        )

        deployment_status = response['DeploymentStatus']
        if deployment_status not in {'Success', 'Failure'}:
            print("Deployment status: '{0}'.".format(deployment_status))
            raise Exception("Deployment is still in progress.")

        return deployment_status

    def wait_for_deployment_ending(self):
        """
        Wait until the triggered deployment has ended, or the maximum
        number of retries was reached.
        """
        print('Waiting for deployment to finish...')

        deployment_status = Utils.retry(self.check_deployment_status, self.status_retries)
        print("Deployment finished with status: '{0}'.".format(deployment_status))
        if deployment_status == 'Failure':
            raise Exception('Group deployment has failed.')

    def execute(self):
        """
        Execute the steps required to deploy the Greengrass group.
        """
        self.prepare_deployment()
        self.wait_for_deployment_ending()


class GreengrassCertsProvisioner:
    """ Class containing the Greengrass certificate deployment steps. """

    # Greengrass root directory
    GREENGRASS_DIR = '/greengrass/'
    # Path to the Greengrass core daemon
    GREENGRASSD_PATH = os.path.join(GREENGRASS_DIR, 'ggc', 'core', 'greengrassd')
    # Path to config.json file
    CONFIG_PATH = os.path.join(GREENGRASS_DIR, 'config', 'config.json')

    def __init__(self, bucket_name=None):
        """
        :param bucket_name: the name of the S3 bucket that stores the certificates
        """
        self.bucket_name = bucket_name
        self.__s3_client = boto3.client('s3')
        self.__setup_tarball = None

    def deploy_certificates(self):
        """
        Download the setup tarball and unpack it.
        """
        gzip = BytesIO()
        print('Downloading the setup tarball...')
        self.__s3_client.download_fileobj(self.bucket_name, self.__setup_tarball, gzip)
        gzip.seek(0)

        print('Copying the Greengrass configuration files...')
        with tarfile.open(fileobj=gzip, mode='r:gz') as tar:
            tar.extractall(path=self.GREENGRASS_DIR)

    def set_ports(self, mqtt_port, http_port):
        """
        Configure the Greengrass core to use port 443 for
        MQTT and HTTPS communication (by default 8883 and 8443)
        :param mqtt_port: mqtt port used by greengrass.
        :param http_port: http port used by greengrass.
        """
        with open(self.CONFIG_PATH, 'r+', encoding="utf-8") as config_file:
            config = json.load(config_file)
            config["coreThing"]["iotMqttPort"] = mqtt_port
            config["coreThing"]["iotHttpPort"] = http_port
            config["coreThing"]["ggHttpPort"] = http_port
            config_file.seek(0, 0)
            config_file.write(json.dumps(config, indent=4))

    @staticmethod
    def control_greengrass(command):
        """
        Control the Greengrass service (restart / stop / start).
        """
        print('{0}ing greengrass daemon...'.format(command.title()))
        Utils.execute_command('{0} {1}'.format(GreengrassCertsProvisioner.GREENGRASSD_PATH,
                                               command))

    def execute(self, mqtt_port, http_port):
        """
        Execute the steps required to deploy the Greengrass certificates.
        :param mqtt_port: mqtt port used by greengrass.
        :param http_port: http port used by greengrass.
        """
        self.__setup_tarball = Utils.check_certificates_tarball(
            self.__s3_client, self.bucket_name, Utils.GOLDVIP_SETUP_ARCHIVE)

        try:
            # Stopping the greengrass daemon may fail when the config files are missing.
            self.control_greengrass('stop')
        # pylint: disable=broad-except
        except Exception:
            pass

        self.deploy_certificates()
        self.set_ports(mqtt_port, http_port)
        self.control_greengrass('restart')


class GreengrassSetup():
    """ Class that contains the setup steps for Greengrass core. """

    def __init__(self, cfn_stack_name, aws_region_name=None):
        """
        :param cfn_stack_name: the name of the deployed CloudFormation stack
        :param aws_region_name: the AWS region where the stack was deployed
        """
        self.cfn_stack_name = cfn_stack_name
        self.aws_region_name = aws_region_name
        self.__gg_group_id = None
        self.__s3_bucket_name = None

    def get_cfn_stack_outputs(self):
        """
        Get the Greengrass group id and the S3 bucket name from the CloudFormation stack's
        output list.
        """
        cfn_stack_outputs = Utils.pull_stack_outputs(
            boto3.client('cloudformation'),
            self.cfn_stack_name)

        self.__gg_group_id = Utils.get_cfn_output_value(cfn_stack_outputs, 'GreengrassGroupId')
        print("Found Greengrass group ID: '{0}'.".format(self.__gg_group_id))
        self.__s3_bucket_name = Utils.get_cfn_output_value(cfn_stack_outputs, 'CertificateBucket')
        print("Found certificates S3 bucket: '{0}'.".format(self.__s3_bucket_name))

    def execute(self, mqtt_port, http_port):
        """
        Check the prerequisites and execute the steps required to setup Greengrass.
        :param mqtt_port: mqtt port used by greengrass.
        :param http_port: http port used by greengrass.
        """
        # Check if the AWS credentials were provided
        if boto3.session.Session().get_credentials() is None:
            raise Exception('There are no AWS credentials defined. '
                            'Please define them via environment variables.')

        # Set the AWS region
        if self.aws_region_name:
            boto3.setup_default_session(region_name=self.aws_region_name)

        # Get the certificate S3 bucket and the Greengrass group ID from the
        # output list of the CloudFormation stack.
        self.get_cfn_stack_outputs()

        GreengrassCertsProvisioner(self.__s3_bucket_name).execute(mqtt_port, http_port)
        GreengrassGroupDeployment(self.__gg_group_id).execute()


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
    parser.add_argument('--http-port', dest='http_port', type=int, default=443, choices=[8443, 443],
                        help='HTTP port used by Greengrass.')
    parser.add_argument('--setup-sja', dest='setup_sja', default=False, action='store_true',
                        help="Local ip address of the sja1110 interface.")

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

    if args.no_deploy:
        GreengrassCertsProvisioner.control_greengrass('restart')
    else:
        GreengrassSetup(args.cfn_stack_name,
                        args.aws_region_name).execute(args.mqtt_port, args.http_port)

    # Start the sja provisioning client.
    if args.setup_sja:
        # Network error occurs when publishing without a wait.
        time.sleep(10)
        SjaProvisioningClient(args.cfn_stack_name, args.aws_region_name, args.netif).execute()

# entry point
if __name__ == '__main__':
    main()
