/**
*   @file       ipc-chardev.c
*   @brief      Implementation of a character device driver on top of IPCF
*
*/
/* ==========================================================================
*   (c) Copyright 2022-2024 NXP
*   All Rights Reserved.
=============================================================================*/
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/kobject.h>
#include <linux/sysfs.h>
#include <linux/string.h>
#include <linux/stat.h>
#include <linux/completion.h>
#include <linux/fs.h>
#include <linux/uaccess.h>
#include <linux/init.h>
#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/of.h>
#include <linux/of_reserved_mem.h>
#include <linux/kern_levels.h>
#include <linux/ioport.h>
#include <linux/mod_devicetable.h>
#include <asm/io.h>
#include <ipc-shm.h>
#include <ipc-platform-cfg.h>

/* ==========================================================================
 * MODULE INFORMATION
 * ==========================================================================*/
#define MODULE_NAME "ipc-shm-chdev"
#define MODULE_VER "0.1"
MODULE_AUTHOR("NXP");
MODULE_LICENSE("Dual BSD/GPL");
MODULE_ALIAS(MODULE_NAME);
MODULE_DESCRIPTION("GoldVIP IPC shared memory character device driver");
MODULE_VERSION(MODULE_VER);

/* ==========================================================================
 * MACROS AND SYMBOLIC CONSTANTS
 * ==========================================================================*/
/* Device name, as it will be listed under /dev directory */
#define DEVICE_NAME                     "ipcfshm"

/* Marker for IPCF instances / channels */
#define IPC_INVALID                     0xFFu

/* IPCF instances count, by default, only one is enabled */
#ifndef IPC_NUM_INSTANCES
#define IPC_NUM_INSTANCES               1u
#endif /* IPC_NUM_INSTANCES */

#ifndef IPC_INST_0_CHAN_NUM
#define IPC_INST_0_CHAN_NUM             4u
#endif /* IPC_INST_0_CHAN_NUM */

#ifndef IPC_INST_1_CHAN_NUM
#define IPC_INST_1_CHAN_NUM             0u
#endif /* IPC_INST_1_CHAN_NUM */

#ifndef IPC_INST_2_CHAN_NUM
#define IPC_INST_2_CHAN_NUM             0u
#endif /* IPC_INST_2_CHAN_NUM */

#ifndef IPC_INST_3_CHAN_NUM
#define IPC_INST_3_CHAN_NUM             0u
#endif /* IPC_INST_3_CHAN_NUM */

/* Total number of IPCF channels */
#define IPC_NUM_CHANNELS                (IPC_INST_0_CHAN_NUM + IPC_INST_1_CHAN_NUM +\
                                         IPC_INST_2_CHAN_NUM + IPC_INST_3_CHAN_NUM)

/* Maximum name size for a channel/instance */
#define MAX_NAME_SIZE                   20u

/* A53 RX interupt number */
#define INTER_CORE_RX_IRQ               2u

/* ==========================================================================
 * STRUCTURES AND TYPEDEFS
 * ==========================================================================*/
/* IPCF channel descriptor, internal structure of the character device driver */
struct ipc_chan_descr_t {
    /* Memory pool, handled as a round buffer */
    uint8_t  chan_pool[IPC_QUEUE_SIZE][IPCF_BUF_LEN];
    /* Array of message sizes received from the remote counterpart */
    uint32_t msg_size[IPC_QUEUE_SIZE];
    /* Message status */
    bool     msg_processed[IPC_QUEUE_SIZE];
    /* Associated character device driver */
    struct   cdev chardev;
    /* Index of the next free buffer in the round memory pool */
    uint32_t free_buff_idx;
    /* Number of pending messages (messages received via callback)
       but not read via the ipcf_read function */
    uint32_t num_pending_msg;
    /* Associated instance id */
    uint8_t  instance_id;
    /* Associated channel id */
    uint8_t  channel_id;
};

/* IPCF instance descriptor used to map the existing channels in the rootfs.
 * Each IPCF instance is linked to a core (set in the instance_name field)
 * Each of the channel names are then shown in the rootfs as files, under the
 * coresponding instance.
 */
