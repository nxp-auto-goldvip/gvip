#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2022-2023 NXP
"""
import binascii
import logging
import os
import struct
import sys
import threading
import time

# Setup logging to stdout.
LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format="%(asctime)s|%(levelname)s| %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")

# Time between idps collect
IDPS_COLLECT_INTERVAL = 1

# IDPS data expiration interval. If statistics are not read within this time frame
# the statistics will be deleted.
IDPS_DATA_EXPIRATION_INTERVAL = 60


# pylint: disable=too-few-public-methods
class CanIdpsStats:
    """
    Telemetry collector class for IDPS statistics
    """
    # path to the ipc character device driver
    CAN_STATS_DEV = "/dev/ipcfshm/M7_0/idps_statistics"
    # Each entry from the CAN_STATS_DEV contains 4 Bytes which denote the input message size
    IPCF_CH_DEV_MSG_SIZE = 4
    # Minimum message size of one IDPS entry
    CAN_IDPS_MIN_MSG_SIZE = 22
    # Lock for accessing the stats variable.
    LOCK = threading.Lock()
    # Specific identifiers for LLCE/M7 IDPS
    LLCE_ENGINE_ID = 0
    M7_ENGINE_ID = 1

    def __init__(self):
        """
        Initializes the local stats variables and starts the telemetry collector thread
        """
        # statistics
        self.__stats = None
        # variable denoting the latest data reset
        self.__last_data_reset = None
        # marker for ipcf device driver availability
        self.__ipcf_dev_available = False
        self.__reset_stats()
        self.__collect_stats()

    def __reset_stats(self):
        """
        Resets the statistics variable and updates the last_data_reset variable
        """
        self.__last_data_reset = time.time()
        with self.LOCK:
            self.__stats = {"global_stats": {"m7_anomalies": 0, "llce_anomalies": 0},
                            "idps_data": []}

    def get_telemetry(self):
        """
        Function used to get data from the internal statistics structure.
        After data is copied, the structure is reset to its original values.
        In case the IPCF device driver is not available, an empty dictionary is returned
        :returns: dictionary containing IDPS statistics or empty dictionary in case
        the IDPS statistics are not available
        """
        data = {}
        if self.__ipcf_dev_available:
            with self.LOCK:
                data = self.__stats
        self.__reset_stats()
        return data

    def __update_telemetry_stats(self, data_entries):
        """
        Updates the local stats variable with the latest entry received
        from the character device driver
        :param data_entries: list of dictionaries containing CAN IDPS data
        """
        if not data_entries:
            return

        with self.LOCK:
            self.__stats["idps_data"].extend(data_entries)
            # update global stats based on the added entries
            for entry in data_entries:
                if entry["engine_id"] is self.LLCE_ENGINE_ID:
                    self.__stats["global_stats"]["llce_anomalies"] += 1
                elif entry["engine_id"] is self.M7_ENGINE_ID:
                    self.__stats["global_stats"]["m7_anomalies"] += 1

    def __parse_input_data(self, raw_data):
        """
        Parses the input data received from the IPCF character device driver
        and returns the data formatted as a list of dictionaries
        :param raw_data: byte array read from the IPCF character device driver
        :returns: list of dictionaries containing formatted data per each IDPS entry
        """
        total_data_size = len(raw_data)
        idps_statistics = []
        # parsed data index
        p_idx = 0
        while p_idx < total_data_size:
            # first 4 bytes is the message (specific to the IPCF character device driver)
            msg_size = int.from_bytes(raw_data[p_idx: p_idx + self.IPCF_CH_DEV_MSG_SIZE], "big")
            if msg_size < self.CAN_IDPS_MIN_MSG_SIZE:
                LOGGER.error("Invalid data length received via IPCF via %s, having message "
                             "size of %s Bytes, expected %s",
                             self.CAN_STATS_DEV, msg_size, self.CAN_IDPS_MIN_MSG_SIZE)
                break
            # get to the next index
            p_idx += self.IPCF_CH_DEV_MSG_SIZE
            # next 22 bytes are the payload which does not change
            idps_values = struct.unpack("<BBIIIII",
                                        raw_data[p_idx: p_idx + self.CAN_IDPS_MIN_MSG_SIZE])
            data_entry = dict(zip(["engine_id", "idps_status", "timestamp", "message_id", "bus_id",
                                   "detection_tag", "dbg_data_len"], idps_values))
            # increment p
            p_idx += self.CAN_IDPS_MIN_MSG_SIZE
            if data_entry["dbg_data_len"]:
                # copy remaining data and increment parsing index
                # as json cannot serialize byte arrays, we need to decode the string
                data_entry["dbg_data"] = binascii.hexlify(
                    raw_data[p_idx: p_idx + data_entry["dbg_data_len"]]).decode()
                p_idx += data_entry["dbg_data_len"]

            idps_statistics.append(data_entry)

        return idps_statistics

    def __collect_stats(self):
        """
        Statistic collector, this function runs every IDPS_COLLECT_INTERVAL.
        This function checks if any new data was received on the CAN_STATS_DEV.
        In case new data was received, the function will save data in the stats variable.
        In case the data was not reset or read in the last IDPS_DATA_EXPIRATION_INTERVAL,
        the function will reset the statistics, invalidating the entries added in the last
        IDPS_DATA_EXPIRATION_INTERVAL.
        """
        # Reset data in case it wasn't fetched in the last IDPS data expiration interval
        if time.time() - self.__last_data_reset > IDPS_DATA_EXPIRATION_INTERVAL:
            self.__reset_stats()

        # check if CAN data is available
        if not os.path.exists(self.CAN_STATS_DEV):
            self.__ipcf_dev_available = False
        else:
            self.__ipcf_dev_available = True
            with open(self.CAN_STATS_DEV, "rb") as file_:
                raw_data = file_.read()
            if raw_data:
                self.__update_telemetry_stats(self.__parse_input_data(raw_data))

        threading.Timer(IDPS_COLLECT_INTERVAL, self.__collect_stats).start()


# pylint: disable=too-few-public-methods
class IdpsStats:
    """
    Aggregator class, responsible for collecting IDPS data for
    CAN and ETH (not currently supported) interfaces.
    """
    def __init__(self):
        self.__can_idps = CanIdpsStats()

    def get_telemetry(self):
        """
        Aggregates telemetry from CAN and ETH IDPS.
        :returns: Dictionary containing aggregated data for ETH and CAN IDPS
        """
        idps_data = {}
        can_idps_data = self.__can_idps.get_telemetry()
        if can_idps_data:
            idps_data = {"can_idps": can_idps_data}
        return idps_data
