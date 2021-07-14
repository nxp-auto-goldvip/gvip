#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Script used to test the Telemetry extraction code on local machine.

Copyright 2020-2021 NXP
"""
from time import sleep
import json

from stats import stats_to_json

# Time interval in seconds between telemetry data points.
TELEMETRY_INTERVAL = 1


if __name__ == "__main__":
    # An infinite loop that gets datapoints every <telemetry_interval> seconds.
    try:
        while True:
            print(json.dumps(json.loads(stats_to_json()), indent=2))
            sleep(TELEMETRY_INTERVAL)
    except KeyboardInterrupt as _:
        print("\nStopped")
