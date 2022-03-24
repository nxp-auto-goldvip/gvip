#
# Copyright 2022 NXP Semiconductors
# Makefile for the ipc character device driver 

MODULE_NAME := ipc-chdev

ARCH ?= arm64

# additional module symbols dependency
EXTRA_SYMBOLS ?= ${IPC_SHM_DEV_PATH}/Module.symvers 

ifneq ($(KERNELRELEASE),)
# kbuild part of makefile
obj-m := $(MODULE_NAME).o
$(MODULE_NAME)-y := ipc-chardev.o

# Add here cc flags (e.g. header lookup paths, defines, etc) 
ccflags-y += -I$(IPC_SHM_DEV_PATH) -I$(src) 

else
# normal part of makefile

# The following parameters must be passed from the caller,
# e.g. build system (Yocto), command line:
# KERNELDIR    : Linux kernel source code location
# INSTALL_DIR  : location of the module installation
# CROSS_COMPILE: cross compiler path and prefix

modules:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) KBUILD_EXTRA_SYMBOLS=$(EXTRA_SYMBOLS) ARCH=$(ARCH) CROSS_COMPILE=$(CROSS_COMPILE) $@

modules_install: modules
	$(MAKE) -C $(KERNELDIR) M=$(PWD) INSTALL_MOD_PATH="$(INSTALL_DIR)" $@

clean:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) ARCH=$(ARCH) CROSS_COMPILE=$(CROSS_COMPILE) $@

.PHONY: clean
endif
