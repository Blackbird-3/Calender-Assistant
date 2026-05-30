import os
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID")

if not BOT_TOKEN or not CLIENT_ID:
    print("Error: Please set DISCORD_BOT_TOKEN and DISCORD_CLIENT_ID in your environment or .env file.")
    exit(1)

url = f"https://discord.com/api/v10/applications/{CLIENT_ID}/commands"

headers = {
    "Authorization": f"Bot {BOT_TOKEN}",
    "Content-Type": "application/json"
}

commands = [
    {
        "name": "now",
        "description": "Trigger an urgent schedule interrupt",
        "options": [
            {
                "name": "task",
                "description": "Describe the urgent task and duration",
                "type": 3, # String
                "required": True
            }
        ]
    },
    {
        "name": "approve",
        "description": "Approve the daily scheduled forecast"
    },
    {
        "name": "modify",
        "description": "Provide schedule adjustments feedback",
        "options": [
            {
                "name": "feedback",
                "description": "Describe your schedule adjustments",
                "type": 3, # String
                "required": True
            }
        ]
    }
]

for cmd in commands:
    response = requests.post(url, headers=headers, json=cmd)
    if response.status_code in [200, 201]:
        print(f"Successfully registered command: /{cmd['name']}")
    else:
        print(f"Failed to register command /{cmd['name']}: {response.text}")
