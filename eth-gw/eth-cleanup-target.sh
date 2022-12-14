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
ipsec stop 2> /dev/null || true
pkill -9 iperf3 || true
# Re-add the HSE module.
modprobe hse

# Stop any DHCP client that runs on pfe0 and pfe2 interfaces.
dhcpcd -x pfe2 || true
dhcpcd -x pfe0 || true

for netif in "pfe0" "pfe2"; do
    for iptables_chain in "INPUT" "FORWARD"; do
        iptables -D "${iptables_chain}" -i "${netif}" -j ACCEPT > /dev/null 2>&1 || true
    done
done

delete_log
exit
