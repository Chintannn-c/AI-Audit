# StatAudit AI Platform: Next-Gen Autonomous AI Auditing

StatAudit AI is a high-performance, hardened enterprise AI infrastructure designed for professional auditing. It automates the complex task of invoice vouching, risk assessment, and smart audit sampling using a world-class, multi-tiered AI failover system with live telemetry status monitoring.

---

## 🚀 Key Features

### 1. Ultra-Resilient Multi-Tiered AI Orchestration
The core AI engine (`backend/ai_engine.py`) is powered by an ultra-resilient, dynamic routing and failover system featuring:
*   **Direct Mistral Large Integration [NEW]**: Leverages your premium **Mistral Large Enterprise API** (`mistral-large-latest`) directly for deep analytical auditing, heavy reasoning, and structured JSON parsing.
*   **Self-Healing Auto-Router (`openrouter/free`) [NEW]**: Integrates OpenRouter's dynamic gateway which automatically negotiates the healthiest, most available free provider at runtime, neutralizing 404s and 429s.
*   **Active 2026 Model Support [NEW]**: Upgraded to use active, state-of-the-art endpoints:
    *   **Reasoning (FORENSIC)**: `mistral/mistral-large-latest` (Direct), `deepseek/deepseek-r1:free`, `meta-llama/llama-3.3-70b-instruct:free`, `openrouter/free`
    *   **Fast Scanning (FAST_SCAN)**: `mistral/mistral-large-latest` (Direct), `qwen/qwen-2.5-coder-32b-instruct:free`, `openrouter/free`
    *   **OCR/Vouching (VOUCHING)**: `mistral/mistral-large-latest` (Direct), `deepseek/deepseek-r1:free`, `qwen/qwen-2.5-coder-32b-instruct:free`
*   **Dynamic Telemetry Dashboard [NEW]**: Real-time status page in the UI that displays model latency in milliseconds, live health status (`🟢 LIVE`), daily request quotas, and rate limits.

### 2. Hardened StatAudit Sampling Engine
*   **Guaranteed Sample Target**: Requesting a target (e.g. 100 samples) guarantees exactly **100 distinct transaction rows** (indices) from your ledger if available.
*   **Absolute Strict Repetition Capping**: Features progressive capped vendor balancing:
    *   *Phase 1 & 2*: Searches for a unique vendor for every row (Cap = 1).
    *   *Phase 3*: Relaxes to a strict fallback cap of **2 appearances per vendor** only when unique vendors are exhausted to meet sample sizes.
    *   *No Bypasses*: Uncapped loops are completely deleted. Under no circumstances can a single vendor appear more than 2 times in the selected sample.
*   **Vendor Repetition Dashboard [NEW]**: A glassmorphic panel in the UI presenting:
    *   **KPI Counters**: Unique vs. Repeated vendor count breakdowns.
    *   **Interactive List**: Sorted details showing repeating vendor names accompanied by badge frequencies.
    *   **Absolute Unique Clean State**: Helpful reassuring indicator when no vendors repeat.

### 3. Vouching & Materiality Analysis
*   **Materiality Engine**: Synchronized frontend/backend materiality calculations with dynamic percentage overrides.
*   **Hardened Risk Assessment**: Quantitative and qualitative risk logic that automatically classifies audit depth.
*   **Automated Excel Export**: Generates 5-sheet enterprise audit working papers with flexible field mapping for heterogeneous AI outputs.

---

## 🛠️ Tech Stack

*   **Backend**: FastAPI (Python), MongoDB, HTTPX (Asynchronous API Probing), OpenRouter (OpenAI SDK), HuggingFace Hub.
*   **Frontend**: React (Vite), CSS3 (Modern Glassmorphism Design with HSL Tailored Color Schemes), Lucide React (Icons).
*   **Testing**: Pytest & Python Unittest.

---

## 🔒 Security & Secrets Management

*   **Ignored Configuration**: Sensitive tokens (`GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `MISTRAL_API_KEY`) are stored safely in `backend/.env`, which is strictly listed in `.gitignore` and is never pushed to the remote repository.
*   **Data Isolation**: Automated MongoDB TTL indexes for temporary session data compliance.

---

## 🏃 Getting Started

### 1. Set Up Backend Environment
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create a `.env` file containing your active keys:
   ```env
   GEMINI_API_KEY=your_gemini_key
   GROQ_API_KEY=your_groq_key
   OPENROUTER_API_KEY=your_openrouter_key
   MISTRAL_API_KEY=your_mistral_key
   MONGO_URI=mongodb://localhost:27017/
   MONGO_DB_NAME=stataudit_db
   ```
3. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the FastAPI server:
   ```bash
   python main.py
   ```

### 2. Set Up Frontend Environment
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install npm packages:
   ```bash
   npm install
   ```
3. Compile production assets:
   ```bash
   npm run build
   ```
4. Run the local development server:
   ```bash
   npm run dev
   ```

---
*Built for absolute forensic precision. Hardened for enterprise production.*
