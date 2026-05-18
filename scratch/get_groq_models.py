import requests
import os
from dotenv import load_dotenv

load_dotenv(r'c:\Users\sharm\.gemini\antigravity\scratch\audit_ai_app\backend\.env')
key = os.getenv("GROQ_API_KEY")

if not key:
    print("GROQ_API_KEY not configured in env.")
    exit(1)

url = "https://api.groq.com/openai/v1/models"
headers = {"Authorization": f"Bearer {key}"}

try:
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json().get("data", [])
        print(f"=== GROQ SUPPORTED MODELS LIST ({len(data)} total models) ===")
        for idx, model in enumerate(sorted(data, key=lambda x: x['id'])):
            model_id = model.get('id')
            owned_by = model.get('owned_by', 'Unknown')
            print(f"{idx+1}. {model_id} (Owned by: {owned_by})")
    else:
        print(f"Failed to fetch models. Status {resp.status_code}: {resp.text}")
except Exception as e:
    print(f"Error making request: {e}")
