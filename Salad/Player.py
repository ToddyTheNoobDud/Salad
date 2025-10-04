from .Queue import Queue
import asyncio
import aiohttp
from typing import Optional, Dict, Any, Callable

__all__ = ('Player', 'NullQueue')


class NullQueue:
    """Minimal no-op queue used after destroy to prevent further operations."""
    __slots__ = ('_q', 'loop')

    def __init__(self, player=None):
        self._q = []
        self.loop = None

    def add(self, item):
        return None

    def insert(self, item, idx=0):
        return None

    def clear(self):
        self._q.clear()

    def getNext(self):
        return None

    def consumeNext(self):
        return None

    def __len__(self):
        return 0

    @property
    def queue(self):
        return []


class Player:
    """
    High-performance player with:
    - Non-blocking voice updates with debouncing
    - Efficient state management
    - Proper event emission for all state changes
    - Thread-safe destroy with cleanup
    - Built-in voice connection management helpers
    - Automatic queue advancement on track end
    """

    __slots__ = ('salad', 'nodes', 'guildId', 'voiceChannel', 'textChannel',
                 'mute', 'deaf', 'playing', 'destroyed', 'current',
                 'currentTrackObj', 'position', 'timestamp', 'ping',
                 'connected', 'volume', '_voiceState', '_lastVoiceUpdate',
                 'paused', 'queue', '_playLock', '_voiceUpdateTask',
                 '_destroying', '_voiceConnectAttempts', '_lastVoiceConnect',
                 '_voiceCleanupCallback', '_trackEndHandled', '__weakref__')

    def __init__(self, salad, nodes, opts: Optional[Dict] = None):
        opts = opts or {}
        self.salad = salad
        self.nodes = nodes
        self.guildId: Optional[int] = opts.get('guildId')
        self.voiceChannel: Optional[str] = opts.get('voiceChannel')
        self.textChannel: Optional[str] = opts.get('textChannel')
        self.mute: bool = opts.get('mute', False)
        self.deaf: bool = opts.get('deaf', True)

        # Playback state
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

        # Voice state
        self._voiceState: Dict = {'voice': {}}
        self._lastVoiceUpdate: Dict = {}
        self._voiceConnectAttempts: int = 0
        self._lastVoiceConnect: float = 0

        # Queue and locks
        self.queue = Queue(self)
        self._playLock = asyncio.Lock()
        self._voiceUpdateTask: Optional[asyncio.Task] = None
        self._destroying: bool = False
        self._trackEndHandled: bool = False

        # Callback for voice cleanup (set by bot)
        self._voiceCleanupCallback: Optional[Callable] = None

    def setVoiceCleanupCallback(self, callback: Callable) -> None:
        """
        Set callback function for voice cleanup.
        This allows the bot to handle discord.py-specific cleanup.

        Callback should be: async def cleanup(guild_id: int) -> None
        """
        self._voiceCleanupCallback = callback

    def isVoiceReady(self) -> bool:
        """Check if voice state is ready for connection."""
        vd = self._voiceState.get('voice', {})
        return bool(
            vd.get('session_id') and
            vd.get('token') and
            vd.get('endpoint')
        )

    def getVoiceState(self) -> Dict:
        """Get current voice state for debugging."""
        return {
            'connected': self.connected,
            'ready': self.isVoiceReady(),
            'channel': self.voiceChannel,
            'session_id': self._voiceState.get('voice', {}).get('session_id'),
            'has_token': bool(self._voiceState.get('voice', {}).get('token')),
            'has_endpoint': bool(self._voiceState.get('voice', {}).get('endpoint')),
            'connect_attempts': self._voiceConnectAttempts,
        }

    def resetVoiceState(self) -> None:
        """Reset voice state for reconnection."""
        self._voiceState = {'voice': {}}
        self._lastVoiceUpdate = {}
        self.connected = False
        self._voiceConnectAttempts = 0

    async def connect(self, opts: Optional[Dict] = None) -> None:
        """Connect player to voice channel."""
        opts = opts or {}
        vc = opts.get('vc', self.voiceChannel)

        if not vc:
            return

        # Allow reconnection after remote destroy
        if self.destroyed:
            self.destroyed = False
            self._destroying = False
            self.connected = False
            self.playing = False
            self.paused = False
            self.current = None
            self.currentTrackObj = None
            self.position = 0
            self.resetVoiceState()

        self._voiceConnectAttempts += 1
        self._lastVoiceConnect = asyncio.get_event_loop().time()

        self.salad.emit('playerConnect', self)

    async def handleVoiceStateUpdate(self, data: Dict) -> None:
        """Handle voice state update from Discord."""
        if self.destroyed or self._destroying:
            return

        cid = data.get('channel_id')
        sid = data.get('session_id')

        if sid:
            self._voiceState['voice']['session_id'] = sid

        self.voiceChannel = cid if cid else None

        # If disconnected from voice, mark as not connected
        if cid is None:
            self.connected = False

        # Debounce voice updates
        self._scheduleVoiceUpdate()

        self.salad.emit('playerVoiceStateUpdate', self, data)

    async def handleVoiceServerUpdate(self, data: Dict) -> None:
        """Handle voice server update from Discord."""
        if self.destroyed or self._destroying:
            return

        self._voiceState['voice']['token'] = data['token']
        self._voiceState['voice']['endpoint'] = data['endpoint']

        # Debounce voice updates
        self._scheduleVoiceUpdate()

        self.salad.emit('playerVoiceServerUpdate', self, data)

    def _scheduleVoiceUpdate(self) -> None:
        """Debounce voice updates to prevent spam."""
        if self.destroyed or self._destroying:
            return

        # Cancel pending update
        if self._voiceUpdateTask and not self._voiceUpdateTask.done():
            self._voiceUpdateTask.cancel()

        # Schedule new update
        self._voiceUpdateTask = asyncio.create_task(self._debouncedDispatch())

    async def _debouncedDispatch(self) -> None:
        """Wait briefly to batch voice updates."""
        try:
            await asyncio.sleep(0.05)  # 50ms debounce
            await self._dispatchVoiceUpdate()
        except asyncio.CancelledError:
            pass

    async def _dispatchVoiceUpdate(self) -> None:
        """Send voice update to Lavalink node."""
        if self.destroyed or self._destroying:
            return

        data = self._voiceState['voice']
        sid = data.get('session_id')
        token = data.get('token')
        endpoint = data.get('endpoint')

        # Fast fail: missing required data
        if not (sid and token and endpoint):
            return

        # Fast fail: duplicate update
        if (self._lastVoiceUpdate.get('session_id') == sid and
            self._lastVoiceUpdate.get('token') == token and
            self._lastVoiceUpdate.get('endpoint') == endpoint):
            return

        # Fast fail: node not ready
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
            self.salad.emit('playerVoiceError', self, e)

    async def handlePlayerUpdate(self, data: Dict) -> None:
        """Handle player update event from Lavalink."""
        if self.destroyed or self._destroying:
            return

        # Position
        if 'position' in data and data['position'] is not None:
            try:
                self.position = int(data['position'])
            except (ValueError, TypeError):
                pass

        # Volume
        if 'volume' in data and data['volume'] is not None:
            try:
                self.volume = int(data['volume'])
            except (ValueError, TypeError):
                pass

        # Paused state
        if 'paused' in data:
            self.paused = bool(data['paused'])

        # Track handling
        encoded = None
        if 'track' in data and data['track'] is not None:
            tr = data['track']
            if isinstance(tr, dict):
                encoded = tr.get('encoded') or tr.get('identifier')
            else:
                encoded = tr
        else:
            encoded = data.get('encodedTrack') or data.get('identifier')

        if encoded is None:
            # Null track = stop
            self.playing = False
            self.current = None
            self.currentTrackObj = None
            if 'position' not in data:
                self.position = 0
        else:
            self.current = encoded
            self.playing = True

        # Voice state in update
        if 'voice' in data and data['voice'] is not None:
            vd = data['voice']
            sid = vd.get('sessionId') or vd.get('session_id')
            token = vd.get('token')
            endpoint = vd.get('endpoint')

            if sid:
                self._voiceState['voice']['session_id'] = sid
            if token:
                self._voiceState['voice']['token'] = token
            if endpoint:
                self._voiceState['voice']['endpoint'] = endpoint

            self._scheduleVoiceUpdate()

        self.salad.emit('playerUpdate', self, data)

    async def handleTrackEnd(self, data: Dict) -> None:
        """
        Handle track end event from Lavalink.
        Automatically advances queue and plays next track.
        """
        if self.destroyed or self._destroying:
            return

        # Prevent duplicate handling
        if self._trackEndHandled:
            return
        self._trackEndHandled = True

        reason = data.get('reason', 'unknown')
        ended_track = self.currentTrackObj

        # Clear current track
        self.current = None
        self.currentTrackObj = None
        self.position = 0
        self.playing = False

        # Emit track end event
        self.salad.emit('trackEnd', self, ended_track, reason)

        # Handle based on reason
        if reason == 'finished':
            # Track finished naturally - consume from queue and play next
            if self.queue.loop == 'track':
                # Loop current track - re-add to front
                if ended_track:
                    self.queue.insert(ended_track, 0)
            else:
                # Normal mode or queue loop - consume the track
                consumed = self.queue.consumeNext()

                if self.queue.loop == 'queue' and consumed:
                    # Queue loop mode - add consumed track to end
                    self.queue.add(consumed)

            # Play next track
            if len(self.queue) > 0:
                asyncio.create_task(self._playNext())
            else:
                self.salad.emit('queueEnd', self)

        elif reason == 'loadFailed':
            # Track failed to load - consume and try next
            self.queue.consumeNext()
            self.salad.emit('trackError', self, ended_track, Exception('Track failed to load'))

            if len(self.queue) > 0:
                asyncio.create_task(self._playNext())
            else:
                self.salad.emit('queueEnd', self)

        elif reason == 'stopped':
            # Manually stopped - don't auto-play next
            pass

        elif reason == 'replaced':
            # Track was replaced - don't consume, new track is already playing
            pass

        elif reason == 'cleanup':
            # Cleanup - don't do anything
            pass

    async def _playNext(self) -> None:
        """Internal method to play next track with small delay."""
        await asyncio.sleep(0.1)  # Small delay to prevent race conditions
        self._trackEndHandled = False
        await self.play()

    async def handlePlayerDestroyed(self, data: Optional[Dict] = None) -> None:
        """Handle player destroyed event from Lavalink."""
        if self.destroyed or self._destroying:
            return

        self._destroying = True

        # Call voice cleanup callback if set
        if self._voiceCleanupCallback and self.guildId:
            try:
                await self._voiceCleanupCallback(self.guildId)
            except Exception as e:
                self.salad.emit('playerVoiceError', self, e)

        # Cancel voice updates
        if self._voiceUpdateTask and not self._voiceUpdateTask.done():
            self._voiceUpdateTask.cancel()

        # Clear queue locally
        try:
            self.queue.clear()
        except Exception:
            pass

        # Reset state
        self.current = None
        self.currentTrackObj = None
        self.position = 0
        self.playing = False
        self.paused = False
        self.connected = False
        self.destroyed = True
        self.resetVoiceState()

        # Remove from node players
        try:
            if hasattr(self.nodes, 'players') and self.guildId in self.nodes.players:
                del self.nodes.players[self.guildId]
        except Exception:
            pass

        # Remove from salad players
        if hasattr(self.salad, 'destroyPlayer'):
            self.salad.destroyPlayer(self.guildId)

        self.salad.emit('playerDestroy', self, data)

    async def play(self) -> None:
        """
        Play next track from queue.
        Track is peeked (not removed) - removed when track ends.
        """
        async with self._playLock:
            # Reset track end handler flag
            self._trackEndHandled = False

            # Fast fail checks
            if self.destroyed or self._destroying:
                return

            # Check voice state
            if not self.isVoiceReady():
                self.salad.emit('playerVoiceError', self,
                              Exception('Voice state not ready for playback'))
                return

            if not self.connected:
                self.salad.emit('playerVoiceError', self,
                              Exception('Not connected to Lavalink'))
                return

            # Check queue
            if len(self.queue) == 0:
                self.playing = False
                self.current = None
                self.currentTrackObj = None
                self.salad.emit('queueEnd', self)
                return

            # Peek next track (don't remove - removed on track end)
            item = self.queue.getNext()
            if not item:
                self.playing = False
                self.current = None
                self.currentTrackObj = None
                return

            try:
                self.currentTrackObj = item

                # Resolve track encoding
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
                    self.current = None
                    self.currentTrackObj = None
                    return

                # Send play request
                playData = {
                    'encodedTrack': self.current,
                    'position': 0,
                    'volume': self.volume,
                    'paused': False
                }

                await self.nodes._updatePlayer(self.guildId, data=playData)

                # Update state
                self.position = 0
                self.playing = True
                self.paused = False

                self.salad.emit('trackStart', self, item)

            except Exception as e:
                # On error, consume failed track and try next
                self.playing = False
                self.current = None
                self.currentTrackObj = None

                # Consume the failed track
                self.queue.consumeNext()

                self.salad.emit('trackError', self, item, e)

                # Try next track
                if len(self.queue) > 0:
                    asyncio.create_task(self._playNext())

    def addToQueue(self, item: Any) -> Optional[bool]:
        """Add track to queue without sending to Lavalink."""
        if self.destroyed or self._destroying:
            return None

        result = self.queue.add(item)
        if result:
            self.salad.emit('trackAdd', self, item)
        return result

    async def skip(self) -> None:
        """Skip current track and play next."""
        if self.destroyed or self._destroying:
            return

        prev_track = self.currentTrackObj

        # Send stop to Lavalink (this will trigger trackEnd with reason 'stopped')
        try:
            await self.nodes._updatePlayer(self.guildId, data={'encodedTrack': None})
        except Exception:
            pass

        # Consume the skipped track
        self.queue.consumeNext()

        # Clear current
        self.current = None
        self.currentTrackObj = None
        self.position = 0
        self.playing = False

        self.salad.emit('trackSkip', self, prev_track)

        # Play next
        if len(self.queue) > 0:
            asyncio.create_task(self._playNext())
        else:
            self.salad.emit('queueEnd', self)

    async def stop(self) -> None:
        """Stop playback and clear queue."""
        if self.destroyed or self._destroying:
            return

        try:
            await self.nodes._updatePlayer(self.guildId, data={'encodedTrack': None})
        except Exception:
            pass

        self.queue.clear()
        self.current = None
        self.currentTrackObj = None
        self.position = 0
        self.playing = False
        self.paused = False

        self.salad.emit('playerStop', self)

    async def pause(self) -> None:
        """Pause current track."""
        if self.destroyed or self._destroying or not self.playing:
            return

        try:
            await self.nodes._updatePlayer(self.guildId, data={'paused': True})
            self.paused = True
            self.salad.emit('playerPause', self)
        except Exception:
            pass

    async def resume(self) -> None:
        """Resume paused track."""
        if self.destroyed or self._destroying or not self.paused:
            return

        try:
            await self.nodes._updatePlayer(self.guildId, data={'paused': False})
            self.paused = False
            self.salad.emit('playerResume', self)
        except Exception:
            pass

    async def setVolume(self, vol: int) -> None:
        """Set player volume (0-1000)."""
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
        """Seek to position in current track (milliseconds)."""
        if self.destroyed or self._destroying or not self.playing:
            return

        try:
            await self.nodes._updatePlayer(self.guildId, data={'position': position})
            self.position = position
            self.salad.emit('playerSeek', self, position)
        except Exception:
            pass

    def setLoop(self, mode: Optional[str] = None) -> None:
        """
        Set loop mode.

        Args:
            mode: 'track' to loop current track, 'queue' to loop queue, None for no loop
        """
        if mode not in [None, 'track', 'queue']:
            raise ValueError("Loop mode must be None, 'track', or 'queue'")

        self.queue.loop = mode
        self.salad.emit('playerLoopChange', self, mode)

    async def reconnect(self) -> bool:
        """
        Attempt to reconnect to voice.
        Returns True if reconnection was initiated.
        """
        if self.destroyed or self._destroying:
            return False

        # Reset voice state
        self.resetVoiceState()

        # Call voice cleanup callback to disconnect old connection
        if self._voiceCleanupCallback and self.guildId:
            try:
                await self._voiceCleanupCallback(self.guildId)
            except Exception as e:
                self.salad.emit('playerVoiceError', self, e)
                return False

        self.salad.emit('playerReconnect', self)
        return True

    async def destroy(self, *, cleanup_voice: bool = True) -> None:
        """
        Destroy player and cleanup all resources.

        Args:
            cleanup_voice: If True, calls voice cleanup callback

        Emits playerDestroy event when complete.
        """
        # Prevent multiple simultaneous destroys
        if self.destroyed or self._destroying:
            return

        self._destroying = True

        # Call voice cleanup callback if requested and available
        if cleanup_voice and self._voiceCleanupCallback and self.guildId:
            try:
                await self._voiceCleanupCallback(self.guildId)
            except Exception as e:
                self.salad.emit('playerVoiceError', self, e)

        # Cancel voice updates immediately
        if self._voiceUpdateTask and not self._voiceUpdateTask.done():
            try:
                self._voiceUpdateTask.cancel()
            except Exception:
                pass

        # Mark as disconnected immediately
        self.connected = False
        self.playing = False
        self.paused = False

        # Try to remove from Lavalink (best-effort)
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
                        pass  # Ignore response
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

        # Stop playback locally
        try:
            await self.stop()
        except Exception:
            pass

        # Clear queue
        try:
            self.queue.clear()
        except Exception:
            pass

        # Replace with null queue to prevent further operations
        try:
            self.queue = NullQueue(self)
        except Exception:
            self.queue = NullQueue()

        # Clear all state
        self.current = None
        self.currentTrackObj = None
        self.position = 0
        self.playing = False
        self.paused = False
        self.connected = False
        self.volume = 100

        # Clear voice state
        self.resetVoiceState()
        self.voiceChannel = None
        self.textChannel = None

        # Clear cleanup callback reference
        self._voiceCleanupCallback = None

        # Mark as destroyed
        self.destroyed = True

        # Remove from node players
        try:
            if hasattr(self.nodes, 'players') and isinstance(self.nodes.players, dict):
                self.nodes.players.pop(self.guildId, None)
        except Exception:
            pass

        # Remove from salad players
        if hasattr(self.salad, 'destroyPlayer'):
            self.salad.destroyPlayer(self.guildId)

        # Emit destroy event
        self.salad.emit('playerDestroy', self, None)