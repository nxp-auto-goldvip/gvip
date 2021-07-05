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
import re
import subprocess
import tarfile
import time

from io import BytesIO

import boto3


class Utils():
    """ Class containing general utility methods. """
    # Path to the default configuration file for wpa_supplicant.
    WPA_SUPPLICANT_CONF_FILE = os.path.join('/etc', 'wpa_supplicant.conf')
    # Time in seconds used to wait for wpa_supplicant initialization.
    WPA_WAIT_TIME = 3

    @staticmethod
    def execute_command(command, timeout=None):
        """
        Execute a command (process with arguments), capturing stdout, stderr and returns code.
        :param command: the command to execute
        :return: return code, stdout and stderr output
        """
        # pylint: disable=consider-using-with
        proc = subprocess.Popen(command, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, shell=True)

        try:
            std_out, std_err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            std_out, std_err = proc.communicate()

        if proc.returncode != 0:
            err_msg = 'Execution of command {0} resulted in error.\nstdout: {1}\nstderr: {2}' \
                      .format(command, std_out, std_err)
            raise Exception(err_msg)

        return proc.returncode, std_out, std_err

    @staticmethod
    def retry(func, retries, *args):
        """
        Retry the execution of a method (with arguments) on any exception.
        :param func: the function handler to execute
        :param retries: the number of retries to be made
        :param *args: the arguments used to call the function
        :return: value returned by the method
        """
        ret = None

        while retries:
            try:
                ret = func(*args)
            # pylint: disable=broad-except
            except Exception:
                retries -= 1
                time.sleep(5)
            else:
                break
        else:
            raise Exception('retry failed: {0}'.format(func.__name__))

        return ret

    @staticmethod
    def setup_wireless_interface(netif, ssid=None, password=None):
        """
        Configure the wireless connection using wpa_supplicant tool.
        :param netif: wireless interface used for connection
        :param ssid: name of the wireless network to connect to
        :param password: network password
        """
        print('Starting the wpa_supplicant service...')

        # Stop wpa_supplicant, if it is running.
        Utils.execute_command('pkill wpa_supplicant || true')
        # If wpa_supplicant is killed, it will set the interface down. Bring it up again.
        Utils.execute_command('ip link set dev {0} up'.format(netif))
        # Start wpa_supplicand service on the given interface.
        Utils.execute_command('wpa_supplicant -i{0} -Dnl80211,wext -c{1} -B'.format(
            netif, Utils.WPA_SUPPLICANT_CONF_FILE))

        # Wait a bit for proper initialization.
        time.sleep(Utils.WPA_WAIT_TIME)

        # Check whether we are already connected to a network.
        wpa_status = Utils.execute_command('wpa_cli status')[1].decode().splitlines()
        if 'wpa_state=COMPLETED' in wpa_status:
            used_ssid = [val for val in wpa_status if val.startswith('ssid=')][0].split('=', 1)[1]
            if not ssid or used_ssid == ssid:
                print("Successfully connected to '{0}'.".format(used_ssid))
                return

        # Create a new network configuration.
        wpa_network_id = Utils.execute_command('wpa_cli add_network')[1].decode().splitlines()[1]

        if ssid:
            # Setup de SSID.
            Utils.execute_command('wpa_cli set_network {0} ssid "\\"{1}\\""'.format(
                wpa_network_id, ssid))
            # Configure the network password.
            if password:
                Utils.execute_command('wpa_cli set_network {0} psk "\\"{1}\\""'.format(
                    wpa_network_id, password))

        if not password:
            Utils.execute_command('wpa_cli set_network {0} key_mgmt NONE'.format(wpa_network_id))

        # Connect to the configured network (it will disable the others).
        Utils.execute_command('wpa_cli select_network {0}'.format(wpa_network_id))

        # Give a bit of time for the connection to be established.
        time.sleep(Utils.WPA_WAIT_TIME)

        # Check whether we are already connected to a network.
        wpa_status = Utils.execute_command('wpa_cli status')[1].decode().splitlines()
        if 'wpa_state=COMPLETED' in wpa_status:
            used_ssid = [val for val in wpa_status if val.startswith('ssid=')][0].split('=', 1)[1]
            print("Successfully connected to '{0}'. Saving the configuration...".format(used_ssid))
            # Save the credentials for future use.
            Utils.execute_command('wpa_cli save_config')
        else:
            print("wpa_supplicant wasn't able to connect to any known network...")
            # Scan for nearby networks and list them for the user.
            avail_networks = Utils.execute_command('wpa_cli scan && wpa_cli scan_results')[1]
            print('(Hint) Nearby wireless networks:\n{0}'.format(avail_networks.decode()))

            raise Exception("Couldn't establish a connection to a known wireless network.")

    @staticmethod
    def setup_network_interface(netif, netip=None, ssid=None, password=None):
        """
        Setup a given network interface to be used for internet connection.
        :param netif: the network interface name.
        :param netip: optional IP to be set statically on the given interface.
        :param ssid: the SSID of the network to connect when using a wireless interface.
        :param password: the password of the wireless network.
        """
        try:
            print('Checking the internet connection...')
            Utils.execute_command('ping -c4 -I{0} 8.8.8.8'.format(netif))
        # pylint: disable=broad-except
        except Exception:
            print('Setting up the network interface...')

            # Bring up the given interface.
            Utils.execute_command('ip link set dev {0} up'.format(netif))

            # Generally, the wireless interface will start with ‘w’ (i.e. 'wlan0').
            if netif.startswith('w'):
                print('Wireless interface detected, configuring wpa_supplicant...')
                Utils.setup_wireless_interface(netif, ssid, password)

            # Set up the IP address on the given interface (statically or dynamically assigned).
            if netip:
                print('Setting up static IP address...')
                Utils.execute_command('ip address add {0} dev {1}'.format(netip, netif))
            else:
                print('Getting an IP address using DHCP client...')
                Utils.execute_command('udhcpc -nq -i{0} -t10'.format(netif))

        print("Setting '{0}' as the default network interface...".format(netif))
        # Increase the route metric so the given network interface will be used by default for
        # access to open internet.
        default_routes = Utils.execute_command('ip route show default to match 8.8.8.8')[1]
        for dev in re.findall(r"dev\s+(\S+)", default_routes.decode()):
            if dev != netif:
                Utils.execute_command('ifmetric {0} 1024'.format(dev))
        Utils.execute_command('ifmetric {0} 0'.format(netif))

    @staticmethod
    def sync_system_datetime():
        """
        Force a system datetime update by restarting the ntp daemon.
        """
        ntpd_path = os.path.join('/usr', 'sbin', 'ntpd')
        ntpd_pid_filename = os.path.join('/var', 'run', 'ntpd.pid')

        restart_ntp_service = '{0} -u ntp:ntp -p {1} -g'.format(ntpd_path, ntpd_pid_filename)
        sync_system_timedate = '{0} -gq'.format(ntpd_path)

        try:
            # Stop the ntp daemon, if it is running.
            Utils.execute_command('pkill ntpd || true')
            print('Synchronizing the system datetime with the ntp servers...')
            # Start the ntp to force the timedate sync.
            Utils.execute_command(sync_system_timedate, timeout=60)
        finally:
            # Re-establish the ntp service.
            Utils.execute_command(restart_ntp_service)


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
        with open(self.CONFIG_PATH, 'r+') as config_file:
            config = json.load(config_file)
            config["coreThing"]["iotMqttPort"] = mqtt_port
            config["coreThing"]["iotHttpPort"] = http_port
            config["coreThing"]["ggHttpPort"] = http_port
            config_file.seek(0, 0)
            config_file.write(json.dumps(config, indent=4))


    def ensure_certificates_tarball(self):
        """
        Check wheter the specified bucket exists and is accessible, then
        get the name of the setup tarball.
        """
        response = self.__s3_client.head_bucket(Bucket=self.bucket_name)
        if response['ResponseMetadata']['HTTPStatusCode'] != 200:
            raise Exception("Bucket '{0}' does not exist or you don't have permission to access it."
                            .format(self.bucket_name))

        bucket_contents = self.__s3_client.list_objects(Bucket=self.bucket_name,
                                                        MaxKeys=1)['Contents']
        if len(bucket_contents) != 1:
            raise Exception("Couldn't find any setup tarball in the S3 bucket.")

        self.__setup_tarball = bucket_contents[0]['Key']

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
        self.ensure_certificates_tarball()

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

    @staticmethod
    def _get_cfn_output_value(cfn_outputs, key):
        """
        Extract values from the CloufFormation stack's output list based on a given key.
        :param cfn_outputs: the outputs of CloudFormation stack
        :param key: the OutputKey to search for
        """
        matching_outputs = [output_data for output_data in cfn_outputs
                            if output_data['OutputKey'] == key]

        if len(matching_outputs) != 1:
            raise Exception("Couldn't find '{0}' in the output list.".format(key))

        return matching_outputs[0]['OutputValue']

    def get_cfn_stack_outputs(self):
        """
        Get the Greengrass group id and the S3 bucket name from the CloudFormation stack's
        output list.
        """
        cfn_client = boto3.client('cloudformation')
        matching_stacks = cfn_client.describe_stacks(StackName=self.cfn_stack_name)['Stacks']

        if len(matching_stacks) != 1:
            raise Exception("The '{0}' CloudFormation stack does not exist."
                            .format(self.cfn_stack_name))

        cfn_stack_outputs = matching_stacks[0]['Outputs']

        self.__gg_group_id = self._get_cfn_output_value(cfn_stack_outputs, 'GreengrassGroupId')
        print("Found Greengrass group ID: '{0}'.".format(self.__gg_group_id))
        self.__s3_bucket_name = self._get_cfn_output_value(cfn_stack_outputs, 'CertificateBucket')
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


# entry point
if __name__ == '__main__':
    main()
