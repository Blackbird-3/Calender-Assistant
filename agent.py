import os
import json
from google import genai
from typing import List, Dict, Any

def get_llm_client():
    # Uses GOOGLE_API_KEY environment variable implicitly
    return genai.Client()

async def prioritize_tasks(raw_tasks: str, goals: str) -> List[Dict[str, Any]]:
    """
    Takes unprioritized raw tasks from Notion and goals from Markdown.
    Uses LLM to assign semantic priorities (1-5) and estimate duration.
    """
    client = get_llm_client()
    prompt = f"""
    You are an expert AI productivity assistant.
    Given the following goals document:
    {goals}

    And the following raw tasks:
    {raw_tasks}

    Prioritize the tasks on a scale of 1 to 5 (5 is Critical, 1 is Low/Errands).
    Output the result as a strict JSON array of objects, with keys: "task_name", "priority", "estimated_hours".
    Return ONLY the JSON array without markdown formatting.
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
        return json.loads(text.strip())
    except Exception as e:
        print(f"Error parsing LLM response: {e}")
        return []

async def schedule_tasks(prioritized_tasks: List[Dict[str, Any]], fixed_events: List[Dict[str, Any]], current_time_str: str, user_updates: str = "") -> List[Dict[str, Any]]:
    """
    Computes an optimized schedule for the remaining blocks based on prioritized tasks.
    """
    client = get_llm_client()
    prompt = f"""
    You are an expert scheduling agent.
    Current Date/Time Context: {current_time_str}
    
    Fixed Events (Do not modify):
    {json.dumps(fixed_events, indent=2)}
    
    Prioritized Tasks Queue (from Notion):
    {json.dumps(prioritized_tasks, indent=2)}
    
    User Updates / Direct Requests:
    "{user_updates}"
    
    Create a detailed daily schedule for tomorrow. 
    Fit the highest priority tasks into the available open blocks around the fixed events.
    Return ONLY a JSON array of scheduled events with keys: "title", "start_time" (ISO format), "end_time" (ISO format), "type".
    IMPORTANT RULES: 
    1. For newly scheduled tasks, you MUST set "type" to "flexible". ONLY pre-existing fixed events should retain "type": "fixed".
    2. Do NOT break down a single task into multiple separate blocks. Schedule each task as a single contiguous time block.
    3. You MUST prioritize and explicitly include any tasks directly requested in the "User Updates", even if they aren't in the Notion queue. If the user specifies a time constraint, respect it exactly.
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
        
        parsed = json.loads(text.strip())
        if not isinstance(parsed, list):
            print("Error: LLM did not return a JSON array.")
            return []
        return parsed
    except Exception as e:
        print(f"Error parsing LLM response: {e}")
        return []

async def modify_schedule(schedule: List[Dict[str, Any]], user_feedback: str, current_time_str: str) -> List[Dict[str, Any]]:
    """
    Takes an existing forecast schedule and applies user modifications (e.g. removing tasks, changing times).
    """
    client = get_llm_client()
    prompt = f"""
    You are a real-time calendar orchestrator.
    Current Date/Time: {current_time_str}
    
    Current Forecast Schedule:
    {json.dumps(schedule, indent=2)}
    
    User Feedback: "{user_feedback}"
    
    Modify the schedule exactly as requested by the user. Remove, add, or shift tasks as needed based on their feedback.
    Return ONLY the new modified JSON array of scheduled events with keys: "title", "start_time", "end_time", "type".
    IMPORTANT RULES:
    1. Do NOT alter any 'fixed' events unless the user explicitly requested to change them.
    2. Any newly added tasks should be "type": "flexible".
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
            
        parsed = json.loads(text.strip())
        if not isinstance(parsed, list):
            print("Error: LLM did not return a JSON array.")
            return schedule
        return parsed
    except Exception as e:
        print(f"Error parsing LLM response: {e}")
        return schedule

async def process_webhook_interrupt(schedule: List[Dict[str, Any]], interrupt_message: str, current_time_str: str) -> List[Dict[str, Any]]:
    """
    Handles a /now command to inject an urgent task and shift flexible tasks.
    """
    client = get_llm_client()
    prompt = f"""
    You are a real-time calendar orchestrator.
    Current Date/Time: {current_time_str}
    
    Current Schedule:
    {json.dumps(schedule, indent=2)}
    
    Urgent Interrupt Received: "{interrupt_message}"
    
    Inject the urgent interrupt into the schedule immediately.
    Push back, truncate, or drop flexible low-priority tasks as needed. Do NOT alter any 'fixed' events happening in the future. Past events are locked.
    Return ONLY the new modified JSON array of scheduled events with keys: "title", "start_time", "end_time", "type".
    IMPORTANT RULES:
    1. For the newly injected urgent task, you MUST set its "type" to "urgent".
    2. All other shifted tasks MUST remain "type": "flexible".
    3. DO NOT set "type": "fixed" for anything except the pre-existing fixed events.
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
            
        parsed = json.loads(text.strip())
        if not isinstance(parsed, list):
            print("Error: LLM did not return a JSON array.")
            return schedule
        return parsed
    except Exception as e:
        print(f"Error parsing LLM response: {e}")
        return schedule
