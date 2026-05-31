import os
import logging
from notion_client import Client

logger = logging.getLogger(__name__)

NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_PAGE_ID = os.environ.get("NOTION_PAGE_ID")

def get_notion_client():
    if not NOTION_TOKEN:
        logger.warning("NOTION_TOKEN not set.")
        return None
    return Client(auth=NOTION_TOKEN)

def get_notion_tasks() -> str:
    """
    Fetches incomplete tasks from a standard Notion Page.
    Returns a consolidated string of task block contents.
    """
    notion = get_notion_client()
    if not notion or not NOTION_PAGE_ID:
        logger.warning("Notion is not fully configured (missing Token or Page ID).")
        return ""

    try:
        response = notion.blocks.children.list(block_id=NOTION_PAGE_ID)
        
        tasks = []
        for block in response.get("results", []):
            block_type = block.get("type")
            if not block_type:
                continue
                
            block_content = block.get(block_type, {})
            
            # If it's a to-do item, we check if it's already completed.
            if block_type == "to_do" and block_content.get("checked") is True:
                continue
                
            # Extract rich text from supported blocks
            rich_text = block_content.get("rich_text", [])
            
            if rich_text:
                plain_text = "".join([rt.get("plain_text", "") for rt in rich_text])
                if plain_text.strip():
                    tasks.append(plain_text.strip())
                    
        if not tasks:
            return "No tasks found in Notion page."
            
        return "\n".join(tasks)
        
    except Exception as e:
        logger.error(f"Error fetching tasks from Notion: {e}")
        return ""
