#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2020-2022 NXP
#
# This script is used to clean up the target remotely when
# the host cleans up as well.

# shellcheck source=eth-gw/eth-common-target.sh
source "${BASH_SOURCE[0]%/*}/eth-common-target.sh"

set_trap
flush_ip
delete_bridge
delete_pfe_fast_path

# Stop the strongSwan IPsec process.
ipsec stop
pkill -9 iperf3 || true

# Stop any DHCP client that runs on pfe0 and pfe2 interfaces.
dhcpcd -x pfe2 || true
dhcpcd -x pfe0 || true

delete_log
exit
