#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2021-2024 NXP
"""
import sensors

# pylint: disable=too-few-public-methods
class TemperatureStats:
    """
    Reads and processes temperature stats from lm-sensors*
    """
    # Tags which denote the placement of each temperature sensor.
    TAGS = {
        "ddr_sram-virtual-0"      : "ddr_sram_temperature",
        "a53_cores-virtual-0"     : "a53_cluster_temperature",
        "llce-virtual-0"          : "hse_llce_temperature",
        "ddr_sram_avg-virtual-0"  : "ddr_sram_average_temperature",
        "a53_cores_avg-virtual-0" : "a53_cluster_average_temperature",
        "llce_avg-virtual-0"      : "hse_llce_average_temperature"
    }

    def __init__(self):
        sensors.init()

    @staticmethod
    def get_temperature():
        """
        Reads and parses measured temperature data to a dictionary
        :returns: a dictionary of stats.
        :rtype: dict
        """
        temperature_data = {}

        for chip in sensors.iter_detected_chips():
            try:
                feature = list(iter(chip))
                temperature_data[TemperatureStats.TAGS[str(chip)]] = feature[0].get_value()
            except KeyError:
                pass
        return temperature_data
