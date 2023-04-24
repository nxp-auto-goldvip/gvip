#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2023 NXP

# Performance run using seeds 0,0,0x66 and a buffer size of 2000 bytes.
/home/root/benchmark/coremark.exe  0x0 0x0 0x66 0 7 1 2000 > ./run1.log
cat run1.log
# Validation run using seeds 0x3415,0x3415,0x66 and a buffer size of 2000 bytes.
/home/root/benchmark/coremark.exe  0x3415 0x3415 0x66 0 7 1 2000  > ./run2.log
cat run2.log
