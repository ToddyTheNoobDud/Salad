# Salad

[![License: GPL](https://img.shields.io/github/license/ToddyTheNoobDud/salad?style=flat-square&logo=gnu&logoColor=white&color=A42E2B&labelColor=2f2f2f)](https://github.com/ToddyTheNoobDud/salad/blob/main/LICENSE) [![Python](https://img.shields.io/pypi/pyversions/salad?style=flat-square&logo=python&logoColor=white&color=3776AB&labelColor=2f2f2f)](https://pypi.org/project/salada/) [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg?style=flat-square&logo=python&logoColor=white)](https://github.com/psf/black) [![Discord](https://img.shields.io/discord/899324069235810315?style=flat-square&logo=discord&logoColor=white&color=5865F2&label=Support&labelColor=2f2f2f)](https://discord.gg/UKNDx2JWa5)

Salad is a lightning-fast, completely asynchronous Python framework designed for effortless [Lavalink](https://github.com/freyacodes/Lavalink) integration with [discord.py](https://github.com/Rapptz/discord.py). With full [Lavalink](https://github.com/freyacodes/Lavalink) specification support, clean API architecture, and robust integrated Spotify and Apple Music functionality, Salad enables creators to craft outstanding music bots effortlessly.

Developed as an improved fork of [AquaLink](https://github.com/ToddyTheNoobDud/AquaLink), Salad provides enhanced performance and developer satisfaction.

## Essential Resources
- [Discord Community Hub](https://discord.gg/UKNDx2JWa5)
- [PyPI Distribution](https://pypi.org/project/salada/)

# Setup Instructions
Requires Python 3.8 or newer and current pip version.

> Production Version (Suggested)

pip install salada

> Bleeding Edge (Newest Features)

pip install git+https://github.com/ToddyTheNoobDud/salad

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

bot.run('YOUR_BOT_TOKEN_HERE')
```
# Common Questions

**How do I configure Lavalink initially?**
- Salad needs an active Lavalink server to operate. Get the newest Lavalink build [here](https://github.com/freyacodes/Lavalink/releases/latest), set up your `application.yml`, and launch the server prior to starting Salad in your application.

**What skills do I need to use Salad?**
- You need moderate Python knowledge, strong understanding of async programming patterns, and practical discord.py experience. Knowledge of music bot design is beneficial but not essential.

**My application can't locate the Salad package. What should I do?**
- This usually indicates Salad isn't present in your Python setup. Execute `pip install salad` or follow the [setup commands](#setup-instructions) above. When working with virtual environments, verify you've enabled the appropriate one.

**Why should I choose Salad over alternative Lavalink packages?**
- Salad delivers exceptional speed, a user-friendly and thoroughly documented API, consistent updates featuring current Lavalink capabilities, native compatibility with popular streaming services, and a vibrant Discord community prepared to assist.

**Can Salad work with Lavalink extensions?**
- Absolutely! Salad keeps complete alignment with the Lavalink specification, including extension compatibility. You can utilize any Lavalink extension smoothly with Salad.

# Acknowledgments

Appreciation to [southctrl](https://github.com/southctrl) for creating filters and enums!
