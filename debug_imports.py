import sys
import os

# Add backend to path
backend_path = r"c:\Flutter\ai_coding\backend"
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

try:
    from app.services import orchestrator_service
    from app.services import ai_service
    from app.services import openrouter_service
    
    print(f"Orchestrator file: {orchestrator_service.__file__}")
    print(f"AI Service file: {ai_service.__file__}")
    print(f"OpenRouter Service file: {openrouter_service.__file__}")
    
    orch = orchestrator_service.orchestrator
    print("\nOrchestrator model mapping:")
    for name, mod in orch.models.items():
        print(f"  {name}: {mod.__name__} (from {getattr(mod, '__file__', 'unknown')})")
        # Check if generate exists and its arguments
        import inspect
        if hasattr(mod, 'generate'):
            sig = inspect.signature(mod.generate)
            print(f"    generate signature: {sig}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
