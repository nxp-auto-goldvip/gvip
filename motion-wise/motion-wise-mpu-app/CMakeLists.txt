# INVOKE:
# cmake -DCMAKE_TOOLCHAIN_FILE=../toolchain_aarch64-none-linux-gnu.cmake ..
# make

# set minimum cmake version
cmake_minimum_required(VERSION 3.5 FATAL_ERROR)

# project name - using C language
project(motion-wise-mpu-app C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_C_STANDARD_REQUIRED ON)

if(ENABLE_LEGACY)
  set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -v")
endif()

# CycloneDDS C install dir (not the C++ bindings)
if(NOT TARGET CycloneDDS::ddsc)
  find_package(CycloneDDS REQUIRED)
endif()

# CycloneDDS generated code for C
set(Topics_DIR topics)

# For other platforms, use idlc to generate C code from IDL
idlc_generate(TARGET types_c FILES ${Topics_DIR}/Topics.idl WARNINGS no-implicit-extensibility)

# Define sources
set(AllSources motion-wise-mpu-app.c)

# Define executable and its source file
add_executable(motion-wise-mpu-app ${AllSources})

# Include directories
target_include_directories(motion-wise-mpu-app PRIVATE ${Topics_DIR})

if ((CMAKE_SYSTEM_NAME STREQUAL "QNX") AND (${ETHTSP_IOSOCK}) )
  list (PREPEND LD_LIBRARY_PATH "$ENV{QNX_TARGET}/${CMAKE_SYSTEM_PROCESSOR}/io-sock/lib")
endif()

# DDS libraries - using C library (ddsc) not C++ (ddscxx)
set(DDSLibs CycloneDDS::ddsc)
list(APPEND DDSLibs types_c)

target_link_libraries(motion-wise-mpu-app LINK_PUBLIC ${DDSLibs} rt pthread)
