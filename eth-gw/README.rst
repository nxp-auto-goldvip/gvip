================
Ethernet Gateway
================

The Ethernet gateway currently supports the following use cases:

 - Layer 2 (bridge/switch) ETH forwarding
 - Layer 3 (router) IP forwarding

Both use cases can be run either in slow-path mode with Cortex-A53 cores
handling the forwarding or in fast path mode on SJA1110A switch without any
load on A53 cores.
For the case of Cortex-M7 forwarding only the L3 option is available since
the routing can be done only on IP level in the AUTOSAR COM stack.

GoldVIP provides scripts that can be used to measure performance in slow-path and
fast-path mode for both UDP and TCP traffic generated with iperf3(python for Cortex-M7
use case) from host PC.
Slow-path means the traffic is routed by Linux running on A53 cores or AUTOSAR COM
stack running on Cortex-M7 cores.
Fast-path means the data-path traffic is routed by PFE (Packet Forwarding Engine) or
SJA1110 companion switch from the board.

Prerequisites
-------------

 - S32G Reference Design Board or GoldBox running GoldVIP images.
 - PC with 2 Ethernet ports, running Ubuntu 18.04 (with iperf3, minicom, iproute2,
   python3, strongSwan) or a built GoldVIP Docker image that already contains all the necessary
   tools.

.. _running_A53_slow_path:

Running the A53 slow-path use cases
-----------------------------------

1. Connect one host PC ETH port to the board's SJA1110A switch Port 2.

2. Connect another PC ETH port to the board's PFE-MAC2 ETH port.
   An USB-to-ETH adaptor can be used as the second PC ETH card but make sure it
   supports Gigabit ETH and is plugged into an USB3.0 port.

3. Start GoldVIP Docker container on PC (see :ref:`building_goldvip_docker_image` chapter)

4. Run on host PC ``eth-slow-path-host.sh`` script to measure performance for L2/L3
   forwarding between pfe0 and pfe2, with UDP or TCP traffic, with various
   payload sizes, e.g.::

    sudo ./eth-slow-path-host.sh -L 3 -d full -t UDP <eth0> <eth1>

   The above command is measuring throughput between PC eth0 and eth1 that are
   connected to the board pfe0 and pfe2, in full duplex mode (*-d full*), with UDP
   traffic (*-t UDP*) with default packet size (ETH MTU). Use *-h* option to
   list all available options.

   **Note**: run ``ip a`` command on your host PC to find out the exact names of the
   interfaces <eth0> and <eth1> connected to the board.

   **Note**: The script is connecting to target console via */dev/ttyUSB0*. In case
   tty port is different on your PC, specify it explicitly with *-u* argument,
   e.g., ``-u /dev/ttyUSB1``
   
Running the Cortex-M7 slow-path use cases
-----------------------------------------

1. Follow steps 1-3 from :ref:`running_A53_slow_path`. 

2. Run on host PC ``eth-slow-path-m7-host.sh`` script to measure the performance of
   Ethernet packet forwarding between pfe0 and pfe2 but through the AUTOSAR COM stack
   running on Cortex-M7 core::

    sudo ./eth-slow-path-m7-host.sh -l 10 -d full -t UDP <eth0> <eth1>

   The above command is measuring throughput between PC eth0 and eth1 that are
   connected to the board pfe0 and pfe2 for a test length of 10 seconds(*-l 10*)
   in full duplex mode (*-d full*), with UDP traffic (*-t UDP*) with default packet 
   size (ETH MTU). Use *-h* option to list all available options.

   **Note**: run ``ip a`` command on your host PC to find out the exact names of the
   interfaces <eth0> and <eth1> connected to the board.
   
Running the PFE fast-path use cases
-----------------------------------

1. Follow steps 1-3 from :ref:`running_A53_slow_path`.

2. Run on host PC ``eth-pfe-fast-path-host.sh`` script to measure the same performance
   scenarios as above but this time offloaded in PFE without involving A53 core::

    sudo ./eth-pfe-fast-path-host.sh -L 3 -d full -t UDP <eth0> <eth1>

   Same notes apply as in previous section.

Running the SJA1110A fast-path use cases
----------------------------------------

1. Connect both host PC ETH ports to the board's SJA1110A Port 2 and Port 3.

