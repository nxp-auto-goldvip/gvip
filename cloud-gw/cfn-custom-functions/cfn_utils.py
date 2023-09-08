#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Functions to encode (and decode) a dictionary of ids into a string.

Copyright 2021-2023 NXP
"""
import json
import logging

import boto3

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

class Utils:
    """
    Functions that transform a dictionary into a string, and vice versa.
    """
    # Label to common configuration of all platforms
    COMMON_CONFIG_LABEL = "common"
    DASHBOARD_LABEL = "dashboards"

    @staticmethod
    def recursive_dict_merge(orig_dict, new_dict):
        """
        Recursively merges two dictionaries
        :param orig_dict: the first dict to merge, this is updated in place.
        :param new_dict: the second dict to merge.
        :return: the orig_dict, updated with the values from the second one.
        """
        for key, val in new_dict.items():
            if isinstance(val, dict):
                orig_dict[key] = Utils.recursive_dict_merge(orig_dict.get(key, { }), val)
            elif isinstance(val, list):
                orig_dict[key] = orig_dict.get(key, []) + val
            else:
                orig_dict[key] = new_dict[key]
        return orig_dict

    @staticmethod
    def parse_sitewise_config(config_path, device_type):
        """
        Parse the Sitewise configuration

        :param config_path: path to the Sitewise configuration file
        :param device_type: Platform device
        :return: Sitewise configuration
        """

        with open(config_path, 'r', encoding='utf-8') as config_file:
            configs = json.load(config_file)

        # Merge common configuration and specific device configuration
        config = configs[Utils.COMMON_CONFIG_LABEL]
        Utils.recursive_dict_merge(
            config[Utils.DASHBOARD_LABEL],
            configs[device_type][Utils.DASHBOARD_LABEL]
            )

        return config

    @staticmethod
    def set_cloudwatch_retention(stack_name, region, retention_days=14):
        """
        Retrieves the cloudwatch logs associated with the current cloudformation stack
        and sets them to expire after a number of days.
        :param stack_name: The name of the current cloudforamtion stack.
        :param region: AWS region name.
        :param retention_days: Number of days after which the logs will be deleted.
                               Possible values are: [1, 3, 5, 7, 14, 30, 60, 90, 120, ...]
        """
        try:
            client = boto3.client('logs', region_name=region)
            for page in client.get_paginator('describe_log_groups').paginate(logGroupNamePattern=stack_name):
                for log in page['logGroups']:
                    client.put_retention_policy(logGroupName=log['logGroupName'], retentionInDays=retention_days)
        # pylint: disable=broad-exception-caught
        except Exception as err:
            LOGGER.error("Failed to set retention in cloudwatch logs: %s", err)


    @staticmethod
    def encode_ids(ids_dict):
        """
        Packs dictionary ids into a id string
        :param ids_dict: Dictionary of resource ids
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
        """
        key_values = ids_str.split("|")
        ids_dict = {}

        for entry in key_values:
            key, _, value = entry.partition(":")

            ids_dict[key] = value

        return ids_dict