struct ipc_inst_descr_t {
    /* channel names */
    char channel_names[IPC_SHM_MAX_CHANNELS][MAX_NAME_SIZE];
    /* Instance name */
    char instance_name[MAX_NAME_SIZE];
    /* Array of configuration structures which enforce data size
       prepending to data read from user space */
    bool chan_prepend_size[IPC_SHM_MAX_CHANNELS];
    /* Number of channels assigned to the instance */
    uint8_t channel_count;
};

/* ==========================================================================
 * LOCAL FUNCTION PROTOTYPES
 * ==========================================================================*/
int ipcf_close(struct inode *pinode, struct file *pfile);
int ipcf_open(struct inode *pinode, struct file *pfile);
ssize_t ipcf_read(struct file *pfile, char __user *buffer, size_t length,
                  loff_t *offset);
ssize_t ipcf_write(struct file *pfile, const char __user *buffer, size_t length,
                   loff_t *offset);
static void init_state_vars(void);
static void data_chan_rx_cb(void *cb_arg, const uint8_t instance,
                            uint8_t chan_id, void *buf, uint32_t size);
static uint8_t get_device_idx(uint8_t inst_id, uint8_t chan_id);
static uint8_t *get_next_pending_buff(struct ipc_chan_descr_t *ch, uint32_t *size);
static uint8_t *get_next_free_buff(struct ipc_chan_descr_t *ch, uint32_t size);

/* ==========================================================================
 * File operations
 * ==========================================================================*/
/* This structure contains available file operations which are registered via
 * ipcf_module_init function */
struct file_operations ipcf_file_operations = {
    .owner = THIS_MODULE,
    .open  = ipcf_open,
    .read  = ipcf_read,
    .write = ipcf_write,
    .release = ipcf_close,
};

/* ==========================================================================
 * IPCF Configuration
 * ==========================================================================*/
/* IPCF memory pools configuration */
static struct ipc_shm_pool_cfg buf_pools[] = {
    { .num_bufs = IPC_QUEUE_SIZE, .buf_size = IPCF_BUF_LEN}
};

/* IPCF channel configuration */
static const struct ipc_shm_channel_cfg data_chan_cfg = {
    .type = IPC_SHM_MANAGED,
    .ch = {
        .managed = {
            .num_pools = ARRAY_SIZE(buf_pools),
            .pools = buf_pools,
            .rx_cb = data_chan_rx_cb,
            .cb_arg = NULL,
        },
    }
};

/* IPCF instance 0 channels configuration */
static struct ipc_shm_channel_cfg instance_0_channels[IPC_INST_0_CHAN_NUM] = {
    data_chan_cfg,
    data_chan_cfg,
    data_chan_cfg,
    data_chan_cfg
};

/* IPCF SHM compatible values */
static const struct of_device_id ipcf_res_no_map_name[IPC_NUM_INSTANCES] = {
    { .compatible = "nxp,s32g-ipcf-shm"}
};

/* IPCF shared memory configuration */
static struct ipc_shm_cfg shm_cfg[IPC_NUM_INSTANCES] = {
    {
        /* IPCF shared memory address will be used by init function. */
        .inter_core_tx_irq = IPC_IRQ_NONE,
        .inter_core_rx_irq = INTER_CORE_RX_IRQ,
        .local_core = {
            .type = IPC_CORE_A53,
            .index = IPC_CORE_INDEX_0,
            .trusted = IPC_CORE_INDEX_0 | IPC_CORE_INDEX_1 |
                    IPC_CORE_INDEX_2 | IPC_CORE_INDEX_3
        },
        .remote_core = {
            .type = IPC_CORE_M7,
            .index = IPC_CORE_INDEX_0,
        },
        .num_channels = IPC_INST_0_CHAN_NUM,
        .channels = instance_0_channels
    }
};

/* ==========================================================================
 * LOCAL VARIABLES
 * ==========================================================================*/

/* Pointer to the allocated device class */
static struct class *ipcfshm_class = NULL;

/* Character device major number */
static int    dev_major = 0;

/* IPC channel descriptors, containing status and memory pool associated with
 * the channel */
static struct ipc_chan_descr_t ipc_ch_descr[IPC_NUM_CHANNELS];

