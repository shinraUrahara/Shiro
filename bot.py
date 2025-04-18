import threading
from flask import Flask
import os
import discord
from discord.ext import commands, tasks
from discord import app_commands  # Slash Commands
import youtube_dl
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import asyncio
import json
import random

# Flask setup (for keeping bot alive)
app = Flask(__name__)

@app.route('/')
def home():
    return "Discord bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web).start()

# Discord Bot Setup
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)
tree = app_commands.CommandTree(bot)  # Slash commands

# Spotify Setup (optional)
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    ))
else:
    print("Spotify support disabled (missing credentials)")

# Music Queue
queue = []
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'extract_flat': True
}

# ===== Slash Commands Setup =====
@tree.command(name="help", description="Show all available commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎵 Music Bot Commands",
        description="Here's what I can do:",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="🎶 Music",
        value="`/play [url]` - Play YouTube/Spotify\n`/skip` - Skip song\n`/stop` - Stop music",
        inline=False
    )
    embed.add_field(
        name="📊 Leveling",
        value="`/rank` - Check your level\n`/leaderboard` - Top users",
        inline=False
    )
    await interaction.response.send_message(embed=embed)

# ===== Music Commands (Slash) =====
@tree.command(name="play", description="Play a song from YouTube or Spotify")
async def play(interaction: discord.Interaction, url: str):
    await interation.response.defer()  # Bot is "thinking"

    # Check if user is in a voice channel
    if not interaction.user.voice:
        await interaction.followup.send("❌ You must be in a voice channel!")
        return

    voice_client = interaction.guild.voice_client
    if not voice_client:
        voice_client = await interaction.user.voice.channel.connect()
    elif voice_client.channel != interaction.user.voice.channel:
        await voice_client.move_to(interaction.user.voice.channel)

    # Check if URL is Spotify
    if "open.spotify.com" in url:
        if not SPOTIFY_CLIENT_ID:
            await interaction.followup.send("❌ Spotify support is disabled (missing API keys)")
            return

        try:
            if "track" in url:  # Single track
                track = sp.track(url)
                query = f"{track['name']} {track['artists'][0]['name']}"
            elif "playlist" in url:  # Playlist
                playlist = sp.playlist_tracks(url)
                for item in playlist['items']:
                    track = item['track']
                    query = f"{track['name']} {track['artists'][0]['name']}"
                    await add_to_queue(query, interaction)
                await interaction.followup.send(f"✅ Added {len(playlist['items'])} songs from Spotify!")
                return
        except Exception as e:
            await interaction.followup.send(f"❌ Spotify error: {e}")
            return
    else:
        query = url  # YouTube URL

    await add_to_queue(query, interaction)
    await interaction.followup.send(f"✅ Added to queue: `{query}`")

async def add_to_queue(query: str, interaction: discord.Interaction):
    with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)
            url = info['entries'][0]['url']
            queue.append(url)
            if not interaction.guild.voice_client.is_playing():
                await play_next(interaction)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}")

async def play_next(interaction: discord.Interaction):
    if queue:
        voice_client = interaction.guild.voice_client
        voice_client.play(
            discord.FFmpegPCMAudio(queue.pop(0), 
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next(interaction), bot.loop)
        )

@tree.command(name="skip", description="Skip the current song")
async def skip(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await interaction.response.send_message("⏭️ Skipped!")
    else:
        await interaction.response.send_message("❌ Nothing is playing!")

# ===== Leveling System (Slash) =====
@tree.command(name="rank", description="Check your level and XP")
async def rank(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    level_data = levels.get(user_id, {"xp": 0, "level": 1})
    await interaction.response.send_message(
        f"🎖️ **{interaction.user.display_name}**\n"
        f"Level: **{level_data['level']}**\n"
        f"XP: **{level_data['xp']}**"
    )

# ===== Run Bot =====
@bot.event
async def on_ready():
    await tree.sync()  # Sync slash commands
    print(f"Logged in as {bot.user.name}")

bot_token = os.getenv('DISCORD_TOKEN')
if not bot_token:
    raise ValueError("No DISCORD_TOKEN set!")
bot.run(bot_token)
