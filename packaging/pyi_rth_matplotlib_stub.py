"""Let MediaPipe import without bundling matplotlib.

MediaPipe's drawing helpers import matplotlib at startup. AFK never draws those
overlays, so a stand-in module is enough and the exe stays smaller.
"""

import sys
import types


def _package(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__path__ = []
    module.__package__ = name
    sys.modules[name] = module
    return module


matplotlib = _package("matplotlib")
pyplot = types.ModuleType("matplotlib.pyplot")
pyplot.__package__ = "matplotlib"
sys.modules["matplotlib.pyplot"] = pyplot
matplotlib.pyplot = pyplot
