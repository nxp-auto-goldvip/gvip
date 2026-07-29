# -------------------------------------------------------------------------------------------------
#
# CMake toolchain file for cross-compiling to aarch64 (64-bit ARM) Linux targets
# using the Arm GNU Toolchain (aarch64-none-linux-gnu).
#
# This file configures CMake to use the Linux cross-compiler hosted on an x86-64
# build machine and to locate pre-built sysroot headers, libraries, and
# staging artifacts provided by the MotionWise Communication middleware.
#
# Build command
#   cmake -DCMAKE_TOOLCHAIN_FILE=... ..
#
# Copyright 2026 NXP
#
# -------------------------------------------------------------------------------------------------

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

# -------------------------------------------------------------------------------------------------
# Configurable paths
#   export TOOLCHAIN_ROOT=/opt/gcc-arm-10.2-...
#   export ZETTAAUTO_ROOT=/path/to/folder/ZettaAuto/
# -------------------------------------------------------------------------------------------------
if(DEFINED ENV{TOOLCHAIN_ROOT})
    set(TOOLCHAIN_ROOT $ENV{TOOLCHAIN_ROOT})
elseif(NOT TOOLCHAIN_ROOT)
    set(TOOLCHAIN_ROOT /root/gcc-arm-10.2-2020.11-x86_64-aarch64-none-linux-gnu)
endif()

if(DEFINED ENV{ZETTAAUTO_ROOT})
    set(ZETTAAUTO_ROOT $ENV{ZETTAAUTO_ROOT})
elseif(NOT ZETTAAUTO_ROOT)
    set(ZETTAAUTO_ROOT ${TOOLCHAIN_ROOT}/stage)
endif()
# -------------------------------------------------------------------------------------------------

get_filename_component(TOOLCHAIN_ROOT ${TOOLCHAIN_ROOT} ABSOLUTE)

set(CMAKE_STAGING_PREFIX  ${ZETTAAUTO_ROOT}/MPU/linux-prebuilt/aarch64)
set(CMAKE_FIND_ROOT_PATH  ${ZETTAAUTO_ROOT}/MPU/linux-prebuilt/aarch64)
set(CMAKE_SYSROOT         ${TOOLCHAIN_ROOT}/aarch64-none-linux-gnu/libc)

set(CMAKE_LIBRARY_ARCHITECTURE ${TOOLCHAIN_ROOT}/bin/aarch64-none-linux-gnu)

set(CMAKE_ADDR2LINE        ${CMAKE_LIBRARY_ARCHITECTURE}-addr2line)
set(CMAKE_AR               ${CMAKE_LIBRARY_ARCHITECTURE}-ar)
set(CMAKE_CXX_COMPILER     ${CMAKE_LIBRARY_ARCHITECTURE}-g++)
set(CMAKE_CXX_COMPILER_AR  ${CMAKE_LIBRARY_ARCHITECTURE}-gcc-ar)
set(CMAKE_CXX_COMPILER_RANLIB ${CMAKE_LIBRARY_ARCHITECTURE}-gcc-ranlib)
set(CMAKE_C_COMPILER       ${CMAKE_LIBRARY_ARCHITECTURE}-gcc)
set(CMAKE_C_COMPILER_AR    ${CMAKE_LIBRARY_ARCHITECTURE}-gcc-ar)
set(CMAKE_C_COMPILER_RANLIB ${CMAKE_LIBRARY_ARCHITECTURE}-gcc-ranlib)
set(CMAKE_LINKER           ${CMAKE_LIBRARY_ARCHITECTURE}-ld)
set(CMAKE_NM               ${CMAKE_LIBRARY_ARCHITECTURE}-nm)
set(CMAKE_OBJCOPY          ${CMAKE_LIBRARY_ARCHITECTURE}-objcopy)
set(CMAKE_OBJDUMP          ${CMAKE_LIBRARY_ARCHITECTURE}-objdump)
set(CMAKE_RANLIB           ${CMAKE_LIBRARY_ARCHITECTURE}-ranlib)
set(CMAKE_STRIP            ${CMAKE_LIBRARY_ARCHITECTURE}-strip)

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)

# Add HOST_TOOLS_BIN to the program search path so idlc is found
list(APPEND CMAKE_PROGRAM_PATH ${ZETTAAUTO_ROOT}/MPU/linux-prebuilt/x86_64/bin)

# Search path for additional dependencies
set(TINYXML2_INCLUDE_DIR ${CMAKE_STAGING_PREFIX}/include)

include_directories(${TOOLCHAIN_ROOT}/aarch64-none-linux-gnu/include/c++/10.2.1/aarch64-none-linux-gnu)
include_directories(${TOOLCHAIN_ROOT}/aarch64-none-linux-gnu/include/c++/10.2.1)