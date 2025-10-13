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
import re
import random
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

SC_LINK_RE = re.compile(r'<a\s+itemprop="url"\s+href="(\/[^"]+)"')
MAX_SC_LINKS = 20
MAX_SP_RESULTS = 5

async def _fetch(session, url):
    try:
        async with session.get(url, timeout=8.0, allow_redirects=True) as response:
            if response.status == 200:
                return await response.text()
            return None
    except Exception as e:
        logger.error(f"Autoplay fetch error for {url}: {e}")
        return None

async def sc_autoplay(track_url: str) -> List[str]:
    """
    Gets a list of recommended SoundCloud tracks based on the last played song.
    """
    if not track_url or "soundcloud.com" not in track_url:
        return []
    
    try:
        async with aiohttp.ClientSession() as session:
            html = await _fetch(session, f"{track_url}/recommended")
            if not html:
                return []

            links = [f"https://soundcloud.com{m.group(1)}" for m in SC_LINK_RE.finditer(html)]
            
            if not links:
                return []

            random.shuffle(links)
            return links[:MAX_SC_LINKS]
    except Exception as e:
        logger.error(f"sc_autoplay error: {e}")
        return []

async def sp_autoplay(player, seed_track) -> Optional[List]:
    """
    Gets a list of recommended Spotify tracks using the Spotify recommendations API.
    """
    try:
        if not seed_track or not seed_track.identifier:
            return None

        query = f"sprec:seed_tracks={seed_track.identifier}"
        
        result = await player.salad.resolve(query, requester=seed_track.requester)
        
        if not result or not result.get('tracks'):
            return None

        excluded_ids = {player.current.identifier if player.current else None}
        
        unique_tracks = []
        for t in result['tracks']:
            if t.identifier not in excluded_ids:
                t.pluginInfo = {**(t.pluginInfo or {}), "fromAutoplay": True}
                unique_tracks.append(t)
                excluded_ids.add(t.identifier)

        return unique_tracks[:MAX_SP_RESULTS] if unique_tracks else None

    except Exception as e:
        logger.error(f"sp_autoplay error: {e}")
        return None

async def yt_autoplay(player, seed_track) -> Optional[List]:
    """
    Gets a list of recommended YouTube tracks.
    """
    try:
        query = f"https://www.youtube.com/watch?v={seed_track.identifier}&list=RD{seed_track.identifier}"
        result = await player.salad.resolve(query, requester=seed_track.requester)

        if not result or result.get('loadType') != 'playlist' or not result.get('tracks'):
            return None
        
        tracks = result['tracks']
        
        if tracks[0].identifier == seed_track.identifier:
            tracks.pop(0)
        
        random.shuffle(tracks)
        
        for t in tracks:
            t.pluginInfo = {**(t.pluginInfo or {}), "fromAutoplay": True}

        return tracks[:10] if tracks else None

    except Exception as e:
        logger.error(f"yt_autoplay error: {e}")
        return None
