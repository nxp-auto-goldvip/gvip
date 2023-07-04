#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2023 NXP
"""

import struct
import time

def get_benchmark_score(timeout=25):
    """
    Prints the benchmark results from M7_1.

    Sends a message to M7 cores via the IPCF benchmark channel 
    which triggers the run of the benchmark on M7_1.
    Then it polls the IPCF channel for the results.
    Running the benchmark takes around 15 seconds, but if
    there are results from a previous run the function will return those
    and not wait for the current benchmark run.
    :param timeout: Time in seconds to wait for a benchmark result from ipcf.
    """
    print("Running benchmark on M7_1, "\
          "it might take up to 15 seconds to run the benchmark.")

    with open("/dev/ipcfshm/M7_0/benchmark", "rb") as file_r:
        raw_data = None

        while not raw_data and timeout > 0:
            raw_data = file_r.read()
            if len(raw_data) < 24:
                with open("/dev/ipcfshm/M7_0/benchmark", "wb") as file_w:
                    # By sending a message to the benchmark IPCF channel we trigger a benchmark run,
                    # and write the results from the previous run (if there was one) in the buffer.
                    # The text sent is irrelevant.
                    file_w.write(b"Get benchmark result.")

                timeout -= 1
                raw_data = None
                time.sleep(1)

        if not raw_data:
            print("Timeout. Could not retrieve benchmark score from M7_1.")

        # If there are multiple results written to the buffer, take only one of them.
        # 24 bytes is the length of the results struct, which contains two doubles and two ints.
        values = struct.unpack("<ddII", raw_data[0:24])
        results = dict(zip([
            "benchmark_score",
            "time_in_seconds",
            "time_in_ticks",
            "iterations"], values))

        for key, value in results.items():
            print(f"{key}: {value}")

if __name__ == "__main__":
    get_benchmark_score()
