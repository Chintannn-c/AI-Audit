import os
import sys
from dotenv import load_dotenv

# Add the current directory to sys.path so we can import from backend
sys.path.append(os.path.join(os.getcwd(), 'backend'))

load_dotenv('backend/.env')

try:
    from ai_engine import ai_engine
    print("[SUCCESS] ai_engine.py imported correctly.")
    
    # Check if keys are loaded
    print(f"Gemini Key loaded: {bool(ai_engine.gemini_key)}")
    print(f"Groq Key loaded: {bool(ai_engine.groq_key)}")
    print(f"OpenRouter Key loaded: {bool(ai_engine.openrouter_key)}")
    
    if not ai_engine.or_client:
        print("[ERROR] OpenRouter client failed to initialize. Check your API key format.")
    else:
        print("[SUCCESS] OpenRouter client initialized.")
        
        # Test a very small model to verify the connection
        print("[TEST] Testing OpenRouter connection with gpt-4o-mini...")
        test_stats = {"total_rows": 100, "total_value": 5000}
        result = ai_engine.get_summary("Test Audit", test_stats)
        
        if result and 'summary' in result:
            print(f"[SUCCESS] AI is working! Summary: {result['summary']}")
        else:
            print("[ERROR] AI call returned no result. Check API key balance or rate limits.")

except Exception as e:
    print(f"[CRITICAL ERROR] Testing failed: {e}")
    import traceback
    traceback.print_exc()
