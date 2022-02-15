===========
CAN Gateway
===========

The CAN gateway is based on EB tresos AutoCore Platform for S32G.
It is distributed in binary and source code format.
It is loaded from the QSPI Flash, then booted to Cortex-M7 core 0 of S32G platform, by the bootloader.

GoldVIP provides the canperf script to generate CAN traffic from Linux/A53 on FlexCAN
and measure CAN forwarding performance between two LLCE-CAN ports connected to
two FlexCAN ports.

The following architecture was employed:

.. image:: can-gw-architecture.png

The CAN gateway currently supports the following use cases:
 - CAN to CAN 1:1 frame routing on Cortex-M7 core (Slow route).
   The CAN packets are sent from Linux and received on the M7 through the LLCE filters, then passed
   through the PDU router instance running on the M7 core.
 - CAN to CAN 1:1 frame routing on LLCE (Fast Route)
   The CAN packets are sent from Linux and received on the LLCE. As opposed to the previous use case,
   the packets are routed directly by the LLCE, without any M7 core intervention.
 - CAN to ETH and CAN 1:1 frame routing on LLCE (CAN to Ethernet Route).
   The CAN packets are sent from Linux and received on the LLCE. The packet will then be routed by the LLCE
   firmware to the output LLCE CAN instance. The packet will then be formatted into AVTP format and sent to the PFE.
   The packets sent to the PFE firmware are then captured on the AUX0 interface as inbound traffic.
   When the canperf script detects that the injected packets will also be sent to the AUX0 interface, a network service
   listener, namely "avtp_listener", will start to capture AVTP packets and log them to a file. In this case, the canperf
   script will also report how much data was captured by the ethernet service listener.
 - CAN to ETH routing through M7 core.
   The CAN packets are sent from Linux and received on the M7 CAN driver from where they are passed to the AUTOSAR COM
   stack which forwards it to the PFE2. The format used for the ethernet packets is UDP.
 - IDPS filtering.
   CAN frames inspection by Argus CAN IDPS (Intrusion Detection and Prevention System). IDPS is provided by 
   Argus Cyber Security (https://argus-sec.com/) for demonstration purposes. Argus CAN IDPS looks for cyber attacks in 
   the CAN network by monitoring frames for deviations in expected behavior and characteristics. Analysis is performed by
   an advanced rule-based heuristic detection and prevention engine.

   The engine is based on a Ruleset specifically generated for each vehicle model (i.e., in consideration of its
   architecture, messaging database, communication traffic models and other elements unique to the vehicle line). 
   This Ruleset reflects the vehicle’s traffic in normal operating circumstances and based on this Ruleset, Argus CAN IDS
   determines when a frame is anomalous, valid or in need of further investigation.

   Every CAN frame is inspected by Argus CAN IDPS based on the configuration of the Ruleset. The Ruleset may include
   features such as ensuring that the DLC (Data Length Code) matches the OEM’s definitions, that all signals are in their
   allowed ranges, that frames’ timing is as expected and that diagnostic frames are meeting the requirements of the ISO
   standards (see further details below under `Available CAN IDPS features`_ chapter).
   
   Any frame meeting the rules in the Ruleset is considered “accepted” and is forwarded to be further handled by the
   gateway and routed to its destination.
   In the case a frame is detected to include an anomaly, it is considered “rejected”, dropped and an anomaly report
   shall be sent for further diagnostics and logging.

   There could be cases where an anomaly is identified, yet the specific anomalous frame cannot be pinpointed. In these
   cases, the frame by which the anomaly was detected shall also be considered “accepted”, but an anomaly report 
   shall be sent for further diagnostics and logging. 
   This can happen, for example, when a Fixed-Periodic frame is received twice in a very short time interval. 
   In this case, the legitimate frame cannot be distinguished from the injected frame, yet it is clearly an anomaly in
   the CAN traffic.
 

Available CAN IDPS features
---------------------------

The features detailed below are available in Argus CAN IDPS. Each of the available features are enabled via Ruleset
configuration.

*    **ID Enforcement**: Reports and drops a frame as anomalous when the CAN ID is not expected on the inspected bus.
*    **DLC Enforcement**: Reports and drops a frame as anomalous when its DLC (Data Length Code) does not match the value defined by the customer.
*    **Signal Range Enforcement**: Reports and drops a frame as anomalous when at least one signal value is out of its allowed range.
*    **Unallocated Bits**: Reports and drops a frame as anomalous when bits not allocated to any signal have an unexpected value.
*    **Various frame timing inspection features**: The IDPS has several features to check the timing of frames on the
     bus. When frames appear on the bus at an unexpected timing, the frame shall be reported either as “rejected” and
     shall be dropped, or as “accepted” but with an anomaly report. This depends on the measure of certainty that the 
     IDPS can determine the specific anomalous frame.
*    **Bus Load detection**: Reports when a bus or several buses are loaded beyond a predefined threshold that suggest
     that the bus might be flooded. This feature only detects the load.
*    **Diagnostic frames inspection features**: The IDPS offers several features for inspecting diagnostic frames of 
      the UDS protocol (Unified Diagnostics Services), including:

     *    Inspection of service identifiers (reports and drops “rejected” frames)
     *    Detection of Brute force usage of diagnostics
     *    Detection of diagnostic services scanning
     *    Detection and prevention (drops “rejected” frames) of diagnostic services forbidden during driving.


Prerequisites
-------------
- S32G Reference Design Board or GoldBox running GoldVIP images

Running the measurements
------------------------
1. About:

   These commands will measure throughput of CAN frames routing between the configured CAN ports (``-t can0 -r can1``).
   The used CAN frames are 8(``-s 64``) to 64-bytes in size. A configured ms gap(``-g 0``) is used between consecutive frames.

2. HW setup:

   Connect FlexCAN0 to LLCE-CAN0 and FlexCAN1 to LLCE-CAN1. To locate the CAN
   connector and pins check the figures from the appendix. The CAN wires should
   be directly connected High to High and Low to Low.

3. Run CAN perf script:

   a) Parameter description:

      - | ``-t`` CAN transmit interface -use the values as per CAN-GW configuration. For the default CAN-GW configuration provided in GoldVIP, use the values as indicated for each flow(e.g. slow path, fast path, ...) in below sub-chapters
      - | ``-r`` CAN receive interface -use the values as per CAN-GW configuration. For the default CAN-GW configuration provided in GoldVIP, use the values as indicated for each flow(e.g. slow path, fast path, ...) in below sub-chapters
      - | ``-i`` id of transmit CAN frame -use the values as per CAN-GW configuration. For the default CAN-GW configuration provided in GoldVIP, use the values as indicated for each flow(e.g. slow path, fast path, ...) in below sub-chapters
      - | ``-o`` id of receive CAN frame -use the values as per CAN-GW configuration. For the default CAN-GW configuration provided in GoldVIP, use the values as indicated for each flow(e.g. slow path, fast path, ...) in below sub-chapters
      - | ``-s`` CAN frame data size in bytes
      - | ``-g`` frame gap in milliseconds between two consecutive generated CAN frames, use any integer >= 0
      - | ``-l`` the length of the CAN frames generation session in seconds, use any integer > 1

   b) For slow route:

      - Use the following arguments combinations which match the GoldVIP default configuration for CAN-GW

       | -t can0 -r can1 -i 0 -o 4
       | -t can1 -r can0 -i 2 -o 3

       ex: ``./canperf.sh -t can0 -r can1 -i 0 -o 4 -s 64 -g 0 -l 10``

      - Optionally, one can use the default script provided in the can-gw directory: can-slow-path.sh

        ex: ``./can-slow-path.sh``

   c) For fast route:

      - Use the following arguments combinations which match the GoldVIP default configuration for CAN-GW

       | -t can0 -r can1 -i 245 -o 245
       | -t can1 -r can0 -i 246 -o 246

       ex: ``./canperf.sh -s 64 -g 0 -i 245 -o 245 -t can0 -r can1 -l 10``

      - Optionally, one can use the default script provided in the can-gw directory: can-fast-path.sh

        ex: ``./can-fast-path.sh``

   d) For can to ethernet route fast path:

      - Use the following arguments combinations which match the GoldVIP default configuration for CAN-GW

       | -t can0 -r can1 -i 228 -o 228
       | -t can1 -r can0 -i 229 -o 229

       ex: ``./canperf.sh -s 64 -g 0 -i 228 -o 228 -t can0 -r can1 -l 10``

      - Optionally, one can use the default script provided in the can-gw directory: can-to-eth.sh

        ex: ``./can-to-eth.sh``
		
   e) For IDPS:

      - CAN-GW IDPS library ruleset is configured to act on CAN IDs 257 and 258 on can0 bus. If all preconditions are met then the frame will be routed
        with CAN ID 256 on can1 bus otherwise the CAN frame is considered malicious and dropped.

      - The preconditions are as follows:

         1. Both frames must have a value between 0x00 and 0x20 in the first byte of the payload (e.g., ``-D 2000000000000000``).
         2. Both frames must have a DLC value of 8 (e.g., ``-s 8``).
         3. Both frames must have only zeros in the last 7 bytes of the payload (e.g., ``-D 2000000000000000``).
         4. CAN ID 257 shall have a cycle time of 1000 ms with a tolerance of 180 ms (e.g., ``-g 1000``).
         5. CAN ID 258 must not have a cycle time lower than 18 ms (e.g., ``-g 100``).

      - With all the preconditions from above the following arguments to canperf should give you the same count of Tx and Rx frames:

       | -t can0 -r can1 -i 257 -o 256 -s 8 -g 1000 -D 2000000000000000
       | -t can0 -r can1 -i 258 -o 256 -s 8 -g 1000 -D 1000000000000000

       ex: ``./canperf.sh -t can0 -r can1 -i 257 -o 256 -s 8 -g 1000 -D 2000000000000000 -l 10``
	
      - With all the preconditions from above the following arguments to canperf should result in the frames being rejected:

       | -t can0 -r can1 -i 257 -o 256 **-s 7** -g 1000 -D 2000000000000000
       | -t can0 -r can1 -i 257 -o 256 -s 8 -g 1000 **-D 4500000000000000**
       | -t can0 -r can1 -i 258 -o 256 -s 8 -g 1000 **-D 1000000000000001**
       | -t can0 -r can1 -i 257 -o 256 -s 8 **-g 100** -D 1000000000000000

       ex: ``./canperf.sh -t can0 -r can1 -i 257 -o 256 -s 7 -g 1000 -D 2000000000000000 -l 10``

      - Optionally, one can use the default script provided in the can-gw directory: can-aidps-slow-path.sh

       ex: ``./can-aidps-slow-path.sh``

   **Note**: Please run ``./canperf.sh -h`` to see all the available options.

