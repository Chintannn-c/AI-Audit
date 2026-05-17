import os
import sys
import secrets
import hmac
import hashlib
import time
import re
import io
import json
import traceback
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# Ensure local directory is in path BEFORE imports
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, '.env'))

import pandas as pd
import numpy as np
import gridfs
from pymongo import MongoClient

from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, Security, Request, Cookie, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, constr

try:
    from analyzer import AuditAnalyzer
    from report_generator import AuditReportGenerator
    from materiality import MaterialityCalculator
    from risk_assessment import RiskAssessmentEngine
    from ai_engine import ai_engine
except ImportError:
    from backend.analyzer import AuditAnalyzer
    from backend.report_generator import AuditReportGenerator
    from backend.materiality import MaterialityCalculator
    from backend.risk_assessment import RiskAssessmentEngine
    from backend.ai_engine import ai_engine

app = FastAPI(title="StatAudit Pro - Enterprise AI Sampling")

# ──────────────────────────────────────────────
# SECURITY CONFIGURATION & CORS HARDENING
# ──────────────────────────────────────────────
CORS_ORIGINS_ENV = os.getenv("CORS_ORIGINS", "")
allowlist_origins = [o.strip() for o in CORS_ORIGINS_ENV.split(",") if o.strip()]
if not allowlist_origins:
    allowlist_origins = ["http://localhost:8000", "http://127.0.0.1:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowlist_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Cookie"],
)

# MongoDB Setup
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "stataudit_db")

# Force TLS in connection string for production environment
if "replicaSet" in MONGO_URI or "mongodb+srv" in MONGO_URI:
    if "ssl=true" not in MONGO_URI.lower() and "tls=true" not in MONGO_URI.lower():
        if "?" in MONGO_URI:
            MONGO_URI += "&tls=true"
        else:
            MONGO_URI += "?tls=true"

try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    mongo_client.server_info()
    db = mongo_client[MONGO_DB_NAME]
    fs = gridfs.GridFS(db)
    sessions_coll = db["sessions"]
    logs_coll = db["audit_logs"]
    print(f"[SUCCESS] Connected to MongoDB ({MONGO_DB_NAME})")
    
    # Create indexes and TTL auto-purges
    try:
        sessions_coll.create_index("expires_at", expireAfterSeconds=0)
        logs_coll.create_index("timestamp", expireAfterSeconds=30*24*3600)
        db["rate_limits"].create_index("expires_at", expireAfterSeconds=0)
        db["ip_bans"].create_index("expires_at", expireAfterSeconds=0)
        db["rate_limit_breaches"].create_index("expires_at", expireAfterSeconds=0)
    except Exception:
        pass
except Exception as e:
    print(f"[ERROR] MongoDB connection failed: {e}. Ensure MongoDB is running on localhost:27017.")
    fs = None
    sessions_coll = None
    logs_coll = None
    audit_context = {"materiality": {}, "risk": {}}

