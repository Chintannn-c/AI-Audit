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
                # OpenRouter uses OpenAI compatible client
                self.or_client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=self.openrouter_key,
                )
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

        # 3. Try OpenRouter (GPT-4o / Claude 3)
        if self.or_client:
            try:
                print("[AI] Falling back to OpenRouter...")
                resp = self.or_client.chat.completions.create(
                    model="openai/gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                return json.loads(resp.choices[0].message.content)
            except Exception as e:
                print(f"[AI] OpenRouter failed: {e}")

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

        # 2. Try OpenRouter (GPT-4o Vision)
        if self.or_client:
            try:
                print("[AI] Falling back to OpenRouter (GPT-4o) for Vouching...")
                base64_img = base64.b64encode(contents).decode('utf-8')
                resp = self.or_client.chat.completions.create(
                    model="openai/gpt-4o",
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
                # Ensure it's the array format expected by the frontend
                if isinstance(data, dict) and 'data' in data: return data['data']
                if isinstance(data, list): return data
                # If it's a flat dict of fields, convert to array
                return [{"field": k, "value": v} for k, v in data.items()]
            except Exception as e:
                print(f"[AI] OpenRouter Vouching failed: {e}")

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
