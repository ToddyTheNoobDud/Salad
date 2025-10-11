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
import re
from enum import Enum, IntEnum
from typing import Pattern, Optional, ClassVar, Iterable

__all__ = (
    "SearchType",
    "TrackType",
    "PlaylistType",
    "NodeAlgorithm",
    "LoopMode",
    "RouteStrategy",
    "RouteIPType",
    "URLRegex",
    "LogLevel",
)


class SearchType(Enum):
    """
    The enum for the different search types.
    """

    ytsearch = "ytsearch"
    ytmsearch = "ytmsearch"
    scsearch = "scsearch"

    def __str__(self) -> str:
        return self.value


class TrackType(Enum):
    """
    Flags for the origin/source of a track.
    """

    YOUTUBE = "youtube"
    SOUNDCLOUD = "soundcloud"
    SPOTIFY = "spotify"
    APPLE_MUSIC = "apple_music"
    HTTP = "http"
    LOCAL = "local"
    OTHER = "other"

    @classmethod
    def _missing_(cls, _: object) -> "TrackType":
        return cls.OTHER

    def __str__(self) -> str:
        return self.value


class PlaylistType(Enum):
    """Playlist source identifiers."""

    YOUTUBE = "youtube"
    SOUNDCLOUD = "soundcloud"
    SPOTIFY = "spotify"
    APPLE_MUSIC = "apple_music"
    OTHER = "other"

    @classmethod
    def _missing_(cls, _: object) -> "PlaylistType":
        return cls.OTHER

    def __str__(self) -> str:
        return self.value


class NodeAlgorithm(Enum):
    """Node selection algorithm identifiers."""

    by_ping = "BY_PING"
    by_players = "BY_PLAYERS"

    def __str__(self) -> str:
        return self.value


class LoopMode(Enum):
    """Queue loop modes."""

    TRACK = "track"
    QUEUE = "queue"

    def __str__(self) -> str:
        return self.value


class RouteStrategy(Enum):
    """Route planner strategies for Lavalink-like nodes."""

    ROTATE_ON_BAN = "RotatingIpRoutePlanner"
    LOAD_BALANCE = "BalancingIpRoutePlanner"
    NANO_SWITCH = "NanoIpRoutePlanner"
    ROTATING_NANO_SWITCH = "RotatingNanoIpRoutePlanner"

    def __str__(self) -> str:
        return self.value


class RouteIPType(Enum):
    """IP address family used by the route planner."""

    IPV4 = "Inet4Address"
    IPV6 = "Inet6Address"

    def __str__(self) -> str:
        return self.value


class URLRegex:
    """Container for commonly used URL regex patterns and helpers.

    Each attribute is a compiled Pattern[str]. Use the helper methods to
    test or extract information from a URL.
    """

    SPOTIFY_URL: ClassVar[Pattern[str]] = re.compile(
        r"https?://open.spotify.com/(?P<type>album|playlist|track|artist)/(?P<id>[A-Za-z0-9]+)"
    )

    DISCORD_MP3_URL: ClassVar[Pattern[str]] = re.compile(
        r"https?://cdn\.discordapp\.com/attachments/(?P<channel_id>[0-9]+)/"
        r"(?P<message_id>[0-9]+)/(?P<file>[A-Za-z0-9_.-]+)"
    )

    YOUTUBE_URL: ClassVar[Pattern[str]] = re.compile(
        r"^((?:https?:)?//)?((?:www|m)\.)?((?:youtube\.com|youtu.be))"
        r"(/(?:[\w\-]+\?v=|embed/|v/)?)([\w\-]+)(\S+)?$"
    )

    YOUTUBE_PLAYLIST_URL: ClassVar[Pattern[str]] = re.compile(
        r"^((?:https?:)?//)?((?:www|m)\.)?((?:youtube\.com|youtu.be))/playlist\?list=.*"
    )

    YOUTUBE_TIMESTAMP: ClassVar[Pattern[str]] = re.compile(r"(?P<video>^.*?)(\?t|&start)=(?P<time>\d+)?.*")

    AM_URL: ClassVar[Pattern[str]] = re.compile(
        r"https?://music.apple.com/(?P<country>[A-Za-z]{2})/"
        r"(?P<type>album|playlist|song|artist)/(?P<name>.+)/(?P<id>[^?]+)"
    )

    AM_SINGLE_IN_ALBUM_REGEX: ClassVar[Pattern[str]] = re.compile(
        r"https?://music.apple.com/(?P<country>[A-Za-z]{2})/(?P<type>album|playlist|song|artist)/"
        r"(?P<name>.+)/(?P<id>.+)(\?i=)(?P<id2>.+)"
    )

    SOUNDCLOUD_URL: ClassVar[Pattern[str]] = re.compile(r"((?:https?:)?//)?((?:www|m)\.)?soundcloud.com/.*/.*")

    SOUNDCLOUD_PLAYLIST_URL: ClassVar[Pattern[str]] = re.compile(
        r"^(https?:\\/\\/)?(www\.)?(m\.)?soundcloud\.com\/.*/sets/.*"
    )

    SOUNDCLOUD_TRACK_IN_SET_URL: ClassVar[Pattern[str]] = re.compile(
        r"^(https?:\\/\\/)?(www\.)?(m\.)?soundcloud\.com/[A-Za-z0-9-._]+/[A-Za-z0-9-._]+(\?in)"
    )

    LAVALINK_SEARCH: ClassVar[Pattern[str]] = re.compile(r"(?P<type>ytm?|sc)search:")

    BASE_URL: ClassVar[Pattern[str]] = re.compile(r"https?://(?:www\.)?.+")

    @classmethod
    def any_match(cls, url: str, patterns: Optional[Iterable[Pattern[str]]] = None) -> bool:
        """Return True if any of the selected patterns match the URL.

        If `patterns` is None, tests against a sensible default set.
        """
        candidates = patterns or (
            cls.YOUTUBE_URL,
            cls.YOUTUBE_PLAYLIST_URL,
            cls.SPOTIFY_URL,
            cls.SOUNDCLOUD_URL,
            cls.AM_URL,
            cls.BASE_URL,
        )
        for p in candidates:
            if p.search(url):
                return True
        return False


class LogLevel(IntEnum):
    """Shorthand for logging levels.

    Use `LogLevel.from_str(...)` for robust parsing from user input.
    """

    DEBUG = 10
    INFO = 20
    WARN = 30
    ERROR = 40
    CRITICAL = 50

    @classmethod
    def from_str(cls, level_str: str) -> "LogLevel":
        """Parse a string (case-insensitive) into a LogLevel.

        Raises:
            ValueError: if the provided string does not map to a valid level.
        """
        if not isinstance(level_str, str):
            raise TypeError("level_str must be a string")

        normalized = level_str.strip().upper()
        synonyms = {
            "WARNING": "WARN",
            "WARN": "WARN",
            "INFO": "INFO",
            "DEBUG": "DEBUG",
            "ERROR": "ERROR",
            "CRITICAL": "CRITICAL",
            "FATAL": "CRITICAL",
        }

        key = synonyms.get(normalized)
        if key is None:
            try:
                return cls[normalized]
            except KeyError:
                allowed = ", ".join([m.name for m in cls])
                raise ValueError(f"No such log level: {level_str!r}. Allowed: {allowed}")

        return cls[key]

    def __str__(self) -> str:
        return self.name
