"""Control a running Noise Filter from another process (command line, scripts, AI agents).

The app listens on a local pipe that only the signed-in Windows user can open (a Unix socket in the
temp folder elsewhere). Each request is one JSON line, each answer one JSON line:

    -> {"cmd": "set", "args": {"strength": 1.2}}
    <- {"ok": true, "result": {...}}      or      {"ok": false, "error": "..."}

This module has no Qt import, so `noise-filter ctl ...` and the MCP server start fast.
"""
from __future__ import annotations

import getpass
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time

# Settings that `set` accepts: name -> (type, min, max, help). The app checks the same table.
PARAMS: dict[str, tuple] = {
    "bypass": (bool, None, None, "pass the microphone through unprocessed"),
    "denoise": (str, None, None, "noise reduction mode: off | spectral | ai"),
    "strength": (float, 0.0, 2.0, "noise reduction strength (1.0 = normal)"),
    "highpass_hz": (float, 0, 300, "high-pass cutoff in Hz (0 = off)"),
    "gate_enabled": (bool, None, None, "noise gate on/off"),
    "gate_threshold_db": (float, -90, -20, "noise gate threshold in dB"),
    "output_gain_db": (float, -20, 20, "output gain in dB"),
    "eq_enabled": (bool, None, None, "equalizer on/off"),
    "comp_enabled": (bool, None, None, "compressor on/off"),
    "comp_threshold_db": (float, -60, 0, "compressor threshold in dB"),
    "comp_ratio": (float, 1.0, 20.0, "compressor ratio (x : 1)"),
    "comp_attack_ms": (float, 1, 100, "compressor attack in ms"),
    "comp_release_ms": (float, 20, 1000, "compressor release in ms"),
    "comp_makeup_db": (float, 0, 24, "compressor makeup gain in dB"),
    "limiter_enabled": (bool, None, None, "limiter on/off"),
    "limiter_ceiling_db": (float, -24, 0, "limiter ceiling in dBFS"),
    "language": (str, None, None, "app language: en | id"),
    "close_to_tray": (bool, None, None, "keep running in the tray when the window is closed"),
    "start_with_windows": (bool, None, None, "open hidden in the tray at Windows sign-in"),
    "resume": (bool, None, None, "turn the filter back on at launch if it was on"),
}
DENOISE_MODES = {"off": "off", "spectral": "spectral", "ai": "onnx", "onnx": "onnx"}

EXIT_OK, EXIT_ERROR, EXIT_NOT_RUNNING = 0, 1, 3


class ControlError(Exception):
    """The app answered with an error (bad value, no device, ...)."""


class NotRunning(ControlError):
    """No Noise Filter is open for this user."""


def server_name() -> str:
    env = os.environ.get("NF_CONTROL_NAME")
    if env:
        return env
    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    return f"SkillsHUB.NoiseFilter.{user}"


def _pipe_path(name: str) -> str:
    # Same addresses QLocalServer uses: \\.\pipe\<name> on Windows, <temp>/<name> on Unix.
    if sys.platform == "win32":
        return r"\\.\pipe" + "\\" + name
    return os.path.join(tempfile.gettempdir(), name)


def parse_value(text: str):
    """Command-line value: true/false, numbers, or text ("on"/"off" stay text; the app reads them
    as switches where a switch is expected, and "off" is also a denoise mode)."""
    if not isinstance(text, str):
        return text
    low = text.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(low) if low.lstrip("+-").isdigit() else float(low)
    except ValueError:
        return text.strip()


def coerce(name: str, value):
    """Check one `set` value against PARAMS. Returns the cleaned value or raises ControlError."""
    if name not in PARAMS:
        raise ControlError(f"unknown setting '{name}'. Valid: {', '.join(PARAMS)}")
    kind, lo, hi, _ = PARAMS[name]
    if kind is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
        if isinstance(value, str) and value.strip().lower() in ("on", "off", "yes", "no", "true", "false"):
            return value.strip().lower() in ("on", "yes", "true")
        raise ControlError(f"{name} must be true or false")
    if kind is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ControlError(f"{name} must be a number between {lo} and {hi}")
        if not lo <= value <= hi:
            raise ControlError(f"{name} must be between {lo} and {hi} (got {value})")
        return float(value)
    value = str(value).strip().lower()
    if name == "denoise":
        if value not in DENOISE_MODES:
            raise ControlError("denoise must be off, spectral or ai")
        return DENOISE_MODES[value]
    if name == "language" and value not in ("en", "id"):
        raise ControlError("language must be en or id")
    return value


def _exchange_windows(path: str, data: bytes, deadline: float) -> bytes:
    while True:
        try:
            f = open(path, "r+b", buffering=0)
            break
        except FileNotFoundError:
            raise NotRunning("Noise Filter is not running")
        except OSError as e:            # ERROR_PIPE_BUSY: the app is opening the next pipe instance
            if time.monotonic() > deadline:
                raise ControlError(f"Noise Filter did not accept the connection: {e}")
            time.sleep(0.05)
    with f:
        f.write(data)
        out = b""
        while not out.endswith(b"\n"):
            chunk = f.read(65536)
            if not chunk:
                break
            out += chunk
        return out


def _exchange_unix(path: str, data: bytes, deadline: float) -> bytes:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(max(0.1, deadline - time.monotonic()))
    try:
        s.connect(path)
    except (FileNotFoundError, ConnectionRefusedError):
        s.close()
        raise NotRunning("Noise Filter is not running")
    with s:
        s.sendall(data)
        out = b""
        while not out.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            out += chunk
        return out


def request(cmd: str, timeout: float = 10.0, **args):
    """Send one command to the running app and return its result. Raises NotRunning / ControlError."""
    path = _pipe_path(server_name())
    data = (json.dumps({"cmd": cmd, "args": args}) + "\n").encode("utf-8")
    deadline = time.monotonic() + timeout
    box: dict = {}

    def work():
        try:
            fn = _exchange_windows if sys.platform == "win32" else _exchange_unix
            box["out"] = fn(path, data, deadline)
        except BaseException as e:      # handed to the caller's thread
            box["err"] = e

    t = threading.Thread(target=work, daemon=True, name="nf-remote")
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise ControlError(f"Noise Filter did not answer within {timeout:.0f} s")
    if "err" in box:
        e = box["err"]
        if isinstance(e, ControlError):
            raise e
        raise ControlError(f"connection failed: {e}") from e
    raw = box.get("out", b"").strip()
    if not raw:
        raise ControlError("Noise Filter closed the connection without an answer")
    reply = json.loads(raw.decode("utf-8"))
    if not reply.get("ok"):
        raise ControlError(reply.get("error", "unknown error"))
    return reply.get("result")


def is_running() -> bool:
    try:
        request("ping", timeout=2.0)
        return True
    except ControlError:
        return False


def launch_command() -> list[str]:
    """How to open the app hidden in the tray: the frozen NoiseFilter.exe next to this program, or Python."""
    if getattr(sys, "frozen", False):
        exe = os.path.join(os.path.dirname(sys.executable), "NoiseFilter.exe")
        return [exe, "ui", "--minimized"]
    return [sys.executable, "-m", "noise_filter.cli", "ui", "--minimized"]


def launch(wait: float = 20.0) -> bool:
    """Open the app (hidden in the tray) if it is not running and wait until it answers.
    Returns True if it was started now, False if it was already running."""
    if is_running():
        return False
    kw: dict = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen(launch_command(), **kw)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        time.sleep(0.3)
        if is_running():
            return True
    raise ControlError(f"Noise Filter did not start within {wait:.0f} s")
