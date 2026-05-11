# StatAudit AI Platform: Next-Gen Autonomous Vouching

StatAudit AI is a high-performance, hardened AI infrastructure designed for professional auditing. It automates the complex task of invoice vouching and risk assessment using a world-class, multi-tiered AI failover system.

## 🚀 Key Features

- **Autonomous Vouching**: Automatically extracts data from uploaded invoices (PDF/Images) and matches them against ledger records.
- **Ultra-Resilient AI Pipeline**: Features an 8-tier failover system to ensure zero downtime, even during API rate limits:
  1. **Gemini 3.1 Pro & 3.0 Pro** (Primary Reasoning)
  2. **Gemini 2.0 Flash** (High-speed Multimodal)
  3. **Hugging Face Qwen2-VL** (Secondary API Fallback)
  4. **Local Tesseract OCR** (Absolute Offline Last-Resort)
- **Materiality Engine**: Synchronized frontend/backend materiality calculations with dynamic percentage overrides.
- **Hardened Risk Assessment**: Quantitative and qualitative risk logic that automatically classifies audit depth (TOC/TOD) based on governance and misstatement history.
- **Multimodal Support**: Native handling of PDFs and Images using PyMuPDF and Pillow.

## 🛠️ Tech Stack

- **Backend**: FastAPI (Python), MongoDB, Google GenAI SDK, Hugging Face Hub, PyMuPDF.
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
