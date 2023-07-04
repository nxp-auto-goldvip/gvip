#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2020-2023 NXP
"""

import json

#/proc/stat columns:
CPU_USER = 0 # Normal processes executing in user mode
CPU_NICE = 1 # Niced processes executing in user mode
CPU_SYS = 2 # Processes executing in kernel mode
CPU_IDLE = 3 # Idle time
CPU_IOWAIT = 4 # Waiting for I/O to complete
CPU_IRQ = 5 # Servicing interrupts
CPU_SOFTIRQ = 6 # Servicing soft interrupts

PROC_STAT = "/proc/stat"

STATS = {
    CPU_USER : "usermode",
    CPU_NICE : "nicemode",
    CPU_SYS : "kernelmode",
    CPU_IDLE : "idle",
    CPU_IOWAIT : "iowait",
    CPU_IRQ : "irq",
    CPU_SOFTIRQ : "softirq",
}


class CpuStats:
    """
    Computes the load of each cpu using the /proc/stat info.

    Stores the result of the last /proc/stat interrogation.
    Computes the load of each cpu core for the time interval between
    interrogations.
    """
    def __init__(self):
        self._prev_cpus_dict = None
        self._current_cpus_dict = None
        self._current_load_dict = {}
        self._items_no = None

    @staticmethod
    def _parse_stat_line(file):
        """
        Parses a line from the file.

        :param file: File object pointing to the opened file.
        :type file: file object
        :returns: Tuple of stat name and list of attributes.
        :rtype: (str, list)
        """
        line = file.readline()[:-1]
        line_s = line.split(" ")
        stat = line_s[0]
        items = []

        for i in range(1, len(line_s)):
            if line_s[i] == "":
                continue

            items.append(int(line_s[i]))

        return stat, items

    @staticmethod
    def _parse_cpu_telemetry():
        """
        Opens the /proc/stat file and reads the stats.

        :returns: a dictionary with each cpu and a list of integer values.
        :rtype: dict
        """
        cpus_dict = {}
        with open(PROC_STAT, "r", encoding="utf-8") as file:
            while True:
                stat, items = CpuStats._parse_stat_line(file)

                if not stat.startswith("cpu"):
                    break

                cpus_dict[stat] = items

        return cpus_dict

    def cpu_load(self, cpu_no, process=True):
        """
        Returns the load of a CPU, can normalize the values.

        The load is only for the interval between the current
        and previous read of the proc stat file (of the step function call)

        :param cpu_no: cpu core
        :type cpu_no: str
        :param process: A flag used to indicate wheder or not to
            normalize load values. (default is True)
        :type process: bool
        :returns: a list with the oresponding load for each field.
        :rtype: list
        """
        items_delta_sec = []
        items_load = []
        total_time = 0

        if self._items_no is None:
            self._items_no = len(self._current_cpus_dict[cpu_no])

        for i in range(self._items_no):
            # Compute the diference between previous and current
            # /proc/stat interogations
            item = self._current_cpus_dict[cpu_no][i]
            item -= self._prev_cpus_dict[cpu_no][i]
            items_delta_sec.append(item)

            # By summing all values of a line we get
            # the total time in this interval
            total_time += item

        if total_time == 0:
            print("Resolution too low\n")
            return None

        for i in range(self._items_no):
            if process:
                load = items_delta_sec[i] / total_time
                items_load.append(load)
            else:
                items_load.append(items_delta_sec[i])

        return items_load

    def step(self, process=True):
        """
        Reads /proc/stat file and updates the previous and current
        cpu data.

        :param process: A flag used to indicate wheder or not to
            normalize load values. (default is True)
        :type process: bool
        """
        self._current_cpus_dict = CpuStats._parse_cpu_telemetry()

        if self._prev_cpus_dict is not None:
            for cpu_no in self._current_cpus_dict:
                items_load = self.cpu_load(cpu_no, process)

                if items_load is None:
                    continue

                self._current_load_dict[cpu_no] = items_load

        self._prev_cpus_dict = self._current_cpus_dict

    def cpu_load_to_string(self, items=None):
        """
        Returns the cpu statistics as a string

        :param items: the list of cpu fields to get for each cpu
            (default is empty list, if so it takes all fields)
        :type items: list
        :return: stats as a string
        :rtype: str
        """
        if self._current_load_dict is None or self._items_no is None:
            return ""

        if not items:
            items = range(self._items_no)

        str_ret = ""

        for cpu_no, cpu_items in self._current_load_dict.items():
            str_ret += f"{cpu_no:5f} "
            for item in items:
                str_ret += f"{cpu_items[item]:5.2f} "

            str_ret += "\n"

        return str_ret

    def get_load(self, scale_to_percents=False):
        """
        Returns the loads for the interval given by the last two
        stat interrogations.

        :return: a dictionary where the key is a string containing
            the cpu number one of the fields; the value is a number
        :rtype: dict
        """
        load_dict = {}
        if self._current_load_dict is None:
            return load_dict

        scale = 1.

        if scale_to_percents:
            scale = 100.

        for cpu, value in self._current_load_dict.items():
            for i in range(CPU_IDLE + 1):
                stat_name = f"dom0_v{cpu}_{STATS[i]}"
                load_dict[stat_name] = scale * value[i]

        return load_dict

    def to_json(self):
        """
        :return: cpu loads as a json formatted string.
        :rtype: str
        """
        if self._current_load_dict is None or self._items_no is None:
            return json.dumps({})

        return json.dumps(self._current_load_dict)
