import os
import sys
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
sys.path.append(os.path.dirname(__file__))

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import pandas as pd
import io
import json
import traceback
import numpy as np
import gridfs
from datetime import datetime, timezone
from pymongo import MongoClient
from analyzer import AuditAnalyzer
from report_generator import AuditReportGenerator
from materiality import MaterialityCalculator
from risk_assessment import RiskAssessmentEngine
from ai_engine import ai_engine

app = FastAPI(title="StatAudit Pro - Enterprise AI Sampling")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# AI Engine is handled by ai_engine.py

# MongoDB Setup
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "stataudit_db")

try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    mongo_client.server_info() # Trigger exception if offline
    db = mongo_client[MONGO_DB_NAME]
    fs = gridfs.GridFS(db)
    sessions_coll = db["sessions"]
    logs_coll = db["audit_logs"]
    print(f"[SUCCESS] Connected to MongoDB ({MONGO_DB_NAME})")
    # Create TTL indexes for auto-purge
    try:
        sessions_coll.create_index("last_updated", expireAfterSeconds=7*24*3600)  # 7 days
        logs_coll.create_index("timestamp", expireAfterSeconds=30*24*3600)  # 30 days
    except Exception:
        pass  # Index may already exist
except Exception as e:
    print(f"[ERROR] MongoDB connection failed: {e}. Ensure MongoDB is running on localhost:27017.")
    # Fallback to local dict for testing if mongo isn't available
    fs = None
    sessions_coll = None
    logs_coll = None
    audit_context = {"materiality": {}, "risk": {}}

def get_session(session_id: str):
    if sessions_coll is not None:
        doc = sessions_coll.find_one({"session_id": session_id})
        return doc if doc else {"materiality": {}, "risk": {}}
    return audit_context

def update_session(session_id: str, data: dict):
    if sessions_coll is not None:
        sessions_coll.update_one(
            {"session_id": session_id},
            {"$set": {**data, "last_updated": datetime.now(timezone.utc)}},
            upsert=True
        )
    else:
        audit_context.update(data)

def log_audit_action(session_id: str, action: str, details: dict):
    if logs_coll is not None:
        logs_coll.insert_one({
            "session_id": session_id,
            "action": action,
            "details": details,
            "timestamp": datetime.now(timezone.utc)
        })

# ──────────────────────────────────────────────
# FAVICON (prevent spurious download)
# ──────────────────────────────────────────────

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

# ──────────────────────────────────────────────
# UTILITIES
# ──────────────────────────────────────────────

def load_ledger(contents: bytes, file_ext: str) -> pd.DataFrame:
    """Robustly load a ledger file, auto-detecting the header row."""
    # Phase 3: Detect HTML files disguised as .xls (common ERP export)
    header_check = contents[:500].decode('utf-8', errors='ignore').strip().lower()
    if header_check.startswith('<!doctype') or header_check.startswith('<html') or '<table' in header_check[:200]:
        try:
            tables = pd.read_html(io.BytesIO(contents))
            if tables:
                return tables[0]
        except Exception:
            pass  # Fall through to normal parsing

    if file_ext == '.csv':
        try:
            return pd.read_csv(io.BytesIO(contents))
        except:
            pass

    # Try default load first, catching engine errors
    try:
        engine = 'openpyxl' if file_ext == '.xlsx' else ('xlrd' if file_ext == '.xls' else None)
        df = pd.read_excel(io.BytesIO(contents), engine=engine)
    except Exception:
        # Fallback 1: Might be an .xlsx incorrectly named as .xls
        try:
            df = pd.read_excel(io.BytesIO(contents), engine='openpyxl')
        except Exception:
            # Fallback 2: Might be a CSV masquerading as Excel
            try:
                df = pd.read_csv(io.BytesIO(contents))
            except Exception:
                raise ValueError("File format could not be determined. Please ensure it is a valid .xlsx, .xls, or .csv")

    # If >50% of columns are "Unnamed", the real header is further down
    unnamed_ratio = sum('Unnamed' in str(c) for c in df.columns) / max(len(df.columns), 1)
    if unnamed_ratio > 0.5:
        for skip in range(1, 15):
            try:
                engine = 'openpyxl' if file_ext == '.xlsx' else ('xlrd' if file_ext == '.xls' else None)
                try:
                    df = pd.read_excel(io.BytesIO(contents), skiprows=skip, engine=engine)
                except Exception:
                    try:
                        df = pd.read_excel(io.BytesIO(contents), skiprows=skip, engine='openpyxl')
                    except Exception:
                        df = pd.read_csv(io.BytesIO(contents), skiprows=skip)
                    
                new_ratio = sum('Unnamed' in str(c) for c in df.columns) / max(len(df.columns), 1)
                if new_ratio <= 0.5:
                    break
            except:
                break
    return df

