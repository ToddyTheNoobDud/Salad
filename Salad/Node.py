import aiohttp
import asyncio
from .Rest import Rest
from typing import Dict, Optional, Any

try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    import json
    HAS_ORJSON = False

__all__ = ('Node', 'WS_PATH')

WS_PATH = 'v4/websocket'


class Node:
    """
    High-performance Lavalink node with:
    - Fast orjson parsing when available
    - Non-blocking WebSocket message handling
    - Efficient event routing
    - Proper cleanup and reconnection
    """

    __slots__ = ('salad', 'host', 'port', 'auth', 'ssl', 'wsUrl', 'opts',
                 'connected', 'info', 'players', 'clientName', 'sessionId',
                 'session', 'ws', 'stats', '_listenTask', 'headers', 'rest',
                 '_reconnect_attempts', '_max_reconnect_attempts')

    def __init__(self, salad, connOpts: Dict, opts: Optional[Dict] = None):
        self.salad = salad
        self.host = connOpts.get('host', '127.0.0.1')
        self.port = connOpts.get('port', 8000)
        self.auth = connOpts.get('auth', 'youshallnotpass')
        self.ssl = connOpts.get('ssl', False)
        self.wsUrl = f"ws{'s' if self.ssl else ''}://{self.host}:{self.port}/{WS_PATH}"
        self.opts = opts or {}

        self.connected = False
        self.info: Optional[Dict] = None
        self.players: Dict[int, Any] = {}
        self.clientName = 'Salad/v1.0.0'
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

        # Reconnection config
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5

        # Initialize Rest after all attributes
        self.rest = Rest(salad, self)

    async def connect(self) -> None:
        """Connect to Lavalink node via WebSocket."""
        try:
            self.session = aiohttp.ClientSession()
            self.ws = await self.session.ws_connect(
                self.wsUrl,
                headers=self.headers,
                autoclose=False,
                heartbeat=30
            )
            self.connected = True
            self._reconnect_attempts = 0

            # Start listening to WebSocket
            self._listenTask = asyncio.create_task(self._listenWs())

            # Wait for sessionId (max 5 seconds)
            for _ in range(50):
                if self.sessionId:
                    break
                await asyncio.sleep(0.1)

            # Fetch node info
            resp = await self.rest.makeRequest('GET', 'v4/info')
            if resp:
                self.info = resp

            self.salad.emit('nodeConnect', self)

        except Exception as e:
            self.connected = False
            await self._cleanup()
            self.salad.emit('nodeError', self, e)

    async def _listenWs(self) -> None:
        """
        Listen to WebSocket messages.
        CRITICAL: Must never block to prevent audio stuttering.
        """
        try:
            if not self.ws:
                return

            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        # Fast JSON parsing with orjson (~6x faster)
                        if HAS_ORJSON:
                            data = orjson.loads(msg.data)
                        else:
                            data = msg.json()

                        # Fire and forget - NEVER await here
                        asyncio.create_task(self._handleWsMsg(data))

                    except Exception:
                        pass

                elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                    break

        except Exception:
            pass

        finally:
            self.connected = False
            self.salad.emit('nodeDisconnect', self)

            # Attempt reconnection if not at max attempts
            if self._reconnect_attempts < self._max_reconnect_attempts:
                self._reconnect_attempts += 1
                asyncio.create_task(self._attemptReconnect())

    async def _attemptReconnect(self) -> None:
        """Attempt to reconnect to node after delay."""
        delay = min(30, 2 ** self._reconnect_attempts)  # Exponential backoff
        await asyncio.sleep(delay)

        if not self.connected:
            await self.connect()

    async def _handleWsMsg(self, data: Dict) -> None:
        """
        Process WebSocket messages asynchronously.
        Uses fast-path optimizations for frequent events.
        """
        op = data.get('op')

        if op == 'ready':
            self.sessionId = data.get('sessionId')
            self.salad.emit('nodeReady', self, data)

        elif op == 'stats':
            # Stats update - just store it
            self.stats = data
            self.salad.emit('nodeStats', self, data)

        elif op == 'playerUpdate':
            # FAST PATH: Most frequent event (~every 5s per player)
            # Process inline for minimal latency
            gid = data.get('guildId')
            if gid and gid in self.players:
                state = data.get('state', {})
                player = self.players[gid]
                player.position = state.get('position', 0)
                player.timestamp = state.get('time', 0)

                # Emit to salad
                self.salad.emit('playerPositionUpdate', player, state)

        elif op == 'event':
            # Events can be slow - handle in separate task
            asyncio.create_task(self._handleEvent(data))

    async def _handleEvent(self, data: Dict) -> None:
        """Handle Lavalink events (TrackEnd, TrackStart, etc.)."""
        gid = data.get('guildId')
        evType = data.get('type')

        if not gid:
            return

        # Convert string guildId to int
        if isinstance(gid, str):
            try:
                gid = int(gid)
            except ValueError:
                return

        if gid not in self.players:
            return

        player = self.players[gid]

        # Route to specific event handler
        if evType == 'TrackEndEvent':
            await self._handleTrackEnd(player, data)

        elif evType == 'TrackStartEvent':
            await self._handleTrackStart(player, data)

        elif evType in ('TrackStuckEvent', 'TrackExceptionEvent'):
            await self._handleTrackError(player, data)

        elif evType == 'WebSocketClosedEvent':
            self.salad.emit('playerWebSocketClosed', player, data)

    async def _handleTrackEnd(self, player, data: Dict) -> None:
        """Handle track end event."""
        reason = data.get('reason', 'UNKNOWN')
        reason_lower = reason.lower() if isinstance(reason, str) else str(reason)

        if reason_lower in ('finished', 'load_failed'):
            # Track finished - consume from queue
            if player.queue.loop != 'track':
                consumed = player.queue.consumeNext()
                player.current = None
                player.currentTrackObj = None
                self.salad.emit('trackEnd', player, consumed, reason)

            player.playing = False
            player.position = 0

            # Play next track
            if player.queue._q or player.queue.loop == 'track':
                asyncio.create_task(player.play())
            else:
                player.current = None
                player.currentTrackObj = None
                self.salad.emit('queueEnd', player)

        elif reason == 'REPLACED':
            # Track replaced - consume it
            if player.queue.loop != 'track':
                consumed = player.queue.consumeNext()
                self.salad.emit('trackEnd', player, consumed, reason)

        else:
            # Other reasons - consume and stop
            if player.queue.loop != 'track':
                consumed = player.queue.consumeNext()
                self.salad.emit('trackEnd', player, consumed, reason)

            player.current = None
            player.currentTrackObj = None
            player.playing = False

    async def _handleTrackStart(self, player, data: Dict) -> None:
        """Handle track start event."""
        player.playing = True
        player.paused = False
        self.salad.emit('trackStart', player, player.currentTrackObj)

    async def _handleTrackError(self, player, data: Dict) -> None:
        """Handle track stuck or exception."""
        # Consume failed track
        if player.queue.loop != 'track':
            consumed = player.queue.consumeNext()
        else:
            consumed = player.currentTrackObj

        player.current = None
        player.currentTrackObj = None
        player.playing = False

        # Emit error event
        self.salad.emit('trackError', player, consumed, data)

        # Try next track
        if player.queue._q and not player.destroyed:
            asyncio.create_task(player.play())

    def updateClientId(self, cid: str) -> None:
        """Update client ID in headers."""
        self.headers['User-Id'] = str(cid)
        if self.rest:
            self.rest.headers.update(self.headers)

    async def _updatePlayer(self, gid: int, /, *, data: Dict, replace: bool = False) -> Optional[Dict]:
        """
        Update player state on Lavalink.
        Uses orjson for fast encoding when available.
        """
        noReplace = not replace
        scheme = 'https' if self.ssl else 'http'
        uri = (f"{scheme}://{self.host}:{self.port}/v4/sessions/"
               f"{self.sessionId}/players/{gid}?noReplace={str(noReplace).lower()}")

        if not self.session:
            self.session = aiohttp.ClientSession()

        # Fast JSON encoding with orjson
        if HAS_ORJSON:
            json_data = orjson.dumps(data)
            headers = {**self.headers, 'Content-Type': 'application/json'}

            async with self.session.patch(uri, data=json_data, headers=headers) as resp:
                if resp.status in (200, 201):
                    try:
                        body = await resp.read()
                        return orjson.loads(body) if body else None
                    except Exception:
                        return None
                if resp.status == 204:
                    return None
                raise Exception(f"Player update failed: {resp.status}")
        else:
            async with self.session.patch(uri, json=data, headers=self.headers) as resp:
                if resp.status in (200, 201):
                    try:
                        return await resp.json()
                    except Exception:
                        return None
                if resp.status == 204:
                    return None
                raise Exception(f"Player update failed: {resp.status}")

    async def _cleanup(self) -> None:
        """Cleanup node resources."""
        # Cancel WebSocket listener
        if self._listenTask and not self._listenTask.done():
            self._listenTask.cancel()
            try:
                await self._listenTask
            except asyncio.CancelledError:
                pass

        # Close WebSocket
        if self.ws and not self.ws.closed:
            await self.ws.close()

        # Close session
        if self.session and not self.session.closed:
            await self.session.close()

        self.connected = False
        self.sessionId = None