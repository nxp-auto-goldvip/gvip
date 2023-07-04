#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON Configuration parser.

Copyright 2022-2023 NXP
"""
import os
import json

# Label to common configuration of all platforms
COMMON_CONFIG_LABEL = "common"

device_name = os.uname().nodename
device_type = device_name[0:5]

# Global configurator is accessible from anywhere
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
with open(config_path, 'r', encoding='utf-8') as config_file:
    configs = json.load(config_file)

# Merge common configuration and specific device configuration
config = configs[COMMON_CONFIG_LABEL]
config.update(configs[device_type])
config["device"] = device_type