/* IPCF instance descriptor used to map the existing channels in the rootfs.
 * Each IPCF instance is linked to a core (set in the instance_name field)
 * Each of the channel names are then shown in the rootfs as files, under the
 * coresponding instance. For example, the existing configuration will be
 * shown as:
 * /dev/ipcfshm/M7_0/echo
 * /dev/ipcfshm/M7_0/idps_statistics
 * /dev/ipcfshm/M7_0/benchmark
 * /dev/ipcfshm/M7_0/health_mon
 */
static struct ipc_inst_descr_t inst_descr[IPC_NUM_INSTANCES] = {
    {
        .instance_name = "M7_0",
        .channel_count = IPC_INST_0_CHAN_NUM,
        .channel_names = {"echo", "idps_statistics", "benchmark", "health_mon"},
        .chan_prepend_size = {false, true, false, false},
    },
};

/* ==========================================================================
 *                              LOCAL FUNCTIONS
 * ==========================================================================*/
 /**
 *  @brief  Gets the device index from the global channel descriptor
 *  @return IPC_INVALD/Channel ID
 */
static uint8_t get_device_idx(uint8_t inst_id, uint8_t chan_id)
{
    uint8_t i;
    uint8_t dev_id = IPC_INVALID;
    for (i = 0; i < IPC_NUM_CHANNELS; i++) {
        if (ipc_ch_descr[i].instance_id == inst_id &&
            ipc_ch_descr[i].channel_id == chan_id) {
            dev_id = i;
            break;
        }
    }
    return dev_id;
}

/**
 *  @brief          Gets the next available buffer from the round
 *                  pool associated with the channel descriptor
 *                  and saves the size of the input buffer in the channel descriptor.
 *                  If the buffer is full, the oldest data in the buffer will
 *                  be overwritten.
 *  @param ch       Pointer to the internal channel descriptor
 *  @param size     Data size
 *  @return         pointer to the allocated buffer
 */
static uint8_t *get_next_free_buff(struct ipc_chan_descr_t *ch, uint32_t size)
{
    uint8_t *pbuff = NULL;
    uint32_t buff_idx = 0;

    /* Last index in pool was reached, reset counter */
    if (ch->free_buff_idx >= IPC_QUEUE_SIZE) {
        ch->free_buff_idx = 0;
    }
    buff_idx = ch->free_buff_idx;

    ch->num_pending_msg = min(IPC_QUEUE_SIZE, ch->num_pending_msg + 1);
    /* get buff */
    pbuff = ch->chan_pool[buff_idx];

    /* Go to the next buffer */
    ch->msg_size[buff_idx] = size;
    /* mark buffer as not processed */
    ch->msg_processed[buff_idx] = false;
    /* Go to the next buffer */
    ch->free_buff_idx++;

    return pbuff;
}

/**
 *  @brief          Gets the oldest unprocessed buffer in the pool,
 *                  while updating the number of pending buffers.
 *  @param ch       Pointer to the internal channel descriptor
 *  @param size     Pointer to a variable holding the buffer size
 *  @return         pointer to the allocated buffer
 */
static uint8_t *get_next_pending_buff(struct ipc_chan_descr_t *ch, uint32_t *size)
{
    uint8_t *pbuff = NULL;

    /* Get next pending buffer index, ensuring that no illegal accesses take place */
    uint32_t buff_idx = ((IPC_QUEUE_SIZE + ch->free_buff_idx - ch->num_pending_msg) % IPC_QUEUE_SIZE);

    if (0 == ch->num_pending_msg) {
        return NULL;
    }

    if (ch->msg_processed[buff_idx] == false) {
        ch->msg_processed[buff_idx] = true;
        *size = ch->msg_size[buff_idx];
        pbuff = ch->chan_pool[buff_idx];
        ch->num_pending_msg --;
    }
    return pbuff;
}

/**
 *  @brief  This function initializes local variables
 *          This function shall be called when the module is registered in order
 *          to avoid usage of values received at a previous registration of the
 *          device driver
 *  @return N/A
 */
