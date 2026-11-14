"""`noise-filter ctl ...`: control the running app from a terminal, a script or an AI agent.

Every command prints JSON on stdout. Exit codes: 0 ok, 1 error, 3 the app is not running.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from . import remote

EXAMPLES = """examples:
  nfctl status
  nfctl start                      (opens the app in the tray first if needed)
  nfctl set strength=1.3 highpass_hz=100 denoise=ai
  nfctl devices
  nfctl device --input "USB" --output "CABLE Input"
  nfctl preset voice_clarity hum_50
  nfctl preset --clear
  nfctl learn
  nfctl stop
"""


def add_parser(sub) -> None:
    p = sub.add_parser("ctl", help="control the running app (JSON output, for scripts and AI agents)",
                       description=__doc__, epilog=EXAMPLES, formatter_class=argparse.RawDescriptionHelpFormatter)
    fill(p)


def fill(p: argparse.ArgumentParser) -> None:
    c = p.add_subparsers(dest="action", required=True, metavar="COMMAND")
    c.add_parser("status", help="filter on/off, devices, every setting, levels and latency")
    c.add_parser("start", help="turn the filter on (opens the app in the tray first if needed)")
    c.add_parser("stop", help="turn the filter off (the app keeps running)")
    s = c.add_parser("set", help="change settings: name=value ...  (see 'help' for names and ranges)")
    s.add_argument("pairs", nargs="+", metavar="NAME=VALUE")
    d = c.add_parser("devices", help="list input and output devices")
    d.add_argument("--refresh", action="store_true", help="scan for new devices first (filter must be off)")
    dv = c.add_parser("device", help="choose devices by name (or part of it) or id")
    dv.add_argument("--input"); dv.add_argument("--output")
    g = dv.add_mutually_exclusive_group()
    g.add_argument("--exclusive", dest="exclusive", action="store_true", default=None, help="WASAPI exclusive mode")
    g.add_argument("--shared", dest="exclusive", action="store_false", help="WASAPI shared mode")
    c.add_parser("presets", help="list EQ presets")
    pr = c.add_parser("preset", help="tick EQ presets (merged into one curve)")
    pr.add_argument("names", nargs="*")
    pr.add_argument("--clear", action="store_true", help="untick all presets")
    ln = c.add_parser("learn", help="learn the room noise for 3 s (be quiet); the filter must be on")
    ln.add_argument("--no-wait", action="store_true", help="return at once instead of after 3 s")
    c.add_parser("launch", help="open the app hidden in the tray if it is not running")
    c.add_parser("show", help="show the window"); c.add_parser("hide", help="hide the window to the tray")
    c.add_parser("quit", help="close the app")
    c.add_parser("help", help="commands and every setting with its range")
    c.add_parser("mcp-config", help="print the MCP server entry for Claude Desktop / other AI apps")


def mcp_config() -> dict:
    if getattr(sys, "frozen", False):
        import os
        cmd, args = os.path.join(os.path.dirname(sys.executable), "nfctl.exe"), ["mcp"]
    else:
        cmd, args = sys.executable, ["-m", "noise_filter.cli", "mcp"]
    return {"mcpServers": {"noise-filter": {"command": cmd, "args": args}}}


def run(a) -> int:
    try:
        result = _do(a)
        code = remote.EXIT_OK
        out = {"ok": True, "result": result}
    except remote.NotRunning as e:
        code, out = remote.EXIT_NOT_RUNNING, {"ok": False, "error": f"{e}. Run 'start' or 'launch' first."}
    except remote.ControlError as e:
        code, out = remote.EXIT_ERROR, {"ok": False, "error": str(e)}
    text = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    try:
        sys.stdout.buffer.write(text.encode("utf-8")); sys.stdout.flush()
    except AttributeError:          # no console (windowed exe): nothing to print to
        pass
    return code


def _do(a):
    act = a.action
    if act == "mcp-config":
        return mcp_config()
    if act == "help":                   # works without the app
        return {"commands": ["status", "start", "stop", "set", "devices", "device", "presets", "preset", "learn",
                             "launch", "show", "hide", "quit", "mcp-config"],
                "settings": {k: {"type": v[0].__name__, "min": v[1], "max": v[2], "help": v[3]}
                             for k, v in remote.PARAMS.items()}}
    if act == "launch":
        started = remote.launch()
        return {"started": started, "already_running": not started}
    if act == "start":
        remote.launch()
        return remote.request("start")
    if act == "set":
        values = {}
        for pair in a.pairs:
            name, eq, value = pair.partition("=")
            if not eq:
                raise remote.ControlError(f"'{pair}' is not NAME=VALUE")
            values[name.strip()] = remote.parse_value(value)
        return remote.request("set", **values)
    if act == "devices":
        return remote.request("devices", refresh=a.refresh)
    if act == "device":
        if a.input is None and a.output is None and a.exclusive is None:
            raise remote.ControlError("give --input, --output, --exclusive or --shared")
        return remote.request("select_devices", input=a.input, output=a.output, exclusive=a.exclusive)
    if act == "presets":
        return remote.request("eq_presets")
    if act == "preset":
        if not a.names and not a.clear:
            raise remote.ControlError("give preset names, or --clear")
        return remote.request("set_eq_presets", presets=[] if a.clear else a.names)
    if act == "learn":
        r = remote.request("learn_noise")
        if a.no_wait:
            return r
        time.sleep(r.get("seconds", 3) + 0.4)
        return {"learned": True, "seconds": r.get("seconds", 3)}
    names = {"status": "status", "stop": "stop", "show": "show", "hide": "hide", "quit": "quit"}
    return remote.request(names[act])
