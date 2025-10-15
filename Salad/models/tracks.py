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
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

from ..Player import Player


class AudioInfo(dict):
    """Audio track information structure."""
    id: str
    seekable: bool
    artist: str
    duration: int
    live: bool
    offset: int
    name: str
    url: Optional[str]
    thumbnail: Optional[str]
    isrc_code: Optional[str]
    source: str


class AudioTrack(dict):
    """Full audio track payload."""
    track: str
    metadata: AudioInfo
    plugins: Dict[str, Any]
    custom: Dict[str, Any]


class CollectionInfo(dict):
    """Collection/playlist information."""
    title: str
    selected: int


class AudioCollection(dict):
    """Full playlist/collection payload."""
    details: CollectionInfo
    items: List[AudioTrack]
    plugins: Dict[str, Any]


class SearchResponse(dict):
    """Search result response structure."""
    type: str  # 'track', 'playlist', 'search', 'empty', 'error'
    data: Union[AudioCollection, List[AudioTrack]]
    exception: Optional[Dict[str, Any]]


class LoadResult(dict):
    """Load result from Lavalink node."""
    loadType: str
    data: Any


class PlayerState(dict):
    """Player state for persistence."""
    guild_id: int
    voice_channel: Optional[str]
    text_channel: Optional[str]
    volume: int
    paused: bool
    position: int
    current_track: Optional[AudioTrack]
    queue: List[AudioTrack]
    loop_mode: Optional[str]


class QueueSnapshot(dict):
    """Queue state snapshot."""
    tracks: List[AudioTrack]
    loop: Optional[str]
    previous: List[AudioTrack]


TrackList = List[AudioTrack]
SearchResults = Dict[str, Any]
LavalinkResponse = Dict[str, Any]
PlayerDict = Dict[int, 'Player']
GuildID = Union[int, str]
