import json
from google import genai
from typing import Dict, Any

class AIVoucherAgent:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)

    async def extract_and_match(self, file_content: bytes, mime_type: str, ledger_row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Uses Gemini 2.0 Flash to extract data from an invoice and match it against the ledger entry.
        """
        prompt = f"""
        Extract the following data from this invoice:
        - Invoice Number
        - Invoice Date
        - Vendor Name
        - GST Number
        - Total Amount
        - Tax Amount
        - Payment Terms
        
        Then, compare it with the following Ledger Entry:
        {json.dumps(ledger_row)}
        
        Return a JSON object with two fields:
        1. 'extracted': The data from the invoice.
        2. 'match_analysis': Any discrepancies found (mismatched amount, date, vendor).
        3. 'audit_remark': A professional audit note for the working papers.
        """
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[
                    prompt,
                    {'mime_type': mime_type, 'data': file_content}
                ],
                config={'response_mime_type': 'application/json'}
            )
            return json.loads(response.text)
        except Exception as e:
            return {"error": f"Vouching failed: {str(e)}"}
