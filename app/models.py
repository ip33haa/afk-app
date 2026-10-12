"""Download the face models used by AFK. Run: python -m app.models"""

from __future__ import annotations

import urllib.request

from app.paths import (
    LANDMARKER_NAME,
    LANDMARKER_URL,
    SFACE_NAME,
    SFACE_URL,
    YUNET_NAME,
    YUNET_URL,
    model_path,
    models_dir,
)

_FILES = (
    (YUNET_NAME, YUNET_URL, 100_000),
    (SFACE_NAME, SFACE_URL, 1_000_000),
    (LANDMARKER_NAME, LANDMARKER_URL, 100_000),
)


def download() -> None:
    models_dir().mkdir(parents=True, exist_ok=True)
    for name, url, minimum in _FILES:
        path = model_path(name)
        if path.exists() and path.stat().st_size >= minimum:
            print(f"already present: {name}")
            continue
        print(f"downloading {name}")
        urllib.request.urlretrieve(url, path)
        if path.stat().st_size < minimum:
            raise RuntimeError(f"{name} download looks incomplete")
        print(f"saved {path}")


if __name__ == "__main__":
    download()
