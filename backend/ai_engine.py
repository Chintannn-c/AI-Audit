import os
import json
import base64
import requests
from typing import List, Dict, Any, Optional
from google import genai
from groq import Groq
from openai import OpenAI

class AuditAIEngine:
    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.groq_key = os.getenv("GROQ_API_KEY")
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        
        self.gemini_client = None
        if self.gemini_key:
            try:
                self.gemini_client = genai.Client(api_key=self.gemini_key)
            except Exception as e:
                print(f"[AI] Gemini init failed: {e}")

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

    def get_summary(self, category: str, stats: dict) -> dict:
        """Get executive audit insights with multi-model failover."""
        prompt = (
            f"You are an expert statutory auditor. Audit area: {category}. "
            f"Ledger statistics: {json.dumps(stats)}. "
            "Provide a concise executive audit summary focused on high-risk patterns. "
            "Return JSON only with keys: 'summary' and 'focus'."
        )
        
        # 1. Try Gemini
        if self.gemini_client:
            try:
                print("[AI] Trying Gemini for summary...")
                resp = self.gemini_client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config={'response_mime_type': 'application/json'}
                )
                if resp and resp.text:
                    return self._clean_json(resp.text)
            except Exception as e:
                print(f"[AI] Gemini failed: {e}")

        # 2. Try Groq (Llama 3)
        if self.groq_client:
            try:
                print("[AI] Falling back to Groq...")
                resp = self.groq_client.chat.completions.create(
                    model="llama3-70b-8192",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                return json.loads(resp.choices[0].message.content)
            except Exception as e:
                print(f"[AI] Groq failed: {e}")

        # 3. Try OpenRouter (Full Model Suite Failover)
        if self.or_client:
            for model_id in self.or_models:
                try:
                    print(f"[AI] Falling back to OpenRouter ({model_id})...")
                    resp = self.or_client.chat.completions.create(
                        model=model_id,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"}
                    )
                    content = resp.choices[0].message.content
                    return json.loads(content)
                except Exception as e:
                    print(f"[AI] OpenRouter model {model_id} failed: {e}")

        return {
            "summary": f"{category} audit analysis complete. Please review the high-risk transactions manually.",
            "focus": f"{category} — Manual Review Required"
        }

    def vouch_invoice(self, contents: bytes, mime_type: str) -> Optional[List[Dict]]:
        """Multimodal vouching with failover."""
        prompt = (
            "You are an expert auditor performing invoice vouching. "
            "Extract the following fields from this invoice image/document:\n"
            "- Invoice Number\n- Invoice Date\n- Vendor Name\n- GSTIN\n"
            "- Gross Amount\n- Tax Amount\n- Net Amount\n"
            "Return ONLY a JSON array of objects with 'field' and 'value' keys. "
            "Add a final entry with field='Match Status' and value='EXTRACTED - AI Validated'."
        )

        # 1. Try Gemini (Native Multimodal)
        if self.gemini_client:
            try:
                print("[AI] Trying Gemini for Vouching...")
                # Gemini expects bytes in a specific structure
                from google.genai import types
                resp = self.gemini_client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[
                        types.Part.from_bytes(data=contents, mime_type=mime_type),
                        prompt
                    ],
                    config={'response_mime_type': 'application/json'}
                )
                if resp and resp.text:
                    return self._clean_json(resp.text)
            except Exception as e:
                print(f"[AI] Gemini Vouching failed: {e}")

        # 2. Try OpenRouter (GPT-4o Vision and Claude 3.5 Sonnet)
        if self.or_client:
            vision_models = ["openai/gpt-4o", "anthropic/claude-3.5-sonnet", "google/gemini-flash-1.5"]
            for model_id in vision_models:
                try:
                    print(f"[AI] Falling back to OpenRouter ({model_id}) for Vouching...")
                    base64_img = base64.b64encode(contents).decode('utf-8')
                    resp = self.or_client.chat.completions.create(
                        model=model_id,
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": f"data:{mime_type};base64,{base64_img}"}
                                    }
                                ]
                            }
                        ],
                        response_format={"type": "json_object"}
                    )
                    data = json.loads(resp.choices[0].message.content)
                    # Handle different model output formats
                    if isinstance(data, dict) and 'data' in data: return data['data']
                    if isinstance(data, list): return data
                    if isinstance(data, dict): return [{"field": k, "value": v} for k, v in data.items()]
                except Exception as e:
                    print(f"[AI] OpenRouter model {model_id} failed: {e}")

        return None

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
