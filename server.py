import os
import ast
import aiohttp
import asyncio
import pandas as pd
import re
from fastapi import FastAPI, UploadFile, File, Form, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

# ---------- Configuration ----------
APP_TITLE = "Bulk Video Downloader"
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
MAX_CONCURRENT_DEFAULT = 6

app = FastAPI(title=APP_TITLE)
app.mount("/downloads", StaticFiles(directory=DOWNLOAD_DIR), name="downloads")
templates = Jinja2Templates(directory="templates")

TASKS = []
clients = set()
total_downloaded_bytes = 0
CURRENT_BASE_PATH = None


# ---------- Helper ----------
def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name)


async def broadcast(msg: dict):
    for ws in list(clients):
        try:
            await ws.send_json(msg)
        except Exception:
            clients.discard(ws)


# ---------- WebSocket ----------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except Exception:
        clients.discard(ws)


# ---------- Routes ----------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    global TASKS
    TASKS = []
    try:
        df = pd.read_excel(file.file, engine="openpyxl")
    except Exception as e:
        return JSONResponse({"error": f"Failed to read Excel: {e}"}, status_code=400)

    df.columns = [c.strip().lower() for c in df.columns]
    required = {"program_code", "course_name", "exam_date", "link", "roll_no"}
    if not required.issubset(set(df.columns)):
        return JSONResponse({"error": f"Excel must contain columns: {required}"}, status_code=400)

    for _, row in df.iterrows():
        program = str(row["program_code"]).strip()
        course = str(row["course_name"]).strip().replace("/", "_")
        exam_date = str(row["exam_date"]).strip()
        roll = str(row["roll_no"]).strip()
        raw = str(row["link"]).strip()

        urls = []
        try:
            clean = raw.replace("\n", "").replace("\r", "").strip()
            if clean.startswith("[") and clean.endswith("]"):
                parsed = ast.literal_eval(clean)
                if isinstance(parsed, list):
                    urls = [u.strip() for u in parsed if isinstance(u, str) and u.startswith("http")]
            elif "http" in clean:
                urls = [p.strip().strip('"').strip("'") for p in clean.split(",") if "http" in p]
        except Exception:
            urls = [p.strip().strip('"').strip("'") for p in raw.split(",") if "http" in p]

        for u in urls:
            TASKS.append({"program": program, "course": course, "exam_date": exam_date, "roll": roll, "url": u})

    if not TASKS:
        return JSONResponse({"error": "No valid video links found"}, status_code=400)

    return {"message": "Excel parsed successfully", "total": len(TASKS)}


@app.post("/start_downloads")
async def start_downloads(folder: str = Form(...), concurrency: int = Form(None)):
    global CURRENT_BASE_PATH
    if not TASKS:
        return JSONResponse({"error": "No tasks found. Upload Excel first."}, status_code=400)

    folder = folder.strip()
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)
    CURRENT_BASE_PATH = folder

    concurrency_value = concurrency if concurrency and int(concurrency) > 0 else MAX_CONCURRENT_DEFAULT
    asyncio.create_task(download_all(TASKS.copy(), folder, concurrency_value))
    return {"message": f"Downloads started in: {folder}", "total": len(TASKS)}


@app.get("/status")
async def status():
    base_path = CURRENT_BASE_PATH if CURRENT_BASE_PATH else DOWNLOAD_DIR
    completed = []
    total_bytes = 0
    for root, _, files in os.walk(base_path):
        for f in files:
            if f.lower().endswith(".mp4"):
                full = os.path.join(root, f)
                size = os.path.getsize(full)
                total_bytes += size
                rel = os.path.relpath(full, DOWNLOAD_DIR).replace("\\", "/")
                completed.append({"file": f, "preview": f"/downloads/{rel}", "size_bytes": size})
    total_gb = round(total_bytes / (1024 ** 3), 2)
    return {"completed": completed, "count": len(completed), "total_gb": total_gb}


# ---------- Download Logic ----------
async def download_one(session: aiohttp.ClientSession, task: dict, base_path: str, total_videos: int, semaphore: asyncio.Semaphore):
    global total_downloaded_bytes

    roll = task["roll"]
    program = sanitize_filename(task["program"])
    course = sanitize_filename(task["course"])
    exam_date = sanitize_filename(task["exam_date"])
    url = task["url"]

    course_path = os.path.join(base_path, program, course, exam_date)
    os.makedirs(course_path, exist_ok=True)
    filename = f"{roll}.mp4"
    filepath = os.path.join(course_path, filename)

    rel_path = os.path.relpath(filepath, DOWNLOAD_DIR).replace("\\", "/")
    download_url = f"/downloads/{rel_path}"

    headers = {}
    mode = "wb"
    downloaded = 0

    if os.path.exists(filepath):
        downloaded = os.path.getsize(filepath)
        if downloaded > 0:
            headers = {"Range": f"bytes={downloaded}-"}
            mode = "ab"

    async with semaphore:
        await broadcast({"roll": roll, "program": program, "course": course, "status": "Starting", "progress": 0})

        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=None)) as resp:
                resp.raise_for_status()
                total_size = int(resp.headers.get("content-length", 0)) + downloaded
                chunk_size = 64 * 1024
                start = asyncio.get_event_loop().time()

                with open(filepath, mode) as f:
                    async for chunk in resp.content.iter_chunked(chunk_size):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        total_downloaded_bytes += len(chunk)

                        elapsed = asyncio.get_event_loop().time() - start
                        speed = f"{(downloaded / 1024) / (elapsed if elapsed > 0 else 1):.1f} KB/s"
                        progress = int(downloaded * 100 / total_size) if total_size else 0
                        readable_size = f"{downloaded / (1024 ** 2):.2f} MB"

                        await broadcast({
                            "roll": roll, "program": program, "course": course,
                            "status": "Downloading", "progress": progress,
                            "speed": speed, "size": readable_size,
                            "total_gb": round(total_downloaded_bytes / (1024 ** 3), 2)
                        })

            final_size = os.path.getsize(filepath)
            await broadcast({
                "roll": roll, "program": program, "course": course,
                "status": "✅ Completed", "progress": 100,
                "speed": "-", "size": f"{final_size / (1024 ** 2):.2f} MB",
                "download_url": download_url,
                "total_gb": round(total_downloaded_bytes / (1024 ** 3), 2)
            })

        except Exception as e:
            await broadcast({"roll": roll, "program": program, "course": course, "status": f"❌ Failed: {e}", "progress": 0})


async def download_all(tasks: list, base_path: str, concurrency_value: int):
    global total_downloaded_bytes
    total_downloaded_bytes = 0
    semaphore = asyncio.Semaphore(concurrency_value)
    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*(download_one(session, t, base_path, len(tasks), semaphore) for t in tasks))

    await broadcast({"status": "🎉 All downloads finished", "type": "done", "total": len(tasks)})

