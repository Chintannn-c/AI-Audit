import os
import sys
import asyncio
from dotenv import load_dotenv

# Define absolute paths
ROOT_DIR = r"c:\Users\sharm\.gemini\antigravity\scratch\audit_ai_app"
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

# Add both to path to be safe
if ROOT_DIR not in sys.path: sys.path.insert(0, ROOT_DIR)
if BACKEND_DIR not in sys.path: sys.path.insert(0, BACKEND_DIR)

load_dotenv(os.path.join(BACKEND_DIR, ".env"))

async def main():
    try:
        # Try direct import first
        try:
            from ai_engine import ai_engine
            print("[SUCCESS] ai_engine imported directly.")
        except ImportError:
            from backend.ai_engine import ai_engine
            print("[SUCCESS] ai_engine imported via backend package.")
        
        print(f"Keys: Gemini={bool(ai_engine.gemini_key)}, Groq={bool(ai_engine.groq_key)}, OR={bool(ai_engine.openrouter_key)}")
        
        print("[TEST] Running get_summary...")
        result = await ai_engine.get_summary("Test Audit", {"rows": 100, "value": 5000})
        print(f"[SUCCESS] AI Result: {result.get('model_used', 'Unknown Model')}")

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
