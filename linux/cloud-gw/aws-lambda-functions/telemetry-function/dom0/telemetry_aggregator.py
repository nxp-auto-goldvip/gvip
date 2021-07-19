#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2021 NXP
"""

import json
import logging
import os
import platform
import sys
import threading

from cpu_stats import CpuStats
from dev_mem_uid import get_uid
from mem_stats import MemStats
from net_stats import NetStats
from m7_stats import M7CoreMovingAverage

# Telemetry parameters
# time interval between MQTT packets
TELEMETRY_INTERVAL = "telemetry_interval"

# M7 core status query time
M7_STAT_QUERY_TIME = "m7_status_query_time_interval"

# M7 core status window size multiplier
# Used for getting M7 core load
M7_WINDOW_SIZE_MULTIPLIER = "m7_window_size_multiplier"

# A lock for accessing the config variable.
LOCK = threading.Lock()

# Setup logging to stdout.
LOGGER = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

class TelemetryAggregator:
    """
    Collects telemetry data from the system and puts data into a json format
    """
    def __init__(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "config.json")) as config_file:
            self.__config = json.load(config_file)

        # Retrieve platform information
        self.__current_platform = platform.platform()
        # Get instances for telemetry data
        self.__cpu_stats = CpuStats()
        self.__net_stats = NetStats(["pfe2", "pfe0"])
        self.__m7_core_load = M7CoreMovingAverage(
            max_window_size=self.__config[TELEMETRY_INTERVAL] / self.__config[M7_STAT_QUERY_TIME],
            m7_status_query_time_interval=self.__config[M7_STAT_QUERY_TIME])
        self.__mem_stats = MemStats()
        self.__m7_core_load.start()
        self.__stats = None

    def __calculate_stats(self):
        """
        Compiles a dictionary of all telemetry statistics and
        saves it as a string into a class variable
        """
        self.__cpu_stats.step(process=True)
        self.__net_stats.step()

        cpu_stats = self.__cpu_stats.get_load(scale_to_percents=True)
        mem_stats = self.__mem_stats.get_telemetry(verbose=False)
        net_stats = self.__net_stats.get_load()
        m7_stats = self.__m7_core_load.get_load()

        platform_name = {
            "Device" : self.__current_platform,
            "board_uuid_high" : get_uid()[0],
            "board_uuid_low" : get_uid()[1],
        }

        tot_stats = {
            **platform_name,
            **net_stats,
            **cpu_stats,
            **mem_stats,
            **m7_stats
        }

        # Prepare stats as a string
        self.__stats = json.dumps(tot_stats)

        with LOCK:
            # Set telemetry interval for next function call
            telemetry_interval = self.__config[TELEMETRY_INTERVAL]

        threading.Timer(telemetry_interval, self.__calculate_stats).start()

    @staticmethod
    def __extract_parameter(event, parameter_name, parameter_type, min_value, default):
        """
        Extracts parameters from an event dictionary. If the event does not
        contain the desired value, the default is returned
        :param event: Event in json format
        :param parameter_name: Parameter name which shall be a key in the
        event dictionary
        :param parameter_type: Parameter type (int, float)
        :param min_value: Minimum accepted value
        :param default: Parameter default (in case the event does not contain
        the desired parameter, this value will be returned
        :return: updated parameter value/default
        """
        # get new parameter value from the event
        updated_param_value = event.get(parameter_name, default)

        # if the type is not correct, cast the parameter
        if not isinstance(updated_param_value, parameter_type):
            try:
                # cast to the expected format
                updated_param_value = parameter_type(updated_param_value)
            except ValueError:
                updated_param_value = default

        if updated_param_value != default:
            if updated_param_value < min_value:
                # new value is not valid
                updated_param_value = default
            else:
                # Log the updated value
                LOGGER.info("Updated %s, new value %s",
                    parameter_name.replace("_", " "), updated_param_value)
        return updated_param_value

    def update_configuration_parameters(self, event):
        """
        Checks if the event contains new values for the configuration,
        and updates them accordingly.
        :param event: The MQTT message in json string  format.
        """
        try:
            event_dict = json.loads(event)
        except ValueError:
            # Malformed event, discard value
            return

        with LOCK:
            # get telemetry collector parameters
            self.__config[TELEMETRY_INTERVAL] = \
                self.__extract_parameter(event_dict, TELEMETRY_INTERVAL, int, 1,
                                         self.__config[TELEMETRY_INTERVAL])
            self.__config[M7_STAT_QUERY_TIME] = \
                self.__extract_parameter(event_dict, M7_STAT_QUERY_TIME, float, 0.0001,
                                         self.__config[M7_STAT_QUERY_TIME])
            self.__config[M7_WINDOW_SIZE_MULTIPLIER] = \
                self.__extract_parameter(event_dict, M7_WINDOW_SIZE_MULTIPLIER, int, 1,
                                         self.__config[M7_WINDOW_SIZE_MULTIPLIER])

        M7CoreMovingAverage.update_measurement(
            new_m7_status_query_time_interval=self.__config[M7_STAT_QUERY_TIME],
            telemetry_interval=self.__config[TELEMETRY_INTERVAL],
            m7_window_size_multiplier=self.__config[M7_WINDOW_SIZE_MULTIPLIER])

    def get_stats(self):
        """
        Gets the telemetry stats calculated from the __calculate_stats function
        :return: stats in string format
        """
        return self.__stats

    def run(self):
        """
        Class entry point. This function shall be called once. It will start the
        Thread responsible for telemetry data calculation
        """
        self.__calculate_stats()