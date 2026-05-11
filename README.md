# StatAudit AI Platform: Next-Gen Autonomous Vouching

StatAudit AI is a high-performance, hardened AI infrastructure designed for professional auditing. It automates the complex task of invoice vouching and risk assessment using a world-class, multi-tiered AI failover system.

## 🚀 Key Features

- **Autonomous Vouching**: Automatically extracts data from uploaded invoices (PDF/Images) and matches them against ledger records.
- **Ultra-Resilient AI Pipeline**: Features a 20+ model orchestration system powered by **Gemini, Groq, and OpenRouter** to ensure zero downtime:
  1. **Primary**: **Gemini 2.0 Flash** (High-speed Multimodal & Reasoning)
  2. **Secondary**: **Groq (Llama 3 70B)** (Lightning-fast text failover)
  3. **Tertiary**: **OpenRouter Ensemble** (Failover access to **GPT-4o, Claude 3.5 Sonnet, Llama 3.1 405B, DeepSeek**, and more)
  4. **Last Resort**: **Local Tesseract OCR** (Offline extraction fallback)
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
