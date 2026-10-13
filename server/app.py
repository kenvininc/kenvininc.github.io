"""Facebook video downloader API (FastAPI + yt-dlp).

Nhận link Facebook, tải video bằng yt-dlp và trả file .mp4 về cho client
(web trên kenvin.me hoặc iOS Shortcut).
"""

import asyncio
import hmac
import logging
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

API_KEY = os.environ.get("API_KEY", "")
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "https://kenvin.me").split(",") if o.strip()]
COOKIES_FILE = os.environ.get("COOKIES_FILE", "/data/cookies.txt")
MAX_FILESIZE_MB = int(os.environ.get("MAX_FILESIZE_MB", "500"))
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "2"))
DOWNLOAD_TIMEOUT = int(os.environ.get("DOWNLOAD_TIMEOUT", "300"))

# Chỉ nhận link Facebook để yt-dlp không bị dùng làm downloader cho URL bất kỳ.
ALLOWED_HOSTS = ("facebook.com", "fb.watch", "fb.com")

# Ưu tiên H.264 + AAC trong mp4 để Photos trên iPhone mở được.
FORMAT = "bv*[vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4][vcodec^=avc1]/b[ext=mp4]/bv*+ba/b"

log = logging.getLogger("fbdl")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

if not API_KEY:
    raise RuntimeError("API_KEY chưa được set")

app = FastAPI(title="fb-download", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
    expose_headers=["Content-Disposition"],
)

semaphore = asyncio.Semaphore(MAX_CONCURRENT)


class DownloadRequest(BaseModel):
    url: str


def check_key(key: str | None) -> None:
    if not key or not hmac.compare_digest(key.encode(), API_KEY.encode()):
        raise HTTPException(status_code=401, detail="Sai API key")


def check_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not any(
        host == h or host.endswith("." + h) for h in ALLOWED_HOSTS
    ):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ link Facebook")
    return url


def run_ytdlp(url: str, workdir: str) -> Path:
    opts = {
        "format": FORMAT,
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(workdir, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": MAX_FILESIZE_MB * 1024 * 1024,
        "socket_timeout": 30,
    }
    if os.path.isfile(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(url, download=True)
    files = [p for p in Path(workdir).iterdir() if p.is_file() and p.suffix in (".mp4", ".mov", ".m4v")]
    if not files:
        raise RuntimeError("yt-dlp không tạo ra file video")
    return max(files, key=lambda p: p.stat().st_size)


async def handle(url: str, key: str | None) -> FileResponse:
    check_key(key)
    url = check_url(url)
    workdir = tempfile.mkdtemp(prefix="fbdl-")
    cleanup = BackgroundTask(shutil.rmtree, workdir, ignore_errors=True)
    try:
        async with semaphore:
            log.info("download %s", url)
            path = await asyncio.wait_for(asyncio.to_thread(run_ytdlp, url, workdir), DOWNLOAD_TIMEOUT)
    except asyncio.TimeoutError:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=504, detail="Tải quá lâu, đã huỷ")
    except yt_dlp.utils.DownloadError as e:
        shutil.rmtree(workdir, ignore_errors=True)
        log.warning("yt-dlp error: %s", e)
        raise HTTPException(status_code=422, detail=f"Không tải được: {e}")
    except Exception as e:
        shutil.rmtree(workdir, ignore_errors=True)
        log.exception("unexpected error")
        raise HTTPException(status_code=500, detail=str(e))
    return FileResponse(path, media_type="video/mp4", filename=path.name, background=cleanup)


@app.get("/api/health")
def health():
    return {"ok": True, "yt_dlp": yt_dlp.version.__version__}


@app.post("/api/download")
async def download_post(req: DownloadRequest, x_api_key: str | None = Header(default=None)):
    return await handle(req.url, x_api_key)


@app.get("/api/download")
async def download_get(url: str = Query(...), x_api_key: str | None = Header(default=None)):
    return await handle(url, x_api_key)
