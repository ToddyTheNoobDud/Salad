# type: ignore
"""
DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
Version 2, December 2004

Copyright (C) 2004 Sam Hocevar <sam@hocevar.net>

Everyone is permitted to copy and distribute verbatim or modified
copies of this license document, and changing it is allowed as long
as the name is changed.

DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
TERMS AND CONDITIONS FOR COPYING, DISTRIBUTION AND MODIFICATION

0. You just DO WHAT THE FUCK YOU WANT TO.
"""
from contextlib import suppress
from typing import cast, Optional

import discord
from discord.ext import commands
from discord import app_commands

from salada import Salad
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SaladVoiceClient(discord.VoiceProtocol):
    """Custom voice protocol for Lavalink integration."""

    def __init__(self, client, channel):
        self.client = client
        self.channel = channel
        self.guild = getattr(channel, 'guild', None)
        self.guild_id = self.guild.id if self.guild else None
        self._connected = False

    async def on_voice_state_update(self, data):
        if not self.guild_id:
            return
        cog = self.client.get_cog('Music')
        if not cog or not cog.salad:
            return
        player = cog.salad.players.get(self.guild_id)
        if player and not player.destroyed:
            await player.handleVoiceStateUpdate(data)

    async def on_voice_server_update(self, data):
        if not self.guild_id:
            return
        cog = self.client.get_cog('Music')
        if not cog or not cog.salad:
            return
        player = cog.salad.players.get(self.guild_id)
        if player and not player.destroyed:
            await player.handleVoiceServerUpdate(data)

    async def connect(self, *, timeout=60.0, reconnect=True, self_deaf=True, self_mute=False):
        if self.guild:
            await self.guild.change_voice_state(
                channel=self.channel,
                self_deaf=self_deaf,
                self_mute=self_mute
            )
        self._connected = True

    async def disconnect(self, *, force=False):
        if self.guild and self._connected:
            with suppress(Exception):
                await self.guild.change_voice_state(channel=None)
        self._connected = False
        self.cleanup()

    def cleanup(self):
        self._connected = False
        with suppress(Exception):
            if self.guild_id and hasattr(self.client, '_connection'):
                voice_clients = self.client._connection._voice_clients
                if self.guild_id in voice_clients:
                    del voice_clients[self.guild_id]

    def is_connected(self):
        return self._connected


