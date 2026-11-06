import asyncio
import hashlib
import inspect
import json
import os
import re
import shutil
import resource
import signal
import subprocess
import sys
import time
import traceback
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone

from vplus import VPlusClient, Filters, Update

# ───────────────────────── تنظیمات ─────────────────────────

SOROUSH_BOT_TOKEN = os.environ.get("SOROUSH_BOT_TOKEN") or "70904265:t9D0f47anBR7H7ctvLqSm_Itzzmsu-A-iUU"
ADMIN_ID = 66009832

PORT = int(os.environ.get("PORT", "10000"))
PING_URL = os.environ.get("RENDER_EXTERNAL_URL", "") or os.environ.get("PING_URL", "")
PING_INTERVAL = 240

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "host_data")
USERS_DIR = os.path.join(DATA_DIR, "users")
STATE_FILE = os.path.join(DATA_DIR, "host_state.json")
TMP_DIR = os.path.join(DATA_DIR, "tmp")
LOGS_DIR = os.path.join(DATA_DIR, "logs")  # لاگ‌ها بیرون از پوشه‌ی کاربر نگه داشته میشن
for _d in (DATA_DIR, USERS_DIR, TMP_DIR, LOGS_DIR):
    os.makedirs(_d, exist_ok=True)

MAX_UPLOAD_MB = 50
MAX_UNZIP_MB = 200
MAX_ZIP_FILES = 3000
MAX_LOG_BYTES = 512 * 1024  # سقف لاگ هر کاربر؛ بیشتر شد ریست میشه
LOG_CHECK_INTERVAL = 60
MAX_CACHE_MB = 50          # سقف __pycache__ هر کاربر بر حسب مگابایت
CACHE_CLEAN_INTERVAL = 3600  # هر یک ساعت یک‌بار پاکسازی کش
LOG_TAIL_LINES = 30
CONSOLE_INTERVAL = 2.5      # فاصله‌ی چک خروجی جدید برای کنسول (ثانیه)
CONSOLE_VIEW_CHARS = 3000   # حداکثر طول متن کنسول
CONSOLE_MAX_INPUT = 1000
USERS_PER_PAGE = 8
MESSAGE_LIMIT = 3500
PIP_TIMEOUT = 300
STOP_GRACE = 5
BROADCAST_DELAY = 0.15
ENTRY_NAME = "main.py"  # تنها فایلی که اجرا میشه
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))

DIVIDER = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
SOFT = "· · · · · · · · · · · ·"

ST_ON = "🟢 روشن"
ST_OFF = "🔴 خاموش"


def card(icon: str, title: str, rows=(), footer: str = "") -> str:
    """قالب یکدست همه‌ی پیام‌ها: تیتر، خط جداکننده، ردیف‌ها، و در انتها راهنمایی."""
    out = [f"{icon} {title}", DIVIDER]
    out.extend(r for r in rows if r is not None)
    if footer:
        out += [SOFT, footer]
    return "\n".join(out)


def kv(icon: str, label: str, value) -> str:
    return f"{icon} {label}: {value}"

# ───────────────────────── دکمه‌ها ─────────────────────────

BTN_SEND = "📤 ارسال zip / py"
BTN_START = "▶️ استارت"
BTN_STOP = "⏹ استوپ"
BTN_RESTART = "🔄 ری‌استارت"
BTN_STATUS = "📊 وضعیت"
BTN_LOG = "📜 لاگ اسکریپت"
BTN_FILES = "📦 فایل‌های من"
BTN_BACKUP = "💾 بکاپ"
BTN_CONSOLE = "💻 کنسول"
BTN_CLOSE_CONSOLE = "🔙 بستن کنسول"
BTN_DELETE = "🗑 حذف اسکریپت"
BTN_HELP = "❕ راهنما"
BTN_ADMIN = "🛠 مدیریت"
BTN_MENU = "🏠 منوی اصلی"
BTN_CANCEL = "❌ انصراف"
BTN_YES = "✅ بله، مطمئنم"
BTN_NO = "❌ نه، بی‌خیال"

ADM_USERS = "👥 لیست کاربرها"
ADM_STATS = "📈 آمار سرور"
ADM_RUNNING = "🟢 اسکریپت‌های روشن"
ADM_STOPALL = "🛑 توقف همه‌ی اسکریپت‌ها"
ADM_BROADCAST = "📢 پیام همگانی"
ADM_SEARCH = "🔍 جستجوی کاربر"
ADM_BACK = "🔙 خروج از مدیریت"
ADM_SEND = "✅ ارسال"
ADM_CANCEL = "❌ لغو"
ADM_NEXT = "➡️ صفحه‌ی بعد"
ADM_PREV = "⬅️ صفحه‌ی قبل"
ADM_LIST_BACK = "🔙 لیست کاربرها"
ADM_PANEL_BACK = "🔙 پنل مدیریت"

T_ZIP = "📥 دریافت zip کاربر"
T_PY = "📄 دریافت py کاربر"
T_START = "▶️ استارت کاربر"
T_STOP = "⏹ استوپ کاربر"
T_LOG = "📜 لاگ کاربر"
T_RESET = "♻️ ریست حافظه‌ی کاربر"
T_BAN = "🚫 مسدود کردن کاربر"
T_UNBAN = "✅ رفع مسدودی کاربر"
T_MSG = "✉️ پیام به کاربر"

USER_BTN_RE = re.compile(r"•\s*(\d+)\s*$")

# ───────────────────────── ابزارهای کوچک ─────────────────────────


def fa(n) -> str:
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def gregorian_to_jalali(gy: int, gm: int, gd: int):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def fmt_time(ts) -> str:
    if not ts:
        return "—"
    try:
        local = datetime.fromtimestamp(float(ts), IRAN_TZ)
        jy, jm, jd = gregorian_to_jalali(local.year, local.month, local.day)
        return fa(f"{jy}/{jm:02d}/{jd:02d} - {local.strftime('%H:%M')}")
    except Exception:
        return "—"


def fmt_size(num_bytes) -> str:
    num_bytes = int(num_bytes or 0)
    if num_bytes >= 1024 * 1024:
        return f"{fa(round(num_bytes / (1024 * 1024), 1))} مگابایت"
    return f"{fa(max(1, round(num_bytes / 1024)))} کیلوبایت"


def fmt_dur(seconds) -> str:
    seconds = int(max(0, seconds))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{fa(d)} روز")
    if h:
        parts.append(f"{fa(h)} ساعت")
    if m:
        parts.append(f"{fa(m)} دقیقه")
    if not parts:
        parts.append(f"{fa(s)} ثانیه")
    return " و ".join(parts[:2])


def _g(obj, *names):
    if obj is None:
        return None
    for n in names:
        v = obj.get(n) if isinstance(obj, dict) else getattr(obj, n, None)
        if v is not None and not callable(v):
            return v
    return None


async def _maybe_await(x):
    if hasattr(x, "__await__"):
        return await x
    return x


def split_text(text: str, limit: int = MESSAGE_LIMIT) -> list:
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks


# ───────────────────────── وضعیت و ذخیره‌سازی ─────────────────────────

bot = VPlusClient(token=SOROUSH_BOT_TOKEN)

users: dict = {}
procs: dict = {}
upload_state: set = set()
confirm_state: dict = {}
admin_state: dict = {}
user_locks: dict = {}
_seen_msgs: dict = {}
_tasks: set = set()
_shutting_down = False
console_state: dict = {}   # uid -> {"chat_id", "mid", "notice", "task"}


def spawn(coro):
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


def save_state():
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"users": {str(k): v for k, v in users.items()}}, f, ensure_ascii=False)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        print(f"⚠️ ذخیره‌ی وضعیت نشد: {type(e).__name__}: {e}")


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for k, v in (raw.get("users") or {}).items():
            users[int(k)] = v
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"⚠️ خوندن وضعیت نشد: {type(e).__name__}: {e}")


def user_dir(uid: int) -> str:
    return os.path.join(USERS_DIR, str(uid))


def code_dir(uid: int) -> str:
    return os.path.join(user_dir(uid), "code")


def log_path(uid: int) -> str:
    return os.path.join(LOGS_DIR, f"{uid}.log")


def dir_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def full_name(u: dict) -> str:
    name = " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x).strip()
    return name or u.get("username") or f"کاربر {u.get('id')}"


def touch_user(user, chat_id: int) -> dict:
    uid = int(_g(user, "id"))
    u = users.get(uid)
    new = u is None
    if new:
        u = {"id": uid, "joined": time.time(), "banned": False, "script": None,
             "was_running": False, "starts": 0, "uploads": 0, "last_exit": None, "pid": None}
        users[uid] = u
    changed = new
    for key, names in (("first_name", ("first_name", "name")), ("last_name", ("last_name",)),
                       ("username", ("username",)), ("phone", ("phone", "phone_number"))):
        val = _g(user, *names)
        if val is not None and str(val) != str(u.get(key) or ""):
            u[key] = str(val)
            changed = True
    if u.get("chat_id") != chat_id:
        u["chat_id"] = chat_id
        changed = True
    u["last_seen"] = time.time()
    if changed or (time.time() - u.get("_saved", 0) > 60):
        u["_saved"] = time.time()
        save_state()
    return u


# ───────────────────────── ارسال پیام ─────────────────────────

async def plain_send(chat_id: int, text: str, **kwargs):
    try:
        return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except Exception as e:
        print(f"❌ send_message failed: {type(e).__name__}: {e}")
        return None


