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
from typing import Optional, Tuple

class Track:
  def __init__(self, data, requester=None):
    self.track = data.get('track') or data.get('encoded')
    info = data.get('info', {})
    self.identifier = info.get('identifier') or data.get('identifier', '')
    self.isSeekable = info.get('isSeekable', data.get('isSeekable', True))
    self.author = info.get('author') or data.get('author', '')
    self.length = info.get('length') or data.get('length', 0)
    self.isStream = info.get('isStream', data.get('isStream', False))
    self.title = info.get('title') or data.get('title', '')
    self.uri = info.get('uri') or data.get('uri', '')
    self.sourceName = info.get('sourceName') or data.get('sourceName', '')
    self.isrc = info.get('isrc') or data.get('isrc', '')
    self.requester = requester
    self._lyrics = None
    self._lyrics_synced = False

  @property
  def lyrics(self) -> Optional[str]:
    return self._lyrics

  @property
  def lyrics_synced(self) -> bool:
    return self._lyrics_synced

  async def fetch_lyrics(self, player) -> Tuple[Optional[str], bool]:
    """Fetches lyrics for the track and caches them."""
    if self._lyrics:
        return self._lyrics, self._lyrics_synced

    lyrics_handler = player.get_lyrics_handler()
    if not lyrics_handler:
        return None, False

    lyrics, is_synced, _, _ = await lyrics_handler.get_synced_lyrics(self.title, self.author)
    self._lyrics = lyrics
    self._lyrics_synced = is_synced
    return self._lyrics, self._lyrics_synced

  def resolve(self, salad):
    return self.track

  def __str__(self):
    return f"{self.title} by {self.author}"

  def __repr__(self):
    return f"Track(title='{self.title}', author='{self.author}', length={self.length})"
