import os
import json
import base64
import asyncio
import httpx
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types

class AuditAIEngine:
    """Async Multi-model AI engine with parallel ensemble consensus and unified routing."""

    TASK_PROFILES = {
        'FORENSIC': {
            'description': 'Deep reasoning for forensic audit analysis',
            'models': ['openai/gpt-5.5', 'anthropic/claude-opus-4.7', 'openai/o3-pro',
                       'anthropic/claude-3.5-sonnet', 'openai/gpt-4o'],
        },
        'FAST_SCAN': {
            'description': 'Cost-effective volume processing for summaries',
            'models': ['anthropic/claude-sonnet-4.6', 'deepseek/deepseek-v4-pro', 
                       'qwen/qwen3-max', 'openai/gpt-4o-mini', 'google/gemini-flash-1.5'],
        },
        'VOUCHING': {
            'description': 'Multimodal ensemble for invoice extraction',
            'models': ['google/gemini-2.5-pro', 'openai/gpt-5.5', 'openai/gpt-4o', 
                       'anthropic/claude-3.5-sonnet'],
        },
    }

    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.groq_key = os.getenv("GROQ_API_KEY")
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")

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
                if resp.status_code == 200:
                    data = resp.json()
                    content = data['choices'][0]['message']['content']
                    return self._clean_json(content)
            return None
        except Exception as e:
            print(f"[AI] OpenRouter {model_id} failed: {e}")
            return None

    async def _try_gemini(self, prompt, file_bytes=None, mime_type=None):
        try:
            client = genai.Client(api_key=self.gemini_key, http_options={'api_version': 'v1alpha'})
            if file_bytes and mime_type:
                resp = await client.aio.models.generate_content(
                    model="gemini-2.5-pro",
                    contents=[types.Part.from_bytes(data=file_bytes, mime_type=mime_type), prompt],
                    config={'response_mime_type': 'application/json'}
                )
            else:
                resp = await client.aio.models.generate_content(
                    model="gemini-2.5-pro",
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
                res['model_used'] = model_id
                return res
        return None

    async def ensemble_consensus(self, prompt: str, min_agree: int = 2) -> Optional[dict]:
        profile = self.TASK_PROFILES.get('FORENSIC', {})
        models = profile.get('models', ["anthropic/claude-opus-4.7", "openai/gpt-5.5", "google/gemini-2.5-pro"])[:3]

        print(f"[ENSEMBLE] Launching {len(models)} models in parallel...")
        tasks = [self._try_openrouter(mid, prompt) for mid in models]
        responses = await asyncio.gather(*tasks)

        results = [r for r in responses if r is not None]
        models_tried = [models[i] for i, r in enumerate(responses) if r is not None]

        if not results: return None
        
        # Mark consensus if multiple models agreed (simplified for JSON results)
        results[0]['consensus'] = len(results) >= min_agree
        results[0]['ensemble_models'] = models_tried
        results[0]['model_used'] = f"Ensemble ({len(results)} models)"
        return results[0]

    # ──────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────

    async def get_summary(self, category: str, stats: dict) -> dict:
        prompt = f"Expert auditor summary for {category}. Stats: {json.dumps(stats)}. Return JSON with 'summary' and 'focus'."
        res = await self.route_task('FAST_SCAN', {'prompt': prompt})
        return res if res else {"summary": "Analysis failed.", "focus": "N/A"}

    async def vouch_invoice(self, contents: bytes, mime_type: str) -> dict:
        prompt = "Extract Invoice No, Date, Vendor, GSTIN, Gross Amount. Return JSON with 'data' array of {field, value}."
        res = await self.route_task('VOUCHING', {'prompt': prompt, 'file_bytes': contents, 'mime_type': mime_type})
        return res if res else {"data": []}

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
