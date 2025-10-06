# PlayerStateManager.py - Fixed with voice reconnection callback
import asyncio
from pathlib import Path
from typing import Dict, Optional, Any, List, Callable
import logging

try:
    import msgpack
    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False
    try:
        import orjson as json
    except ImportError:
        try:
            import ujson as json
        except ImportError:
            import json

from typing import cast

try:
    import aiofiles
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False

logger = logging.getLogger(__name__)


class PlayerStateManager:
    """Optimized state manager with msgpack and batch operations."""

    __slots__ = ('salad', 'state_file', '_save_task', '_save_interval',
                 '_dirty_players', '_lock', '_batch_size', '_voice_connect_callback')

    def __init__(self, salad, state_file: str = 'player_states.msgpack',
                 save_interval: float = 5.0, batch_size: int = 50):
        self.salad = salad
        self.state_file = Path(state_file)
        self._save_interval = save_interval
        self._save_task: Optional[asyncio.Task] = None
        self._dirty_players: set = set()
        self._lock = asyncio.Lock()
        self._batch_size = batch_size
        self._voice_connect_callback: Optional[Callable] = None

    def set_voice_connect_callback(self, callback: Callable) -> None:
        """
        Set callback to reconnect to Discord voice channel.

        Callback signature: async def callback(guild_id: int, channel_id: str, deaf: bool, mute: bool) -> bool
        Should return True if connection initiated successfully.
        """
        self._voice_connect_callback = callback

    async def start(self) -> None:
        """Start periodic save task."""
        if self._save_task and not self._save_task.done():
            return
        self._save_task = asyncio.create_task(self._periodic_save())

    async def stop(self) -> None:
        """Stop and final save."""
        if self._save_task and not self._save_task.done():
            self._save_task.cancel()
            try:
                await self._save_task
            except asyncio.CancelledError:
                pass
        await self.save_all_states()

    def mark_dirty(self, guild_id: int) -> None:
        """Mark player as dirty."""
        self._dirty_players.add(guild_id)

    async def _periodic_save(self) -> None:
        """Disabled - only save on disconnect."""
        await asyncio.sleep(3600)

    def _serialize_player_state(self, player) -> Optional[Dict]:
        """Fast serialization with minimal checks."""
        if player.destroyed or not player.guildId or not player.voiceChannel:
            return None

        try:
            current_track = None
            if player.currentTrackObj:
                # Store both the encoded track and metadata for restoration
                track_data = {
                    'encoded': getattr(player.currentTrackObj, 'track', None),  # Lavalink encoded track
                    'info': getattr(player.currentTrackObj, 'info', {}),
                }

                # Fallback to URI if no encoded track
                if not track_data['encoded'] and hasattr(player.currentTrackObj, 'uri'):
                    track_data['uri'] = player.currentTrackObj.uri

                current_track = track_data

            queue_tracks = []
            if hasattr(player.queue, '_q') and player.queue._q:
                for track in player.queue._q[:100]:  # Limit to 100 tracks
                    track_data = {
                        'encoded': getattr(track, 'track', None),
                        'info': getattr(track, 'info', {}),
                    }

                    # Fallback to URI
                    if not track_data['encoded'] and hasattr(track, 'uri'):
                        track_data['uri'] = track.uri

                    if track_data.get('encoded') or track_data.get('uri'):
                        queue_tracks.append(track_data)

            return {
                'guildId': str(player.guildId),
                'voiceChannelId': str(player.voiceChannel) if player.voiceChannel else None,
                'textChannelId': str(player.textChannel) if player.textChannel else None,
                'selfDeaf': getattr(player, 'deaf', False),
                'selfMute': getattr(player, 'mute', False),
                'volume': getattr(player, 'volume', 100),
                'paused': getattr(player, 'paused', False),
                'position': getattr(player, 'position', 0),
                'currentTrack': current_track,
                'queue': queue_tracks,
                'queueLoop': getattr(player.queue, 'loop', None),
            }
        except Exception as e:
            logger.debug(f"Serialize error: {e}")
            return None

    async def save_all_states(self) -> int:
        """Save all states with msgpack."""
        async with self._lock:
            states = []
            for player in self.salad.players.values():
                state = self._serialize_player_state(player)
                if state:
                    states.append(state)

            if not states:
                return 0

            try:
                if HAS_MSGPACK:
                    msgpack_data = cast(bytes, msgpack.packb(states, use_bin_type=True))
                    if HAS_AIOFILES:
                        async with aiofiles.open(self.state_file, 'wb') as f:
                            await f.write(msgpack_data)
                    else:
                        with open(self.state_file, 'wb') as f:
                            f.write(msgpack_data)
                else:
                    # Fallback to JSON
                    json_data = cast(str, json.dumps(states))
                    if HAS_AIOFILES:
                        async with aiofiles.open(self.state_file, 'w') as f:
                            await f.write(json_data)
                    else:
                        with open(self.state_file, 'w') as f:
                            f.write(json_data)

                self._dirty_players.clear()
                return len(states)
            except Exception as e:
                logger.error(f"Save failed: {e}")
                return 0

    async def load_states(self) -> List[Dict]:
        """Load states with msgpack."""
        if not self.state_file.exists():
            return []

        try:
            if HAS_MSGPACK:
                if HAS_AIOFILES:
                    async with aiofiles.open(self.state_file, 'rb') as f:
                        data = await f.read()
                else:
                    with open(self.state_file, 'rb') as f:
                        data = f.read()
                return msgpack.unpackb(data, raw=False)
            else:
                if HAS_AIOFILES:
                    async with aiofiles.open(self.state_file, 'r') as f:
                        data = await f.read()
                else:
                    with open(self.state_file, 'r') as f:
                        data = f.read()
                return json.loads(data)
        except Exception as e:
            logger.error(f"Load failed: {e}")
            return []

    async def restore_player(self, state: Dict, node) -> Optional[Any]:
        """Restore single player with proper voice reconnection."""
        try:
            guild_id = int(state['guildId'])
            voice_channel_id = state.get('voiceChannelId')

            if not voice_channel_id:
                logger.warning(f"No voice channel ID for guild {guild_id}, skipping")
                return None

            # Destroy existing player completely before restoration
            if guild_id in self.salad.players:
                existing = self.salad.players[guild_id]
                logger.info(f"Destroying existing player for guild {guild_id} before restoration")
                try:
                    await existing.destroy(cleanup_voice=True)
                    await asyncio.sleep(0.5)  # Wait for cleanup
                except Exception as e:
                    logger.debug(f"Error destroying existing player: {e}")

                # Force remove from players dict
                if guild_id in self.salad.players:
                    del self.salad.players[guild_id]

            # Step 1: Reconnect to Discord voice channel
            if self._voice_connect_callback:
                logger.info(f"Reconnecting to voice channel {voice_channel_id} in guild {guild_id}")
                try:
                    deaf = state.get('selfDeaf', False)
                    mute = state.get('selfMute', False)

                    # Call the callback to reconnect to Discord voice
                    voice_connected = await self._voice_connect_callback(
                        guild_id,
                        voice_channel_id,
                        deaf,
                        mute
                    )

                    if not voice_connected:
                        logger.error(f"Failed to reconnect to voice channel for guild {guild_id}")
                        return None

                    # Wait for Discord voice updates to propagate
                    await asyncio.sleep(1.0)

                except Exception as e:
                    logger.error(f"Voice reconnection callback failed: {e}")
                    return None
            else:
                logger.warning("No voice connect callback set! Player cannot reconnect to Discord.")
                return None

            # Step 2: Create player with Lavalink
            opts = {
                'guildId': guild_id,
                'voiceChannel': voice_channel_id,
                'textChannel': state.get('textChannelId'),
                'deaf': state.get('selfDeaf', True),
                'mute': state.get('selfMute', False),
                'volume': state.get('volume', 100)
            }

            player = await self.salad.createPlayer(node, opts)
            if not player:
                logger.error(f"Failed to create player for guild {guild_id}")
                return None

            # Wait for player to be fully connected
            max_wait = 10  # seconds
            waited = 0
            while not player.connected and waited < max_wait:
                await asyncio.sleep(0.2)
                waited += 0.2

            if not player.connected:
                logger.error(f"Player did not connect within {max_wait}s")
                await player.destroy()
                return None

            logger.info(f"Player connected for guild {guild_id}")

            # Set volume if not default
            if state.get('volume', 100) != 100:
                await player.setVolume(state['volume'])

            # Set loop mode
            loop_mode = state.get('queueLoop')
            if loop_mode and loop_mode != 'off':
                if hasattr(player.queue, 'setLoop'):
                    player.queue.setLoop(loop_mode)

            # Restore tracks
            current = state.get('currentTrack')
            queue_tracks = state.get('queue', [])

            logger.info(f"Restoring {len(queue_tracks)} queue tracks for guild {guild_id}")

            # First, add all queue tracks
            for i, track_data in enumerate(queue_tracks[:self._batch_size]):
                try:
                    track = None

                    # Try to use encoded track directly if available
                    if track_data.get('encoded'):
                        # Create track object from encoded data
                        from Salad.Track import Track
                        track = Track({
                            'encoded': track_data['encoded'],
                            'info': track_data.get('info', {})
                        }, requester=None)
                    # Fallback to resolving URI
                    elif track_data.get('uri'):
                        queue_result = await self.salad.resolve(
                            track_data['uri'],
                            requester=None,
                            nodes=[node]
                        )
                        if queue_result and queue_result.get('tracks'):
                            track = queue_result['tracks'][0]

                    if track:
                        player.addToQueue(track)
                        logger.debug(f"Added queue track {i+1}/{len(queue_tracks[:self._batch_size])}")

                except Exception as e:
                    logger.debug(f"Failed to restore queue track {i+1}: {e}")

            # Then handle current track
            if current:
                try:
                    logger.info(f"Restoring current track")
                    current_track = None

                    # Try encoded track first
                    if current.get('encoded'):
                        from Salad.Track import Track
                        current_track = Track({
                            'encoded': current['encoded'],
                            'info': current.get('info', {})
                        }, requester=None)
                    # Fallback to URI resolution
                    elif current.get('uri'):
                        result = await self.salad.resolve(current['uri'], requester=None, nodes=[node])
                        if result and result.get('tracks'):
                            current_track = result['tracks'][0]

                    if current_track:

                        # Insert at front of queue
                        player.queue.insert(current_track, 0)
                        logger.info("Inserted current track at front of queue")

                        # Start playback
                        await player.play()
                        logger.info("Started playback")

                        # Wait briefly for track to start
                        await asyncio.sleep(0.5)

                        # Apply saved position if not paused
                        if not state.get('paused', False):
                            position = state.get('position', 0)
                            if position > 1000:  # Only seek if more than 1 second
                                logger.info(f"Seeking to position {position}ms")
                                await player.seek(position)

                        # Apply paused state
                        if state.get('paused', False):
                            logger.info("Pausing player")
                            await player.pause()

                except Exception as e:
                    logger.error(f"Failed to restore current track: {e}")
                    # Try to play from queue if current track fails
                    if len(player.queue) > 0:
                        logger.info("Attempting to play from queue after current track failure")
                        try:
                            await player.play()
                        except Exception as play_error:
                            logger.error(f"Failed to play from queue: {play_error}")

            elif len(player.queue) > 0:
                # No current track but queue exists - start playing
                logger.info("No current track, starting playback from queue")
                try:
                    await player.play()
                except Exception as e:
                    logger.error(f"Failed to start playback: {e}")

            self.salad.emit('playerRestored', player, state)
            logger.info(f"Successfully restored player for guild {guild_id}")
            return player

        except Exception as e:
            logger.error(f"Player restore failed for guild {state.get('guildId')}: {e}")
            return None

    async def restore_all_players(self, node=None) -> int:
        """Restore all with concurrency limit."""
        states = await self.load_states()
        if not states:
            return 0

        if not node:
            node = self.salad._getReqNode()
        if not node:
            return 0

        # Batch restore with concurrency limit
        semaphore = asyncio.Semaphore(5)  # Lower concurrency for voice connections

        async def restore_with_limit(state):
            async with semaphore:
                return await self.restore_player(state, node)

        tasks = [restore_with_limit(state) for state in states]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        restored = sum(1 for r in results if r and not isinstance(r, Exception))
        logger.info(f"Restored {restored}/{len(states)} players")
        return restored

    async def clear_states(self) -> None:
        """Clear saved states."""
        try:
            if self.state_file.exists():
                self.state_file.unlink()
        except Exception:
            pass