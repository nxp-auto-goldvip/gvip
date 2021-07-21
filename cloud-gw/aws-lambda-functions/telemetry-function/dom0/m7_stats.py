#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2021 NXP
"""

import logging
import mmap
import os
import time
import threading


LOCK = threading.Lock()
LOGGER = logging.getLogger(__name__)

# Values of status registers of m7 cores.
CORE_INACTIVE = 0x0
CORE_ACTIVE = 0x1
CORE_WFI = 0x80000001

M7_0 = "m7_0"
M7_1 = "m7_1"
M7_2 = "m7_2"

# Address of /dev/mem registers for each core.
M7_CORES_STAT_REGISTERS = {
    M7_0: 0x40088148,
    M7_1: 0x40088168,
    M7_2: 0x40088188
}

# Sum of wfi flags values in the rolling window for each core.
ROLLING_WFI_SUM = {
    M7_0: 0,
    M7_1: 0,
    M7_2: 0
}

# Size of rolling windows for each core.
WINDOW_SIZE = {
    M7_0: 0,
    M7_1: 0,
    M7_2: 0
}

UPDATED = "updated"
NEW_MAX_WINDOW_SIZE = "new_max_window_size"
NEW_M7_STATUS_QUERY_TIME_INTERVAL = "new_m7_status_query_time_interval"

# Dictionary of updated values
MEASUREMENT_UPDATE = {
    UPDATED: False,
    NEW_MAX_WINDOW_SIZE: None,
    NEW_M7_STATUS_QUERY_TIME_INTERVAL: None
}

TERMINATE_THREAD = False


class M7CoreMovingAverage(threading.Thread):
    """
    Creates rolling average of M7 core loads.
    Continuously query each M7 core WFI register state.
    Wait For Interrupt (WFI) is a flag which states whether a core is
    active or not in a given moment.
    This class stores a moving window of wfi values from which the core load
    is deduced.
    """

    def __init__(self, max_window_size, m7_status_query_time_interval):
        """
        :param max_window_size: maximum size of the rolling window.
        :param m7_status_query_time_interval: time interval between WFI registers reads.
        """
        threading.Thread.__init__(self)

        self.max_window_size = max_window_size
        self.m7_status_query_time_interval = m7_status_query_time_interval

        # List of WFI values for each core in the moving window.
        self.window_values = {
            M7_0: [],
            M7_1: [],
            M7_2: []
        }

        self.file = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)

        self.mfile = mmap.mmap(
            self.file,
            mmap.PAGESIZE,
            mmap.MAP_SHARED,
            mmap.PROT_READ,
            offset=M7_CORES_STAT_REGISTERS[M7_0] & ~(mmap.PAGESIZE - 1))

    def run(self):
        """
        Thread run function.
        Runs in infinite loop and computes the moving window of wfi status values.
        """
        try:
            while not TERMINATE_THREAD:
                self._check_update()

                for core, addr in M7_CORES_STAT_REGISTERS.items():
                    status = self._get_status(addr)

                    if status == -1:
                        os.close(self.file)
                        LOGGER.error("M7 status returned erroneous value.")
                        return

                    # pylint: disable=consider-using-with
                    LOCK.acquire()
                    # Add current WFI
                    self.window_values[core].append(status)
                    ROLLING_WFI_SUM[core] += status
                    WINDOW_SIZE[core] += 1

                    # Remove last item from list only if list is at max length
                    if WINDOW_SIZE[core] > self.max_window_size:
                        last_wfi = self.window_values[core].pop(0)

                        # Discount last WFI
                        ROLLING_WFI_SUM[core] -= last_wfi
                        WINDOW_SIZE[core] -= 1

                    LOCK.release()

                time.sleep(self.m7_status_query_time_interval)
        # pylint: disable=broad-except
        except Exception as exception:
            LOGGER.error("M7 core stat error: %s", exception)
            os.close(self.file)

    def _get_status(self, core):
        """
        Queries the state of a M7 core at a certain moment.
        :param core: core-specific wfi register address.
        :ret: 0 if the core is idle or disabled. 1 if is active.
              -1 in case of erroneous value
        """
        self.mfile.seek(core & (mmap.PAGESIZE - 1))
        status = int.from_bytes(self.mfile.read(4), byteorder='little')

        if status == CORE_ACTIVE:
            return 1
        if status in [CORE_WFI, CORE_INACTIVE]:
            return 0
        return -1

    def _check_update(self):
        """
        Check if update is signaled. If yes update the values of window size
        and frequency.
        If new window is smaller then reduce the size of existing window lists.
        """
        # pylint: disable=consider-using-with
        LOCK.acquire()
        if not MEASUREMENT_UPDATE[UPDATED]:
            LOCK.release()
            return

        self.max_window_size = MEASUREMENT_UPDATE[NEW_MAX_WINDOW_SIZE]
        self.m7_status_query_time_interval = MEASUREMENT_UPDATE[NEW_M7_STATUS_QUERY_TIME_INTERVAL]

        for core in [M7_0, M7_1, M7_2]:
            WINDOW_SIZE[core] = 0
            self.window_values[core].clear()
            ROLLING_WFI_SUM[core] = 0

        MEASUREMENT_UPDATE[UPDATED] = False
        MEASUREMENT_UPDATE[NEW_MAX_WINDOW_SIZE] = None
        MEASUREMENT_UPDATE[NEW_M7_STATUS_QUERY_TIME_INTERVAL] = None
        LOCK.release()
        return

    @staticmethod
    def get_load():
        """
        Retrieves the core load for each M7 core.
        """
        m7_cores_load = dict()

        try:
            # pylint: disable=consider-using-with
            LOCK.acquire()
            for core, wfi_sum in ROLLING_WFI_SUM.items():
                m7_cores_load[core] = 100 * wfi_sum / WINDOW_SIZE[core]
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

        MEASUREMENT_UPDATE[UPDATED] = True
        MEASUREMENT_UPDATE[NEW_MAX_WINDOW_SIZE] = m7_window_size_multiplier * \
            telemetry_interval / new_m7_status_query_time_interval
        MEASUREMENT_UPDATE[NEW_M7_STATUS_QUERY_TIME_INTERVAL] = new_m7_status_query_time_interval

        LOCK.release()

        LOGGER.info("Updated M7 window size, new size: %d",
                    MEASUREMENT_UPDATE[NEW_MAX_WINDOW_SIZE])

    @staticmethod
    def terminate_thread():
        """Signal the termination of the run while loop."""
        # pylint: disable=global-statement
        global TERMINATE_THREAD
        TERMINATE_THREAD = True
