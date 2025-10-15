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
from .Node import Node
from .Player import Player
from .Track import Track
from .EventEmitter import EventEmitter
from .voiceclient import SaladVoiceClient
from typing import Optional, List, Dict, Any
import asyncio
import urllib.parse
import weakref
import logging

logger = logging.getLogger(__name__)

__all__ = ('Salad', 'DEFAULT_CONFIGS', 'EMPTY_TRACKS_RESPONSE')

DEFAULT_CONFIGS = {
    'host': '127.0.0.1',
    'port': 50166,
    'auth': 'youshallnotpass',
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
    """The main file for the Salad client"""
    __slots__ = ('nodes', 'client', 'players', '_player_refs', 'initiated',
                 'clientId', 'started', 'opts', 'version', '_listeners',
                 '_once_listeners', '_max_listeners', '_cleanup_counter',
                 '_state_manager', '_restoring_players')

    def __init__(self, client, nodes, opts=None):
        super().__init__(max_listeners=1000)

        if not client or not nodes:
            return

        self.nodes: List[Node] = []
        self.client = client
        self.players: Dict[int, Player] = {}
        self._player_refs: weakref.WeakValueDictionary = weakref.WeakValueDictionary()

        self.initiated = False
        self.clientId: Optional[str] = None
        self.started = False
        self.opts = opts or {}
        self.version = "1.0.0"
        self._state_manager = None
        self._restoring_players = False

        if opts and opts.get('enableReconnect', True):
            from .PlayerStateManager import PlayerStateManager
            state_file = opts.get('stateFile', 'player_states.jsonl')
            save_interval = opts.get('stateSaveInterval', 5.0)
            self._state_manager = PlayerStateManager(self, state_file, save_interval)

    async def start(self, nodes: List[Dict], userId: str) -> 'Salad':
        if self.started:
            return self

        self.clientId = userId
        self.nodes = [Node(self, nc, self.opts) for nc in nodes]

        for node in self.nodes:
            node.updateClientId(userId)

        conn_tasks = [asyncio.create_task(n.connect()) for n in self.nodes]
        await asyncio.gather(*conn_tasks, return_exceptions=True)

        await asyncio.sleep(2.0)

        if self.state_manager:
            await self.state_manager.start()
            self.state_manager.set_voice_connect_callback(self._voice_connect_for_restore)

        connected_nodes = [n for n in self.nodes if n.connected and n.sessionId]
        if connected_nodes:
            self.started = True
            self.emit('ready', self)

        return self

    async def _voice_connect_for_restore(self, guild_id: int, voice_channel_id: str,
                                         deaf: bool = True, mute: bool = False) -> bool:
        """
        Voice connection callback for PlayerStateManager restoration.

        Args:
            guild_id: Guild ID to connect in
            voice_channel_id: Voice channel ID to connect to
            deaf: Whether to self-deafen
            mute: Whether to self-mute

        Returns:
            bool: True if connection was successful
        """
        try:
            guild = self.client.get_guild(guild_id)
            if not guild:
                logger.warning(f"Guild {guild_id} not found for voice restoration")
                return False

            voice_channel = guild.get_channel(int(voice_channel_id))
            if not voice_channel:
                logger.warning(f"Voice channel {voice_channel_id} not found in guild {guild_id}")
                return False

            if guild.voice_client:
                if guild.voice_client.channel.id == int(voice_channel_id):
                    logger.info(f"Already connected to voice channel {voice_channel_id}")
                    return True
                else:
                    await guild.voice_client.disconnect(force=True)
                    await asyncio.sleep(0.5)

            voice_client = await voice_channel.connect(
                cls=SaladVoiceClient,
                timeout=30.0,
                reconnect=True,
                self_deaf=deaf,
                self_mute=mute
            )

            logger.info(f"Connected to voice channel {voice_channel_id} in guild {guild_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to voice for guild {guild_id}: {e}")
            return False

    async def createPlayer(self, node: Node, opts: Optional[Dict] = None) -> Optional[Player]:
        opts = opts or {}
        gid = opts.get('guildId')

        if not gid:
            return None

        if gid in self.players:
            existing = self.players[gid]
            if not existing.destroyed:
                return existing
            del self.players[gid]

        player = Player(self, node, opts)
        self.players[gid] = player
        self._player_refs[gid] = player
        node.players[gid] = player

        player.setVoiceCleanupCallback(self._cleanup_voice_connection)

        await player.connect(opts)

        self.emit('playerCreate', player)

        return player

    async def _cleanup_voice_connection(self, guild_id: int) -> None:
        """
        Cleanup voice connection for a guild.

        Args:
            guild_id: The guild ID to cleanup voice for
        """
        try:
            guild = self.client.get_guild(guild_id)
            if guild and guild.voice_client:
                await guild.voice_client.disconnect(force=True)
                logger.info(f"Cleaned up voice connection for guild {guild_id}")
        except Exception as e:
            logger.debug(f"Error cleaning up voice connection for guild {guild_id}: {e}")

    async def createConnection(self, opts: Dict) -> Optional[Player]:
        """
        Create a connection and player for a guild.
        This handles Discord voice connection using SaladVoiceClient.

        Args:
            opts: Options dict containing:
                - guildId: Guild ID (required)
                - voiceChannel: Voice channel ID (required)
                - textChannel: Text channel ID (optional)
                - deaf: Self-deafen (default: True)
                - mute: Self-mute (default: False)
                - volume: Initial volume (default: 100)

        Returns:
            Optional[Player]: Created player or None
        """
        if not self.started:
            return None

        gid = opts.get('guildId')
        if not gid:
            return None

        existing = self.players.get(gid)
        if existing:
            if existing.destroyed:
                try:
                    del self.players[gid]
                except KeyError:
                    pass
                existing = None
            else:
                return existing

        guild = self.client.get_guild(gid)
        if not guild:
            logger.error(f"Guild {gid} not found")
            return None

        voice_channel_id = opts.get('voiceChannel')
        if not voice_channel_id:
            logger.error(f"No voice channel specified for guild {gid}")
            return None

        voice_channel = guild.get_channel(int(voice_channel_id))
        if not voice_channel:
            logger.error(f"Voice channel {voice_channel_id} not found in guild {gid}")
            return None

        if guild.voice_client:
            if guild.voice_client.channel.id != int(voice_channel_id):
                await guild.voice_client.disconnect(force=True)
                await asyncio.sleep(0.5)
            else:
                logger.info(f"Already connected to voice channel {voice_channel_id}")

        if not guild.voice_client or not guild.voice_client.is_connected():
            try:
                deaf = opts.get('deaf', True)
                mute = opts.get('mute', False)

                voice_client = await voice_channel.connect(
                    cls=SaladVoiceClient,
                    timeout=30.0,
                    reconnect=True,
                    self_deaf=deaf,
                    self_mute=mute
                )

                logger.info(f"Connected to voice channel {voice_channel_id} in guild {gid}")
            except Exception as e:
                logger.error(f"Failed to connect to voice channel: {e}")
                return None

        for node in self.nodes:
            if node.connected and node.sessionId:
                player = await self.createPlayer(node, opts)

                if player and guild.voice_client:
                    if isinstance(guild.voice_client, SaladVoiceClient):
                        guild.voice_client.set_player(player)
                        logger.info(f"Linked SaladVoiceClient to player for guild {gid}")

                return player

        return None

    def getPlayer(self, guildId: int) -> Optional[Player]:
        player = self.players.get(guildId)
        if player and not player.destroyed:
            return player
        return None

    def destroyPlayer(self, guildId: int) -> None:
        try:
            del self.players[guildId]
        except KeyError:
            pass

    async def stop(self) -> None:
        player_tasks = []
        for player in list(self.players.values()):
            if not player.destroyed:
                player_tasks.append(asyncio.create_task(player.destroy()))

        if player_tasks:
            await asyncio.gather(*player_tasks, return_exceptions=True)

        if self.state_manager:
            await self.state_manager.stop()

        for node in self.nodes:
            await node._cleanup()
            if hasattr(node, 'rest') and hasattr(node.rest, 'close'):
                await node.rest.close()

        self.players.clear()
        self._player_refs.clear()
        self.started = False

        self.emit('shutdown', self)

    def _getReqNode(self, nodes: Optional[List[Node]] = None) -> Optional[Node]:
        node_list = nodes or self.nodes

        for node in node_list:
            if node.connected and node.sessionId:
                return node

        return None

    @staticmethod
    def _formatQuery(query: str, source: str = 'ytsearch') -> str:
        if source in ('ytsearch', 'ytmsearch', 'scsearch'):
            return f"{source}:{query}"
        return query

    @staticmethod
    def _makeTrack(data: Any, requester: Any, node: Node) -> Optional[Track]:
        if isinstance(data, dict):
            return Track(data, requester)
        return None

    async def resolve(self, query: str, source: str = 'ytsearch',
                     requester: Any = None, nodes: Optional[List[Node]] = None) -> Dict:
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
        """Constructs a standardized response dictionary from the node's response.
        """
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

        if loadType in ('error', 'LOAD_FAILED'):
            base['exception'] = data or resp.get('exception')
            return base

        if loadType == 'track' and data:
            base['pluginInfo'] = data.get('info', {}).get('pluginInfo',
                                                          data.get('pluginInfo', base['pluginInfo']))
            track = self._makeTrack(data, requester, node)
            if track and track.track:
                base['tracks'].append(track)

        elif loadType == 'playlist' and data:
            info = data.get('info')
            if info:
                thumb = (data.get('pluginInfo', {}).get('artworkUrl') or
                        (data.get('tracks', [{}])[0].get('info', {}).get('artworkUrl')
                         if data.get('tracks') else None))

                base['playlistInfo'] = {
                    'name': info.get('name') or info.get('title'),
                    'thumbnail': thumb,
                    **info
                }

            base['pluginInfo'] = data.get('pluginInfo', base['pluginInfo'])

            tracks_data = data.get('tracks', [])
            if isinstance(tracks_data, list):
                for td in tracks_data:
                    track = self._makeTrack(td, requester, node)
                    if track and track.track:
                        base['tracks'].append(track)

        elif loadType == 'search' and isinstance(data, list):
            for td in data:
                track = self._makeTrack(td, requester, node)
                if track and track.track:
                    base['tracks'].append(track)

        return base

    async def save_player_states(self) -> int:
        """Saves all current player states to the player_states file."""
        if not self.started or not self.state_manager:
            return 0

        return await self.state_manager.save_all_states()

    async def restore_players(self) -> int:
        """Restores all players from the player_states file."""
        if not self.started or not self.state_manager:
            return 0

        self._restoring_players = True
        try:
            return await self.state_manager.restore_all_players()
        finally:
            self._restoring_players = False

    async def clear_saved_states(self) -> None:
        if not self.started or not self.state_manager:
            return

        await self.state_manager.clear_states()

    @property
    def state_manager(self):
        """Get the player state manager."""
        return getattr(self, '_state_manager', None)

    @state_manager.setter
    def state_manager(self, value):
        """Set the player state manager."""
        self._state_manager = value
