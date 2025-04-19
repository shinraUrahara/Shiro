import threading
from flask import Flask
import os
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp as youtube_dl
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import asyncio
import json
import random

# Flask for hosting
app = Flask(__name__)

@app.route('/')
def home():
    return "Discord bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web).start()

# Discord setup
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)
tree = bot.tree
GUILD_ID = discord.Object(id=1357634699375284346)  # Replace with your server ID

# Spotify setup
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_PLAYLIST_ID = os.getenv('SPOTIFY_PLAYLIST_ID')

if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    ))
else:
    sp = None
    print("⚠️ Spotify support disabled (missing credentials)")

# Global state
queue = []
volume_level = 1.0
loop_enabled = False
current_song = None

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': True
}

# Level system
levels = {}

def load_levels():
    try:
        with open('levels.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_levels():
    with open('levels.json', 'w') as f:
        json.dump(levels, f, indent=4)

levels = load_levels()

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    if user_id not in levels:
        levels[user_id] = {"xp": 0, "level": 1}

    levels[user_id]["xp"] += random.randint(5, 15)
    xp_needed = levels[user_id]["level"] * 100
    if levels[user_id]["xp"] >= xp_needed:
        levels[user_id]["level"] += 1
        levels[user_id]["xp"] = 0
        await message.channel.send(f"🎉 {message.author.mention} leveled up to level {levels[user_id]['level']}!")

    save_levels()
    await bot.process_commands(message)

def youtube_search(query):
    with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
        info = ydl.extract_info(f"ytsearch:{query}", download=False)
        if 'entries' in info and info['entries']:
            return info['entries'][0]['url']
    return None

async def play_next(interaction: discord.Interaction):
    global current_song
    if loop_enabled and current_song:
        queue.insert(0, current_song)
    if queue:
        voice_client = interaction.guild.voice_client
        url = queue.pop(0)
        current_song = url

        def after_playing(error):
            if error:
                print(f"Error: {error}")
            asyncio.run_coroutine_threadsafe(play_next(interaction), bot.loop)

        source = discord.FFmpegPCMAudio(
            url,
            **{
                **FFMPEG_OPTIONS,
                "options": f"-vn -filter:a volume={volume_level}"
            }
        )
        voice_client.play(source, after=after_playing)

async def add_to_queue(query: str, interaction: discord.Interaction):
    yt_url = youtube_search(query)
    if yt_url:
        queue.append(yt_url)
        if not interaction.guild.voice_client.is_playing():
            await play_next(interaction)

# Slash commands
@tree.command(name="help", description="Show all commands", guild=GUILD_ID)
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 Bot Commands", color=discord.Color.blue())
    embed.add_field(name="🎵 Music", value="/play, /playskip, /skip, /stop, /pause, /resume, /volume, /nowplaying, /queue, /loop", inline=False)
    embed.add_field(name="🎧 Playlist", value="/pl_add, /pl_play", inline=False)
    embed.add_field(name="📊 Leveling", value="/rank, /leaderboard", inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="play", description="Play a song by name", guild=GUILD_ID)
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    if not interaction.user.voice:
        await interaction.followup.send("❌ You must be in a voice channel!")
        return

    voice_client = interaction.guild.voice_client
    if not voice_client:
        voice_client = await interaction.user.voice.channel.connect()
    elif voice_client.channel != interaction.user.voice.channel:
        await voice_client.move_to(interaction.user.voice.channel)

    await add_to_queue(query, interaction)
    await interaction.followup.send(f"✅ Added to queue: `{query}`")

@tree.command(name="playskip", description="Skip and play song now", guild=GUILD_ID)
async def playskip(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    if not interaction.user.voice:
        await interaction.followup.send("❌ You must be in a voice channel!")
        return

    voice_client = interaction.guild.voice_client
    if not voice_client:
        voice_client = await interaction.user.voice.channel.connect()
    elif voice_client.channel != interaction.user.voice.channel:
        await voice_client.move_to(interaction.user.voice.channel)

    yt_url = youtube_search(query)
    if yt_url:
        queue.insert(0, yt_url)
        if voice_client.is_playing():
            voice_client.stop()
        else:
            await play_next(interaction)
        await interaction.followup.send(f"⏭️ Playing now: `{query}`")
    else:
        await interaction.followup.send("❌ Could not find that song.")

@tree.command(name="pl_add", description="Add a song to your Spotify playlist", guild=GUILD_ID)
async def pl_add(interaction: discord.Interaction, song: str):
    if not sp or not SPOTIFY_PLAYLIST_ID:
        await interaction.response.send_message("❌ Spotify playlist not configured.")
        return

    results = sp.search(q=song, type='track', limit=1)
    if not results['tracks']['items']:
        await interaction.response.send_message("❌ Song not found.")
        return

    track_id = results['tracks']['items'][0]['id']
    sp.playlist_add_items(SPOTIFY_PLAYLIST_ID, [track_id])
    await interaction.response.send_message(f"✅ Added to playlist: {results['tracks']['items'][0]['name']}")

@tree.command(name="pl_play", description="Play all songs from your Spotify playlist", guild=GUILD_ID)
async def pl_play(interaction: discord.Interaction):
    if not sp or not SPOTIFY_PLAYLIST_ID:
        await interaction.response.send_message("❌ Spotify playlist not configured.")
        return

    await interaction.response.defer()
    playlist = sp.playlist_tracks(SPOTIFY_PLAYLIST_ID)
    if not playlist['items']:
        await interaction.followup.send("❌ Playlist is empty.")
        return

    for item in playlist['items']:
        track = item['track']
        query = f"{track['name']} {track['artists'][0]['name']}"
        await add_to_queue(query, interaction)

    await interaction.followup.send(f"✅ Added {len(playlist['items'])} songs from playlist.")

@tree.command(name="skip", description="Skip current song", guild=GUILD_ID)
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await interaction.response.send_message("⏭️ Skipped!")
    else:
        await interaction.response.send_message("❌ Nothing playing.")

@tree.command(name="stop", description="Stop music and clear queue", guild=GUILD_ID)
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        queue.clear()
        vc.stop()
        await vc.disconnect()
        await interaction.response.send_message("⏹️ Stopped.")
    else:
        await interaction.response.send_message("❌ Not in a voice channel.")

@tree.command(name="pause", description="Pause the song", guild=GUILD_ID)
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("⏸️ Paused.")
    else:
        await interaction.response.send_message("❌ Nothing to pause.")

@tree.command(name="resume", description="Resume the song", guild=GUILD_ID)
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("▶️ Resumed.")
    else:
        await interaction.response.send_message("❌ Nothing is paused.")

@tree.command(name="volume", description="Set the music volume", guild=GUILD_ID)
@app_commands.describe(level="Volume from 1 to 100")
async def volume(interaction: discord.Interaction, level: int):
    global volume_level
    if 1 <= level <= 100:
        volume_level = level / 100
        await interaction.response.send_message(f"🔊 Volume set to {level}%")
    else:
        await interaction.response.send_message("❌ Volume must be 1–100.")

@tree.command(name="nowplaying", description="Show current song", guild=GUILD_ID)
async def nowplaying(interaction: discord.Interaction):
    if current_song:
        await interaction.response.send_message(f"🎶 Now Playing: {current_song}")
    else:
        await interaction.response.send_message("❌ Nothing playing.")

@tree.command(name="queue", description="Show song queue", guild=GUILD_ID)
async def show_queue(interaction: discord.Interaction):
    if queue:
        msg = "\n".join([f"{i+1}. {url}" for i, url in enumerate(queue)])
        await interaction.response.send_message(f"📜 Queue:\n{msg}")
    else:
        await interaction.response.send_message("📭 Queue is empty.")

@tree.command(name="loop", description="Toggle loop", guild=GUILD_ID)
async def loop(interaction: discord.Interaction):
    global loop_enabled
    loop_enabled = not loop_enabled
    await interaction.response.send_message(f"🔁 Loop is now {'enabled' if loop_enabled else 'disabled'}.")

@tree.command(name="rank", description="Check your level", guild=GUILD_ID)
async def rank(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    level_data = levels.get(user_id, {"xp": 0, "level": 1})
    await interaction.response.send_message(
        f"🏆 {interaction.user.display_name} - Level: {level_data['level']} | XP: {level_data['xp']}/{level_data['level'] * 100}"
    )

@tree.command(name="leaderboard", description="Top 10 users", guild=GUILD_ID)
async def leaderboard(interaction: discord.Interaction):
    sorted_users = sorted(levels.items(), key=lambda x: (x[1]['level'], x[1]['xp']), reverse=True)[:10]
    embed = discord.Embed(title="🏆 Leaderboard", color=discord.Color.gold())
    for i, (user_id, data) in enumerate(sorted_users, 1):
        user = await bot.fetch_user(int(user_id))
        embed.add_field(name=f"{i}. {user.display_name}", value=f"Level {data['level']} | XP {data['xp']}", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_ready():
    await bot.wait_until_ready()
    try:
        synced = await tree.sync(guild=GUILD_ID)
        print(f"✅ Synced {len(synced)} commands")
    except Exception as e:
        print(f"❌ Failed to sync: {e}")
    print(f"✅ Logged in as {bot.user.name}")

# Run bot
token = os.getenv('DISCORD_TOKEN')
if not token:
    raise ValueError("No DISCORD_TOKEN set!")
bot.run(token)