async def send_long(chat_id: int, text: str, **kwargs):
    chunks = split_text(text)
    for i, chunk in enumerate(chunks):
        await plain_send(chat_id, chunk, **(kwargs if i == len(chunks) - 1 else {}))


async def send_document_file(chat_id: int, path: str, caption: str = ""):
    try:
        with open(path, "rb") as doc_file:
            return await bot.send_document(chat_id=chat_id, document=doc_file, caption=caption)
    except Exception as e:
        print(f"❌ send_document failed: {type(e).__name__}: {e}")
        return None


# ───────────────────────── کیبوردها ─────────────────────────

def kb(rows: list) -> dict:
    return {"keyboard": [[{"text": t} for t in row] for row in rows], "resize_keyboard": True}


def kb_user_menu(user_id: int) -> dict:
    """فقط دکمه‌هایی که الان به کار میان نمایش داده میشن."""
    u = users.get(user_id) or {}
    if not u.get("script"):
        rows = [[BTN_SEND], [BTN_STATUS, BTN_HELP]]
    elif is_running(user_id):
        rows = [[BTN_SEND], [BTN_STOP, BTN_RESTART], [BTN_CONSOLE, BTN_STATUS],
                [BTN_LOG, BTN_FILES], [BTN_BACKUP, BTN_DELETE], [BTN_HELP]]
    else:
        rows = [[BTN_SEND], [BTN_START], [BTN_STATUS, BTN_LOG],
                [BTN_FILES, BTN_BACKUP], [BTN_DELETE, BTN_HELP]]
    if user_id == ADMIN_ID:
        rows.append([BTN_ADMIN])
    return kb(rows)


def kb_console() -> dict:
    return kb([[BTN_CLOSE_CONSOLE]])


def kb_after_upload() -> dict:
    return kb([[BTN_START], [BTN_SEND, BTN_MENU]])


def kb_cancel() -> dict:
    return kb([[BTN_CANCEL]])


def kb_confirm() -> dict:
    return kb([[BTN_YES, BTN_NO]])


def kb_admin_panel() -> dict:
    return kb([
        [ADM_USERS, ADM_SEARCH],
        [ADM_STATS, ADM_RUNNING],
        [ADM_BROADCAST, ADM_STOPALL],
        [ADM_BACK],
    ])


def kb_users_page(ids: list, page: int, pages: int) -> dict:
    rows = []
    row = []
    for uid in ids:
        u = users[uid]
        icon = "🚫" if u.get("banned") else ("🟢" if is_running(uid) else "👤")
        row.append(f"{icon} {full_name(u)[:18]} • {uid}")
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav = []
    if page > 0:
        nav.append(ADM_PREV)
    if page < pages - 1:
        nav.append(ADM_NEXT)
    if nav:
        rows.append(nav)
    rows.append([ADM_PANEL_BACK])
    return kb(rows)


def kb_target(uid: int) -> dict:
    banned = users.get(uid, {}).get("banned")
    return kb([
        [T_ZIP, T_PY],
        [T_START, T_STOP],
        [T_LOG, T_MSG],
        [T_RESET, T_UNBAN if banned else T_BAN],
        [ADM_LIST_BACK],
    ])


ADMIN_TEXTS = {
    BTN_ADMIN, ADM_USERS, ADM_STATS, ADM_RUNNING, ADM_STOPALL, ADM_BROADCAST, ADM_SEARCH,
    ADM_BACK, ADM_SEND, ADM_CANCEL, ADM_NEXT, ADM_PREV, ADM_LIST_BACK, ADM_PANEL_BACK,
    T_ZIP, T_PY, T_START, T_STOP, T_LOG, T_RESET, T_BAN, T_UNBAN, T_MSG,
}

# ───────────────────────── متن‌ها ─────────────────────────


def txt_welcome(name: str) -> str:
    return card("✨", f"سلام {name}، خوش اومدی!", [
        "🐍 اسکریپت پایتونت رو اینجا آنلاین و همیشه روشن نگه دار.",
        "",
        "1️⃣ فایل main.py یا zip رو بفرست توجه کن که حتما داخل فایل zip شما requirements.txt وجود داشته باشه✅",
        "2️⃣ دکمه‌ی ▶️ استارت رو بزن",
        "3️⃣ نتیجه رو از لاگ و کنسول زنده ببین",
    ], "👇 از منوی پایین شروع کن")


def txt_help() -> str:
    return card("❕", "راهنمای ربات", [
        "🎛 کنترل",
        "▶️ استارت · ⏹ استوپ · 🔄 ری‌استارت",
        "",
        "👀 نظارت",
        "📊 وضعیت · 📜 لاگ · 💻 کنسول زنده",
        "",
        "📦 فایل‌ها",
        "📦 فایل‌های من ← zip کد",
        "💾 بکاپ ← کل محیط (کد و دیتا)",
        "🗑 حذف ← پاک‌سازی کامل",
    ], f"💡 requirements.txt خودکار نصب میشه\n📏 حداکثر حجم فایل: {fa(MAX_UPLOAD_MB)} مگابایت")


def txt_upload_prompt() -> str:
    return card("📤", "ارسال اسکریپت", [
        "🐍 فایل main.py",
        "🗜 یا zip که main.py داخلش باشه",
        kv("📏", "حداکثر حجم", f"{fa(MAX_UPLOAD_MB)} مگابایت"),
    ], "👇 فایل رو همین‌جا بفرست")


# ───────────────────────── مدیریت فایل و zip ─────────────────────────

def safe_extract(zip_path: str, dest: str) -> int:
    real_dest = os.path.realpath(dest)
    os.makedirs(real_dest, exist_ok=True)
    count = 0
    total = 0
    limit = MAX_UNZIP_MB * 1024 * 1024
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("__MACOSX/") or name.endswith(".DS_Store"):
                continue
            target = os.path.realpath(os.path.join(real_dest, name))
            if target != real_dest and not target.startswith(real_dest + os.sep):
                raise ValueError("مسیر نامعتبر داخل zip")
            if info.is_dir() or name.endswith("/"):
                os.makedirs(target, exist_ok=True)
                continue
            count += 1
            if count > MAX_ZIP_FILES:
                raise ValueError("تعداد فایل‌های داخل zip خیلی زیاده")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                while True:
                    chunk = src.read(1024 * 256)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        raise ValueError("حجم بعد از استخراج خیلی زیاده")
                    dst.write(chunk)
    entries = [e for e in os.listdir(real_dest) if e != "__MACOSX"]
    if len(entries) == 1 and os.path.isdir(os.path.join(real_dest, entries[0])):
        inner = os.path.join(real_dest, entries[0])
        for item in os.listdir(inner):
            shutil.move(os.path.join(inner, item), os.path.join(real_dest, item))
        os.rmdir(inner)
    return count


def list_py(root: str) -> list:
    found = []
    for r, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "venv", ".venv", "node_modules")]
        for f in files:
            if f.endswith(".py"):
                found.append(os.path.relpath(os.path.join(r, f), root))
    return found


def find_entry(root: str):
    """فقط main.py؛ اگه چندتا بود نزدیک‌ترین به ریشه."""
    hits = [p for p in list_py(root) if os.path.basename(p) == ENTRY_NAME]
    hits.sort(key=lambda p: p.count(os.sep))
    return hits[0] if hits else None


def build_zip(src_dir: str, out_path: str, skip=("__pycache__",)):
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for r, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in skip and not os.path.islink(os.path.join(r, d))]
            for f in files:
                full = os.path.join(r, f)
                if os.path.islink(full) or not os.path.isfile(full):
                    continue
                try:
                    z.write(full, os.path.relpath(full, src_dir))
                except OSError:
                    continue  # فایلی که وسط بکاپ پاک/قفل شده رو رد کن


def safe_filename(name: str) -> str:
    base = os.path.basename((name or "").replace("\\", "/")) or "script.py"
    base = re.sub(r"[^\w.\-]", "_", base)
    return base[:80] or "script.py"


def wipe_user_data(uid: int):
    shutil.rmtree(user_dir(uid), ignore_errors=True)
    try:
        os.remove(log_path(uid))
    except OSError:
        pass


# ───────────────────────── گرفتن فایل از پیام ─────────────────────────

def get_doc(message):
    if message is None:
        return None
    for attr in ("document", "file", "attachment", "media", "doc"):
        obj = _g(message, attr)
        if obj is None or isinstance(obj, (str, bytes, int, float, bool, list)):
            continue
        name = _g(obj, "file_name", "filename", "name", "title")
        fid = _g(obj, "file_id", "id", "fid", "file_unique_id")
        url = _g(obj, "url", "file_url", "download_url", "link")
        size = _g(obj, "file_size", "size")
        if name or fid or url:
            return {"obj": obj, "name": str(name or ""), "fid": fid, "url": url, "size": size}
    return None


def _http_download(url: str, dest: str) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": "script-host-bot"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)
    return os.path.isfile(dest) and os.path.getsize(dest) > 0


def _absorb_result(res, dest: str) -> bool:
    if isinstance(res, (bytes, bytearray)):
        with open(dest, "wb") as f:
            f.write(res)
        return True
    if hasattr(res, "read"):
        data = res.read()
        if isinstance(data, (bytes, bytearray)):
            with open(dest, "wb") as f:
                f.write(data)
            return True
    if isinstance(res, str) and os.path.isfile(res):
        if os.path.abspath(res) != os.path.abspath(dest):
            shutil.move(res, dest)
        return True
    return os.path.isfile(dest) and os.path.getsize(dest) > 0


