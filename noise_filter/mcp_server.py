"""MCP server (stdio) so AI apps can control Noise Filter: `nfctl mcp` / `noise-filter mcp`.

Speaks the Model Context Protocol's JSON-RPC over stdin/stdout (one message per line) with no extra
dependency. Each tool forwards to the running app through noise_filter.remote.
"""
from __future__ import annotations

import json
import sys
import time

from . import __version__, remote

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

INSTRUCTIONS = (
    "Noise Filter cleans the user's microphone in real time on this Windows PC and sends it to a virtual "
    "microphone (VB-CABLE: apps should use 'CABLE Output' as their mic). Use get_status first. start_filter "
    "opens the app if needed. Settings change live; to learn the room noise ask the user to stay quiet, then "
    "call learn_noise.")


def _setting_schema() -> dict:
    props = {}
    for name, (kind, lo, hi, help_) in remote.PARAMS.items():
        if kind is bool:
            props[name] = {"type": "boolean", "description": help_}
        elif kind is float:
            props[name] = {"type": "number", "minimum": lo, "maximum": hi, "description": help_}
        elif name == "denoise":
            props[name] = {"type": "string", "enum": ["off", "spectral", "ai"], "description": help_}
        elif name == "language":
            props[name] = {"type": "string", "enum": ["en", "id"], "description": help_}
    return {"type": "object", "properties": props, "additionalProperties": False}


EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}
TOOLS = [
    ("get_status", "Is the filter on, which devices, every setting, EQ presets, levels and latency.", EMPTY),
    ("start_filter", "Turn the noise filter on (opens the app hidden in the tray if it is not running).", EMPTY),
    ("stop_filter", "Turn the noise filter off. The app keeps running in the tray.", EMPTY),
    ("set_settings", "Change one or more filter settings live. Only pass what should change.", _setting_schema()),
    ("list_devices", "List microphones (input) and output devices; the output should be 'CABLE Input'.",
     {"type": "object", "properties": {"refresh": {"type": "boolean", "description": "scan for new devices (filter must be off)"}},
      "additionalProperties": False}),
    ("select_devices", "Choose the input and/or output device by name (or part of it) or id. A running filter restarts.",
     {"type": "object", "properties": {"input": {"type": "string"}, "output": {"type": "string"},
                                       "exclusive": {"type": "boolean", "description": "WASAPI exclusive mode (lowest latency)"}},
      "additionalProperties": False}),
    ("list_eq_presets", "List the equalizer presets (built-in and the user's own) and which are ticked.", EMPTY),
    ("set_eq_presets", "Tick exactly these EQ presets (merged into one curve, max 8 bands). Empty list clears them.",
     {"type": "object", "properties": {"presets": {"type": "array", "items": {"type": "string"},
                                                   "description": "preset ids or names, e.g. voice_clarity, hum_50, podcast"}},
      "required": ["presets"], "additionalProperties": False}),
    ("learn_noise", "Learn the room noise for 3 seconds from the live microphone. The user must be quiet. Filter must be on.", EMPTY),
    ("show_window", "Show the Noise Filter window.", EMPTY),
    ("hide_window", "Hide the window to the system tray (the filter keeps running).", EMPTY),
    ("quit_app", "Close Noise Filter completely (the virtual mic goes silent).", EMPTY),
]


def call_tool(name: str, args: dict):
    if name == "get_status":
        return remote.request("status")
    if name == "start_filter":
        remote.launch()
        return remote.request("start")
    if name == "stop_filter":
        return remote.request("stop")
    if name == "set_settings":
        return remote.request("set", **args)
    if name == "list_devices":
        return remote.request("devices", refresh=bool(args.get("refresh", False)))
    if name == "select_devices":
        return remote.request("select_devices", **{k: args.get(k) for k in ("input", "output", "exclusive")})
    if name == "list_eq_presets":
        return remote.request("eq_presets")
    if name == "set_eq_presets":
        return remote.request("set_eq_presets", presets=args.get("presets", []))
    if name == "learn_noise":
        r = remote.request("learn_noise")
        time.sleep(r.get("seconds", 3) + 0.4)
        return {"learned": True, "seconds": r.get("seconds", 3)}
    if name == "show_window":
        return remote.request("show")
    if name == "hide_window":
        return remote.request("hide")
    if name == "quit_app":
        return remote.request("quit")
    raise KeyError(name)


def handle(msg: dict) -> dict | None:
    """One JSON-RPC message in, the reply out (None for notifications)."""
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:
        return None                              # notifications/initialized, cancelled, ...
    ok = lambda result: {"jsonrpc": "2.0", "id": mid, "result": result}
    if method == "initialize":
        asked = params.get("protocolVersion")
        return ok({"protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                   "capabilities": {"tools": {}},
                   "serverInfo": {"name": "noise-filter", "version": __version__},
                   "instructions": INSTRUCTIONS})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": [{"name": n, "description": d, "inputSchema": s} for n, d, s in TOOLS]})
    if method == "tools/call":
        name = params.get("name")
        if name not in {t[0] for t in TOOLS}:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
        try:
            result = call_tool(name, params.get("arguments") or {})
            return ok({"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=1)}],
                       "isError": False})
        except remote.NotRunning:
            text = "Noise Filter is not running. Call start_filter to open it."
        except remote.ControlError as e:
            text = str(e)
        return ok({"content": [{"type": "text", "text": text}], "isError": True})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            reply = handle(msg) if isinstance(msg, dict) else None
        if reply is not None:
            stdout.write((json.dumps(reply, ensure_ascii=False) + "\n").encode("utf-8"))
            stdout.flush()
    return 0
