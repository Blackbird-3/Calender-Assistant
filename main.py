import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import discord
from discord.ext import commands
from google import genai

from database import upsert_task_state, get_incomplete_tasks
from agent import prioritize_tasks, schedule_tasks, process_webhook_interrupt
from calendar_service import get_events, update_calendar_schedule

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Calendar Orchestrator")
scheduler = AsyncIOScheduler()

# Dummy state management mapping
system_state = {
    "status": "IDLE", # IDLE, AWAITING_REVIEW
    "forecast_schedule": []
}

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")

# Setup Discord Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}')

@bot.event
async def on_message(message):
    # Ignore bot's own messages
    if message.author == bot.user:
        return
        
    # Check if the message is a command
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.process_commands(message)
        return
        
    # Handle conversational reviews
    if system_state["status"] == "AWAITING_UPDATES":
        logger.info(f"Received updates: {message.content}")
        await message.channel.send("Processing your updates and fetching tasks from Notion...")
        
        # Get real tasks from Notion
        from notion_service import get_notion_tasks
        notion_tasks = get_notion_tasks()
        
        if not notion_tasks:
            # Fallback if Notion isn't configured or empty
            raw_tasks = f"Mock Tasks: Fix the authentication bug. Go to the gym.\nUser Updates: {message.content}"
        else:
            raw_tasks = f"Notion Tasks: {notion_tasks}\nUser Updates: {message.content}"
            
        goals_md = "Focus on deep engineering sprints and fitness."
        
        try:
            prioritized = await prioritize_tasks(raw_tasks, goals_md)
            
            berlin_tz = ZoneInfo("Europe/Berlin")
            now_dt = datetime.now(berlin_tz)
            tomorrow_start = (now_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow_end = tomorrow_start + timedelta(days=1)
            
            from calendar_service import get_events
            raw_events = get_events(time_min=tomorrow_start.isoformat(), time_max=tomorrow_end.isoformat())
            
            fixed_events = []
            for e in raw_events:
                start = e.get('start', {}).get('dateTime') or e.get('start', {}).get('date')
                end = e.get('end', {}).get('dateTime') or e.get('end', {}).get('date')
                if start and end:
                    fixed_events.append({
                        "title": e.get('summary', 'Busy'),
                        "start_time": start,
                        "end_time": end,
                        "type": "fixed"
                    })
            
            new_schedule = await schedule_tasks(prioritized, fixed_events, now_dt.isoformat(), user_updates=message.content)
            system_state["forecast_schedule"] = new_schedule
            
            if not new_schedule:
                await message.channel.send("⚠️ The AI failed to generate a valid forecast.")
                return
                
            schedule_markdown = "### Tomorrow's Forecast\n"
            for ev in new_schedule:
                schedule_markdown += f"- **{ev.get('title')}**: {ev.get('start_time')} - {ev.get('end_time')}\n"
                
            await message.channel.send(schedule_markdown)
            
            system_state["status"] = "AWAITING_REVIEW"
            upsert_task_state("system_state", {"status": "AWAITING_REVIEW", "last_updated": datetime.now().isoformat()})
        except Exception as e:
            logger.error(f"Error generating forecast: {e}")
            await message.channel.send(f"⚠️ Failed to generate nightly forecast: {e}")
        return

    elif system_state["status"] == "AWAITING_REVIEW":
        logger.info(f"Processing conversational review message: {message.content}")
        client = genai.Client()
        
        prompt = f"""
        The user is currently reviewing tomorrow's schedule forecast.
        They said: "{message.content}"
        
        If this is a confirmation (e.g. "looks good", "approve", "looks clean", "ok"), output JSON: {{"action": "approve", "reply": "Confirmed! Pushing tomorrow's schedule to your calendar."}}
        If this is a modification (e.g. "remove gym", "add 1 hour of piano"), output JSON: {{"action": "modify", "reply": "Updating schedule with your changes...", "feedback": "their specific request"}}
        If they are asking a question (e.g. "what tasks did I have?"), output JSON: {{"action": "answer", "reply": "a helpful response answering their query"}}
        
        Return ONLY the raw JSON.
        """
        try:
            response = await client.aio.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            res = json.loads(text.strip())
            
            action = res.get("action")
            reply = res.get("reply")
            
            await message.channel.send(reply)
            
            if action == "approve":
                system_state["status"] = "IDLE"
                upsert_task_state("system_state", {"status": "IDLE", "last_updated": datetime.now().isoformat()})
                forecast_schedule = system_state.get("forecast_schedule", [])
                if forecast_schedule:
                    success = update_calendar_schedule(forecast_schedule)
                    if success:
                        await message.channel.send("Calendar successfully updated!")
                    else:
                        await message.channel.send("⚠️ Failed to update Google Calendar. Check Render logs for Google API errors.")
            elif action == "modify":
                forecast_schedule = system_state.get("forecast_schedule", [])
                if not forecast_schedule:
                    await message.channel.send("⚠️ No active forecast found to modify. Please run `/triage` again.")
                    return
                
                from agent import modify_schedule
                berlin_tz = ZoneInfo("Europe/Berlin")
                new_schedule = await modify_schedule(forecast_schedule, message.content, datetime.now(berlin_tz).isoformat())
                
                system_state["forecast_schedule"] = new_schedule
                
                schedule_markdown = "### Updated Forecast\n"
                for ev in new_schedule:
                    schedule_markdown += f"- **{ev.get('title')}**: {ev.get('start_time')} - {ev.get('end_time')}\n"
                
                await message.channel.send(schedule_markdown)
                # Stay in AWAITING_REVIEW state so user can review the modified schedule
        except Exception as e:
            logger.error(f"Error handling conversational review message: {e}")
            await message.channel.send("Sorry, I had trouble processing that request.")
            
    elif system_state.get("status", "IDLE") == "IDLE":
        logger.info(f"Processing general conversation: {message.content}")
        from notion_service import get_notion_tasks
        notion_tasks = get_notion_tasks()
        
        client = genai.Client()
        prompt = f"""
        You are a helpful AI calendar and productivity assistant.
        The user just said: "{message.content}"
        
        Here is the user's current Notion task list context:
        {notion_tasks if notion_tasks else "No tasks found."}
        
        Answer their question or respond naturally, helpfully, and concisely.
        """
        try:
            response = await client.aio.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            await message.channel.send(response.text.strip())
        except Exception as e:
            logger.error(f"Error in general conversation: {e}")

@bot.command(name="now")
async def now_command(ctx, *, task: str = ""):
    logger.info("Processing mid-day real-time interrupt.")
    if not task:
        await ctx.send("Please specify a task. Example: `/now Urgent meeting for 1 hour`")
        return
        
    berlin_tz = ZoneInfo("Europe/Berlin")
    current_time = datetime.now(berlin_tz).isoformat()
    await ctx.send("Fetching active schedule from Google Calendar...")
    
    # 1. Fetch next 24 hours of events from Google Calendar
    from datetime import timedelta
    now_dt = datetime.utcnow()
    time_min = now_dt.isoformat() + 'Z'
    time_max = (now_dt + timedelta(hours=24)).isoformat() + 'Z'
    events = get_events(time_min=time_min, time_max=time_max)
    current_schedule = []
    for event in events:
        is_flex = '[Flexible]' in event.get('description', '') or '#flex' in event.get('description', '')
        current_schedule.append({
            "title": event.get('summary'),
            "start_time": event.get('start', {}).get('dateTime'),
            "end_time": event.get('end', {}).get('dateTime'),
            "type": "flexible" if is_flex else "fixed"
        })
        
    # 2. Reschedule
    new_schedule = await process_webhook_interrupt(current_schedule, task, current_time)
    
    # 3. Update Google Calendar
    success = update_calendar_schedule(new_schedule)
    if success:
        await ctx.send(f"Urgent task inserted. Schedule updated: \n```json\n{json.dumps(new_schedule, indent=2)}\n```")
    else:
        await ctx.send("⚠️ Failed to update Google Calendar. Check Render logs for Google API errors.")

@bot.command(name="approve")
async def approve_command(ctx):
    await ctx.send("Confirmed. Pushing schedule to Google Calendar.")
    system_state["status"] = "IDLE"
    upsert_task_state("system_state", {"status": "IDLE", "last_updated": datetime.now().isoformat()})
    
    forecast_schedule = system_state.get("forecast_schedule", [])
    if forecast_schedule:
        success = update_calendar_schedule(forecast_schedule)
        if success:
            await ctx.send("Calendar successfully updated!")
        else:
            await ctx.send("⚠️ Failed to update Google Calendar. Check Render logs for Google API errors.")
    else:
        await ctx.send("No forecast schedule found to push.")

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
    await send_discord_message("Did you finish your tasks today? Reply with updates, and let me know if there are any extra tasks for tomorrow that aren't on Notion.")
    
    system_state["status"] = "AWAITING_UPDATES"
    upsert_task_state("system_state", {"status": "AWAITING_UPDATES", "last_updated": datetime.now().isoformat()})

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