4. Running CAN to ethernet slow path:

   a) Connect one host PC ETH port to the board's PFE-MAC2 ETH port.

   b) Start GoldVIP Docker container on PC (see :ref:`building_goldvip_docker_image` chapter)

   c) Run on host PC can-to-eth-slow-path-m7-host.sh script to measure performance for CAN to
      ethernet routing, with various payload sizes and time gaps between CAN frames e.g.::

        sudo ./eth-slow-path-host.sh -s 64 -g 10 <can> <eth>


      **Note**: run ``ip a`` command on your host PC to find out the exact name of the
      ethernet interface <eth> connected to the board.

      **Note**: The script is connecting to target console via */dev/ttyUSB0*. In case
      tty port is different on your PC, specify it explicitly with *-u* argument,
      e.g., *-u /dev/ttyUSB1*. Also, no other process should use the port during the test.




Building the M7 Application
---------------------------

The distributed CAN-GW binary is compiled from an EB tresos AutoCore Platform that requires some updates for the tresos plugins to get the same functionality as in the distributed binary image:

1. Download and install the Elektrobit tresos ACG version mentioned in :ref:`software_prerequisites`.

2. Download S32 Design Studio v3.4 from your nxp.com account and install it. The GCC compiler needed for the build process is included in S32 Design Studio.

