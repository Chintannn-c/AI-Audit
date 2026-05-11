import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv(r"c:\Users\sharm\.gemini\antigravity\scratch\audit_ai_app\backend\.env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def list_models():
    if not OPENROUTER_API_KEY:
        print("Error: OPENROUTER_API_KEY not found in .env")
        return

    url = "https://openrouter.ai/api/v1/models"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://github.com/Chintannn-c/code-genie-ai-ide", # Optional
        "X-Title": "Code Genie AI IDE" # Optional
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        models = response.json().get("data", [])

        print(f"{'Model ID':<60} | {'Pricing (P/C)':<20} | {'Context':<10}")
        print("-" * 100)

        free_models = []
        paid_models = []

        for model in models:
            m_id = model.get("id")
            pricing = model.get("pricing", {})
            prompt = pricing.get("prompt", "0")
            completion = pricing.get("completion", "0")
            context = model.get("context_length", "N/A")
            
            # pricing is usually in USD per token (or 1M tokens depending on API version)
            # OpenRouter returns pricing in USD per token.
            is_free = float(prompt) == 0 and float(completion) == 0
            
            row = f"{m_id:<60} | {prompt}/{completion:<15} | {context:<10}"
            
            if is_free:
                free_models.append(row)
            else:
                paid_models.append(row)

        print("\n--- FREE MODELS ---")
        for m in sorted(free_models):
            print(m)

        print("\n--- PAID MODELS (First 20) ---")
        for m in sorted(paid_models)[:20]:
            print(m)
            
        print(f"\nTotal Models: {len(models)} ({len(free_models)} Free)")

    except Exception as e:
        print(f"Error fetching models: {e}")

if __name__ == "__main__":
    list_models()
