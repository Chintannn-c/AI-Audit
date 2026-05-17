import asyncio
import httpx
import os
from dotenv import load_dotenv

# Load env from c:\Users\sharm\.gemini\antigravity\scratch\audit_ai_app\backend\.env
load_dotenv(r'c:\Users\sharm\.gemini\antigravity\scratch\audit_ai_app\backend\.env')

async def check_key(name, key):
    if not key:
        print(f"{name}: [NOT CONFIGURED]")
        return
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
    payload = {
        "contents": [{
            "parts": [{"text": "Hi"}]
        }]
    }
    
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                print(f"[VALID] {name} (ends in ...{key[-4:]}): VALID (Status 200)")
            else:
                print(f"[INVALID] {name} (ends in ...{key[-4:]}): INVALID (Status {resp.status_code})")
                try:
                    print(f"   Error Body: {resp.text}")
                except Exception:
                    pass
    except Exception as e:
        print(f"[ERROR] {name}: Connection failed: {type(e).__name__}: {str(e)}")

async def main():
    print("Testing Gemini Keys from .env...")
    await check_key("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
    await check_key("GEMINI_API_KEY_2", os.getenv("GEMINI_API_KEY_2"))
    await check_key("GEMINI_API_KEY_3", os.getenv("GEMINI_API_KEY_3"))

if __name__ == "__main__":
    asyncio.run(main())
