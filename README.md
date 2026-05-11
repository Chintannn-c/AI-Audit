# StatAudit AI Platform: Next-Gen Autonomous Vouching

StatAudit AI is a high-performance, hardened AI infrastructure designed for professional auditing. It automates the complex task of invoice vouching and risk assessment using a world-class, multi-tiered AI failover system.

## 🚀 Key Features

- **Forensic Reconciliation Dashboard**: Real-time summary of vouching history with automated match/mismatch status and deep-audit logs.
- **Ultra-Resilient AI Pipeline**: Features a multi-tiered orchestration system powered by **Gemini, Groq, and OpenRouter** with **Automatic 429 Rate-Limit Backoff** (2s wait logic) to ensure extraction reliability. The stack is optimized with the latest free models:
  1. **Reasoning**: `openai/gpt-oss-120b:free` (Forensic Consensus)
  2. **Coding & Data**: `qwen/qwen3-coder:free` (Structured extraction)
  3. **Fast Backup**: `meta-llama/llama-3.3-70b-instruct:free` (Volume scanning)
  4. **OCR/Vision**: `baidu/qianfan-ocr-fast:free` (Vouching Intelligence)
  5. **Last Resort**: **Local Tesseract OCR** (Offline extraction fallback)
- **Smart Audit Sampling**: Forensic-grade sampling logic that ensures robust coverage (TOD/TOC) across all high-risk vendors.
- **Materiality Engine**: Synchronized frontend/backend materiality calculations with dynamic percentage overrides.
- **Hardened Risk Assessment**: Quantitative and qualitative risk logic that automatically classifies audit depth.
- **Automated Excel Export**: Generates 5-sheet enterprise audit working papers with flexible field mapping for heterogeneous AI outputs.

## 🛠️ Tech Stack

- **Backend**: FastAPI (Python), MongoDB, Google GenAI, Groq, OpenRouter (OpenAI SDK), Hugging Face Hub.
- **Frontend**: Vanilla JS (Dynamic UI), CSS3 (Modern Glassmorphism Design).
- **OCR**: Pytesseract (Local Fallback).

## 🔒 Security

- **Credential Masking**: All sensitive API keys are managed via `.env` and are strictly ignored by Git.
- **Data Integrity**: Automated MongoDB TTL indexes for session data compliance.

## 🏃 Getting Started

1. **Install Dependencies**:
   ```bash
   pip install -r backend/requirements.txt
   ```
2. **Setup Environment**:
   Create a `backend/.env` file with your `GEMINI_API_KEY`, `HF_TOKEN`, and `MONGO_URI`.
3. **Run Platform**:
   ```bash
   python backend/main.py
   ```

---
*Built for accuracy. Hardened for production.*
