#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2021-2023 NXP
"""

import argparse
import time

from telemetry import M7CoreMovingAverage

# Time interval between core load value updates in seconds.
LOAD_UPDATE_TIME = 0.5

# Time interval between M7 core status queries in seconds.
QUERY_TIME_INTERVAL = 0.001


def main():
    """
    Start a M7CoreMovingAverage thread to measure core load for M7 0.
    Computes the average over <time> seconds.
    Updates the average every <LOAD_UPDATE_TIME> seconds and saves it in
    the file given as a parameter.
    """
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--outfile",
        dest="output_file",
        type=str,
        help="The name of the file where the M7 cores load data will be stored.",
        required=True,
    )

    parser.add_argument(
        "--monitored-cores",
        choices=['all', 'M7_0', 'M7_1', 'M7_2', 'M7_3'],
        nargs="+",
        dest="chosen_cores",
        type=str,
        help="M7 cores to monitor.",
        default='M7_0',
    )
    parser.add_argument(
        "--time",
        dest="time",
        type=int,
        help="Measurement time in seconds.",
        required=True,
    )
    args = parser.parse_args()

    # Initialize class with a window size coresponding
    # with (args.time - LOAD_UPDATE_TIME) seconds
    m7_stats = M7CoreMovingAverage(
        max_window_size=LOAD_UPDATE_TIME / QUERY_TIME_INTERVAL,
        m7_status_query_time_interval=QUERY_TIME_INTERVAL,
    )

    m7_stats.start()

    end_time = time.time() + args.time

    while time.time() < end_time:
        time.sleep(LOAD_UPDATE_TIME)

        loads = M7CoreMovingAverage.get_load()

        with open(args.output_file, "a", encoding="UTF-8") as output_file:
            for core in M7CoreMovingAverage.M7_CORES:
                if (core.upper() in args.chosen_cores ) or ("all" in args.chosen_cores):
                    output_file.write(f"{core.upper()}: {loads.get(core, -1)}\n")

    # Stop thread.
    M7CoreMovingAverage.terminate_thread()
    m7_stats.join()


if __name__ == "__main__":
    main()