static void init_state_vars(void)
{
    int idx = 0;
    int ch_idx = 0;
    for (ch_idx = 0; ch_idx < IPC_NUM_CHANNELS; ch_idx++) {
        ipc_ch_descr[ch_idx].num_pending_msg = 0;
        ipc_ch_descr[ch_idx].free_buff_idx = 0;
        for (idx = 0; idx < IPC_QUEUE_SIZE; idx++) {
            ipc_ch_descr[ch_idx].msg_size[idx] = 0;
            ipc_ch_descr[ch_idx].msg_processed[idx] = true;
        }
    }
}

/**
 *  @brief          Callback function for the received messages.
 *
 *  @param arg      Callback argument
 *  @param inst_id  The instance for which the callback is called
 *  @param chan_id  Channel unique identifier for which the callback is called
 *  @param buf      Pointer to the received buffer
 *  @param instance The instance for which the callback is called
 *
 *  @return         N/A
 */
static void data_chan_rx_cb(void *arg, const uint8_t inst_id, uint8_t chan_id,
                            void *buf, uint32_t size)
{
    int err;
    uint8_t dev_id = IPC_INVALID;
    uint8_t *pbuff;
    (void)arg;

    if (IPCF_BUF_LEN >= size) {
        dev_id = get_device_idx(inst_id, chan_id);
        if (IPC_INVALID == dev_id) {
            printk(KERN_ALERT "IPCF callback called for unknown device via \
                   instance id: %d and channel %d \n", inst_id, chan_id);
            goto free_ipc_buffer;
        }

        pbuff = get_next_free_buff(&ipc_ch_descr[dev_id], size);

        /* Copy to pool, these message will be available to user space via the
           read function */
        memcpy_fromio(pbuff, buf, size);
    } else {
        printk(KERN_ALERT "Received data does not fit \
               in the existing buffers with for instance id %d, channel id %d,\
               of size %zu \n", inst_id, chan_id, size);
    }

free_ipc_buffer:
    /* release the buffer */
    err = ipc_shm_release_buf(inst_id, chan_id, buf);
    if (err) {
        printk(KERN_ALERT "failed to free buffer for instance %d, channel %d,"
               "err code %d \n", inst_id, chan_id, err);
    }
}

/* ==========================================================================
 *                              GLOBAL FUNCTIONS
 * ==========================================================================*/
/**
 *  @brief          Read function for Ipc character device driver.
 *                  This function is called whenever the character device driver
 *                  is open for reading, e.g: a "cat" operation.
 *                  It reads from the message queue and returns the first
 *                  unprocessed message to the user space.
 *  @param pfile    Pointer to the device driver file
 *  @param buffer   Pointer to the allocated buffer for reading
 *  @param length   Allocated buffer size
 *  @param offset   Pointer containing last read line from the device driver.
 *
 *  @return         size of read data
 */
ssize_t ipcf_read(struct file *pfile, char __user *buffer, size_t length,
                  loff_t *offset)
{
    size_t ret = 0;
    struct ipc_chan_descr_t *ch = pfile->private_data;
    uint8_t inst_id = ch->instance_id;
    uint8_t chan_id = ch->channel_id;
    uint32_t pbuff_size = 0;

    uint8_t *pbuff = get_next_pending_buff(ch, &pbuff_size);
    uint32_t pbuff_size_be = cpu_to_be32(pbuff_size);
    if (NULL != pbuff) {
        if (inst_descr[inst_id].chan_prepend_size[chan_id]) {
            if (copy_to_user(buffer, &pbuff_size_be, sizeof(uint32_t))) {
                printk(KERN_ALERT "failed to copy message size to user space \n");
                /* Discard message */
                return -EFAULT;
            }
            buffer += sizeof(uint32_t);
            ret += sizeof(uint32_t);
        }
        /* Copy payload to user space */
        if (copy_to_user(buffer, pbuff, pbuff_size)) {
            printk(KERN_ALERT "failed to copy payload to user \n");
            ret = -EFAULT;
        } else {
            ret += pbuff_size;
        }
    }
    return ret;
}

