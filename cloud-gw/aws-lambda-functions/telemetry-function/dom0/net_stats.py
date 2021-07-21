#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2020-2021 NXP
"""

from time import time

DEV = "/proc/net/dev"


class NetStats:
    """
    Reads and processes network stats from /proc/net/dev.
    """
    def __init__(self, desired_ifaces=None):
        self._prev_net_stats = None
        self._net_load = {}
        self.previous_timestamp = None
        self.current_timestamp = None

        if not desired_ifaces:
            self._desired_ifaces = []
        else:
            self._desired_ifaces = desired_ifaces

    def _read_stats(self, desired_ifaces):
        """
        Reads network statistics from /proc/net/dev file

        :param desired_ifaces: A list that specifies the desired interfaces.
            If empty the function will return all interfaces.
        :type desired_faces: List[str]
        :returns: a dictionary of stats.
        :rtype: dict
        """
        stat_dict = {}

        desired_ifaces = set(desired_ifaces)

        self.previous_timestamp = self.current_timestamp
        self.current_timestamp = time()

        with open(DEV, "r") as file:
            # Read the first line.
            row_1 = file.readline().split("|")

            # Read the Second line, save the stat names.
            col = []
            row_2 = file.readline().split("|")
            for i in range(1, len(row_2)):
                for stat_name in row_2[i].split():
                    col.append("{}_{}".format(row_1[i].strip(), stat_name))

            # Read the remaining lines, these contain the counters for each iface.
            for row in file:
                iface, _, values = row.partition(":")
                iface = iface.strip()

                # If desired ifaces are specified we only save their stats.
                if len(desired_ifaces) > 0:
                    if iface not in desired_ifaces:
                        continue

                    values = values.split()

                    for i, _ in enumerate(col):
                        stat = iface + "_" + col[i]
                        val = int(values[i])
                        stat_dict[stat] = val
                else:
                    values = values.split()

                    for i, _ in enumerate(col):
                        # Add the iface name to the stat.
                        stat = iface + "_" + col[i]
                        val = int(values[i])
                        stat_dict[stat] = val

        return stat_dict

    def compute_bits_per_second(self):
        """
        Adds bits per second and packets per second stats for received
        transmitted traffic for all queried interfaces.
        """
        delta_time = self.current_timestamp - self.previous_timestamp
        new_dict = {}

        for stat in self._net_load:
            if stat.endswith("bytes"):
                stat_bps = stat[:-len("bytes")] + "bps"

                value = self._net_load[stat]
                value *= 8.
                value /= delta_time

                new_dict[stat_bps] = value

            if stat.endswith("packets"):
                stat_pps = stat[:-len("packets")] + "pps"

                value = self._net_load[stat]
                value /= delta_time

                new_dict[stat_pps] = value

        self._net_load.update(new_dict)

    def step(self):
        """
        Reads network stats and updates the aggregate stat counters
        and the stat loads for the interval between the last two
        interrogations.
        """
        stat_dict = self._read_stats(self._desired_ifaces)

        if self._prev_net_stats is None:
            self._prev_net_stats = stat_dict
        else:
            for stat in stat_dict:
                load = stat_dict[stat] - self._prev_net_stats[stat]
                self._net_load[stat] = load
                self._prev_net_stats[stat] = stat_dict[stat]

            self.compute_bits_per_second()

    def get_load(self):
        """
        :returns: a dictionary of network stats load
        :rtype: dict
        """
        if self._prev_net_stats is None:
            return {}

        return self._net_load

    def get_total_counters(self):
        """
        :returns: a dictionary of aggregate network stats
        :rtype: dict
        """
        if self._prev_net_stats is None:
            return {}

        return self._prev_net_stats
