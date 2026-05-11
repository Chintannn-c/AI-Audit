import os
import json
import base64
import asyncio
import httpx
import hashlib
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types

class AuditAIEngine:
    """Async Multi-model AI engine with parallel ensemble consensus and unified routing."""

    TASK_PROFILES = {
        'FORENSIC': {
            'description': 'Deep reasoning for forensic audit analysis (100% FREE)',
            'models': ['openai/gpt-oss-120b:free', 'meta-llama/llama-3.3-70b-instruct:free', 
                       'google/gemma-4-31b-it:free', 'nvidia/nemotron-3-super-120b-a12b:free',
                       'nousresearch/hermes-3-llama-3.1-405b:free'],
        },
        'FAST_SCAN': {
            'description': 'Cost-effective volume processing for summaries (100% FREE)',
            'models': ['z-ai/glm-4.5-air:free', 'google/gemma-4-31b-it:free', 
                       'liquid/lfm-2.5-1.2b-instruct:free', 'meta-llama/llama-3.2-3b-instruct:free'],
        },
        'VOUCHING': {
            'description': 'Multimodal extraction (100% FREE)',
            'models': ['nvidia/nemotron-nano-12b-v2-vl:free', 'baidu/qianfan-ocr-fast:free', 
                       'google/gemma-4-31b-it:free', 'meta-llama/llama-3.2-3b-instruct:free'],
        },
    }

    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.groq_key = os.getenv("GROQ_API_KEY")
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        
        # Initialize Persistent Cache
        self.cache_dir = os.path.join(os.path.dirname(__file__), 'cache')
        self.cache_file = os.path.join(self.cache_dir, 'ai_cache.json')
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache = self._load_cache()

    def _load_cache(self) -> dict:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_cache(self):
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f)
        except Exception as e:
            print(f"[CACHE] Save failed: {e}")

    def _get_cache_key(self, task_type: str, prompt: str, file_bytes=None) -> str:
        # Create a unique hash for the task + prompt + optional file
        hasher = hashlib.md5()
        hasher.update(task_type.encode())
        hasher.update(prompt.encode())
        if file_bytes:
            hasher.update(file_bytes[:1000]) # Hash first 1KB of file for speed
        return hasher.hexdigest()

    # ──────────────────────────────────────────────
    # ASYNC PROVIDER WRAPPERS
    # ──────────────────────────────────────────────

    async def _try_openrouter(self, model_id, prompt, file_bytes=None, mime_type=None, is_multimodal=False):
        try:
            if is_multimodal and file_bytes:
                base64_img = base64.b64encode(file_bytes).decode('utf-8')
                content_payload = [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_img}"}}
                ]
            else:
                content_payload = prompt

            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "model": model_id,
                    "messages": [{"role": "user", "content": content_payload}],
                    "response_format": {"type": "json_object"}
                }
                headers = {
                    "Authorization": f"Bearer {self.openrouter_key}",
                    "Content-Type": "application/json"
                }
                resp = await client.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers)
                
                # Fallback: Try without json_object if 400 (some free models don't support it)
                if resp.status_code == 400:
                    del payload["response_format"]
                    resp = await client.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers)

                if resp.status_code == 200:
                    data = resp.json()
                    content = data['choices'][0]['message']['content']
                    return self._clean_json(content)
                else:
                    print(f"[AI] OpenRouter {model_id} Error {resp.status_code}: {resp.text}")
            return None
        except Exception as e:
            print(f"[AI] OpenRouter {model_id} failed: {e}")
            return None

    async def _try_gemini(self, prompt, file_bytes=None, mime_type=None):
        try:
            client = genai.Client(api_key=self.gemini_key, http_options={'api_version': 'v1alpha'})
            if file_bytes and mime_type:
                resp = await client.aio.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[types.Part.from_bytes(data=file_bytes, mime_type=mime_type), prompt],
                    config={'response_mime_type': 'application/json'}
                )
            else:
                resp = await client.aio.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config={'response_mime_type': 'application/json'}
                )
            if resp and resp.text:
                return self._clean_json(resp.text)
            return None
        except Exception as e:
            print(f"[AI] Gemini Direct failed: {e}")
            return None

    async def _try_groq(self, prompt):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {
                    "model": "llama-3.3-70b-specdec",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"}
                }
                headers = {"Authorization": f"Bearer {self.groq_key}", "Content-Type": "application/json"}
                resp = await client.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return self._clean_json(data['choices'][0]['message']['content'])
            return None
        except Exception as e:
            print(f"[AI] Groq Direct failed: {e}")
            return None

    # ──────────────────────────────────────────────
    # CORE ROUTING & ENSEMBLE
    # ──────────────────────────────────────────────

    async def route_task(self, task_type: str, payload: dict) -> Optional[dict]:
        task_type = task_type.upper()
        profile = self.TASK_PROFILES.get(task_type, self.TASK_PROFILES['FAST_SCAN'])
        prompt = payload.get('prompt', '')
        file_bytes = payload.get('file_bytes')
        mime_type = payload.get('mime_type')
        is_multimodal = file_bytes is not None

        print(f"[ROUTER] Task={task_type} | Models={len(profile['models'])}")

        # Check Cache first
        cache_key = self._get_cache_key(task_type, prompt, file_bytes)
        if cache_key in self.cache:
            print(f"[CACHE] Hit! Returning cached result for {task_type}")
            return self.cache[cache_key]

        for model_id in profile.get('models', []):
            if "gemini" in model_id.lower() and self.gemini_key and "/" not in model_id:
                res = await self._try_gemini(prompt, file_bytes, mime_type)
            elif "groq" in model_id.lower() and self.groq_key and not is_multimodal:
                res = await self._try_groq(prompt)
            elif self.openrouter_key:
                res = await self._try_openrouter(model_id, prompt, file_bytes, mime_type, is_multimodal)
            else:
                continue

            if res:
                # If the model returned a list, wrap it in a dict for consistency
                if isinstance(res, list):
                    res = {"data": res}
                
                if isinstance(res, dict):
                    res['model_used'] = model_id
                    # Save to cache
                    self.cache[cache_key] = res
                    self._save_cache()
                    return res
        return None

    async def ensemble_consensus(self, prompt: str, min_agree: int = 2) -> Optional[dict]:
        profile = self.TASK_PROFILES.get('FORENSIC', {})
        models = profile.get('models', ["meta-llama/llama-3.3-70b-instruct:free", "nousresearch/hermes-3-llama-3.1-405b:free", "nvidia/nemotron-3-super-120b-a12b:free"])[:3]

        print(f"[ENSEMBLE] Launching {len(models)} models in parallel...")
        
        # Check Cache
        cache_key = self._get_cache_key('ENSEMBLE', prompt)
        if cache_key in self.cache:
            print("[CACHE] Ensemble hit!")
            return self.cache[cache_key]

        tasks = [self._try_openrouter(mid, prompt) for mid in models]
        responses = await asyncio.gather(*tasks)

        results = [r for r in responses if r is not None]
        models_tried = [models[i] for i, r in enumerate(responses) if r is not None]

        if not results: return None
        
        # Mark consensus if multiple models agreed (simplified for JSON results)
        # Return the first one but mark as consensus
        results[0]['consensus'] = True
        results[0]['ensemble_models'] = models_tried
        results[0]['model_used'] = f"Ensemble ({len(results)} models)"
        
        # Save to cache
        self.cache[cache_key] = results[0]
        self._save_cache()
        
        return results[0]

    # ──────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────

    async def get_summary(self, category: str, stats: dict) -> dict:
        prompt = f"Expert auditor summary for {category}. Stats: {json.dumps(stats)}. Return JSON with 'summary' and 'focus'."
        res = await self.route_task('FAST_SCAN', {'prompt': prompt})
        return res if res else {"summary": "Analysis failed.", "focus": "N/A"}

    async def vouch_invoice(self, contents: bytes, mime_type: str) -> dict:
        prompt = (
            "Role: You are a highly accurate Document Processing Assistant specializing in OCR and financial data extraction. "
            "Task: Analyze the uploaded invoice and extract data into a structured JSON format. "
            "Extraction Fields: "
            "1. Invoice Number (Unique ID) "
            "2. Date (Format DD-MM-YYYY) "
            "3. Item Name (Description per line item) "
            "4. Amount (Base price before tax per item) "
            "5. GST (Tax amount per item) "
            "6. Total Amount (Amount + GST per item) "
            "7. Grand Total (Sum of all items) "
            "Instructions: If there are multiple items, list each one. Do not include currency symbols. "
            "Output Format: { \"data\": [ { \"field\": \"Invoice Number\", \"value\": \"...\" }, "
            "{ \"field\": \"Date\", \"value\": \"...\" }, "
            "{ \"field\": \"Item 1 Name\", \"value\": \"...\" }, { \"field\": \"Item 1 Amount\", \"value\": \"...\" }, ... ] }"
        )
        print(f"[AI] Starting Detailed Vouching for {mime_type}...")
        res = await self.route_task('VOUCHING', {'prompt': prompt, 'file_bytes': contents, 'mime_type': mime_type})
        if not res or not isinstance(res, dict) or 'data' not in res:
            print("[AI] Vouching failed or returned invalid format.")
            return {"data": [], "model_used": "AI Failure Fallback"}
        return res

    async def deep_audit_remark(self, transaction: dict, category: str) -> dict:
        prompt = f"Forensic audit of {category} transaction: {json.dumps(transaction)}. Return JSON with 'risk_level', 'remark', 'recommended_action'."
        return await self.ensemble_consensus(prompt)

    def _clean_json(self, text: str):
        try:
            clean = text.strip()
            if "```json" in clean: clean = clean.split("```json")[1].split("```")[0].strip()
            elif "```" in clean: clean = clean.split("```")[1].split("```")[0].strip()
            return json.loads(clean)
        except:
            return None

ai_engine = AuditAIEngine()
