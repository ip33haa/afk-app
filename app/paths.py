"""Filesystem locations and the credential-provider id."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROVIDER_CLSID = "{7C2E9A14-6B3F-4F0A-9E21-4D8B5C6A1F30}"
PIPE_NAME = r"\\.\pipe\AFKPresenceLock"

YUNET_NAME = "face_detection_yunet_2023mar.onnx"
SFACE_NAME = "face_recognition_sface_2021dec.onnx"
LANDMARKER_NAME = "face_landmarker.task"

YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
SFACE_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_recognition_sface/face_recognition_sface_2021dec.onnx"
)
LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def models_dir() -> Path:
    if is_frozen():
        bundled = Path(getattr(sys, "_MEIPASS", project_root())) / "models"
        if bundled.is_dir():
            return bundled
    return project_root() / "models"


def model_path(name: str) -> Path:
    return models_dir() / name


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / "AFK"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pythonw_path() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve()
    venv_pythonw = project_root() / ".venv" / "Scripts" / "pythonw.exe"
    if venv_pythonw.exists():
        return venv_pythonw
    current = Path(sys.executable)
    sibling = current.with_name("pythonw.exe")
    if sibling.exists():
        return sibling
    return current


def startup_cmd_path() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return (
        Path(appdata)
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
        / "AFK.cmd"
    )


def credential_provider_registered() -> bool:
    import winreg

    key = (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication"
        rf"\Credential Providers\{PROVIDER_CLSID}"
    )
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key):
            return True
    except OSError:
        return False
