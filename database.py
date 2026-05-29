import os
from supabase import create_client, Client
from pydantic import BaseModel
from typing import Optional, Dict, Any

# Load environment variables (ideally using python-dotenv in main.py)
SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "https://ynzzhtngaproptkapkdn.supabase.co")
SUPABASE_KEY = os.environ.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_2ro2vuxbzMRMVGlSs1dGyQ_gj4gFIaj")

def get_supabase_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Supabase credentials not found in environment.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)

db = get_supabase_client()

def upsert_task_state(task_id: str, state_data: Dict[str, Any]):
    """
    Updates the state of a task in the Supabase Cloud Database.
    """
    response = db.table("tasks").upsert({"id": task_id, **state_data}).execute()
    return response

def get_incomplete_tasks():
    """
    Retrieves all tasks marked as incomplete.
    """
    response = db.table("tasks").select("*").eq("status", "incomplete").execute()
    return response.data

def log_system_metrics(metrics: Dict[str, Any]):
    """
    Records system metrics to the database.
    """
    response = db.table("system_metrics").insert(metrics).execute()
    return response
