/**********************************************************************************************************************
 *  EXAMPLE CODE ONLY
 *  -------------------------------------------------------------------------------------------------------------------
 *  This Example Code is only intended for illustrating an example of a possible Zetta Auto application.
 *  The Example Code has not passed any quality control measures and may be incomplete. The Example Code is neither
 *  intended nor qualified for use in series production. The Example Code as well as any of its modifications and/or
 *  implementations must be tested with diligent care and must comply with all quality requirements which are necessary
 *  according to the state of the art before their use.
 *
 *  (c) Copyright 2026 NXP
 *  All Rights Reserved.
 *
 *********************************************************************************************************************/

/* Enable POSIX extensions for timer_create, clock_gettime, CLOCK_REALTIME, etc. */
#define _POSIX_C_SOURCE 199309L
#define _GNU_SOURCE

#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <signal.h>
#include <unistd.h>
#include <time.h>
#include <pthread.h>

/* Include the CycloneDDS C API */
#include "dds/dds.h"

/* Include data type definitions */
#include "Topics.h"

#define GIGA 1000000000ULL
#define HYPERPERIOD_NS 100000000ULL
#define APP_PERIOD_NS 50000000ULL

/* Global application context */
static dds_entity_t participant;

/* Mutex for thread-safe logging */
static pthread_mutex_t g_mutex = PTHREAD_MUTEX_INITIALIZER;

/**
 * @brief Callback for data available on HeadLamp reader
 */
static void on_data_available_HeadLamp(dds_entity_t reader, void *arg)
{
    void *samples[1];
    dds_sample_info_t infos[1];
    int rc;
    struct timespec ts;
    unsigned long long ns_global;

    samples[0] = NULL;

    /* Take one sample */
    rc = dds_take(reader, samples, infos, 1, 1);
    if (rc < 0) {
        fprintf(stderr, "Error: dds_take failed: %s\n", dds_strretcode(-rc));
        return;
    }

    if (rc == 0) {
        return;
    }

    if (!infos[0].valid_data) {
        dds_return_loan(reader, samples, rc);
        return;
    }

    /* Get current time */
    if (clock_gettime(CLOCK_REALTIME, &ts)) {
        perror("Error to clock_gettime");
        ns_global = 0;
    } else {
        ns_global = (unsigned long long)ts.tv_sec * GIGA + (unsigned long long)ts.tv_nsec;
    }

    /* Copy received data */
    Topics_MotionWise_DDS_HeadLamp *msg1 = (Topics_MotionWise_DDS_HeadLamp *)samples[0];

    /* Thread-safe logging */
    pthread_mutex_lock(&g_mutex);
    printf(" DDS - receiving HeadLamp: side=%c; highBeam=%d; lowBeam=%d; dayLight=%d; fog=%d; parking=%d; turn=%d\n",
           msg1->side,
           msg1->highBeam,
           msg1->lowBeam,
           msg1->dayLight,
           msg1->fog,
           msg1->parking,
           msg1->turn
        );
    fflush(stdout);
    pthread_mutex_unlock(&g_mutex);

    dds_return_loan(reader, samples, rc);
}

/**
 * @brief Callback for data available on RearLight reader
 */
static void on_data_available_RearLight(dds_entity_t reader, void *arg)
{
    void *samples[1];
    dds_sample_info_t infos[1];
    int rc;
    struct timespec ts;
    unsigned long long ns_global;

    samples[0] = NULL;

    /* Take one sample */
    rc = dds_take(reader, samples, infos, 1, 1);
    if (rc < 0) {
        fprintf(stderr, "Error: dds_take failed: %s\n", dds_strretcode(-rc));
        return;
    }

    if (rc == 0) {
        return;
    }

    if (!infos[0].valid_data) {
        dds_return_loan(reader, samples, rc);
        return;
    }

    /* Get current time */
    if (clock_gettime(CLOCK_REALTIME, &ts)) {
        perror("Error to clock_gettime");
        ns_global = 0;
    } else {
        ns_global = (unsigned long long)ts.tv_sec * GIGA + (unsigned long long)ts.tv_nsec;
    }

    /* Copy received data */
    Topics_MotionWise_DDS_RearLight *msg1 = (Topics_MotionWise_DDS_RearLight *)samples[0];

    /* Thread-safe logging */
    pthread_mutex_lock(&g_mutex);
    printf(" DDS - receiving RearLight: side=%c; tail=%d; reverse=%d; brake=%d; fog=%d; parking=%d; turn=%d\n",
           msg1->side,
           msg1->tail,
           msg1->reverse,
           msg1->brake,
           msg1->fog,
           msg1->parking,
           msg1->turn
        );
    fflush(stdout);
    pthread_mutex_unlock(&g_mutex);

    dds_return_loan(reader, samples, rc);
}

/**
 * @brief Callback for data available on StopLamp reader
 */
