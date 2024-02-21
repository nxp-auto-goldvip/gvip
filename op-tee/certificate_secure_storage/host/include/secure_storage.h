/*
 * Copyright 2024 NXP
 */

#ifndef __SECURE_STORAGE_H__
#define __SECURE_STORAGE_H__

#define OBJECT_SIZE     2000

#define PUT "PUT"
#define GET "GET"

#define OK "OK"
#define NOT_FOUND "NOT_FOUND"

#define HELP "\n\
Usage: cmd PUT OBJECT_ID OBJECT_DATA\n\
   or: cmd GET OBJECT_ID\n\
\n\
Put response: FOUND\n\
          or: error_message\n\
\n\
Get response: FOUND OBJECT_ID OBJECT_DATA\n\
          or: NOT_FOUND\n\
          or: error_message \n\
"

#ifdef _MSC_VER
    #define EXPORT_SYMBOL __declspec(dllexport)
#else
    #define EXPORT_SYMBOL
#endif

EXPORT_SYMBOL const int buffer_len;

EXPORT_SYMBOL int rpmb_get(const char *key, const char *data);
EXPORT_SYMBOL int rpmb_put(const char *key, const char *data);

#endif /* __SECURE_STORAGE_H__ */
