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
from typing import Optional, Dict, Any, Callable, TYPE_CHECKING
import asyncio
import aiohttp
import logging
from .Queue import Queue

if TYPE_CHECKING:
    from .models.tracks import AudioTrack
    from .Node import Node

logger = logging.getLogger(__name__)


class NullQueue:
    """No-op queue for destroyed players."""
    __slots__ = ('_q', 'loop')

    def __init__(self, player=None):
        self._q = []
        self.loop = None

    def add(self, item): return bool(self)
    def insert(self, item, idx=0): return None
    def clear(self): self._q.clear()
    def getNext(self): return None
    def consumeNext(self): return None
    def getAll(self): return []
    def __len__(self): return 0
    @property
    def queue(self): return []


class Player:
    """Optimized player with built-in Discord voice state management."""

    __slots__ = (
        'salad', 'nodes', 'guildId', 'voiceChannel', 'textChannel',
        'mute', 'deaf', 'playing', 'destroyed', 'current',
        'currentTrackObj', 'position', 'timestamp', 'ping',
        'connected', 'volume', '_voiceState', '_lastVoiceUpdate',
        'paused', 'queue', '_playLock', '_voiceUpdateTask',
        '_destroying', '_voiceCleanupCallback', '_trackEndHandled',
        '_kickCheckTask', '_lastVoiceChannelId', '_voice_client', 'autoplay',
        '__weakref__'
    )

    def __init__(self, salad, nodes: 'Node', opts: Optional[Dict] = None):
        opts = opts or {}
        self.salad = salad
        self.nodes = nodes
        self.guildId: Optional[int] = opts.get('guildId')
        self.voiceChannel: Optional[str] = opts.get('voiceChannel')
        self.textChannel: Optional[str] = opts.get('textChannel')
        self.mute: bool = opts.get('mute', False)
        self.deaf: bool = opts.get('deaf', True)
        self.playing: bool = False
        self.destroyed: bool = False
        self.current: Optional[str] = None
        self.currentTrackObj: Optional['AudioTrack'] = None
        self.position: int = 0
        self.timestamp: int = 0
        self.ping: int = 0
        self.connected: bool = False
        self.volume: int = opts.get('volume', 100)
        self.paused: bool = False
        self.autoplay: bool = False
        self._voiceState: Dict = {'voice': {}}
        self._lastVoiceUpdate: Dict = {}
        self.queue = Queue(self)
        self._playLock = asyncio.Lock()
        self._voiceUpdateTask: Optional[asyncio.Task] = None
        self._destroying: bool = False
        self._trackEndHandled: bool = False
        self._voiceCleanupCallback: Optional[Callable] = None
        self._kickCheckTask: Optional[asyncio.Task] = None
        self._lastVoiceChannelId: Optional[str] = None
        self._voice_client: Optional[Any] = None 

    def setVoiceCleanupCallback(self, callback: Callable) -> None:
        """Set voice cleanup callback."""
        self._voiceCleanupCallback = callback

    def setVoiceClient(self, voice_client: Any) -> None:
        """
        Set the voice client reference for this player.
        
        Args:
            voice_client: SaladVoiceClient instance
        """
        self._voice_client = voice_client
        logger.debug(f"Voice client set for player in guild {self.guildId}")

    def getVoiceClient(self) -> Optional[Any]:
        """
        Get the voice client for this player.
        
        Returns:
            Optional[Any]: SaladVoiceClient instance or None
        """
        if self._voice_client:
            return self._voice_client
        
        if self.salad and self.salad.client and self.guildId:
            guild = self.salad.client.get_guild(self.guildId)
            if guild and guild.voice_client:
                self._voice_client = guild.voice_client
                return self._voice_client
        
        return None

    def isVoiceReady(self) -> bool:
        """Check if voice ready."""
        vd = self._voiceState.get('voice', {})
        return bool(vd.get('session_id') and vd.get('token') and vd.get('endpoint'))

    async def connect(self, opts: Optional[Dict] = None) -> None:
        """
        Connect to voice. This now handles voice state updates that come from
        Discord through the SaladVoiceClient.
        """
        opts = opts or {}
        vc = opts.get('vc', self.voiceChannel)
        if not vc:
            return

        if self.destroyed:
            self.destroyed = False
            self._destroying = False
            self.connected = False
            self.playing = False
            self.paused = False
            self.current = None
            self.currentTrackObj = None
            self.position = 0
            self.deaf = opts.get('deaf', True)
            self.mute = opts.get('mute', False)
            self._voiceState = {'voice': {}}
            self._lastVoiceUpdate = {}

        self._lastVoiceChannelId = str(vc) if vc else None
        
        voice_client = self.getVoiceClient()
        if voice_client:
            logger.info(f"Voice client connected for guild {self.guildId}")
        
        self.salad.emit('playerConnect', self)

    async def handleVoiceStateUpdate(self, data: Dict) -> None:
        """
        Handle voice state update with kick detection.
        This is called by SaladVoiceClient when Discord sends voice state updates.
        """
        if self.destroyed or self._destroying:
            return

        cid = data.get('channel_id')
        sid = data.get('session_id')
        user_id = data.get('user_id')

        if user_id and str(user_id) != str(self.salad.clientId):
            return

        if sid:
            self._voiceState['voice']['session_id'] = sid

        old_channel = self.voiceChannel
        new_channel = cid

        if old_channel and not new_channel:
            logger.warning(f'Bot disconnected from voice in guild {self.guildId}')

            if self._kickCheckTask and not self._kickCheckTask.done():
                self._kickCheckTask.cancel()

            self._kickCheckTask = asyncio.create_task(self._handleKickCheck())
            return await self.destroy(cleanup_voice=True)

        if old_channel and new_channel and old_channel != new_channel:
            logger.info(f'Bot moved from channel {old_channel} to {new_channel} in guild {self.guildId}')
            self.voiceChannel = new_channel
            self._lastVoiceChannelId = new_channel

            self.salad.emit('playerMove', self, old_channel, new_channel)

            self._scheduleVoiceUpdate()
            return

        self.voiceChannel = new_channel
        if new_channel:
            self._lastVoiceChannelId = new_channel
            self.connected = bool(new_channel)

        self._scheduleVoiceUpdate()
        self.salad.emit('playerVoiceStateUpdate', self, data)

    async def _handleKickCheck(self) -> None:
        """Check if disconnect was a kick after a delay."""
        try:
            await asyncio.sleep(1.5)

            if not self.voiceChannel and not self.destroyed and not self._destroying:
                logger.info(f'Confirmed kick for guild {self.guildId}, destroying player')

                self.salad.emit('playerKick', self)

                await self.destroy(cleanup_voice=False)

        except asyncio.CancelledError:
            logger.debug(f'Kick check cancelled for guild {self.guildId}')
        except Exception as e:
            logger.error(f'Error in kick check: {e}')

    async def handleVoiceServerUpdate(self, data: Dict) -> None:
        """
        Handle voice server update.
        This is called by SaladVoiceClient when Discord sends voice server updates.
        """
        if self.destroyed or self._destroying:
            return

        self._voiceState['voice']['token'] = data['token']
        self._voiceState['voice']['endpoint'] = data['endpoint']

        if self._kickCheckTask and not self._kickCheckTask.done():
            self._kickCheckTask.cancel()

        self._scheduleVoiceUpdate()
        self.salad.emit('playerVoiceServerUpdate', self, data)

    def _scheduleVoiceUpdate(self) -> None:
        """Debounce voice updates."""
        if self.destroyed or self._destroying:
            return

        if self._voiceUpdateTask and not self._voiceUpdateTask.done():
            self._voiceUpdateTask.cancel()

        self._voiceUpdateTask = asyncio.create_task(self._debouncedDispatch())

    async def _debouncedDispatch(self) -> None:
        """Wait and dispatch."""
        try:
            await asyncio.sleep(0.05)
            await self._dispatchVoiceUpdate()
        except asyncio.CancelledError:
            pass

    async def _dispatchVoiceUpdate(self) -> None:
        """Send voice update to Lavalink."""
        if self.destroyed or self._destroying:
            return

        data = self._voiceState['voice']
        sid = data.get('session_id')
        token = data.get('token')
        endpoint = data.get('endpoint')

        if not (sid and token and endpoint):
            return

        if (self._lastVoiceUpdate.get('session_id') == sid and
            self._lastVoiceUpdate.get('token') == token and
            self._lastVoiceUpdate.get('endpoint') == endpoint):
            return

        if not getattr(self.nodes, 'sessionId', None):
            return

        req = {
            'voice': {
                'sessionId': sid,
                'token': token,
                'endpoint': endpoint
            },
            'volume': self.volume
        }

        try:
            await self.nodes._updatePlayer(self.guildId, data=req)
            self.connected = True
            self._lastVoiceUpdate = {
                'session_id': sid,
                'token': token,
                'endpoint': endpoint
            }
            self.salad.emit('playerVoiceUpdate', self)
            logger.info(f"Voice update dispatched to Lavalink for guild {self.guildId}")
        except Exception as e:
            self.connected = False
            logger.debug(f"Voice update failed: {e}")

    async def play(self) -> None:
        """Play next track."""
        async with self._playLock:
            self._trackEndHandled = False

            if self.destroyed or self._destroying:
                return

            if not self.isVoiceReady() or not self.connected:
                logger.warning(f"Cannot play - voice not ready for guild {self.guildId}")
                return

            if len(self.queue) == 0:
                self.playing = False
                self.current = None
                self.currentTrackObj = None
                self.salad.emit('queueEnd', self)
                return

            item = self.queue.getNext()
            if not item:
                self.playing = False
                return

            try:
                self.currentTrackObj = item

                if hasattr(item, 'track') and item.track:
                    self.current = item.track
                elif hasattr(item, 'resolve'):
                    self.current = item.resolve(self.salad)
                else:
                    self.playing = False
                    self.current = None
                    self.currentTrackObj = None
                    return

                if not self.current:
                    self.playing = False
                    return

                playData = {
                    'encodedTrack': self.current,
                    'position': 0,
                    'volume': self.volume,
                    'paused': False
                }

                await self.nodes._updatePlayer(self.guildId, data=playData)

                self.position = 0
                self.playing = True
                self.paused = False

                self.salad.emit('trackStart', self, item)
                logger.info(f"Started playing track in guild {self.guildId}")

            except Exception as e:
                self.playing = False
                self.current = None
                self.currentTrackObj = None
                self.queue.consumeNext()
                logger.debug(f"Play failed: {e}")

                if len(self.queue) > 0:
                    asyncio.create_task(self.play())

    async def skip(self) -> None:
        """Skip current track."""
        if self.destroyed or self._destroying:
            return

        prev_track = self.currentTrackObj

        try:
            await self.nodes._updatePlayer(self.guildId, data={'encodedTrack': None}, replace=True)
        except Exception as e:
            logger.debug(f"Skip stop failed: {e}")

        if self.queue.loop != 'track':
            self.queue.consumeNext()

        self.current = None
        self.currentTrackObj = None
        self.position = 0
        self.playing = False

        self.salad.emit('trackSkip', self, prev_track)

        await asyncio.sleep(0.2)

        if len(self.queue) > 0:
            await self.play()
        else:
            self.salad.emit('queueEnd', self)

    async def stop(self) -> None:
        """Stop playback and clear queue."""
        if self.destroyed or self._destroying:
            return

        was_playing = self.playing

        try:
            if was_playing or self.current:
                await self.nodes._updatePlayer(self.guildId, data={'encodedTrack': None}, replace=True)
        except Exception as e:
            logger.debug(f"Stop track failed: {e}")

        self.current = None
        self.currentTrackObj = None
        self.position = 0
        self.playing = False
        self.paused = False
        self.queue.clear()

        self.salad.emit('playerStop', self)

    async def pause(self, paused: bool = True) -> None:
        """
        Set pause state.
        
        Args:
            paused: True to pause, False to resume. Defaults to True.
        """
        if self.destroyed or self._destroying:
            return

        if paused:
            if not self.playing:
                return
            try:
                await self.nodes._updatePlayer(self.guildId, data={'paused': True}, replace=True)
                self.paused = True
                self.salad.emit('playerPause', self)
            except Exception:
                pass
        else:
            await self.resume()

    async def resume(self) -> None:
        """Resume playback."""
        if self.destroyed or self._destroying or not self.paused:
            return

        try:
            await self.nodes._updatePlayer(self.guildId, data={'paused': False}, replace=True)
            self.paused = False
            self.salad.emit('playerResume', self)
        except Exception:
            pass

    async def setVolume(self, vol: int) -> None:
        """Set volume."""
        if self.destroyed or self._destroying:
            return

        vol = max(0, min(1000, vol))
        old_volume = self.volume
        self.volume = vol

        try:
            await self.nodes._updatePlayer(self.guildId, data={'volume': vol})
            self.salad.emit('playerVolumeChange', self, old_volume, vol)
        except Exception:
            pass

    async def seek(self, position: int) -> None:
        """Seek to position."""
        if self.destroyed or self._destroying or not self.playing:
            return

        try:
            await self.nodes._updatePlayer(self.guildId, data={'position': position})
            self.position = position
            self.salad.emit('playerSeek', self, position)
        except Exception:
            pass

    def addToQueue(self, track: 'AudioTrack') -> bool:
        """
        Add a track to the queue.

        Args:
            track: Track object to add

        Returns:
            bool: True if added successfully, False otherwise
        """
        return self.queue.add(track)

    async def destroy(self, *, cleanup_voice: bool = True) -> None:
        """
        Destroy player and cleanup all resources.

        Args:
            cleanup_voice: If True, calls voice cleanup callback

        Emits playerDestroy event when complete.
        """
        if self.destroyed or self._destroying:
            return

        self._destroying = True

        if self._kickCheckTask and not self._kickCheckTask.done():
            self._kickCheckTask.cancel()
            try:
                await self._kickCheckTask
            except asyncio.CancelledError:
                pass

        if cleanup_voice and self._voiceCleanupCallback and self.guildId:
            try:
                await self._voiceCleanupCallback(self.guildId)
            except Exception as e:
                self.salad.emit('playerVoiceError', self, e)

        if self._voiceUpdateTask and not self._voiceUpdateTask.done():
            try:
                self._voiceUpdateTask.cancel()
            except Exception:
                pass

        self.connected = False
        self.playing = False
        self.paused = False

        local_session = None
        local_session_created = False

        try:
            if (hasattr(self.nodes, 'sessionId') and
                getattr(self.nodes, 'sessionId') and
                hasattr(self.nodes, 'host') and
                hasattr(self.nodes, 'port') and
                self.guildId):

                scheme = 'https' if getattr(self.nodes, 'ssl', False) else 'http'
                uri = (f"{scheme}://{self.nodes.host}:{self.nodes.port}/"
                       f"v4/sessions/{self.nodes.sessionId}/players/{self.guildId}")

                session = getattr(self.nodes, 'session', None)
                if not session:
                    local_session = aiohttp.ClientSession()
                    session = local_session
                    local_session_created = True

                headers = getattr(self.nodes, 'headers', {}) or {}

                try:
                    async with session.delete(uri, headers=headers) as resp:
                        pass
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            if local_session_created and local_session:
                try:
                    await local_session.close()
                except Exception:
                    pass

        try:
            await self.stop()
        except Exception:
            pass

        try:
            self.queue.clear()
        except Exception:
            pass

        try:
            self.queue = NullQueue(self)
        except Exception:
            self.queue = NullQueue()

        self.current = None
        self.currentTrackObj = None
        self.position = 0
        self.playing = False
        self.paused = False
        self.connected = False
        self.volume = 100
        self._voice_client = None

        if cleanup_voice and self._voiceCleanupCallback and self.guildId:
            try:
                await self._voiceCleanupCallback(self.guildId)
            except Exception:
                pass

        if self._voiceUpdateTask and not self._voiceUpdateTask.done():
            self._voiceUpdateTask.cancel()
        self.voiceChannel = None
        self.textChannel = None

        self._voiceCleanupCallback = None
        self.destroyed = True

        try:
            if hasattr(self.nodes, 'players') and isinstance(self.nodes.players, dict):
                self.nodes.players.pop(self.guildId, None)
        except Exception:
            pass

        if hasattr(self.salad, 'destroyPlayer'):
            self.salad.destroyPlayer(self.guildId)

        self.salad.emit('playerDestroy', self, None)
        logger.info(f"Player destroyed for guild {self.guildId}")

    def get_lyrics_handler(self):
        """Returns the lyrics handler from the node if available."""
        if self.nodes and hasattr(self.nodes, 'lyrics'):
            return self.nodes.lyrics
        return None

    def toggle_autoplay(self) -> bool:
        """Toggles the autoplay state."""
        self.autoplay = not self.autoplay
        return self.autoplay