# ──────────────────────────────────────────────
# PII & SECURITY LOG REDACTION
# ──────────────────────────────────────────────
def redact_sensitive_data(message: str) -> str:
    if not isinstance(message, str):
        return message
    message = re.sub(r"stataudit_session_id=[A-Za-z0-9_-]{32,64}", "stataudit_session_id=[REDACTED]", message)
    message = re.sub(r"Bearer [A-Za-z0-9_-]{32,64}", "Bearer [REDACTED]", message)
    message = re.sub(r"(?i)vendor[_ ]name['\"]?\s*:\s*['\"]?[^'\"]+['\"]?", "vendor_name: [REDACTED]", message)
    message = re.sub(r"(?i)amount['\"]?\s*:\s*['\"]?\d+(\.\d+)?['\"]?", "amount: [REDACTED]", message)
    message = re.sub(r"\b[a-zA-Z]{5}\d{4}[a-zA-Z]{1}\b", "[PAN REDACTED]", message)
    message = re.sub(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b", "[GSTIN REDACTED]", message)
    return message

class RedactingFormatter(logging.Formatter):
    def format(self, record):
        orig_msg = super().format(record)
        return redact_sensitive_data(orig_msg)

# Setup Redacting Logger
logger = logging.getLogger("stataudit")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setFormatter(RedactingFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(ch)

# ──────────────────────────────────────────────
# MONGO RATE LIMITER & IP BAN CIRCUIT BREAKER
# ──────────────────────────────────────────────
def check_rate_limit(key: str, limit: int, window_seconds: int) -> tuple:
    if db is None:
        return True, 0
    rate_limits_coll = db["rate_limits"]
    now = datetime.now(timezone.utc)
    bucket_id = int(now.timestamp() / window_seconds)
    db_key = f"{key}:{bucket_id}"
    
    res = rate_limits_coll.find_one_and_update(
        {"_id": db_key},
        {
            "$inc": {"count": 1},
            "$setOnInsert": {
                "expires_at": now + timedelta(seconds=window_seconds * 2),
                "created_at": now
            }
        },
        upsert=True,
        return_document=True
    )
    count = res.get("count", 1)
    if count > limit:
        created_at = res["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        elapsed = (now - created_at).total_seconds()
        retry_after = max(1, int(window_seconds - elapsed))
        return False, retry_after
    return True, 0

def record_rate_limit_breach(ip: str):
    if db is None:
        return
    breaches_coll = db["rate_limit_breaches"]
    now = datetime.now(timezone.utc)
    breaches_coll.insert_one({
        "ip": ip,
        "timestamp": now,
        "expires_at": now + timedelta(minutes=5)
    })
    count = breaches_coll.count_documents({
        "ip": ip,
        "timestamp": {"$gte": now - timedelta(minutes=5)}
    })
    if count >= 3:
        logger.warning(f"IP {ip} triggered global circuit breaker. Temporary ban active.")
        db["ip_bans"].update_one(
            {"_id": ip},
            {"$set": {"expires_at": now + timedelta(hours=1)}},
            upsert=True
        )

def check_ip_ban(ip: str) -> bool:
    if os.getenv("TESTING") == "1":
        return False
    if db is None:
        return False
    bans_coll = db["ip_bans"]
    ban = bans_coll.find_one({"_id": ip})
    if ban:
        now = datetime.now(timezone.utc)
        expires_at = ban.get("expires_at", now)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > now:
            return True
        else:
            bans_coll.delete_one({"_id": ip})
    return False

# ──────────────────────────────────────────────
# UPLOAD / DOWNLOAD SECURITY & ISOLATION
# ──────────────────────────────────────────────
DATA_ROOT = os.path.abspath(os.path.join(BASE_DIR, "data"))
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB

def get_session_dir(session_id: str) -> str:
    verify_session_id(session_id)
    session_dir = os.path.abspath(os.path.join(DATA_ROOT, session_id))
    if not session_dir.startswith(DATA_ROOT):
        raise HTTPException(status_code=400, detail="Invalid session path")
    os.makedirs(session_dir, exist_ok=True)
    return session_dir

def sanitize_filename(filename: str) -> str:
    if ".." in filename or "/" in filename or "\\" in filename or "\x00" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename format")
    try:
        filename.encode("utf-8").decode("utf-8")
    except UnicodeError:
        raise HTTPException(status_code=400, detail="Invalid non-UTF-8 characters in filename")
    
    cleaned = re.sub(r"[^a-zA-Z0-9_\.-]", "", filename)
    return cleaned if cleaned else "upload.bin"

def validate_uploaded_file(file: UploadFile):
    contents = file.file.read(MAX_FILE_SIZE + 1)
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File size exceeds maximum limit of 25MB")
    file.file.seek(0)
    
    ext = os.path.splitext(file.filename)[1].lower()
    magic = contents[:4]
    
    if ext in (".xlsx", ".xls"):
        # Excel files can be:
        # 1. OpenXML Zip (.xlsx or incorrectly named .xls) -> PK\x03\x04
        # 2. OLE2 Compound Document (.xls or incorrectly named .xlsx) -> \xD0\xCF\x11\xE0
        # 3. HTML/XML spreadsheet disguised as xls/xlsx -> starts with <
        header_check = contents[:500].decode('utf-8', errors='ignore').strip().lower()
        is_html = header_check.startswith('<!doctype') or header_check.startswith('<html') or '<table' in header_check[:200]
        if magic != b"\x50\x4B\x03\x04" and magic != b"\xD0\xCF\x11\xE0" and not is_html:
            raise HTTPException(status_code=400, detail=f"Invalid Excel ({ext}) file contents (magic bytes mismatch)")
    elif ext == ".csv":
        try:
            contents[:500].decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Invalid CSV file contents (not valid UTF-8 text)")
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format. Only .xlsx, .xls, and .csv files are permitted")

# ──────────────────────────────────────────────
# AUTHENTICATION & SESSION MANAGEMENT HELPERS
# ──────────────────────────────────────────────
SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{32,64}$"
security_bearer = HTTPBearer(auto_error=False)

def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()

def verify_session_id(session_id: str) -> str:
    if not session_id or not isinstance(session_id, str) or not re.match(SESSION_ID_PATTERN, session_id):
        raise HTTPException(status_code=401, detail="Unauthorized session credentials")
    return session_id

def hash_fingerprint(user_agent: str, accept_lang: str) -> str:
    return hashlib.sha256(f"{user_agent}|{accept_lang}".encode("utf-8")).hexdigest()

def get_ip_subnet(ip: str) -> str:
    if not ip:
        return ""
    if ":" in ip:
        return ":".join(ip.split(":")[:3])  # /48 prefix for IPv6
    return ".".join(ip.split(".")[:3])  # /24 subnet prefix for IPv4

def raise_unauthorized(start_time: float):
    elapsed = time.time() - start_time
    delay = 0.250 - elapsed
    if delay > 0:
        time.sleep(delay)
    raise HTTPException(status_code=401, detail="Unauthorized session credentials")

def safe_filter(**kwargs) -> dict:
    sanitized = {}
    for k, v in kwargs.items():
        if isinstance(v, dict):
            raise HTTPException(status_code=422, detail=f"Invalid parameter structure for {k}")
        if v is not None:
            sanitized[k] = str(v)
    return sanitized

# ──────────────────────────────────────────────
# FastAPI Security Dependency
# ──────────────────────────────────────────────
async def require_session(
    request: Request,
    stataudit_session_id: Optional[str] = Cookie(None),
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> dict:
    start_time = time.time()
    if not stataudit_session_id:
        raise_unauthorized(start_time)
    try:
        session_id = verify_session_id(stataudit_session_id)
    except Exception:
        raise_unauthorized(start_time)
        
    if not auth or not auth.credentials:
        raise_unauthorized(start_time)
    session_secret = auth.credentials
    
    if db is None:
        raise HTTPException(status_code=500, detail="Database offline")
        
    sessions_coll = db["sessions"]
    session = sessions_coll.find_one({"session_id": session_id})
    if not session or session.get("is_revoked", False):
        raise_unauthorized(start_time)
        
    stored_hash = session.get("session_secret_hash")
    provided_hash = hash_secret(session_secret)
    if not stored_hash or not hmac.compare_digest(stored_hash, provided_hash):
        sessions_coll.update_one({"session_id": session_id}, {"$set": {"is_revoked": True}})
        raise_unauthorized(start_time)
        
    now = datetime.now(timezone.utc)
    expires_at = session.get("expires_at")
    last_activity_at = session.get("last_activity_at", session.get("created_at"))
    
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if last_activity_at and last_activity_at.tzinfo is None:
        last_activity_at = last_activity_at.replace(tzinfo=timezone.utc)
        
    if (expires_at and now > expires_at) or (last_activity_at and now > last_activity_at + timedelta(hours=2)):
        raise_unauthorized(start_time)
        
    client_ip = request.client.host if request.client else ""
    user_agent = request.headers.get("User-Agent", "")
    accept_lang = request.headers.get("Accept-Language", "")
    
    current_subnet = get_ip_subnet(client_ip)
    current_fingerprint = hash_fingerprint(user_agent, accept_lang)
    
    stored_subnet = session.get("ip_subnet", "")
    stored_fingerprint = session.get("browser_fingerprint", "")
    
    if (stored_subnet and current_subnet != stored_subnet) or (stored_fingerprint and current_fingerprint != stored_fingerprint):
        sessions_coll.update_one({"session_id": session_id}, {"$set": {"is_revoked": True}})
        raise_unauthorized(start_time)
        
    # Rate Limiting
    await check_rate_limits(request, session)
    
    # Update last active time
    sessions_coll.update_one(
        {"session_id": session_id},
        {"$set": {"last_activity_at": now}}
    )
    
    # Secret rotation (older than 15 mins)
    secret_created_at = session.get("secret_created_at", session.get("created_at"))
    if secret_created_at and secret_created_at.tzinfo is None:
        secret_created_at = secret_created_at.replace(tzinfo=timezone.utc)
        
    if secret_created_at and (now - secret_created_at) > timedelta(minutes=15):
        new_secret = secrets.token_urlsafe(32)
        new_hash = hash_secret(new_secret)
        sessions_coll.update_one(
            {"session_id": session_id},
            {"$set": {
                "session_secret_hash": new_hash,
                "secret_created_at": now
            }}
        )
        request.state.rotated_secret = new_secret
        
    return session

async def check_rate_limits(request: Request, session: Optional[dict] = None):
    if os.getenv("TESTING") == "1":
        return
    client_ip = request.client.host if request.client else ""
    if check_ip_ban(client_ip):
        raise HTTPException(status_code=403, detail="Access temporarily suspended due to security rate limit breaches.")
        
    path = request.url.path
    
    if path == "/api/session/create":
        allowed, retry_after = check_rate_limit(f"ip_create:{client_ip}", 5, 60)
        if not allowed:
            record_rate_limit_breach(client_ip)
            raise HTTPException(status_code=429, headers={"Retry-After": str(retry_after)}, detail="Rate limit exceeded")
            
    elif path in ["/api/analyze", "/api/vouch/deep-audit"]:
        if not session:
            return
        session_id = session["session_id"]
        
        allowed_ip, retry_after_ip = check_rate_limit(f"ip_heavy:{client_ip}", 30, 3600)
        if not allowed_ip:
            record_rate_limit_breach(client_ip)
            raise HTTPException(status_code=429, headers={"Retry-After": str(retry_after_ip)}, detail="Rate limit exceeded")
            
        allowed_sess, retry_after_sess = check_rate_limit(f"sess_heavy:{session_id}", 10, 3600)
        if not allowed_sess:
            raise HTTPException(status_code=429, headers={"Retry-After": str(retry_after_sess)}, detail="Rate limit exceeded")
            
    elif path in ["/api/download", "/api/download/vouching"]:
        if not session:
            return
        session_id = session["session_id"]
        allowed, retry_after = check_rate_limit(f"sess_dl:{session_id}", 20, 3600)
        if not allowed:
            raise HTTPException(status_code=429, headers={"Retry-After": str(retry_after)}, detail="Rate limit exceeded")
            
    else:
        if session:
            session_id = session["session_id"]
            allowed, retry_after = check_rate_limit(f"sess_general:{session_id}", 60, 60)
            if not allowed:
                raise HTTPException(status_code=429, headers={"Retry-After": str(retry_after)}, detail="Rate limit exceeded")

# Security Headers & Ban Filter Middleware
@app.middleware("http")
async def add_security_headers_and_rotation(request: Request, call_next):
    client_ip = request.client.host if request.client else ""
    if check_ip_ban(client_ip):
        return JSONResponse(
            status_code=403,
            content={"error": "Access temporarily suspended due to security rate limit breaches."}
        )
        
    response = await call_next(request)
    
    if hasattr(request.state, "rotated_secret"):
        response.headers["X-Session-Secret"] = request.state.rotated_secret
        
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com https://cdn.jsdelivr.net; "
        "img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; frame-ancestors 'none'"
    )
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response

# Legacy fallback handlers
def get_session(session_id: str):
    verify_session_id(session_id)
    if sessions_coll is not None:
        doc = sessions_coll.find_one({"session_id": session_id})
        return doc if doc else {"materiality": {}, "risk": {}}
    return {"materiality": {}, "risk": {}}

def update_session(session_id: str, data: dict):
    verify_session_id(session_id)
    if sessions_coll is not None:
        sessions_coll.update_one(
            {"session_id": session_id},
            {"$set": {**data, "last_updated": datetime.now(timezone.utc)}},
            upsert=True
        )

def log_audit_action(session_id: str, action: str, details: dict):
    verify_session_id(session_id)
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

@app.post("/api/session/create")
async def create_session(request: Request):
    client_ip = request.client.host if request.client else ""
    user_agent = request.headers.get("User-Agent", "")
    accept_lang = request.headers.get("Accept-Language", "")
    
    # Rate limit check for session creation (5/min per IP)
    await check_rate_limits(request)
    
    session_id = secrets.token_urlsafe(32)
    session_secret = secrets.token_urlsafe(32)
    secret_hash = hash_secret(session_secret)
    
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=24) # Absolute expiry: 24h
    
    session_doc = {
        "session_id": session_id,
        "session_secret_hash": secret_hash,
        "created_at": now,
        "last_activity_at": now,
        "expires_at": expires_at,
        "secret_created_at": now,
        "ip_subnet": get_ip_subnet(client_ip),
        "browser_fingerprint": hash_fingerprint(user_agent, accept_lang),
        "is_revoked": False,
        "materiality": {},
        "risk": {},
        "files": {}
    }
    
    if sessions_coll is not None:
        sessions_coll.insert_one(session_doc)
        
    log_audit_action(session_id, "CREATE_SESSION", {"client_ip": client_ip})
    
    # Set httpOnly cookie
    response = JSONResponse(content={"session_secret": session_secret})
    response.set_cookie(
        key="stataudit_session_id",
        value=session_id,
        httponly=True,
        secure=not os.getenv("TESTING") == "1",
        samesite="strict",
        path="/api"
    )
    return response

@app.post("/api/session/revoke")
async def revoke_session(session: dict = Depends(require_session)):
    session_id = session["session_id"]
    
    if sessions_coll is not None:
        sessions_coll.update_one({"session_id": session_id}, {"$set": {"is_revoked": True}})
        
    # Evict cache and files
    import shutil
    try:
        session_dir = get_session_dir(session_id)
        if os.path.exists(session_dir):
            shutil.rmtree(session_dir)
    except Exception as e:
        logger.error(f"Error evicting session directory for {session_id}: {e}")
        
    log_audit_action(session_id, "REVOKE_SESSION", {})
    
    response = JSONResponse(content={"status": "revoked"})
    response.delete_cookie("stataudit_session_id", path="/api")
    return response

@app.post("/api/materiality")
async def setup_materiality(
    value: float = Form(...),
    benchmark: str = Form("NPBT"),
    romm: str = Form(...),
    perf_pct: float = Form(75.0),
    trivial_pct: float = Form(3.0),
    overall_pct: Optional[float] = Form(None),
    session: dict = Depends(require_session)
):
    session_id = session["session_id"]
    try:
        # Validate ROMM
        if romm not in ["low", "medium", "high"]:
            raise HTTPException(status_code=400, detail="Invalid ROMM basis")
        # Validate numeric boundaries
        if value <= 0:
            raise HTTPException(status_code=400, detail="Turnover value must be positive")
        if not (50.0 <= perf_pct <= 100.0):
            raise HTTPException(status_code=400, detail="Performance materiality percentage must be between 50 and 100")
        if not (0.1 <= trivial_pct <= 10.0):
            raise HTTPException(status_code=400, detail="Trivial threshold percentage must be between 0.1 and 10")
        if overall_pct is not None and not (0.5 <= overall_pct <= 15.0):
            raise HTTPException(status_code=400, detail="Overall materiality percentage must be between 0.5 and 15")
            
        calc = MaterialityCalculator(value, benchmark, romm)
        res = calc.calculate(perf_pct, trivial_pct, explicit_overall_pct=overall_pct)
        
        if sessions_coll is not None:
            sessions_coll.update_one(
                {"session_id": session_id},
                {"$set": {"materiality": res}}
            )
        log_audit_action(session_id, "SETUP_MATERIALITY", {"value": value, "benchmark": benchmark})
        return res
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/risk-assessment")
async def setup_risk(
    turnover_250: bool = Form(...),
    ifc: bool = Form(...),
    governance: bool = Form(...),
    misstatements: bool = Form(...),
    session: dict = Depends(require_session)
):
    session_id = session["session_id"]
    try:
        engine = RiskAssessmentEngine(turnover_250, ifc, governance, misstatements)
        res = engine.assess()
        res.update({
            "turnover_250": turnover_250,
            "ifc": ifc,
            "governance": governance,
            "misstatements": misstatements
        })
        
        if sessions_coll is not None:
            sessions_coll.update_one(
                {"session_id": session_id},
                {"$set": {"risk": res}}
            )
        log_audit_action(session_id, "SETUP_RISK", res)
        return res
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/key-status")
async def check_api_key_status(session: dict = Depends(require_session)):
    try:
        status_data = await ai_engine.check_keys_status()
        return JSONResponse(status_data)
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/analyze")
async def analyze_ledger(
    file: UploadFile = File(...),
    category: str = Form(...),
    sample_pct: float = Form(20.0),
    sampling_basis: str = Form('count'),
    tod_pct: float = Form(70.0),
    target_count: Optional[int] = Form(None),
    audit_type: str = Form('large'),
    session: dict = Depends(require_session)
):
    session_id = session["session_id"]
    try:
        validate_uploaded_file(file)
        contents = await file.read()
        
        clean_name = sanitize_filename(file.filename)
        session_dir = get_session_dir(session_id)
        disk_path = os.path.join(session_dir, clean_name)
        with open(disk_path, "wb") as f:
            f.write(contents)
            
        file_id = None
        if fs is not None:
            existing = db.fs.files.find_one({"metadata.session_id": session_id, "metadata.type": "source_ledger"})
            if not existing:
                file_id = fs.put(contents, filename=clean_name, metadata={"session_id": session_id, "type": "source_ledger"})
            else:
                file_id = existing["_id"]

        ext = os.path.splitext(clean_name)[1].lower()
        df = load_ledger(contents, ext)

        trivial = session.get("materiality", {}).get("trivial_threshold", 0)
        perf_mat = session.get("materiality", {}).get("performance_materiality", 0)

        analyzer = AuditAnalyzer(df, category,
                                  trivial_threshold=trivial,
                                  performance_materiality=perf_mat)

        stats = analyzer.get_statistics()
        tod, toc = analyzer.generate_samples(
            sample_pct=sample_pct,
            sampling_basis=sampling_basis,
            tod_pct=tod_pct,
            target_count=target_count,
            audit_type=audit_type
        )
        risk_analysis = analyzer.get_risk_analysis()

        # Compute values
        amt_col = analyzer.amount_col
        tod_value = float(tod[amt_col].abs().sum()) if amt_col and len(tod) > 0 else 0
        toc_value = float(toc[amt_col].abs().sum()) if amt_col and len(toc) > 0 else 0

        # AI insights (non-blocking)
        ai_insights = await get_ai_insights(category, stats)

        # Dashboard JSON
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
            "filename": clean_name,
            "deficit_info": getattr(analyzer, "sampling_deficit", None)
        })
        
        log_audit_action(session_id, "RUN_ANALYSIS", {
            "category": category, "file": clean_name, "stats": stats,
            "tod_count": len(tod), "toc_count": len(toc),
            "gridfs_file_id": str(file_id) if file_id else None
        })
        
        return response

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"{type(e).__name__}: {str(e)}"})

