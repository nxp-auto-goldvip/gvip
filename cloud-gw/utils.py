#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Auxiliary functions used for the provisioning scripts.

Copyright 2021 NXP
"""

import os
import re
import subprocess
import time


class Utils():
    """ Class containing general utility methods. """
    # Time in seconds used to wait for wpa_supplicant initialization.
    WPA_WAIT_TIME = 3

    # Certificate tarball names.
    GOLDVIP_SETUP_ARCHIVE = "GoldVIP_setup.tar.gz"
    SJA_CERTIFICATE = "Sja_Certificate.tar.gz"

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
    def setup_wireless_interface(
            netif, ssid=None, password=None,
            wpa_conf_file=os.path.join('/etc', 'wpa_supplicant.conf')):
        """
        Configure the wireless connection using wpa_supplicant tool.
        :param netif: wireless interface used for connection
        :param ssid: name of the wireless network to connect to
        :param password: network password
        :param wpa_conf_file: Path to the default configuration file for wpa_supplicant.
        """
        print('Starting the wpa_supplicant service...')

        # Stop wpa_supplicant, if it is running.
        Utils.execute_command('pkill wpa_supplicant || true')
        # If wpa_supplicant is killed, it will set the interface down. Bring it up again.
        Utils.execute_command('ip link set dev {0} up'.format(netif))
        # Start wpa_supplicand service on the given interface.
        Utils.execute_command('wpa_supplicant -i{0} -Dnl80211,wext -c{1} -B'.format(
            netif, wpa_conf_file))

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

    @staticmethod
    def pull_stack_outputs(cfn_client, cfn_stack_name):
        """
        Return a list of the cloudformation stack outputs.
        :param cfn_client: boto3 cloudformation client.
        :param cfn_stack_name: cloudformation stack name.
        """
        matching_stacks = cfn_client.describe_stacks(StackName=cfn_stack_name)['Stacks']

        if len(matching_stacks) != 1:
            raise Exception("The '{0}' CloudFormation stack does not exist."
                            .format(cfn_stack_name))

        return matching_stacks[0]['Outputs']

    @staticmethod
    def get_cfn_output_value(cfn_outputs, key):
        """
        Extract values from the CloufFormation stack's output list based on a given key.
        :param cfn_outputs: the outputs of CloudFormation stack.
        :param key: the OutputKey to search for.
        """
        matching_outputs = [output_data for output_data in cfn_outputs
                            if output_data['OutputKey'] == key]

        if len(matching_outputs) != 1:
            raise Exception("Couldn't find '{0}' in the output list.".format(key))

        return matching_outputs[0]['OutputValue']

    @staticmethod
    def check_certificates_tarball(s3_client, bucket_name, tar_name):
        """
        Check whether the specified bucket and tarball exists.
        :param s3_client: boto3 s3 client.
        :param bucket_name: name of the s3 bucket containing the certificates.
        :param tar_name: name of the tar object.
        """
        response = s3_client.head_bucket(Bucket=bucket_name)
        if response['ResponseMetadata']['HTTPStatusCode'] != 200:
            raise Exception("Bucket '{0}' does not exist or you don't have permission to access it."
                            .format(bucket_name))

        bucket_contents = s3_client.list_objects(Bucket=bucket_name)['Contents']
        if len(bucket_contents) == 0:
            raise Exception("S3 bucket is empty.")

        for s3_object in bucket_contents:
            if s3_object['Key'] == tar_name:
                return tar_name

        raise Exception("Bucket {0} does not contain tarball {1}.".format(bucket_name, tar_name))
