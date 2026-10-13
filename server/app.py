"""Facebook video downloader API (FastAPI + yt-dlp).

Nhận link Facebook, tải video bằng yt-dlp và trả file .mp4 về cho client
(web serve ở "/" hoặc iOS Shortcut).
"""

import asyncio
import hmac
import logging
import os
import shutil
import tempfile
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

API_KEY = os.environ.get("API_KEY", "").strip()  # .env sửa trên Windows có thể dính \r
# Web serve cùng domain nên không cần CORS. Chỉ set khi gọi API từ domain khác.
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
COOKIES_FILE = os.environ.get("COOKIES_FILE", "/data/cookies.txt")
MAX_FILESIZE_MB = int(os.environ.get("MAX_FILESIZE_MB", "500"))
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "2"))
DOWNLOAD_TIMEOUT = int(os.environ.get("DOWNLOAD_TIMEOUT", "300"))

# Public mode: ai cũng dùng được không cần key. Request có key đúng thì không bị giới hạn.
PUBLIC_MODE = os.environ.get("PUBLIC_MODE", "0").strip() == "1"
PUBLIC_RATE_LIMIT = int(os.environ.get("PUBLIC_RATE_LIMIT", "10"))  # số lần tải / giờ / IP
PUBLIC_MAX_FILESIZE_MB = int(os.environ.get("PUBLIC_MAX_FILESIZE_MB", "200"))

# Chỉ nhận link Facebook để yt-dlp không bị dùng làm downloader cho URL bất kỳ.
ALLOWED_HOSTS = ("facebook.com", "fb.watch", "fb.com")

# Ưu tiên H.264 + AAC trong mp4 để Photos trên iPhone mở được.
FORMAT = "bv*[vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4][vcodec^=avc1]/b[ext=mp4]/bv*+ba/b"

log = logging.getLogger("fbdl")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

if not API_KEY and not PUBLIC_MODE:
    raise RuntimeError("API_KEY chưa được set (hoặc bật PUBLIC_MODE=1)")

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="fb-download", docs_url=None, redoc_url=None, openapi_url=None)
if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["X-API-Key", "Content-Type"],
        expose_headers=["Content-Disposition"],
    )

semaphore = asyncio.Semaphore(MAX_CONCURRENT)
rate_hits: dict[str, deque] = defaultdict(deque)


class DownloadRequest(BaseModel):
    url: str


def check_key(key: str | None) -> bool:
    """True nếu là người có key (không giới hạn), False nếu là khách public."""
    if key and API_KEY and hmac.compare_digest(key.encode(), API_KEY.encode()):
        return True
    if key or not PUBLIC_MODE:
        raise HTTPException(status_code=401, detail="Sai API key")
    return False


def client_ip(request: Request) -> str:
    # Đi qua Cloudflare thì IP thật nằm ở CF-Connecting-IP.
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")


def check_rate(ip: str) -> None:
    now = time.monotonic()
    hits = rate_hits[ip]
    while hits and now - hits[0] > 3600:
        hits.popleft()
    if len(hits) >= PUBLIC_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Bạn tải nhiều quá, thử lại sau 1 giờ")
    hits.append(now)
    # Dọn IP cũ để dict không phình ra mãi
    if len(rate_hits) > 10000:
        for k in [k for k, v in rate_hits.items() if not v or now - v[-1] > 3600]:
            del rate_hits[k]


def check_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not any(
        host == h or host.endswith("." + h) for h in ALLOWED_HOSTS
    ):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ link Facebook")
    return url


def run_ytdlp(url: str, workdir: str, trusted: bool) -> Path:
    opts = {
        "format": FORMAT,
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(workdir, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": (MAX_FILESIZE_MB if trusted else PUBLIC_MAX_FILESIZE_MB) * 1024 * 1024,
        "socket_timeout": 30,
    }
    # Cookies chỉ dùng cho người có key: khách public không được xem video
    # private/group mà tài khoản chủ cookie thấy được.
    if trusted and os.path.isfile(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(url, download=True)
    files = [p for p in Path(workdir).iterdir() if p.is_file() and p.suffix in (".mp4", ".mov", ".m4v")]
    if not files:
        raise RuntimeError("yt-dlp không tạo ra file video")
    return max(files, key=lambda p: p.stat().st_size)


async def handle(request: Request, url: str, key: str | None) -> FileResponse:
    trusted = check_key(key)
    url = check_url(url)
    ip = client_ip(request)
    if not trusted:
        if semaphore.locked():
            raise HTTPException(status_code=503, detail="Server đang bận, thử lại sau ít phút")
        check_rate(ip)

    await semaphore.acquire()
    workdir = tempfile.mkdtemp(prefix="fbdl-")
    log.info("download ip=%s trusted=%s %s", ip, trusted, url)
    task = asyncio.ensure_future(asyncio.to_thread(run_ytdlp, url, workdir, trusted))
    # Thread yt-dlp không huỷ được, nên giữ slot cho tới khi nó thật sự chạy xong
    # (kể cả khi đã timeout) để không vượt MAX_CONCURRENT.
    task.add_done_callback(lambda _: semaphore.release())
    try:
        path = await asyncio.wait_for(asyncio.shield(task), DOWNLOAD_TIMEOUT)
    except asyncio.TimeoutError:
        task.add_done_callback(lambda _: shutil.rmtree(workdir, ignore_errors=True))
        raise HTTPException(status_code=504, detail="Tải quá lâu, đã huỷ")
    except yt_dlp.utils.DownloadError as e:
        shutil.rmtree(workdir, ignore_errors=True)
        log.warning("yt-dlp error: %s", e)
        raise HTTPException(status_code=422, detail=f"Không tải được: {e}")
    except Exception as e:
        shutil.rmtree(workdir, ignore_errors=True)
        log.exception("unexpected error")
        raise HTTPException(status_code=500, detail=str(e))
    cleanup = BackgroundTask(shutil.rmtree, workdir, ignore_errors=True)
    return FileResponse(path, media_type="video/mp4", filename=path.name, background=cleanup)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


@app.get("/api/health")
def health():
    return {"ok": True, "yt_dlp": yt_dlp.version.__version__, "auth_required": not PUBLIC_MODE}


@app.post("/api/download")
async def download_post(request: Request, req: DownloadRequest, x_api_key: str | None = Header(default=None)):
    return await handle(request, req.url, x_api_key)


@app.get("/api/download")
async def download_get(request: Request, url: str = Query(...), x_api_key: str | None = Header(default=None)):
    return await handle(request, url, x_api_key)