/**
* @brief WRITE function for Ipc module.
*        This function is called whenever the character device driver is open
*        for writing, e.g: a "echo" operation. It reads from the user buffer
*        the message intended to be sent, allocates a buffer from the ones
*        available and sends it to the communication partner.
*
* @param  pfile     Pointer to the device driver file
* @param  buffer    Pointer to the allocated buffer for reading
* @param  length    Allocated buffer size
* @param  offset    Pointer containing last read line from the device driver.
*
* @return number of written bytes.
*/
ssize_t ipcf_write(struct file *pfile, const char __user *buffer, size_t length,
                   loff_t *offset)
{
    size_t err;
    char *buf = NULL;
    struct ipc_chan_descr_t *ch = pfile->private_data;
    uint8_t inst_id = ch->instance_id;
    uint8_t chan_id = ch->channel_id;

    if (IPCF_BUF_LEN < length) {
        length = IPCF_BUF_LEN;
    }

    buf = ipc_shm_acquire_buf(inst_id, chan_id, length);
    if (!buf) {
        printk(KERN_ALERT "failed to get buffer for instance ID %d channel ID"
               " %d and size %d\n", inst_id, chan_id, (int)length);
        return -ENOMEM;
    }

    /* copy the buffer from user to ipc engine */
    if (copy_from_user(buf, buffer, length)) {
        printk(KERN_ALERT "failed to copy payload from user \n");
        return -EFAULT;
    }

    err = ipc_shm_tx(inst_id, chan_id, buf, length);
    if (err) {
        printk(KERN_ALERT "tx failed for instance ID %d channel ID %d, size "
               "%d, error code %d\n", inst_id, chan_id, (int)length, (int)err);
        return err;
    }
    return length;
}

/**
* @brief  Open function for ipc module
*
* @param  pinode    Pointer to the device driver directory
* @param  pfile     Pointer to the device driver file
*
* @return 0
*/
int ipcf_open(struct inode *pinode, struct file *pfile)
{
    pfile->private_data = &ipc_ch_descr[iminor(pinode)];
    return 0;
}

/**
* @brief  Close function for ipc module
*
* @param  pinode    Pointer to the device driver directory
* @param  pfile     Pointer to the device driver file
*
* @return 0
*/
int ipcf_close(struct inode *pinode, struct file *pfile)
{
    (void) pinode;
    (void) pfile;
    return 0;
}

/**
* @brief  This function ensures that the files have the same permissions
*
* @param  dev               Pointer to the device
* @param  kobj_uevent_env   Event
*
* @return 0
*/
static int ipcfshm_uevent(struct device *dev, struct kobj_uevent_env *env)
{
    add_uevent_var(env, "DEVMODE=%#o", 0666);
    return 0;
}

