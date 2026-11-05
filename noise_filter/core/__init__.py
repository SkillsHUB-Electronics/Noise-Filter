"""Pure audio core. No UI or device imports here, so it can be ported to C++ 1:1.

Contract: every processor takes one float32 frame of FRAME_SIZE samples
(mono, 48 kHz, range -1..1) and returns one frame of the same size.
"""
from .constants import SAMPLE_RATE, FRAME_SIZE, FRAME_MS
from .pipeline import Pipeline, PipelineConfig

__all__ = ["SAMPLE_RATE", "FRAME_SIZE", "FRAME_MS", "Pipeline", "PipelineConfig"]
