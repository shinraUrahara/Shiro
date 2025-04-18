import threading
from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "Discord bot is running."

def run_web():
    port = int(os.environ.get("PORT", 10000))  # use Render-assigned port or fallback
    app.run(host='0.0.0.0', port=port)

# Start Flask in a separate thread
threading.Thread(target=run_web).start()
import discord
from discord.ext import commands, tasks
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
scheduler = AsyncIOScheduler()

# Check for owner permission
def is_owner():
    async def predicate(ctx):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")
    scheduler.start()

@bot.command()
@is_owner()
async def shutdown(ctx):
    await ctx.send("Shutting down 📴")
    await bot.close()

@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! 🏓 Latency: {round(bot.latency * 1000)}ms")

@bot.command()
@is_owner()
async def restart(ctx):
    await ctx.send("Restarting bot... 🔄")
    await bot.close()
    await bot.run(TOKEN)

@bot.command()
@is_owner()
async def say(ctx, *, message):
    await ctx.send(message)

@bot.command()
@is_owner()
async def ban(ctx, user: discord.User, reason: str = "No reason provided"):
    await ctx.guild.ban(user, reason=reason)
    await ctx.send(f"Banned {user.name} for: {reason}")
    log_channel = bot.get_channel(CHANNEL_ID)
    await log_channel.send(f"Banned {user.name} for: {reason}")

@bot.command()
@is_owner()
async def kick(ctx, user: discord.User, reason: str = "No reason provided"):
    await ctx.guild.kick(user, reason=reason)
    await ctx.send(f"Kicked {user.name} for: {reason}")
    log_channel = bot.get_channel(CHANNEL_ID)
    await log_channel.send(f"Kicked {user.name} for: {reason}")

@bot.command()
@is_owner()
async def mute(ctx, user: discord.User, time: int, reason: str = "No reason provided"):
    # Mute the user for `time` seconds
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
    await user.add_roles(muted_role)
    await ctx.send(f"Muted {user.name} for {time} seconds.")
    log_channel = bot.get_channel(CHANNEL_ID)
    await log_channel.send(f"Muted {user.name} for {time} seconds. Reason: {reason}")
    await asyncio.sleep(time)
    await user.remove_roles(muted_role)

@bot.command()
async def members(ctx):
    guild = ctx.guild
    await ctx.send(f"👥 Members in {guild.name}: {guild.member_count}")

# Scheduler Task Example
@scheduler.scheduled_job(IntervalTrigger(hours=1))
async def scheduled_task():
    log_channel = bot.get_channel(CHANNEL_ID)
    await log_channel.send("⏰ Hourly Reminder!")

@bot.command()
@is_owner()
async def upload(ctx, file: discord.File):
    await ctx.send("Uploading file!")
    await ctx.send(file=file)

# Logging important actions
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.content.startswith("!"):
        log_channel = bot.get_channel(CHANNEL_ID)
        await log_channel.send(f"Command {message.content} used by {message.author.name}")
    await bot.process_commands(message)

bot.run(TOKEN)
