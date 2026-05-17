import asyncio
import httpx
import os
from dotenv import load_dotenv

# Load env from c:\Users\sharm\.gemini\antigravity\scratch\audit_ai_app\backend\.env
load_dotenv(r'c:\Users\sharm\.gemini\antigravity\scratch\audit_ai_app\backend\.env')

async def check_gemma_key(name, key):
    if not key:
        print(f"{name}: [NOT CONFIGURED]")
        return
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent?key={key}"
    payload = {
        "contents": [{
            "parts": [{"text": "Hi"}]
        }]
    }
    
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                print(f"[SUCCESS] {name}: Model gemma-4-31b-it works perfectly! (Status 200)")
            else:
                print(f"[FAILED] {name}: Status {resp.status_code}")
                try:
                    print(f"   Error Body: {resp.text}")
                except Exception:
                    pass
    except Exception as e:
        print(f"[ERROR] {name}: Connection failed: {type(e).__name__}: {str(e)}")

async def main():
    print("Testing Gemma 4 Model ID on Google AI Studio Key 3...")
    await check_gemma_key("GEMINI_API_KEY_3", os.getenv("GEMINI_API_KEY_3"))

if __name__ == "__main__":
    asyncio.run(main())
