#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2021-2023 NXP
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
from health_mon import HealthMonStats
from idps_stats import IdpsStats
from mem_stats import MemStats
from net_stats import NetStats
from temperature_stats import TemperatureStats
from telemetry import M7CoreMovingAverage


# Configuration options
# Time interval between consecutive MQTT packets
TELEMETRY_INTERVAL = config.get("telemetry_interval", 1)
# List of interfaces for which network statistics are gathered
MONITORED_NETIFS = config.get("monitored_netifs", [])
# List of aliases for the monitored interfaces
MONITORED_NETIFS_ALIASES = config.get("monitored_netifs_aliases", None)
# M7 core status query time
M7_STAT_QUERY_TIME = config.get("m7_status_query_time_interval", 0.1)
# Logger verbosity flag
VERBOSE_FLAG = config.get("verbose", False)
# Device name
DEVICE = config.get("device", None)

# A lock for accessing the stats dict.
STATS_LOCK = threading.Lock()

# Setup logging to stdout
LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format="%(asctime)s|%(levelname)s| %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")

# pylint: disable=too-many-instance-attributes
class TelemetryAggregator:
    """
    Collects telemetry data from the system and puts data into a json format
    """
    def __init__(self):
        self.__telemetry_interval = TELEMETRY_INTERVAL
        # Retrieve platform information
        self.__current_platform = platform.platform()
        # Get instances for telemetry data
        self.__cpu_stats = CpuStats()
        self.__net_stats = NetStats(MONITORED_NETIFS, MONITORED_NETIFS_ALIASES)
        self.__m7_core_load = M7CoreMovingAverage(
            self.__telemetry_interval / M7_STAT_QUERY_TIME,
            M7_STAT_QUERY_TIME)
        self.__mem_stats = MemStats()
        self.__temperature_stats = TemperatureStats()
        self.__idps_stats = IdpsStats()
        self.__hmon_stats = HealthMonStats()
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
                hmon_stats = self.__hmon_stats.get_telemetry()

                platform_name = {
                    "platform" : self.__current_platform,
                    "device" : DEVICE,
                    "board_uuid_high" : self.__board_uuid[0],
                    "board_uuid_low" : self.__board_uuid[1],
                }

                telemetry_stats = {
                    **platform_name,
                    **net_stats,
                    **cpu_stats,
                    **mem_stats,
                    **m7_stats,
                    **temperature_stats,
                    **hmon_stats
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

                if config.get(VERBOSE_FLAG, False):
                    LOGGER.info("Updated system telemetry: %s\n", tot_stats)
            # pylint: disable=broad-exception-caught
            except Exception as exception:
                LOGGER.error("Failed to retrieve telemetry data: %s", exception)

            loop_exec_time = time.time() - loop_entry_time
            next_run = self.__telemetry_interval - loop_exec_time

            if next_run > 0:
                time.sleep(next_run)

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
