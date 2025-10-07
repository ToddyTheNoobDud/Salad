from typing import Optional, Dict, Any, Callable
import asyncio
import aiohttp
import logging

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
        '_kickCheckTask', '_lastVoiceChannelId', '__weakref__'
    )

    def __init__(self, salad, nodes, opts: Optional[Dict] = None):
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
        self.currentTrackObj: Optional[Any] = None
        self.position: int = 0
        self.timestamp: int = 0
        self.ping: int = 0
        self.connected: bool = False
        self.volume: int = opts.get('volume', 100)
        self.paused: bool = False

        self._voiceState: Dict = {'voice': {}}
        self._lastVoiceUpdate: Dict = {}

        from .Queue import Queue
        self.queue = Queue(self)
        self._playLock = asyncio.Lock()
        self._voiceUpdateTask: Optional[asyncio.Task] = None
        self._destroying: bool = False
        self._trackEndHandled: bool = False
        self._voiceCleanupCallback: Optional[Callable] = None
        self._kickCheckTask: Optional[asyncio.Task] = None
        self._lastVoiceChannelId: Optional[str] = None

    def setVoiceCleanupCallback(self, callback: Callable) -> None:
        """Set voice cleanup callback."""
        self._voiceCleanupCallback = callback

    def isVoiceReady(self) -> bool:
        """Check if voice ready."""
        vd = self._voiceState.get('voice', {})
        return bool(vd.get('session_id') and vd.get('token') and vd.get('endpoint'))

    async def connect(self, opts: Optional[Dict] = None) -> None:
        """Connect to voice."""
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
        self.salad.emit('playerConnect', self)

    async def handleVoiceStateUpdate(self, data: Dict) -> None:
        """Handle voice state update with kick detection."""
        if self.destroyed or self._destroying:
            return

        cid = data.get('channel_id')
        sid = data.get('session_id')
        user_id = data.get('user_id')

        # Only process if it's for this bot
        if user_id and str(user_id) != str(self.salad.clientId):
            return

        if sid:
            self._voiceState['voice']['session_id'] = sid

        old_channel = self.voiceChannel
        new_channel = cid

        # Bot was KICKED/DISCONNECTED (moved to no channel)
        if old_channel and not new_channel:
            logger.warning(f'Bot disconnected from voice in guild {self.guildId}')

            # Cancel any existing kick check
            if self._kickCheckTask and not self._kickCheckTask.done():
                self._kickCheckTask.cancel()

            # Schedule delayed kick check
            self._kickCheckTask = asyncio.create_task(self._handleKickCheck())
            return await self.destroy(cleanup_voice=True)

        # Bot was MOVED to different channel
        if old_channel and new_channel and old_channel != new_channel:
            logger.info(f'Bot moved from channel {old_channel} to {new_channel} in guild {self.guildId}')
            self.voiceChannel = new_channel
            self._lastVoiceChannelId = new_channel

            # Emit playerMove event
            self.salad.emit('playerMove', self, old_channel, new_channel)

            # Schedule voice update
            self._scheduleVoiceUpdate()
            return

        # Normal channel update
        self.voiceChannel = new_channel
        if new_channel:
            self._lastVoiceChannelId = new_channel
            self.connected = bool(new_channel)

        self._scheduleVoiceUpdate()
        self.salad.emit('playerVoiceStateUpdate', self, data)

    async def _handleKickCheck(self) -> None:
        """Check if disconnect was a kick after a delay."""
        try:
            # Wait to see if it's temporary
            await asyncio.sleep(1.5)

            # If still no voice channel, it's a kick
            if not self.voiceChannel and not self.destroyed and not self._destroying:
                logger.info(f'Confirmed kick for guild {self.guildId}, destroying player')

                # Emit kick event
                self.salad.emit('playerKick', self)

                # Destroy player (without voice cleanup since already disconnected)
                await self.destroy(cleanup_voice=False)

        except asyncio.CancelledError:
            # Reconnected before timeout
            logger.debug(f'Kick check cancelled for guild {self.guildId}')
        except Exception as e:
            logger.error(f'Error in kick check: {e}')

    async def handleVoiceServerUpdate(self, data: Dict) -> None:
        """Handle voice server update."""
        if self.destroyed or self._destroying:
            return

        self._voiceState['voice']['token'] = data['token']
        self._voiceState['voice']['endpoint'] = data['endpoint']

        # Cancel kick check if we got server update (means reconnecting)
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

        # Stop current track explicitly with REPLACE=True to force stop
        try:
            await self.nodes._updatePlayer(self.guildId, data={'encodedTrack': None}, replace=True)
        except Exception as e:
            logger.debug(f"Skip stop failed: {e}")

        # Consume from queue AFTER stopping
        if self.queue.loop != 'track':
            self.queue.consumeNext()

        # Clear current track state
        self.current = None
        self.currentTrackObj = None
        self.position = 0
        self.playing = False

        self.salad.emit('trackSkip', self, prev_track)

        # Wait briefly for Lavalink to process stop
        await asyncio.sleep(0.2)

        # Play next track if available
        if len(self.queue) > 0:
            await self.play()
        else:
            self.salad.emit('queueEnd', self)

    async def stop(self) -> None:
        """Stop playback and clear queue."""
        if self.destroyed or self._destroying:
            return

        # Stop current track first with REPLACE=True to force stop
        was_playing = self.playing

        try:
            if was_playing or self.current:
                await self.nodes._updatePlayer(self.guildId, data={'encodedTrack': None}, replace=True)
        except Exception as e:
            logger.debug(f"Stop track failed: {e}")

        # Clear state
        self.current = None
        self.currentTrackObj = None
        self.position = 0
        self.playing = False
        self.paused = False

        # Clear queue after stopping
        self.queue.clear()

        self.salad.emit('playerStop', self)

    async def pause(self) -> None:
        """Pause playback."""
        if self.destroyed or self._destroying or not self.playing:
            return

        try:
            await self.nodes._updatePlayer(self.guildId, data={'paused': True}, replace=True)
            self.paused = True
            self.salad.emit('playerPause', self)
        except Exception:
            pass

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

    def addToQueue(self, track) -> bool:
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