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
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import LavalinkFilterPayload

__all__ = ("AudioFilters",)


class AudioFilters:
    """
    Manages audio filter configurations for Lavalink playback.
    
    Supports equalizer, timescale, karaoke, tremolo, vibrato, rotation,
    distortion, channel mixing, low-pass filtering, and volume control.
    
    Example:
        filters = AudioFilters()
        filters.equalizer(bands=[(0, 0.25), (1, -0.15)])
        filters.timescale(speed=1.2)
        payload = filters.get_payload()
    """

    __slots__ = (
        "_eq",
        "_timescale",
        "_karaoke",
        "_tremolo",
        "_vibrato",
        "_rotation",
        "_distortion",
        "_channel_mix",
        "_low_pass",
        "_volume",
        "_plugin_filters",
    )

    def __init__(self) -> None:
        self._eq: list[dict[str, Any]] | None = None
        self._timescale: dict[str, float] | None = None
        self._karaoke: dict[str, float] | None = None
        self._tremolo: dict[str, float] | None = None
        self._vibrato: dict[str, float] | None = None
        self._rotation: dict[str, float] | None = None
        self._distortion: dict[str, float] | None = None
        self._channel_mix: dict[str, float] | None = None
        self._low_pass: dict[str, float] | None = None
        self._volume: float | None = None
        self._plugin_filters: dict[str, Any] | None = None

    def equalizer(self, *, bands: list[tuple[int, float]]) -> AudioFilters:
        """
        Configure equalizer bands.
        
        Args:
            bands: List of (band_index, gain) tuples. Band index is 0-14,
                   gain is typically -0.25 to 1.0 (in dB).
        
        Returns:
            Self for method chaining.
        """
        self._eq = [
            {"band": int(band), "gain": max(-1.0, min(10.0, float(gain)))}
            for band, gain in bands
        ]
        return self

    def timescale(
        self,
        *,
        speed: float | None = None,
        pitch: float | None = None,
        rate: float | None = None,
    ) -> AudioFilters:
        """
        Adjust audio playback characteristics.
        
        Args:
            speed: Playback speed (0.1 to 10.0)
            pitch: Pitch adjustment (0.5 to 2.0)
            rate: Sample rate adjustment (0.1 to 10.0)
        
        Returns:
            Self for method chaining.
        """
        config: dict[str, float] = {}
        if speed is not None:
            config["speed"] = max(0.1, min(10.0, float(speed)))
        if pitch is not None:
            config["pitch"] = max(0.5, min(2.0, float(pitch)))
        if rate is not None:
            config["rate"] = max(0.1, min(10.0, float(rate)))
        
        self._timescale = config if config else None
        return self

    def karaoke(
        self,
        *,
        level: float = 1.0,
        mono_level: float = 1.0,
        filter_band: float = 220.0,
        filter_width: float = 100.0,
    ) -> AudioFilters:
        """
        Apply karaoke effect (vocal removal).
        
        Args:
            level: Effect level
            mono_level: Mono effect level
            filter_band: Frequency band to filter (Hz)
            filter_width: Filter bandwidth (Hz)
        
        Returns:
            Self for method chaining.
        """
        self._karaoke = {
            "level": float(level),
            "monoLevel": float(mono_level),
            "filterBand": float(filter_band),
            "filterWidth": float(filter_width),
        }
        return self

    def tremolo(self, *, frequency: float = 2.0, depth: float = 0.5) -> AudioFilters:
        """
        Apply tremolo effect (volume oscillation).
        
        Args:
            frequency: Oscillation frequency (Hz)
            depth: Effect depth (0.0 to 1.0)
        
        Returns:
            Self for method chaining.
        """
        self._tremolo = {
            "frequency": float(frequency),
            "depth": max(0.0, min(1.0, float(depth))),
        }
        return self

    def vibrato(self, *, frequency: float = 2.0, depth: float = 0.5) -> AudioFilters:
        """
        Apply vibrato effect (pitch oscillation).
        
        Args:
            frequency: Oscillation frequency (Hz)
            depth: Effect depth (0.0 to 1.0)
        
        Returns:
            Self for method chaining.
        """
        self._vibrato = {
            "frequency": float(frequency),
            "depth": max(0.0, min(1.0, float(depth))),
        }
        return self

    def rotation(self, *, rotation_hz: float = 0.2) -> AudioFilters:
        """
        Apply 8D audio rotation effect.
        
        Args:
            rotation_hz: Rotation frequency (Hz)
        
        Returns:
            Self for method chaining.
        """
        self._rotation = {"rotationHz": float(rotation_hz)}
        return self

    def distortion(
        self,
        *,
        sin_offset: float = 0.0,
        sin_scale: float = 1.0,
        cos_offset: float = 0.0,
        cos_scale: float = 1.0,
        tan_offset: float = 0.0,
        tan_scale: float = 1.0,
        offset: float = 0.0,
        scale: float = 1.0,
    ) -> AudioFilters:
        """
        Apply distortion effect.
        
        Args:
            sin_offset: Sine wave offset
            sin_scale: Sine wave scale
            cos_offset: Cosine wave offset
            cos_scale: Cosine wave scale
            tan_offset: Tangent wave offset
            tan_scale: Tangent wave scale
            offset: Overall offset
            scale: Overall gain/scale
        
        Returns:
            Self for method chaining.
        """
        self._distortion = {
            "sinOffset": float(sin_offset),
            "sinScale": float(sin_scale),
            "cosOffset": float(cos_offset),
            "cosScale": float(cos_scale),
            "tanOffset": float(tan_offset),
            "tanScale": float(tan_scale),
            "offset": float(offset),
            "gain": float(scale),
        }
        return self

    def channel_mix(
        self,
        *,
        left_to_left: float = 1.0,
        left_to_right: float = 0.0,
        right_to_left: float = 0.0,
        right_to_right: float = 1.0,
    ) -> AudioFilters:
        """
        Configure stereo channel mixing.
        
        Args:
            left_to_left: Left input to left output multiplier
            left_to_right: Left input to right output multiplier
            right_to_left: Right input to left output multiplier
            right_to_right: Right input to right output multiplier
        
        Returns:
            Self for method chaining.
        """
        self._channel_mix = {
            "leftToLeft": float(left_to_left),
            "leftToRight": float(left_to_right),
            "rightToLeft": float(right_to_left),
            "rightToRight": float(right_to_right),
        }
        return self

    def low_pass(self, *, smoothing: float = 20.0) -> AudioFilters:
        """
        Apply low-pass filter.
        
        Args:
            smoothing: Filter smoothing factor
        
        Returns:
            Self for method chaining.
        """
        self._low_pass = {"smoothing": float(smoothing)}
        return self

    def volume(self, *, level: float) -> AudioFilters:
        """
        Set playback volume.
        
        Args:
            level: Volume level (0.0 to 5.0, 1.0 is normal)
        
        Returns:
            Self for method chaining.
        """
        self._volume = float(level)
        return self

    def plugin(self, name: str, config: dict[str, Any]) -> AudioFilters:
        """
        Add a custom plugin filter.
        
        Args:
            name: Plugin filter name
            config: Plugin configuration dictionary
        
        Returns:
            Self for method chaining.
        """
        if self._plugin_filters is None:
            self._plugin_filters = {}
        self._plugin_filters[name] = config
        return self

    def reset(self) -> AudioFilters:
        """
        Clear all filter configurations.
        
        Returns:
            Self for method chaining.
        """
        self._eq = None
        self._timescale = None
        self._karaoke = None
        self._tremolo = None
        self._vibrato = None
        self._rotation = None
        self._distortion = None
        self._channel_mix = None
        self._low_pass = None
        self._volume = None
        self._plugin_filters = None
        return self

    def get_payload(self) -> LavalinkFilterPayload:
        """
        Build the complete filter payload for Lavalink.
        
        Returns:
            Dictionary containing all configured filters.
        """
        payload: dict[str, Any] = {}
        
        if self._eq is not None:
            payload["equalizer"] = self._eq
        if self._timescale is not None:
            payload["timescale"] = self._timescale
        if self._karaoke is not None:
            payload["karaoke"] = self._karaoke
        if self._tremolo is not None:
            payload["tremolo"] = self._tremolo
        if self._vibrato is not None:
            payload["vibrato"] = self._vibrato
        if self._rotation is not None:
            payload["rotation"] = self._rotation
        if self._distortion is not None:
            payload["distortion"] = self._distortion
        if self._channel_mix is not None:
            payload["channelMix"] = self._channel_mix
        if self._low_pass is not None:
            payload["lowPass"] = self._low_pass
        if self._volume is not None:
            payload["volume"] = self._volume
        if self._plugin_filters is not None:
            payload["pluginFilters"] = self._plugin_filters
        
        return payload # type: ignore

    def __repr__(self) -> str:
        active = []
        if self._eq:
            active.append(f"equalizer({len(self._eq)} bands)")
        if self._timescale:
            active.append("timescale")
        if self._karaoke:
            active.append("karaoke")
        if self._tremolo:
            active.append("tremolo")
        if self._vibrato:
            active.append("vibrato")
        if self._rotation:
            active.append("rotation")
        if self._distortion:
            active.append("distortion")
        if self._channel_mix:
            active.append("channel_mix")
        if self._low_pass:
            active.append("low_pass")
        if self._volume is not None:
            active.append(f"volume={self._volume}")
        if self._plugin_filters:
            active.append(f"plugins({len(self._plugin_filters)})")
        
        filters_str = ", ".join(active) if active else "no filters"
        return f"<AudioFilters {filters_str}>"
