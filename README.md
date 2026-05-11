# StatAudit AI Platform: Next-Gen Autonomous Vouching

StatAudit AI is a high-performance, hardened AI infrastructure designed for professional auditing. It automates the complex task of invoice vouching and risk assessment using a world-class, multi-tiered AI failover system.

## 🚀 Key Features

- **Autonomous Vouching**: Automatically extracts data from uploaded invoices (PDF/Images) and matches them against ledger records.
- **Ultra-Resilient AI Pipeline**: Features a multi-tiered orchestration system powered by **Gemini, Groq, and OpenRouter** to ensure zero downtime. The stack is optimized with the **Best Free Models (May 2026)**:
  1. **Reasoning**: `openai/gpt-oss-120b:free` & `nousresearch/hermes-3-llama-3.1-405b:free` (Forensic Consensus)
  2. **Coding & Data**: `qwen/qwen3-coder:free` (Structured extraction)
  3. **OCR/Vision**: `nvidia/nemotron-nano-12b-v2-vl:free` (Vouching Intelligence)
  4. **Performance**: `glm-4.5-air:free` & `google/gemma-4-31b-it:free` (Rapid summarization)
  5. **Stability**: `meta-llama/llama-3.3-70b-instruct:free` (Consensus Anchor)
  6. **Last Resort**: **Local Tesseract OCR** (Offline extraction fallback)
- **Materiality Engine**: Synchronized frontend/backend materiality calculations with dynamic percentage overrides.
- **Hardened Risk Assessment**: Quantitative and qualitative risk logic that automatically classifies audit depth (TOC/TOD) based on governance and misstatement history.
- **Multimodal Support**: Native handling of PDFs and Images using PyMuPDF and Pillow.

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