static void on_data_available_StopLamp(dds_entity_t reader, void *arg)
{
    void *samples[1];
    dds_sample_info_t infos[1];
    int rc;
    struct timespec ts;
    unsigned long long ns_global;

    samples[0] = NULL;

    /* Take one sample */
    rc = dds_take(reader, samples, infos, 1, 1);
    if (rc < 0) {
        fprintf(stderr, "Error: dds_take failed: %s\n", dds_strretcode(-rc));
        return;
    }

    if (rc == 0) {
        return;
    }

    if (!infos[0].valid_data) {
        dds_return_loan(reader, samples, rc);
        return;
    }

    /* Get current time */
    if (clock_gettime(CLOCK_REALTIME, &ts)) {
        perror("Error to clock_gettime");
        ns_global = 0;
    } else {
        ns_global = (unsigned long long)ts.tv_sec * GIGA + (unsigned long long)ts.tv_nsec;
    }

    /* Copy received data */
    Topics_MotionWise_DDS_StopLamp *msg1 = (Topics_MotionWise_DDS_StopLamp *)samples[0];

    /* Thread-safe logging */
    pthread_mutex_lock(&g_mutex);
    printf(" DDS - receiving StopLamp: intensity=%d\n", msg1->intensity);
    fflush(stdout);
    pthread_mutex_unlock(&g_mutex);

    dds_return_loan(reader, samples, rc);
}

/**
 * @brief Callback for data available on HazardLights reader
 */
static void on_data_available_HazardLights(dds_entity_t reader, void *arg)
{
    void *samples[1];
    dds_sample_info_t infos[1];
    int rc;
    struct timespec ts;
    unsigned long long ns_global;

    samples[0] = NULL;

    /* Take one sample */
    rc = dds_take(reader, samples, infos, 1, 1);
    if (rc < 0) {
        fprintf(stderr, "Error: dds_take failed: %s\n", dds_strretcode(-rc));
        return;
    }

    if (rc == 0) {
        return;
    }

    if (!infos[0].valid_data) {
        dds_return_loan(reader, samples, rc);
        return;
    }

    /* Get current time */
    if (clock_gettime(CLOCK_REALTIME, &ts)) {
        perror("Error to clock_gettime");
        ns_global = 0;
    } else {
        ns_global = (unsigned long long)ts.tv_sec * GIGA + (unsigned long long)ts.tv_nsec;
    }

    /* Copy received data */
    Topics_MotionWise_DDS_HazardLights *msg1 = (Topics_MotionWise_DDS_HazardLights *)samples[0];

    /* Thread-safe logging */
    pthread_mutex_lock(&g_mutex);
    printf(" DDS - receiving HazardLights: on=%d\n", msg1->on);
    fflush(stdout);
    pthread_mutex_unlock(&g_mutex);

    dds_return_loan(reader, samples, rc);
}

/**
 * @brief Callback for data available on LicensePlateLight reader
 */
static void on_data_available_LicensePlateLight(dds_entity_t reader, void *arg)
{
    void *samples[1];
    dds_sample_info_t infos[1];
    int rc;
    struct timespec ts;
    unsigned long long ns_global;

    samples[0] = NULL;

    /* Take one sample */
    rc = dds_take(reader, samples, infos, 1, 1);
    if (rc < 0) {
        fprintf(stderr, "Error: dds_take failed: %s\n", dds_strretcode(-rc));
        return;
    }

    if (rc == 0) {
        return;
    }

    if (!infos[0].valid_data) {
        dds_return_loan(reader, samples, rc);
        return;
    }

    /* Get current time */
    if (clock_gettime(CLOCK_REALTIME, &ts)) {
        perror("Error to clock_gettime");
        ns_global = 0;
    } else {
        ns_global = (unsigned long long)ts.tv_sec * GIGA + (unsigned long long)ts.tv_nsec;
    }

    /* Copy received data */
    Topics_MotionWise_DDS_LicensePlateLight *msg1 = (Topics_MotionWise_DDS_LicensePlateLight *)samples[0];

    /* Thread-safe logging */
    pthread_mutex_lock(&g_mutex);
    printf(" DDS - receiving LicensePlateLight: on=%d\n", msg1->on);
    fflush(stdout);
    pthread_mutex_unlock(&g_mutex);

    dds_return_loan(reader, samples, rc);
}

