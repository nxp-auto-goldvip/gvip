#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Collects the data required for the telemetry server charts.

Copyright 2022-2024 NXP
"""

import json
import logging
import sys
import threading
from time import time, sleep
from datetime import datetime

from dds_telemetry_sub import DDSTelemetrySubscriber

# Setup logging to stdout.
LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format="%(asctime)s|%(levelname)s| %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")

class SystemTelemetryCollector():
    """ Collects the telemetry data from the dom0 via a socket connection and compiles it in the
    format required to display. """
    TIMESERIES = {
        "dom0_vcpu_load": {"key": "dom0_vcpu_idle", "transform": lambda x: 100 - x},
        "pfe0_rx_mbps": {"key": "pfe0_rx_bps", "transform": lambda x: x / 1000000},
        "pfe0_tx_mbps": {"key": "pfe0_tx_bps", "transform": lambda x: x / 1000000},
        "pfe2_rx_mbps": {"key": "pfe2_rx_bps", "transform": lambda x: x / 1000000},
        "pfe2_tx_mbps": {"key": "pfe2_tx_bps", "transform": lambda x: x / 1000000},
        "mem_load": {"key": "mem_load", "transform": lambda x: x / 1024},
        "ddr_sram_temperature": None,
        "a53_cluster_temperature": None,
        "hse_llce_temperature": None,
        "m7_anomalies": None,
        "llce_anomalies": None,
        "hmon_1V1": None,
        "hmon_1V2": None,
        "hmon_1V8": None
    }

    # The raw system telemetry.
    RAW_DATA = {}
    # Lock for handling the RAW_DATA variable on the two threads.
    DATA_LOCK = threading.Lock()
    # Class which handles the dds communication.
    DDS_SUB = DDSTelemetrySubscriber(
        dds_domain_participant="TelemetryParticipantLibrary::TelemetryServerParticipant")

    def __init__(self, chart_window_size=60):
        """
        Initializes the telemetry data fields.
        :param chart_window_size: Size of the charts timeseries.
        """
        self.__chart_window_size = chart_window_size
        self.__timeseries_config = {}
        self.__data = {
            "timestamps": [],
            "time_range": [],
            "telemetry": {},
            "device": None
        }

        # Adding the Dom0 vCPU load timeseries
        # When running on G2, the entries specific to G3 will be ignored.
        for cpu_idx in range(0, 8):
            ts_key = f"dom0_vcpu{cpu_idx}_load"
            self.__timeseries_config[ts_key] = {
                "key": f"dom0_vcpu{cpu_idx}_idle",
                "transform": lambda x: 100 - x
            }
            self.__data["telemetry"][ts_key] = []

        # Adding the Cortex-M7 core loads.
        for cpu_idx in range(0, 4):
            ts_key = f"m7_{cpu_idx}"
            self.__timeseries_config[ts_key] = {
                "key": ts_key,
                "transform": None
            }
            self.__data["telemetry"][ts_key] = []

        for ts_key, ts_params in SystemTelemetryCollector.TIMESERIES.items():
            if not ts_params:
                ts_params = {}

            self.__timeseries_config[ts_key] = {
                "key": ts_params.get("key", ts_key),
                "transform": ts_params.get("transform", None)
            }
            self.__data["telemetry"][ts_key] = []

    @staticmethod
    def data_retriever_run():
        """ Start the data retriever loop in a separate thread. """
        threading.Thread(target=SystemTelemetryCollector.data_retriever).start()

    @staticmethod
    def data_retriever():
        """ Gets the latest system telemetry data every second. """
        while True:
            try:
                dds_messages = SystemTelemetryCollector.DDS_SUB.receive()
                with SystemTelemetryCollector.DATA_LOCK:
                    SystemTelemetryCollector.RAW_DATA = json.loads(dds_messages[0])
            # pylint: disable=broad-except
            except Exception as exception:
                LOGGER.error("Failed to get telemetry, received data: %s. Exception: %s\n", dds_messages, exception)

            sleep(1)

    def update_window_size(self, new_window_size):
        """
        Updates the charts window size. If the new size is smaller than
        the current one, truncate the timeseries to the new size.
        :param new_window_size: New size of the charts window display.
        """
        # Ignore timewindows smaller than 10 seconds.
        if new_window_size < 10:
            return

        if new_window_size < self.__chart_window_size:
            self.__data["timestamps"] = self.__data["timestamps"][-new_window_size - 1:]
            for key in self.__data["telemetry"]:
                if self.__data["telemetry"][key]:
                    self.__data["telemetry"][key] = self.__data["telemetry"][key][-new_window_size - 1:]

        self.__chart_window_size = new_window_size

    @staticmethod
    def get_raw_telemetry():
        """ Gets the data from the socket.
        Merges the system telemetry entry with the idps stats entry. if availabile. """
        raw_data = None

        with SystemTelemetryCollector.DATA_LOCK:
            raw_data = SystemTelemetryCollector.RAW_DATA
            SystemTelemetryCollector.RAW_DATA = {}

        data = {
            **raw_data.get("system_telemetry", {}),
            **raw_data.get("idps_stats", {}).get("can_idps", {}).get("global_stats", {})
        }

        return data

    def update_data(self):
        """ Update the telemetry data timeseries with the new
        data taken from the socket """
        raw_data = self.get_raw_telemetry()
        if not raw_data:
            return

        # Set the device type
        if not self.__data["device"]:
            self.__data["device"] = raw_data.get("device", "s32g2")

        # Set update the date timeseries
        self.__data["timestamps"].append(str(datetime.fromtimestamp(int(time()))))

        for ts_key, ts_params in self.__timeseries_config.items():
            # Ignore the G3 timeseries if there is no data for them.
            if ts_params["key"] not in raw_data:
                continue

            # Apply the transform lambda on the raw data and append it to the timeseries.
            if ts_params["transform"]:
                self.__data["telemetry"][ts_key].append(
                    ts_params["transform"](raw_data[ts_params["key"]]))
            else:
                self.__data["telemetry"][ts_key].append(raw_data[ts_params["key"]])

        # If the timeseries window is at its full length remove the tail element.
        if len(self.__data["timestamps"]) > self.__chart_window_size:
            self.__data["timestamps"].pop(0)
            for key in self.__data["telemetry"]:
                if self.__data["telemetry"][key]:
                    self.__data["telemetry"][key].pop(0)

        # Set the time range of the charts, a window of <chart_window_size> seconds.
        self.__data["time_range"] = [
            str(datetime.fromtimestamp(int(time()) - self.__chart_window_size + 1)),
            str(datetime.fromtimestamp(int(time())))
        ]

    def get_data(self):
        """ Getter for the chart data. """
        return self.__data
