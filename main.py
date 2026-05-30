import os
import json
import logging
import asyncio
from datetime import datetime
from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import discord
from discord.ext import commands

from database import upsert_task_state, get_incomplete_tasks
from agent import prioritize_tasks, schedule_tasks, process_webhook_interrupt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Calendar Orchestrator")
scheduler = AsyncIOScheduler()

# Dummy state management mapping
system_state = {
    "status": "IDLE" # IDLE, AWAITING_REVIEW
}

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")

# Setup Discord Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}')

@bot.command(name="now")
async def now_command(ctx, *, task: str = ""):
    logger.info("Processing mid-day real-time interrupt.")
    if not task:
        await ctx.send("Please specify a task. Example: `/now Urgent meeting for 1 hour`")
        return
        
    current_time = datetime.now().isoformat()
    current_schedule = [] # Mocked Calendar MCP
    new_schedule = process_webhook_interrupt(current_schedule, task, current_time)
    
    await ctx.send(f"Urgent task inserted. Schedule updated: \n```json\n{json.dumps(new_schedule, indent=2)}\n```")

@bot.command(name="approve")
async def approve_command(ctx):
    await ctx.send("Confirmed. Pushing schedule to Google Calendar.")
    system_state["status"] = "IDLE"
    upsert_task_state("system_state", {"status": "IDLE", "last_updated": datetime.now().isoformat()})

@bot.command(name="modify")
async def modify_command(ctx, *, feedback: str):
    await ctx.send(f"Feedback received: '{feedback}'. Updating schedule...")
    # Logic to adjust schedule based on feedback

@bot.command(name="triage")
async def triage_command(ctx):
    await ctx.send("Manually triggering nightly triage job...")
    await nightly_triage_job()


async def send_discord_message(text: str):
    # Sends a message to a specific channel if DISCORD_CHANNEL_ID is set
    channel_id_str = os.environ.get("DISCORD_CHANNEL_ID")
    if not channel_id_str:
        logger.warning("DISCORD_CHANNEL_ID not set. Cannot send proactive messages.")
        return
    channel = bot.get_channel(int(channel_id_str))
    if channel:
        await channel.send(text)

async def nightly_triage_job():
    """
    Executes at 21:00 CEST. Post-mortem & Forecast.
    """
    logger.info("Starting Nightly Triage...")
    await send_discord_message("Did you finish the prioritized tasks today? Reply with updates.")
    
    system_state["status"] = "AWAITING_REVIEW"
    upsert_task_state("system_state", {"status": "AWAITING_REVIEW", "last_updated": datetime.now().isoformat()})
    
    goals_md = "Focus on deep engineering sprints and fitness."
    raw_tasks = "Fix the authentication bug. Go to the gym. Buy groceries."
    prioritized = prioritize_tasks(raw_tasks, goals_md)
    
    fixed_events = [
        {"title": "Team Standup", "start_time": "10:00:00", "end_time": "10:30:00", "type": "fixed"}
    ]
    
    new_schedule = schedule_tasks(prioritized, fixed_events, datetime.now().isoformat())
    schedule_markdown = "### Tomorrow's Forecast\n"
    for ev in new_schedule:
        schedule_markdown += f"- **{ev.get('title')}**: {ev.get('start_time')} - {ev.get('end_time')}\n"
        
    await send_discord_message(schedule_markdown)
    logger.info("Nightly Triage Forecast sent.")

@app.on_event("startup")
async def startup_event():
    scheduler.add_job(nightly_triage_job, CronTrigger(hour=21, minute=0, timezone='Europe/Berlin'))
    scheduler.start()
    if DISCORD_BOT_TOKEN:
        asyncio.create_task(bot.start(DISCORD_BOT_TOKEN))
    else:
        logger.warning("No DISCORD_BOT_TOKEN set, Discord bot will not start.")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    await bot.close()

@app.get("/health")
def health_check():
    """
    Pinged by UptimeRobot every ~5-10 minutes to keep the Render instance awake.
    """
    return {"status": "ok", "timestamp": datetime.now().isoformat()}
