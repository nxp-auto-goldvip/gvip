#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate the GoldVIP telemetry pacakges

Copyright 2022-2023 NXP
"""
import os
from setuptools import setup, find_packages

# Allow script to be able to run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='goldvip-telemetry',
    version='0.0.1',
    description="Goldvip telemetry fetcher scripts",
    install_requires=["build"],
    include_package_data=True,
    zip_safe=False,
    packages=find_packages(),
)
