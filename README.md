# Salad

[![License: WTFPL](https://img.shields.io/badge/License-WTFPL-A42E2B?style=flat-square&logo=gnu&logoColor=white&labelColor=2f2f2f)](https://github.com/ToddyTheNoobDud/Salad/blob/main/LICENSE) [![Python](https://img.shields.io/pypi/pyversions/salada?style=flat-square&logo=python&logoColor=white&color=3776AB&labelColor=2f2f2f)](https://pypi.org/project/salada/) [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg?style=flat-square&logo=python&logoColor=white)](https://github.com/psf/black) [![Discord](https://img.shields.io/discord/899324069235810315?style=flat-square&logo=discord&logoColor=white&color=5865F2&label=Support&labelColor=2f2f2f)](https://discord.gg/UKNDx2JWa5)

Salad is a lightning-fast, completely asynchronous Python framework designed for effortless [Lavalink](https://github.com/freyacodes/Lavalink) integration with [discord.py](https://github.com/Rapptz/discord.py). With full [Lavalink](https://github.com/freyacodes/Lavalink) specification support, clean API architecture, and robust integrated Spotify and Apple Music functionality, Salad enables creators to craft outstanding music bots effortlessly.

Developed as an improved fork of [AquaLink](https://github.com/ToddyTheNoobDud/AquaLink), Salad provides enhanced performance and developer satisfaction.

## Essential Resources
- [Discord Community Hub](https://discord.gg/UKNDx2JWa5)
- [PyPI Distribution](https://pypi.org/project/salada/)
- [Documentation](https://salad-ffed6391.mintlify.app)

# Setup Instructions
Requires Python 3.8 or newer and current pip version.

> Production Version (Suggested)

```
pip install salada
```

> Unstable version of Salad.

```
pip install git+https://github.com/ToddyTheNoobDud/salad
```

# Quick Start Guide
Browse detailed examples in the [examples folder](https://github.com/ToddyTheNoobDud/salad/tree/main/examples)

Here's a basic starter code:
```py
import discord
from discord.ext import commands
from discord import app_commands
from salada import Salad

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.voice_states = True

NODES = [{
    'host': '127.0.0.1',
    'port': 50166,
    'auth': 'youshallnotpass',
    'ssl': False
}]

class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=INTENTS)
        self.salad = None

    async def setup_hook(self):
        self.salad = Salad(self, NODES)
        await self.salad.start(NODES, str(self.user.id))
        await self.tree.sync()

bot = MusicBot()

@bot.tree.command(name='play')
@app_commands.describe(query='Song name or URL')
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()

    if not interaction.user.voice:
        await interaction.followup.send('❌ Join a voice channel first!')
        return

    player = bot.salad.players.get(interaction.guild.id)

    if not player:
        player = await bot.salad.createConnection({
            'guildId': interaction.guild.id,
            'voiceChannel': interaction.user.voice.channel.id,
            'textChannel': interaction.channel.id
        })
        await interaction.user.voice.channel.connect()

    result = await bot.salad.resolve(query, requester=interaction.user)
    tracks = result.get('tracks', [])

    if not tracks:
        await interaction.followup.send('❌ No tracks found!')
        return

    track = tracks[0]
    player.addToQueue(track)

    if not player.playing:
        await player.play()
        await interaction.followup.send(f'▶️ Now playing: **{track.title}**')
    else:
        await interaction.followup.send(f'➕ Added: **{track.title}**')

bot.run('putyourtokenhere.')
```
# Common Questions

**How do I configure Lavalink initially?**
- To configure Lavalink look [Here](https://github.com/lavalink-devs/Lavalink/blob/master/LavalinkServer/application.yml.example) For plugins look [Here](https://lavalink.dev/plugins.html)

**What skills do I need to use Salad?**
- Salad requires you have a little experience with python and discord.py

**My application can't locate the Salad package. What should I do?**
- This means you don't have Salad installed, To install it run: `pip install salada` and check if it's installed by doing `pip freeze` and searching for salada.

**Why should I choose Salad over alternative Lavalink packages?**
- Salad has a wide variety of features to use aswell as `enableReconnect, infiniteReconnect, maxReconnectAttempts` and autoplay coming soon.

# Acknowledgments

Appreciation to [southctrl](https://github.com/southctrl) for creating filters and enums!
