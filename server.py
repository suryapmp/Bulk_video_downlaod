import os
import ast
import aiohttp
import asyncio
import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

TASKS = []
clients = set()
MAX_CONCURRENT = 10

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except Exception:
        clients.discard(ws)

async def broadcast(msg: dict):
    for ws in list(clients):
        try:
            await ws.send_json(msg)
        except Exception:
            clients.discard(ws)

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
    required = {"program_code", "course_name", "link", "roll_no"}
    if not required.issubset(set(df.columns)):
        return JSONResponse({"error": f"Excel must contain {required}"}, status_code=400)

    for _, row in df.iterrows():
        program = str(row["program_code"]).strip()
        course = str(row["course_name"]).strip()
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

        for i, u in enumerate(urls, start=1):
            TASKS.append({
                "program": program,
                "course": course,
                "roll": roll,
                "url": u,
                "index": i
            })
    if not TASKS:
        return JSONResponse({"error": "No valid links found"}, status_code=400)
    return {"message": "Excel parsed successfully", "total": len(TASKS)}

@app.post("/start_downloads")
async def start_downloads(path: str = Form(...)):
    global TASKS
    if not TASKS:
        return JSONResponse({"error": "No tasks found"}, status_code=400)
    path = os.path.expanduser(path.strip())
    os.makedirs(path, exist_ok=True)
    asyncio.create_task(download_all(TASKS.copy(), path))
    return {"message": f"Downloads started in: {path}", "total": len(TASKS)}

async def download_one(session, sem, task, base_path):
    async with sem:
        program, course, roll, url, idx = task.values()
        folder = os.path.join(base_path, program, course)
        os.makedirs(folder, exist_ok=True)
        filename = f"{roll}_{idx}.mp4"
        filepath = os.path.join(folder, filename)

        await broadcast({
            "roll": roll, "program": program, "course": course,
            "status": "Starting", "progress": 0, "speed": "-", "size": "-"
        })

        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=None)) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}")
                total = int(resp.headers.get("content-length", 0))
                downloaded = 0
                start_time = asyncio.get_event_loop().time()
                with open(filepath, "wb") as f:
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        elapsed = asyncio.get_event_loop().time() - start_time
                        speed = f"{(downloaded/1024)/elapsed:.1f} KB/s" if elapsed > 0 else "-"
                        progress = int(downloaded * 100 / total) if total else 0
                        await broadcast({
                            "roll": roll, "program": program, "course": course,
                            "status": "Downloading", "progress": progress,
                            "speed": speed, "size": f"{total/(1024*1024):.2f} MB" if total else "-"
                        })
            await broadcast({
                "roll": roll, "program": program, "course": course,
                "status": "Completed", "progress": 100,
                "speed": "Done", "size": f"{os.path.getsize(filepath)/(1024*1024):.2f} MB"
            })
        except Exception as e:
            await broadcast({
                "roll": roll, "program": program, "course": course,
                "status": f"Failed: {e}", "progress": 0, "speed": "-", "size": "-"
            })

async def download_all(tasks, base_path):
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*(download_one(session, sem, t, base_path) for t in tasks))
    await broadcast({"status": "All downloads finished"})