static bool Mpu_CreateTopic(
    dds_entity_t participant,
    const dds_topic_descriptor_t *topic_desc,
    const char *name,
    dds_on_data_available_fn callback)
{
    dds_entity_t topic;
    dds_entity_t subscriber;
    dds_entity_t reader;
    dds_listener_t *listener = NULL;

    /* Create topic for subscribing (HeadLamp) */
    topic = dds_create_topic(participant, topic_desc, name, NULL, NULL);
    if (topic < 0) {
        fprintf(stderr, "Error: dds_create_topic failed for %s: %s\n", name, dds_strretcode(-topic));
        return false;
    }

    /* Create subscriber */
    subscriber = dds_create_subscriber(participant, NULL, NULL);
    if (subscriber < 0) {
        fprintf(stderr, "Error: dds_create_subscriber failed for %s: %s\n", name, dds_strretcode(-subscriber));
        return false;
    }

    /* Create listener for HeadLamp data available callback */
    listener = dds_create_listener(NULL);
    if (listener == NULL) {
        fprintf(stderr, "Error: dds_create_listener failed for %s\n", name);
        return false;
    }
    dds_lset_data_available(listener, callback);

    /* Create data reader for HeadLamp with listener */
    reader = dds_create_reader(subscriber, topic, NULL, listener);
    dds_delete_listener(listener);
    if (reader < 0) {
        fprintf(stderr, "Error: dds_create_reader failed for %s: %s\n", name, dds_strretcode(-reader));
        return false;
    }
    printf("MPU Data reader constructed successfully for %s\n", name);
    fflush(stdout);

    return true;
}

/**
 * @brief Initialize the DDS entities
 */
static bool Mpu_Subscriber_Init(dds_entity_t *participant)
{
    dds_return_t rc;

    /* Create a DDS participant */
    *participant = dds_create_participant(DDS_DOMAIN_DEFAULT, NULL, NULL);
    if (*participant < 0) {
        fprintf(stderr, "Error: dds_create_participant failed: %s\n", dds_strretcode(*participant));
        return false;
    }

    if (false == Mpu_CreateTopic(
        *participant,
        &Topics_MotionWise_DDS_HeadLamp_desc,
        "Topics_MotionWise_DDS_HeadLamp",
        on_data_available_HeadLamp
    )) {
        return false;
    }

    if (false == Mpu_CreateTopic(
        *participant,
        &Topics_MotionWise_DDS_RearLight_desc,
        "Topics_MotionWise_DDS_RearLight",
        on_data_available_RearLight
    )) {
        return false;
    }

    if (false == Mpu_CreateTopic(
        *participant,
        &Topics_MotionWise_DDS_StopLamp_desc,
        "Topics_MotionWise_DDS_StopLamp",
        on_data_available_StopLamp
    )) {
        return false;
    }

    if (false == Mpu_CreateTopic(
        *participant,
        &Topics_MotionWise_DDS_HazardLights_desc,
        "Topics_MotionWise_DDS_HazardLights",
        on_data_available_HazardLights
    )) {
        return false;
    }

    if (false == Mpu_CreateTopic(
        *participant,
        &Topics_MotionWise_DDS_LicensePlateLight_desc,
        "Topics_MotionWise_DDS_LicensePlateLight",
        on_data_available_LicensePlateLight
    )) {
        return false;
    }

    return true;
}

/**
 * @brief Cleanup DDS entities
 */
static void Mpu_Subscriber_Cleanup(dds_entity_t * participant)
{
    if (*participant > 0) {
        dds_delete(*participant);
        *participant = 0;
    }
}

int main(int argc, char *argv[])
{
    struct timespec ts;
    struct itimerspec its;
    timer_t timer_id;
    uint64_t time_ns;
    uint64_t time_ns_offset_point;
    uint64_t time_ns_to_start;

    (void)argc;
    (void)argv;

    /* Initialize DDS */
    if (!Mpu_Subscriber_Init(&participant)) {
        fprintf(stderr, "Failed to initialize DDS\n");
        return EXIT_FAILURE;
    }

    printf("Scheduling Application using Timer and Thread\n");

    /* Calculate starting point aligned to hyperperiod */
    if (clock_gettime(CLOCK_REALTIME, &ts)) {
        perror("clock_gettime");
        Mpu_Subscriber_Cleanup(&participant);
        return EXIT_FAILURE;
    }

    time_ns = (uint64_t)ts.tv_sec * GIGA + (uint64_t)ts.tv_nsec;
    time_ns_offset_point = HYPERPERIOD_NS - (time_ns % HYPERPERIOD_NS);
    time_ns_to_start = time_ns + time_ns_offset_point;

    printf("actual time_stamp : %ld.%09ld\n", ts.tv_sec, ts.tv_nsec);
    printf("hyper-period (ms): %llu\n", HYPERPERIOD_NS / 1000000ULL);
    printf("time_ns_offset_point : %llu\n", (unsigned long long)time_ns_offset_point);
    printf("time_ns_to_start :  %llu.%09llu\n", 
           (unsigned long long)(time_ns_to_start / GIGA), 
           (unsigned long long)(time_ns_to_start % GIGA));

    /* Wait for user to press Enter to exit */
    while (getchar() != '\n') {
    }

    /* Cleanup */
    timer_delete(timer_id);
    Mpu_Subscriber_Cleanup(&participant);

    return EXIT_SUCCESS;
}
