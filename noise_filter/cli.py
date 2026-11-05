import argparse
import sys
import numpy as np
from .core import Pipeline, PipelineConfig, FRAME_SIZE, FRAME_MS


def main(argv=None):
    ap = argparse.ArgumentParser(prog="noise-filter")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("devices", help="list input/output devices (WASAPI)")
    ui = sub.add_parser("ui", help="open the graphical interface")
    ui.add_argument("--demo", action="store_true", help="synthetic input signal (no audio device needed)")
    run = sub.add_parser("run", help="live: input device -> filter -> output device")
    run.add_argument("--in", dest="indev", type=int, required=True)
    run.add_argument("--out", dest="outdev", type=int, required=True)
    run.add_argument("--exclusive", action="store_true", help="WASAPI exclusive mode (lowest latency)")
    run.add_argument("--bypass", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "ui":
        from .ui.app import run as run_ui
        return run_ui(demo=a.demo)

    if a.cmd == "devices":
        from .audio.devices import list_devices
        for kind in ("input", "output"):
            print(f"[{kind}]")
            for d in list_devices(kind):
                print(f"  {d.index:3d}  {d.name}{'  (default)' if d.is_default else ''}")
        return 0

    from .audio.engine import Engine
    pipe = Pipeline(PipelineConfig(bypass=a.bypass))
    eng = Engine(pipe, a.indev, a.outdev, exclusive=a.exclusive)
    print(f"Running. frame={FRAME_SIZE} samples ({FRAME_MS:.1f} ms). Ctrl+C to stop.")
    eng.start()
    try:
        while True:
            import time; time.sleep(1)
    except KeyboardInterrupt:
        eng.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