/**
* @brief  This function will register character device driver for ipc
*         This function is called whenever the character device driver being registered in the
*         kernel via insmod function.
*
* @return ERROR or 0
*/
static int __init ipcf_module_init(void)
{
    int err;
    int cdev_idx = 0;
    dev_t dev;
    int inst_id = 0;
    int ch_id = 0;
    uint32_t M7_0_stat = 0;
    uint32_t *pM7_0_stat = NULL;
    struct device *pdev = NULL;
    struct device_node *mem_node;
    struct reserved_mem *rmem;
    struct ipc_shm_instances_cfg shm_instances_cfg = {
        .num_instances = IPC_NUM_INSTANCES,
        .shm_cfg = shm_cfg
    };

    for (inst_id = 0; inst_id < IPC_NUM_INSTANCES; inst_id++) {
        /* Find a node by its "compatible" property */
        mem_node = of_find_compatible_node(NULL, NULL, ipcf_res_no_map_name[inst_id].compatible);
        if (!mem_node) {
            printk(KERN_ERR "The node was not found by its compatible: %s\n", ipcf_res_no_map_name[inst_id].compatible);
            return -ENODEV;
        }

        rmem = of_reserved_mem_lookup(mem_node);
        if (!rmem) {
            printk(KERN_ERR "of_reserved_mem_lookup() returned NULL\n");
            of_node_put(mem_node);
            return -ENODEV;
        }

        of_node_put(mem_node);

        shm_instances_cfg.shm_cfg[inst_id].shm_size = rmem->size / 2;
        shm_instances_cfg.shm_cfg[inst_id].remote_shm_addr = rmem->base;
        shm_instances_cfg.shm_cfg[inst_id].local_shm_addr = rmem->base + rmem->size / 2;
    }

    pM7_0_stat = ioremap(M7_0_CORE_STAT_REG, M7_0_CORE_STAT_REG_SIZE);
    if (IS_ERR(pM7_0_stat)) {
        printk (KERN_ALERT "Failed to map M7_0 core status register \n");
        return -EFAULT;
    }
    M7_0_stat = ioread32(pM7_0_stat);
    iounmap(pM7_0_stat);
    /* Check if M7 is up */
    if (M7_0_CORE_ACTIVE != (M7_0_stat & M7_0_CORE_ACTIVE)) {
        printk(KERN_ALERT "M7_0 core is not started, %s module will not be inserted\n", 
               MODULE_NAME);
        return -EFAULT;
    }

    err = alloc_chrdev_region(&dev, 0, IPC_NUM_CHANNELS, DEVICE_NAME);
    if (err) {
        printk(KERN_ALERT "Failed to allocate character device driver \n");
        return err;
    }
    /* get major number for device driver */
    dev_major = MAJOR(dev);

    ipcfshm_class = class_create(THIS_MODULE, DEVICE_NAME);
    if (NULL == ipcfshm_class) {
        printk(KERN_ALERT "Failed to create device class for %s \n", DEVICE_NAME);
        goto free_chdev_region;
    }
    ipcfshm_class->dev_uevent = ipcfshm_uevent;

    for (inst_id = 0; inst_id < IPC_NUM_INSTANCES; inst_id++) {
        for (ch_id = 0; ch_id < inst_descr[inst_id].channel_count; ch_id++) {
            ipc_ch_descr[cdev_idx].instance_id = inst_id;
            ipc_ch_descr[cdev_idx].channel_id = ch_id;

            cdev_init(&(ipc_ch_descr[cdev_idx].chardev), &ipcf_file_operations);
            ipc_ch_descr[cdev_idx].chardev.owner = THIS_MODULE;

            if (0 != cdev_add(&(ipc_ch_descr[cdev_idx].chardev), MKDEV(dev_major, cdev_idx), 1)) {
                printk(KERN_ALERT "Failed to add device in rootfs \n");
                goto free_cdev;
            }
            /* Create character device driver */
            pdev = device_create(ipcfshm_class, NULL, MKDEV(dev_major, cdev_idx), NULL,
                                 "%s!%s!%s", DEVICE_NAME, inst_descr[inst_id].instance_name,
                                 inst_descr[inst_id].channel_names[ch_id]);
            if (IS_ERR(pdev)) {
                cdev_del(&(ipc_ch_descr[cdev_idx].chardev));
                printk(KERN_ALERT "Failed to insert device in rootfs \n");
                goto free_cdev;
            }
            cdev_idx++;
        }
    }
    /* Initialize local variables in case they were written previously */
    init_state_vars();

    if (ipc_shm_init(&shm_instances_cfg)) {
        printk(KERN_ALERT "Failed to initialize IPCF \n");
        goto free_cdev;
    }
    return 0;

free_cdev:
    for (cdev_idx = cdev_idx - 1; cdev_idx >= 0; cdev_idx--) {
        cdev_del(&(ipc_ch_descr[cdev_idx].chardev));
        device_destroy(ipcfshm_class, MKDEV(dev_major, cdev_idx));
    }
    class_destroy(ipcfshm_class);

free_chdev_region:
    unregister_chrdev_region(MKDEV(dev_major, 0), MINORMASK);

    return -EFAULT;
}

/**
* @brief  This function will un-register character device driver for ipc
*         This function is called whenever the character device driver being
*         unregistered in the kernel via the rmmod functionality.
*
* @return N/A
*/
static void __exit ipcf_module_exit(void)
{
    int i;

    for (i = 0; i < IPC_NUM_CHANNELS; i++) {
        cdev_del(&(ipc_ch_descr[i].chardev));
        device_destroy(ipcfshm_class, MKDEV(dev_major, i));
    }

    unregister_chrdev_region(MKDEV(dev_major, 0), MINORMASK);

    class_destroy(ipcfshm_class);

    ipc_shm_free();
}

/* ==========================================================================
 *                CHARACTER DEVICE DRIVER SPECIFIC OPERATIONS
 * ==========================================================================*/
module_init(ipcf_module_init);
module_exit(ipcf_module_exit);
