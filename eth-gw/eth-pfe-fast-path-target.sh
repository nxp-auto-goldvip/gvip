#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2021-2023 NXP
#
# This script implements the target machine logic for the L2/L3 forwarding
# fast path scenario using the PFE interfaces of the board.
#
# The fast path scenario demonstrates that the traffic can flow solely through
# the PFE peripheral, without any Linux netstack interaction. 
#
# This scenario presumes having traffic flow between PFE0 and PFE2 interfaces,
# which belong to a separate network namespace.
#
# The target script takes care of setting up the L2 or L3 functionality for the PFE peripheral via	
# the "libfci" utility.

# shellcheck source=eth-gw/eth-common-target.sh
source "${BASH_SOURCE[0]%/*}/eth-common-target.sh"

# Set layer two switch between the local interfaces.
_setup_l2_switch() {
    # Clear previous configuration.
    libfci_cli route-and-cntk-reset --all

    # Configure HW bridge>
    libfci_cli bd-insif --vlan "${vlan_id}" --i emac0 --tag OFF
    libfci_cli bd-insif --vlan "${vlan_id}" --i emac2 --tag OFF
    libfci_cli bd-update --vlan "${vlan_id}" --ucast-hit 0 --ucast-miss 1 --mcast-hit 0 --mcast-miss 1

    # Update PHY configuration for EMAC0 and EMAC2.
    libfci_cli phyif-update --i emac0 --mode VLAN_BRIDGE --enable --promisc ON
    libfci_cli phyif-update --i emac2 --mode VLAN_BRIDGE --enable --promisc ON
}

# Set layer three routing for the two local PFE interfaces.
_setup_l3_router() {
    # Set ip for each interface.
    _set_ip "${PFE0_NETIF}" "10.0.1.2"
    _set_ip "${PFE2_NETIF}" "192.168.100.2"

    # kube-proxy is inserting a rule that drop packets in "INVALID" state, affecting the L3
    # router in TCP mode. Prepend rules to accept all the traffic that reside on
    # pfe interfaces to avoid the iptables rules inserted by Kubernetes components.
    for netif in "${PFE0_NETIF}" "${PFE2_NETIF}"; do
        for iptables_chain in "INPUT" "FORWARD"; do
            iptables -I "${iptables_chain}" 1 -i "${netif}" -j ACCEPT
        done
    done

    # Clear previous config.
    libfci_cli route-and-cntk-reset --all

    # Configure route rules via libfci.
    libfci_cli route-add --dst-mac "${host_mac_pfe0}"  --i emac0 --route 1 --ip4
    libfci_cli phyif-update --i emac0 --mode ROUTER --enable --promisc OFF
    libfci_cli route-add --dst-mac "${host_mac_pfe2}" --i emac2 --route 0 --ip4
    libfci_cli phyif-update --i emac2 --mode ROUTER --enable --promisc OFF

    # UDP rules
    # Add routing table entry (conntrack) this will be fast forwarded.
    libfci_cli cntk-add --sip "10.0.1.1" --dip "192.168.100.1" --proto 17 --sport 5001 --dport 5678 --route 0 --no-reply
    # Add routing table entry (conntrack) this will be fast forwarded.
    libfci_cli cntk-add --sip "192.168.100.1" --dip "10.0.1.1" --proto 17 --sport 5001 --dport 5678 --route 1 --no-reply
    # TCP rules
    # Add routing table entry (conntrack) this will be fast forwarded.
    libfci_cli cntk-add --sip "10.0.1.1" --dip "192.168.100.1" --proto 6 --sport 5001 --dport 5678 --route 0 --no-reply
    # Add routing table entry (conntrack) this will be fast forwarded.
    libfci_cli cntk-add --sip "192.168.100.1" --dip "10.0.1.1" --proto 6 --sport 5001 --dport 5678 --route 1 --no-reply

    # Enable forwarding (used for management data).
    echo 1 > /proc/sys/net/ipv4/ip_forward
}

usage() {
    echo -e "Usage: ./$(basename "$0") [option]
Set up L2-Switch or L3-Router forwarding between pfe0 and pfe2 interfaces.\n
OPTIONS:
        -L <layer_number>       specify network layer to set up
                                layer_number=2 for L2-Switch
                                             3 for L3-Router (default)
        -m0 <host_mac_0>		Host MAC adress connected to pfe0
        -m1 <host_mac_1>		Host MAC adress connected to pfe2
        -V <VLAN ID>			VLAN ID for L2 bridge
        -h                      help"
}

# Set up network depending on the configured layer.
_setup_network() {
    # Enable forward policy from netfilter table.
    iptables --policy FORWARD ACCEPT

    if [ "${layer_number}" -eq 2 ]; then
        _setup_l2_switch
    else
        _setup_l3_router
    fi
}

set_trap
check_input "$@"
delete_bridge
_bring_up_interface
_setup_network
