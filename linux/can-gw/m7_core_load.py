#!/usr/bin/env python3.8
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2021 NXP
"""

import argparse
import time

# pylint: disable=import-error
from m7_stats import M7CoreMovingAverage, M7_0

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
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--file', dest='file', type=str,
                        help='The name of the file where the core load will be stored.')
    parser.add_argument('--time', dest='time', type=int,
                        help='Measurement time in seconds.')
    args = parser.parse_args()

    # Initialize class with a window size coresponding
    # with (args.time - LOAD_UPDATE_TIME) seconds
    m7_stats = M7CoreMovingAverage(
        max_window_size=LOAD_UPDATE_TIME / QUERY_TIME_INTERVAL,
        m7_status_query_time_interval=QUERY_TIME_INTERVAL)

    m7_stats.start()

    end_time = time.time() + args.time

    while time.time() < end_time:
        time.sleep(LOAD_UPDATE_TIME)

        loads = M7CoreMovingAverage.get_load()
        load = -1

        if M7_0 in loads:
            load = loads.get(M7_0)

        with open(args.file, 'a') as file:
            file.write('{}\n'.format(load))

    # Stop thread.
    M7CoreMovingAverage.terminate_thread()
    m7_stats.join()


if __name__ == '__main__':
    main()