2. Run on host PC ``eth-sja-fast-path-host.sh`` script to measure the same performance
   scenarios but this time going through SJA1110A switch Port 2 and Port 3::

    sudo ./eth-sja-fast-path-host.sh -L 3 -d full -t UDP <eth0> <eth1>

   Same notes apply as in previous sections.

Running the IPsec A53 slow-path use cases
-----------------------------------------

This use case establishes a secured connection through IPsec between the host and the target. IPSec
provides security at the level of the IP layer. The payload of IP datagrams is securely encapsulated
using Encapsulating Security Payload (ESP), providing integrity, authentication, and encryption of
the IP datagrams. strongSwan is used as a keying daemon on both the host and the target to establish
security associations (SA) between the two peers. The connection can be established either in
transport or tunnel mode, with X.509 authentication.

1. Connect one host PC ETH port to the board's PFE-MAC2.

2. Run on host PC ``eth-ipsec-slow-path-host.sh`` script to measure the performance for the
   IPsec-established connection between the host and the board's PFE-MAC2 interface::

    sudo ./eth-ipsec-slow-path-host.sh -l 10 -m transport -d full -t UDP <eth0>

   The above command is establishing an IPsec connection between PC eth0 and board pfe2 in transport
   mode (*-m transport*), then it measures the throughput for a test length of 10 seconds (*-l 10*)
   in full-duplex mode (*-d full*), with UDP traffic (*-t UDP*) with default packet size (ETH MTU).
   Use *-h* option to list all available options.

   Same notes apply as in previous section.

Running the IDPS slow-path use cases
------------------------------------

This use case demonstrates the Ethernet IDPS (Intrusion Detection and Prevention System) provided 
by Argus Cyber Security (https://argus-sec.com/).
Argus Ethernet IDPS is a security mechanism designed to provide complementary protection 
for automotive Ethernet networks, on top of the existing commodity security controls available 
for Ethernet components.

Argus’s IDPS includes Access control capabilities from the Data link layer to the Application layer and supports 
most of the protocols in those layers (both whitelist and blacklist are supported). In addition, more advanced 
inspection features are available (stateful inspection, DPI). For information on the full IDPS feature set, please contact Argus. 

In this use case, the access control capabilities of the IDPS are demonstrated. The inspection is done on the whole 
network stack (Ethernet, IP, UDP, SOME/IP) on prerecorded network traffic that contains both valid and invalid SOME/IP packets.
Only intrusion detection capability is demonstrated in this use case (no prevention or packet dropping).
The prerecorded traffic is injected from PC and sent to the target that runs the Ethernet IDPS.

Please follow these steps in order to run this use case:

1. Connect one host PC ETH port to the board's PFE-MAC2.

2. Run on host PC ``eth-idps-slow-path-host.sh`` script to send packets from PC ETH port
   to the board's PFE-MAC2. The IDPS will detect invalid messages and send the log back
   to the PC.
   On the host PC, run the following command::

     sudo ./eth-idps-slow-path-host.sh <eth-interface>

   **Note**: Use *-h* option to see all available arguments.

The output of this use case has two parts:

*  **IDPS host log:** Contains information about the number of packets transmitted from the host.
*  **IDPS target log:** Contains the output of the IDPS executable:

   *  **Valid packets:** The number of packets that matched a whitelist rule of the IDPS and are considered valid.
   *  **Invalid packets:** The number of packets that did not match any whitelist rule of the IDPS and are considered invalid. 
   *  **Relevant packets:** The number of packets that are relevant to this use case (SOME/IP packets), this value 
      should contain the sum of the valid and invalid packets and shall be equal to the number of packets that were transmitted by the host.   
   *  **Irrelevant packets:** - Packets that are not part of the use case (ARP, general network packets), and not SOME/IP packets. 
      This number varies between different runs of this use case.


Connecting to a Wi-Fi network
-----------------------------

1. Insert the Wireless Adapter into the board's USB port.

2. Modify configuration file at ``/etc/wifi_nxp.conf`` to choose the Wi-Fi interface to run on

3. Add ssid and passphrase to ``/etc/wpa_supplicant.conf``:

   - If your Wi-Fi network uses a password::

      wpa_passphrase SSID PASSPHRASE >> /etc/wpa_supplicant.conf

   - If you are using a public network::

      echo -e "network={\n\tssid="SSID"\n\tkey_mgmt=NONE\n}" >> /etc/wpa_supplicant.conf

4. Restart Wi-Fi service::

      /etc/init.d/wifi_setup restart
