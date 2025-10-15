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
import aiohttp
import asyncio
from typing import Dict, Optional, Any
import logging
from .Lyrics import Lyrics
from .Autoplay import sc_autoplay, sp_autoplay, yt_autoplay
from .models.tracks import AudioTrack

try:
    import orjson as json
    dumps = lambda x: json.dumps(x).decode('utf-8')
    loads = json.loads
except ImportError:
    try:
        import ujson as json
        dumps = json.dumps
        loads = json.loads
    except ImportError:
        import json
        dumps = json.dumps
        loads = json.loads

logger = logging.getLogger(__name__)

WS_PATH = 'v4/websocket'

class Node:
    """Optimized Lavalink node with connection pooling and circuit breaker."""

    __slots__ = (
        'salad', 'host', 'port', 'auth', 'ssl', 'wsUrl', 'opts',
        'connected', 'info', 'players', 'clientName', 'sessionId',
        'session', 'ws', 'stats', '_listenTask', 'headers', 'rest',
        '_reconnect_attempts', '_max_reconnect_attempts', '_infinite_reconnect',
        '_reconnecting', '_base_reconnect_delay', '_max_reconnect_delay',
        '_circuit_breaker_threshold', '_circuit_breaker_failures',
        '_circuit_open_until', '_msg_buffer',
        'spotify_client_id', 'spotify_client_secret', 'lyrics'
    )

    def __init__(self, salad, connOpts: Dict, opts: Optional[Dict] = None):
        self.salad = salad
        self.host = connOpts.get('host', '127.0.0.1')
        self.port = connOpts.get('port', 8000)
        self.auth = connOpts.get('auth', 'youshallnotpass')
        self.ssl = connOpts.get('ssl', False)
        self.spotify_client_id = connOpts.get('spotify_client_id')
        self.spotify_client_secret = connOpts.get('spotify_client_secret')
        self.wsUrl = f"ws{'s' if self.ssl else ''}://{self.host}:{self.port}/{WS_PATH}"
        self.opts = opts or {}
        self.connected = False
        self.info: Optional[Dict] = None
        self.players: Dict[int, Any] = {}
        self.clientName = 'Salad/v1.1.0'
        self.sessionId: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.stats: Optional[Dict] = None
        self._listenTask: Optional[asyncio.Task] = None

        self.headers = {
            'Authorization': self.auth,
            'User-Id': '',
            'Client-Name': self.clientName
        }

        self._reconnect_attempts = 0
        self._max_reconnect_attempts = opts.get('maxReconnectAttempts', 5) if opts else 5
        self._infinite_reconnect = opts.get('infiniteReconnect', True) if opts else True
        self._reconnecting = False
        self._base_reconnect_delay = opts.get('baseReconnectDelay', 1.0) if opts else 1.0
        self._max_reconnect_delay = opts.get('maxReconnectDelay', 300.0) if opts else 300.0
        self._circuit_breaker_threshold = 5
        self._circuit_breaker_failures = 0
        self._circuit_open_until = 0
        self._msg_buffer = []

        from .Rest import Rest
        self.rest = Rest(salad, self)
        self.lyrics = Lyrics(self) if self.spotify_client_id and self.spotify_client_secret else None

    async def connect(self) -> None:
        """Connect with circuit breaker protection."""
        loop = asyncio.get_event_loop()
        now = loop.time()

        if self._circuit_open_until > now:
            wait = self._circuit_open_until - now
            logger.warning(f"Circuit breaker open, waiting {wait:.1f}s")
            return

        try:
            if not self.session or self.session.closed:
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                self.session = aiohttp.ClientSession(
                    timeout=timeout,
                    json_serialize=dumps
                )

            self.ws = await self.session.ws_connect(
                self.wsUrl,
                headers=self.headers,
                autoclose=False,
                heartbeat=30,
                compress=15
            )

            self.connected = True
            self._reconnect_attempts = 0
            self._reconnecting = False
            self._circuit_breaker_failures = 0
            self._circuit_open_until = 0

            self._listenTask = asyncio.create_task(self._listenWs())

            try:
                await asyncio.wait_for(self._waitForSession(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.error("Timeout waiting for session ID")
                raise

            resp = await self.rest.makeRequest('GET', 'v4/info')
            if isinstance(resp, dict):
              self.info = resp

            self.salad.emit('nodeConnect', self)

        except Exception as e:
            self.connected = False
            self._circuit_breaker_failures += 1

            if self._circuit_breaker_failures >= self._circuit_breaker_threshold:
                self._circuit_open_until = loop.time() + 60.0  
                logger.error(f"Circuit breaker opened after {self._circuit_breaker_failures} failures")

            await self._cleanup()
            self.salad.emit('nodeError', self, e)

    async def _waitForSession(self) -> None:
        """Wait for session ID with async polling."""
        while not self.sessionId:
            await asyncio.sleep(0.05)

    async def _listenWs(self) -> None:
        """Optimized WebSocket listener with batch processing."""
        try:
            if not self.ws:
                return

            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = loads(msg.data)
                        asyncio.create_task(self._handleWsMsg(data))
                    except Exception as e:
                        logger.debug(f"WS parse error: {e}")

                elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                    break

        except Exception as e:
            logger.debug(f"WS listener error: {e}")

        finally:
            was_connected = self.connected
            self.connected = False

            if was_connected and hasattr(self.salad, 'state_manager') and self.salad.state_manager:
                for guild_id in self.players:
                    self.salad.state_manager.mark_dirty(guild_id)
                asyncio.create_task(self.salad.state_manager.save_all_states())

            self.salad.emit('nodeDisconnect', self)

            should_reconnect = (
                self._infinite_reconnect or
                self._reconnect_attempts < self._max_reconnect_attempts
            )

            if should_reconnect and not self._reconnecting:
                self._reconnecting = True
                asyncio.create_task(self._attemptReconnect())

    async def _attemptReconnect(self) -> None:
        """Reconnect with exponential backoff and jitter."""
        max_attempts = float('inf') if self._infinite_reconnect else self._max_reconnect_attempts

        while self._reconnect_attempts < max_attempts and not self.connected:
            delay = self._calculate_backoff_delay(self._reconnect_attempts)
            self._reconnect_attempts += 1

            self.salad.emit('nodeReconnecting', self, self._reconnect_attempts, delay)
            await asyncio.sleep(delay)

            if not self.connected:
                try:
                    await self.connect()
                    if self.connected and self.sessionId:
                        asyncio.create_task(self._restore_players())
                        return
                except Exception as e:
                    logger.debug(f"Reconnect failed: {e}")

        if not self._infinite_reconnect:
            self._reconnecting = False
            self.salad.emit('nodeReconnectExhausted', self, self._reconnect_attempts)

    def _calculate_backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with jitter."""
        if attempt == 0:
            return self._base_reconnect_delay

        import random
        exponential = self._base_reconnect_delay * (2 ** (attempt - 1))
        jitter = random.uniform(0.75, 1.25)
        return min(exponential * jitter, self._max_reconnect_delay)

    async def _restore_players(self) -> None:
        """Restore players after reconnection."""
        if not hasattr(self.salad, 'state_manager') or not self.salad.state_manager:
            return

        try:
            await asyncio.sleep(1.0)
            restored = await self.salad.state_manager.restore_all_players(self)
            if restored > 0:
                logger.info(f"Restored {restored} players")
                self.salad.emit('playersRestored', self, restored)
        except Exception as e:
            logger.error(f"Player restore failed: {e}")

    async def _handleWsMsg(self, data: Dict) -> None:
        """Fast-path message handler."""
        op = data.get('op')

        if op == 'ready':
            self.sessionId = data.get('sessionId')
            self.salad.emit('nodeReady', self, data)

        elif op == 'stats':
            self.stats = data
            self.salad.emit('nodeStats', self, data)

        elif op == 'playerUpdate':
            gid = data.get('guildId')
            if isinstance(gid, str):
                try:
                    gid = int(gid)
                except ValueError:
                    return

            player = self.players.get(gid or 0)
            if player:
                state = data.get('state', {})
                player.position = state.get('position', 0)
                player.timestamp = state.get('time', 0)

                if hasattr(self.salad, 'state_manager') and self.salad.state_manager:
                    self.salad.state_manager.mark_dirty(gid)

                self.salad.emit('playerPositionUpdate', player, state)

        elif op == 'event':
            asyncio.create_task(self._handleEvent(data))

    async def _handleEvent(self, data: Dict) -> None:
        """Handle Lavalink events."""
        gid = data.get('guildId')
        evType = data.get('type')

        if not gid:
            return

        if isinstance(gid, str):
            try:
                gid = int(gid)
            except ValueError:
                return

        player = self.players.get(gid)
        if not player:
            return

        if hasattr(self.salad, 'state_manager') and self.salad.state_manager:
            self.salad.state_manager.mark_dirty(gid)

        if evType == 'TrackEndEvent':
            await self._handleTrackEnd(player, data)
        elif evType in ('TrackStuckEvent', 'TrackExceptionEvent'):
            await self._handleTrackError(player, data)
        elif evType == 'WebSocketClosedEvent':
            self.salad.emit('playerWebSocketClosed', player, data)

    async def _handleTrackEnd(self, player, data: Dict) -> None:
        """Handle track end with proper queue management."""
        reason = data.get('reason', 'UNKNOWN').lower()

        if reason in ('finished', 'load_failed'):
            if player.queue.loop != 'track':
                consumed = player.queue.consumeNext()
                player.current = None
                player.currentTrackObj = None
                self.salad.emit('trackEnd', player, consumed, reason)

            player.playing = False
            player.position = 0

            if player.queue._q or player.queue.loop == 'track':
                asyncio.create_task(player.play())
            else:
                if player.autoplay:
                    await self._handle_autoplay(player)
                else:
                    player.current = None
                    player.currentTrackObj = None
                    self.salad.emit('queueEnd', player)

        elif reason == 'replaced':
            pass

        else:
            if player.queue.loop != 'track':
                consumed = player.queue.consumeNext()
                self.salad.emit('trackEnd', player, consumed, reason)

            player.current = None
            player.currentTrackObj = None
            player.playing = False

    async def _handleTrackError(self, player, data: Dict) -> None:
        """Handle track errors."""
        consumed = player.queue.consumeNext() if player.queue.loop != 'track' else player.currentTrackObj

        player.current = None
        player.currentTrackObj = None
        player.playing = False

        self.salad.emit('trackError', player, consumed, data)

        if player.queue._q and not player.destroyed:
            asyncio.create_task(player.play())

    def updateClientId(self, cid: str) -> None:
        """Update client ID."""
        self.headers['User-Id'] = str(cid)
        if self.rest:
            self.rest.headers.update(self.headers)

    async def _updatePlayer(self, gid: int, /, *, data: Dict, replace: bool = False) -> Optional[Dict]:
        """Update player state with connection pooling."""
        noReplace = not replace
        scheme = 'https' if self.ssl else 'http'
        uri = (f"{scheme}://{self.host}:{self.port}/v4/sessions/"
               f"{self.sessionId}/players/{gid}?noReplace={str(noReplace).lower()}")

        if not self.session or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self.session = aiohttp.ClientSession(timeout=timeout, json_serialize=dumps)

        json_data = dumps(data).encode('utf-8') if isinstance(dumps(data), str) else dumps(data)
        headers = {**self.headers, 'Content-Type': 'application/json'}

        try:
            async with self.session.patch(uri, data=json_data, headers=headers) as resp:
                if resp.status in (200, 201):
                    body = await resp.read()
                    return loads(body) if body else None
                if resp.status == 204:
                    return None
                raise Exception(f"Player update failed: {resp.status}")
        except Exception as e:
            logger.debug(f"Player update error: {e}")
            raise

    async def _handle_autoplay(self, player):
        """Handles the autoplay logic."""
        last_track = player.queue.previous[-1] if player.queue.previous else None
        if not last_track:
            self.salad.emit('queueEnd', player)
            return

        next_track = None
        source = getattr(last_track, 'sourceName', 'youtube')

        try:
            if source == 'soundcloud':
                recommended_urls = await sc_autoplay(last_track.uri)
                if recommended_urls:
                    result = await self.salad.resolve(recommended_urls[0], requester=last_track.requester)
                    if result and result.get('tracks'):
                        next_track = result['tracks'][0]
            elif source == 'spotify':
                recommended_tracks = await sp_autoplay(player, last_track)
                if recommended_tracks:
                    next_track = recommended_tracks[0]
            else: # Default to YouTube
                recommended_tracks = await yt_autoplay(player, last_track)
                if recommended_tracks:
                    next_track = recommended_tracks[0]

            if next_track:
                player.addToQueue(next_track)
                self.salad.emit('autoplayTrack', player, next_track)
                await player.play()
            else:
                self.salad.emit('queueEnd', player)
        except Exception as e:
            logger.error(f"Autoplay failed: {e}")
            self.salad.emit('queueEnd', player)

    async def _cleanup(self) -> None:
        """Cleanup resources."""
        if self._listenTask and not self._listenTask.done():
            self._listenTask.cancel()
            try:
                await self._listenTask
            except asyncio.CancelledError:
                pass

        if self.ws and not self.ws.closed:
            await self.ws.close()

        self.connected = False
        self.sessionId = None
