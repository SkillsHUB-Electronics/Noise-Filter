import json
import os
from pathlib import Path
from ..core import PipelineConfig


def config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "NoiseFilter" / "config.json"


def load() -> dict:
    try:
        return json.loads(config_path().read_text("utf-8"))
    except Exception:
        return {}


def save(data: dict) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), "utf-8")


def pipeline_config(data: dict) -> PipelineConfig:
    fields = PipelineConfig.__dataclass_fields__
    return PipelineConfig(**{k: v for k, v in data.get("pipeline", {}).items() if k in fields})
