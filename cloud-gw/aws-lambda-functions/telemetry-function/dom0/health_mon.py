#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2023 NXP
"""

import os
import struct
import threading
# Time between health monitoring collect
HMON_COLLECT_INTERVAL = 0.1

# pylint: disable=too-few-public-methods
class HealthMonStats:
    """
    Telemetry collector class for health monitoring stats
    """
    # path to the ipc character device driver
    HMON_STATS_DEV = "/dev/ipcfshm/M7_0/health_mon"

    # Lock for accessing the stats variable.
    LOCK = threading.Lock()

    def __init__(self):
        self.__stats = {}
        self.__collect_stats()

    def __collect_stats(self):
        """
        Statistic collector, this function runs every HMON_COLLECT_INTERVAL seconds.
        This function checks if any new data was received on the HMON_STATS_DEV.
        In case new data was received, the function will save data in the stats variable.
        In case the data was not reset or read in the last HMON_COLLECT_INTERVAL,
        the function will reset the statistics.
        """

        with self.LOCK:
            # check if data is available
            if not os.path.exists(self.HMON_STATS_DEV):
                self.__stats = {}
            else:
                with open(self.HMON_STATS_DEV, "rb") as file_:
                    raw_data = file_.read()
                if len(raw_data) >= 12:
                    volt_values = struct.unpack("<III", raw_data[0:12])
                    self.__stats["hmon_1V1"] = volt_values[0]
                    self.__stats["hmon_1V2"] = volt_values[1]
                    self.__stats["hmon_1V8"] = volt_values[2]

        threading.Timer(HMON_COLLECT_INTERVAL, self.__collect_stats).start()

    def get_telemetry(self):
        """
        Getter method for health monitoring telemetry
        :returns: Dictionary containing aggregated data voltages from health monitoring
        """
        data = {}
        with self.LOCK:
            data = self.__stats
        return data
