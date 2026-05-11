import os
import json
import base64
import time
import requests
from typing import List, Dict, Any, Optional
from google import genai
from groq import Groq
from openai import OpenAI


class AuditAIEngine:
    """Multi-model AI engine with task routing, exponential backoff, and ensemble consensus."""

    # ── Task Routing Profiles ──
    TASK_PROFILES = {
        'FORENSIC': {
            'description': 'Deep reasoning for forensic audit analysis',
            'models': ['anthropic/claude-3.5-sonnet', 'openai/gpt-4o', 'openai/gpt-4-turbo',
                       'anthropic/claude-3-opus', 'google/gemini-pro-1.5'],
        },
        'FAST_SCAN': {
            'description': 'Cost-effective volume processing for summaries',
            'models': ['openai/gpt-4o-mini', 'google/gemini-flash-1.5',
                       'anthropic/claude-3-haiku', 'deepseek/deepseek-chat',
                       'mistralai/mixtral-8x22b-instruct'],
        },
        'VOUCHING': {
            'description': 'Multimodal ensemble for invoice extraction',
            'models': ['openai/gpt-4o', 'anthropic/claude-3.5-sonnet',
                       'google/gemini-flash-1.5'],
        },
    }

    MAX_RETRIES = 3
    BACKOFF_BASE = 1.5  # seconds

    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.gemini_key_2 = os.getenv("GEMINI_API_KEY_2")
        self.groq_key = os.getenv("GROQ_API_KEY")
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")

        # Primary Gemini client
        self.gemini_client = None
        if self.gemini_key:
            try:
                self.gemini_client = genai.Client(api_key=self.gemini_key)
                print("[AI] Gemini Key 1 initialized.")
            except Exception as e:
                print(f"[AI] Gemini Key 1 init failed: {e}")

        # Secondary Gemini client (for rate-limit failover)
        self.gemini_client_2 = None
        if self.gemini_key_2:
            try:
                self.gemini_client_2 = genai.Client(api_key=self.gemini_key_2)
                print("[AI] Gemini Key 2 initialized.")
            except Exception as e:
                print(f"[AI] Gemini Key 2 init failed: {e}")

        self.groq_client = None
        if self.groq_key:
            try:
                self.groq_client = Groq(api_key=self.groq_key)
            except Exception as e:
                print(f"[AI] Groq init failed: {e}")

        self.or_client = None
        if self.openrouter_key:
            try:
                self.or_client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=self.openrouter_key,
                )
                # Comprehensive list of top-tier models from OpenRouter
                self.or_models = [
                    # S-Tier (General Intelligence)
                    "anthropic/claude-3.5-sonnet",
                    "openai/gpt-4o",
                    "openai/gpt-4-turbo",
                    "anthropic/claude-3-opus",
                    "google/gemini-pro-1.5",

                    # High Performance / Large Scale
                    "meta-llama/llama-3.1-405b-instruct",
                    "mistralai/mistral-large",
                    "databricks/dbrx-instruct",
                    "qwen/qwen-72b-chat",
                    "cohere/command-r-plus",

                    # Fast & Efficient
                    "openai/gpt-4o-mini",
                    "anthropic/claude-3-haiku",
                    "google/gemini-flash-1.5",
                    "deepseek/deepseek-chat",
                    "mistralai/mixtral-8x22b-instruct",

                    # Specialized / Search
                    "perplexity/sonar-medium-chat",
                    "perplexity/sonar-small-online",
                    "gryphe/mythomax-l2-13b"
                ]
            except Exception as e:
                print(f"[AI] OpenRouter init failed: {e}")

    # ──────────────────────────────────────────────
    # TASK ROUTER (Brain Routing Layer)
    # ──────────────────────────────────────────────

    def route_task(self, task_type: str, payload: dict) -> Optional[dict]:
        """
        Intelligent task router that selects the optimal AI model pipeline
        based on the task type.

        Returns:
            Parsed JSON response from the best available model, plus 'model_used' metadata.
        """
        task_type = task_type.upper()
        profile = self.TASK_PROFILES.get(task_type, self.TASK_PROFILES['FAST_SCAN'])
        prompt = payload.get('prompt', '')
        file_bytes = payload.get('file_bytes')
        mime_type = payload.get('mime_type')
        is_multimodal = file_bytes is not None

        print(f"[ROUTER] Task={task_type} | Multimodal={is_multimodal} | "
              f"Models={len(profile['models'])}")

        # 1. Try Gemini first (always — it's the primary)
        if self.gemini_client:
            result = self._try_gemini(prompt, file_bytes, mime_type)
            if result is not None:
                result['model_used'] = "Gemini 2.0 Flash"
                return result

        # 2. Try Groq for text-only tasks
        if not is_multimodal and self.groq_client:
            result = self._try_groq(prompt)
            if result is not None:
                result['model_used'] = "Groq (Llama 3 70B)"
                return result

        # 3. Try OpenRouter with task-specific model ordering
        if self.or_client:
            models = profile['models'] if self.or_client else []
            for model_id in models:
                result = self._try_openrouter(
                    model_id, prompt, file_bytes, mime_type, is_multimodal
                )
                if result is not None:
                    result['model_used'] = f"OpenRouter: {model_id}"
                    return result

        print(f"[ROUTER] All models exhausted for task={task_type}")
        return None

    # ──────────────────────────────────────────────
    # ENSEMBLE CONSENSUS (For High-Risk Items)
    # ──────────────────────────────────────────────

    def ensemble_consensus(self, prompt: str, min_agree: int = 2) -> Optional[dict]:
        """
        Query multiple models and only flag if at least `min_agree` agree.
        Reduces false positives for forensic risk flagging.
        """
        results = []
        models_tried = []

        # Collect from up to 3 models
        if self.gemini_client:
            r = self._try_gemini(prompt)
            if r:
                r['model_used'] = "Gemini 2.0 Flash"
                results.append(r)
                models_tried.append("Gemini")

        if self.groq_client and len(results) < 3:
            r = self._try_groq(prompt)
            if r:
                r['model_used'] = "Groq (Llama 3 70B)"
                results.append(r)
                models_tried.append("Groq")

        if self.or_client and len(results) < 3:
            # Use the S-Tier model as the professional forensic tie-breaker
            model_id = "anthropic/claude-3.5-sonnet"
            r = self._try_openrouter(model_id, prompt)
            if r:
                r['model_used'] = f"OpenRouter: {model_id}"
                results.append(r)
                models_tried.append(model_id)

        if len(results) < min_agree:
            if results:
                results[0]['ensemble_models'] = models_tried
                return results[0]
            return None

        # Check consensus: compare 'risk_level' or 'flag' keys
        risk_levels = [r.get('risk_level', r.get('flag', 'unknown')) for r in results]
        from collections import Counter
        most_common, count = Counter(risk_levels).most_common(1)[0]
        if count >= min_agree:
            # Return the first result that matches the consensus
            for r in results:
                if r.get('risk_level', r.get('flag', '')) == most_common:
                    r['consensus'] = True
                    r['agreement_count'] = count
                    r['ensemble_models'] = models_tried
                    return r

        if results:
            results[0]['ensemble_models'] = models_tried
            return results[0]
        return None

    # ──────────────────────────────────────────────
    # MODEL IMPLEMENTATIONS (with exponential backoff)
    # ──────────────────────────────────────────────

    def _try_gemini(self, prompt: str, file_bytes=None, mime_type=None) -> Optional[dict]:
        """
        Try Gemini with dual-key rotation and exponential backoff.
        - Even attempts (0, 2, ...) use Key 1 (gemini_client).
        - Odd attempts  (1, 3, ...) use Key 2 (gemini_client_2).
        - On a rate-limit error the loop continues immediately to the next attempt,
          which automatically switches keys — doubling effective quota.
        """
        clients = []
        if self.gemini_client:
            clients.append(("Key 1", self.gemini_client))
        if self.gemini_client_2:
            clients.append(("Key 2", self.gemini_client_2))

        if not clients:
            print("[AI] No Gemini clients available.")
            return None

        for attempt in range(self.MAX_RETRIES):
            # Pick key by round-robin
            key_label, client = clients[attempt % len(clients)]
            try:
                print(f"[AI] Trying Gemini {key_label} (attempt {attempt + 1}/{self.MAX_RETRIES})...")
                if file_bytes and mime_type:
                    from google.genai import types
                    resp = client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=[
                            types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                            prompt
                        ],
                        config={'response_mime_type': 'application/json'}
                    )
                else:
                    resp = client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=prompt,
                        config={'response_mime_type': 'application/json'}
                    )
                if resp and resp.text:
                    result = self._clean_json(resp.text)
                    if result is not None:
                        print(f"[AI] Gemini {key_label} succeeded.")
                        return result
                    print(f"[AI] Gemini {key_label} returned unparseable JSON, retrying...")
            except Exception as e:
                err_str = str(e).lower()
                if '429' in err_str or 'quota' in err_str or 'rate' in err_str or '500' in err_str:
                    # Switch to the other key on next attempt — no sleep needed if 2 keys available
                    if len(clients) > 1:
                        next_label = clients[(attempt + 1) % len(clients)][0]
                        print(f"[AI] Gemini {key_label} rate-limited. Switching to {next_label}...")
                    else:
                        wait = self.BACKOFF_BASE * (2 ** attempt)
                        print(f"[AI] Gemini rate-limited (only 1 key). Backoff {wait:.1f}s...")
                        time.sleep(wait)
                    continue
                print(f"[AI] Gemini {key_label} failed (non-retryable): {e}")
                break

        print("[AI] All Gemini attempts exhausted.")
        return None

    def _try_groq(self, prompt: str) -> Optional[dict]:
        """Try Groq with retries and exponential backoff."""
        for attempt in range(self.MAX_RETRIES):
            try:
                print(f"[AI] Trying Groq (attempt {attempt + 1})...")
                resp = self.groq_client.chat.completions.create(
                    model="llama3-70b-8192",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                return json.loads(resp.choices[0].message.content)
            except Exception as e:
                err_str = str(e).lower()
                if '429' in err_str or 'rate' in err_str or '500' in err_str:
                    wait = self.BACKOFF_BASE * (2 ** attempt)
                    print(f"[AI] Groq rate-limited. Backoff {wait:.1f}s...")
                    time.sleep(wait)
                    continue
                print(f"[AI] Groq failed: {e}")
                break
        return None

    def _try_openrouter(self, model_id: str, prompt: str,
                        file_bytes=None, mime_type=None,
                        is_multimodal=False) -> Optional[dict]:
        """Try an OpenRouter model with retries and exponential backoff."""
        for attempt in range(self.MAX_RETRIES):
            try:
                print(f"[AI] Trying OpenRouter ({model_id}, attempt {attempt + 1})...")
                if is_multimodal and file_bytes:
                    base64_img = base64.b64encode(file_bytes).decode('utf-8')
                    messages = [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url",
                             "image_url": {"url": f"data:{mime_type};base64,{base64_img}"}}
                        ]
                    }]
                else:
                    messages = [{"role": "user", "content": prompt}]

                resp = self.or_client.chat.completions.create(
                    model=model_id,
                    messages=messages,
                    response_format={"type": "json_object"}
                )
                content = resp.choices[0].message.content
                return json.loads(content)
            except Exception as e:
                err_str = str(e).lower()
                if '429' in err_str or 'rate' in err_str or '500' in err_str:
                    wait = self.BACKOFF_BASE * (2 ** attempt)
                    print(f"[AI] OpenRouter {model_id} rate-limited. Backoff {wait:.1f}s...")
                    time.sleep(wait)
                    continue
                print(f"[AI] OpenRouter model {model_id} failed: {e}")
                break
        return None

    # ──────────────────────────────────────────────
    # PUBLIC API (Backward-Compatible)
    # ──────────────────────────────────────────────

    def get_summary(self, category: str, stats: dict) -> dict:
        """Get executive audit insights with multi-model failover."""
        prompt = (
            f"You are an expert statutory auditor. Audit area: {category}. "
            f"Ledger statistics: {json.dumps(stats)}. "
            "Provide a concise executive audit summary focused on high-risk patterns. "
            "Return JSON only with keys: 'summary' and 'focus'."
        )
        result = self.route_task('FAST_SCAN', {'prompt': prompt})
        if result:
            return result
        return {
            "summary": f"{category} audit analysis complete. Please review the high-risk transactions manually.",
            "focus": f"{category} — Manual Review Required"
        }

    def vouch_invoice(self, contents: bytes, mime_type: str) -> Optional[Dict[str, Any]]:
        """Multimodal vouching with failover."""
        prompt = (
            "You are an expert auditor performing invoice vouching. "
            "Extract the following fields from this invoice image/document:\n"
            "- Invoice Number\n- Invoice Date\n- Vendor Name\n- GSTIN\n"
            "- Gross Amount\n- Tax Amount\n- Net Amount\n"
            "Return ONLY a JSON array of objects with 'field' and 'value' keys. "
            "Add a final entry with field='Match Status' and value='EXTRACTED - AI Validated'."
        )
        result = self.route_task('VOUCHING', {
            'prompt': prompt,
            'file_bytes': contents,
            'mime_type': mime_type
        })
        if result:
            model_used = result.pop('model_used', 'Unknown')
            if isinstance(result, dict) and 'data' in result:
                return {"data": result['data'], "model_used": model_used}
            if isinstance(result, list):
                return {"data": result, "model_used": model_used}
            if isinstance(result, dict):
                # If it's a flat dict of field:value, convert to list
                data = [{"field": k, "value": v} for k, v in result.items()]
                return {"data": data, "model_used": model_used}
        return None

    def deep_audit_remark(self, transaction: dict, category: str) -> dict:
        """Generate forensic-grade AI remarks for a single transaction."""
        prompt = (
            f"You are a forensic auditor. Analyze this {category} transaction and "
            f"provide professional audit remarks:\n{json.dumps(transaction)}\n\n"
            "Return JSON with keys: 'risk_level' (High/Medium/Low), "
            "'remark' (professional audit observation), "
            "'recommended_action' (next steps for the auditor)."
        )
        # Use ensemble consensus for high-value forensic analysis
        result = self.ensemble_consensus(prompt, min_agree=2)
        if result:
            return result
        return {
            "risk_level": "Review",
            "remark": "AI analysis unavailable — manual review required.",
            "recommended_action": "Perform manual substantive testing."
        }

    def _clean_json(self, text: str):
        try:
            clean = text.strip()
            if clean.startswith("```"):
                clean = clean.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
            return json.loads(clean)
        except:
            return None


# Global instance
ai_engine = AuditAIEngine()
