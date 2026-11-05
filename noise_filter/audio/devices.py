"""Windows audio device discovery (WASAPI preferred). Requires `sounddevice`."""
from dataclasses import dataclass


@dataclass
class Device:
    index: int
    name: str
    hostapi: str
    channels: int
    default_rate: float
    is_default: bool = False


def _sd():
    import sounddevice as sd
    return sd


def list_devices(kind: str = "input", hostapi: str = "Windows WASAPI") -> list[Device]:
    """kind: 'input' or 'output'. Re-call to pick up plugged/unplugged devices
    (call sd._terminate(); sd._initialize() first for a hot refresh)."""
    sd = _sd()
    apis = sd.query_hostapis()
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    default_idx = sd.default.device[0 if kind == "input" else 1]
    out = []
    for i, d in enumerate(sd.query_devices()):
        api = apis[d["hostapi"]]["name"]
        if d[key] > 0 and (hostapi is None or api == hostapi):
            out.append(Device(i, d["name"], api, d[key], d["default_samplerate"], i == default_idx))
    return out


def refresh():
    sd = _sd()
    sd._terminate()
    sd._initialize()
