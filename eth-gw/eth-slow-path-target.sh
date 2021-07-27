#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2020-2021 NXP
#
# This script implements the target machine logic for the L2/L3 forwarding slow path scenario.
#
# The slow path scenario demonstrates that the traffic can flow between the two configured
# host interfaces using the Linux network stack running on the remote A53 core. 
#
# The target script takes care of setting up the L2 or L3 functionality via standard Linux commands.
# In case L3 forwarding is used, the PFE interfaces are configured to match the host network.

# shellcheck source=eth-gw/eth-common-target.sh
source "${BASH_SOURCE[0]%/*}/eth-common-target.sh"

_setup_l2_switch() {
    flush_ip
    create_bridge
    setup_bridge
}

# Enable routing between the two local PFE interfaces.
_setup_l3_router() {
    delete_bridge

    _bring_up_interface

    # Set ip for each interface
    _set_ip "pfe0" "10.0.1.2"
    _set_ip "pfe2" "192.168.100.2"

    #Enable forwarding
    echo 1 > /proc/sys/net/ipv4/ip_forward
}

usage() {
    echo -e "Usage: ./$(basename "$0") [option]
Set up L2-Switch or L3-Router forwarding between pfe0 and pfe2 interfaces.\n
OPTIONS:
        -L <layer_number>       specify network layer to set up
                                layer_number=2 for L2-Switch
                                             3 for L3-Router (default)
        -h                      help"
}

_setup_network() {
    # Enable forward policy from netfilter table
    iptables --policy FORWARD ACCEPT

    if [ "${layer_number}" -eq 2 ]; then
        _setup_l2_switch
    else
        _setup_l3_router
    fi
}

set_trap
check_input "$@"
_setup_network
