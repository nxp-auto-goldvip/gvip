/**
*   @file       ipc-platform-cfg.h
*   @brief      IPCF platform-specific settings
*/
/* ==========================================================================
*   (c) Copyright 2022, 2024 NXP
*   All Rights Reserved.
=============================================================================*/
#ifndef __IPC_PLATFORM_CFG__H__
#define __IPC_PLATFORM_CFG__H__

#if defined(PLATFORM_s32g2) || defined(PLATFORM_s32g3)

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

#error "Platform not supported"

#endif /* defined(PLATFORM_s32g2) || defined(PLATFORM_s32g2) */

#endif /* __IPC_PLATFORM_CFG__H__ */
