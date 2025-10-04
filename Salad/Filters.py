from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple, Any

__all__ = (
    "equalizer_bands",
    "build_equalizer",
    "build_timescale",
    "build_karaoke",
    "build_tremolo",
    "build_vibrato",
    "build_rotation",
    "build_distortion",
    "build_channel_mix",
    "build_low_pass",
    "build_volume",
    "Filters",
)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def equalizer_bands(count: int = 15) -> List[int]:
    """Return default band indices for an equalizer (0..count-1)."""
    return list(range(count))


def build_equalizer(bands: Sequence[Tuple[int, float]]) -> Dict[str, Any]:
    """Build an equalizer payload.

    bands: iterable of (band_index, gain) where gain is in dB (-0.25..1.0 typical)
    """
    eq = []
    for band, gain in bands:
        try:
            bi = int(band)
        except Exception:
            raise ValueError("band index must be an integer")
        g = float(gain)
        # Many lavalink implementations accept -0.25 .. 1.0 range, but clamp generously
        g = _clamp(g, -1.0, 10.0)
        eq.append({"band": bi, "gain": g})
    return {"equalizer": eq}


def build_timescale(speed: Optional[float] = None, pitch: Optional[float] = None, rate: Optional[float] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    ts: Dict[str, float] = {}
    if speed is not None:
        ts["speed"] = float(_clamp(speed, 0.1, 10.0))
    if pitch is not None:
        ts["pitch"] = float(_clamp(pitch, 0.5, 2.0))
    if rate is not None:
        ts["rate"] = float(_clamp(rate, 0.1, 10.0))
    if ts:
        payload["timescale"] = ts
    return payload


def build_karaoke(level: float = 1.0, mono_level: float = 1.0, filter_band: float = 220.0, filter_width: float = 100.0) -> Dict[str, Any]:
    return {
        "karaoke": {
            "level": float(level),
            "monoLevel": float(mono_level),
            "filterBand": float(filter_band),
            "filterWidth": float(filter_width),
        }
    }


def build_tremolo(frequency: float = 2.0, depth: float = 0.5) -> Dict[str, Any]:
    return {"tremolo": {"frequency": float(frequency), "depth": float(_clamp(depth, 0.0, 1.0))}}


def build_vibrato(frequency: float = 2.0, depth: float = 0.5) -> Dict[str, Any]:
    return {"vibrato": {"frequency": float(frequency), "depth": float(_clamp(depth, 0.0, 1.0))}}


def build_rotation(rotation_hz: float = 0.2) -> Dict[str, Any]:
    return {"rotation": {"rotationHz": float(rotation_hz)}}


def build_distortion(shift: float = 0.0, sin_offset: float = 0.0, cos_offset: float = 0.0, tan_offset: float = 0.0, offset: float = 0.0, gain: float = 1.0) -> Dict[str, Any]:
    return {
        "distortion": {
            "sinOffset": float(sin_offset),
            "sinScale": float(shift),
            "cosOffset": float(cos_offset),
            "cosScale": float(shift),
            "tanOffset": float(tan_offset),
            "tanScale": float(shift),
            "offset": float(offset),
            "gain": float(gain),
        }
    }


def build_channel_mix(left_to_left: float = 1.0, left_to_right: float = 0.0, right_to_left: float = 0.0, right_to_right: float = 1.0) -> Dict[str, Any]:
    return {
        "channelMix": {
            "leftToLeft": float(left_to_left),
            "leftToRight": float(left_to_right),
            "rightToLeft": float(right_to_left),
            "rightToRight": float(right_to_right),
        }
    }


def build_low_pass(smoothing: float = 20.0) -> Dict[str, Any]:
    return {"lowPass": {"smoothing": float(smoothing)}}


def build_volume(volume: float) -> Dict[str, Any]:
    # volume is a multiplier: 1.0 = 100%
    return {"volume": float(volume)}


@dataclass
class Filters:
    """Accumulate filter changes and build a single payload.

    Usage:
      f = Filters()
      f.set_equalizer([(0, 0.5), (1, -0.3)])
      f.set_timescale(speed=1.1)
      payload = f.to_payload()
    """

    equalizer: Optional[List[Dict[str, Any]]] = field(default=None)
    timescale: Optional[Dict[str, Any]] = field(default=None)
    karaoke: Optional[Dict[str, Any]] = field(default=None)
    tremolo: Optional[Dict[str, Any]] = field(default=None)
    vibrato: Optional[Dict[str, Any]] = field(default=None)
    rotation: Optional[Dict[str, Any]] = field(default=None)
    distortion: Optional[Dict[str, Any]] = field(default=None)
    channelMix: Optional[Dict[str, Any]] = field(default=None)
    lowPass: Optional[Dict[str, Any]] = field(default=None)
    volume: Optional[float] = field(default=None)

    def set_equalizer(self, bands: Sequence[Tuple[int, float]]) -> None:
        self.equalizer = build_equalizer(bands)["equalizer"]

    def set_timescale(self, speed: Optional[float] = None, pitch: Optional[float] = None, rate: Optional[float] = None) -> None:
        self.timescale = build_timescale(speed, pitch, rate).get("timescale")

    def set_karaoke(self, level: float = 1.0, mono_level: float = 1.0, filter_band: float = 220.0, filter_width: float = 100.0) -> None:
        self.karaoke = build_karaoke(level, mono_level, filter_band, filter_width)["karaoke"]

    def set_tremolo(self, frequency: float = 2.0, depth: float = 0.5) -> None:
        self.tremolo = build_tremolo(frequency, depth)["tremolo"]

    def set_vibrato(self, frequency: float = 2.0, depth: float = 0.5) -> None:
        self.vibrato = build_vibrato(frequency, depth)["vibrato"]

    def set_rotation(self, rotation_hz: float = 0.2) -> None:
        self.rotation = build_rotation(rotation_hz)["rotation"]

    def set_distortion(self, **kwargs) -> None:
        self.distortion = build_distortion(**kwargs)["distortion"]

    def set_channel_mix(self, **kwargs) -> None:
        self.channelMix = build_channel_mix(**kwargs)["channelMix"]

    def set_low_pass(self, smoothing: float = 20.0) -> None:
        self.lowPass = build_low_pass(smoothing)["lowPass"]

    def set_volume(self, volume: float) -> None:
        self.volume = float(volume)

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if self.equalizer is not None:
            payload["equalizer"] = self.equalizer
        if self.timescale is not None:
            payload["timescale"] = self.timescale
        if self.karaoke is not None:
            payload["karaoke"] = self.karaoke
        if self.tremolo is not None:
            payload["tremolo"] = self.tremolo
        if self.vibrato is not None:
            payload["vibrato"] = self.vibrato
        if self.rotation is not None:
            payload["rotation"] = self.rotation
        if self.distortion is not None:
            payload["distortion"] = self.distortion
        if self.channelMix is not None:
            payload["channelMix"] = self.channelMix
        if self.lowPass is not None:
            payload["lowPass"] = self.lowPass
        if self.volume is not None:
            payload["volume"] = self.volume
        return payload
