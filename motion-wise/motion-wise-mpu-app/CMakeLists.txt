# INVOKE (no idlc - use pre-generated Topics.c):
#   cmake -DCMAKE_TOOLCHAIN_FILE=../toolchain_aarch64-none-linux-gnu.cmake ..
#   make
#
# INVOKE (with idlc - generate Topics.c from IDL at build time):
#   cmake -DUSE_IDLC=ON -DCMAKE_TOOLCHAIN_FILE=../toolchain_aarch64-none-linux-gnu.cmake ..
#   make

cmake_minimum_required(VERSION 3.5 FATAL_ERROR)

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

set(Topics_DIR topics)

option(USE_IDLC "Generate Topics.c from IDL using idlc at build time" OFF)

if(USE_IDLC)
  # Generate C code from IDL at build time
  idlc_generate(TARGET types_c FILES ${Topics_DIR}/Topics.idl WARNINGS no-implicit-extensibility)
  set(AllSources motion-wise-mpu-app.c)
else()
  # Use pre-generated Topics.c (no idlc dependency)
  set(AllSources motion-wise-mpu-app.c ${Topics_DIR}/Topics.c)
endif()

add_executable(motion-wise-mpu-app ${AllSources})

target_include_directories(motion-wise-mpu-app PRIVATE ${Topics_DIR})

if((CMAKE_SYSTEM_NAME STREQUAL "QNX") AND (${ETHTSP_IOSOCK}))
  list(PREPEND LD_LIBRARY_PATH "$ENV{QNX_TARGET}/${CMAKE_SYSTEM_PROCESSOR}/io-sock/lib")
endif()

set(DDSLibs CycloneDDS::ddsc)
if(USE_IDLC)
  list(APPEND DDSLibs types_c)
endif()

target_link_libraries(motion-wise-mpu-app LINK_PUBLIC ${DDSLibs} rt pthread)
