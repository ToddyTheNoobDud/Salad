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
from typing import Optional, List, TYPE_CHECKING
import random

if TYPE_CHECKING:
    from .Player import Player
    from .models.tracks import AudioTrack, TrackList


class Queue:
    """Optimized queue with __slots__ and fast operations."""

    __slots__ = ('player', '_q', 'loop', 'previous', '_maxPreviousSize')

    def __init__(self, player: 'Player'):
        self.player = player
        self._q: List['AudioTrack'] = []
        self.loop: Optional[str] = None
        self.previous: List['AudioTrack'] = []
        self._maxPreviousSize = 10

    def add(self, track: 'AudioTrack') -> bool:
        """Add track to queue."""
        if not track:
            return False
        self._q.append(track)
        return True

    def insert(self, track: 'AudioTrack', position: int = 0) -> bool:
        """Insert track at position."""
        if not track:
            return False
        position = max(0, min(position, len(self._q)))
        self._q.insert(position, track)
        return True

    def remove(self, index: int) -> Optional['AudioTrack']:
        """Remove track at index."""
        if 0 <= index < len(self._q):
            return self._q.pop(index)
        return None

    def clear(self) -> None:
        """Clear queue."""
        self._q.clear()
        self.previous.clear()

    def shuffle(self) -> None:
        """Shuffle queue in-place."""
        random.shuffle(self._q)

    def getNext(self) -> Optional['AudioTrack']:
        """Get next track without removing."""
        if self.loop == 'track' and self.player.currentTrackObj:
            return self.player.currentTrackObj

        if not self._q:
            if self.loop == 'queue' and self.previous:
                self._q = self.previous.copy()
                self.previous.clear()
                return self._q[0] if self._q else None
            return None

        return self._q[0]

    def consumeNext(self) -> Optional['AudioTrack']:
        """Remove and return next track."""
        if not self._q:
            return None

        consumed = self._q.pop(0)
        self.previous.append(consumed)

        if len(self.previous) > self._maxPreviousSize:
            self.previous.pop(0)

        return consumed

    def peek(self, index: int = 0) -> Optional['AudioTrack']:
        """Look at track without removing."""
        if 0 <= index < len(self._q):
            return self._q[index]
        return None

    def getAll(self) -> 'TrackList':
        """Get copy of all tracks."""
        return self._q.copy()

    def __len__(self) -> int:
        return len(self._q)

    def __bool__(self) -> bool:
        return bool(self._q)

    def setLoop(self, mode: Optional[str] = None) -> None:
        """Set loop mode."""
        if mode not in [None, 'track', 'queue']:
            raise ValueError("Loop mode must be None, 'track', or 'queue'")
        self.loop = mode

    def __repr__(self) -> str:
        return f"Queue(length={len(self._q)}, loop={self.loop})"
