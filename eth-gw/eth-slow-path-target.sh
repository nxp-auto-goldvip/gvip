#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2020-2021,2023 NXP
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

_create_vlan_interfaces() {
    ip link add link "${PFE0_NETIF}" name "${PFE0_NETIF}.${vlan_id_pfe0}" type vlan id "${vlan_id_pfe0}"
    ip link add link "${PFE2_NETIF}" name "${PFE2_NETIF}.${vlan_id_pfe2}" type vlan id "${vlan_id_pfe2}"
    ip link set dev "${PFE0_NETIF}.${vlan_id_pfe0}" up
    ip link set dev "${PFE2_NETIF}.${vlan_id_pfe2}" up
}

_setup_l2_switch() {
    USE_VLANS=true

    # Clear previous configuration.
    libfci_cli route-and-cntk-reset --all

    # Add vlans to the pfe interfaces
    for vlan_id in "${vlan_id_pfe0}" "${vlan_id_pfe2}"; do
        libfci_cli bd-print | grep "domain ${vlan_id}" || libfci_cli bd-add --vlan="${vlan_id}"
        libfci_cli bd-update --vlan "${vlan_id}" --ucast-hit FORWARD --ucast-miss FLOOD --mcast-hit FORWARD --mcast-miss FLOOD

        for if in "${PFE_VLAN_IFS[@]}"; do
            libfci_cli bd-insif --vlan "${vlan_id}" --interface "${if}" --tag ON
        done
    done
    for if in "${PFE_VLAN_IFS[@]}"; do
        libfci_cli phyif-update  --interface "${if}" --enable  --promisc ON  --mode VLAN_BRIDGE  --block-state NORMAL
    done

    flush_ip
    _create_vlan_interfaces
    create_bridge
    setup_bridge
}

# Enable routing between the two local PFE interfaces.
_setup_l3_router() {
    delete_bridge

    _bring_up_interface

    # Set ip for each interface
    _set_ip "${PFE0_NETIF}" "10.0.1.2"
    _set_ip "${PFE2_NETIF}" "192.168.100.2"

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