_REMOTE_NAMES = {"file_path", "remote_path", "remote", "url", "link", "src", "source"}
_DEST_NAMES = {"destination", "dest", "dest_path", "destination_path", "save_path", "save_to", "output",
               "output_path", "out", "out_path", "custom_path", "target", "target_path", "to",
               "local_path", "filepath", "filename", "path", "file_name", "dst"}


def _smart_kwargs(fn, fid, remote, dest):
    """از روی امضای تابع، آرگومان‌ها رو با اسم پارامترها پر می‌کنه."""
    params = list(inspect.signature(fn).parameters.values())
    kwargs = {}
    for p in params:
        if p.name == "self" or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        n = p.name.lower()
        if n in _DEST_NAMES:
            kwargs[p.name] = dest
        elif n in _REMOTE_NAMES:
            kwargs[p.name] = remote if remote is not None else fid
        elif n in ("file_id", "fid", "id", "file", "document", "media"):
            kwargs[p.name] = fid
        elif p.default is p.empty:
            raise TypeError(f"پارامتر ناشناخته: {p.name}")
    return kwargs


def _sig_str(fn) -> str:
    try:
        return str(inspect.signature(fn))
    except Exception:
        return "?"


def _candidate_urls(remote, fid) -> list:
    urls = []
    if isinstance(remote, str) and remote.startswith("http"):
        return [remote]
    bases = []
    for attr in ("base_url", "api_url", "_base_url", "_api_url", "base", "api_base", "url"):
        v = getattr(bot, attr, None)
        if isinstance(v, str) and v.startswith("http"):
            bases.append(v.rstrip("/"))
    for b in dict.fromkeys(bases):
        for tail in (remote, fid):
            if tail:
                tail = str(tail).lstrip("/")
                urls += [f"{b}/file/bot{SOROUSH_BOT_TOKEN}/{tail}", f"{b}/{tail}"]
    return urls


async def fetch_document(message, doc: dict, dest: str):
    errors = []
    loop = asyncio.get_running_loop()
    obj, fid, url = doc["obj"], doc["fid"], doc["url"]

    async def attempt(label, fn, *args, **kwargs):
        try:
            res = await _maybe_await(fn(*args, **kwargs))
            if _absorb_result(res, dest):
                return True, res
            return False, res
        except TypeError as e:
            errors.append(f"{label}: TypeError {str(e)[:80]}")
        except Exception as e:
            errors.append(f"{label}: {type(e).__name__}: {str(e)[:120]}")
        return False, None

    async def http(u):
        try:
            if await loop.run_in_executor(None, _http_download, u, dest):
                return True
        except Exception as e:
            errors.append(f"http {u[:60]}: {type(e).__name__}: {str(e)[:80]}")
        return False

    # ۱) لینک مستقیم داخل خود پیام
    if isinstance(url, str) and url.startswith("http") and await http(url):
        return True, ""

    # ۲) متدهای خود شیء فایل/پیام
    for holder in (obj, message):
        for mname in ("download", "download_to_drive", "download_media", "save"):
            fn = getattr(holder, mname, None)
            if not callable(fn):
                continue
            for args, kw in (((dest,), {}), ((), {"file_path": dest}), ((), {"path": dest}), ((), {})):
                ok, _ = await attempt(mname, fn, *args, **kw)
                if ok:
                    return True, ""

    if fid is None:
        return False, "; ".join(errors)[:400]

    # ۳) get_file → مسیر ریموت (مهم‌ترین قدم؛ download_file معمولاً file_path می‌خواد نه file_id)
    remote = None
    get_file = getattr(bot, "get_file", None)
    if callable(get_file):
        info = None
        for args, kw in (((fid,), {}), ((), {"file_id": fid})):
            try:
                info = await _maybe_await(get_file(*args, **kw))
                break
            except TypeError:
                continue
            except Exception as e:
                errors.append(f"get_file: {type(e).__name__}: {str(e)[:120]}")
                break
        if info is not None:
            try:
                if _absorb_result(info, dest):
                    return True, ""
            except Exception:
                pass
            remote = _g(info, "file_path", "path", "url", "file_url", "download_url", "link")
            if remote is not None:
                remote = str(remote)
            print(f"ℹ️ get_file → remote={remote!r} | info={repr(info)[:300]}")
            if remote and remote.startswith("http") and await http(remote):
                return True, ""

    # ۴) download_file / بقیه با امضای واقعی
    for mname in ("download_file", "download_media", "download_document", "get_file_content"):
        fn = getattr(bot, mname, None)
        if not callable(fn):
            continue
        # الف) بر اساس امضا
        try:
            kw = _smart_kwargs(fn, fid, remote, dest)
        except Exception as e:
            kw = None
            errors.append(f"{mname}{_sig_str(fn)}: {e}")
        if kw is not None:
            ok, res = await attempt(f"{mname}(smart)", fn, **kw)
            if ok:
                return True, ""
        # ب) حدس‌های موضعی؛ هم با file_path هم با file_id
        for first in dict.fromkeys(x for x in (remote, fid) if x):
            for args in ((first, dest), (first,)):
                ok, _ = await attempt(f"{mname}{args[:1]!r}"[:40], fn, *args)
                if ok:
                    return True, ""

    # ۵) ساخت URL دانلود از روی آدرس سرور
    for u in _candidate_urls(remote, fid):
        if await http(u):
            return True, ""

    # ── اطلاعات عیب‌یابی ──
    diag = []
    for mname in ("get_file", "download_file"):
        fn = getattr(bot, mname, None)
        if callable(fn):
            diag.append(f"{mname}{_sig_str(fn)}")
    diag.append(f"remote={remote!r} fid={str(fid)[:40]!r}")
    try:
        print("❌ دانلود ناموفق | doc:", repr(obj)[:400], "|", " | ".join(diag), "|", errors)
    except Exception:
        pass
    return False, " || ".join(diag + errors)[:900]



# ───────────────────────── اجرای اسکریپت‌ها ─────────────────────────

def is_running(uid: int) -> bool:
    rec = procs.get(uid)
    return bool(rec and rec["proc"].returncode is None)


_MASK_SALT = os.urandom(8)


def _mask(prefix: str) -> str:
    h = hashlib.sha256(_MASK_SALT + prefix.encode("utf-8", "ignore")).digest()
    return "/" + "".join(chr(97 + b % 26) for b in h[:10])


def hide_paths(text: str, uid: int) -> str:
    """مسیر واقعی پروژه/پوشه‌ی کاربر رو با چند حرف الکی عوض می‌کنه تا توی لاگ لو نره."""
    prefixes = []
    for p in (code_dir(uid), user_dir(uid), DATA_DIR, BASE_DIR):
        for q in (p, os.path.realpath(p)):
            if q and q not in prefixes:
                prefixes.append(q)
    for p in sorted(prefixes, key=len, reverse=True):
        text = text.replace(p, _mask(p))
    return text


def read_log_tail(uid: int, lines: int = LOG_TAIL_LINES, hide: bool = True) -> str:
    path = log_path(uid)
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 8000))
            data = f.read()
        text = data.decode("utf-8", errors="ignore")
        if hide:
            text = hide_paths(text, uid)
        return "\n".join(text.strip().splitlines()[-lines:])
    except Exception:
        return ""


def kill_stale(uid: int):
    u = users.get(uid) or {}
    pid = u.get("pid")
    if not pid:
        return
    try:
        cwd = os.path.realpath(f"/proc/{pid}/cwd")
        if cwd.startswith(os.path.realpath(code_dir(uid))):
            try:
                os.killpg(pid, signal.SIGKILL)
            except Exception:
                os.kill(pid, signal.SIGKILL)
    except Exception:
        pass
    u["pid"] = None


# ───────────────────────── ایزوله‌سازی اسکریپت کاربر ─────────────────────────

DEPS_DIRNAME = ".pydeps"
SCRIPT_MAX_FILE_MB = 200
SCRIPT_MAX_MEM_MB = int(os.environ.get("SCRIPT_MAX_MEM_MB", "0"))  # 0 = بدون سقف
_ENV_KEEP = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE")


def clean_env(uid: int) -> dict:
    env = {k: os.environ[k] for k in _ENV_KEEP if k in os.environ}
    cd = code_dir(uid)
    env.update({
        "HOME": cd,
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": os.path.join(cd, DEPS_DIRNAME),
        "PIP_NO_CACHE_DIR": "1",
    })
    return env


def _limits():
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        fs = SCRIPT_MAX_FILE_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (fs, fs))
        if SCRIPT_MAX_MEM_MB:
            m = SCRIPT_MAX_MEM_MB * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (m, m))
    except Exception:
        pass


async def spawn_script(uid: int, argv: list, cwd: str, stdout, stdin=asyncio.subprocess.DEVNULL):
    return await asyncio.create_subprocess_exec(
        *argv, cwd=cwd, stdout=stdout, stderr=asyncio.subprocess.STDOUT,
        stdin=stdin, start_new_session=True, env=clean_env(uid), preexec_fn=_limits)


async def install_requirements(uid: int):
    root = code_dir(uid)
    req = None
    for r, _dirs, files in os.walk(root):
        if "requirements.txt" in files:
            req = os.path.join(r, "requirements.txt")
            break
    if not req:
        return None
    proc = None
    try:
        deps = os.path.join(root, DEPS_DIRNAME)
        argv = [sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                "--no-cache-dir", "--target", deps, "-r", req]
        proc = await spawn_script(uid, argv, root, asyncio.subprocess.PIPE)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=PIP_TIMEOUT)
        return proc.returncode == 0
    except Exception as e:
        print(f"⚠️ pip install failed: {type(e).__name__}: {e}")
        if proc is not None and proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass
        return False


