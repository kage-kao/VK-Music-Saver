from fastapi import FastAPI, APIRouter, BackgroundTasks, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import re
import json
import zipfile
import shutil
import asyncio
import aiohttp
import aiofiles
import uuid
import time
import signal
import subprocess
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict
from datetime import datetime, timezone

try:
    from aiohttp_socks import ProxyConnector
except ImportError:
    ProxyConnector = None

try:
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, USLT, ID3NoHeaderError
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

KATE_USER_AGENT = "KateMobileAndroid/56 lite-460 (Android 4.4.2; SDK 19; x86; unknown Android SDK built for x86; en)"

vk_sessions: Dict[str, dict] = {}
xray_processes: Dict[str, dict] = {}
active_cancel_flags: Dict[str, bool] = {}

DOWNLOAD_DIR = Path("/tmp/vk_downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)
XRAY_CONFIG_DIR = Path("/tmp/xray_configs")
XRAY_CONFIG_DIR.mkdir(exist_ok=True)
XRAY_BIN = "/usr/local/bin/xray"
TEMPSHARE_MAX_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
CHUNK_SIZE_LIMIT = 1 * 1024 * 1024 * 1024  # 1GB - FIX BUG #2: chunk threshold
CONCURRENT_DOWNLOADS = 8


# ==================== MODELS ====================

class VkTokenLoginRequest(BaseModel):
    token: str = Field(..., min_length=1)

class PlaylistDownloadRequest(BaseModel):
    session_id: str
    playlist_url: str
    add_tags: bool = False
    add_lyrics: bool = False
    quality: str = "high"

class MultiPlaylistDownloadRequest(BaseModel):
    session_id: str
    playlist_urls: List[str]
    add_tags: bool = False
    add_lyrics: bool = False
    quality: str = "high"

class TrackDownloadRequest(BaseModel):
    session_id: str
    track_url: str
    add_tags: bool = False
    add_lyrics: bool = False
    quality: str = "high"

class MyMusicDownloadRequest(BaseModel):
    session_id: str
    add_tags: bool = False
    add_lyrics: bool = False
    quality: str = "high"

class DownloadHistoryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    playlist_url: str = ""
    playlist_title: str = ""
    track_count: int = 0
    downloaded_count: int = 0
    status: str = "pending"
    progress: float = 0.0
    current_track: str = ""
    download_url: str = ""
    download_urls: List[str] = []
    error_message: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ""
    file_size: str = ""
    download_type: str = "playlist"

class ProxyAddRequest(BaseModel):
    proxy_type: str = Field(..., description="http, socks5, vless")
    address: str = Field(..., min_length=1)
    name: str = Field(default="")

class ProxyUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    name: Optional[str] = None


# ==================== VLESS PARSING ====================

def parse_vless_uri(uri: str) -> dict:
    if not uri.startswith("vless://"):
        raise ValueError("Not a VLESS URI")
    rest = uri[8:]
    fragment = ""
    if "#" in rest:
        rest, fragment = rest.rsplit("#", 1)
        fragment = unquote(fragment)
    params = {}
    if "?" in rest:
        rest, query = rest.split("?", 1)
        for pair in query.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k] = unquote(v)
    if "@" not in rest:
        raise ValueError("Invalid VLESS URI: missing @")
    user_id, hostport = rest.split("@", 1)
    if ":" in hostport:
        host, port_str = hostport.rsplit(":", 1)
        port = int(port_str)
    else:
        host = hostport
        port = 443
    return {
        "uuid": user_id, "host": host, "port": port, "fragment": fragment,
        "type": params.get("type", "tcp"), "security": params.get("security", "none"),
        "encryption": params.get("encryption", "none"), "sni": params.get("sni", ""),
        "fp": params.get("fp", ""), "pbk": params.get("pbk", ""),
        "sid": params.get("sid", ""), "spx": params.get("spx", ""),
        "path": params.get("path", "/"), "host_header": params.get("host", ""),
        "mode": params.get("mode", ""), "flow": params.get("flow", ""),
    }


