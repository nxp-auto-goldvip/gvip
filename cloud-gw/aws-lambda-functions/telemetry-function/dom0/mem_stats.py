#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2020-2021, 2023 NXP
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

        with open(MEM_INFO, "r", encoding="utf-8") as file:
            for _ in range(MEM_NUMBER_ITEMS):
                line = file.readline()
                stat, _, line = line.partition(":")

                if stat.startswith("Mem"):
                    stat = stat[3:]

                stat = "mem_" + stat.lower()

                if verbose:
                    val = line.strip()
                    mem_dict[stat] = val
                else:
                    val, _, _ = line.strip().partition(" ")
                    mem_dict[stat] = int(val)

            if "mem_available" in mem_dict:
                mem_dict["mem_load"] = mem_dict["mem_total"] - mem_dict["mem_available"]
            elif "mem_free" in mem_dict:
                mem_dict["mem_load"] = mem_dict["mem_total"] - mem_dict["mem_free"]

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
        mem_total = mem_dict["mem_total"]

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

        for item, value in mem_dict.items():
            str_ret += f"{item} {value}\n"

        return str_ret[:-1]
