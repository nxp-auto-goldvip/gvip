#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2020-2021 NXP
"""

# The number of rows to get from the /proc/meminfo file.
MEM_NUMBER_ITEMS = 5
MEM_INFO = "/proc/meminfo"


class MemStats:
    """
    A class that contains methods for retrieving memory statistics
    from /proc/meminfo file.
    """

    @staticmethod
    def get_telemetry(verbose=False):
        """
        Reads /proc/meminfo and parses its contents into key:value pairs

        :param verbose: A flag that indicates how values are returned;
            as a int if False, as a string if True. (Default is False)
        :type verbose: bool
        :return: A dictionary of (stat name, stat value) pairs
        :rtype: dict
        """
        mem_dict = {}

        with open(MEM_INFO, "r") as file:
            for _ in range(MEM_NUMBER_ITEMS):
                line = file.readline()
                stat, _, line = line.partition(":")

                if stat.startswith("Mem"):
                    stat = stat[3:]

                stat = "mem_" + stat

                if verbose:
                    val = line.strip()
                    mem_dict[stat] = val
                else:
                    val, _, _ = line.strip().partition(" ")
                    mem_dict[stat] = int(val)

            if "mem_Available" in mem_dict:
                mem_dict["mem_Load"] = mem_dict["mem_Total"] - mem_dict["mem_Available"]
            elif "mem_Free" in mem_dict:
                mem_dict["mem_Load"] = mem_dict["mem_Total"] - mem_dict["mem_Free"]

        return mem_dict

    @staticmethod
    def mem_load():
        """
        Normalizes the values from parse_mem_telemetry.

        Normalization of values only makes sense when they are stored as
        numbers. Values are transformed into floating point numbers in the
        range of [0, 1] where 1 represents the entire RAM memory of the os.

        :returns: A dictionary of (stat name, stat value) pairs
        :rtype: dict
        """
        mem_dict = MemStats.get_telemetry(verbose=False)
        mem_total = mem_dict["mem_Total"]

        for item in mem_dict:
            mem_dict[item] /= mem_total

        return mem_dict

    @staticmethod
    def mem_load_to_string():
        """
        Formats the dictionary information form mem_load as a string.

        :return: the load as a string
        :rtype: str
        """
        mem_dict = MemStats.mem_load()
        str_ret = ""

        for item in mem_dict:
            str_ret += "{:14} {:5.2f}\n".format(item, mem_dict[item])

        return str_ret[:-1]
