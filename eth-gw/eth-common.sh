#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2020-2021,2023 NXP
#
# This script collects base functions and variables for all host/target scripts.

# Enable bash strict mode (i.e. fail on any non-zero exit code,
# undefined variable reference and prevent masked pipeline errors).
set -euo pipefail
# Fail on unset variables usage.
set -o nounset
# Inherit the ERR trap.
set -E

# Custom non-standard exit codes
readonly GENERAL_ERR=1
readonly PRIVILEGE_ERR=3
readonly INVALID_USER_ARGUMENT_ERR=4
readonly INVALID_CONFIG_ERR=5
readonly NET_ERR=6

# Global constants
readonly integer_regex="^[0-9]+$"
readonly payload_size_regex="^[0-9]+[K|k|M|m]?$"

# Name of the pfe0/pfe2 network interfaces
readonly PFE0_NETIF="pfe0sl"
readonly PFE2_NETIF="pfe2sl"

# Default modes for emac0/emac2 physical interfaces
readonly EMAC0_DEFAULT_MODE="FLEXIBLE_ROUTER"
readonly EMAC2_DEFAULT_MODE="FLEXIBLE_ROUTER"

