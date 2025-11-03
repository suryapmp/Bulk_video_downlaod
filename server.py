# server.py
import os
import ast
import aiohttp
import asyncio
import pandas as pd
import re
import datetime
import time
from urllib.parse import quote, unquote
from typing import List, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

# ---------- Configuration ----------
APP_TITLE = "Bulk Video Downloader"
DOWNLOAD_DIR = "downloads"        # internal downloads dir for preview fallback
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# default concurrency if user doesn't provide one
MAX_CONCURRENT_DEFAULT = 6

# ---------- FastAPI Setup ----------
app = FastAPI(title=APP_TITLE)
app.mount("/downloads", StaticFiles(directory=DOWNLOAD_DIR), name="downloads")
templates = Jinja2Templates(directory="templates")

# ---------- Globals ----------
TASKS: List[Dict[str, Any]] = []   # each: {program, course, roll, url, exam_date}
clients = set()                    # ws clients
total_downloaded_bytes = 0         # total bytes downloaded this session (updated live)
CURRENT_BASE_PATH: str = ""        # user selected base path for storage (absolute)

# ---------- Helpers ----------
def sanitize_filename(name: str) -> str:
    if name is None:
        return ""
    name = str(name)
    # remove unsafe chars, replace slashes with hyphen
    return re.sub(r'[<>:"/\\|?*\n\r]+', "_", name).strip()

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

async def broadcast(msg: dict):
    """Send JSON message to all connected websocket clients."""
    for ws in list(clients):
        try:
            await ws.send_json(msg)
        except Exception:
            clients.discard(ws)

# ---------- WebSocket ----------
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            # keep socket alive; client may send pings
            await ws.receive_text()
    except Exception:
        clients.discard(ws)