def safe_json(obj):
    """Make an object JSON-serializable (handle NaN, numpy types)."""
    if isinstance(obj, dict):
        return {k: safe_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [safe_json(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if np.isnan(v) else v
    if isinstance(obj, float) and np.isnan(obj):
        return None
    return obj

async def get_ai_insights(category: str, stats: dict) -> dict:
    """Delegated to Multi-Model Engine."""
    return await ai_engine.get_summary(category, stats)

# ──────────────────────────────────────────────
# ENDPOINTS
# ──────────────────────────────────────────────



@app.post("/api/materiality")
async def setup_materiality(
    session_id: str = Form(...),
    npbt: float = Form(...),
    romm: str = Form(...),
    perf_pct: float = Form(75.0),
    trivial_pct: float = Form(3.0),
    overall_pct: Optional[float] = Form(None)
):
    try:
        calc = MaterialityCalculator(npbt, romm)
        res = calc.calculate(perf_pct, trivial_pct, explicit_overall_pct=overall_pct)
        update_session(session_id, {"materiality": res})
        return res
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/risk-assessment")
async def setup_risk(
    session_id: str = Form(...),
    turnover_250: bool = Form(...),
    ifc: bool = Form(...),
    governance: bool = Form(...),
    misstatements: bool = Form(...)
):
    try:
        engine = RiskAssessmentEngine(turnover_250, ifc, governance, misstatements)
        res = engine.assess()
        update_session(session_id, {"risk": res})
        return res
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/analyze")
async def analyze_ledger(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    category: str = Form(...),
    sample_pct: float = Form(20.0),
    sampling_basis: str = Form('count'),
    tod_pct: float = Form(70.0)
):
    try:
        print(f"--- Analysis [{session_id}]: {file.filename} | {category} | {sample_pct}% | {sampling_basis} | TOD:{tod_pct}% ---")
        contents = await file.read()
        
        # Store original ledger in GridFS
        file_id = None
        if fs is not None:
            # Check if we already stored it this session to avoid duplicates
            existing = db.fs.files.find_one({"metadata.session_id": session_id, "metadata.type": "source_ledger"})
            if not existing:
                file_id = fs.put(contents, filename=file.filename, metadata={"session_id": session_id, "type": "source_ledger"})
            else:
                file_id = existing["_id"]

        ext = os.path.splitext(file.filename)[1].lower()
        df = load_ledger(contents, ext)
        print(f"Loaded: {len(df)} rows, {len(df.columns)} cols")

        context = get_session(session_id)
        trivial = context.get("materiality", {}).get("trivial_threshold", 0)
        perf_mat = context.get("materiality", {}).get("performance_materiality", 0)

        analyzer = AuditAnalyzer(df, category,
                                  trivial_threshold=trivial,
                                  performance_materiality=perf_mat)

        stats = analyzer.get_statistics()
        tod, toc = analyzer.generate_samples(
            sample_pct=sample_pct,
            sampling_basis=sampling_basis,
            tod_pct=tod_pct
        )
        risk_analysis = analyzer.get_risk_analysis()
        print(f"Results: TOD={len(tod)}, TOC={len(toc)}, HighRisk={risk_analysis.get('high_risk_count', 0)}")

        # Compute values
        amt_col = analyzer.amount_col
        tod_value = float(tod[amt_col].abs().sum()) if amt_col and len(tod) > 0 else 0
        toc_value = float(toc[amt_col].abs().sum()) if amt_col and len(toc) > 0 else 0

        # AI insights (non-blocking)
        ai_insights = await get_ai_insights(category, stats)

        # Dashboard JSON (forensic metrics, Gini, trends, etc.)
        dashboard = analyzer.get_dashboard_json()

        # Top 10 preview
        scored = analyzer.score_risks()
        top_10 = scored.head(10).replace({np.nan: None}).to_dict(orient="records")

        response = safe_json({
            "stats": stats,
            "ai_insights": ai_insights,
            "risk_analysis": risk_analysis,
            "dashboard": dashboard,
            "tod_count": len(tod),
            "toc_count": len(toc),
            "tod_value": tod_value,
            "toc_value": toc_value,
            "total_selected": len(tod) + len(toc),
            "sampling_basis": sampling_basis,
            "top_10": top_10,
            "filename": file.filename
        })
        
        
        log_audit_action(session_id, "RUN_ANALYSIS", {
            "category": category, "file": file.filename, "stats": stats,
            "tod_count": len(tod), "toc_count": len(toc),
            "gridfs_file_id": str(file_id) if file_id else None
        })
        
        return response

    except Exception as e:
        print("CRITICAL ERROR:")
        traceback.print_exc()
        return JSONResponse(status_code=500,
                            content={"error": f"{type(e).__name__}: {str(e)}"})

@app.post("/api/download")
async def download_report(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    category: str = Form(...),
    sample_pct: float = Form(20.0),
    sampling_basis: str = Form('count'),
    tod_pct: float = Form(70.0)
):
    try:
        contents = await file.read()
        ext = os.path.splitext(file.filename)[1].lower()
        df = load_ledger(contents, ext)

        context = get_session(session_id)
        trivial = context.get("materiality", {}).get("trivial_threshold", 0)
        perf_mat = context.get("materiality", {}).get("performance_materiality", 0)

        analyzer = AuditAnalyzer(df, category,
                                  trivial_threshold=trivial,
                                  performance_materiality=perf_mat)

        stats = analyzer.get_statistics()
        tod, toc = analyzer.generate_samples(
            sample_pct=sample_pct,
            sampling_basis=sampling_basis,
            tod_pct=tod_pct
        )
        risk_analysis = analyzer.get_risk_analysis()
        print(f"--- Download: Loaded={len(df)} rows | AmtCol={analyzer.amount_col} | VendorCol={analyzer.vendor_col}")
        print(f"--- Download: TOD={len(tod)} rows | TOC={len(toc)} rows | Total={len(tod)+len(toc)}")

        sampling_config = {
            'basis': sampling_basis,
            'sample_pct': sample_pct,
            'tod_pct': tod_pct,
            'amount_col': analyzer.amount_col or ''
        }

        # Fetch Vouching Results for this session
        vouching_results = []
        if db is not None:
            try:
                vouching_results = list(db["vouching_results"].find({"session_id": session_id}))
            except Exception:
                pass

        report = AuditReportGenerator(
            original_df=df,
            tod=tod, toc=toc,
            stats=stats, category=category,
            risk_analysis=risk_analysis,
            sampling_config=sampling_config
        )
        report.add_engagement_data(
            context.get("materiality", {}),
            context.get("risk", {})
        )
        output = report.generate(vouching_results=vouching_results)

        # Store generated Working Paper in GridFS
        wp_file_id = None
        if fs is not None:
            output.seek(0)
            wp_filename = f"Audit_Working_Papers_{category}_{sample_pct}pct.xlsx"
            wp_file_id = fs.put(output.read(), filename=wp_filename, metadata={"session_id": session_id, "type": "generated_report"})
            output.seek(0) # Reset stream pointer for the StreamingResponse

        log_audit_action(session_id, "DOWNLOAD_REPORT", {
            "category": category, "file": file.filename,
            "gridfs_report_id": str(wp_file_id) if wp_file_id else None
        })

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition":
                      f"attachment; filename=Audit_Working_Papers_{category}_{int(sample_pct)}pct.xlsx"}
        )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/vouch")
async def vouch_invoice(
    session_id: str = Form(...),
    file: UploadFile = File(...)
):
    """Real AI Vouching via Multi-Model Engine."""
    contents = await file.read()
    
    # Store in GridFS
    file_id = None
    if fs is not None:
        file_id = fs.put(contents, filename=file.filename, metadata={"session_id": session_id, "type": "voucher_upload"})

    # Determine MIME type
    ext = os.path.splitext(file.filename)[1].lower()
    mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.pdf': 'application/pdf'}
    mime_type = mime_map.get(ext, 'application/octet-stream')

    # 1. Local OCR Extraction (MANDATORY per requirements)
    from ocr_service import ocr_service
    ocr_text = ocr_service.extract_text(contents, mime_type)
    
    if not ocr_text:
        return JSONResponse(status_code=400, content={"error": "OCR failed to extract text from document."})

    # 2. AI Structured Parsing from OCR Text
    ai_result = await ai_engine.vouch_invoice(ocr_text)
    
    extracted_data = ai_result.get("data", [])
    model_used = ai_result.get("model_used", "Ensemble AI")
    raw_extraction = ai_result.get("raw_extraction", {})

    if not extracted_data:
        extracted_data = [{"field": "Extraction Status", "value": "AI parsing failed - raw OCR only"}]
        # Optionally add some raw text if AI fails
        extracted_data.append({"field": "Raw Text Sample", "value": ocr_text[:100] + "..."})
    else:
        # We successfully got data, we can now skip the old fallback logic
        return {"data": extracted_data, "model_used": model_used}
    
    if not extracted_data:
        try:
            print("[VOUCH] AI extraction failed. Falling back to Tesseract OCR...")
            import pytesseract
            from PIL import Image
            import re
            
            if os.name == 'nt':
                pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
            
            # Handle PDFs vs Images
            if mime_type == 'application/pdf':
                import fitz  # PyMuPDF
                doc = fitz.open(stream=contents, filetype="pdf")
                page = doc.load_page(0) # First page only
                pix = page.get_pixmap()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            else:
                img = Image.open(io.BytesIO(contents))
                
            raw_text = pytesseract.image_to_string(img)
            
            inv_no = re.search(r'(?i)(?:invoice\s*(?:no|number|#)?)\s*[:\-]?\s*([A-Z0-9\-]+)', raw_text)
            date = re.search(r'(?i)(?:date)\s*[:\-]?\s*([\d]{1,2}[/\-\.][\d]{1,2}[/\-\.][\d]{2,4})', raw_text)
            amt = re.search(r'(?i)(?:total|amount|gross|net)\s*[:\-]?\s*[$₹£€Rs\.]?\s*([\d,]+\.\d{2})', raw_text)
            gst = re.search(r'(?i)(?:gstin|gst|tin)\s*[:\-]?\s*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1})', raw_text)
            
            extracted_data = [
                {"field": "Invoice No", "value": inv_no.group(1) if inv_no else "Not Found (OCR)"},
                {"field": "Vendor Name", "value": "Review Manually (OCR)"},
                {"field": "Date", "value": date.group(1) if date else "Not Found (OCR)"},
                {"field": "Gross Amount", "value": amt.group(1) if amt else "Not Found (OCR)"},
                {"field": "GSTIN", "value": gst.group(1) if gst else "Not Found (OCR)"},
                {"field": "Match Status", "value": "EXTRACTED (Tesseract OCR Fallback)"}
            ]
        except Exception as ocr_e:
            print(f"[VOUCH] Tesseract OCR failed: {ocr_e}")

    # Final fallback if both AI and OCR failed
    if not extracted_data:
        extracted_data = [
            {"field": "Invoice No", "value": "Could not extract (AI/OCR unavailable)"},
            {"field": "Vendor Name", "value": "N/A"},
            {"field": "Date", "value": "N/A"},
            {"field": "Gross Amount", "value": "N/A"},
            {"field": "GSTIN", "value": "N/A"},
            {"field": "Match Status", "value": "FALLBACK - Extraction failed"}
        ]

    # Store vouching results in MongoDB for persistence and Excel reporting
    if db is not None:
        try:
            vouch_results_coll = db["vouching_results"]
            vouch_results_coll.update_one(
                {"session_id": session_id, "filename": file.filename},
                {"$set": {
                    "extracted_data": extracted_data,
                    "model_used": model_used,
                    "timestamp": datetime.now(timezone.utc)
                }},
                upsert=True
            )
        except Exception as db_err:
            print(f"[ERROR] Failed to store vouching result: {db_err}")

    log_audit_action(session_id, "VOUCH_INVOICE", {
        "file": file.filename,
        "model_used": model_used,
        "gridfs_voucher_id": str(file_id) if file_id else None
    })

    return {"status": "success", "data": extracted_data, "model_used": model_used}

@app.get("/api/download/vouching")
async def download_vouching_report(session_id: str):
    """Generates a vouching-only reconciliation report."""
    try:
        if db is None:
            return JSONResponse(status_code=400, content={"error": "Database not connected"})
            
        vouch_results_coll = db["vouching_results"]
        results = list(vouch_results_coll.find({"session_id": session_id}, {"_id": 0}).sort("timestamp", -1))
        
        if not results:
            return JSONResponse(status_code=400, content={"error": "No vouching results found for this session"})
            
        # Create a report with empty sampling data
        report = AuditReportGenerator(
            original_df=pd.DataFrame(),
            tod=pd.DataFrame(), toc=pd.DataFrame(),
            stats={'count': 0, 'sum': 0}, category="Forensic Vouching",
            risk_analysis={},
            sampling_config={}
        )
        
        output = report.generate(vouching_results=results)
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=Vouching_Reconciliation_Report.xlsx"}
        )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/vouch/history")
async def get_vouch_history(session_id: str):
    """Fetch all vouching results for a session."""
    if db is None:
        return {"data": []}
    
    try:
        vouch_results_coll = db["vouching_results"]
        results = list(vouch_results_coll.find({"session_id": session_id}, {"_id": 0}).sort("timestamp", -1))
        return {"data": results}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/vouch/deep-audit")
async def deep_audit_transaction(
    session_id: str = Form(...),
    transaction: str = Form(...),
    category: str = Form("Sales")
):
    """AI-powered multi-model forensic remarks for a single transaction."""
    try:
        txn_data = json.loads(transaction)
        result = await ai_engine.deep_audit_remark(txn_data, category)
        
        log_audit_action(session_id, "DEEP_AUDIT", {
            "category": category,
            "risk_level": result.get("risk_level", "Unknown"),
            "consensus": result.get("consensus", False)
        })
        
        return {"status": "success", "data": result}
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend')
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
