import os
import datetime
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

def get_calendar_service():
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    
    if not (refresh_token and client_id and client_secret):
        raise ValueError("Google OAuth credentials (GOOGLE_REFRESH_TOKEN, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET) missing from environment.")
        
    info = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    creds = Credentials.from_authorized_user_info(info, scopes=['https://www.googleapis.com/auth/calendar'])
    
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        
    return build('calendar', 'v3', credentials=creds)

def get_events(time_min: str = None, time_max: str = None):
    try:
        service = get_calendar_service()
        if not time_min:
            time_min = datetime.datetime.utcnow().isoformat() + 'Z'
        
        events_result = service.events().list(
            calendarId='primary', 
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        return events_result.get('items', [])
    except Exception as e:
        logger.error(f"Error fetching Google Calendar events: {e}")
        return []

def delete_event(event_id: str):
    try:
        service = get_calendar_service()
        service.events().delete(calendarId='primary', eventId=event_id).execute()
    except Exception as e:
        logger.error(f"Error deleting event {event_id}: {e}")

def create_event(title: str, start_time: str, end_time: str, description: str = ""):
    try:
        service = get_calendar_service()
        event = {
            'summary': title,
            'description': description,
            'start': {
                'dateTime': start_time,
            },
            'end': {
                'dateTime': end_time,
            },
        }
        event = service.events().insert(calendarId='primary', body=event).execute()
        return event
    except Exception as e:
        logger.error(f"Error creating event: {e}")
        return None

def update_calendar_schedule(new_schedule):
    """
    Clears all existing flexible events for today (after current time) and inserts the new schedule.
    """
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    events = get_events(time_min=now)
    
    # 1. Wipe out existing flexible blocks
    for event in events:
        desc = event.get('description', '')
        if '[Flexible]' in desc or '#flex' in desc:
            logger.info(f"Deleting flexible event: {event.get('summary')}")
            delete_event(event.get('id'))
            
    # 2. Inject the newly computed schedule
    for item in new_schedule:
        title = item.get('title', item.get('task_name', 'Scheduled Task'))
        start = item.get('start_time')
        end = item.get('end_time')
        # Mark as flexible so we can delete/shift it later if needed
        create_event(title, start, end, description="[Flexible] Scheduled by Orchestrator")