async def start_script(uid: int):
    u = users.get(uid)
    sc = (u or {}).get("script")
    if not sc:
        return False, "هنوز اسکریپتی نفرستادی 📭"
    if is_running(uid):
        return False, "اسکریپتت همین الان روشنه ✅"
    entry = os.path.join(code_dir(uid), sc["entry"])
    if not os.path.isfile(entry):
        return False, "فایل اسکریپت پیدا نشد، دوباره بفرستش."
    kill_stale(uid)
    lp = log_path(uid)
    try:
        if os.path.isfile(lp) and os.path.getsize(lp) > MAX_LOG_BYTES:
            open(lp, "wb").close()
        logf = open(lp, "ab")
        logf.write(f"\n===== start {datetime.now(IRAN_TZ).strftime('%Y-%m-%d %H:%M:%S')} =====\n".encode())
        logf.flush()
        proc = await spawn_script(uid, [sys.executable, "-u", os.path.basename(entry)],
                                     os.path.dirname(entry), logf, stdin=asyncio.subprocess.PIPE)
        logf.close()
    except Exception as e:
        return False, f"اجرا نشد: {type(e).__name__}: {hide_paths(str(e), uid)}"
    rec = {"proc": proc, "started": time.time(), "manual": False}
    procs[uid] = rec
    u["starts"] = u.get("starts", 0) + 1
    u["was_running"] = True
    u["pid"] = proc.pid
    u["last_start"] = time.time()
    save_state()
    spawn(watch_script(uid, rec))
    return True, "استارت شد"


async def watch_script(uid: int, rec: dict):
    code = await rec["proc"].wait()
    if procs.get(uid) is rec:
        procs.pop(uid, None)
    had_console = await console_close(uid, "⏹ اسکریپت متوقف شد")
    u = users.get(uid)
    if not u:
        return
    u["last_exit"] = code
    u["pid"] = None
    if rec["manual"] or _shutting_down:
        save_state()
        if had_console and u.get("chat_id") and not _shutting_down:
            await plain_send(u["chat_id"], card("⏹", "اسکریپت متوقف شد"), reply_markup=kb_user_menu(uid))
        return
    u["was_running"] = False
    save_state()
    chat_id = u.get("chat_id")
    if chat_id:
        tail = read_log_tail(uid, 12)
        rows = [kv("🔚", "کد خروج", fa(code))]
        if tail:
            rows += ["", "📜 آخرین خروجی:", tail[-1500:]]
        msg = card("⚠️", "اسکریپت خودش متوقف شد", rows, f"برای اجرای دوباره «{BTN_START}» رو بزن 👇")
        await plain_send(chat_id, msg, reply_markup=kb_user_menu(uid))


async def stop_script(uid: int, manual: bool = True) -> bool:
    rec = procs.get(uid)
    if not rec or rec["proc"].returncode is not None:
        procs.pop(uid, None)
        return False
    rec["manual"] = manual
    proc = rec["proc"]
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except Exception:
            try:
                proc.terminate() if sig == signal.SIGTERM else proc.kill()
            except Exception:
                pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=STOP_GRACE)
            break
        except asyncio.TimeoutError:
            continue
    if manual and uid in users:
        users[uid]["was_running"] = False
        users[uid]["pid"] = None
        save_state()
    return True


def status_text(uid: int) -> str:
    u = users.get(uid) or {}
    sc = u.get("script")
    if not sc:
        return card("📊", "وضعیت", ["📭 هنوز اسکریپتی نفرستادی."], f"برای شروع «{BTN_SEND}» رو بزن 👇")
    if is_running(uid):
        state = f"{ST_ON} · {fmt_dur(time.time() - procs[uid]['started'])}"
    else:
        state = ST_OFF + (f" · کد خروج {fa(u['last_exit'])}" if u.get("last_exit") is not None else "")
    return card("📊", "وضعیت اسکریپت", [
        kv("⚙️", "وضعیت", state),
        kv("🐍", "فایل اصلی", sc["entry"]),
        kv("📦", "حجم", fmt_size(dir_size(code_dir(uid)))),
        kv("📅", "آخرین آپلود", fmt_time(sc.get("uploaded_at"))),
        kv("🔁", "تعداد استارت", f"{fa(u.get('starts', 0))} بار"),
    ])


# ───────────────────────── کنسول زنده ─────────────────────────

def _call_kwargs(fn, **kw):
    """فقط پارامترهایی که امضای تابع قبول می‌کنه رو نگه می‌داره."""
    try:
        params = inspect.signature(fn).parameters
        if not any(p.kind == p.VAR_KEYWORD for p in params.values()):
            kw = {k: v for k, v in kw.items() if k in params}
    except (TypeError, ValueError):
        pass
    return kw


async def edit_text(chat_id: int, mid, text: str) -> bool:
    try:
        fn = bot.edit_message_text
        await _maybe_await(fn(**_call_kwargs(fn, chat_id=chat_id, message_id=mid, text=text)))
        return True
    except Exception as e:
        if "not modified" in str(e).lower():
            return True
        print(f"⚠️ edit_message_text: {type(e).__name__}: {str(e)[:150]}")
        return False


async def delete_msg(chat_id: int, mid):
    try:
        fn = bot.delete_message
        await _maybe_await(fn(**_call_kwargs(fn, chat_id=chat_id, message_id=mid)))
    except Exception:
        pass


def console_text(uid: int, footer: str = "✍️ هرچی بنویسی به ورودی اسکریپت میره\n🔙 برای خروج «بستن کنسول» رو بزن") -> str:
    tail = read_log_tail(uid, 25)[-CONSOLE_VIEW_CHARS:] or "(هنوز خروجی‌ای نیست)"
    return f"💻 کنسول زنده\n{DIVIDER}\n{tail}\n{DIVIDER}\n{footer}"


async def _console_push(uid: int, chat_id: int, view: str, **kwargs) -> bool:
    """پیام جدید کنسول رو می‌فرسته، بعد پیام قبلی (و اعلان «کامند ارسال شد») رو پاک می‌کنه."""
    st = console_state.get(uid)
    if not st:
        return False
    sent = await plain_send(chat_id, view, **kwargs)
    new_mid = _g(sent, "message_id", "id")
    if new_mid is None:
        return False
    old = [st.get("mid"), st.get("notice")]
    st["mid"], st["notice"] = new_mid, None
    for m in old:
        if m is not None:
            await delete_msg(chat_id, m)
    return True


async def console_loop(uid: int, chat_id: int, last: str):
    fails = 0
    while uid in console_state and is_running(uid):
        await asyncio.sleep(CONSOLE_INTERVAL)
        if uid not in console_state:
            return
        view = console_text(uid)
        if view == last:
            continue
        if await _console_push(uid, chat_id, view):
            last, fails = view, 0
        else:
            fails += 1
            if fails >= 5:
                console_state.pop(uid, None)
                await plain_send(chat_id, "⚠️ ارسال کنسول ممکن نشد، بسته شد.", reply_markup=kb_user_menu(uid))
                return


async def console_close(uid: int, final=None) -> bool:
    st = console_state.get(uid)
    if not st:
        return False
    task = st.get("task")
    if task and task is not asyncio.current_task():
        task.cancel()
    if final:
        await _console_push(uid, st["chat_id"], console_text(uid, final))
    elif st.get("notice") is not None:
        await delete_msg(st["chat_id"], st["notice"])
    console_state.pop(uid, None)
    return True


async def console_open(uid: int, chat_id: int):
    if not is_running(uid):
        await plain_send(chat_id, "ℹ️ کنسول وقتی اسکریپت روشنه کار می‌کنه.", reply_markup=kb_user_menu(uid))
        return
    await console_close(uid)
    view = console_text(uid)
    sent = await plain_send(chat_id, view, reply_markup=kb_console())
    mid = _g(sent, "message_id", "id")
    if mid is None:
        await plain_send(chat_id, "⚠️ کنسول زنده پشتیبانی نشد.", reply_markup=kb_user_menu(uid))
        return
    st = {"chat_id": chat_id, "mid": mid, "notice": None, "task": None}
    console_state[uid] = st
    st["task"] = spawn(console_loop(uid, chat_id, view))


async def console_input(uid: int, chat_id: int, text: str, mid):
    rec = procs.get(uid)
    stdin = rec["proc"].stdin if rec and is_running(uid) else None
    if stdin is None:
        await console_close(uid, "⏹ اسکریپت خاموشه")
        await plain_send(chat_id, "⏹ اسکریپت خاموشه.", reply_markup=kb_user_menu(uid))
        return
    text = text[:CONSOLE_MAX_INPUT]
    try:
        with open(log_path(uid), "ab") as f:
            f.write(f"> {text}\n".encode("utf-8"))
    except OSError:
        pass
    try:
        stdin.write((text + "\n").encode("utf-8"))
        await stdin.drain()
    except (BrokenPipeError, ConnectionResetError, OSError):
        await console_close(uid, "⏹ اسکریپت ورودی قبول نمی‌کنه")
        await plain_send(chat_id, "⚠️ ورودی نرسید.", reply_markup=kb_user_menu(uid))
        return
    if mid is not None:
        await delete_msg(chat_id, mid)  # پیام خود کاربر پاک میشه؛ خودش توی خروجی کنسول دیده میشه
    st = console_state.get(uid)
    if st:
        if st.get("notice") is not None:
            await delete_msg(chat_id, st["notice"])
        sent = await plain_send(chat_id, "✅ کامند ارسال شد")
        st["notice"] = _g(sent, "message_id", "id")


