#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2021 NXP

# This script runs the CAN perf script with default arguments to test CAN to ETH path.

"$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"/canperf.sh -g 0 -s 64 -i 228 -o 228 -t can0 -r can1 -l 10
