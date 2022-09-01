#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2021-2022 NXP
"""

import json
import logging
import platform
import sys
import threading
import time

from app_data_collector_server import AppDataCollectorServer
from configuration import config
from cpu_stats import CpuStats
from dev_mem_uid import get_uid
from idps_stats import IdpsStats
from mem_stats import MemStats
from net_stats import NetStats
from temperature_stats import TemperatureStats
from telemetry import M7CoreMovingAverage


# Telemetry parameters
# time interval between MQTT packets
TELEMETRY_INTERVAL = "telemetry_interval"

# M7 core status query time
M7_STAT_QUERY_TIME = "m7_status_query_time_interval"

# M7 core status window size multiplier
# Used for getting M7 core load
M7_WINDOW_SIZE_MULTIPLIER = "m7_window_size_multiplier"

# A lock for accessing the config variable.
CONFIG_LOCK = threading.Lock()
# A lock for accessing the stats dict.
STATS_LOCK = threading.Lock()

# Setup logging to stdout.
LOGGER = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

# pylint: disable=too-many-instance-attributes
class TelemetryAggregator:
    """
    Collects telemetry data from the system and puts data into a json format
    """
    def __init__(self):
        # Retrieve platform information
        self.__current_platform = platform.platform()
        # Get instances for telemetry data
        self.__cpu_stats = CpuStats()
        self.__net_stats = NetStats(["pfe2", "pfe0"])
        self.__m7_core_load = M7CoreMovingAverage(
            config[TELEMETRY_INTERVAL] / config[M7_STAT_QUERY_TIME],
            config[M7_STAT_QUERY_TIME])
        self.__mem_stats = MemStats()
        self.__temperature_stats = TemperatureStats()
        self.__idps_stats = IdpsStats()
        self.__m7_core_load.start()
        self.__stats = None
        self.__board_uuid = get_uid()

        # Start the App Data Collector server in a separate thread.
        self.__app_data_collector = AppDataCollectorServer()
        threading.Thread(target=self.__app_data_collector.run).start()

    def __calculate_stats(self):
        """
        At every telemetry_interval seconds compiles a dictionary
        of all telemetry statistics and saves it as a string into a class variable.
        """
        while True:
            loop_entry_time = time.time()

            try:
                self.__cpu_stats.step(process=True)
                self.__net_stats.step()

                cpu_stats = self.__cpu_stats.get_load(scale_to_percents=True)
                mem_stats = self.__mem_stats.get_telemetry(verbose=False)
                net_stats = self.__net_stats.get_load()
                m7_stats = self.__m7_core_load.get_load()
                idps_stats = self.__idps_stats.get_telemetry()
                temperature_stats = self.__temperature_stats.get_temperature()

                platform_name = {
                    "platform" : self.__current_platform,
                    "device" : config["device"],
                    "board_uuid_high" : self.__board_uuid[0],
                    "board_uuid_low" : self.__board_uuid[1],
                }

                telemetry_stats = {
                    **platform_name,
                    **net_stats,
                    **cpu_stats,
                    **mem_stats,
                    **m7_stats,
                    **temperature_stats
                }

                tot_stats = {
                    "system_telemetry": telemetry_stats,
                }

                # Add IDPS data
                if idps_stats:
                    tot_stats.update({"idps_stats": {**idps_stats}})

                # Add the application data
                tot_stats.update(self.__app_data_collector.get_data())

                # Prepare stats as a string
                with STATS_LOCK:
                    self.__stats = json.dumps(tot_stats)

                with CONFIG_LOCK:
                    # Set telemetry interval for next function call
                    telemetry_interval = config[TELEMETRY_INTERVAL]
            # pylint: disable=broad-except
            except Exception as exception:
                LOGGER.error("Failed to retrieve telemetry data: %s", exception)

            loop_exec_time = time.time() - loop_entry_time
            next_run = telemetry_interval - loop_exec_time

            if next_run > 0:
                time.sleep(next_run)

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

        with CONFIG_LOCK:
            # get telemetry collector parameters
            config[TELEMETRY_INTERVAL] = \
                self.__extract_parameter(event_dict, TELEMETRY_INTERVAL, int, 1,
                                         config[TELEMETRY_INTERVAL])
            config[M7_STAT_QUERY_TIME] = \
                self.__extract_parameter(event_dict, M7_STAT_QUERY_TIME, float, 0.0001,
                                         config[M7_STAT_QUERY_TIME])
            config[M7_WINDOW_SIZE_MULTIPLIER] = \
                self.__extract_parameter(event_dict, M7_WINDOW_SIZE_MULTIPLIER, int, 1,
                                         config[M7_WINDOW_SIZE_MULTIPLIER])

        M7CoreMovingAverage.update_measurement(
            new_m7_status_query_time_interval=config[M7_STAT_QUERY_TIME],
            telemetry_interval=config[TELEMETRY_INTERVAL],
            m7_window_size_multiplier=config[M7_WINDOW_SIZE_MULTIPLIER])

    def get_stats(self):
        """
        Gets the telemetry stats calculated from the __calculate_stats function
        :return: stats in string format
        """
        with STATS_LOCK:
            return self.__stats

    def run(self):
        """
        Class entry point. Start the __calculate_stats function in another thread.
        """
        threading.Thread(target=self.__calculate_stats).start()