# ───────────────────────── دریافت و پردازش فایل کاربر ─────────────────────────

def _lock(uid: int) -> asyncio.Lock:
    if uid not in user_locks:
        user_locks[uid] = asyncio.Lock()
    return user_locks[uid]


def _process_upload_sync(uid: int, tmp_file: str, kind: str, orig_name: str):
    new_code = os.path.join(user_dir(uid), "code_new")
    shutil.rmtree(new_code, ignore_errors=True)
    os.makedirs(new_code, exist_ok=True)
    if kind == "zip":
        if not zipfile.is_zipfile(tmp_file):
            raise ValueError("فایل zip سالم نیست")
        files = safe_extract(tmp_file, new_code)
        os.remove(tmp_file)
        entry = find_entry(new_code)
        if not entry:
            shutil.rmtree(new_code, ignore_errors=True)
            raise ValueError("داخل zip فایل main.py پیدا نشد؛ اسم فایل اصلی باید main.py باشه")
    else:
        if safe_filename(orig_name).lower() != ENTRY_NAME:
            shutil.rmtree(new_code, ignore_errors=True)
            raise ValueError("اسم فایل باید main.py باشه")
        shutil.move(tmp_file, os.path.join(new_code, ENTRY_NAME))
        entry = ENTRY_NAME
        files = 1
    return new_code, entry, files


async def handle_document(update):
    message = update.message
    chat_id = message.chat.id
    user = message.from_user
    uid = int(user.id)
    key = (chat_id, _g(message, "message_id", "id"))
    now = time.monotonic()
    if key[1] is not None:
        if now - _seen_msgs.get(key, -1e9) < 10:
            return
        _seen_msgs[key] = now
        if len(_seen_msgs) > 500:
            for k in [k for k, t in _seen_msgs.items() if now - t > 60]:
                _seen_msgs.pop(k, None)
    u = touch_user(user, chat_id)
    if u.get("banned") and uid != ADMIN_ID:
        return
    doc = get_doc(message)
    if not doc:
        if uid in upload_state:
            print("ℹ️ پیام بدون فایل قابل‌شناسایی:", repr(message)[:400])
        return
    upload_state.discard(uid)

    name = doc["name"]
    lower = name.lower()
    if name and not (lower.endswith(".zip") or lower.endswith(".py")):
        await plain_send(chat_id, card("⚠️", "فایل نامعتبر", ["فقط فایل main.py یا zip قبوله."],
                                       "👇 دوباره بفرست یا «انصراف» رو بزن"),
                         reply_markup=kb_cancel())
        upload_state.add(uid)
        return
    if lower.endswith(".py") and safe_filename(name).lower() != ENTRY_NAME:
        await plain_send(chat_id, card("⚠️", "اسم فایل درست نیست", ["اسم فایل باید دقیقاً main.py باشه."],
                                       "👇 دوباره بفرست یا «انصراف» رو بزن"),
                         reply_markup=kb_cancel())
        upload_state.add(uid)
        return
    size = doc["size"]
    if isinstance(size, (int, float)) and size > MAX_UPLOAD_MB * 1024 * 1024:
        await plain_send(chat_id, card("⚠️", "فایل خیلی بزرگه", [f"حداکثر حجم مجاز {fa(MAX_UPLOAD_MB)} مگابایته."]), reply_markup=kb_user_menu(uid))
        return

    async with _lock(uid):
        wait_text = ("⏳ در حال نصب کتابخانه و استخراج..." if lower.endswith(".zip")
                     else "⏳ در حال بررسی...")
        wait_msg = await plain_send(chat_id, wait_text, reply_markup=kb_cancel())
        os.makedirs(user_dir(uid), exist_ok=True)
        tmp_file = os.path.join(TMP_DIR, f"{uid}_{int(time.time())}_{safe_filename(name or 'upload')}")
        ok, err = await fetch_document(message, doc, tmp_file)
        if not ok:
            await plain_send(chat_id, card("❌", "دانلود فایل نشد", ["یه بار دیگه بفرستش 🙏"]), reply_markup=kb_user_menu(uid))
            if err:
                print(f"❌ fetch_document: {err}")
                if uid != ADMIN_ID:
                    await plain_send(ADMIN_ID, f"⚠️ دانلود فایل کاربر {uid} ناموفق بود:\n{err[:1500]}")
                else:
                    await plain_send(chat_id, f"🔧 جزئیات خطا:\n{err[:1500]}")
            return
        try:
            if os.path.getsize(tmp_file) > MAX_UPLOAD_MB * 1024 * 1024:
                os.remove(tmp_file)
                await plain_send(chat_id, card("⚠️", "فایل خیلی بزرگه", [f"حداکثر حجم مجاز {fa(MAX_UPLOAD_MB)} مگابایته."]), reply_markup=kb_user_menu(uid))
                return
            if lower.endswith(".zip"):
                kind = "zip"
            elif lower.endswith(".py"):
                kind = "py"
            else:
                with open(tmp_file, "rb") as f:
                    kind = "zip" if f.read(4) == b"PK\x03\x04" else "py"
            loop = asyncio.get_running_loop()
            new_code, entry, files = await loop.run_in_executor(None, _process_upload_sync, uid, tmp_file, kind, name)
        except Exception as e:
            try:
                os.remove(tmp_file)
            except OSError:
                pass
            shutil.rmtree(os.path.join(user_dir(uid), "code_new"), ignore_errors=True)
            await plain_send(chat_id, card("❌", "آپلود انجام نشد", [hide_paths(str(e), uid)]), reply_markup=kb_user_menu(uid))
            return

        was_running = is_running(uid)
        if was_running:
            await stop_script(uid, manual=True)
        shutil.rmtree(code_dir(uid), ignore_errors=True)
        os.replace(new_code, code_dir(uid))
        u["script"] = {"entry": entry, "orig_name": name or entry, "kind": kind,
                       "uploaded_at": time.time(), "files": files}
        u["uploads"] = u.get("uploads", 0) + 1
        u["last_exit"] = None
        save_state()

        pip_line = None
        if os.path.isdir(code_dir(uid)):
            res = await install_requirements(uid)
            if res is True:
                pip_line = "📚 کتابخونه‌ها نصب شدن ✅"
            elif res is False:
                pip_line = "⚠️ نصب بعضی کتابخونه‌ها نشد"

        rows = [
            kv("🐍", "فایل اصلی", entry),
            kv("🗂", "تعداد فایل", fa(files)),
            kv("📦", "حجم", fmt_size(dir_size(code_dir(uid)))),
            pip_line,
            "♻️ نسخه‌ی قبلی متوقف و جایگزین شد." if was_running else None,
        ]
        text = card("✅", "اسکریپت دریافت شد", rows, f"برای اجرا «{BTN_START}» رو بزن 👇")
        wait_mid = _g(wait_msg, "message_id", "id")
        if wait_mid is not None:
            await delete_msg(chat_id, wait_mid)
        await plain_send(chat_id, text, reply_markup=kb_after_upload())


# ───────────────────────── عملیات کاربر ─────────────────────────

async def act_start(uid: int, chat_id: int):
    ok, msg = await start_script(uid)
    if not ok:
        await plain_send(chat_id, card("⚠️", "توجه", [msg]), reply_markup=kb_user_menu(uid))
        return
    await plain_send(chat_id, card("🚀", "اسکریپت روشن شد", ["چند ثانیه‌ی اول خروجی رو برات می‌فرستم 👀"]),
                     reply_markup=kb_user_menu(uid))
    await asyncio.sleep(2)
    if not is_running(uid):
        return
    tail = read_log_tail(uid, 8)
    if tail:
        await plain_send(chat_id, card("📜", "خروجی اولیه", [tail[-1200:]]), reply_markup=kb_user_menu(uid))


async def act_stop(uid: int, chat_id: int):
    if await stop_script(uid, manual=True):
        await plain_send(chat_id, card("⏹", "اسکریپت متوقف شد", [], f"هر وقت خواستی «{BTN_START}» رو بزن 👇"),
                         reply_markup=kb_user_menu(uid))
    else:
        await plain_send(chat_id, card("ℹ️", "الان خاموشه", ["اسکریپتت در حال اجرا نیست."]),
                         reply_markup=kb_user_menu(uid))


async def act_restart(uid: int, chat_id: int):
    await plain_send(chat_id, "🔄 در حال ری‌استارت...", reply_markup=kb_user_menu(uid))
    await stop_script(uid, manual=True)
    await act_start(uid, chat_id)


async def act_log(uid: int, chat_id: int, target_uid=None):
    owner = target_uid or uid
    tail = read_log_tail(owner, hide=target_uid is None)
    markup = kb_target(owner) if target_uid else kb_user_menu(uid)
    if not tail:
        await plain_send(chat_id, card("📜", "لاگ اسکریپت", ["هنوز خروجی‌ای ثبت نشده 🌱"]), reply_markup=markup)
        return
    await send_long(chat_id, card("📜", "لاگ اسکریپت", [tail]), reply_markup=markup)


