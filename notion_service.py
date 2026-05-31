import os
import logging
from notion_client import Client

logger = logging.getLogger(__name__)

NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

def get_notion_client():
    if not NOTION_TOKEN:
        logger.warning("NOTION_TOKEN not set.")
        return None
    return Client(auth=NOTION_TOKEN)

def get_notion_tasks() -> str:
    """
    Fetches incomplete tasks from Notion database.
    Returns a comma-separated string of task titles, or a fallback message if not configured.
    """
    notion = get_notion_client()
    if not notion or not NOTION_DATABASE_ID:
        logger.warning("Notion is not fully configured (missing Token or Database ID).")
        return ""

    try:
        # Query the database for items that are not marked as Done.
        # This assumes standard checkbox or status property.
        # To make it robust without knowing the exact schema, we will just fetch all pages
        # and extract their titles. We'll leave filtering for later if they have a specific schema.
        # But generally, people use a 'Status' select or 'Done' checkbox.
        # Let's try to fetch all active tasks. If they don't have a filter, we fetch the top 20.
        
        response = notion.databases.query(
            **{
                "database_id": NOTION_DATABASE_ID,
                "page_size": 20,
                # We won't apply a strict filter yet because we don't know their schema
                # e.g., "Status" != "Done" or "Done" != True
            }
        )
        
        tasks = []
        for page in response.get("results", []):
            properties = page.get("properties", {})
            # Find the title property (it's the only one of type "title")
            for prop_name, prop_data in properties.items():
                if prop_data.get("type") == "title":
                    title_arr = prop_data.get("title", [])
                    if title_arr:
                        tasks.append(title_arr[0].get("plain_text", ""))
                    break
                    
        if not tasks:
            return "No tasks found in Notion."
            
        return " ".join(tasks)
        
    except Exception as e:
        logger.error(f"Error fetching tasks from Notion: {e}")
        return ""