def generate_xray_config(vless_params: dict, local_port: int) -> dict:
    stream_settings = {"network": vless_params["type"]}
    transport_type = vless_params["type"]
    if transport_type == "ws":
        stream_settings["wsSettings"] = {"path": vless_params.get("path", "/"), "headers": {}}
        if vless_params.get("host_header"):
            stream_settings["wsSettings"]["headers"]["Host"] = vless_params["host_header"]
    elif transport_type == "tcp":
        stream_settings["tcpSettings"] = {}
    elif transport_type == "grpc":
        stream_settings["grpcSettings"] = {"serviceName": vless_params.get("path", ""), "multiMode": False}
    elif transport_type in ("xhttp", "splithttp"):
        xhttp_settings = {"path": vless_params.get("path", "/")}
        if vless_params.get("host_header"):
            xhttp_settings["host"] = vless_params["host_header"]
        if vless_params.get("mode"):
            xhttp_settings["mode"] = vless_params["mode"]
        stream_settings["xhttpSettings"] = xhttp_settings
        stream_settings["network"] = "xhttp"

    security = vless_params.get("security", "none")
    stream_settings["security"] = security
    if security == "tls":
        tls_settings = {"allowInsecure": False}
        if vless_params.get("sni"): tls_settings["serverName"] = vless_params["sni"]
        if vless_params.get("fp"): tls_settings["fingerprint"] = vless_params["fp"]
        stream_settings["tlsSettings"] = tls_settings
    elif security == "reality":
        reality_settings = {"show": False}
        if vless_params.get("sni"): reality_settings["serverName"] = vless_params["sni"]
        if vless_params.get("fp"): reality_settings["fingerprint"] = vless_params["fp"]
        if vless_params.get("pbk"): reality_settings["publicKey"] = vless_params["pbk"]
        if vless_params.get("sid"): reality_settings["shortId"] = vless_params["sid"]
        if vless_params.get("spx"): reality_settings["spiderX"] = vless_params["spx"]
        stream_settings["realitySettings"] = reality_settings

    vless_user = {"id": vless_params["uuid"], "encryption": vless_params.get("encryption", "none"), "level": 0}
    if vless_params.get("flow"):
        vless_user["flow"] = vless_params["flow"]

    return {
        "log": {"loglevel": "warning"},
        "inbounds": [{"tag": "socks-in", "port": local_port, "listen": "127.0.0.1",
                       "protocol": "socks", "settings": {"auth": "noauth", "udp": True},
                       "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}}],
        "outbounds": [
            {"tag": "proxy", "protocol": "vless",
             "settings": {"vnext": [{"address": vless_params["host"], "port": vless_params["port"], "users": [vless_user]}]},
             "streamSettings": stream_settings},
            {"tag": "direct", "protocol": "freedom"}
        ],
        "routing": {"domainStrategy": "AsIs", "rules": []}
    }


def find_free_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


# FIX BUG #3: Check if xray binary exists before starting
def check_xray_available():
    if not os.path.isfile(XRAY_BIN):
        raise FileNotFoundError(
            f"Xray не найден по пути {XRAY_BIN}. "
            "Установите Xray для поддержки VLESS прокси: "
            "запустите deploy.sh или скачайте вручную с https://github.com/XTLS/Xray-core/releases"
        )
    if not os.access(XRAY_BIN, os.X_OK):
        raise PermissionError(
            f"Xray найден ({XRAY_BIN}), но не имеет прав на выполнение. "
            "Выполните: chmod +x /usr/local/bin/xray"
        )


async def start_xray_for_proxy(proxy_id: str, vless_uri: str) -> dict:
    await stop_xray_for_proxy(proxy_id)
    try:
        # FIX BUG #3: Check xray exists before attempting to run
        check_xray_available()

        vless_params = parse_vless_uri(vless_uri)
        local_port = find_free_port()
        config = generate_xray_config(vless_params, local_port)
        config_path = XRAY_CONFIG_DIR / f"{proxy_id}.json"
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        process = subprocess.Popen(
            [XRAY_BIN, "run", "-c", str(config_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=os.setsid
        )
        await asyncio.sleep(1.5)
        if process.poll() is not None:
            stderr_output = process.stderr.read().decode('utf-8', errors='replace')[:500]
            raise Exception(f"Xray exited: {stderr_output}")
        xray_processes[proxy_id] = {
            "process": process, "port": local_port,
            "config_path": str(config_path), "started_at": datetime.now(timezone.utc).isoformat()
        }
        logger.info(f"Xray started for proxy {proxy_id} on port {local_port}")
        return {"port": local_port, "status": "running"}
    except (FileNotFoundError, PermissionError) as e:
        logger.error(f"Xray not available for {proxy_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to start xray for {proxy_id}: {e}")
        raise


async def stop_xray_for_proxy(proxy_id: str):
    if proxy_id in xray_processes:
        proc_info = xray_processes[proxy_id]
        process = proc_info.get("process")
        if process and process.poll() is None:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                process.wait(timeout=5)
            except Exception:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except Exception:
                    pass
        config_path = proc_info.get("config_path")
        if config_path and os.path.exists(config_path):
            os.remove(config_path)
        del xray_processes[proxy_id]


async def test_proxy_connectivity(proxy_url: str, timeout: int = 10) -> dict:
    start_time = time.time()
    try:
        if ProxyConnector and proxy_url.startswith("socks5://"):
            connector = ProxyConnector.from_url(proxy_url)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    "https://api.vk.com/method/utils.getServerTime?v=5.131&access_token=",
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    data = await resp.json(content_type=None)
                    latency = round((time.time() - start_time) * 1000)
                    ip = None
                    try:
                        async with session.get("https://api.ipify.org?format=json", timeout=aiohttp.ClientTimeout(total=5)) as ip_resp:
                            ip_data = await ip_resp.json(content_type=None)
                            ip = ip_data.get("ip")
                    except Exception:
                        pass
                    return {"success": True, "latency_ms": latency, "ip": ip, "vk_accessible": data is not None}
        else:
            async with aiohttp.ClientSession() as session:
                kwargs = {"timeout": aiohttp.ClientTimeout(total=timeout)}
                if proxy_url.startswith("http"):
                    kwargs["proxy"] = proxy_url
                async with session.get("https://api.vk.com/method/utils.getServerTime?v=5.131&access_token=", **kwargs) as resp:
                    data = await resp.json(content_type=None)
                    latency = round((time.time() - start_time) * 1000)
                    return {"success": True, "latency_ms": latency, "ip": None, "vk_accessible": data is not None}
    except asyncio.TimeoutError:
        return {"success": False, "error": "Timeout", "latency_ms": timeout * 1000}
    except Exception as e:
        return {"success": False, "error": str(e)[:200], "latency_ms": 0}


# ==================== PROXY MANAGEMENT ====================

async def get_active_proxy():
    proxy = await db.proxies.find_one({"enabled": True}, {"_id": 0})
    return proxy

def build_proxy_url(proxy_doc):
    if not proxy_doc:
        return None
    ptype = proxy_doc.get("proxy_type", "")
    address = proxy_doc.get("address", "")
    proxy_id = proxy_doc.get("id", "")
    if ptype == "vless":
        if proxy_id in xray_processes:
            port = xray_processes[proxy_id]["port"]
            return f"socks5://127.0.0.1:{port}"
        return None
    if ptype in ("http", "https"):
        return f"http://{address}" if not address.startswith("http") else address
    if ptype == "socks5":
        return f"socks5://{address}" if not address.startswith("socks5") else address
    return None


def create_proxy_connector(proxy_url):
    if proxy_url and ProxyConnector and proxy_url.startswith(("socks5://", "socks4://")):
        return ProxyConnector.from_url(proxy_url)
    return None


async def make_vk_session(proxy_url=None):
    connector = create_proxy_connector(proxy_url)
    if connector:
        return aiohttp.ClientSession(connector=connector), None
    session = aiohttp.ClientSession()
    http_proxy = proxy_url if proxy_url and proxy_url.startswith("http") else None
    return session, http_proxy


async def make_request_with_proxy(method, url, proxy_url=None, **kwargs):
    headers = kwargs.pop("headers", {})
    headers.setdefault("User-Agent", KATE_USER_AGENT)
    kwargs["headers"] = headers

    if proxy_url and proxy_url.startswith(("socks5://", "socks4://")) and ProxyConnector:
        connector = ProxyConnector.from_url(proxy_url)
        async with aiohttp.ClientSession(connector=connector) as session:
            if method == "GET":
                async with session.get(url, **kwargs) as resp:
                    return await resp.json(content_type=None)
            else:
                async with session.post(url, **kwargs) as resp:
                    return await resp.json(content_type=None)
    else:
        async with aiohttp.ClientSession() as session:
            req_kwargs = kwargs.copy()
            if proxy_url and proxy_url.startswith("http"):
                req_kwargs["proxy"] = proxy_url
            if method == "GET":
                async with session.get(url, **req_kwargs) as resp:
                    return await resp.json(content_type=None)
            else:
                async with session.post(url, **req_kwargs) as resp:
                    return await resp.json(content_type=None)


# ==================== VK API ====================

async def vk_api_method(token, method, **params):
    params["access_token"] = token
    params["v"] = "5.131"
    proxy_doc = await get_active_proxy()
    proxy_url = build_proxy_url(proxy_doc) if proxy_doc else None
    data = await make_request_with_proxy("GET", f"https://api.vk.com/method/{method}", proxy_url=proxy_url, params=params)
    if "error" in data:
        raise Exception(data["error"].get("error_msg", "VK API Error"))
    return data.get("response", data)


async def get_user_info(token):
    try:
        result = await vk_api_method(token, "users.get", fields="photo_100,first_name,last_name")
        if isinstance(result, list) and len(result) > 0:
            return result[0]
    except Exception as e:
        logger.error(f"Error getting user info: {e}")
    return {"first_name": "VK", "last_name": "User", "photo_100": ""}


async def get_all_audio(token, owner_id=None, album_id=None, access_key=None):
    all_tracks = []
    offset = 0
    batch_size = 200
    while True:
        params = {"count": batch_size, "offset": offset}
        if owner_id is not None:
            params["owner_id"] = owner_id
        if album_id is not None:
            params["album_id"] = album_id
        if access_key:
            params["access_key"] = access_key
        result = await vk_api_method(token, "audio.get", **params)
        if isinstance(result, dict):
            items = result.get("items", [])
            total = result.get("count", 0)
        else:
            items = []
            total = 0
        all_tracks.extend(items)
        offset += batch_size
        if not items or offset >= total:
            break
        await asyncio.sleep(0.35)
    return all_tracks


async def get_lyrics(token, lyrics_id):
    try:
        result = await vk_api_method(token, "audio.getLyrics", lyrics_id=lyrics_id)
        return result.get("text", "")
    except Exception:
        return ""


# ==================== AUTH ENDPOINTS ====================

@api_router.post("/vk/token-login")
async def vk_token_login(req: VkTokenLoginRequest):
    try:
        user_info = await get_user_info(req.token)
        if user_info.get("first_name") == "VK" and user_info.get("last_name") == "User":
            try:
                await vk_api_method(req.token, "account.getProfileInfo")
            except Exception:
                raise HTTPException(status_code=401, detail="Invalid token")
        session_id = str(uuid.uuid4())
        vk_sessions[session_id] = {"token": req.token}
        return {
            "status": "success", "session_id": session_id,
            "user": {"first_name": user_info.get("first_name", ""), "last_name": user_info.get("last_name", ""), "photo": user_info.get("photo_100", "")}
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token login error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@api_router.post("/vk/logout")
async def vk_logout(data: dict):
    session_id = data.get("session_id")
    if session_id in vk_sessions:
        del vk_sessions[session_id]
    return {"status": "ok"}


# ==================== PROXY ENDPOINTS ====================

@api_router.get("/proxies")
async def get_proxies():
    proxies = await db.proxies.find({}, {"_id": 0}).to_list(100)
    for p in proxies:
        pid = p.get("id", "")
        if pid in xray_processes:
            proc = xray_processes[pid]["process"]
            if proc.poll() is None:
                p["xray_running"] = True
                p["xray_port"] = xray_processes[pid]["port"]
            else:
                p["xray_running"] = False
                del xray_processes[pid]
        else:
            p["xray_running"] = False
    return proxies

@api_router.post("/proxies")
async def add_proxy(req: ProxyAddRequest):
    proxy_id = str(uuid.uuid4())
    proxy_doc = {
        "id": proxy_id, "proxy_type": req.proxy_type, "address": req.address,
        "name": req.name or f"{req.proxy_type.upper()} proxy",
        "enabled": False, "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "unchecked", "status_message": "", "check_ip": "", "check_latency": 0,
    }
    await db.proxies.insert_one(proxy_doc)
    proxy_doc.pop("_id", None)
    return proxy_doc

@api_router.post("/proxies/{proxy_id}/toggle")
async def toggle_proxy(proxy_id: str):
    proxy = await db.proxies.find_one({"id": proxy_id}, {"_id": 0})
    if not proxy:
        raise HTTPException(status_code=404, detail="Proxy not found")
    new_state = not proxy.get("enabled", False)
    if new_state:
        all_proxies = await db.proxies.find({}, {"_id": 0}).to_list(100)
        for p in all_proxies:
            if p["id"] != proxy_id and p.get("enabled"):
                await stop_xray_for_proxy(p["id"])
        await db.proxies.update_many({}, {"$set": {"enabled": False}})
        if proxy.get("proxy_type") == "vless":
            try:
                result = await start_xray_for_proxy(proxy_id, proxy["address"])
                await db.proxies.update_one({"id": proxy_id}, {"$set": {"enabled": True, "status_message": f"Xray on port {result['port']}"}})
            except Exception as e:
                await db.proxies.update_one({"id": proxy_id}, {"$set": {"status": "error", "status_message": str(e)[:200]}})
                return {"id": proxy_id, "enabled": False, "error": str(e)[:200]}
        else:
            await db.proxies.update_one({"id": proxy_id}, {"$set": {"enabled": True}})
    else:
        await stop_xray_for_proxy(proxy_id)
        await db.proxies.update_one({"id": proxy_id}, {"$set": {"enabled": False}})
    return {"id": proxy_id, "enabled": new_state}

@api_router.delete("/proxies/{proxy_id}")
async def delete_proxy(proxy_id: str):
    await stop_xray_for_proxy(proxy_id)
    await db.proxies.delete_one({"id": proxy_id})
    return {"status": "ok"}

@api_router.post("/proxies/{proxy_id}/check")
async def check_proxy(proxy_id: str):
    proxy = await db.proxies.find_one({"id": proxy_id}, {"_id": 0})
    if not proxy:
        raise HTTPException(status_code=404, detail="Proxy not found")
    await db.proxies.update_one({"id": proxy_id}, {"$set": {"status": "checking", "status_message": "Checking..."}})
    proxy_type = proxy.get("proxy_type", "")
    address = proxy.get("address", "")

    if proxy_type == "vless":
        if proxy.get("enabled") and proxy_id in xray_processes:
            port = xray_processes[proxy_id]["port"]
            socks_url = f"socks5://127.0.0.1:{port}"
            test_result = await test_proxy_connectivity(socks_url, timeout=10)
        else:
            temp_id = f"check_{proxy_id}"
            try:
                result = await start_xray_for_proxy(temp_id, address)
                socks_url = f"socks5://127.0.0.1:{result['port']}"
                test_result = await test_proxy_connectivity(socks_url, timeout=10)
                await stop_xray_for_proxy(temp_id)
            except Exception as e:
                await stop_xray_for_proxy(temp_id)
                await db.proxies.update_one({"id": proxy_id}, {"$set": {"status": "error", "status_message": f"Xray error: {str(e)[:200]}"}})
                return {"status": "error", "message": str(e)[:200]}
    else:
        proxy_url = build_proxy_url(proxy)
        if not proxy_url:
            await db.proxies.update_one({"id": proxy_id}, {"$set": {"status": "error", "status_message": "Unsupported type"}})
            raise HTTPException(status_code=400, detail="Unsupported proxy type")
        test_result = await test_proxy_connectivity(proxy_url, timeout=10)

    if test_result["success"]:
        status_msg = f"OK! Ping: {test_result['latency_ms']}ms"
        if test_result.get("ip"):
            status_msg += f" | IP: {test_result['ip']}"
        await db.proxies.update_one({"id": proxy_id}, {"$set": {
            "status": "ok", "status_message": status_msg,
            "check_ip": test_result.get("ip", ""), "check_latency": test_result.get("latency_ms", 0),
            "last_check": datetime.now(timezone.utc).isoformat()
        }})
        return {"status": "ok", "message": status_msg, "ip": test_result.get("ip"), "latency_ms": test_result.get("latency_ms")}
    else:
        error_msg = test_result.get("error", "Connection failed")
        await db.proxies.update_one({"id": proxy_id}, {"$set": {"status": "error", "status_message": error_msg, "check_ip": "", "check_latency": 0}})
        return {"status": "error", "message": error_msg}


# ==================== PLAYLIST PARSING ====================

def parse_playlist_url(url):
    patterns = [
        r'audio_playlist(-?\d+)_(\d+)/([a-f0-9]+)',
        r'audio_playlist(-?\d+)_(\d+)',
        r'playlist/(-?\d+)_(\d+)_([a-f0-9]+)',
        r'playlist/(-?\d+)_(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            groups = match.groups()
            return int(groups[0]), int(groups[1]), groups[2] if len(groups) > 2 else None
    return None, None, None


def parse_track_url(url):
    patterns = [
        r'audio(-?\d+)_(\d+)',
        r'audio_id=(-?\d+)_(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None, None


# ==================== DOWNLOAD ENGINE ====================

async def download_track_file(session, url, filepath, http_proxy=None, timeout=60):
    try:
        headers = {"User-Agent": KATE_USER_AGENT}
        req_kwargs = {"timeout": aiohttp.ClientTimeout(total=timeout), "headers": headers}
        if http_proxy:
            req_kwargs["proxy"] = http_proxy
        async with session.get(url, **req_kwargs) as response:
            if response.status == 200:
                async with aiofiles.open(filepath, 'wb') as f:
                    async for chunk in response.content.iter_chunked(16384):
                        await f.write(chunk)
                return True
    except Exception as e:
        logger.error(f"Download error: {e}")
    return False


async def apply_id3_tags(filepath, track, cover_data=None, lyrics_text=None):
    if not HAS_MUTAGEN:
        return
    try:
        try:
            audio = MP3(str(filepath), ID3=ID3)
        except ID3NoHeaderError:
            audio = MP3(str(filepath))
            audio.add_tags()

        audio.tags.add(TIT2(encoding=3, text=[track.get('title', 'Unknown')]))
        audio.tags.add(TPE1(encoding=3, text=[track.get('artist', 'Unknown')]))

        album_info = track.get('album', {})
        if album_info and isinstance(album_info, dict):
            audio.tags.add(TALB(encoding=3, text=[album_info.get('title', '')]))

        if cover_data:
            audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=cover_data))

        if lyrics_text:
            audio.tags.add(USLT(encoding=3, lang='rus', desc='', text=lyrics_text))

        audio.save()
    except Exception as e:
        logger.error(f"ID3 tag error: {e}")


async def fetch_cover(session, track, http_proxy=None):
    album = track.get('album', {})
    if not album or not isinstance(album, dict):
        return None
    thumb = album.get('thumb', {})
    if not thumb or not isinstance(thumb, dict):
        return None
    cover_url = thumb.get('photo_600') or thumb.get('photo_300') or thumb.get('photo_270')
    if not cover_url:
        return None
    try:
        req_kwargs = {"timeout": aiohttp.ClientTimeout(total=15)}
        if http_proxy:
            req_kwargs["proxy"] = http_proxy
        async with session.get(cover_url, **req_kwargs) as resp:
            if resp.status == 200:
                return await resp.read()
    except Exception:
        pass
    return None


async def upload_to_tempshare(filepath):
    try:
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field('file', open(filepath, 'rb'), filename=os.path.basename(filepath))
            data.add_field('duration', '7')
            async with session.post('https://api.tempshare.su/upload', data=data, timeout=aiohttp.ClientTimeout(total=600)) as response:
                result = await response.json()
                if result.get('success'):
                    return {"success": True, "url": result.get('url', ''), "raw_url": result.get('raw_url', '')}
                return {"success": False, "error": result.get('error', 'Upload failed')}
    except Exception as e:
        logger.error(f"TempShare upload error: {e}")
        return {"success": False, "error": str(e)}


def format_size(bytes_size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} TB"


async def update_task_status(task_id, status, **kwargs):
    update = {"status": status}
    update.update(kwargs)
    await db.download_history.update_one({"id": task_id}, {"$set": update})


def get_dir_size(dir_path):
    total = 0
    for f in Path(dir_path).iterdir():
        if f.is_file():
            total += f.stat().st_size
    return total


# FIX BUG #2: Chunked download with 1GB threshold
# Downloads tracks, when accumulated size reaches ~1GB:
# stop -> zip -> upload to tempshare -> save link -> clean cache -> continue
async def download_tracks_batch(task_id, token, tracks, title, add_tags=False, add_lyrics=False, quality="high"):
    try:
        if active_cancel_flags.get(task_id):
            await update_task_status(task_id, "cancelled", error_message="Cancelled by user")
            return

        valid_tracks = [t for t in tracks if t.get('url')]
        actual_count = len(valid_tracks)

        await db.download_history.update_one(
            {"id": task_id},
            {"$set": {"playlist_title": title, "track_count": actual_count, "downloaded_count": 0}}
        )

        if not valid_tracks:
            await update_task_status(task_id, "error", error_message="Треки недоступны для скачивания. Вероятно, сервер находится за пределами России и контент ограничен по региону. Подключите российский прокси в настройках.")
            return

        task_dir = DOWNLOAD_DIR / task_id
        task_dir.mkdir(exist_ok=True)

        proxy_doc = await get_active_proxy()
        proxy_url = build_proxy_url(proxy_doc) if proxy_doc else None

        connector = create_proxy_connector(proxy_url)
        if connector:
            http_session = aiohttp.ClientSession(connector=connector)
            http_proxy = None
        else:
            http_session = aiohttp.ClientSession()
            http_proxy = proxy_url if proxy_url and proxy_url.startswith("http") else None

        total_downloaded = 0
        chunk_part = 0
        upload_urls = []
        total_size_all = 0
        semaphore = asyncio.Semaphore(CONCURRENT_DOWNLOADS)

        # Process tracks in sequential chunks to control disk usage
        i = 0
        while i < len(valid_tracks):
            if active_cancel_flags.get(task_id):
                break

            # Download tracks until we hit ~1GB or run out
            chunk_files = []
            chunk_size = 0

            async def download_one_track(track_idx, track):
                nonlocal chunk_size
                if active_cancel_flags.get(task_id):
                    return None

                async with semaphore:
                    if active_cancel_flags.get(task_id):
                        return None

                    artist = track.get('artist', 'Unknown')
                    track_title = track.get('title', 'Unknown')
                    url = track.get('url', '')

                    # FIX BUG #1: Limit filename length to 200 chars to avoid Linux 255-byte limit
                    safe_name = re.sub(r'[<>:"/\\|?*]', '_', f"{track_idx+1:03d}. {artist} - {track_title}")[:200]
                    filepath = task_dir / f"{safe_name}.mp3"

                    success = await download_track_file(http_session, url, str(filepath), http_proxy=http_proxy)

                    if success:
                        file_size = filepath.stat().st_size if filepath.exists() else 0
                        chunk_size += file_size

                        if add_tags and HAS_MUTAGEN:
                            cover_data = await fetch_cover(http_session, track, http_proxy=http_proxy)
                            lyrics_text = None
                            if add_lyrics and track.get('lyrics_id'):
                                lyrics_text = await get_lyrics(token, track['lyrics_id'])
                            await apply_id3_tags(filepath, track, cover_data, lyrics_text)

                        return str(filepath)
                    return None

            # Download tracks one-by-one or in small batches, checking size after each
            batch_start = i
            while i < len(valid_tracks) and chunk_size < CHUNK_SIZE_LIMIT:
                if active_cancel_flags.get(task_id):
                    break

                # Download a small batch of up to CONCURRENT_DOWNLOADS tracks
                batch_end = min(i + CONCURRENT_DOWNLOADS, len(valid_tracks))
                batch_tasks = []
                for j in range(i, batch_end):
                    batch_tasks.append(download_one_track(j, valid_tracks[j]))

                results = await asyncio.gather(*batch_tasks)
                for r in results:
                    if r:
                        chunk_files.append(r)
                        total_downloaded += 1

                i = batch_end

                # Update progress
                progress = (total_downloaded / actual_count) * 80
                current_artist = valid_tracks[min(i - 1, len(valid_tracks) - 1)].get('artist', '')
                current_title = valid_tracks[min(i - 1, len(valid_tracks) - 1)].get('title', '')
                await update_task_status(
                    task_id, "downloading",
                    progress=progress,
                    current_track=f"{current_artist} - {current_title}",
                    downloaded_count=total_downloaded
                )

                # Check if we've hit the chunk size limit
                if chunk_size >= CHUNK_SIZE_LIMIT:
                    break

            if active_cancel_flags.get(task_id):
                break

            # If we have files in this chunk, zip and upload them
            if chunk_files:
                chunk_part += 1
                total_size_all += chunk_size

                await update_task_status(task_id, "zipping", progress=80 + (chunk_part * 2),
                                         current_track=f"Создание архива (часть {chunk_part})...")

                safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)[:150]
                part_suffix = f"_part{chunk_part}" if (chunk_size >= CHUNK_SIZE_LIMIT or chunk_part > 1) else ""
                zip_filename = f"{safe_title}_{task_id[:8]}{part_suffix}.zip"
                zip_path = DOWNLOAD_DIR / zip_filename

                loop = asyncio.get_event_loop()
                def create_chunk_zip(files_to_zip, zpath):
                    with zipfile.ZipFile(str(zpath), 'w', zipfile.ZIP_STORED) as zf:
                        for fpath in sorted(files_to_zip):
                            zf.write(fpath, os.path.basename(fpath))

                await loop.run_in_executor(None, create_chunk_zip, chunk_files, zip_path)

                # Check if zip itself exceeds 2GB and needs splitting
                zip_file_size = os.path.getsize(str(zip_path))
                if zip_file_size > TEMPSHARE_MAX_SIZE:
                    # Split the zip
                    split_parts = await loop.run_in_executor(None, split_zip_files, zip_path)
                    for sp_idx, sp_path in enumerate(split_parts):
                        await update_task_status(task_id, "uploading",
                                                 progress=82 + (chunk_part * 3),
                                                 current_track=f"Загрузка части {chunk_part}.{sp_idx + 1}...")
                        result = await upload_to_tempshare(sp_path)
                        if result.get("success"):
                            upload_urls.append(result.get("url", ""))
                        else:
                            logger.error(f"Upload failed for split part: {result.get('error')}")
                        if os.path.exists(sp_path):
                            os.remove(sp_path)
                else:
                    await update_task_status(task_id, "uploading",
                                             progress=82 + (chunk_part * 3),
                                             current_track=f"Загрузка части {chunk_part}...")
                    result = await upload_to_tempshare(str(zip_path))
                    if result.get("success"):
                        upload_urls.append(result.get("url", ""))
                    else:
                        logger.error(f"Upload failed: {result.get('error')}")

                # Clean up: remove zip and downloaded track files to free disk space
                if zip_path.exists():
                    os.remove(str(zip_path))
                for fpath in chunk_files:
                    if os.path.exists(fpath):
                        os.remove(fpath)

                logger.info(f"Chunk {chunk_part} uploaded and cleaned. Tracks so far: {total_downloaded}/{actual_count}")

        await http_session.close()

        if active_cancel_flags.get(task_id):
            shutil.rmtree(str(task_dir), ignore_errors=True)
            active_cancel_flags.pop(task_id, None)
            await update_task_status(task_id, "cancelled", error_message="Cancelled by user")
            return

        await db.download_history.update_one({"id": task_id}, {"$set": {"downloaded_count": total_downloaded}})

        if total_downloaded == 0:
            shutil.rmtree(str(task_dir), ignore_errors=True)
            await update_task_status(task_id, "error", error_message="Не удалось скачать ни одного трека. Скорее всего, сервер находится за пределами России и треки ограничены по региону. Подключите российский прокси в настройках.")
            return

        if not upload_urls:
            shutil.rmtree(str(task_dir), ignore_errors=True)
            await update_task_status(task_id, "error", error_message="Не удалось загрузить архив на TempShare.")
            return

        size_str = format_size(total_size_all)
        await update_task_status(
            task_id, "completed", progress=100.0,
            download_url=upload_urls[0],
            download_urls=upload_urls,
            file_size=size_str,
            current_track="",
            downloaded_count=total_downloaded
        )
        await db.download_history.update_one({"id": task_id}, {"$set": {"completed_at": datetime.now(timezone.utc).isoformat()}})

        shutil.rmtree(str(task_dir), ignore_errors=True)
        active_cancel_flags.pop(task_id, None)

    except Exception as e:
        logger.error(f"Download task error {task_id}: {e}")
        await update_task_status(task_id, "error", error_message=str(e)[:300])
        active_cancel_flags.pop(task_id, None)


def split_zip_files(zip_path, max_size=TEMPSHARE_MAX_SIZE):
    file_size = os.path.getsize(str(zip_path))
    if file_size <= max_size:
        return [str(zip_path)]

    parts = []
    base_name = str(zip_path).replace('.zip', '')

    with zipfile.ZipFile(str(zip_path), 'r') as src_zip:
        all_names = src_zip.namelist()
        part_num = 1
        current_size = 0
        current_names = []

        for name in all_names:
            info = src_zip.getinfo(name)
            entry_size = info.compress_size + 100

            if current_size + entry_size > max_size * 0.95 and current_names:
                part_path = f"{base_name}_split{part_num}.zip"
                with zipfile.ZipFile(part_path, 'w', zipfile.ZIP_DEFLATED) as part_zip:
                    for n in current_names:
                        part_zip.writestr(src_zip.getinfo(n), src_zip.read(n))
                parts.append(part_path)
                part_num += 1
                current_names = []
                current_size = 0

            current_names.append(name)
            current_size += entry_size

        if current_names:
            part_path = f"{base_name}_split{part_num}.zip"
            with zipfile.ZipFile(part_path, 'w', zipfile.ZIP_DEFLATED) as part_zip:
                for n in current_names:
                    part_zip.writestr(src_zip.getinfo(n), src_zip.read(n))
            parts.append(part_path)

    return parts


async def process_playlist_download(task_id, session_id, playlist_url, add_tags=False, add_lyrics=False, quality="high"):
    session_data = vk_sessions.get(session_id)
    if not session_data:
        await update_task_status(task_id, "error", error_message="VK session expired")
        return

    token = session_data["token"]
    owner_id, playlist_id, access_key = parse_playlist_url(playlist_url)

    if owner_id is None:
        await update_task_status(task_id, "error", error_message="Invalid playlist URL")
        return

    await update_task_status(task_id, "downloading", progress=0.0, current_track="Getting track list...")

    try:
        pl_params = {"owner_id": owner_id, "playlist_id": playlist_id}
        if access_key:
            pl_params["access_key"] = access_key
        pl_info = await vk_api_method(token, "audio.getPlaylistById", **pl_params)
        title = pl_info.get("title", f"playlist_{owner_id}_{playlist_id}")
    except Exception:
        title = f"playlist_{owner_id}_{playlist_id}"

    try:
        tracks = await get_all_audio(token, owner_id=owner_id, album_id=playlist_id, access_key=access_key)
    except Exception as e:
        logger.error(f"Error getting tracks: {e}")
        tracks = []

    if not tracks:
        await update_task_status(task_id, "error", error_message="No tracks found. Check URL and access.")
        return

    await download_tracks_batch(task_id, token, tracks, title, add_tags, add_lyrics, quality)


async def process_my_music_download(task_id, session_id, add_tags=False, add_lyrics=False, quality="high"):
    session_data = vk_sessions.get(session_id)
    if not session_data:
        await update_task_status(task_id, "error", error_message="VK session expired")
        return

    token = session_data["token"]
    await update_task_status(task_id, "downloading", progress=0.0, current_track="Getting your music library...")

    try:
        tracks = await get_all_audio(token)
    except Exception as e:
        logger.error(f"Error getting my music: {e}")
        await update_task_status(task_id, "error", error_message=f"Error: {str(e)[:200]}")
        return

    if not tracks:
        await update_task_status(task_id, "error", error_message="Your music library is empty or inaccessible")
        return

    user_info = await get_user_info(token)
    title = f"My_Music_{user_info.get('first_name', 'VK')}_{user_info.get('last_name', 'User')}"

    await download_tracks_batch(task_id, token, tracks, title, add_tags, add_lyrics, quality)


async def process_track_download(task_id, session_id, track_url, add_tags=False, add_lyrics=False, quality="high"):
    session_data = vk_sessions.get(session_id)
    if not session_data:
        await update_task_status(task_id, "error", error_message="VK session expired")
        return

    token = session_data["token"]
    owner_id, audio_id = parse_track_url(track_url)

    if owner_id is None:
        await update_task_status(task_id, "error", error_message="Invalid track URL")
        return

    await update_task_status(task_id, "downloading", progress=0.0, current_track="Getting track info...")

    try:
        audios_str = f"{owner_id}_{audio_id}"
        result = await vk_api_method(token, "audio.getById", audios=audios_str)
        if isinstance(result, list) and len(result) > 0:
            tracks = result
        else:
            tracks = []
    except Exception as e:
        logger.error(f"Error getting track: {e}")
        await update_task_status(task_id, "error", error_message=f"Error: {str(e)[:200]}")
        return

    if not tracks:
        await update_task_status(task_id, "error", error_message="Track not found or not accessible")
        return

    track = tracks[0]
    title = f"{track.get('artist', 'Unknown')} - {track.get('title', 'Unknown')}"
    await download_tracks_batch(task_id, token, [track], title, add_tags, add_lyrics, quality)


# ==================== API ENDPOINTS ====================

@api_router.get("/")
async def root():
    return {"message": "VK Music Saver API"}


@api_router.post("/download/start")
async def start_download(req: PlaylistDownloadRequest, background_tasks: BackgroundTasks):
    if req.session_id not in vk_sessions:
        raise HTTPException(status_code=401, detail="Session not found")
    owner_id, playlist_id, access_key = parse_playlist_url(req.playlist_url)
    if owner_id is None:
        raise HTTPException(status_code=400, detail="Invalid VK playlist URL")

    task_id = str(uuid.uuid4())
    task = DownloadHistoryItem(id=task_id, session_id=req.session_id, playlist_url=req.playlist_url, download_type="playlist")
    doc = task.model_dump()
    await db.download_history.insert_one(doc)
    background_tasks.add_task(process_playlist_download, task_id, req.session_id, req.playlist_url, req.add_tags, req.add_lyrics, req.quality)
    return {"task_id": task_id, "status": "pending"}


@api_router.post("/download/multi")
async def start_multi_download(req: MultiPlaylistDownloadRequest, background_tasks: BackgroundTasks):
    if req.session_id not in vk_sessions:
        raise HTTPException(status_code=401, detail="Session not found")

    task_ids = []
    for url in req.playlist_urls:
        url = url.strip()
        if not url:
            continue
        owner_id, playlist_id, _ = parse_playlist_url(url)
        if owner_id is None:
            continue
        task_id = str(uuid.uuid4())
        task = DownloadHistoryItem(id=task_id, session_id=req.session_id, playlist_url=url, download_type="playlist")
        doc = task.model_dump()
        await db.download_history.insert_one(doc)
        background_tasks.add_task(process_playlist_download, task_id, req.session_id, url, req.add_tags, req.add_lyrics, req.quality)
        task_ids.append(task_id)

    return {"task_ids": task_ids, "count": len(task_ids)}


@api_router.post("/download/track")
async def start_track_download(req: TrackDownloadRequest, background_tasks: BackgroundTasks):
    if req.session_id not in vk_sessions:
        raise HTTPException(status_code=401, detail="Session not found")
    owner_id, audio_id = parse_track_url(req.track_url)
    if owner_id is None:
        raise HTTPException(status_code=400, detail="Invalid VK track URL")

    task_id = str(uuid.uuid4())
    task = DownloadHistoryItem(id=task_id, session_id=req.session_id, playlist_url=req.track_url, download_type="track")
    doc = task.model_dump()
    await db.download_history.insert_one(doc)
    background_tasks.add_task(process_track_download, task_id, req.session_id, req.track_url, req.add_tags, req.add_lyrics, req.quality)
    return {"task_id": task_id, "status": "pending"}


@api_router.post("/download/my-music")
async def start_my_music_download(req: MyMusicDownloadRequest, background_tasks: BackgroundTasks):
    if req.session_id not in vk_sessions:
        raise HTTPException(status_code=401, detail="Session not found")

    task_id = str(uuid.uuid4())
    task = DownloadHistoryItem(id=task_id, session_id=req.session_id, playlist_url="my_music", download_type="my_music")
    doc = task.model_dump()
    await db.download_history.insert_one(doc)
    background_tasks.add_task(process_my_music_download, task_id, req.session_id, req.add_tags, req.add_lyrics, req.quality)
    return {"task_id": task_id, "status": "pending"}


@api_router.post("/download/cancel/{task_id}")
async def cancel_download(task_id: str):
    task = await db.download_history.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("status") in ("completed", "error", "cancelled"):
        return {"status": "already_finished"}
    active_cancel_flags[task_id] = True
    await update_task_status(task_id, "cancelling", current_track="Cancelling...")
    return {"status": "cancelling"}


@api_router.get("/download/status/{task_id}")
async def get_download_status(task_id: str):
    task = await db.download_history.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@api_router.get("/download/history/{session_id}")
async def get_download_history(session_id: str):
    tasks = await db.download_history.find({"session_id": session_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return tasks


@api_router.get("/download/active/{session_id}")
async def get_active_downloads(session_id: str):
    tasks = await db.download_history.find(
        {"session_id": session_id, "status": {"$in": ["pending", "downloading", "zipping", "uploading", "cancelling"]}},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return tasks


@api_router.delete("/download/{task_id}")
async def delete_download(task_id: str):
    await db.download_history.delete_one({"id": task_id})
    return {"status": "ok"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    for proxy_id in list(xray_processes.keys()):
        await stop_xray_for_proxy(proxy_id)
    client.close()