async def send_user_zip(chat_id: int, owner: int, markup):
    u = users.get(owner) or {}
    if not u.get("script") or not os.path.isdir(code_dir(owner)):
        await plain_send(chat_id, "📭 این کاربر اسکریپتی نداره.", reply_markup=markup)
        return
    out = os.path.join(TMP_DIR, f"{owner}_{int(time.time())}.zip")
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, build_zip, code_dir(owner), out, ("__pycache__", DEPS_DIRNAME))
        caption = card("📦", "کد کاربر", [kv("👤", "نام", full_name(u)), kv("🆔", "آیدی", owner),
                                       kv("🔗", "یوزرنیم", "@" + u["username"]) if u.get("username") else None])
        sent = await send_document_file(chat_id, out, caption)
        if sent is None:
            await plain_send(chat_id, "❌ ارسال فایل ناموفق بود.", reply_markup=markup)
        else:
            await plain_send(chat_id, "✅ ارسال شد 📬", reply_markup=markup)
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


async def send_backup(chat_id: int, uid: int):
    u = users.get(uid) or {}
    if not u.get("script") or not os.path.isdir(user_dir(uid)):
        await plain_send(chat_id, "📭 اسکریپتی نداری.", reply_markup=kb_user_menu(uid))
        return
    await plain_send(chat_id, "⏳ در حال ساخت بکاپ، چند لحظه صبر کن...", reply_markup=kb_user_menu(uid))
    stamp = datetime.now(IRAN_TZ).strftime("%Y%m%d_%H%M")
    out = os.path.join(TMP_DIR, f"backup_{uid}_{stamp}.zip")
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, build_zip, user_dir(uid), out)
        size = os.path.getsize(out)
        caption = card("💾", "بکاپ کامل محیط", [
            kv("🕒", "زمان", fmt_time(time.time())),
            kv("📦", "حجم", fmt_size(size)),
            "📁 شامل: کد، دیتابیس و همه‌ی فایل‌های ساخته‌شده",
        ], "برای بازگردانی کد، پوشه‌ی code رو از zip بفرست.")
        sent = await send_document_file(chat_id, out, caption)
        if sent is None:
            await plain_send(chat_id, "❌ ارسال بکاپ ناموفق بود (شاید حجمش زیاده).", reply_markup=kb_user_menu(uid))
        else:
            await plain_send(chat_id, "✅ بکاپ ارسال شد 💾", reply_markup=kb_user_menu(uid))
    except Exception as e:
        print(f"❌ backup failed: {type(e).__name__}: {e}")
        await plain_send(chat_id, "❌ ساخت بکاپ ناموفق بود.", reply_markup=kb_user_menu(uid))
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


async def send_user_py(chat_id: int, owner: int, markup):
    u = users.get(owner) or {}
    sc = u.get("script")
    if not sc:
        await plain_send(chat_id, "📭 این کاربر اسکریپتی نداره.", reply_markup=markup)
        return
    path = os.path.join(code_dir(owner), sc["entry"])
    real_root = os.path.realpath(code_dir(owner))
    if (not os.path.isfile(path) or os.path.islink(path)
            or not os.path.realpath(path).startswith(real_root + os.sep)):
        await plain_send(chat_id, "⚠️ فایل py پیدا نشد.", reply_markup=markup)
        return
    caption = card("📄", "فایل py کاربر", [kv("👤", "نام", full_name(u)), kv("🆔", "آیدی", owner),
                                           kv("🔗", "یوزرنیم", "@" + u["username"]) if u.get("username") else None])
    sent = await send_document_file(chat_id, path, caption)
    await plain_send(chat_id, "✅ py ارسال شد." if sent else "❌ ارسال فایل ناموفق بود.", reply_markup=markup)


async def reset_user_memory(uid: int):
    await stop_script(uid, manual=True)
    wipe_user_data(uid)
    u = users.get(uid)
    if u:
        u["script"] = None
        u["was_running"] = False
        u["pid"] = None
        u["last_exit"] = None
        save_state()


# ───────────────────────── پنل مدیریت ─────────────────────────

def user_card(uid: int, brief: bool = False) -> str:
    u = users[uid]
    sc = u.get("script")
    running = is_running(uid)
    lines = [f"👤 {full_name(u)}", f"🆔 {uid}"]
    if u.get("username"):
        lines.append(f"🔗 @{u['username']}")
    if brief:
        if sc:
            lines.append(f"🐍 {sc['entry']} | {'🟢 روشن' if running else '🔴 خاموش'}")
        else:
            lines.append("📭 بدون اسکریپت")
        if u.get("banned"):
            lines.append("🚫 مسدود")
        return "\n".join(lines)
    if u.get("phone"):
        lines.append(f"📱 {u['phone']}")
    lines.append(f"💬 chat id: {u.get('chat_id', '—')}")
    lines.append(f"📅 عضویت: {fmt_time(u.get('joined'))}")
    lines.append(f"🕐 آخرین فعالیت: {fmt_time(u.get('last_seen'))}")
    lines.append(SOFT)
    if sc:
        lines.append(f"🐍 فایل اصلی: {sc['entry']}")
        lines.append(f"🗂 نوع آپلود: {sc.get('kind', '—')} | فایل‌ها: {fa(sc.get('files', 1))}")
        lines.append(f"📦 حجم: {fmt_size(dir_size(code_dir(uid)))}")
        lines.append(f"⬆️ آخرین آپلود: {fmt_time(sc.get('uploaded_at'))}")
        lines.append(f"⚙️ وضعیت: {'🟢 روشن' if running else '🔴 خاموش'}")
        if running:
            lines.append(f"⏱ مدت روشن بودن: {fmt_dur(time.time() - procs[uid]['started'])}")
        elif u.get("last_exit") is not None:
            lines.append(f"🔚 آخرین کد خروج: {fa(u['last_exit'])}")
    else:
        lines.append("📭 اسکریپتی نداره")
    lines.append(f"🔁 تعداد استارت: {fa(u.get('starts', 0))} | آپلود: {fa(u.get('uploads', 0))}")
    lines.append("🚫 وضعیت حساب: مسدود" if u.get("banned") else "✅ وضعیت حساب: آزاد")
    return "\n".join(lines)


def sorted_user_ids(query: str = "") -> list:
    ids = sorted(users.keys(), key=lambda i: users[i].get("last_seen", 0), reverse=True)
    query = (query or "").strip().lstrip("@").lower()
    if not query:
        return ids
    out = []
    for i in ids:
        u = users[i]
        hay = f"{i} {full_name(u)} {u.get('username', '')} {u.get('phone', '')}".lower()
        if query in hay:
            out.append(i)
    return out


