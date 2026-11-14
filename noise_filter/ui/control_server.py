"""Local control channel of the running app (see noise_filter.remote for the protocol).

Every command goes through the same widgets a person would use, so the window, the tray, the saved
settings and the audio pipeline always agree.
"""
from __future__ import annotations

import json

from PySide6 import QtCore
from PySide6.QtNetwork import QLocalServer

from .. import __version__, model_update
from ..core import eq
from ..i18n import tr
from ..remote import PARAMS, ControlError, coerce
from .dynamics_panel import COMP_PARAMS, LIM_PARAMS

MODES = ["off", "spectral", "onnx"]


def listen(name: str, window) -> QLocalServer:
    """Serve control requests for `window`. A plain "show" line (sent by a second copy of the app) shows it."""
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)   # only this Windows user may connect
    if not server.listen(name):          # stale socket after a crash (Unix)
        QLocalServer.removeServer(name)
        server.listen(name)
    ctl = Controller(window)
    server._controller = ctl             # keep alive with the server

    def serve(c):
        while c.canReadLine():
            line = bytes(c.readLine()).strip()
            if not line:
                continue
            if not line.startswith(b"{"):
                if line == b"show":
                    window.show_window()
                continue
            c.write((json.dumps(ctl.handle(line), ensure_ascii=False) + "\n").encode("utf-8"))
            c.flush()

    def accept():
        while server.hasPendingConnections():
            c = server.nextPendingConnection()
            c.readyRead.connect(lambda c=c: serve(c))
            c.disconnected.connect(c.deleteLater)
            if c.bytesAvailable():
                serve(c)
    server.newConnection.connect(accept)
    return server


