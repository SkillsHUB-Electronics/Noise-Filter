# Command line and AI control

The running app can be controlled from a terminal, a script or an AI assistant. The installer adds
`nfctl.exe` (a console companion of `NoiseFilter.exe`) and can put it on `PATH`. From source, the
same commands are `noise-filter ctl …`.

## Commands

Every command prints JSON. Exit code `0` = ok, `1` = error, `3` = the app is not running.

```powershell
nfctl status                                   # on/off, devices, every setting, levels, latency
nfctl start                                    # opens the app in the tray first if needed
nfctl stop
nfctl set strength=1.3 highpass_hz=100 denoise=ai gate_enabled=off
nfctl set vocal_mode=on mix=0.8                # singing: keep harmonics, blend in 20 % original
nfctl devices
nfctl device --input "USB" --output "CABLE Input" [--exclusive | --shared]
nfctl presets                                  # list EQ presets
nfctl preset voice_clarity hum_50              # tick these presets (merged into one EQ)
nfctl preset --clear
nfctl learn                                    # learn room noise for 3 s (filter on, stay quiet)
nfctl launch | show | hide | quit
nfctl help                                     # every setting with its range
```

Changes made by command go through the same controls as the window, so the window, the tray and
the saved settings always match. While the EQ presets are locked, `preset` is refused and `status`
reports `eq_locked`.

## MCP server for AI apps

`nfctl mcp` speaks the [Model Context Protocol](https://modelcontextprotocol.io) over stdio with
these tools: `get_status`, `start_filter`, `stop_filter`, `set_settings`, `list_devices`,
`select_devices`, `list_eq_presets`, `set_eq_presets`, `learn_noise`, `show_window`, `hide_window`,
`quit_app`.

In the app, **Settings › Command line & AI control › Copy MCP setting** copies the entry for you.

Claude Desktop (`claude_desktop_config.json`):

```json
{"mcpServers": {"noise-filter": {"command": "C:\\Program Files\\Noise Filter\\nfctl.exe", "args": ["mcp"]}}}
```

Claude Code:

```powershell
claude mcp add noise-filter -- "C:\Program Files\Noise Filter\nfctl.exe" mcp
```

## How it works

The app listens on a local named pipe, `\\.\pipe\SkillsHUB.NoiseFilter.<user>`, that only the
signed-in Windows user can open. Nothing listens on the network. Each request and answer is one
JSON line:

```text
{"cmd": "set", "args": {"strength": 1.2}}   ->   {"ok": true, "result": {...}}
```

The implementation is in [`noise_filter/remote.py`](../noise_filter/remote.py) (protocol),
[`noise_filter/ctl.py`](../noise_filter/ctl.py) (command line) and
[`noise_filter/mcp_server.py`](../noise_filter/mcp_server.py) (MCP).
