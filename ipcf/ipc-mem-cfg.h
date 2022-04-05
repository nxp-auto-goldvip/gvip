/**
*   @file       ipc-mem-cfg.h
*   @brief      IPCF memory settings
*/
/* ==========================================================================
*   (c) Copyright 2022 NXP
*   All Rights Reserved.
=============================================================================*/
#ifndef __IPCF_MEM_CFG__H__
#define __IPCF_MEM_CFG__H__

#ifndef PLATFORM
#define S32G74A
#endif /* PLATFORM */

#if defined(S32G74A)

/* Local core shared memory address */
#ifndef LOCAL_SHM_ADDR
#define LOCAL_SHM_ADDR              0x34080000
#endif /* LOCAL_SHM_ADDR */

/* Remote core shared memory address */
#ifndef REMOTE_SHM_ADDR
#define REMOTE_SHM_ADDR             0x34000000
#endif /* REMOTE_SHM_ADDR */

/* Shared memory size, half for local, half for remote */
#ifndef IPC_SHM_SIZE
#define IPC_SHM_SIZE                0x80000
#endif /* IPC_SHM_SIZE */

/* IPCF Buffer size */
#ifndef IPCF_BUF_LEN
#define IPCF_BUF_LEN                128u
#endif /* IPCF_BUF_LEN */

/* Kernel object queue size */
#ifndef IPC_QUEUE_SIZE
#define IPC_QUEUE_SIZE 	            64u
#endif /* IPC_QUEUE_SIZE */

/* M7_0 core status register */
#define M7_0_CORE_STAT_REG          0x40088148u
#define M7_0_CORE_STAT_REG_SIZE     0x4u
#define M7_0_CORE_ACTIVE            0x1u

#else
#error "UNKNOWN PLATFORM"
#endif /* defined(S32G74A) */

#endif /* __IPCF_MEM_CFG__H__ */