# ---------- Routes ----------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    """
    Parse Excel and populate TASKS.
    Required columns (case-insensitive): program_code, course_name, link, roll_no, exam_date
    Returns parsed 'tasks' list for UI population.
    """
    global TASKS
    TASKS = []
    try:
        df = pd.read_excel(file.file, engine="openpyxl")
    except Exception as e:
        return JSONResponse({"error": f"Failed to read Excel: {e}"}, status_code=400)

    # normalize column names
    df.columns = [c.strip().lower() for c in df.columns]

    required = {"program_code", "course_name", "link", "roll_no", "exam_date"}
    if not required.issubset(set(df.columns)):
        return JSONResponse({"error": f"Excel must contain columns: {required}"}, status_code=400)

    rows_for_ui = []
    for _, row in df.iterrows():
        program = str(row["program_code"]).strip()
        course = str(row["course_name"]).strip()
        roll = str(row["roll_no"]).strip()
        # parse exam_date robustly
        exam_raw = row["exam_date"]
        if pd.isna(exam_raw):
            exam_date = "unknown_date"
        else:
            try:
                # if it's datetime-like, format as YYYY-MM-DD
                if isinstance(exam_raw, (pd.Timestamp, datetime.datetime, datetime.date)):
                    d = pd.to_datetime(exam_raw)
                    exam_date = d.strftime("%Y-%m-%d")
                else:
                    exam_date = str(exam_raw).strip().replace("/", "-").replace(" ", "_")
            except Exception:
                exam_date = str(exam_raw).strip().replace("/", "-").replace(" ", "_")

        raw_link = str(row["link"]).strip()

        # normalize link list — support JSON style list or comma-separated
        urls = []
        try:
            clean = raw_link.replace("\n", "").replace("\r", "").strip()
            if clean.startswith("[") and clean.endswith("]"):
                parsed = ast.literal_eval(clean)
                if isinstance(parsed, list):
                    urls = [u.strip() for u in parsed if isinstance(u, str) and u.startswith("http")]
            elif "http" in clean:
                urls = [p.strip().strip('"').strip("'") for p in clean.split(",") if "http" in p]
        except Exception:
            urls = [p.strip().strip('"').strip("'") for p in raw_link.split(",") if "http" in p]

        for u in urls:
            task = {
                "program": program,
                "course": course,
                "roll": roll,
                "url": u,
                "exam_date": exam_date
            }
            TASKS.append(task)
            rows_for_ui.append({"program": program, "course": course, "roll": roll, "exam_date": exam_date})

    if not TASKS:
        return JSONResponse({"error": "No valid video links found"}, status_code=400)

    return {"message": "Excel parsed successfully", "total": len(TASKS), "tasks": rows_for_ui}

@app.post("/start_downloads")
async def start_downloads(folder: str = Form(...), concurrency: int = Form(None)):
    """
    Start downloads. 'folder' is user-selected absolute path (or relative).
    concurrency: optional number (defaults to MAX_CONCURRENT_DEFAULT)
    """
    global CURRENT_BASE_PATH
    if not TASKS:
        return JSONResponse({"error": "No tasks found. Upload Excel first."}, status_code=400)

    # accept absolute or relative; expanduser
    folder = str(folder).strip()
    if not folder:
        return JSONResponse({"error": "Provide a folder path to store videos."}, status_code=400)

    # convert to absolute
    folder_abs = os.path.abspath(os.path.expanduser(folder))
    ensure_dir(folder_abs)
    CURRENT_BASE_PATH = folder_abs

    concurrency_value = int(concurrency) if concurrency and int(concurrency) > 0 else MAX_CONCURRENT_DEFAULT

    # start background downloads (skips already-completed files)
    asyncio.create_task(download_all(TASKS.copy(), CURRENT_BASE_PATH, concurrency_value))
    return {"message": f"Downloads started in: {CURRENT_BASE_PATH}", "total": len(TASKS), "folder": CURRENT_BASE_PATH, "concurrency": concurrency_value}

@app.get("/status")
async def status():
    """
    Return completed mp4 files from CURRENT_BASE_PATH (if set) otherwise from DOWNLOAD_DIR.
    Also return total_gb aggregated across CURRENT_BASE_PATH (if set) and DOWNLOAD_DIR.
    """
    root_paths = []
    if CURRENT_BASE_PATH:
        root_paths.append(CURRENT_BASE_PATH)
    root_paths.append(DOWNLOAD_DIR)

    completed = []
    total_bytes = 0
    seen = set()
    for root in root_paths:
        if not os.path.exists(root):
            continue
        for r, _, files in os.walk(root):
            for f in files:
                if f.lower().endswith(".mp4"):
                    full = os.path.join(r, f)
                    if full in seen:
                        continue
                    seen.add(full)
                    size = os.path.getsize(full)
                    total_bytes += size
                    # preview link for UI -> use /preview?fp=<quoted absolute path>
                    preview = "/preview?fp=" + quote(full)
                    completed.append({"file": f, "preview": preview, "size_bytes": size, "path": full})
    total_gb = round(total_bytes / (1024 ** 3), 2)
    return {"completed": completed, "count": len(completed), "total_gb": total_gb}

@app.get("/preview")
def preview(fp: str):
    """
    Serve a requested file path. fp is a quoted absolute path.
    For safety, we only serve files inside CURRENT_BASE_PATH or DOWNLOAD_DIR.
    """
    try:
        fp_un = unquote(fp)
    except Exception:
        return JSONResponse({"error": "Invalid path"}, status_code=400)

    if not os.path.exists(fp_un):
        return JSONResponse({"error": "File not found"}, status_code=404)

    allowed_roots = [os.path.abspath(DOWNLOAD_DIR)]
    if CURRENT_BASE_PATH:
        allowed_roots.append(os.path.abspath(CURRENT_BASE_PATH))

    # ensure file is inside allowed roots
    fp_abs = os.path.abspath(fp_un)
    allowed = False
    for root in allowed_roots:
        try:
            if os.path.commonpath([fp_abs, root]) == root:
                allowed = True
                break
        except Exception:
            continue

    if not allowed:
        return JSONResponse({"error": "Access denied"}, status_code=403)

    # Return the file directly
    return FileResponse(fp_abs, media_type="video/mp4", filename=os.path.basename(fp_abs))

# ---------- Download logic ----------
async def download_one(session: aiohttp.ClientSession, task: Dict[str, Any], base_path: str,
                       total_videos: int, semaphore: asyncio.Semaphore):
    """
    Download a single video with resume support and live broadcasts.
    Folder structure:
        <base_path>/<Program>/<Course>/<ExamDate>/<RollNo>.mp4
    """
    global total_downloaded_bytes

    roll = task["roll"]
    program = sanitize_filename(task["program"])
    course = sanitize_filename(task["course"])
    exam_date = sanitize_filename(task.get("exam_date", "unknown_date"))
    url = task["url"]

    # build folder structure
    dest_dir = os.path.join(base_path, program, course, exam_date)
    ensure_dir(dest_dir)

    filename = f"{sanitize_filename(roll)}.mp4"
    filepath = os.path.join(dest_dir, filename)

    # preview url -> /preview?fp=<quoted absolute path>
    preview_url = "/preview?fp=" + quote(os.path.abspath(filepath))

    headers = {}
    mode = "wb"
    downloaded = 0

    # if file exists, assume resume/skip
    if os.path.exists(filepath):
        downloaded = os.path.getsize(filepath)
        if downloaded > 0:
            headers = {"Range": f"bytes={downloaded}-"}
            mode = "ab"

    # notify UI that this task is starting (immediate preview available)
    await broadcast({
        "roll": roll, "program": program, "course": course, "exam_date": exam_date,
        "status": "Starting", "progress": int(100 if downloaded and not mode == "ab" else 0),
        "speed": "-", "size": f"{downloaded / (1024 ** 2):.2f} MB" if downloaded else "-",
        "preview": preview_url, "total": total_videos, "total_gb": round(total_downloaded_bytes / (1024 ** 3), 2)
    })

    async with semaphore:
        try:
            # get with provided range header if resuming
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=None)) as resp:
                resp.raise_for_status()

                # content-length is size of remaining chunk (if Range was used)
                content_len = int(resp.headers.get("content-length") or 0)
                # If content-range present, try to compute full total
                total_size = downloaded + content_len if content_len else 0

                chunk_size = 64 * 1024
                start_time = time.time()

                # write chunks
                with open(filepath, mode) as f:
                    async for chunk in resp.content.iter_chunked(chunk_size):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        total_downloaded_bytes += len(chunk)

                        elapsed = time.time() - start_time
                        speed = f"{(downloaded / 1024) / (elapsed if elapsed > 0 else 1):.1f} KB/s"
                        progress = int(downloaded * 100 / total_size) if total_size else 0
                        readable_size = f"{downloaded / (1024 ** 2):.2f} MB"

                        await broadcast({
                            "roll": roll, "program": program, "course": course, "exam_date": exam_date,
                            "status": "Downloading", "progress": progress,
                            "speed": speed, "size": readable_size,
                            "preview": preview_url, "total": total_videos,
                            "total_gb": round(total_downloaded_bytes / (1024 ** 3), 2)
                        })

            # final status
            final_size = os.path.getsize(filepath)
            await broadcast({
                "roll": roll, "program": program, "course": course, "exam_date": exam_date,
                "status": "Completed", "progress": 100,
                "speed": "-", "size": f"{final_size / (1024 ** 2):.2f} MB",
                "preview": preview_url, "total": total_videos,
                "total_gb": round(total_downloaded_bytes / (1024 ** 3), 2)
            })

        except Exception as e:
            await broadcast({
                "roll": roll, "program": program, "course": course, "exam_date": exam_date,
                "status": f"Failed: {e}", "progress": 0,
                "speed": "-", "size": "-",
                "preview": preview_url, "total": total_videos,
                "total_gb": round(total_downloaded_bytes / (1024 ** 3), 2)
            })

async def download_all(tasks: List[Dict[str, Any]], base_path: str, concurrency_value: int):
    """
    Run downloads concurrently (semaphore-limited).
    Skips already completed files (file exists and size > 0) — UI will show Completed for skipped ones.
    """
    global total_downloaded_bytes
    total_downloaded_bytes = 0
    total_videos = len(tasks)

    # sum existing bytes already saved in the base_path (so total_gb reflects storage)
    for root, _, files in os.walk(base_path):
        for f in files:
            if f.lower().endswith(".mp4"):
                try:
                    total_downloaded_bytes += os.path.getsize(os.path.join(root, f))
                except Exception:
                    pass

    semaphore = asyncio.Semaphore(concurrency_value if concurrency_value and concurrency_value > 0 else MAX_CONCURRENT_DEFAULT)

    async with aiohttp.ClientSession() as session:
        # prepare tasks: we will still call download_one for each task; that function will skip/append as required
        await asyncio.gather(*(download_one(session, t, base_path, total_videos, semaphore) for t in tasks))

    # final broadcast summary
    await broadcast({
        "status": "🎉 All downloads finished",
        "type": "done",
        "total": total_videos,
        "total_gb": round(total_downloaded_bytes / (1024 ** 3), 2)
    })
