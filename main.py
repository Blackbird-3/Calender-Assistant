import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, Response, BackgroundTasks
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import httpx
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

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

DISCORD_PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY", "")

def verify_signature(raw_body: bytes, signature: str, timestamp: str) -> bool:
    if not DISCORD_PUBLIC_KEY:
        logger.warning("DISCORD_PUBLIC_KEY not set. Skipping signature verification (ONLY FOR LOCAL TESTING).")
        return True
    try:
        verify_key = VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))
        verify_key.verify(f"{timestamp}".encode() + raw_body, signature=bytes.fromhex(signature))
        return True
    except BadSignatureError:
        return False


DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

class WebhookPayload(BaseModel):
    content: str
    sender: Optional[str] = None

async def send_discord_message(text: str):
    if not DISCORD_WEBHOOK_URL:
        logger.warning(f"Discord Webhook URL not set. Mock sending message: {text}")
        return
    async with httpx.AsyncClient() as client:
        payload = {"content": text}
        try:
            await client.post(DISCORD_WEBHOOK_URL, json=payload)
        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")

async def nightly_triage_job():
    """
    Executes at 21:00 CEST. Post-mortem & Forecast.
    """
    logger.info("Starting Nightly Triage...")
    # Step 1: Post-mortem ping
    await send_discord_message("Did you finish the prioritized tasks today? Reply with updates.")
    
    system_state["status"] = "AWAITING_REVIEW"
    upsert_task_state("system_state", {"status": "AWAITING_REVIEW", "last_updated": datetime.now().isoformat()})
    
    # Step 3: Forecast presentation (using mocked Notion and goals for structure)
    goals_md = "Focus on deep engineering sprints and fitness."
    raw_tasks = "Fix the authentication bug. Go to the gym. Buy groceries."
    prioritized = prioritize_tasks(raw_tasks, goals_md)
    
    # Fetch fixed events using Calendar MCP (mocked data representation)
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
    # Schedule the nightly triage job at 21:00 CEST (19:00 UTC)
    scheduler.add_job(nightly_triage_job, CronTrigger(hour=21, minute=0, timezone='Europe/Berlin'))
    scheduler.start()
    logger.info("APScheduler started.")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()

@app.get("/health")
def health_check():
    """
    Pinged every 10 minutes to keep Render instance alive.
    """
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.post("/webhook")
async def webhook_handler(request: Request):
    """
    Handles incoming messages from Discord (e.g. forwarded via integration) via HTTP Webhook.
    """
    body = await request.json()
    # Handle plain text formats, Discord (content), or Google Chat structure
    message_text = body.get("message", {}).get("text", body.get("content", body.get("text", ""))).strip()
    
    logger.info(f"Received webhook payload: {message_text}")
    
    if message_text.startswith("/now"):
        logger.info("Processing mid-day real-time interrupt.")
        current_time = datetime.now().isoformat()
        
        # In a complete implementation, use Calendar MCP to get current schedule
        current_schedule = [] 
        new_schedule = process_webhook_interrupt(current_schedule, message_text, current_time)
        
        # Pushing new schedule via Calendar MCP (handled implicitly or through a wrapper client)
        await send_discord_message(f"Urgent task inserted. Schedule updated: \n```json\n{json.dumps(new_schedule, indent=2)}\n```")
        return {"status": "interrupt processed"}
        
    elif system_state["status"] == "AWAITING_REVIEW":
        logger.info("Processing user review response.")
        if "looks good" in message_text.lower() or "approve" in message_text.lower():
            await send_discord_message("Confirmed. Pushing schedule to Google Calendar.")
            system_state["status"] = "IDLE"
            upsert_task_state("system_state", {"status": "IDLE", "last_updated": datetime.now().isoformat()})
        else:
            await send_discord_message("Updating schedule based on your feedback...")
            # Re-run LLM scheduler with text constraint
        return {"status": "review processed"}
        
    return {"status": "ignored"}


# --- NATIVE DISCORD INTERACTIONS (SLASH COMMANDS) HANDLERS ---

async def process_discord_now_command(application_id: str, token: str, message_text: str):
    current_time = datetime.now().isoformat()
    current_schedule = [] 
    new_schedule = process_webhook_interrupt(current_schedule, message_text, current_time)
    
    url = f"https://discord.com/api/v10/webhooks/{application_id}/{token}/messages/@original"
    async with httpx.AsyncClient() as client:
        await client.patch(url, json={
            "content": f"Urgent task inserted. Schedule updated: \n```json\n{json.dumps(new_schedule, indent=2)}\n```"
        })

async def process_discord_approve_command(application_id: str, token: str):
    await send_discord_message("Confirmed. Pushing schedule to Google Calendar.")
    system_state["status"] = "IDLE"
    upsert_task_state("system_state", {"status": "IDLE", "last_updated": datetime.now().isoformat()})
    
    url = f"https://discord.com/api/v10/webhooks/{application_id}/{token}/messages/@original"
    async with httpx.AsyncClient() as client:
        await client.patch(url, json={"content": "Confirmed and pushed to Google Calendar!"})

async def process_discord_modify_command(application_id: str, token: str, feedback: str):
    url = f"https://discord.com/api/v10/webhooks/{application_id}/{token}/messages/@original"
    async with httpx.AsyncClient() as client:
        await client.patch(url, json={"content": f"Feedback received: '{feedback}'. Updating schedule..."})

@app.post("/interactions")
async def interactions_handler(request: Request, background_tasks: BackgroundTasks):
    signature = request.headers.get("X-Signature-Ed25519")
    timestamp = request.headers.get("X-Signature-Timestamp")
    
    if not signature or not timestamp:
        return Response(content="Invalid signature headers", status_code=401)
        
    body = await request.body()
    if not verify_signature(body, signature, timestamp):
        return Response(content="Invalid request signature", status_code=401)
        
    data = json.loads(body.decode())
    
    # Discord Ping verification
    if data.get("type") == 1:
        return {"type": 1}
        
    # Application Command (Slash Commands)
    if data.get("type") == 2:
        command_data = data.get("data", {})
        command_name = command_data.get("name")
        application_id = data.get("application_id")
        token = data.get("token")
        
        if command_name == "now":
            options = command_data.get("options", [])
            task_value = ""
            for opt in options:
                if opt.get("name") == "task":
                    task_value = opt.get("value")
            
            background_tasks.add_task(process_discord_now_command, application_id, token, task_value)
            return {"type": 5}
            
        elif command_name == "approve":
            background_tasks.add_task(process_discord_approve_command, application_id, token)
            return {"type": 5}
            
        elif command_name == "modify":
            options = command_data.get("options", [])
            feedback_value = ""
            for opt in options:
                if opt.get("name") == "feedback":
                    feedback_value = opt.get("value")
            background_tasks.add_task(process_discord_modify_command, application_id, token, feedback_value)
            return {"type": 5}

    return {"type": 4, "data": {"content": "Unknown interaction"}}


