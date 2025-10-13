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
import discord
import asyncio
import logging
from typing import Optional, Dict, Any
from contextlib import suppress

logger = logging.getLogger(__name__)


class SaladVoiceClient(discord.VoiceProtocol):
    """
    Custom voice client that integrates with Salad/Lavalink player system.
    Handles Discord voice state updates and forwards them to the player.
    """
    
    __slots__ = (
        'client', 'channel', 'guild', 'guild_id', 
        '_connected', 'voice_connected', 'player'
    )

    def __init__(self, client: discord.Client, channel: discord.VoiceChannel):
        """
        Initialize the voice client.
        
        Args:
            client: The Discord bot client
            channel: The voice channel to connect to
        """
        self.client = client
        self.channel = channel
        self.guild: Optional[discord.Guild] = getattr(channel, 'guild', None)
        self.guild_id: Optional[int] = self.guild.id if self.guild else None
        self._connected: bool = False
        self.voice_connected: asyncio.Event = asyncio.Event()
        self.player: Optional[Any] = None

    def set_player(self, player) -> None:
        """Set the player instance for this voice client."""
        self.player = player

    async def on_voice_state_update(self, data: Dict[str, Any]) -> None:
        """
        Handle voice state updates from Discord.
        Forwards updates to the Lavalink player.
        
        Args:
            data: Voice state update data from Discord
        """
        if not self.guild_id:
            return
        
        if not self.player or self.player.destroyed:
            return
        
        try:
            await self.player.handleVoiceStateUpdate(data)
        except Exception as e:
            logger.error(f"Error handling voice state update for guild {self.guild_id}: {e}")

    async def on_voice_server_update(self, data: Dict[str, Any]) -> None:
        """
        Handle voice server updates from Discord.
        Forwards updates to the Lavalink player.
        
        Args:
            data: Voice server update data from Discord
        """
        if not self.guild_id:
            return
        
        if not self.player or self.player.destroyed:
            return
        
        try:
            await self.player.handleVoiceServerUpdate(data)
        except Exception as e:
            logger.error(f"Error handling voice server update for guild {self.guild_id}: {e}")

    async def connect(
        self, 
        *, 
        timeout: float = 60.0, 
        reconnect: bool = True, 
        self_deaf: bool = True, 
        self_mute: bool = False
    ) -> None:
        """
        Connect to the voice channel.
        
        Args:
            timeout: Connection timeout in seconds
            reconnect: Whether to reconnect on disconnect
            self_deaf: Whether to deafen the bot
            self_mute: Whether to mute the bot
        """
        if self.guild:
            await self.guild.change_voice_state(
                channel=self.channel,
                self_deaf=self_deaf,
                self_mute=self_mute
            )
        
        self._connected = True
        self.voice_connected.set()
        logger.info(f"Connected to voice channel {self.channel.id} in guild {self.guild_id}")

    async def disconnect(self, *, force: bool = False) -> None:
        """
        Disconnect from the voice channel.
        
        Args:
            force: Force disconnect even if errors occur
        """
        if self.guild and self._connected:
            with suppress(Exception):
                await self.guild.change_voice_state(channel=None)
        
        self._connected = False
        self.cleanup()
        logger.info(f"Disconnected from voice channel in guild {self.guild_id}")

    def cleanup(self) -> None:
        """Clean up voice client resources."""
        self._connected = False
        
        with suppress(Exception):
            if self.guild_id and hasattr(self.client, '_connection'):
                voice_clients = self.client._connection._voice_clients
                if self.guild_id in voice_clients:
                    del voice_clients[self.guild_id]
                    logger.debug(f"Cleaned up voice client for guild {self.guild_id}")

    def is_connected(self) -> bool:
        """
        Check if the voice client is connected.
        
        Returns:
            bool: True if connected, False otherwise
        """
        return self._connected

    @property
    def latency(self) -> float:
        """Get voice connection latency."""
        return 0.0

    @property
    def average_latency(self) -> float:
        """Get average voice connection latency."""
        return 0.0