async def show_users_page(chat_id: int, state: dict):
    ids = state.get("ids") or sorted_user_ids()
    state["ids"] = ids
    pages = max(1, (len(ids) + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
    page = min(max(0, state.get("page", 0)), pages - 1)
    state["page"] = page
    chunk = ids[page * USERS_PER_PAGE:(page + 1) * USERS_PER_PAGE]
    state["mode"] = "list"
    if not chunk:
        await plain_send(chat_id, "📭 کاربری پیدا نشد.", reply_markup=kb_admin_panel())
        state["mode"] = "panel"
        return
    head = f"👥 کاربرها — صفحه {fa(page + 1)} از {fa(pages)}\n📊 مجموع: {fa(len(ids))} نفر\n{DIVIDER}\n"
    body = f"\n{SOFT}\n".join(user_card(i, brief=True) for i in chunk)
    await send_long(chat_id, head + body + f"\n{DIVIDER}\nروی اسم هر کاربر بزن تا مشخصاتش بیاد 👇",
                    reply_markup=kb_users_page(chunk, page, pages))


async def show_target(chat_id: int, state: dict, uid: int):
    state["mode"] = "target"
    state["target"] = uid
    await plain_send(chat_id, f"👤 مشخصات کاربر\n{DIVIDER}\n{user_card(uid)}", reply_markup=kb_target(uid))


def stats_text() -> str:
    total = len(users)
    with_script = sum(1 for u in users.values() if u.get("script"))
    running = sum(1 for i in users if is_running(i))
    banned = sum(1 for u in users.values() if u.get("banned"))
    disk = dir_size(USERS_DIR)
    day_ago = time.time() - 86400
    active = sum(1 for u in users.values() if u.get("last_seen", 0) > day_ago)
    return card("📈", "آمار سرور", [
        kv("👥", "کل کاربرها", fa(total)),
        kv("🕐", "فعال در ۲۴ ساعت اخیر", fa(active)),
        SOFT,
        kv("📦", "دارای اسکریپت", fa(with_script)),
        kv("🟢", "اسکریپت روشن", fa(running)),
        kv("🚫", "مسدودشده", fa(banned)),
        SOFT,
        kv("💾", "فضای مصرفی", fmt_size(disk)),
    ])


def panel_text() -> str:
    running = sum(1 for i in users if is_running(i))
    return card("🛠", "پنل مدیریت", [
        kv("👥", "کاربرها", fa(len(users))),
        kv("🟢", "اسکریپت روشن", fa(running)),
    ], "یکی از گزینه‌ها رو انتخاب کن 👇")


async def do_broadcast(admin_chat_id: int, text: str):
    sent = failed = 0
    body = card("📢", "پیام مدیریت", [text])
    for uid, u in list(users.items()):
        chat = u.get("chat_id")
        if not chat or u.get("banned"):
            continue
        if await plain_send(chat, body) is None:
            failed += 1
        else:
            sent += 1
        await asyncio.sleep(BROADCAST_DELAY)
    await plain_send(admin_chat_id, card("📢", "پیام همگانی تموم شد", [kv("✅", "موفق", fa(sent)), kv("❌", "ناموفق", fa(failed))]),
                     reply_markup=kb_admin_panel())


async def admin_handle(text: str, chat_id: int, user_id: int) -> bool:
    state = admin_state.get(user_id)

    if text == BTN_ADMIN:
        admin_state[user_id] = {"mode": "panel"}
        await plain_send(chat_id, panel_text(), reply_markup=kb_admin_panel())
        return True
    if state is None:
        return False

    mode = state.get("mode")

    if text == ADM_BACK:
        admin_state.pop(user_id, None)
        await plain_send(chat_id, "🏠 برگشتی به منوی اصلی.", reply_markup=kb_user_menu(user_id))
        return True
    if text == ADM_PANEL_BACK:
        admin_state[user_id] = {"mode": "panel"}
        await plain_send(chat_id, panel_text(), reply_markup=kb_admin_panel())
        return True

    if mode == "broadcast_text":
        if text == ADM_CANCEL:
            admin_state[user_id] = {"mode": "panel"}
            await plain_send(chat_id, "❎ لغو شد.", reply_markup=kb_admin_panel())
            return True
        state.update(mode="broadcast_confirm", text=text)
        await plain_send(chat_id, card("👀", "پیش‌نمایش پیام", [text], "ارسال بشه؟"), reply_markup=kb([[ADM_SEND, ADM_CANCEL]]))
        return True
    if mode == "broadcast_confirm":
        if text == ADM_SEND:
            msg = state.get("text", "")
            admin_state[user_id] = {"mode": "panel"}
            await plain_send(chat_id, "⏳ در حال ارسال به همه...", reply_markup=kb_admin_panel())
            spawn(do_broadcast(chat_id, msg))
        else:
            admin_state[user_id] = {"mode": "panel"}
            await plain_send(chat_id, "❎ لغو شد.", reply_markup=kb_admin_panel())
        return True

    if mode == "user_message":
        target = state.get("target")
        if text == ADM_CANCEL:
            await show_target(chat_id, state, target)
            return True
        chat = users.get(target, {}).get("chat_id")
        ok = chat and await plain_send(chat, card("✉️", "پیام مدیریت", [text]))
        await plain_send(chat_id, "✅ پیام ارسال شد." if ok else "❌ ارسال نشد.", reply_markup=kb_target(target))
        state["mode"] = "target"
        return True

    if mode == "search":
        if text == ADM_CANCEL:
            admin_state[user_id] = {"mode": "panel"}
            await plain_send(chat_id, "❎ لغو شد.", reply_markup=kb_admin_panel())
            return True
        state["ids"] = sorted_user_ids(text)
        state["page"] = 0
        await show_users_page(chat_id, state)
        return True

    if mode == "confirm_reset":
        target = state.get("target")
        if text == BTN_YES:
            await reset_user_memory(target)
            chat = users.get(target, {}).get("chat_id")
            if chat:
                await plain_send(chat, "♻️ حافظه‌ی اسکریپتت توسط مدیریت ریست شد.\nباید دوباره اسکریپتت رو بفرستی.",
                                 reply_markup=kb_user_menu(target))
            await plain_send(chat_id, "✅ حافظه‌ی کاربر پاک شد.", reply_markup=kb_target(target))
        else:
            await plain_send(chat_id, "❎ لغو شد.", reply_markup=kb_target(target))
        state["mode"] = "target"
        return True

    if text == ADM_USERS:
        state.update(mode="list", ids=sorted_user_ids(), page=0)
        await show_users_page(chat_id, state)
        return True
    if text == ADM_SEARCH:
        state["mode"] = "search"
        await plain_send(chat_id, "🔍 اسم، یوزرنیم یا آیدی عددی کاربر رو بفرست:", reply_markup=kb([[ADM_CANCEL]]))
        return True
    if text == ADM_STATS:
        await plain_send(chat_id, stats_text(), reply_markup=kb_admin_panel())
        return True
    if text == ADM_RUNNING:
        running = [i for i in users if is_running(i)]
        if not running:
            await plain_send(chat_id, "🔴 الان هیچ اسکریپتی روشن نیست.", reply_markup=kb_admin_panel())
        else:
            rows = []
            for i in running:
                rows.append(f"👤 {full_name(users[i])} • {i}\n   ⏱ {fmt_dur(time.time() - procs[i]['started'])} | 🐍 {users[i]['script']['entry']}")
            lines = [card("🟢", f"اسکریپت‌های روشن ({fa(len(running))})", [f"\n{SOFT}\n".join(rows)])]
            await send_long(chat_id, "\n".join(lines), reply_markup=kb_admin_panel())
        return True
    if text == ADM_STOPALL:
        running = [i for i in users if is_running(i)]
        for i in running:
            await stop_script(i, manual=True)
        await plain_send(chat_id, f"🛑 {fa(len(running))} اسکریپت متوقف شد.", reply_markup=kb_admin_panel())
        return True
    if text == ADM_BROADCAST:
        state["mode"] = "broadcast_text"
        await plain_send(chat_id, "📢 متن پیام همگانی رو بفرست:", reply_markup=kb([[ADM_CANCEL]]))
        return True

    if mode == "list":
        if text == ADM_NEXT:
            state["page"] = state.get("page", 0) + 1
            await show_users_page(chat_id, state)
            return True
        if text == ADM_PREV:
            state["page"] = max(0, state.get("page", 0) - 1)
            await show_users_page(chat_id, state)
            return True
        m = USER_BTN_RE.search(text)
        if m and int(m.group(1)) in users:
            await show_target(chat_id, state, int(m.group(1)))
            return True

    if mode == "target":
        target = state.get("target")
        if target not in users:
            admin_state[user_id] = {"mode": "panel"}
            return True
        if text == ADM_LIST_BACK:
            state["page"] = state.get("page", 0)
            await show_users_page(chat_id, state)
            return True
        if text == T_ZIP:
            spawn(send_user_zip(chat_id, target, kb_target(target)))
            return True
        if text == T_PY:
            spawn(send_user_py(chat_id, target, kb_target(target)))
            return True
        if text == T_START:
            ok, msg = await start_script(target)
            await plain_send(chat_id, ("🚀 " if ok else "⚠️ ") + msg, reply_markup=kb_target(target))
            return True
        if text == T_STOP:
            stopped = await stop_script(target, manual=True)
            await plain_send(chat_id, "⏹ متوقف شد." if stopped else "ℹ️ خاموش بود.", reply_markup=kb_target(target))
            return True
        if text == T_LOG:
            await act_log(user_id, chat_id, target_uid=target)
            return True
        if text == T_MSG:
            state["mode"] = "user_message"
            await plain_send(chat_id, "✉️ متن پیام برای این کاربر رو بفرست:", reply_markup=kb([[ADM_CANCEL]]))
            return True
        if text == T_RESET:
            state["mode"] = "confirm_reset"
            await plain_send(chat_id, f"⚠️ حافظه‌ی «{full_name(users[target])}» پاک بشه؟\n"
                                       "اسکریپت و فایل‌هاش کامل حذف میشن و باید از اول بفرسته.",
                             reply_markup=kb_confirm())
            return True
        if text in (T_BAN, T_UNBAN):
            ban = text == T_BAN
            users[target]["banned"] = ban
            if ban:
                await stop_script(target, manual=True)
            save_state()
            chat = users[target].get("chat_id")
            if chat:
                await plain_send(chat, "🚫 دسترسی شما توسط مدیریت مسدود شد." if ban else "✅ دسترسی شما دوباره فعال شد.",
                                 reply_markup=None if ban else kb_user_menu(target))
            await plain_send(chat_id, "🚫 کاربر مسدود شد." if ban else "✅ مسدودی برداشته شد.", reply_markup=kb_target(target))
            return True

    return True


# ───────────────────────── هندلرها ─────────────────────────

MENU_TEXTS = {BTN_SEND, BTN_START, BTN_STOP, BTN_RESTART, BTN_STATUS, BTN_LOG, BTN_FILES, BTN_BACKUP, BTN_DELETE,
              BTN_HELP, BTN_ADMIN, BTN_MENU, BTN_CANCEL, BTN_CONSOLE, BTN_CLOSE_CONSOLE}


@bot.on(Filters.command("start"))
async def start_handler(update: Update):
    message = update.message
    user = message.from_user
    u = touch_user(user, message.chat.id)
    upload_state.discard(user.id)
    await console_close(user.id)
    confirm_state.pop(user.id, None)
    admin_state.pop(user.id, None)
    if u.get("banned") and user.id != ADMIN_ID:
        await plain_send(message.chat.id, "🚫 دسترسی شما به ربات مسدود شده.")
        return
    await plain_send(message.chat.id, txt_welcome(user.first_name or "دوست من"), reply_markup=kb_user_menu(user.id))


@bot.on(Filters.command("help"))
async def help_handler(update: Update):
    user = update.message.from_user
    touch_user(user, update.message.chat.id)
    await plain_send(update.message.chat.id, txt_help(), reply_markup=kb_user_menu(user.id))


@bot.on(Filters.text)
async def text_handler(update: Update):
    message = update.message
    text = (message.text or "").strip()
    chat_id = message.chat.id
    user = message.from_user
    uid = int(user.id)

    if get_doc(message):
        spawn(handle_document(update))
        return
    if not text or text.startswith("/"):
        return

    u = touch_user(user, chat_id)

    if uid == ADMIN_ID:
        try:
            if await admin_handle(text, chat_id, uid):
                return
        except Exception as e:
            print(f"❌ admin_handle exception: {type(e).__name__}: {e}")
            traceback.print_exc()
            admin_state.pop(uid, None)
            await plain_send(chat_id, "⚠️ تو پنل مدیریت خطایی پیش اومد.", reply_markup=kb_user_menu(uid))
            return
    elif text in ADMIN_TEXTS:
        return

    if u.get("banned") and uid != ADMIN_ID:
        await plain_send(chat_id, "🚫 دسترسی شما توسط مدیریت مسدود شده.")
        return

    pending = confirm_state.get(uid)
    if pending:
        confirm_state.pop(uid, None)
        if pending == "delete" and text == BTN_YES:
            await reset_user_memory(uid)
            await plain_send(chat_id, card("🗑", "همه‌چیز پاک شد", [], f"هر وقت خواستی با «{BTN_SEND}» از نو شروع کن 👇"), reply_markup=kb_user_menu(uid))
        else:
            await plain_send(chat_id, "باشه، پاک نشد 🙂", reply_markup=kb_user_menu(uid))
        return

    if uid in console_state:
        if text == BTN_CLOSE_CONSOLE:
            await console_close(uid)
            await plain_send(chat_id, "🏠 کنسول بسته شد.", reply_markup=kb_user_menu(uid))
        else:
            await console_input(uid, chat_id, text, _g(message, "message_id", "id"))
        return

    if text in (BTN_MENU, BTN_CANCEL):
        upload_state.discard(uid)
        await plain_send(chat_id, "🏠 منوی اصلی", reply_markup=kb_user_menu(uid))
        return
    if text == BTN_SEND:
        upload_state.add(uid)
        await plain_send(chat_id, txt_upload_prompt(), reply_markup=kb_cancel())
        return

    if text in MENU_TEXTS:
        upload_state.discard(uid)
    elif uid in upload_state:
        await plain_send(chat_id, card("⚠️", "منتظر فایلم", ["متن نفرست، فایل main.py یا zip رو بفرست."], "یا «انصراف» رو بزن 👇"), reply_markup=kb_cancel())
        return

    if text == BTN_START:
        spawn(act_start(uid, chat_id))
    elif text == BTN_STOP:
        await act_stop(uid, chat_id)
    elif text == BTN_RESTART:
        spawn(act_restart(uid, chat_id))
    elif text == BTN_STATUS:
        await plain_send(chat_id, status_text(uid), reply_markup=kb_user_menu(uid))
    elif text == BTN_LOG:
        await act_log(uid, chat_id)
    elif text == BTN_CONSOLE:
        await console_open(uid, chat_id)
    elif text == BTN_FILES:
        spawn(send_user_zip(chat_id, uid, kb_user_menu(uid)))
    elif text == BTN_BACKUP:
        spawn(send_backup(chat_id, uid))
    elif text == BTN_DELETE:
        if not u.get("script"):
            await plain_send(chat_id, card("📭", "چیزی برای حذف نیست", ["هنوز اسکریپتی نفرستادی."]), reply_markup=kb_user_menu(uid))
        else:
            confirm_state[uid] = "delete"
            await plain_send(chat_id, card("⚠️", "حذف کامل اسکریپت", ["کد، دیتا و فایل‌هات همگی پاک میشن.", "این کار برگشت نداره!"], "مطمئنی؟"), reply_markup=kb_confirm())
    elif text == BTN_HELP:
        await plain_send(chat_id, txt_help(), reply_markup=kb_user_menu(uid))
    else:
        await plain_send(chat_id, "از منوی پایین انتخاب کن 👇", reply_markup=kb_user_menu(uid))


def _register_document_handlers():
    names = ("document", "documents", "file", "files", "media", "attachment")
    fallback = ("any", "all", "message")
    done = 0
    for group in (names, fallback):
        if done:
            break
        for fname in group:
            flt = getattr(Filters, fname, None)
            if flt is None:
                continue
            cands = [flt]
            if callable(flt) and not isinstance(flt, type):
                try:
                    cands.append(flt())
                except Exception:
                    pass
            for cand in cands:
                try:
                    bot.on(cand)(handle_document)
                    print(f"✅ هندلر فایل روی Filters.{fname} ثبت شد.")
                    done += 1
                    break
                except Exception as e:
                    print(f"⚠️ ثبت هندلر فایل ({fname}) نشد: {type(e).__name__}: {e}")
    if not done:
        print("⚠️ فیلتر فایل پیدا نشد؛ فایل‌ها فقط از مسیر هندلر متن گرفته میشن.")


_register_document_handlers()


# ───────────────────────── سرور سلامت + پینگ ─────────────────────────

async def _handle_http(reader, writer):
    try:
        await asyncio.wait_for(reader.read(4096), timeout=5)
    except Exception:
        pass
    body = b"OK"
    head = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
    try:
        writer.write(head + body)
        await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def start_health_server():
    server = await asyncio.start_server(_handle_http, "0.0.0.0", PORT)
    print(f"🌐 سرور سلامت روی پورت {PORT} بالا اومد.")
    async with server:
        await server.serve_forever()


def _ping_once(url: str) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": "keep-alive-ping"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status


async def ping_loop():
    if not PING_URL:
        while True:
            await asyncio.sleep(3600)
    loop = asyncio.get_running_loop()
    await asyncio.sleep(60)
    while True:
        try:
            await loop.run_in_executor(None, _ping_once, PING_URL)
        except Exception as e:
            print(f"⚠️ پینگ fail شد: {type(e).__name__}: {e}")
        await asyncio.sleep(PING_INTERVAL)


async def log_reset_loop():
    while True:
        await asyncio.sleep(LOG_CHECK_INTERVAL)
        try:
            for uid in list(users.keys()):
                lp = log_path(uid)
                try:
                    if os.path.isfile(lp) and os.path.getsize(lp) > MAX_LOG_BYTES:
                        with open(lp, "r+b") as f:
                            f.truncate(0)
                        print(f"🧹 لاگ کاربر {uid} از سقف گذشت و ریست شد.")
                except OSError:
                    pass
        except Exception as e:
            print(f"⚠️ log_reset_loop: {type(e).__name__}: {e}")


def _clean_pycache(root: str) -> int:
    """تمام __pycache__های زیر root رو پاک می‌کنه؛ تعداد بایت آزاد‌شده رو برمی‌گردونه."""
    freed = 0
    for dirpath, dirnames, _files in os.walk(root, topdown=False):
        if os.path.basename(dirpath) == "__pycache__":
            try:
                freed += dir_size(dirpath)
                shutil.rmtree(dirpath, ignore_errors=True)
            except Exception:
                pass
            dirnames[:] = []
    return freed


async def cleanup_loop():
    while True:
        await asyncio.sleep(1800)
        # ── پاکسازی فایل‌های موقت قدیمی ──
        try:
            now = time.time()
            for f in os.listdir(TMP_DIR):
                p = os.path.join(TMP_DIR, f)
                if os.path.isfile(p) and now - os.path.getmtime(p) > 3600:
                    os.remove(p)
        except Exception:
            pass
        # ── پاکسازی __pycache__ سنگین کاربرها ──
        try:
            limit = MAX_CACHE_MB * 1024 * 1024
            for uid in list(users.keys()):
                cd = code_dir(uid)
                if not os.path.isdir(cd):
                    continue
                cache_size = 0
                for dirpath, dirnames, _files in os.walk(cd):
                    if os.path.basename(dirpath) == "__pycache__":
                        cache_size += dir_size(dirpath)
                if cache_size > limit:
                    loop = asyncio.get_running_loop()
                    freed = await loop.run_in_executor(None, _clean_pycache, cd)
                    print(f"🧹 کش کاربر {uid} پاک شد: {freed // 1024} KB آزاد شد.")
        except Exception as e:
            print(f"⚠️ cache_cleanup: {type(e).__name__}: {e}")


async def supervise(name: str, factory, base_delay: int = 3, max_delay: int = 60):
    delay = base_delay
    while True:
        started = time.monotonic()
        try:
            await factory()
            print(f"⚠️ بخش «{name}» تموم شد؛ دوباره راه می‌اندازمش.")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"❌ بخش «{name}» کرش کرد: {type(e).__name__}: {e}")
            traceback.print_exc()
        if time.monotonic() - started > 120:
            delay = base_delay
        await asyncio.sleep(delay)
        delay = min(delay * 2, max_delay)


async def restore_scripts():
    await asyncio.sleep(3)
    for uid, u in list(users.items()):
        if u.get("was_running") and u.get("script") and not u.get("banned"):
            ok, _msg = await start_script(uid)
            if ok and u.get("chat_id"):
                await plain_send(u["chat_id"], "♻️ بعد از ری‌استارت سرور، اسکریپتت دوباره استارت شد ✅",
                                 reply_markup=kb_user_menu(uid))
            await asyncio.sleep(0.5)


async def main():
    global _shutting_down
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(
        lambda _loop, ctx: print(f"⚠️ asyncio: {ctx.get('message')} {ctx.get('exception')!r}")
    )
    stop_event = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError, ValueError):
            pass

    load_state()
    print(f"📂 {len(users)} کاربر بارگذاری شد.")

    runners = [
        spawn(supervise("health", start_health_server)),
        spawn(supervise("ping", ping_loop)),
        spawn(supervise("cleanup", cleanup_loop)),
        spawn(supervise("logreset", log_reset_loop)),
        spawn(supervise("bot", bot.run_polling)),
        spawn(restore_scripts()),
    ]
    print("🤖 ربات هاست اسکریپت در حال اجراست...")

    await stop_event.wait()
    print("🛑 سیگنال خاموشی گرفتم؛ اسکریپت‌ها رو متوقف و وضعیت رو ذخیره می‌کنم...")
    _shutting_down = True
    for uid in list(procs.keys()):
        try:
            await stop_script(uid, manual=False)
        except Exception:
            pass
    save_state()
    for task in runners:
        task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
