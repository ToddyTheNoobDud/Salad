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
import asyncio
import aiohttp
import base64
import time
import logging
from typing import Optional, Tuple

try:
    import syncedlyrics
except ImportError:
    syncedlyrics = None

logger = logging.getLogger(__name__)

class Lyrics:
    """
    A class to fetch lyrics for a track using syncedlyrics and Spotify for metadata.
    """
    __slots__ = (
        'session', 'spotify_client_id', 'spotify_client_secret',
        'spotify_token', 'spotify_token_expires'
    )

    def __init__(self, node):
        if not syncedlyrics:
            raise RuntimeError("syncedlyrics is not installed. Please install it with 'pip install syncedlyrics'")
        self.session = aiohttp.ClientSession()
        self.spotify_client_id = node.spotify_client_id
        self.spotify_client_secret = node.spotify_client_secret
        self.spotify_token: Optional[str] = None
        self.spotify_token_expires: int = 0

    async def get_synced_lyrics(self, song_name: str, artist_name: Optional[str] = None) -> Tuple[Optional[str], bool, str, Optional[str]]:
        try:
            search_term = f"{artist_name} {song_name}" if artist_name else song_name
            
            lrc = await asyncio.to_thread(syncedlyrics.search, search_term)
            
            if lrc:
                return lrc, True, song_name, artist_name
            
            plain_lyrics = await asyncio.to_thread(syncedlyrics.search, search_term, synced_only=False)
            
            if plain_lyrics:
                return plain_lyrics, False, song_name, artist_name
                
            return None, False, song_name, artist_name
            
        except Exception as e:
            logger.error(f"Error fetching lyrics: {e}")
            return None, False, song_name, artist_name

    async def get_song_info(self, title: str, artist: Optional[str] = None) -> dict:
        """Fetch song info from Spotify including thumbnail and track URL"""
        song_info = {
            "thumbnail_url": None,
            "song_url": None
        }
        
        try:
            if self.spotify_client_id and self.spotify_client_secret:
                if not self.spotify_token or time.time() >= self.spotify_token_expires:
                    await self.refresh_spotify_token()
                
                if self.spotify_token:
                    search_query = f"{artist} {title}" if artist else title
                    
                    async with self.session.get(
                        "https://api.spotify.com/v1/search",
                        params={"q": search_query, "type": "track", "limit": 1},
                        headers={"Authorization": f"Bearer {self.spotify_token}"}
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("tracks", {}).get("items"):
                                track = data["tracks"]["items"][0]
                                if track.get("album", {}).get("images"):
                                    song_info["thumbnail_url"] = track["album"]["images"][0]["url"]
                                song_info["song_url"] = track.get("external_urls", {}).get("spotify")
                                logger.info(f"Found Spotify track: {song_info['song_url']}")
        except Exception as e:
            logger.error(f"Error fetching song info: {e}")
        
        return song_info

    async def refresh_spotify_token(self):
        try:
            if not self.spotify_client_id or not self.spotify_client_secret:
                return
            
            auth_header = base64.b64encode(
                f"{self.spotify_client_id}:{self.spotify_client_secret}".encode()
            ).decode()
            
            async with self.session.post(
                "https://accounts.spotify.com/api/token",
                headers={"Authorization": f"Basic {auth_header}"},
                data={"grant_type": "client_credentials"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.spotify_token = data.get("access_token")
                    expires_in = data.get("expires_in", 3600)
                    self.spotify_token_expires = time.time() + expires_in - 60
        except Exception as e:
            logger.error(f"Error refreshing Spotify token: {e}")

    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
