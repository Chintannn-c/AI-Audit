import asyncio
import httpx
import os
from dotenv import load_dotenv

load_dotenv(r'c:\Users\sharm\.gemini\antigravity\scratch\audit_ai_app\backend\.env')

async def test_gemini(name, key):
    if not key:
        print(f"{name}: [NOT CONFIGURED]")
        return
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
    payload = {"contents": [{"parts": [{"text": "Hi"}]}]}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=payload)
            print(f"{name}: Status {resp.status_code} | Response: {resp.text[:120]}")
    except Exception as e:
        print(f"{name}: Exception: {type(e).__name__}: {e}")

async def test_groq(key):
    if not key:
        print("GROQ_API_KEY: [NOT CONFIGURED]")
        return
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            print(f"GROQ_API_KEY: Status {resp.status_code} | Response: {resp.text[:120]}")
    except Exception as e:
        print(f"GROQ_API_KEY: Exception: {type(e).__name__}: {e}")

async def test_mistral(key):
    if not key:
        print("MISTRAL_API_KEY: [NOT CONFIGURED]")
        return
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {"model": "mistral-large-latest", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            print(f"MISTRAL_API_KEY: Status {resp.status_code} | Response: {resp.text[:120]}")
    except Exception as e:
        print(f"MISTRAL_API_KEY: Exception: {type(e).__name__}: {e}")

async def test_openrouter(key):
    if not key:
        print("OPENROUTER_API_KEY: [NOT CONFIGURED]")
        return
    url = "https://openrouter.ai/api/v1/auth/key"
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers=headers)
            print(f"OPENROUTER_API_KEY: Status {resp.status_code} | Response: {resp.text[:120]}")
    except Exception as e:
        print(f"OPENROUTER_API_KEY: Exception: {type(e).__name__}: {e}")

async def main():
    print("=== STARTING FULL API KEY AUDIT ===")
    await test_gemini("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
    await test_gemini("GEMINI_API_KEY_2", os.getenv("GEMINI_API_KEY_2"))
    await test_gemini("GEMINI_API_KEY_3", os.getenv("GEMINI_API_KEY_3"))
    await test_groq(os.getenv("GROQ_API_KEY"))
    await test_mistral(os.getenv("MISTRAL_API_KEY"))
    await test_openrouter(os.getenv("OPENROUTER_API_KEY"))

if __name__ == "__main__":
    asyncio.run(main())
