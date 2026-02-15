# VK Music Saver — Полная техническая документация

## Содержание

1. [Обзор архитектуры](#1-обзор-архитектуры)
2. [Backend (FastAPI)](#2-backend-fastapi)
3. [Frontend (React)](#3-frontend-react)
4. [Система прокси](#4-система-прокси)
5. [Процесс скачивания](#5-процесс-скачивания)
6. [API Reference](#6-api-reference)
7. [База данных](#7-база-данных)
8. [Деплой и настройка](#8-деплой-и-настройка)

---

## 1. Обзор архитектуры

### Общая схема

```
┌─────────────┐    HTTP     ┌─────────────┐    MongoDB    ┌─────────────┐
│   React     │ ◄─────────► │   FastAPI   │ ◄───────────► │   MongoDB   │
│  Frontend   │             │   Backend   │               │  Database   │
└─────────────┘             └──────┬──────┘               └─────────────┘
                                   │
                                   │ VK API + Proxy
                                   ▼
                           ┌─────────────────┐
                           │  VK API Server  │
                           │  + TempShare    │
                           └─────────────────┘
```

### Технологии

| Компонент | Технология | Версия |
|-----------|------------|--------|
| Backend | FastAPI + uvicorn | 0.100+ |
| Frontend | React + Tailwind CSS | 18+ |
| Database | MongoDB + Motor | 6+ |
| HTTP Client | aiohttp + aiohttp-socks | 3.9+ |
| VLESS Proxy | Xray-core | 25.6+ |
| Аудио теги | mutagen | 1.47+ |

---

## 2. Backend (FastAPI)

### Файл: `backend/server.py`

### 2.1 Инициализация и конфигурация

```python
# Основные константы
KATE_USER_AGENT = "KateMobileAndroid/56 lite-460 (Android 4.4.2; SDK 19; x86; unknown Android SDK built for x86; en)"
TEMPSHARE_MAX_SIZE = 2 * 1024 * 1024 * 1024  # 2GB - максимум для TempShare
CHUNK_SIZE_LIMIT = 1 * 1024 * 1024 * 1024    # 1GB - порог для чанковой загрузки
CONCURRENT_DOWNLOADS = 8                      # Параллельных загрузок

# Директории
DOWNLOAD_DIR = Path("/tmp/vk_downloads")      # Временные файлы
XRAY_CONFIG_DIR = Path("/tmp/xray_configs")   # Конфиги Xray
XRAY_BIN = "/usr/local/bin/xray"              # Путь к Xray
```

### 2.2 Модели данных (Pydantic)

#### Запросы

```python
class VkTokenLoginRequest(BaseModel):
    """Авторизация по токену VK"""
    token: str = Field(..., min_length=1)

class PlaylistDownloadRequest(BaseModel):
    """Скачивание плейлиста"""
    session_id: str
    playlist_url: str
    add_tags: bool = False      # Добавлять ID3 теги
    add_lyrics: bool = False    # Добавлять тексты
    quality: str = "high"       # low/medium/high (128/256/320 kbps)

class MultiPlaylistDownloadRequest(BaseModel):
    """Массовое скачивание плейлистов"""
    session_id: str
    playlist_urls: List[str]    # Список URL
    add_tags: bool = False
    add_lyrics: bool = False
    quality: str = "high"

class TrackDownloadRequest(BaseModel):
    """Скачивание одного трека"""
    session_id: str
    track_url: str
    add_tags: bool = False
    add_lyrics: bool = False
    quality: str = "high"

class MyMusicDownloadRequest(BaseModel):
    """Скачивание всей библиотеки пользователя"""
    session_id: str
    add_tags: bool = False
    add_lyrics: bool = False
    quality: str = "high"

class ProxyAddRequest(BaseModel):
    """Добавление прокси"""
    proxy_type: str  # http, socks5, vless
    address: str     # Адрес или URI
    name: str = ""   # Название (опционально)
```

#### История загрузок

```python
class DownloadHistoryItem(BaseModel):
    """Запись в истории загрузок"""
    id: str                     # UUID задачи
    session_id: str             # ID сессии VK
    playlist_url: str = ""      # URL плейлиста/трека
    playlist_title: str = ""    # Название
    track_count: int = 0        # Всего треков
    downloaded_count: int = 0   # Скачано треков
    status: str = "pending"     # Статус (см. ниже)
    progress: float = 0.0       # Прогресс 0-100%
    current_track: str = ""     # Текущий трек
    download_url: str = ""      # Ссылка на скачивание
    download_urls: List[str] = []  # Ссылки на части (если >2GB или чанки)
    error_message: str = ""     # Сообщение об ошибке
    download_type: str = "playlist"  # playlist/track/my_music
    file_size: str = ""         # Размер файла (форматированный)
    created_at: str             # Время создания (ISO 8601)
    completed_at: str = ""      # Время завершения (ISO 8601)
```

#### Статусы задач

| Статус | Описание |
|--------|----------|
| `pending` | В очереди |
| `downloading` | Скачивание треков |
| `zipping` | Создание ZIP архива |
| `uploading` | Загрузка на TempShare |
| `completed` | Завершено |
| `error` | Ошибка |
| `cancelling` | Отмена в процессе |
| `cancelled` | Отменено |

### 2.3 VK API Интеграция

```python
async def vk_api_method(token, method, **params):
    """Универсальный вызов VK API
    
    Автоматически:
    - Добавляет access_token и версию API (5.131)
    - Использует активный прокси (если настроен)
    - Использует User-Agent Kate Mobile
    """
    params["access_token"] = token
    params["v"] = "5.131"
    proxy_doc = await get_active_proxy()
    proxy_url = build_proxy_url(proxy_doc) if proxy_doc else None
    return await make_request_with_proxy("GET", f"https://api.vk.com/method/{method}", 
                                         proxy_url=proxy_url, params=params)

async def get_all_audio(token, owner_id=None, album_id=None, access_key=None):
    """Получение всех треков (с пагинацией)
    
    VK возвращает максимум 200 треков за запрос.
    Функция автоматически делает несколько запросов.
    """
    all_tracks = []
    offset = 0
    batch_size = 200
    while True:
        result = await vk_api_method(token, "audio.get", 
                                     count=batch_size, offset=offset, ...)
        items = result.get("items", [])
        all_tracks.extend(items)
        offset += batch_size
        if not items or offset >= result.get("count", 0):
            break
        await asyncio.sleep(0.35)  # Задержка между запросами
    return all_tracks
```

### 2.4 Парсинг URL

```python
def parse_playlist_url(url):
    """Извлечение owner_id, playlist_id, access_key из URL
    
    Поддерживаемые форматы:
    - audio_playlist-2001234567_12345678/abc123def
    - audio_playlist-2001234567_12345678
    - playlist/-2001234567_12345678_abc123def
    - playlist/-2001234567_12345678
    
    Returns: (owner_id: int, playlist_id: int, access_key: str|None)
    """

def parse_track_url(url):
    """Извлечение owner_id, audio_id из URL трека
    
    Форматы:
    - audio-2001234567_456239017
    - audio_id=-2001234567_456239017
    
    Returns: (owner_id: int, audio_id: int)
    """
```

### 2.5 Обработка имён файлов

```python
# Имена файлов ограничены 200 символами для совместимости с файловыми системами
# Linux поддерживает до 255 байт, но UTF-8 символы могут занимать до 4 байт
safe_name = re.sub(r'[<>:"/\\|?*]', '_', f"{track_idx+1:03d}. {artist} - {track_title}")[:200]
```

---

## 3. Frontend (React)

### Файл: `frontend/src/App.js`

### 3.1 Структура компонентов

```
App
├── LoginPage          # Страница авторизации
│   └── Token Login    # Форма ввода токена
│
├── Dashboard          # Главная панель
│   ├── Header         # Шапка с навигацией
│   ├── DownloadSection  # Форма скачивания
│   │   ├── ModeSelector   # Выбор режима
│   │   ├── UrlInput       # Ввод URL
│   │   └── OptionsPanel   # Настройки (теги, качество)
│   ├── ActiveDownloads    # Активные загрузки
│   └── HistorySection     # История
│
├── ProxySettings      # Модальное окно прокси
│   ├── ProxyList      # Список прокси
│   ├── AddProxyForm   # Форма добавления
│   └── ProxyStatusBadge  # Статус прокси
│
└── DownloadItem       # Карточка задачи
    ├── StatusIcon     # Иконка статуса
    ├── ProgressBar    # Прогресс-бар
    └── ActionButtons  # Кнопки действий
```

### 3.2 Состояние приложения

```javascript
// Авторизация
const [sessionId, setSessionId] = useState(() => 
    localStorage.getItem("vk_session_id") || ""
);
const [user, setUser] = useState(() => {
    const stored = localStorage.getItem("vk_user");
    return stored ? JSON.parse(stored) : null;
});

// Режимы скачивания
const modes = [
    { id: "playlist", label: "Плейлист" },
    { id: "track", label: "Трек" },
    { id: "my_music", label: "Моя музыка" },
    { id: "multi", label: "Несколько" },
];

// Опции скачивания
const [addTags, setAddTags] = useState(false);     // ID3 теги
const [addLyrics, setAddLyrics] = useState(false); // Тексты
const [quality, setQuality] = useState("high");    // 128/256/320
```

### 3.3 Обновление статуса в реальном времени

```javascript
useEffect(() => {
    fetchTasks();  // Начальная загрузка
    const interval = setInterval(fetchTasks, 2000);  // Каждые 2 сек
    return () => clearInterval(interval);
}, [sessionId]);

const fetchTasks = async () => {
    const [activeRes, historyRes] = await Promise.all([
        axios.get(`${API}/download/active/${sessionId}`),
        axios.get(`${API}/download/history/${sessionId}`)
    ]);
    // Объединение активных и завершённых задач
};
```

---

## 4. Система прокси

### 4.1 Типы прокси

| Тип | Формат адреса | Пример | Требует Xray |
|-----|---------------|--------|---------------|
| HTTP | `ip:port` или `user:pass@ip:port` | `192.168.1.1:8080` | Нет |
| SOCKS5 | `ip:port` или `user:pass@ip:port` | `192.168.1.1:1080` | Нет |
| VLESS | Full URI | `vless://uuid@server:443?type=tcp&security=tls...` | **Да** |

### 4.2 Проверка Xray

Перед запуском VLESS прокси система проверяет наличие Xray:

```python
def check_xray_available():
    """Проверка наличия и прав Xray
    
    Raises:
        FileNotFoundError: если Xray не найден по пути /usr/local/bin/xray
        PermissionError: если Xray не имеет прав на выполнение
    """
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
```

### 4.3 VLESS через Xray

Для VLESS прокси используется локальный Xray процесс:

```python
async def start_xray_for_proxy(proxy_id: str, vless_uri: str):
    """Запуск Xray для VLESS прокси
    
    1. Проверяет наличие Xray
    2. Парсит VLESS URI
    3. Генерирует конфиг Xray
    4. Запускает процесс Xray
    5. Возвращает локальный SOCKS5 порт
    """
    check_xray_available()  # Проверка перед запуском
    vless_params = parse_vless_uri(vless_uri)
    local_port = find_free_port()
    config = generate_xray_config(vless_params, local_port)
    
    # Запуск Xray как подпроцесса
    process = subprocess.Popen(
        [XRAY_BIN, "run", "-c", config_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        preexec_fn=os.setsid  # Для корректного завершения
    )
    
    return {"port": local_port, "status": "running"}
```

### 4.4 Парсинг VLESS URI

```python
def parse_vless_uri(uri: str) -> dict:
    """Парсинг VLESS URI
    
    Формат: vless://uuid@host:port?params#fragment
    
    Возвращает:
    {
        "uuid": "...",
        "host": "server.com",
        "port": 443,
        "type": "tcp",           # tcp, ws, grpc, xhttp
        "security": "tls",       # none, tls, reality
        "sni": "...",
        "fp": "chrome",          # fingerprint
        "pbk": "...",            # public key (reality)
        "sid": "...",            # short id (reality)
        "flow": "...",           # flow control
        ...
    }
    """
```

### 4.5 Проверка прокси

```python
async def test_proxy_connectivity(proxy_url: str, timeout: int = 10):
    """Проверка работоспособности прокси
    
    1. Запрос к VK API
    2. Получение внешнего IP
    3. Измерение задержки
    
    Returns:
    {
        "success": True/False,
        "latency_ms": 150,
        "ip": "1.2.3.4",
        "vk_accessible": True
    }
    """
```

---

## 5. Процесс скачивания

### 5.1 Диаграмма процесса (стандартный)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ 1. Pending  │ ──► │ 2. Download │ ──► │ 3. Zipping  │
│   0%        │     │   0-80%     │     │   80-88%    │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
                    ┌─────────────┐     ┌─────────────┐
                    │ 5. Complete │ ◄── │ 4. Upload   │
                    │   100%      │     │   88-100%   │
                    └─────────────┘     └─────────────┘
```

### 5.2 Чанковая загрузка (для больших библиотек)

Для больших коллекций (>1 ГБ) используется чанковая загрузка для экономии места на диске:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Download    │ ──► │ Chunk ~1GB  │ ──► │ Zip & Upload│
│ Tracks      │     │ reached     │     │ chunk       │
└─────────────┘     └─────────────┘     └──────┬──────┘
       ▲                                       │
       │                                       │
       └───────────── Clean cache ◄────────────┘
                     Continue download
```

**Алгоритм:**
1. Скачиваем треки параллельно (до 8 одновременно)
2. Когда накопленный размер достигает ~1 ГБ:
   - Останавливаем скачивание
   - Создаём ZIP архив текущей части
   - Загружаем на TempShare
   - Очищаем временные файлы
   - Продолжаем скачивание оставшихся треков
3. Повторяем до конца плейлиста
4. В результате: несколько ссылок в `download_urls`

### 5.3 Параллельное скачивание

```python
async def download_tracks_batch(task_id, token, tracks, title, ...):
    """Скачивание треков с семафором и чанкованием"""
    
    semaphore = asyncio.Semaphore(CONCURRENT_DOWNLOADS)  # Max 8
    
    async def download_one(i, track):
        async with semaphore:  # Ограничение параллельности
            success = await download_track_file(session, url, filepath)
            if success:
                downloaded_count += 1
                # Обновление прогресса
    
    # Скачиваем батчами, проверяя размер после каждого
    while i < len(valid_tracks):
        # Скачиваем CONCURRENT_DOWNLOADS треков
        batch_tasks = [download_one(j, track) for j, track in batch]
        await asyncio.gather(*batch_tasks)
        
        # Если накопили ~1GB - создаём чанк
        if chunk_size >= CHUNK_SIZE_LIMIT:
            await create_and_upload_chunk()
            clear_temp_files()
```

### 5.4 Разделение больших архивов

```python
def split_zip_files(zip_path, max_size=TEMPSHARE_MAX_SIZE):
    """Разделение ZIP >2GB на части
    
    Алгоритм:
    1. Проверить размер исходного ZIP
    2. Если <= 2GB, вернуть как есть
    3. Иначе:
       - Читать файлы из ZIP
       - Добавлять в новый part_N.zip
       - Когда размер ~95% от лимита, начать новую часть
    
    Returns: ['file_part1.zip', 'file_part2.zip', ...]
    """
    file_size = os.path.getsize(zip_path)
    if file_size <= max_size:
        return [zip_path]
    
    # Разделение на части по ~95% от лимита
    parts = []
    current_size = 0
    current_names = []
    
    for name in src_zip.namelist():
        entry_size = src_zip.getinfo(name).compress_size + 100
        
        if current_size + entry_size > max_size * 0.95:
            # Создать новую часть
            create_part_zip(current_names)
            current_names = []
            current_size = 0
        
        current_names.append(name)
        current_size += entry_size
    
    return parts
```

### 5.5 ID3 теги

```python
async def apply_id3_tags(filepath, track, cover_data=None, lyrics_text=None):
    """Добавление метаданных в MP3
    
    Теги:
    - TIT2: Название трека
    - TPE1: Исполнитель
    - TALB: Альбом
    - APIC: Обложка (JPEG)
    - USLT: Текст песни (язык: rus)
    """
    audio = MP3(filepath, ID3=ID3)
    audio.tags.add(TIT2(encoding=3, text=[track['title']]))
    audio.tags.add(TPE1(encoding=3, text=[track['artist']]))
    
    if cover_data:
        audio.tags.add(APIC(encoding=3, mime='image/jpeg', 
                           type=3, desc='Cover', data=cover_data))
    
    if lyrics_text:
        audio.tags.add(USLT(encoding=3, lang='rus', desc='', text=lyrics_text))
    
    audio.save()
```

---

## 6. API Reference

### 6.1 Авторизация

#### POST `/api/vk/token-login`

Авторизация по токену VK.

**Request:**
```json
{
    "token": "vk1.a.xxx..."
}
```

**Response (200):**
```json
{
    "status": "success",
    "session_id": "uuid-session-id",
    "user": {
        "first_name": "Иван",
        "last_name": "Иванов",
        "photo": "https://..."
    }
}
```

**Response (401):**
```json
{
    "detail": "Invalid or expired token"
}
```

#### POST `/api/vk/logout`

Выход из сессии.

**Request:**
```json
{
    "session_id": "uuid"
}
```

**Response:**
```json
{
    "status": "ok"
}
```

### 6.2 Скачивание

#### POST `/api/download/start`

Скачивание плейлиста.

**Request:**
```json
{
    "session_id": "uuid",
    "playlist_url": "https://vk.com/music?z=audio_playlist-123_456/xxx",
    "add_tags": true,
    "add_lyrics": false,
    "quality": "high"
}
```

**Response:**
```json
{
    "task_id": "uuid-task-id",
    "status": "pending"
}
```

#### POST `/api/download/track`

Скачивание одного трека.

**Request:**
```json
{
    "session_id": "uuid",
    "track_url": "https://vk.com/audio-123_456789",
    "add_tags": true,
    "add_lyrics": false,
    "quality": "high"
}
```

**Response:**
```json
{
    "task_id": "uuid-task-id",
    "status": "pending"
}
```

#### POST `/api/download/my-music`

Скачивание всей библиотеки пользователя.

**Request:**
```json
{
    "session_id": "uuid",
    "add_tags": true,
    "add_lyrics": false,
    "quality": "high"
}
```

**Response:**
```json
{
    "task_id": "uuid-task-id",
    "status": "pending"
}
```

#### POST `/api/download/multi`

Скачивание нескольких плейлистов.

**Request:**
```json
{
    "session_id": "uuid",
    "playlist_urls": [
        "https://vk.com/music?z=audio_playlist-123_456",
        "https://vk.com/music?z=audio_playlist-123_789"
    ],
    "add_tags": true,
    "add_lyrics": false,
    "quality": "high"
}
```

**Response:**
```json
{
    "task_ids": ["uuid-1", "uuid-2"],
    "count": 2
}
```

#### GET `/api/download/status/{task_id}`

Получение статуса задачи.

**Response:**
```json
{
    "id": "uuid",
    "status": "downloading",
    "progress": 45.5,
    "current_track": "Artist - Title",
    "track_count": 100,
    "downloaded_count": 45,
    "playlist_title": "My Playlist",
    "download_type": "playlist",
    "download_url": "",
    "download_urls": []
}
```

#### POST `/api/download/cancel/{task_id}`

Отмена загрузки.

**Response:**
```json
{
    "status": "cancelling"
}
```

#### DELETE `/api/download/{task_id}`

Удаление задачи из истории.

**Response:**
```json
{
    "status": "ok"
}
```

#### GET `/api/download/history/{session_id}`

История загрузок пользователя.

**Response:**
```json
[
    {
        "id": "uuid",
        "status": "completed",
        "playlist_title": "My Playlist",
        "track_count": 100,
        "downloaded_count": 100,
        "download_url": "https://tempshare.su/xxx",
        "download_urls": ["https://tempshare.su/xxx"],
        "file_size": "1.5 GB",
        "created_at": "2024-01-01T12:00:00Z",
        "completed_at": "2024-01-01T12:30:00Z"
    }
]
```

#### GET `/api/download/active/{session_id}`

Активные загрузки пользователя.

**Response:**
```json
[
    {
        "id": "uuid",
        "status": "downloading",
        "progress": 45.5,
        "current_track": "Artist - Title"
    }
]
```

### 6.3 Прокси

#### GET `/api/proxies`

Список всех прокси.

**Response:**
```json
[
    {
        "id": "uuid",
        "proxy_type": "vless",
        "name": "My Proxy",
        "address": "vless://...",
        "enabled": true,
        "status": "ok",
        "status_message": "OK! Ping: 150ms | IP: 1.2.3.4",
        "check_latency": 150,
        "check_ip": "1.2.3.4",
        "xray_running": true,
        "xray_port": 10808
    }
]
```

#### POST `/api/proxies`

Добавление прокси.

**Request:**
```json
{
    "proxy_type": "vless",
    "address": "vless://uuid@server:443?...",
    "name": "My VLESS Proxy"
}
```

**Response:**
```json
{
    "id": "uuid",
    "proxy_type": "vless",
    "name": "My VLESS Proxy",
    "address": "vless://...",
    "enabled": false,
    "status": "unchecked"
}
```

#### POST `/api/proxies/{id}/toggle`

Включение/выключение прокси. При включении автоматически отключаются другие.

**Response:**
```json
{
    "id": "uuid",
    "enabled": true
}
```

#### POST `/api/proxies/{id}/check`

Проверка прокси.

**Response:**
```json
{
    "status": "ok",
    "message": "OK! Ping: 150ms | IP: 1.2.3.4",
    "ip": "1.2.3.4",
    "latency_ms": 150
}
```

#### DELETE `/api/proxies/{id}`

Удаление прокси.

**Response:**
```json
{
    "status": "ok"
}
```

---

## 7. База данных

### MongoDB Collections

#### `download_history`

```javascript
{
    "_id": ObjectId,
    "id": "uuid",           // Уникальный ID задачи
    "session_id": "uuid",   // Сессия пользователя
    "playlist_url": "...",
    "playlist_title": "...",
    "track_count": 100,
    "downloaded_count": 100,
    "status": "completed",
    "progress": 100.0,
    "current_track": "",
    "download_url": "https://tempshare.su/xxx",
    "download_urls": [],     // Части если >2GB или чанки
    "error_message": "",
    "file_size": "1.5 GB",
    "download_type": "playlist",  // playlist/track/my_music
    "created_at": "2024-01-01T12:00:00Z",
    "completed_at": "2024-01-01T12:30:00Z"
}
```

#### `proxies`

```javascript
{
    "_id": ObjectId,
    "id": "uuid",
    "proxy_type": "vless",   // http, socks5, vless
    "address": "vless://...",
    "name": "My Proxy",
    "enabled": false,
    "status": "unchecked",   // unchecked, checking, ok, error
    "status_message": "",
    "check_ip": "",
    "check_latency": 0,
    "created_at": "2024-01-01T12:00:00Z",
    "last_check": ""
}
```

---

## 8. Деплой и настройка

### 8.1 Docker (опционально)

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Xray (для VLESS прокси)
RUN apt-get update && apt-get install -y curl unzip \
    && curl -sL https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip -o xray.zip \
    && unzip xray.zip -d /usr/local/bin/ \
    && chmod +x /usr/local/bin/xray \
    && rm xray.zip \
    && apt-get clean

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
```

### 8.2 Nginx конфигурация

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
    }

    # Backend API
    location /api {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 8.3 Systemd сервисы

```ini
# /etc/systemd/system/vk-music-backend.service
[Unit]
Description=VK Music Saver Backend
After=network.target mongodb.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/vk-music-saver/backend
EnvironmentFile=/var/www/vk-music-saver/backend/.env
ExecStart=/usr/bin/python3 -m uvicorn server:app --host 0.0.0.0 --port 8001
Restart=always

[Install]
WantedBy=multi-user.target
```

### 8.4 Переменные окружения

| Переменная | Backend | Frontend | Описание |
|------------|---------|----------|----------|
| `MONGO_URL` | ✓ | | MongoDB connection string |
| `DB_NAME` | ✓ | | Название базы данных |
| `CORS_ORIGINS` | ✓ | | Разрешённые origins |
| `REACT_APP_BACKEND_URL` | | ✓ | URL бэкенда |
| `WDS_SOCKET_PORT` | | ✓ | Порт для WebSocket DevServer |

---

## Приложение: Ограничения и лимиты

| Параметр | Значение | Описание |
|----------|----------|----------|
| Максимальный размер файла TempShare | 2 ГБ | Автоматическое разделение |
| Порог чанковой загрузки | 1 ГБ | Создание промежуточных архивов |
| Параллельных загрузок | 8 | Ограничено семафором |
| Длина имени файла | 200 символов | Совместимость с FS |
| Время хранения на TempShare | 7 дней | |
| Лимит загрузок | Нет | |
| API endpoint TempShare | `https://api.tempshare.su/upload` | |
| Путь к Xray | `/usr/local/bin/xray` | Только для VLESS |

---

## Changelog

### Последние изменения

- **Чанковая загрузка**: добавлена для экономии дискового пространства (порог 1 ГБ)
- **Лимит имени файла**: ограничен 200 символами для совместимости с файловыми системами
- **Проверка Xray**: добавлена проверка наличия и прав перед запуском VLESS прокси
- **Новые эндпоинты**: `DELETE /api/download/{task_id}`, `DELETE /api/proxies/{id}`
