================
Virtualization
================

Virtualization uses software to create an abstraction layer over computer hardware that allows the hardware elements of a single computer—processors, memory, storage and more—to be divided into multiple virtual computers, commonly called virtual machines (VMs).

.. _xen_hypervisor:

XEN
===

By default, the GoldVIP deliverable includes XEN hypervisor. XEN is a type 1 hypervisor (bare metal) that makes possible running multiple instances of the same operating system seamlessly on the hardware. XEN allows creation of virtual machines from the command line or automatically at startup. XEN virtualizes CPUs, memory, interrupts and timers, providing virtual machines with virtualized resources.

Two types of virtual machines are defined by XEN:

    - Privileged (**Dom0** or **Domain-0**): The first machine that runs natively on the hardware and provides access to the hardware for unprivileged domains.

    - Unprivileged (**DomUs**): Virtual machines spawned by Dom0. These machines use the hardware resources allocated from the privileged domain (CPU, Memory, Disk, Network).

In the GoldVIP, two virtual machines are started by default, before the user logs in:

    - **Domain-0**, which has access to all the system resources and creates a network bridge for the unprivileged guest. This bridge, namely xenbr0 is the network interface that forwards packets to the DomU;
    - **v2xdomu**, unprivileged domain, which has access only to a limited number of resources.


Using the DomUs
---------------

XEN provides several commands via the xl tool stack which can be used to spawn/restart/shutdown unprivileged domains. Several commands can be used from the Domain-0 command line:

    ``- xl list``: lists all the active domains running in the system.

    ``- xl create <domain configuration file>``: spawns a DomU

    ``- xl console <domain name / domain ID>``: logs into the console of another unprivileged domain.

    ``- CTRL+]``: Resumes to Dom0 console (can be run only from a DomU)

    ``- xl shutdown``: Shuts down a DomU

Networking in DomUs
-------------------
In order to have network access in the DomUs, a bridge must be created from Domain-0. By default, in the provided example, a bridge (xenbr0) is created at boot time. After the DomU boots, a virtual interface will be created in Domain-0 and will forward packets to the DomU. After logging into the DomU console, the interface will be visible as eth0.

Another bridge can be created with the following commands, after choosing a physical interface to be shared::

    ifconfig <eth interface> down
    ip addr flush <eth interface>
    brctl addbr <bridge name>
    brcrl addif <bridge name> <eth interface>
    ip link set dev <bridge name> up
    ip link set dev <eth interface> up

You can then assign an IP to the newly created bridge and use it in Domain-0.

**Note**: Do not set an IP address for the physical interface.

Configuring the V2X domU
------------------------

The V2X domU configuration is stored in the */etc/xen/auto* directory and it is started before the user logs in. In order to prevent the machine from auto-starting at boot time, it is necessary to move the configuration file to a different directory (for example */etc/xen*). After reboot, only Domain-0 will be started.

Several configuration fields are present in the V2X domU configuration file:

    - **kernel**: The image that will be used in order to boot the DomU;
    - **memory**: Allocated memory for the domU, in MB;
    - **name**: DomU name. This name can be used to connect to the DomU using the xl console command;
    - **vcpus**: Number of virtual CPUs that are to be used for the VM;
    - **cpus**: Physical CPUs that are allocated to the VM;
    - **disk**: Physical storage device that stores the file system for the VM;
    - **extra**: Root device, console setting;
    - **vif**: Network bridge that forwards frames from the physical interface, created automatically at Domain-0 boot time.

For more detailed information please consult the XEN official documentation: https://xenproject.org/
