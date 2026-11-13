cmake_minimum_required(VERSION 3.16)
project(nf_core VERSION 0.2.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_VISIBILITY_PRESET hidden)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

option(NF_WITH_ONNX "Build the ONNX Runtime denoiser (needs ONNXRUNTIME_DIR)" OFF)
option(NF_BUILD_TESTS "Build the C++ tests" ON)
option(NF_BUILD_CLI "Build the nf-cli tool" ON)
set(ONNXRUNTIME_DIR "" CACHE PATH "Extracted onnxruntime release (has include/ and lib/)")

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release)
endif()

set(NF_SOURCES
  src/dsp.cpp
  src/eq.cpp
  src/dynamics.cpp
  src/pipeline.cpp
  src/onnx_denoiser.cpp
  src/capi.cpp
  src/engine_wasapi.cpp
  src/engine_stub.cpp)

# Static library: used by the CLI and the tests.
add_library(nf_static STATIC ${NF_SOURCES})
# Shared library: loaded by the Python app (ctypes) and later Flutter (dart:ffi).
add_library(nf_core SHARED ${NF_SOURCES})
target_compile_definitions(nf_core PRIVATE NF_BUILD_SHARED)
if(WIN32)
  set_target_properties(nf_core PROPERTIES PREFIX "")  # nf_core.dll with MSVC and MinGW alike
  # Ship one self-contained DLL (no MinGW / VC++ runtime DLLs needed next to it).
  if(MSVC)
    set_property(TARGET nf_core nf_static PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  else()
    target_link_options(nf_core PRIVATE -static -static-libgcc -static-libstdc++)
  endif()
endif()

foreach(t nf_static nf_core)
  target_include_directories(${t} PUBLIC include PRIVATE src third_party/pocketfft)
  if(MSVC)
    target_compile_options(${t} PRIVATE /W3 /fp:fast /O2)
  else()
    target_compile_options(${t} PRIVATE -Wall -Wextra -O2)
  endif()
  if(WIN32)
    target_link_libraries(${t} PUBLIC ole32 avrt uuid)
  endif()
  if(NF_WITH_ONNX)
    target_compile_definitions(${t} PRIVATE NF_WITH_ONNX)
    target_include_directories(${t} PRIVATE ${ONNXRUNTIME_DIR}/include)
    find_library(ORT_LIB NAMES onnxruntime PATHS ${ONNXRUNTIME_DIR}/lib NO_DEFAULT_PATH REQUIRED)
    target_link_libraries(${t} PUBLIC ${ORT_LIB})
  endif()
endforeach()

if(NF_BUILD_CLI)
  add_executable(nf-cli tools/nf_cli.cpp)
  target_link_libraries(nf-cli PRIVATE nf_static)
  if(WIN32 AND NOT MSVC)
    target_link_options(nf-cli PRIVATE -static)
  elseif(MSVC)
    set_property(TARGET nf-cli PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  endif()
endif()

if(NF_BUILD_TESTS)
  enable_testing()
  add_executable(nf_tests tests/test_core.cpp)
  target_link_libraries(nf_tests PRIVATE nf_static)
  target_include_directories(nf_tests PRIVATE src)
  if(MSVC)
    set_property(TARGET nf_tests PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  endif()
  add_test(NAME nf_tests COMMAND nf_tests)
endif()

# `cmake --install build` copies the DLL next to the Python package so the app picks it up.
install(TARGETS nf_core
  RUNTIME DESTINATION ${CMAKE_CURRENT_SOURCE_DIR}/../noise_filter/_native
  LIBRARY DESTINATION ${CMAKE_CURRENT_SOURCE_DIR}/../noise_filter/_native)
if(NF_BUILD_CLI)
  install(TARGETS nf-cli RUNTIME DESTINATION ${CMAKE_CURRENT_SOURCE_DIR}/../noise_filter/_native)
endif()
