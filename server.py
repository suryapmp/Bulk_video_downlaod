import os
import ast
import aiohttp
import asyncio
import pandas as pd
from fastapi import FastAPI, UploadFile, File, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

# --------------------------------------------------------------------
# CONFIGURATION
# --------------------------------------------------------------------
BASE_DIR = "videos"
os.makedirs(BASE_DIR, exist_ok=True)

MAX_CONCURRENT_DOWNLOADS = 10  # 🔹 limit 10 downloads at a time

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

clients = set()  # Active websocket connections


# --------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except:
        clients.remove(ws)


async def broadcast(data: dict):
    for ws in list(clients):
        try:
            await ws.send_json(data)
        except:
            clients.remove(ws)


@app.post("/upload")
async def upload_excel(file: UploadFile = File(...)):
    try:
        df = pd.read_excel(file.file)
    except Exception as e:
        return JSONResponse({"error": f"Invalid Excel file: {e}"}, status_code=400)

    df.columns = [c.strip().lower() for c in df.columns]
    required_cols = {"program_code", "course_name", "link", "roll_no"}

    if not required_cols.issubset(df.columns):
        return JSONResponse(
            {"error": f"Excel must contain columns: {required_cols}"}, status_code=400
        )

    tasks = []
    for _, row in df.iterrows():
        program = str(row["program_code"]).strip()
        course = str(row["course_name"]).strip()
        roll = str(row["roll_no"]).strip()
        raw_link = str(row["link"]).strip()

        urls = []
        try:
            if raw_link.startswith("[") and raw_link.endswith("]"):
                parsed = ast.literal_eval(raw_link)
                if isinstance(parsed, list):
                    urls = [u.strip() for u in parsed if isinstance(u, str) and u.startswith("http")]
            elif raw_link.startswith("http"):
                urls = [raw_link]
        except Exception:
            urls = [part.strip().strip('"').strip("'") for part in raw_link.split(",") if "http" in part]

        for i, url in enumerate(urls, start=1):
            tasks.append((program, course, roll, url, i))

    if not tasks:
        return JSONResponse({"error": "No valid video links found."}, status_code=400)

    asyncio.create_task(batch_downloads(tasks))
    return {"message": "Downloads started successfully!"}


# --------------------------------------------------------------------
# DOWNLOAD LOGIC
# --------------------------------------------------------------------
async def download_video(session, sem, program, course, roll_no, url, index):
    async with sem:
        folder = os.path.join(BASE_DIR, program, course)
        os.makedirs(folder, exist_ok=True)
        filename = os.path.join(folder, f"{roll_no}_{index}.mp4")

        await broadcast({
            "roll_no": roll_no,
            "program": program,
            "course": course,
            "status": "⏳ Starting...",
            "progress": 0,
            "speed": "-",
            "size": "-"
        })

        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}")

                total = int(resp.headers.get("content-length", 0))
                total_mb = f"{total / (1024 * 1024):.2f} MB" if total else "-"
                downloaded = 0
                start_time = asyncio.get_event_loop().time()

                with open(filename, "wb") as f:
                    async for chunk in resp.content.iter_chunked(1024 * 64):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        elapsed = asyncio.get_event_loop().time() - start_time
                        speed = f"{(downloaded / 1024) / elapsed:.1f} KB/s" if elapsed > 0 else "-"
                        progress = int(downloaded * 100 / total) if total else 0

                        await broadcast({
                            "roll_no": roll_no,
                            "program": program,
                            "course": course,
                            "status": "⬇️ Downloading...",
                            "progress": progress,
                            "speed": speed,
                            "size": total_mb
                        })

            await broadcast({
                "roll_no": roll_no,
                "program": program,
                "course": course,
                "status": "✅ Completed",
                "progress": 100,
                "speed": "Done",
                "size": total_mb
            })

        except Exception as e:
            await broadcast({
                "roll_no": roll_no,
                "program": program,
                "course": course,
                "status": f"❌ Failed: {e}",
                "progress": 0,
                "speed": "-",
                "size": "-"
            })


async def batch_downloads(tasks):
    """Download videos in batches of 10 concurrently"""
    sem = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
    async with aiohttp.ClientSession() as session:
        download_coros = [
            download_video(session, sem, program, course, roll_no, url, index)
            for program, course, roll_no, url, index in tasks
        ]
        await asyncio.gather(*download_coros)
