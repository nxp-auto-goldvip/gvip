#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# -*- coding: utf-8 -*-

"""
Copyright 2020-2023 NXP
"""

import logging
import os
import sys
import mmap

from configuration import config

# Address of device id register
DEVICE_ID_REG_ADDR = int(config["DEVICE_ID_REG"], 16)

# Read UID_SIZE byte from DEVICE_ID_REG_ADDR address
UID_SIZE = 8

# Bit-Masking
MAP_MASK = mmap.PAGESIZE - 1

UUID = {
    "high" : None,
    "low" : None,
}

# Setup logging to stdout.
LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format="%(asctime)s|%(levelname)s| %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")

def get_uid():
    """
    This function reads the Device UID from OCOTP shadow registers.
    This uid is used as the board's unique identifier for the sitewise dashboard.

    :return: The uid in two parts
    :rtype: str, str
    """

    if UUID['high'] is not None:
        return UUID['high'], UUID['low']

    try:
        file = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)

        mfile = mmap.mmap(
            file,
            mmap.PAGESIZE,
            mmap.MAP_SHARED,
            mmap.PROT_READ,
            offset=DEVICE_ID_REG_ADDR & ~MAP_MASK)

        mfile.seek(DEVICE_ID_REG_ADDR & MAP_MASK)

        uid = 0
        power = 0

        for _ in range(UID_SIZE):
            c_byte = mfile.read_byte()
            uid += c_byte << power
            power += 8

        os.close(file)

        uid_split = int(len(str(uid)) / 2)

        UUID['high'] = str(uid)[:uid_split]
        UUID['low'] = str(uid)[uid_split:]

        return UUID['high'], UUID['low']

    except (OSError, TypeError) as exception:
        LOGGER.error("Failed to read uuid: %s", repr(exception))
        return None, None
