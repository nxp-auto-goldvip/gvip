#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2020-2021 NXP
#
# This script is used to clean up the target remotely when
# the host cleans up as well.

# shellcheck source=linux/eth-gw/eth-common-target.sh
source "${BASH_SOURCE[0]%/*}/eth-common-target.sh"

set_trap
flush_ip
delete_bridge
delete_pfe_fast_path
delete_log
exit
