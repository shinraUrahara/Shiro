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
tree = app_commands.CommandTree(bot)

# Spotify Setup
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    ))
else:
    print("Spotify support disabled (missing credentials)")

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
    'quiet': True,
    'extract_flat': True
}

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

# Slash Commands
@tree.command(name="help", description="Show all commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 Bot Commands", color=discord.Color.blue())
    embed.add_field(name="🎵 Music", value="/play, /playskip, /skip, /stop, /pause, /resume, /volume, /nowplaying, /queue, /loop", inline=False)
    embed.add_field(name="📊 Leveling", value="/rank - Check your level\n/leaderboard - Top users", inline=False)
    await interaction.response.send_message(embed=embed)

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
    with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
        info = ydl.extract_info(f"ytsearch:{query}", download=False)
        url = info['entries'][0]['url']
        queue.append(url)
        if not interaction.guild.voice_client.is_playing():
            await play_next(interaction)

@tree.command(name="play", description="Play a song")
async def play(interaction: discord.Interaction, url: str):
    await interaction.response.defer()
    if not interaction.user.voice:
        await interaction.followup.send("❌ You must be in a voice channel!")
        return

    voice_client = interaction.guild.voice_client
    if not voice_client:
        voice_client = await interaction.user.voice.channel.connect()
    elif voice_client.channel != interaction.user.voice.channel:
        await voice_client.move_to(interaction.user.voice.channel)

    if "open.spotify.com" in url:
        if not SPOTIFY_CLIENT_ID:
            await interaction.followup.send("❌ Spotify support disabled")
            return
        try:
            if "track" in url:
                track = sp.track(url)
                query = f"{track['name']} {track['artists'][0]['name']}"
                await add_to_queue(query, interaction)
                await interaction.followup.send(f"✅ Added: {track['name']}")
            elif "playlist" in url or "album" in url:
                items = sp.playlist_tracks(url)['items'] if "playlist" in url else sp.album_tracks(url)['items']
                for item in items:
                    track = item['track'] if 'track' in item else item
                    query = f"{track['name']} {track['artists'][0]['name']}"
                    await add_to_queue(query, interaction)
                await interaction.followup.send(f"✅ Added {len(items)} songs!")
        except Exception as e:
            await interaction.followup.send(f"❌ Spotify error: {e}")
    else:
        await add_to_queue(url, interaction)
        await interaction.followup.send(f"✅ Added to queue!")

@tree.command(name="playskip", description="Skip current and play song immediately")
async def playskip(interaction: discord.Interaction, url: str):
    await interaction.response.defer()
    if not interaction.user.voice:
        await interaction.followup.send("❌ You must be in a voice channel!")
        return

    voice_client = interaction.guild.voice_client
    if not voice_client:
        voice_client = await interaction.user.voice.channel.connect()
    elif voice_client.channel != interaction.user.voice.channel:
        await voice_client.move_to(interaction.user.voice.channel)

    with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
        info = ydl.extract_info(f"ytsearch:{url}", download=False)
        yt_url = info['entries'][0]['url']
        queue.insert(0, yt_url)
        if voice_client.is_playing():
            voice_client.stop()
        else:
            await play_next(interaction)
    await interaction.followup.send("⏭️ Playing now!")

@tree.command(name="skip", description="Skip current song")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await interaction.response.send_message("⏭️ Skipped!")
    else:
        await interaction.response.send_message("❌ Nothing playing!")

@tree.command(name="stop", description="Stop music and clear queue")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        queue.clear()
        vc.stop()
        await vc.disconnect()
        await interaction.response.send_message("⏹️ Stopped!")
    else:
        await interaction.response.send_message("❌ Not in voice channel!")

@tree.command(name="pause", description="Pause current song")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("⏸️ Paused!")
    else:
        await interaction.response.send_message("❌ Nothing to pause!")

@tree.command(name="resume", description="Resume paused song")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("▶️ Resumed!")
    else:
        await interaction.response.send_message("❌ Nothing is paused!")

@tree.command(name="volume", description="Set the music volume (1-100)")
@app_commands.describe(level="Volume level from 1 to 100")
async def volume(interaction: discord.Interaction, level: int):
    global volume_level
    if 1 <= level <= 100:
        volume_level = level / 100
        await interaction.response.send_message(f"🔊 Volume set to {level}%")
    else:
        await interaction.response.send_message("❌ Please provide a volume between 1 and 100.")

@tree.command(name="nowplaying", description="Show currently playing song")
async def nowplaying(interaction: discord.Interaction):
    if current_song:
        await interaction.response.send_message(f"🎶 Now Playing: {current_song}")
    else:
        await interaction.response.send_message("❌ Nothing is playing.")

@tree.command(name="queue", description="Show the music queue")
async def show_queue(interaction: discord.Interaction):
    if queue:
        msg = "\n".join([f"{i+1}. {url}" for i, url in enumerate(queue)])
        await interaction.response.send_message(f"📜 Queue:\n{msg}")
    else:
        await interaction.response.send_message("📭 The queue is empty.")

@tree.command(name="loop", description="Toggle looping for current song")
async def loop(interaction: discord.Interaction):
    global loop_enabled
    loop_enabled = not loop_enabled
    await interaction.response.send_message(f"🔁 Looping is now {'enabled' if loop_enabled else 'disabled'}.")

@tree.command(name="rank", description="Check your level")
async def rank(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    level_data = levels.get(user_id, {"xp": 0, "level": 1})
    await interaction.response.send_message(
        f"🏆 **{interaction.user.display_name}**\nLevel: {level_data['level']}\nXP: {level_data['xp']}/{level_data['level'] * 100}"
    )

@tree.command(name="leaderboard", description="Show top 10 users")
async def leaderboard(interaction: discord.Interaction):
    sorted_users = sorted(levels.items(), key=lambda x: (x[1]['level'], x[1]['xp']), reverse=True)[:10]
    embed = discord.Embed(title="🏆 Leaderboard", color=discord.Color.gold())
    for i, (user_id, data) in enumerate(sorted_users, 1):
        user = await bot.fetch_user(int(user_id))
        embed.add_field(name=f"{i}. {user.display_name}", value=f"Level: {data['level']} | XP: {data['xp']}", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {bot.user.name}")

bot_token = os.getenv('DISCORD_TOKEN')
if not bot_token:
    raise ValueError("No DISCORD_TOKEN set!")
bot.run(bot_token)
