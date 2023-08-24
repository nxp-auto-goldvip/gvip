#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2020-2023 NXP
#
# This script is used to create a remote bridge on the target machine to tranfser the
# CPU load logs.

# shellcheck source=eth-gw/eth-common-target.sh
source "${BASH_SOURCE[0]%/*}/eth-common-target.sh"

set_trap
flush_ip
reset_pfe_setup
create_bridge
setup_bridge
exit