class Music(commands.Cog):
    """Music cog with full queue system."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.salad: Optional[Salad] = None
        bot.loop.create_task(self.start_salad())

    async def cleanup_voice_for_guild(self, guild_id: int) -> None:
        """Cleanup voice connection for a guild."""
        guild = self.bot.get_guild(guild_id)
        if not guild or not guild.voice_client:
            return

        with suppress(Exception):
            await guild.voice_client.disconnect(force=True)
            guild.voice_client.cleanup()

        await asyncio.sleep(0.3)

    async def ensure_voice_disconnected(self, guild: discord.Guild) -> None:
        """Ensure guild is fully disconnected from voice."""
        if not guild.voice_client:
            return

        with suppress(Exception):
            await guild.voice_client.disconnect(force=True)
            guild.voice_client.cleanup()

        await asyncio.sleep(0.3)

    async def connect_voice(self, guild: discord.Guild, channel: discord.VoiceChannel):
        """Connect to voice channel with proper cleanup."""
        await self.ensure_voice_disconnected(guild)

        try:
            voice_client = await channel.connect(
                cls=SaladVoiceClient,
                timeout=15.0,
                reconnect=False
            )
            return cast(SaladVoiceClient, voice_client)
        except discord.errors.ClientException as e:
            if "Already connected" in str(e):
                with suppress(Exception):
                    if hasattr(self.bot, '_connection') and hasattr(self.bot._connection, '_voice_clients'):
                        if guild.id in self.bot._connection._voice_clients:
                            del self.bot._connection._voice_clients[guild.id]

                await asyncio.sleep(1.0)

                with suppress(Exception):
                    return await channel.connect(cls=SaladVoiceClient, timeout=15.0, reconnect=False)
            return None
        except Exception:
            return None

    async def start_salad(self):
        """Initialize Salad client and connect to Lavalink nodes."""
        await self.bot.wait_until_ready()

        nodes = [{
            'host': '127.0.0.1',
            'port': 2333,
            'auth': 'youshallnotpass',
            'ssl': False
        }]

        self.salad = Salad(self.bot, nodes, opts={
            'enableReconnect': True,
            'infiniteReconnect': True,
            'maxReconnectAttempts': 10,
            'baseReconnectDelay': 2.0,
            'maxReconnectDelay': 300.0
        })

        bot_user_id = str(self.bot.user.id if self.bot.user else 0)

        try:
            await self.salad.start(nodes, bot_user_id)
            logger.info('Salad client started successfully')
        except Exception as e:
            logger.error(f'Failed to start Salad: {e}')
            return

        async def reconnect_to_voice(guild_id: int, channel_id: str, deaf: bool, mute: bool) -> bool:
            """Reconnect to voice channel during player restoration."""
            try:
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    return False

                channel = guild.get_channel(int(channel_id))
                if not channel or not isinstance(channel, discord.VoiceChannel):
                    return False

                await self.ensure_voice_disconnected(guild)
                voice_client = await self.connect_voice(guild, channel)
                
                if not voice_client:
                    return False

                player = self.salad.players.get(guild_id)
                if player and not player.destroyed:
                    await player.stop()

                return True
            except Exception as e:
                logger.error(f"Failed to reconnect voice for guild {guild_id}: {e}")
                return False

        if self.salad.state_manager:
            self.salad.state_manager.set_voice_connect_callback(reconnect_to_voice)

        self.salad.on('trackStart', lambda p, t: logger.info(f'Track started: {t.title if hasattr(t, "title") else t}'))
        self.salad.on('trackEnd', lambda p, t, r: logger.info(f'Track ended: {r}'))
        self.salad.on('trackError', lambda p, t, e: logger.error(f'Track error: {e}'))
        self.salad.on('queueEnd', lambda p: logger.info(f'Queue ended for guild {p.guildId}'))

    async def get_or_create_player(self, interaction: discord.Interaction):
        """Get existing player or create new one."""
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send('You must be in a voice channel!', ephemeral=True)
            return None

        if not self.salad or not self.salad.started:
            await interaction.followup.send('Music system not ready!', ephemeral=True)
            return None

        guild = interaction.guild
        if not guild:
            await interaction.followup.send('This command must be used in a server!', ephemeral=True)
            return None

        user_channel = interaction.user.voice.channel
        player = self.salad.players.get(guild.id)

        if player and not player.destroyed:
            voice_client = cast(SaladVoiceClient, guild.voice_client) if guild.voice_client else None
            bot_in_voice = guild.me.voice is not None and guild.me.voice.channel is not None

            if not bot_in_voice or not voice_client or not voice_client.is_connected():
                with suppress(Exception):
                    await player.destroy(cleanup_voice=False)
                    if guild.id in self.salad.players:
                        del self.salad.players[guild.id]
                player = None

        if not player:
            await self.ensure_voice_disconnected(guild)

            try:
                player = await self.salad.createConnection({
                    'guildId': guild.id,
                    'voiceChannel': user_channel.id,
                    'textChannel': interaction.channel.id,
                    'selfDeaf' or 'deaf': True,
                    'mute': False
                })
            except Exception as e:
                logger.error(f'Failed to create player: {e}')
                await interaction.followup.send('Failed to create player!', ephemeral=True)
                return None

            if not player:
                await interaction.followup.send('Failed to create player!', ephemeral=True)
                return None

            player.setVoiceCleanupCallback(self.cleanup_voice_for_guild)

            voice_client = await self.connect_voice(guild, user_channel)
            if not voice_client:
                await interaction.followup.send('Failed to connect to voice!', ephemeral=True)
                await player.destroy(cleanup_voice=False)
                return None

            for _ in range(30):
                if player.connected:
                    return player
                await asyncio.sleep(0.5)

            await interaction.followup.send('Connection timed out!', ephemeral=True)
            await self.ensure_voice_disconnected(guild)
            await player.destroy(cleanup_voice=False)
            return None

        return player

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Handle bot disconnection from voice."""
        if member.id != (self.bot.user.id if self.bot.user else 0):
            return

        if before.channel and not after.channel:
            guild = before.channel.guild
            await asyncio.sleep(1.0)

            if not guild.voice_client or not guild.voice_client.is_connected():
                if self.salad:
                    player = self.salad.players.get(guild.id)
                    if player and not player.destroyed:
                        await player.destroy(cleanup_voice=False)

    @app_commands.command(name='join', description='Join a voice channel')
    async def join(self, interaction: discord.Interaction, channel: Optional[discord.VoiceChannel] = None):
        """Join a voice channel."""
        if not channel:
            if not interaction.user.voice or not interaction.user.voice.channel:
                return await interaction.response.send_message(
                    'You must be in a voice channel!',
                    ephemeral=True
                )
            channel = interaction.user.voice.channel

        await interaction.response.defer()
        player = await self.get_or_create_player(interaction)
        
        if player:
            await interaction.followup.send(f'Joined **{channel.name}**')

    @app_commands.command(name='leave', description='Leave voice channel')
    async def leave(self, interaction: discord.Interaction):
        """Disconnect from voice channel."""
        if not interaction.guild:
            return await interaction.response.send_message(
                'This command must be used in a server!',
                ephemeral=True
            )

        player = self.salad.players.get(interaction.guild.id) if self.salad else None

        if not player or player.destroyed:
            return await interaction.response.send_message(
                'Not connected to a voice channel!',
                ephemeral=True
            )

        await interaction.response.defer()

        with suppress(Exception):
            await player.destroy()
            await interaction.followup.send('Disconnected!')

    @app_commands.command(name='play', description='Play a song')
    @app_commands.describe(query='Song name or URL')
    async def play(self, interaction: discord.Interaction, query: str):
        """Play a song or playlist."""
        await interaction.response.defer()

        player = await self.get_or_create_player(interaction)
        if not player:
            return

        try:
            result = await self.salad.resolve(query, requester=interaction.user)
        except Exception as e:
            return await interaction.followup.send(f'Search failed: {str(e)}')

        load_type = result.get('loadType', 'empty')

        if load_type == 'empty':
            return await interaction.followup.send(f'No results found for: `{query}`')

        if load_type == 'error':
            error_msg = result.get('exception', {})
            if isinstance(error_msg, dict):
                error_msg = error_msg.get('message', 'Unknown error')
            return await interaction.followup.send(f'Error loading track: {error_msg}')

        tracks = result.get('tracks', [])
        if not tracks:
            return await interaction.followup.send('No tracks found!')

        was_playing = player.playing

        if load_type == 'playlist':
            added_count = sum(1 for track in tracks if player.queue.add(track))

            if added_count == 0:
                return await interaction.followup.send('Failed to add tracks!')

            playlist_info = result.get('playlistInfo', {})
            playlist_name = playlist_info.get('name', 'Unknown Playlist')

            await interaction.followup.send(
                f'Added **{added_count}** tracks from **{playlist_name}** to queue'
            )

        elif load_type in ['track', 'search']:
            track = tracks[0]

            if not player.queue.add(track):
                return await interaction.followup.send('Failed to add track!')

            if was_playing:
                position = len(player.queue)
                await interaction.followup.send(
                    f'Added to queue: **{track.title}** by **{track.author}** (Position: {position})'
                )
            else:
                await interaction.followup.send(
                    f'Now playing: **{track.title}** by **{track.author}**'
                )
        else:
            return await interaction.followup.send(f'Unknown load type: {load_type}')

        if not was_playing:
            with suppress(Exception):
                await player.play()

    @app_commands.command(name='skip', description='Skip current track')
    async def skip(self, interaction: discord.Interaction):
        """Skip the currently playing song."""
        if not interaction.guild:
            return await interaction.response.send_message(
                'This command must be used in a server!',
                ephemeral=True
            )

        player = self.salad.players.get(interaction.guild.id) if self.salad else None

        if not player or player.destroyed or not player.current:
            return await interaction.response.send_message('Nothing playing!', ephemeral=True)

        with suppress(Exception):
            await player.skip()
            await interaction.response.send_message('⏭️ Skipped!')

    @app_commands.command(name='stop', description='Stop playback and clear queue')
    async def stop(self, interaction: discord.Interaction):
        """Stop playback and clear the queue."""
        if not interaction.guild:
            return await interaction.response.send_message(
                'This command must be used in a server!',
                ephemeral=True
            )

        player = self.salad.players.get(interaction.guild.id) if self.salad else None

        if not player or player.destroyed:
            return await interaction.response.send_message('No active player!', ephemeral=True)

        await interaction.response.defer()

        with suppress(Exception):
            await player.destroy()
            await interaction.followup.send('⏹️ Stopped and disconnected!')

    @app_commands.command(name='pause', description='Pause playback')
    async def pause(self, interaction: discord.Interaction):
        """Pause the currently playing song."""
        if not interaction.guild:
            return await interaction.response.send_message(
                'This command must be used in a server!',
                ephemeral=True
            )

        player = self.salad.players.get(interaction.guild.id) if self.salad else None

        if not player or player.destroyed:
            return await interaction.response.send_message('No active player!', ephemeral=True)

        if player.paused:
            return await interaction.response.send_message('Already paused!', ephemeral=True)

        with suppress(Exception):
            await player.pause()
            await interaction.response.send_message('⏸️ Paused!')

    @app_commands.command(name='resume', description='Resume playback')
    async def resume(self, interaction: discord.Interaction):
        """Resume the currently paused song."""
        if not interaction.guild:
            return await interaction.response.send_message(
                'This command must be used in a server!',
                ephemeral=True
            )

        player = self.salad.players.get(interaction.guild.id) if self.salad else None

        if not player or player.destroyed:
            return await interaction.response.send_message('No active player!', ephemeral=True)

        if not player.paused:
            return await interaction.response.send_message('Not paused!', ephemeral=True)

        with suppress(Exception):
            await player.resume()
            await interaction.response.send_message('▶️ Resumed!')

    @app_commands.command(name='volume', description='Set player volume')
    @app_commands.describe(volume='Volume level (1-100)')
    async def volume(self, interaction: discord.Interaction, volume: int):
        """Change the player volume."""
        if not interaction.guild:
            return await interaction.response.send_message(
                'This command must be used in a server!',
                ephemeral=True
            )

        if not 1 <= volume <= 100:
            return await interaction.response.send_message(
                'Volume must be between 1 and 100!',
                ephemeral=True
            )

        player = self.salad.players.get(interaction.guild.id) if self.salad else None

        if not player or player.destroyed:
            return await interaction.response.send_message('No active player!', ephemeral=True)

        with suppress(Exception):
            await player.setVolume(volume)
            await interaction.response.send_message(f'🔊 Volume set to **{volume}%**')

    @app_commands.command(name='queue', description='View the current queue')
    async def queue(self, interaction: discord.Interaction):
        """Display the current queue."""
        if not interaction.guild:
            return await interaction.response.send_message(
                'This command must be used in a server!',
                ephemeral=True
            )

        player = self.salad.players.get(interaction.guild.id) if self.salad else None

        if not player or player.destroyed:
            return await interaction.response.send_message('No active player!', ephemeral=True)

        if not player.current and player.queue.isEmpty():
            return await interaction.response.send_message('Queue is empty!', ephemeral=True)

        embed = discord.Embed(title='Queue', color=discord.Color.blue())

        if player.current:
            embed.add_field(
                name='Now Playing',
                value=f'**{player.current.title}** by **{player.current.author}**',
                inline=False
            )

        if not player.queue.isEmpty():
            queue_list = []
            for i, track in enumerate(player.queue[:10], 1):
                queue_list.append(f'`{i}.` **{track.title}** by **{track.author}**')

            if len(player.queue) > 10:
                queue_list.append(f'\n*And {len(player.queue) - 10} more...*')

            embed.add_field(
                name=f'Up Next ({len(player.queue)} tracks)',
                value='\n'.join(queue_list),
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='nowplaying', description='Show currently playing song')
    async def nowplaying(self, interaction: discord.Interaction):
        """Display the currently playing song."""
        if not interaction.guild:
            return await interaction.response.send_message(
                'This command must be used in a server!',
                ephemeral=True
            )

        player = self.salad.players.get(interaction.guild.id) if self.salad else None

        if not player or player.destroyed or not player.current:
            return await interaction.response.send_message('Nothing playing!', ephemeral=True)

        track = player.current
        embed = discord.Embed(
            title='Now Playing',
            description=f'**{track.title}** by **{track.author}**',
            color=discord.Color.green()
        )

        if hasattr(track, 'uri'):
            embed.url = track.uri

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
