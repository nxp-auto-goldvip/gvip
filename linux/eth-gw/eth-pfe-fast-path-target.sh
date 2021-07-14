#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Copyright 2021 NXP
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

# shellcheck source=linux/eth-gw/eth-common-target.sh
source "${BASH_SOURCE[0]%/*}/eth-common-target.sh"

# Set layer two switch between the local interfaces.
_setup_l2_switch() {
    # Clear previous configuration.
    libfci_cli --reset
    libfci_cli --reset6

    # Configure HW bridge>
    libfci_cli --bd_add_if --vlan "${vlan_id}" --i emac0 --tag 0
    libfci_cli --bd_add_if --vlan "${vlan_id}" --i emac2 --tag 0
    libfci_cli --bd_set_act --vlan "${vlan_id}" --ucast_hit 0 --ucast_miss 1 --mcast_hit 0 --mcast_miss 1
    
    # Update PHY configuration for EMAC0 and EMAC2.
    libfci_cli --phyif_update --i emac0 --mode BRIDGE --enable on --promisc on
    libfci_cli --phyif_update --i emac2 --mode BRIDGE --enable on --promisc on
}

# Set layer three routing for the two local PFE interfaces.
_setup_l3_router() {
    delete_bridge
    _bring_up_interface

    # Set ip for each interface.
    _set_ip "pfe0" "10.0.1.2"
    _set_ip "pfe2" "192.168.100.2"
    
    # Clear previous config.
    libfci_cli --reset
    libfci_cli --reset6
    
    # Configure route rules via libfci.
    libfci_cli --add_route --mac "${host_mac_pfe0}" --dstip "10.0.1.1" --i emac0 --routeid 1
    libfci_cli --phyif_update --i emac0 --mode ROUTER --enable on --promisc off
    libfci_cli --add_route --mac "${host_mac_pfe2}" --dstip "192.168.100.1" --i emac2 --routeid 0
    libfci_cli --phyif_update --i emac2 --mode ROUTER --enable on --promisc off
    # UDP rules
    # Add routing table entry (conntrack) this will be fast forwarded.
    libfci_cli --add_conntrack --sip "10.0.1.1" --dip "192.168.100.1" --proto 17 --sport 5001 --dport 5678 --routeid 0
    # Add routing table entry (conntrack) this will be fast forwarded.
    libfci_cli --add_conntrack --sip "192.168.100.1" --dip "10.0.1.1" --proto 17 --sport 5001 --dport 5678 --routeid 1
    # TCP rules
    # Add routing table entry (conntrack) this will be fast forwarded.
    libfci_cli --add_conntrack --sip "10.0.1.1" --dip "192.168.100.1" --proto 6 --sport 5001 --dport 5678 --routeid 0
    # Add routing table entry (conntrack) this will be fast forwarded.
    libfci_cli --add_conntrack --sip "192.168.100.1" --dip "10.0.1.1" --proto 6 --sport 5001 --dport 5678 --routeid 1

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
        -m0	<host_mac_0>		Host MAC adress connected to pfe0
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
_setup_network
