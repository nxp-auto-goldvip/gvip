===================
GoldVIP Quick Start
===================

This guide contains the steps to quickly deploy GoldVIP images, setup the board
connectivity and try out some vehicle gateway use-cases.

Setup cable connections
=======================

To locate the connectors and ports from the board check the figures from the
appendix or check S32G-VNP-RDB2 Quick Start Guide from the board's box.

1. Connect the power cable

2. Connect the board's UART0 serial port to PC using the USB cable from the box.

Deploy GoldVIP images
=====================

Download GoldVIP binary images from `here <https://are.nxp.com/FlexNetCatalog.aspx>`_.

Deploy GoldVIP SD-card image
----------------------------

1. Check the device name under which your SD-card is installed on PC so that you
   won't overwrite another disk. Use `cat /proc/partitions` command before and 
   after inserting SD-card, see which new sd* disk appears (e.g., /dev/sdb) and
   use it's name in the next step command.

2. Write fsl-image-goldvip on SD-card plugged into the Linux host PC, e.g.::

    sudo dd if=fsl-image-goldvip-s32g274ardb2.sdcard of=/dev/sdb bs=1M status=progress && sync

At this point you can plug in the SD-card power on the board and it will boot
u-boot + Linux from SD-card. For trying out Ethernet and cloud telemetry
use-cases you can skip the boot-loader deployment from next section. However,
for CAN use-cases you need to follow the steps from next section too.

Deploy real-time boot-loader
----------------------------

The real-time boot-loader runs on Cortex-M7-0 and is loaded from QSPI NOR flash.
It's main function is to load u-boot on Cortex-A53 cores and the real-time
applications on Cortex-M7 cores.

To write boot-loader in NOR flash, first boot from SD-card using the above
SD-card image, stop in u-boot console when prompted, and run the following commands:

Reset the environment to default::

    env default -a
    setenv bootargs_setup setenv bootargs dom0_mem=${dom0_mem} bootscrub=0
    saveenv

Load QSPI driver::

    sf probe 6:0

Update boot-loader image::

    setenv image boot-loader
    run loadimage
    sf erase 0x0 +${filesize}
    sf write ${loadaddr} 0x0 ${filesize}

Update U-Boot image::

    setenv image u-boot.bin
    run loadimage
    sf erase 0x00100000 +${filesize}
    sf write ${loadaddr} 0x00100000 ${filesize}

Update CAN-GW binary::

    setenv image can-gw.bin
    run loadimage
    sf erase 0x00200000 +${filesize}
    sf write ${loadaddr} 0x00200000 ${filesize}

After all the binaries are written, power off the board, configure the DIP switches
for NOR Flash Boot mode (set SW4.7 to OFF) and then power on the board.
