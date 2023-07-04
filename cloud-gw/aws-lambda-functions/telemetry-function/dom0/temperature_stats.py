#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2021-2023 NXP
"""
import re
import os


# pylint: disable=too-few-public-methods
class TemperatureStats:
    """
    Reads and processes temperature stats
    from  /sys/devices/platform/soc/400a8000.tmu/hwmon/hwmon*
    """
    DIR_HWMON = "/sys/devices/platform/soc/400a8000.tmu/hwmon/"

    # Select the existing directory, it may be either hwmon0 or hwmon1.
    # It contains temperature monitoring data, each temperature data item of a site
    # is presented by a pair of files for example:
    #   temp1_label: contains label of the item, ex: Immediate temperature for site 0
    #   temp1_input: contains temperature value of the item, ex: 70000
    DIR_HWMON_OUTPUT = os.path.join(DIR_HWMON, os.listdir(DIR_HWMON)[0])

    # Get all files that contains temperature value
    # e.g. temp1_input, temp2_input,... temp6_input
    INPUT_FILES = [f for f in os.listdir(DIR_HWMON_OUTPUT) if re.match(r'temp[\d]_input', f)]

    # Tags which denote the placement of each temperature sensor.
    TAGS = {
        "immediate_temperature_0" : "ddr_sram_temperature",
        "immediate_temperature_1" : "a53_cluster_temperature",
        "immediate_temperature_2" : "hse_llce_temperature",
        "average_temperature_0" : "ddr_sram_average_temperature",
        "average_temperature_1" : "a53_cluster_average_temperature",
        "average_temperature_2" : "hse_llce_average_temperature"
    }

    @staticmethod
    def get_temperature():
        """
        Reads and parses measured temperature data to a dictionary
        :returns: a dictionary of stats.
        :rtype: dict
        """
        temperature_data = {}

        for input_file in TemperatureStats.INPUT_FILES:
            # Replace _input by _label to get name of the file that
            # contains label of the temperature data item
            label_file = input_file.replace("_input", "_label")
            # Path of the file that contains value of the temperature data item
            input_path = os.path.join(TemperatureStats.DIR_HWMON_OUTPUT, input_file)
            # Path of the file that contains label of the temperature data item
            label_path = os.path.join(TemperatureStats.DIR_HWMON_OUTPUT, label_file)

            # Read pair of label files to extract temperature data into key=>value
            with open(label_path, 'r', encoding='utf-8') as label_fh, \
                 open(input_path, 'r', encoding='utf-8') as input_fh:
                # Sample content of label files:
                #   Average temperature for site 0
                # or:
                #   Immediate temperature for site 0
                # Sample content of input files:
                #   70000
                label_values = label_fh.readline().strip().split(' ')
                temperature_value = input_fh.readline().strip()

                temperature_key = f"{label_values[0].lower()}_temperature_{label_values[-1]}"
                temperature_tag = TemperatureStats.TAGS[temperature_key]
                temperature_value = int(temperature_value)/1000
                temperature_data[temperature_tag] = temperature_value

        return temperature_data