@app.post("/api/download")
async def download_report(
    file: UploadFile = File(...),
    category: str = Form(...),
    sample_pct: float = Form(20.0),
    sampling_basis: str = Form('count'),
    tod_pct: float = Form(70.0),
    target_count: Optional[int] = Form(None),
    audit_type: str = Form('large'),
    session: dict = Depends(require_session)
):
    session_id = session["session_id"]
    try:
        validate_uploaded_file(file)
        contents = await file.read()
        
        clean_name = sanitize_filename(file.filename)
        ext = os.path.splitext(clean_name)[1].lower()
        df = load_ledger(contents, ext)

        trivial = session.get("materiality", {}).get("trivial_threshold", 0)
        perf_mat = session.get("materiality", {}).get("performance_materiality", 0)

        analyzer = AuditAnalyzer(df, category,
                                  trivial_threshold=trivial,
                                  performance_materiality=perf_mat)

        stats = analyzer.get_statistics()
        tod, toc = analyzer.generate_samples(
            sample_pct=sample_pct,
            sampling_basis=sampling_basis,
            tod_pct=tod_pct,
            target_count=target_count,
            audit_type=audit_type
        )
        risk_analysis = analyzer.get_risk_analysis()

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
            sampling_config=sampling_config,
            deficit_info=getattr(analyzer, "sampling_deficit", None)
        )
        report.add_engagement_data(
            session.get("materiality", {}),
            session.get("risk", {})
        )
        output = report.generate(vouching_results=vouching_results, report_type='sampling')
        output.seek(0)
        
        # GridFS Storage
        wp_file_id = None
        if fs is not None:
            try:
                wp_filename = f"Audit_Working_Papers_{category}_{int(sample_pct)}pct.xlsx".replace(" ", "_")
                wp_file_id = fs.put(output.read(), filename=wp_filename, metadata={"session_id": session_id, "type": "generated_report"})
                output.seek(0)
            except Exception as e:
                print(f"!!! GridFS Error during report save: {e}")

        clean_category = re.sub(r'[^a-zA-Z0-9]', '_', category)
        final_filename = f"StatAudit_Working_Papers_{clean_category}_{int(sample_pct)}pct.xlsx"

        # Save generated file in per-session local data directory
        session_dir = get_session_dir(session_id)
        local_report_path = os.path.join(session_dir, final_filename)
        with open(local_report_path, "wb") as lf:
            lf.write(output.read())
        output.seek(0)

        log_audit_action(session_id, "DOWNLOAD_REPORT", {
            "category": category, "file": clean_name,
            "gridfs_report_id": str(wp_file_id) if wp_file_id else None
        })

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{final_filename}"'}
        )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/vouch")
