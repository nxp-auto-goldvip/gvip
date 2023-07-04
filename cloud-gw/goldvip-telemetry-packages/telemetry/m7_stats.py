#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2021-2023 NXP
"""

import logging
import mmap
import os
import time
import threading

from collections import defaultdict

from configuration import config

LOCK = threading.Lock()
LOGGER = logging.getLogger(__name__)


class M7CoreMovingAverage(threading.Thread):
    """
    Creates rolling average of M7 core loads.
    Continuously query each M7 core WFI register state.
    Wait For Interrupt (WFI) is a flag which states whether a core is
    active or not in a given moment.
    This class stores a moving window of wfi values from which the core load
    is deduced.
    """
    M7_CORES = config["M7_CORES_STAT_REGISTERS"].keys()

    # Values of status registers of m7 cores.
    CORE_INACTIVE = int(config["CORE_INACTIVE"], 16)
    CORE_ACTIVE = int(config["CORE_ACTIVE"], 16)
    CORE_WFI = int(config["CORE_WFI"], 16)

    # Address of /dev/mem registers for each core.
    M7_CORES_STAT_REGS = config["M7_CORES_STAT_REGISTERS"]

    M7_0_STAT_ADDR = int(min(M7_CORES_STAT_REGS.values()), 16)

    # Sum of wfi flags values in the rolling window for each core.
    ROLLING_WFI_SUM = defaultdict(int)

    # Size of rolling windows for each core.
    WINDOW_SIZE = defaultdict(int)

    WINDOW_VALUES = defaultdict(list)

    # Dictionary of updated values
    MEASUREMENT_UPDATE = {
        "updated": False,
        "new_max_window_size": '',
        "new_m7_status_query_time_interval": ''
    }

    TERMINATE_THREAD = False

    def __init__(self, max_window_size, m7_status_query_time_interval):
        """
        :param max_window_size: maximum size of the rolling window.
        :param m7_status_query_time_interval: time interval between WFI registers reads.
        """
        threading.Thread.__init__(self)

        self.max_window_size = max_window_size
        self.m7_status_query_time_interval = m7_status_query_time_interval

        self.file = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)

        self.mfile = mmap.mmap(
            self.file,
            mmap.PAGESIZE,
            mmap.MAP_SHARED,
            mmap.PROT_READ,
            offset=M7CoreMovingAverage.M7_0_STAT_ADDR & ~(mmap.PAGESIZE - 1))

    def run(self):
        """
        Thread run function.
        Runs in infinite loop and computes the moving window of wfi status values.
        """
        try:
            while not self.TERMINATE_THREAD:
                self.__check_update()

                for core, addr in self.M7_CORES_STAT_REGS.items():
                    status = self.__get_status(int(addr, 16))

                    if status == -1:
                        os.close(self.file)
                        LOGGER.error("M7 status returned erroneous value.")
                        return

                    # pylint: disable=consider-using-with
                    LOCK.acquire()
                    # Add current WFI
                    self.WINDOW_VALUES[core].append(status)
                    self.ROLLING_WFI_SUM[core] += status
                    self.WINDOW_SIZE[core] += 1

                    # Remove last item from list only if list is at max length
                    if self.WINDOW_SIZE[core] > self.max_window_size:
                        last_wfi = self.WINDOW_VALUES[core].pop(0)

                        # Discount last WFI
                        self.ROLLING_WFI_SUM[core] -= last_wfi
                        self.WINDOW_SIZE[core] -= 1

                    LOCK.release()

                time.sleep(self.m7_status_query_time_interval)
        # pylint: disable=broad-exception-caught
        except Exception as exception:
            LOGGER.error("M7 core stat error: %s", exception)
            os.close(self.file)

    def __get_status(self, core):
        """
        Queries the state of a M7 core at a certain moment.
        :param core: core-specific wfi register address.
        :ret: 0 if the core is idle or disabled. 1 if is active.
              -1 in case of erroneous value
        """
        self.mfile.seek(core & (mmap.PAGESIZE - 1))
        status = int.from_bytes(self.mfile.read(4), byteorder='little')

        if status == self.CORE_ACTIVE:
            return 1
        if status in [self.CORE_WFI, self.CORE_INACTIVE]:
            return 0
        return -1

    def __check_update(self):
        """
        Check if update is signaled. If yes update the values of window size
        and frequency.
        If new window is smaller then reduce the size of existing window lists.
        """
        # pylint: disable=consider-using-with
        LOCK.acquire()
        if not self.MEASUREMENT_UPDATE["updated"]:
            LOCK.release()
            return

        self.max_window_size = self.MEASUREMENT_UPDATE["new_max_window_size"]
        self.m7_status_query_time_interval = \
            self.MEASUREMENT_UPDATE["new_m7_status_query_time_interval"]

        for core in self.M7_CORES:
            self.WINDOW_SIZE[core] = 0
            self.WINDOW_VALUES[core].clear()
            self.ROLLING_WFI_SUM[core] = 0

        self.MEASUREMENT_UPDATE["updated"] = False
        self.MEASUREMENT_UPDATE["new_max_window_size"] = None
        self.MEASUREMENT_UPDATE["new_m7_status_query_time_interval"] = None
        LOCK.release()
        return

    @staticmethod
    def get_load():
        """
        Retrieves the core load for each M7 core.
        """
        m7_cores_load = {}

        try:
            # pylint: disable=consider-using-with
            LOCK.acquire()
            for core, wfi_sum in M7CoreMovingAverage.ROLLING_WFI_SUM.items():
                m7_cores_load[core] = 100 * wfi_sum / M7CoreMovingAverage.WINDOW_SIZE[core]
            LOCK.release()
        except ZeroDivisionError:
            return {}

        return m7_cores_load

    @staticmethod
    def update_measurement(
            new_m7_status_query_time_interval,
            telemetry_interval,
            m7_window_size_multiplier):
        """
        Set the new values for window size and frequency.
        Signals that a update is needed.
        :param new_m7_status_query_time_interval: new frequency
        :param telemetry_interval: new interval between telemetry messages
        :param m7_window_size_multiplier:
        """
        # pylint: disable=consider-using-with
        LOCK.acquire()

        M7CoreMovingAverage.MEASUREMENT_UPDATE["updated"] = True
        M7CoreMovingAverage.MEASUREMENT_UPDATE["new_max_window_size"] = \
            m7_window_size_multiplier * telemetry_interval / new_m7_status_query_time_interval
        M7CoreMovingAverage.MEASUREMENT_UPDATE["new_m7_status_query_time_interval"] = \
            new_m7_status_query_time_interval

        LOCK.release()

        LOGGER.info("Updated M7 window size, new size: %d", \
            M7CoreMovingAverage.MEASUREMENT_UPDATE["new_max_window_size"])

    @staticmethod
    def terminate_thread():
        """Signal the termination of the run while loop."""
        M7CoreMovingAverage.TERMINATE_THREAD = True
