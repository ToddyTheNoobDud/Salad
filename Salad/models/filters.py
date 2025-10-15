"""DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
                    Version 2, December 2004

 Copyright (C) 2004 Sam Hocevar <sam@hocevar.net>

 Everyone is permitted to copy and distribute verbatim or modified
 copies of this license document, and changing it is allowed as long
 as the name is changed.

            DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
   TERMS AND CONDITIONS FOR COPYING, DISTRIBUTION AND MODIFICATION

  0. You just DO WHAT THE FUCK YOU WANT TO.

URL: https://www.wtfpl.net/txt/copying/
"""
from typing import Any, TypedDict, List, NotRequired


class EqualizerBand(TypedDict):
    """Represents a single equalizer band configuration."""
    band: int
    gain: float


class KaraokeSettings(TypedDict, total=False):
    """Configuration for karaoke vocal removal effect."""
    level: float
    monoLevel: float
    filterBand: float
    filterWidth: float


class TimescaleSettings(TypedDict, total=False):
    """Audio playback manipulation settings."""
    speed: float
    pitch: float
    rate: float


class TremoloSettings(TypedDict, total=False):
    """Volume oscillation effect configuration."""
    frequency: float
    depth: float


class VibratoSettings(TypedDict, total=False):
    """Pitch oscillation effect configuration."""
    frequency: float
    depth: float


class RotationSettings(TypedDict, total=False):
    """8D audio rotation effect settings."""
    rotationHz: float


class DistortionSettings(TypedDict, total=False):
    """Audio distortion effect parameters."""
    sinOffset: float
    sinScale: float
    cosOffset: float
    cosScale: float
    tanOffset: float
    tanScale: float
    offset: float
    gain: float


class ChannelMixSettings(TypedDict, total=False):
    """Stereo channel mixing configuration."""
    leftToLeft: float
    leftToRight: float
    rightToLeft: float
    rightToRight: float


class LowPassSettings(TypedDict, total=False):
    """Low-pass filter configuration."""
    smoothing: float


class LavalinkFilterPayload(TypedDict, total=False):
    """The lavalink filter payload."""
    volume: NotRequired[float]
    equalizer: NotRequired[List[EqualizerBand]]
    karaoke: NotRequired[KaraokeSettings]
    timescale: NotRequired[TimescaleSettings]
    tremolo: NotRequired[TremoloSettings]
    vibrato: NotRequired[VibratoSettings]
    rotation: NotRequired[RotationSettings]
    distortion: NotRequired[DistortionSettings]
    channelMix: NotRequired[ChannelMixSettings]
    lowPass: NotRequired[LowPassSettings]
    pluginFilters: NotRequired[dict[str, Any]]


__all__ = (
    "EqualizerBand",
    "KaraokeSettings",
    "TimescaleSettings",
    "TremoloSettings",
    "VibratoSettings",
    "RotationSettings",
    "DistortionSettings",
    "ChannelMixSettings",
    "LowPassSettings",
    "LavalinkFilterPayload",
)