async def vouch_invoice(
    file: UploadFile = File(...),
    session: dict = Depends(require_session)
):
    session_id = session["session_id"]
    try:
        validate_uploaded_file(file)
        contents = await file.read()
        
        clean_name = sanitize_filename(file.filename)
        session_dir = get_session_dir(session_id)
        disk_path = os.path.join(session_dir, clean_name)
        with open(disk_path, "wb") as f:
            f.write(contents)
        
        file_id = None
        if fs is not None:
            file_id = fs.put(contents, filename=clean_name, metadata={"session_id": session_id, "type": "voucher_upload"})

        ext = os.path.splitext(clean_name)[1].lower()
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

        if not extracted_data:
            extracted_data = [{"field": "Extraction Status", "value": "AI parsing failed"}]
        else:
            # 3. TRANSACTION-VOUCHER BINDING (Forensic Match)
            match_status = "Not Found in Ledger"
            match_row = None
            
            try:
                data_map = {item['field']: str(item['value']).strip() for item in extracted_data}
                inv_no = data_map.get("Invoice Number") or data_map.get("Invoice No") or ""
                raw_amt = data_map.get("Grand Total") or data_map.get("Total Amount") or "0"
                
                amt_str = re.sub(r'[^\d\.]', '', raw_amt)
                clean_amt = float(amt_str) if amt_str else 0.0

                # Load Ledger from GridFS
                if fs is not None:
                    ledger_cursor = fs.find({"metadata.session_id": session_id, "type": "ledger_upload"}).sort("uploadDate", -1).limit(1)
                    ledger_files = list(ledger_cursor)
                    if ledger_files:
                        ledger_data = fs.get(ledger_files[0]._id).read()
                        ledger_df = pd.read_excel(io.BytesIO(ledger_data)) if ledger_files[0].filename.endswith('xlsx') else pd.read_csv(io.BytesIO(ledger_data))
                        
                        # Fuzzy Match Amount first
                        if clean_amt > 0:
                            num_cols = ledger_df.select_dtypes(include=[np.number]).columns
                            for col in num_cols:
                                match = ledger_df[np.isclose(ledger_df[col].abs(), clean_amt, atol=1.0)]
                                if not match.empty:
                                    match_row = match.iloc[0].to_dict()
                                    match_status = "✅ MATCHED"
                                    break
                        
                        # If amount matched, try to verify invoice number if available
                        if match_row and inv_no:
                            inv_found = False
                            for val in match_row.values():
                                if inv_no in str(val):
                                    inv_found = True
                                    break
                            if not inv_found:
                                match_status = "⚠️ AMOUNT MATCHED (Invoice No Mismatch)"
                
                extracted_data.append({"field": "Match Status", "value": match_status})
                if match_row:
                    extracted_data.append({"field": "Ledger Bind", "value": f"Row Matched by Value ({clean_amt})"})
            except Exception as e:
                print(f"[VOUCH] Binding error: {e}")
                extracted_data.append({"field": "Audit Error", "value": "Reconciliation failed"})

        # Store vouching results in MongoDB for persistence and Excel reporting
        if db is not None:
            try:
                vouch_results_coll = db["vouching_results"]
                vouch_results_coll.update_one(
                    {"session_id": session_id, "filename": clean_name},
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
            "file": clean_name,
            "model_used": model_used,
            "gridfs_voucher_id": str(file_id) if file_id else None
        })

        return {"status": "success", "data": extracted_data, "model_used": model_used}
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/download/vouching")
async def download_vouching_report(session: dict = Depends(require_session)):
    session_id = session["session_id"]
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
        
        output = report.generate(vouching_results=results, report_type='vouching')
        
        # Save generated report locally in per-session folder
        session_dir = get_session_dir(session_id)
        local_vouch_report = os.path.join(session_dir, "Vouching_Reconciliation_Report.xlsx")
        with open(local_vouch_report, "wb") as lf:
            lf.write(output.read())
        output.seek(0)

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=Vouching_Reconciliation_Report.xlsx"}
        )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/vouch/history")
async def get_vouch_history(session: dict = Depends(require_session)):
    session_id = session["session_id"]
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
    transaction: str = Form(...),
    category: str = Form("Sales"),
    session: dict = Depends(require_session)
):
    session_id = session["session_id"]
    try:
        txn_data = json.loads(transaction)
        
        # Reject dictionary structures inside transaction parameters to prevent NoSQL injection
        for k, v in txn_data.items():
            if isinstance(v, dict):
                raise HTTPException(status_code=422, detail="Invalid parameter structure inside transaction payload")

        result = await ai_engine.deep_audit_remark(txn_data, category)
        
        log_audit_action(session_id, "DEEP_AUDIT", {
            "category": category,
            "risk_level": result.get("risk_level", "Unknown"),
            "consensus": result.get("consensus", False)
        })
        
        return {"status": "success", "data": result}
    except HTTPException as he:
        raise he
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