3. Update NXP plugins:

   Replace the `McalExt_TS_T40D33M1I0R0` plugin found in the `<EB_tresos_install_path>/plugins/` directory with
   the contents of the `McalExt_TS_T40D33M1I0R0.zip` archive, which can be found in the `<GoldVIP_install_path>/configuration/can-gw/plugins` directory.

   **Note**: EB tresos needs to be restarted after performing this change, in order to load the newly installed plugins.

4. Update the build environment:

   Adapt `<GoldVIP_install_path>/configuration/can-gw/workspace/goldvip-gateway/util/launch_cfg.bat` to your particular system needs.
   In particular *TOOLPATH_COMPILER* needs to point to the compiler that you installed at step 2 and *TRESOS_BASE* needs to point to tresos install location from step 1.

5. Open tresos and import *goldvip-gateway* project located at `<GoldVIP_install_path>/configuration/can-gw/workspace/goldvip-gateway`.

6. If you have a valid system model (`SystemModel2.tdb` file) you can right click the project and hit the generate button. Otherwise, if the system model
   is not valid anymore or if you have done any changes to the configuration it is best to use *CodeGenerator* wizard. You can launch this wizard by going
   in `Project->Unattended Wizards` tresos menu and select *Execute multiple tasks(CodeGenerator)* entry.

7. You should be ready to build the project. Open a Command Prompt and run the following commands::

     cd <GoldVIP_install_path>/configuration/can-gw/workspace/goldvip-gateway/util
     launch.bat make -j

   To create a binary file from elf run the following command in the same Command Prompt::

     C:/NXP/S32DS.3.4/S32DS/build_tools/gcc_v9.2/gcc-9.2-arm32-eabi/arm-none-eabi/bin/objcopy.exe -S -O binary ../output/bin/CORTEXM_S32G27X_goldvip-gateway.elf ../output/bin/goldvip-gateway.bin