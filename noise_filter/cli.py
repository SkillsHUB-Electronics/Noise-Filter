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
    st = sub.add_parser("selftest", help="check the C++ core and i18n load (used by the installer build)")
    st.add_argument("--out", help="write the report to this file instead of stdout")
    a = ap.parse_args(argv)

    if a.cmd == "selftest":
        return selftest(a.out)

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


def selftest(out_path=None) -> int:
    from .core import native
    from .i18n import tr
    lines, ok = [], True
    pipe = native.create_pipeline()
    is_native = getattr(pipe, "native", False)
    lines.append(f"native: {is_native} {native.last_error() if not is_native else ''}".strip())
    y = pipe.process(np.zeros(FRAME_SIZE, np.float32))
    lines.append(f"process: {y.shape == (FRAME_SIZE,)}")
    lines.append(f"i18n: {tr('engine.start', 'id')}")
    ok = is_native and y.shape == (FRAME_SIZE,) and tr("engine.start", "id") != "engine.start"
    lines.append("OK" if ok else "FAILED")
    text = "\n".join(lines) + "\n"
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
    elif sys.stdout:
        sys.stdout.write(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
