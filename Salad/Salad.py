from .Node import Node
from .Player import Player
from .Track import Track
from .EventEmitter import EventEmitter
from typing import Optional, List, Dict, Any
import asyncio
import urllib.parse
import weakref

__all__ = ('Salad', 'DEFAULT_CONFIGS', 'EMPTY_TRACKS_RESPONSE')

DEFAULT_CONFIGS = {
    'host': '127.0.0.1',
    'port': 50166,
    'auth': 'manialwaysforgettoupdatethisongithub',
    'ssl': False
}

EMPTY_TRACKS_RESPONSE = {
    'loadType': 'empty',
    'exception': None,
    'playlistInfo': None,
    'pluginInfo': {},
    'tracks': []
}


class Salad(EventEmitter):
    """
    High-performance Lavalink client with:
    - Weak reference player tracking
    - Built-in event system
    - Optimized node management
    """

    __slots__ = ('nodes', 'client', 'players', '_player_refs', 'initiated',
                 'clientId', 'started', 'opts', 'version', '_listeners',
                 '_once_listeners', '_max_listeners', '_cleanup_counter',
                 '_state_manager', '_restoring_players')

    def __init__(self, client, nodes, opts=None):
        super().__init__(max_listeners=1000)  # Allow many listeners

        if not client or not nodes:
            return

        self.nodes: List[Node] = []
        self.client = client

        # Strong references for active players
        self.players: Dict[int, Player] = {}

        # Weak references to detect garbage collection
        self._player_refs: weakref.WeakValueDictionary = weakref.WeakValueDictionary()

        self.initiated = False
        self.clientId: Optional[str] = None
        self.started = False
        self.opts = opts or {}
        self.version = "1.0.0"

        # Initialize state manager
        self._state_manager = None
        self._restoring_players = False
        if opts and opts.get('enableReconnect', True):
            from .PlayerStateManager import PlayerStateManager
            state_file = opts.get('stateFile', 'player_states.jsonl')
            save_interval = opts.get('stateSaveInterval', 5.0)
            self._state_manager = PlayerStateManager(self, state_file, save_interval)

    async def start(self, nodes: List[Dict], userId: str) -> 'Salad':
        """Initialize and connect all nodes."""
        if self.started:
            return self

        self.clientId = userId
        self.nodes = [Node(self, nc, self.opts) for nc in nodes]

        # Update all nodes with client ID
        for node in self.nodes:
            node.updateClientId(userId)

        # Connect all nodes concurrently
        conn_tasks = [asyncio.create_task(n.connect()) for n in self.nodes]
        await asyncio.gather(*conn_tasks, return_exceptions=True)

        # Brief wait for node initialization
        await asyncio.sleep(2.0)

        # Start state manager if available
        if self.state_manager:
            await self.state_manager.start()

        # Check if any nodes connected successfully
        connected_nodes = [n for n in self.nodes if n.connected and n.sessionId]
        if connected_nodes:
            self.started = True
            self.emit('ready', self)

        return self

    async def createPlayer(self, node: Node, opts: Optional[Dict] = None) -> Optional[Player]:
        """Create a new player instance."""
        opts = opts or {}
        gid = opts.get('guildId')

        if not gid:
            return None

        # Return existing player if available
        if gid in self.players:
            existing = self.players[gid]
            if not existing.destroyed:
                return existing
            # Clean up destroyed player
            del self.players[gid]

        # Create new player
        player = Player(self, node, opts)
        self.players[gid] = player
        self._player_refs[gid] = player
        node.players[gid] = player

        await player.connect(opts)

        # Emit player creation event
        self.emit('playerCreate', player)

        return player

    async def createConnection(self, opts: Dict) -> Optional[Player]:
        """Create or retrieve a player connection."""
        if not self.started:
            return None

        gid = opts.get('guildId')
        if not gid:
            return None

        # Check for existing player
        existing = self.players.get(gid)
        if existing:
            if existing.destroyed:
                # Remove destroyed player
                try:
                    del self.players[gid]
                except KeyError:
                    pass
                existing = None
            else:
                return existing

        # Create new player on first available node
        for node in self.nodes:
            if node.connected and node.sessionId:
                return await self.createPlayer(node, opts)

        return None

    def getPlayer(self, guildId: int) -> Optional[Player]:
        """Get player by guild ID (fast O(1) lookup)."""
        player = self.players.get(guildId)
        if player and not player.destroyed:
            return player
        return None

    def destroyPlayer(self, guildId: int) -> None:
        """Remove player from tracking (called by Player.destroy())."""
        try:
            del self.players[guildId]
        except KeyError:
            pass

    async def stop(self) -> None:
        """Shutdown all nodes and cleanup resources."""
        # Destroy all players first
        player_tasks = []
        for player in list(self.players.values()):
            if not player.destroyed:
                player_tasks.append(asyncio.create_task(player.destroy()))

        if player_tasks:
            await asyncio.gather(*player_tasks, return_exceptions=True)

        # Stop state manager
        if self.state_manager:
            await self.state_manager.stop()

        # Cleanup nodes
        for node in self.nodes:
            await node._cleanup()
            if hasattr(node, 'rest') and hasattr(node.rest, 'close'):
                await node.rest.close()

        self.players.clear()
        self._player_refs.clear()
        self.started = False

        # Emit shutdown event
        self.emit('shutdown', self)

    def _getReqNode(self, nodes: Optional[List[Node]] = None) -> Optional[Node]:
        """Get first available connected node."""
        node_list = nodes or self.nodes

        # Fast iteration without list comprehension
        for node in node_list:
            if node.connected and node.sessionId:
                return node

        return None

    @staticmethod
    def _formatQuery(query: str, source: str = 'ytsearch') -> str:
        """Format search query with source prefix."""
        if source in ('ytsearch', 'ytmsearch', 'scsearch'):
            return f"{source}:{query}"
        return query

    @staticmethod
    def _makeTrack(data: Any, requester: Any, node: Node) -> Optional[Track]:
        """Create Track object from data."""
        if isinstance(data, dict):
            return Track(data, requester)
        return None

    async def resolve(self, query: str, source: str = 'ytsearch',
                     requester: Any = None, nodes: Optional[List[Node]] = None) -> Dict:
        """
        Resolve a search query or URL to tracks.

        Returns a structured response with tracks, playlist info, etc.
        """
        if not self.started:
            raise Exception('Salad not initialized')

        node = self._getReqNode(nodes)
        if not node:
            raise Exception('No nodes available')

        formatted = self._formatQuery(query, source)
        endpoint = f"/v4/loadtracks?identifier={urllib.parse.quote(formatted)}"

        try:
            resp = await node.rest.makeRequest('GET', endpoint)

            if isinstance(resp, dict):
                if not resp or resp.get('loadType') in ('empty', 'NO_MATCHES'):
                    return EMPTY_TRACKS_RESPONSE
                return self._constructResp(resp, requester, node)
            else:
                raise Exception('Invalid response type from node')

        except Exception as e:
            error_name = getattr(e, 'name', None)
            if error_name == 'AbortError':
                raise Exception('Request timeout')
            raise Exception(f"Resolve failed: {str(e)}")

    def _constructResp(self, resp: Dict, requester: Any, node: Node) -> Dict:
        """Construct standardized response from Lavalink data."""
        loadType = resp.get('loadType', 'empty')
        data = resp.get('data')
        rootPlugin = resp.get('pluginInfo', {})

        base = {
            'loadType': loadType,
            'exception': None,
            'playlistInfo': None,
            'pluginInfo': rootPlugin or {},
            'tracks': []
        }

        # Error handling
        if loadType in ('error', 'LOAD_FAILED'):
            base['exception'] = data or resp.get('exception')
            return base

        # Single track
        if loadType == 'track' and data:
            base['pluginInfo'] = data.get('info', {}).get('pluginInfo',
                                                          data.get('pluginInfo', base['pluginInfo']))
            track = self._makeTrack(data, requester, node)
            if track and track.track:
                base['tracks'].append(track)

        # Playlist
        elif loadType == 'playlist' and data:
            info = data.get('info')
            if info:
                # Get thumbnail from various sources
                thumb = (data.get('pluginInfo', {}).get('artworkUrl') or
                        (data.get('tracks', [{}])[0].get('info', {}).get('artworkUrl')
                         if data.get('tracks') else None))

                base['playlistInfo'] = {
                    'name': info.get('name') or info.get('title'),
                    'thumbnail': thumb,
                    **info
                }

            base['pluginInfo'] = data.get('pluginInfo', base['pluginInfo'])

            # Add all tracks
            tracks_data = data.get('tracks', [])
            if isinstance(tracks_data, list):
                for td in tracks_data:
                    track = self._makeTrack(td, requester, node)
                    if track and track.track:
                        base['tracks'].append(track)

        # Search results
        elif loadType == 'search' and isinstance(data, list):
            for td in data:
                track = self._makeTrack(td, requester, node)
                if track and track.track:
                    base['tracks'].append(track)

        return base

    async def save_player_states(self) -> int:
        """
        Manually save all player states.

        Returns number of states saved.
        """
        if not self.started or not self.state_manager:
            return 0

        return await self.state_manager.save_all_states()

    async def restore_players(self) -> int:
        """
        Manually restore all saved players.

        Returns number of players restored.
        """
        if not self.started or not self.state_manager:
            return 0

        self._restoring_players = True
        try:
            return await self.state_manager.restore_all_players()
        finally:
            self._restoring_players = False

    async def clear_saved_states(self) -> None:
        """Clear all saved player states."""
        if not self.started or not self.state_manager:
            return

        await self.state_manager.clear_states()

    @property
    def state_manager(self):
        """Get the state manager instance."""
        return getattr(self, '_state_manager', None)

    @state_manager.setter
    def state_manager(self, value):
        """Set the state manager instance."""
        self._state_manager = value
