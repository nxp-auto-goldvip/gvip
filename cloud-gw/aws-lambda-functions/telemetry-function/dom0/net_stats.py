#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2020-2021, 2023 NXP
"""

from time import time

DEV = "/proc/net/dev"


class NetStats:
    """
    Reads and processes network stats from /proc/net/dev.
    """
    def __init__(self, monitored_ifaces=None, aliases=None):
        self._prev_net_stats = None
        self._net_load = {}
        self.previous_timestamp = None
        self.current_timestamp = None

        if not monitored_ifaces:
            self._monitored_ifaces = []
        else:
            self._monitored_ifaces = monitored_ifaces

        if not aliases:
            self._aliases = {}
        else:
            self._aliases = aliases

    # pylint: disable=too-many-locals
    def _read_stats(self):
        """
        Reads network statistics from /proc/net/dev file
        """
        stat_dict = {}

        desired_ifaces = set(self._monitored_ifaces)

        self.previous_timestamp = self.current_timestamp
        self.current_timestamp = time()

        with open(DEV, "r", encoding="utf-8") as file:
            # Read the first line.
            row_1 = file.readline().split("|")

            # Read the Second line, save the stat names.
            cols = []
            row_2 = file.readline().split("|")
            for i in range(1, len(row_2)):
                for stat_name in row_2[i].split():
                    # Change Receive to rx and Transmit to tx.
                    dirrection = row_1[i].strip()
                    if row_1[i].strip() == "Transmit":
                        dirrection = "tx"
                    elif row_1[i].strip() == "Receive":
                        dirrection = "rx"

                    cols.append(f"{dirrection}_{stat_name}")

            # Read the remaining lines, these contain the counters for each iface.
            for row in file:
                iface, _, values = row.partition(":")
                iface = iface.strip()

                # If desired ifaces are specified we only save their stats.
                if len(desired_ifaces) > 0 and iface not in desired_ifaces:
                    continue

                values = values.split()

                for i, col in enumerate(cols):
                    stat = self._aliases.get(iface, iface) + "_" + col
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

        for stat, raw_value in self._net_load.items():
            if stat.endswith("bytes"):
                stat_bps = stat[:-len("bytes")] + "bps"

                value = raw_value * 8.
                value /= delta_time

                new_dict[stat_bps] = value

            if stat.endswith("packets"):
                stat_pps = stat[:-len("packets")] + "pps"

                value = raw_value
                value /= delta_time

                new_dict[stat_pps] = value

        self._net_load.update(new_dict)

    def step(self):
        """
        Reads network stats and updates the aggregate stat counters
        and the stat loads for the interval between the last two
        interrogations.
        """
        stat_dict = self._read_stats()

        if self._prev_net_stats is None:
            self._prev_net_stats = stat_dict
        else:
            for stat, value in stat_dict.items():
                load = value - self._prev_net_stats[stat]
                self._net_load[stat] = load
                self._prev_net_stats[stat] = value

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
