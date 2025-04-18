import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
from flask import Flask
import threading
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))  # Your Discord user ID
GUILD_ID = int(os.getenv("GUILD_ID"))  # Your server ID
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", 0))

# Set up Flask to keep Render happy
app = Flask(__name__)

@app.route('/')
def home():
    return "Discord bot is running."

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web).start()

# Set up Discord client
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree
scheduler = AsyncIOScheduler()

# Utility: Admin check
def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator or interaction.user.id == OWNER_ID

# On Ready
@bot.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {bot.user} | Synced commands")
    scheduler.start()

# Log function
async def log_action(guild: discord.Guild, message: str):
    if LOG_CHANNEL_ID:
        channel = guild.get_channel(LOG_CHANNEL_ID)
        if channel:
            await channel.send(message)

# Admin Commands
@tree.command(name="ban", description="Ban a member", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Member to ban", reason="Reason")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
    if not is_admin(interaction): return await interaction.response.send_message("You aren't allowed to use this.", ephemeral=True)
    await member.ban(reason=reason)
    await interaction.response.send_message(f"{member} was banned. Reason: {reason}")
    await log_action(interaction.guild, f"{member} was banned by {interaction.user}. Reason: {reason}")

@tree.command(name="kick", description="Kick a member", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Member to kick")
async def kick(interaction: discord.Interaction, member: discord.Member):
    if not is_admin(interaction): return await interaction.response.send_message("You aren't allowed to use this.", ephemeral=True)
    await member.kick()
    await interaction.response.send_message(f"{member} was kicked.")
    await log_action(interaction.guild, f"{member} was kicked by {interaction.user}.")

@tree.command(name="mute", description="Timeout a member", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Member to mute", duration="Duration in minutes")
async def mute(interaction: discord.Interaction, member: discord.Member, duration: int):
    if not is_admin(interaction): return await interaction.response.send_message("You aren't allowed to use this.", ephemeral=True)
    until = datetime.utcnow() + timedelta(minutes=duration)
    await member.timeout(until, reason=f"Muted by {interaction.user}")
    await interaction.response.send_message(f"{member} has been muted for {duration} minutes.")
    await log_action(interaction.guild, f"{member} was muted by {interaction.user} for {duration} minutes.")

@tree.command(name="unmute", description="Remove timeout from member", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Member to unmute")
async def unmute(interaction: discord.Interaction, member: discord.Member):
    if not is_admin(interaction): return await interaction.response.send_message("You aren't allowed to use this.", ephemeral=True)
    await member.timeout(None)
    await interaction.response.send_message(f"{member} has been unmuted.")
    await log_action(interaction.guild, f"{member} was unmuted by {interaction.user}.")

@tree.command(name="warn", description="Warn a user", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="User to warn", reason="Reason")
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    if not is_admin(interaction): return await interaction.response.send_message("You aren't allowed to use this.", ephemeral=True)
    await interaction.response.send_message(f"{member.mention} has been warned: {reason}")
    await log_action(interaction.guild, f"{member} was warned by {interaction.user}. Reason: {reason}")

@tree.command(name="purge", description="Delete messages", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(amount="Number of messages to delete")
async def purge(interaction: discord.Interaction, amount: int):
    if not is_admin(interaction): return await interaction.response.send_message("You aren't allowed to use this.", ephemeral=True)
    await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"Deleted {amount} messages.", ephemeral=True)

# Public Commands
@tree.command(name="schedule", description="Schedule a message", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(minutes="Minutes to wait", message="Message to send")
async def schedule(interaction: discord.Interaction, minutes: int, message: str):
    async def send_later():
        await asyncio.sleep(minutes * 60)
        await interaction.channel.send(f"[Scheduled] {message}")
    asyncio.create_task(send_later())
    await interaction.response.send_message(f"Scheduled message in {minutes} minutes.", ephemeral=True)

@tree.command(name="announce", description="Send a message to a channel", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(channel="Target channel", message="Message to send")
async def announce(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    await channel.send(message)
    await interaction.response.send_message(f"Sent message to {channel.mention}", ephemeral=True)

@tree.command(name="upload", description="Upload a file", guild=discord.Object(id=GUILD_ID))
async def upload(interaction: discord.Interaction):
    await interaction.response.send_message("Please upload a file with this command.", ephemeral=True)

@tree.command(name="help", description="List all commands", guild=discord.Object(id=GUILD_ID))
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("""
**Admin-only:**
/ban, /kick, /mute, /unmute, /warn, /purge

**Everyone:**
/schedule, /announce, /upload, /help
""", ephemeral=True)

bot.run(TOKEN)
