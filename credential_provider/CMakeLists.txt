cmake_minimum_required(VERSION 3.20)
project(FaceUnlockCP LANGUAGES CXX)

add_library(FaceUnlockCP SHARED
    src/dllmain.cpp
    src/Provider.cpp
    src/Credential.cpp
    src/PipeServer.cpp
    src/helpers.cpp
    FaceUnlockCP.def
)

target_compile_features(FaceUnlockCP PRIVATE cxx_std_17)
target_compile_definitions(FaceUnlockCP PRIVATE
    UNICODE
    _UNICODE
    _CRT_SECURE_NO_WARNINGS
    WIN32_LEAN_AND_MEAN
    NOMINMAX
)
target_include_directories(FaceUnlockCP PRIVATE src)

if(MSVC)
    target_compile_options(FaceUnlockCP PRIVATE /W4 /EHsc /permissive-)
    set_property(TARGET FaceUnlockCP PROPERTY
        MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()

target_link_libraries(FaceUnlockCP PRIVATE
    ole32
    advapi32
    secur32
    shlwapi
    user32
    gdi32
    wtsapi32
    bcrypt
)