class Controller:
    def __init__(self, w):
        self.w = w

    # ---------- dispatch ----------
    def handle(self, raw: bytes) -> dict:
        try:
            msg = json.loads(raw.decode("utf-8"))
            cmd, args = msg.get("cmd"), msg.get("args") or {}
            fn = getattr(self, f"cmd_{cmd}", None) if isinstance(cmd, str) else None
            if fn is None:
                raise ControlError(f"unknown command '{cmd}'. Valid: {', '.join(self.commands())}")
            return {"ok": True, "result": fn(**args)}
        except ControlError as e:
            return {"ok": False, "error": str(e)}
        except TypeError as e:          # wrong argument names
            return {"ok": False, "error": f"bad arguments: {e}"}
        except Exception as e:          # never let a request take the app down
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def commands(self) -> list[str]:
        return sorted(n[4:] for n in dir(self) if n.startswith("cmd_"))

    # ---------- helpers ----------
    def _sliders(self) -> dict:
        w = self.w
        out = {"strength": (w.strength, 100), "highpass_hz": (w.hp, 1),
               "gate_threshold_db": (w.gate_th, 1), "output_gain_db": (w.gain, 1)}
        for key, _lo, _hi, scale, _fmt in COMP_PARAMS + LIM_PARAMS:
            out[key] = (w.dyn_panel.sliders[key], scale)
        return out

    def _checks(self) -> dict:
        w = self.w
        return {"bypass": w.bypass, "gate_enabled": w.gate_on, "eq_enabled": w.eq_panel.enable_cb,
                "comp_enabled": w.dyn_panel.comp_on, "limiter_enabled": w.dyn_panel.lim_on,
                "close_to_tray": w.tray_cb, "start_with_windows": w.autostart_cb, "resume": w.resume_cb}

    def _running(self) -> bool:
        return self.w.engine is not None

    @staticmethod
    def _devs(cb) -> list[dict]:
        return [{"id": cb.itemData(i), "name": cb.itemText(i).removesuffix("  *"),
                 "default": cb.itemText(i).endswith("  *"), "selected": i == cb.currentIndex()}
                for i in range(cb.count())]

    def _preset_list(self) -> list[dict]:
        p = self.w.eq_panel
        keys = [f"builtin:{k}" for k in eq.PRESETS] + [f"user:{k}" for k in sorted(p.user_presets)]
        return [{"key": k, "name": p._preset_name(k).removeprefix("★ "), "selected": k in p.selection} for k in keys]

    def _settings(self) -> dict:
        c = self.w.pipe.cfg
        d = {k: getattr(c, k) for k in PARAMS if hasattr(c, k)}
        d["denoise"] = "ai" if c.denoise == "onnx" else c.denoise
        d["language"] = self.w.lang
        for k in ("close_to_tray", "start_with_windows", "resume"):
            d[k] = self._checks()[k].isChecked()
        return d

    # ---------- commands ----------
    def cmd_ping(self):
        return {"app": "Noise Filter", "version": __version__}

    def cmd_help(self):
        return {"commands": self.commands(),
                "settings": {k: {"type": v[0].__name__, "min": v[1], "max": v[2], "help": v[3]}
                             for k, v in PARAMS.items()}}

    def cmd_status(self):
        w = self.w
        p = w.pipe
        model = model_update.current_model()
        out = {
            "version": __version__,
            "running": self._running(),
            "demo": w.demo,
            "window_visible": w.isVisible(),
            "engine": "C++" if w.native else "Python",
            "input_device": w.in_cb.currentText().removesuffix("  *") or None,
            "output_device": w.out_cb.currentText().removesuffix("  *") or None,
            "exclusive": w.excl.isChecked(),
            "ai_model": f"{model['name']} {model['version']}" if model else None,
            "learning_noise": not w.learn_btn.isEnabled() and not w._rec,
            "settings": self._settings(),
            "eq_presets": [k["name"] for k in self._preset_list() if k["selected"]],
            "eq_band_count": len(p.cfg.eq_bands),
            "levels_db": {"input": round(float(p.in_analyzer.level_db()), 1),
                          "output": round(float(p.out_analyzer.level_db()), 1)},
        }
        if w.engine is not None and hasattr(w.engine, "stats"):
            s = w.engine.stats()
            out["stats"] = {"xruns": s["xruns"], "latency_ms": round(s["latency_ms"], 1),
                            "dsp_avg_ms": round(s["dsp_avg_us"] / 1000, 3), "dsp_max_ms": round(s["dsp_max_us"] / 1000, 3)}
        elif w.engine is not None:
            out["stats"] = {"xruns": getattr(w.engine, "xruns", 0)}
        return out

    def cmd_start(self):
        w = self.w
        if w.demo:
            raise ControlError("the app runs in demo mode (no audio devices)")
        if not self._running():
            if w.in_cb.currentData() is None or w.out_cb.currentData() is None:
                raise ControlError("no input or output device selected (see 'devices')")
            w.start_btn.setChecked(True)
            if not self._running():
                raise ControlError(w.status.text() or "the audio engine could not start")
        return self.cmd_status()

    def cmd_stop(self):
        if self._running():
            self.w.start_btn.setChecked(False)
        return self.cmd_status()

    def cmd_set(self, **values):
        if not values:
            raise ControlError(f"nothing to set. Valid settings: {', '.join(PARAMS)}")
        clean = {k: coerce(k, v) for k, v in values.items()}      # check everything before changing anything
        if clean.get("denoise") == "onnx" and not model_update.current_model_path():
            raise ControlError("no AI model is installed; use denoise=spectral")
        w, sliders, checks = self.w, self._sliders(), self._checks()
        for k, v in clean.items():
            if k in sliders:
                s, scale = sliders[k]
                s.setValue(int(round(v * scale)))
            elif k in checks:
                if k == "start_with_windows" and not checks[k].isEnabled():
                    raise ControlError("start_with_windows is only available on Windows")
                checks[k].setChecked(v)
            elif k == "denoise":
                w.mode_cb.setCurrentIndex(MODES.index(v))
                if w.pipe.cfg.denoise != v:
                    raise ControlError(w.status.text() or f"could not switch to {v}")
            elif k == "language":
                w.lang_cb.setCurrentIndex(w.lang_cb.findData(v))
        return self._settings()

    def cmd_devices(self, refresh: bool = False):
        w = self.w
        if refresh and not self._running():
            w.refresh_devices()
        return {"input": self._devs(w.in_cb), "output": self._devs(w.out_cb),
                "exclusive": w.excl.isChecked(), "running": self._running()}

    def cmd_select_devices(self, input=None, output=None, exclusive=None):
        """Pick devices by id or by (part of) the name. A running filter restarts on the new devices."""
        w = self.w
        picks = []
        for value, cb, kind in ((input, w.in_cb, "input"), (output, w.out_cb, "output")):
            if value is None:
                continue
            i = cb.findData(value)
            if i < 0:
                text = str(value).lower()
                names = [cb.itemText(j).removesuffix("  *").lower() for j in range(cb.count())]
                exact = [j for j, n in enumerate(names) if n == text]
                part = exact or [j for j, n in enumerate(names) if text in n]
                if not part:
                    raise ControlError(f"no {kind} device matches '{value}' (see 'devices')")
                if len(part) > 1:
                    raise ControlError(f"'{value}' matches several {kind} devices: "
                                       + "; ".join(cb.itemText(j).removesuffix('  *') for j in part))
                i = part[0]
            picks.append((cb, i))
        was_on = self._running()
        if was_on:
            w.start_btn.setChecked(False)
        for cb, i in picks:
            cb.setCurrentIndex(i)
        if exclusive is not None:
            w.excl.setChecked(coerce("bypass", exclusive))    # any switch value
        w._save()
        if was_on:
            w.start_btn.setChecked(True)
            if not self._running():
                raise ControlError(w.status.text() or "the audio engine could not restart on the new devices")
        return self.cmd_devices()

    def cmd_eq_presets(self):
        return {"presets": self._preset_list(), "enabled": self.w.pipe.cfg.eq_enabled, "max_bands": eq.MAX_BANDS}

    def cmd_set_eq_presets(self, presets=None):
        """Tick exactly these presets (keys, ids like 'podcast', or display names); [] clears them."""
        presets = presets or []
        if isinstance(presets, str):
            presets = [presets]
        known = self._preset_list()
        keys = []
        for p in presets:
            low = str(p).strip().lower()
            hit = [k["key"] for k in known
                   if low in (k["key"].lower(), k["key"].split(":", 1)[1].lower(), k["name"].lower())]
            if not hit:
                raise ControlError(f"unknown preset '{p}'. Known: " + ", ".join(k["key"].split(":", 1)[1] for k in known))
            keys.append(hit[0])
        if not self.w.eq_panel.select_presets(keys):
            raise ControlError(f"these presets need more than {eq.MAX_BANDS} EQ bands together")
        return self.cmd_eq_presets()

    def cmd_learn_noise(self):
        w = self.w
        if not (self._running() or w.demo):
            raise ControlError("start the filter first: noise is learned from the live microphone")
        if not w.learn_btn.isEnabled():
            raise ControlError("already learning or recording")
        from .main_window import LEARN_SECONDS
        w.learn_noise()
        return {"learning": True, "seconds": LEARN_SECONDS, "hint": tr("noise.learning", "en").format(s=LEARN_SECONDS)}

    def cmd_show(self):
        self.w.show_window()
        return {"window_visible": True}

    def cmd_hide(self):
        self.w.hide()
        return {"window_visible": False}

    def cmd_quit(self):
        QtCore.QTimer.singleShot(200, self.w.quit_app)    # answer first, then close
        return {"quitting": True}
