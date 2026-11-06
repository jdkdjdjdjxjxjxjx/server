import asyncio
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
USERS_PER_PAGE = 8
MESSAGE_LIMIT = 3500
PIP_TIMEOUT = 300
STOP_GRACE = 5
BROADCAST_DELAY = 0.15
ENTRY_PRIORITY = ("main.py", "bot.py", "app.py", "run.py", "start.py", "index.py")
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))

DIVIDER = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
SOFT = "· · · · · · · · · · · ·"

# ───────────────────────── دکمه‌ها ─────────────────────────

BTN_SEND = "📤 ارسال zip / py"
BTN_START = "▶️ استارت"
BTN_STOP = "⏹ استوپ"
BTN_RESTART = "🔄 ری‌استارت"
BTN_STATUS = "📊 وضعیت"
BTN_LOG = "📜 لاگ اسکریپت"
BTN_FILES = "📦 فایل‌های من"
BTN_BACKUP = "💾 بکاپ"
BTN_DELETE = "🗑 حذف اسکریپت"
BTN_HELP = "❕ راهنما"
BTN_ADMIN = "🛠 مدیریت"
BTN_MENU = "🏠 منوی اصلی"
BTN_CANCEL = "❌ انصراف"
BTN_YES = "✅ بله، مطمئنم"
BTN_NO = "❌ نه، بی‌خیال"

# نسخه‌ی غیرفعال دکمه‌ها (نمایشی — کاربر می‌بینه ولی پیام‌شون رد میشه)
BTN_START_OFF  = "▷ استارت"
BTN_STOP_OFF   = "◻ استوپ"
BTN_RESTART_OFF= "↺ ری‌استارت"
BTN_LOG_OFF    = "· لاگ اسکریپت"
BTN_FILES_OFF  = "· فایل‌های من"
BTN_BACKUP_OFF = "· بکاپ"
BTN_DELETE_OFF = "· حذف اسکریپت"

_DISABLED_BTNS = {
    BTN_START_OFF, BTN_STOP_OFF, BTN_RESTART_OFF,
    BTN_LOG_OFF, BTN_FILES_OFF, BTN_BACKUP_OFF, BTN_DELETE_OFF,
}

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
    u = users.get(user_id) or {}
    has_script = bool(u.get("script"))
    running = has_script and is_running(user_id)

    if not has_script:
        # ── هیچ اسکریپتی آپلود نشده ──
        rows = [
            [BTN_SEND],
            [BTN_START_OFF,  BTN_STOP_OFF],
            [BTN_RESTART_OFF, BTN_STATUS],
            [BTN_LOG_OFF,    BTN_FILES_OFF],
            [BTN_BACKUP_OFF],
            [BTN_DELETE_OFF, BTN_HELP],
        ]
    elif running:
        # ── اسکریپت در حال اجراست ──
        rows = [
            [BTN_SEND],
            [BTN_START_OFF,  BTN_STOP],
            [BTN_RESTART,    BTN_STATUS],
            [BTN_LOG,        BTN_FILES],
            [BTN_BACKUP],
            [BTN_DELETE,     BTN_HELP],
        ]
    else:
        # ── اسکریپت هست ولی متوقفه ──
        rows = [
            [BTN_SEND],
            [BTN_START,      BTN_STOP_OFF],
            [BTN_RESTART_OFF, BTN_STATUS],
            [BTN_LOG,        BTN_FILES],
            [BTN_BACKUP],
            [BTN_DELETE,     BTN_HELP],
        ]

    if user_id == ADMIN_ID:
        rows.append([BTN_ADMIN])
    return kb(rows)


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
    return (
        f"✨ سلام {name} عزیز، به هاست اسکریپت خوش اومدی ✨\n"
        f"{DIVIDER}\n"
        "📤 فایل zip یا py رو بفرست\n"
        "🔎 خودم پیداش می‌کنم و آماده‌ش می‌کنم\n"
        "▶️ با یه کلیک اجراش کن\n"
        "⏹ هر وقت خواستی خاموشش کن\n"
        f"{DIVIDER}\n"
        "از منوی پایین شروع کن 👇"
    )


def txt_help() -> str:
    return (
        "❕ راهنما\n"
        f"{DIVIDER}\n"
        f"{BTN_SEND}\n"
        "   فایل py یا zip می‌فرستی. اگه zip باشه استخراج میشه و فایل اصلی خودکار پیدا میشه.\n\n"
        f"{BTN_START} / {BTN_STOP} / {BTN_RESTART}\n"
        "   اجرا، خاموش کردن و راه‌اندازی دوباره‌ی اسکریپت.\n\n"
        f"{BTN_STATUS}\n"
        "   وضعیت اجرا، مدت روشن بودن و کد خروج.\n\n"
        f"{BTN_LOG}\n"
        "   آخرین خروجی (print و خطاهای) اسکریپتت.\n\n"
        f"{BTN_FILES}\n"
        "   فایل‌هات رو به‌صورت zip پس می‌گیری.\n\n"
        f"{BTN_BACKUP}\n"
        "   از کل محتویات پوشه‌ت (کد، دیتابیس، فایل‌های ساخته‌شده) یه zip می‌گیره و برات می‌فرسته.\n\n"
        f"{BTN_DELETE}\n"
        "   اسکریپتت و حافظه‌ش رو کامل پاک می‌کنه.\n"
        f"{DIVIDER}\n"
        "💡 اگه کنار اسکریپت فایل requirements.txt باشه، کتابخونه‌ها خودکار نصب میشن.\n"
        f"💡 حداکثر حجم فایل: {fa(MAX_UPLOAD_MB)} مگابایت"
    )


def txt_upload_prompt() -> str:
    return (
        "📤 ارسال اسکریپت\n"
        f"{DIVIDER}\n"
        "فایل خودت رو همین‌جا بفرست:\n"
        "• 🗜 فایل zip (کل پروژه)\n"
        "• 🐍 فایل py (تک‌فایل)\n"
        f"{SOFT}\n"
        f"📏 حداکثر حجم: {fa(MAX_UPLOAD_MB)} مگابایت\n"
        "❌ برای برگشت «انصراف» رو بزن."
    )


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
    pys = list_py(root)
    if not pys:
        return None
    for name in ENTRY_PRIORITY:
        hits = sorted([p for p in pys if os.path.basename(p) == name], key=lambda p: p.count(os.sep))
        if hits:
            return hits[0]
    pys.sort(key=lambda p: (p.count(os.sep), -os.path.getsize(os.path.join(root, p))))
    return pys[0]


def build_zip(src_dir: str, out_path: str):
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for r, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", DEPS_DIRNAME)
                       and not os.path.islink(os.path.join(r, d))]
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


async def fetch_document(message, doc: dict, dest: str):
    errors = []
    loop = asyncio.get_running_loop()
    obj, fid, url = doc["obj"], doc["fid"], doc["url"]

    if isinstance(url, str) and url.startswith("http"):
        try:
            if await loop.run_in_executor(None, _http_download, url, dest):
                return True, ""
        except Exception as e:
            errors.append(f"url: {type(e).__name__}: {e}")

    for holder in (obj, message):
        for mname in ("download", "download_to_drive", "download_media", "save"):
            fn = getattr(holder, mname, None)
            if not callable(fn):
                continue
            for args, kwargs in (((dest,), {}), ((), {"file_path": dest}), ((), {"path": dest}), ((), {})):
                try:
                    res = await _maybe_await(fn(*args, **kwargs))
                    if _absorb_result(res, dest):
                        return True, ""
                except TypeError:
                    continue
                except Exception as e:
                    errors.append(f"{mname}: {type(e).__name__}: {e}")
                    break

    if fid is not None:
        patterns = [((fid, dest), {}), ((fid,), {}), ((), {"file_id": fid, "destination": dest}),
                    ((), {"file_id": fid, "dest": dest}), ((), {"file_id": fid, "path": dest}),
                    ((), {"file_id": fid, "file_path": dest}), ((), {"file_id": fid})]
        for mname in ("download_file", "download_media", "download_document", "get_file_content"):
            fn = getattr(bot, mname, None)
            if not callable(fn):
                continue
            for args, kwargs in patterns:
                try:
                    res = await _maybe_await(fn(*args, **kwargs))
                    if _absorb_result(res, dest):
                        return True, ""
                except TypeError:
                    continue
                except Exception as e:
                    errors.append(f"bot.{mname}: {type(e).__name__}: {e}")
                    break
        fn = getattr(bot, "get_file", None)
        if callable(fn):
            for args, kwargs in (((fid,), {}), ((), {"file_id": fid})):
                try:
                    info = await _maybe_await(fn(*args, **kwargs))
                except TypeError:
                    continue
                except Exception as e:
                    errors.append(f"bot.get_file: {type(e).__name__}: {e}")
                    break
                try:
                    if _absorb_result(info, dest):
                        return True, ""
                except Exception:
                    pass
                link = _g(info, "url", "file_url", "download_url", "link", "file_path", "path")
                if isinstance(link, str) and link.startswith("http"):
                    try:
                        if await loop.run_in_executor(None, _http_download, link, dest):
                            return True, ""
                    except Exception as e:
                        errors.append(f"get_file url: {type(e).__name__}: {e}")
                break

    try:
        print("❌ دانلود فایل ناموفق بود. شیء فایل:", repr(obj)[:500], "| attrs:", [a for a in dir(obj) if not a.startswith("_")][:60])
    except Exception:
        pass
    return False, "; ".join(errors)[:300]


# ───────────────────────── اجرای اسکریپت‌ها ─────────────────────────

def is_running(uid: int) -> bool:
    rec = procs.get(uid)
    return bool(rec and rec["proc"].returncode is None)


def read_log_tail(uid: int, lines: int = LOG_TAIL_LINES) -> str:
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
SANDBOX_UID_BASE = 100000
SANDBOX_MAX_PROCS = 256
SANDBOX_MAX_FILE_MB = 200
SANDBOX_MAX_MEM_MB = int(os.environ.get("SANDBOX_MAX_MEM_MB", "0"))  # 0 = بدون سقف
ALLOW_UNSANDBOXED = os.environ.get("ALLOW_UNSANDBOXED") == "1"
SANDBOX_MODE = "none"  # uid | bwrap | none
_ENV_KEEP = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE")


def sbx_uid(uid: int) -> int:
    return SANDBOX_UID_BASE + (int(uid) % 3_000_000_000)


def _path_traversable(path: str) -> bool:
    p = os.path.abspath(path)
    while True:
        try:
            if not (os.stat(p).st_mode & 0o001):
                return False
        except OSError:
            return False
        parent = os.path.dirname(p)
        if parent == p:
            return True
        p = parent


def detect_sandbox() -> str:
    global SANDBOX_MODE
    SANDBOX_MODE = "none"
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        SANDBOX_MODE = "uid"
    elif shutil.which("bwrap"):
        try:
            r = subprocess.run(["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "true"],
                               capture_output=True, timeout=10)
            if r.returncode == 0:
                SANDBOX_MODE = "bwrap"
        except Exception:
            pass
    return SANDBOX_MODE


def harden_core():
    """فایل‌های هسته رو برای بقیه‌ی یوزرهای سیستم نخوندنی می‌کنه."""
    if SANDBOX_MODE != "uid":
        return
    try:
        st = os.stat(BASE_DIR).st_mode
        os.chmod(BASE_DIR, (st & ~0o006) | 0o001)
        for p in (DATA_DIR, USERS_DIR):
            os.chmod(p, 0o711)
        for p in (TMP_DIR, LOGS_DIR):
            os.chmod(p, 0o700)
        os.chmod(os.path.abspath(__file__), 0o600)
        if os.path.isfile(STATE_FILE):
            os.chmod(STATE_FILE, 0o600)
        for name in os.listdir(BASE_DIR):
            if name.startswith(".env"):
                try:
                    os.chmod(os.path.join(BASE_DIR, name), 0o600)
                except OSError:
                    pass
    except Exception as e:
        print(f"⚠️ harden_core: {type(e).__name__}: {e}")
    if not _path_traversable(BASE_DIR) or not _path_traversable(sys.executable):
        print("⚠️ مسیر پروژه یا پایتون برای یوزرهای ایزوله قابل عبور نیست (o+x لازم داره)؛ "
              "اسکریپت کاربرها ممکنه اجرا نشه.")


def prepare_user_dir(uid: int):
    """پوشه‌ی کاربر مال root میمونه؛ فقط code/ به یوزر ایزوله داده میشه."""
    if SANDBOX_MODE != "uid":
        return
    su = sbx_uid(uid)
    ud = user_dir(uid)
    os.makedirs(ud, exist_ok=True)
    os.chown(ud, 0, 0)
    os.chmod(ud, 0o711)
    cd = code_dir(uid)
    if os.path.isdir(cd) and not os.path.islink(cd):
        os.lchown(cd, su, su)
        os.chmod(cd, 0o700)
        for r, dirs, files in os.walk(cd):
            for n in dirs + files:
                try:
                    os.lchown(os.path.join(r, n), su, su)
                except OSError:
                    pass


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


def _limits_uid():
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NPROC, (SANDBOX_MAX_PROCS, SANDBOX_MAX_PROCS))
        fs = SANDBOX_MAX_FILE_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (fs, fs))
        if SANDBOX_MAX_MEM_MB:
            m = SANDBOX_MAX_MEM_MB * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (m, m))
    except Exception:
        pass


def _bwrap_argv(uid: int, argv: list, cwd: str) -> list:
    cd = os.path.realpath(code_dir(uid))
    base = os.path.realpath(BASE_DIR)
    a = ["bwrap", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--die-with-parent", "--new-session",
         "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--tmpfs", base]
    prefix = os.path.realpath(sys.prefix)
    if prefix.startswith(base + os.sep):
        a += ["--ro-bind", prefix, prefix]
    home = os.path.realpath(os.path.expanduser("~"))
    if home not in ("/", base) and not home.startswith(base + os.sep) and os.path.isdir(home):
        a += ["--tmpfs", home]
    a += ["--bind", cd, cd, "--chdir", cwd, "--"]
    return a + list(argv)


async def spawn_sandboxed(uid: int, argv: list, cwd: str, stdout):
    kwargs = dict(cwd=cwd, stdout=stdout, stderr=asyncio.subprocess.STDOUT,
                  stdin=asyncio.subprocess.DEVNULL, start_new_session=True, env=clean_env(uid))
    if SANDBOX_MODE == "uid":
        su = sbx_uid(uid)
        return await asyncio.create_subprocess_exec(
            *argv, user=su, group=su, extra_groups=[], preexec_fn=_limits_uid, **kwargs)
    if SANDBOX_MODE == "bwrap":
        return await asyncio.create_subprocess_exec(*_bwrap_argv(uid, argv, cwd), **kwargs)
    if ALLOW_UNSANDBOXED:
        return await asyncio.create_subprocess_exec(*argv, **kwargs)
    raise RuntimeError("sandbox unavailable")


NO_SANDBOX_MSG = ("⛔ ایزوله‌سازی روی سرور فعال نیست و برای امنیت هسته، اجرای اسکریپت‌ها بسته شده.\n"
                  "به مدیریت خبر بده.")



async def install_requirements(uid: int):
    root = code_dir(uid)
    req = None
    for r, _dirs, files in os.walk(root):
        if "requirements.txt" in files:
            req = os.path.join(r, "requirements.txt")
            break
    if not req:
        return None
    if SANDBOX_MODE == "none" and not ALLOW_UNSANDBOXED:
        return False
    proc = None
    try:
        prepare_user_dir(uid)
        deps = os.path.join(root, DEPS_DIRNAME)
        argv = [sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                "--no-cache-dir", "--target", deps, "-r", req]
        proc = await spawn_sandboxed(uid, argv, root, asyncio.subprocess.PIPE)
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
        return False, "هنوز اسکریپتی نفرستادی. اول «ارسال zip / py» رو بزن."
    if is_running(uid):
        return False, "اسکریپتت همین الان روشنه ✅"
    entry = os.path.join(code_dir(uid), sc["entry"])
    if not os.path.isfile(entry):
        return False, "فایل اسکریپت پیدا نشد، دوباره بفرستش."
    if SANDBOX_MODE == "none" and not ALLOW_UNSANDBOXED:
        return False, NO_SANDBOX_MSG
    kill_stale(uid)
    lp = log_path(uid)
    try:
        prepare_user_dir(uid)
        if os.path.isfile(lp) and os.path.getsize(lp) > MAX_LOG_BYTES:
            open(lp, "wb").close()
        logf = open(lp, "ab")
        logf.write(f"\n===== start {datetime.now(IRAN_TZ).strftime('%Y-%m-%d %H:%M:%S')} =====\n".encode())
        logf.flush()
        proc = await spawn_sandboxed(uid, [sys.executable, "-u", os.path.basename(entry)],
                                     os.path.dirname(entry), logf)
        logf.close()
    except Exception as e:
        return False, f"اجرا نشد: {type(e).__name__}: {e}"
    rec = {"proc": proc, "started": time.time(), "manual": False}
    procs[uid] = rec
    u["starts"] = u.get("starts", 0) + 1
    u["was_running"] = True
    u["pid"] = proc.pid
    u["last_start"] = time.time()
    save_state()
    spawn(watch_script(uid, rec))
    return True, "اسکریپت با موفقیت استارت شد 🚀"


async def watch_script(uid: int, rec: dict):
    code = await rec["proc"].wait()
    if procs.get(uid) is rec:
        procs.pop(uid, None)
    u = users.get(uid)
    if not u:
        return
    u["last_exit"] = code
    u["pid"] = None
    if rec["manual"] or _shutting_down:
        save_state()
        return
    u["was_running"] = False
    save_state()
    chat_id = u.get("chat_id")
    if chat_id:
        tail = read_log_tail(uid, 12)
        msg = f"⚠️ اسکریپتت متوقف شد (کد خروج: {fa(code)})"
        if tail:
            msg += f"\n{DIVIDER}\n{tail[-1500:]}"
        msg += f"\n{DIVIDER}\nبرای اجرای دوباره «{BTN_START}» رو بزن."
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
        return "📊 وضعیت\n" + DIVIDER + "\n📭 هنوز اسکریپتی نفرستادی."
    lines = ["📊 وضعیت اسکریپت", DIVIDER]
    if is_running(uid):
        rec = procs[uid]
        lines.append("🟢 در حال اجرا")
        lines.append(f"⏱ مدت روشن بودن: {fmt_dur(time.time() - rec['started'])}")
        lines.append(f"🆔 PID: {fa(rec['proc'].pid)}")
    else:
        lines.append("🔴 خاموش")
        if u.get("last_exit") is not None:
            lines.append(f"🔚 آخرین کد خروج: {fa(u['last_exit'])}")
    lines.append(SOFT)
    lines.append(f"🐍 فایل اصلی: {sc['entry']}")
    lines.append(f"📦 حجم: {fmt_size(dir_size(code_dir(uid)))}")
    lines.append(f"📅 آخرین آپلود: {fmt_time(sc.get('uploaded_at'))}")
    lines.append(f"🔁 تعداد استارت: {fa(u.get('starts', 0))}")
    return "\n".join(lines)


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
            raise ValueError("داخل zip هیچ فایل py پیدا نشد")
    else:
        name = safe_filename(orig_name)
        if not name.endswith(".py"):
            name += ".py"
        shutil.move(tmp_file, os.path.join(new_code, name))
        entry = name
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
        return
    upload_state.discard(uid)

    name = doc["name"]
    lower = name.lower()
    if name and not (lower.endswith(".zip") or lower.endswith(".py")):
        await plain_send(chat_id, "⚠️ فقط فایل zip یا py قبول می‌کنم.\nدوباره امتحان کن 👇",
                         reply_markup=kb_cancel())
        upload_state.add(uid)
        return
    size = doc["size"]
    if isinstance(size, (int, float)) and size > MAX_UPLOAD_MB * 1024 * 1024:
        await plain_send(chat_id, f"⚠️ حجم فایل بیشتر از {fa(MAX_UPLOAD_MB)} مگابایته.", reply_markup=kb_user_menu(uid))
        return

    async with _lock(uid):
        wait_msg = await plain_send(chat_id, "⏳ فایل دریافت شد، در حال بررسی...", reply_markup=kb_cancel())
        os.makedirs(user_dir(uid), exist_ok=True)
        tmp_file = os.path.join(TMP_DIR, f"{uid}_{int(time.time())}_{safe_filename(name or 'upload')}")
        ok, err = await fetch_document(message, doc, tmp_file)
        if not ok:
            await plain_send(chat_id, "❌ نتونستم فایل رو دانلود کنم. دوباره بفرستش.\n"
                                       "اگه تکرار شد به مدیریت بگو.", reply_markup=kb_user_menu(uid))
            if err:
                print(f"❌ fetch_document: {err}")
            return
        try:
            if os.path.getsize(tmp_file) > MAX_UPLOAD_MB * 1024 * 1024:
                os.remove(tmp_file)
                await plain_send(chat_id, f"⚠️ حجم فایل بیشتر از {fa(MAX_UPLOAD_MB)} مگابایته.", reply_markup=kb_user_menu(uid))
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
            await plain_send(chat_id, f"❌ فایل پردازش نشد: {e}", reply_markup=kb_user_menu(uid))
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

        pip_note = ""
        if os.path.isdir(code_dir(uid)):
            res = await install_requirements(uid)
            if res is True:
                pip_note = "\n📚 کتابخونه‌های requirements.txt نصب شدن"
            elif res is False:
                pip_note = "\n⚠️ نصب بعضی کتابخونه‌ها ناموفق بود"

        text = (
            "✅ با موفقیت دریافت و پیدا شد!\n"
            f"{DIVIDER}\n"
            f"🗂 نوع فایل: {'zip (استخراج شد)' if kind == 'zip' else 'py'}\n"
            f"🐍 فایل اصلی: {entry}\n"
            f"📄 تعداد فایل‌ها: {fa(files)}\n"
            f"📦 حجم: {fmt_size(dir_size(code_dir(uid)))}"
            f"{pip_note}\n"
            f"{DIVIDER}\n"
            f"برای اجرا «{BTN_START}» رو بزن 👇"
        )
        if was_running:
            text += "\n\n♻️ اسکریپت قبلیت متوقف شد و نسخه‌ی جدید جایگزین شد."
        await plain_send(chat_id, text, reply_markup=kb_after_upload())


# ───────────────────────── عملیات کاربر ─────────────────────────

async def act_start(uid: int, chat_id: int):
    await plain_send(chat_id, "⏳ در حال استارت...", reply_markup=kb_user_menu(uid))
    ok, msg = await start_script(uid)
    await plain_send(chat_id, ("🚀 " if ok else "⚠️ ") + msg, reply_markup=kb_user_menu(uid))
    if ok:
        await asyncio.sleep(2)
        if not is_running(uid):
            return
        tail = read_log_tail(uid, 8)
        if tail:
            await plain_send(chat_id, f"📜 خروجی اولیه:\n{DIVIDER}\n{tail[-1200:]}", reply_markup=kb_user_menu(uid))


async def act_stop(uid: int, chat_id: int):
    if await stop_script(uid, manual=True):
        await plain_send(chat_id, "⏹ اسکریپت متوقف شد.", reply_markup=kb_user_menu(uid))
    else:
        await plain_send(chat_id, "ℹ️ اسکریپتت الان خاموشه.", reply_markup=kb_user_menu(uid))


async def act_restart(uid: int, chat_id: int):
    await stop_script(uid, manual=True)
    await act_start(uid, chat_id)


async def act_log(uid: int, chat_id: int, target_uid=None):
    owner = target_uid or uid
    tail = read_log_tail(owner)
    markup = kb_target(owner) if target_uid else kb_user_menu(uid)
    if not tail:
        await plain_send(chat_id, "📜 هنوز لاگی ثبت نشده.", reply_markup=markup)
        return
    await send_long(chat_id, f"📜 آخرین خروجی اسکریپت\n{DIVIDER}\n{tail}", reply_markup=markup)


async def send_user_zip(chat_id: int, owner: int, markup):
    u = users.get(owner) or {}
    if not u.get("script") or not os.path.isdir(code_dir(owner)):
        await plain_send(chat_id, "📭 این کاربر اسکریپتی نداره.", reply_markup=markup)
        return
    out = os.path.join(TMP_DIR, f"{owner}_{int(time.time())}.zip")
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, build_zip, code_dir(owner), out)
        caption = f"👤 {full_name(u)}\n🆔 {owner}" + (f"\n🔗 @{u['username']}" if u.get("username") else "")
        sent = await send_document_file(chat_id, out, caption)
        if sent is None:
            await plain_send(chat_id, "❌ ارسال فایل ناموفق بود.", reply_markup=markup)
        else:
            await plain_send(chat_id, "✅ zip ارسال شد.", reply_markup=markup)
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


def build_full_backup_zip(src_dir: str, out_path: str):
    """کل محیط کاربر رو zip می‌کنه (کد + دیتابیس + فایل‌های ساخته‌شده)."""
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for r, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__",)
                       and not os.path.islink(os.path.join(r, d))]
            for f in files:
                full = os.path.join(r, f)
                if os.path.islink(full) or not os.path.isfile(full):
                    continue
                try:
                    z.write(full, os.path.relpath(full, src_dir))
                except OSError:
                    continue


async def send_backup(chat_id: int, uid: int):
    u = users.get(uid) or {}
    if not u.get("script") or not os.path.isdir(user_dir(uid)):
        await plain_send(chat_id, "📭 اسکریپتی نداری که ازش بکاپ بگیرم.", reply_markup=kb_user_menu(uid))
        return
    await plain_send(chat_id, "⏳ در حال ساخت بکاپ کامل محیط...", reply_markup=kb_user_menu(uid))
    stamp = datetime.now(IRAN_TZ).strftime("%Y%m%d_%H%M")
    out = os.path.join(TMP_DIR, f"backup_{uid}_{stamp}.zip")
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, build_full_backup_zip, user_dir(uid), out)
        size = os.path.getsize(out)
        caption = (f"💾 بکاپ کامل محیط\n{DIVIDER}\n🕒 {fmt_time(time.time())}\n"
                   f"📦 حجم: {fmt_size(size)}\n"
                   "شامل: کد، دیتابیس و همه‌ی فایل‌های ساخته‌شده\n"
                   "برای بازگردانی کد، پوشه‌ی code رو از zip بفرست.")
        sent = await send_document_file(chat_id, out, caption)
        if sent is None:
            await plain_send(chat_id, "❌ ارسال بکاپ ناموفق بود (شاید حجمش زیاده).", reply_markup=kb_user_menu(uid))
        else:
            await plain_send(chat_id, "✅ بکاپ کامل ارسال شد.", reply_markup=kb_user_menu(uid))
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
    caption = f"👤 {full_name(u)}\n🆔 {owner}" + (f"\n🔗 @{u['username']}" if u.get("username") else "")
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
    return (
        "📈 آمار سرور\n"
        f"{DIVIDER}\n"
        f"👥 کل کاربرها: {fa(total)}\n"
        f"🕐 فعال در ۲۴ ساعت اخیر: {fa(active)}\n"
        f"📦 دارای اسکریپت: {fa(with_script)}\n"
        f"🟢 اسکریپت روشن: {fa(running)}\n"
        f"🚫 مسدودشده: {fa(banned)}\n"
        f"💾 فضای مصرفی: {fmt_size(disk)}"
    )


async def do_broadcast(admin_chat_id: int, text: str):
    sent = failed = 0
    body = f"📢 پیام مدیریت\n{DIVIDER}\n{text}"
    for uid, u in list(users.items()):
        chat = u.get("chat_id")
        if not chat or u.get("banned"):
            continue
        if await plain_send(chat, body) is None:
            failed += 1
        else:
            sent += 1
        await asyncio.sleep(BROADCAST_DELAY)
    await plain_send(admin_chat_id, f"📢 پیام همگانی تموم شد.\n✅ موفق: {fa(sent)}\n❌ ناموفق: {fa(failed)}",
                     reply_markup=kb_admin_panel())


async def admin_handle(text: str, chat_id: int, user_id: int) -> bool:
    state = admin_state.get(user_id)

    if text == BTN_ADMIN:
        admin_state[user_id] = {"mode": "panel"}
        await plain_send(chat_id, f"🛠 پنل مدیریت\n{DIVIDER}\nیکی از گزینه‌ها رو انتخاب کن 👇", reply_markup=kb_admin_panel())
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
        await plain_send(chat_id, f"🛠 پنل مدیریت\n{DIVIDER}", reply_markup=kb_admin_panel())
        return True

    if mode == "broadcast_text":
        if text == ADM_CANCEL:
            admin_state[user_id] = {"mode": "panel"}
            await plain_send(chat_id, "لغو شد.", reply_markup=kb_admin_panel())
            return True
        state.update(mode="broadcast_confirm", text=text)
        await plain_send(chat_id, f"👀 پیش‌نمایش:\n{DIVIDER}\n{text}\n{DIVIDER}\nارسال بشه؟", reply_markup=kb([[ADM_SEND, ADM_CANCEL]]))
        return True
    if mode == "broadcast_confirm":
        if text == ADM_SEND:
            msg = state.get("text", "")
            admin_state[user_id] = {"mode": "panel"}
            await plain_send(chat_id, "⏳ در حال ارسال به همه...", reply_markup=kb_admin_panel())
            spawn(do_broadcast(chat_id, msg))
        else:
            admin_state[user_id] = {"mode": "panel"}
            await plain_send(chat_id, "لغو شد.", reply_markup=kb_admin_panel())
        return True

    if mode == "user_message":
        target = state.get("target")
        if text == ADM_CANCEL:
            await show_target(chat_id, state, target)
            return True
        chat = users.get(target, {}).get("chat_id")
        ok = chat and await plain_send(chat, f"✉️ پیام مدیریت\n{DIVIDER}\n{text}")
        await plain_send(chat_id, "✅ پیام ارسال شد." if ok else "❌ ارسال نشد.", reply_markup=kb_target(target))
        state["mode"] = "target"
        return True

    if mode == "search":
        if text == ADM_CANCEL:
            admin_state[user_id] = {"mode": "panel"}
            await plain_send(chat_id, "لغو شد.", reply_markup=kb_admin_panel())
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
            await plain_send(chat_id, "لغو شد.", reply_markup=kb_target(target))
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
            lines = [f"🟢 اسکریپت‌های روشن ({fa(len(running))})", DIVIDER]
            for i in running:
                lines.append(f"👤 {full_name(users[i])} • {i}\n   ⏱ {fmt_dur(time.time() - procs[i]['started'])} | 🐍 {users[i]['script']['entry']}")
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
              BTN_HELP, BTN_ADMIN, BTN_MENU, BTN_CANCEL} | _DISABLED_BTNS


@bot.on(Filters.command("start"))
async def start_handler(update: Update):
    message = update.message
    user = message.from_user
    u = touch_user(user, message.chat.id)
    upload_state.discard(user.id)
    confirm_state.pop(user.id, None)
    admin_state.pop(user.id, None)
    if u.get("banned") and user.id != ADMIN_ID:
        await plain_send(message.chat.id, "🚫 دسترسی شما توسط مدیریت مسدود شده.")
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

    # دکمه‌های غیرفعال (نمایشی) رو بی‌صدا رد کن
    if text in _DISABLED_BTNS:
        return

    pending = confirm_state.get(uid)
    if pending:
        confirm_state.pop(uid, None)
        if pending == "delete" and text == BTN_YES:
            await reset_user_memory(uid)
            await plain_send(chat_id, "🗑 اسکریپت و حافظه‌ت کامل پاک شد.", reply_markup=kb_user_menu(uid))
        else:
            await plain_send(chat_id, "باشه، چیزی پاک نشد 🙂", reply_markup=kb_user_menu(uid))
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
        await plain_send(chat_id, "⚠️ لطفاً فایل zip یا py بفرست، نه متن.\nیا «انصراف» رو بزن.", reply_markup=kb_cancel())
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
    elif text == BTN_FILES:
        spawn(send_user_zip(chat_id, uid, kb_user_menu(uid)))
    elif text == BTN_BACKUP:
        spawn(send_backup(chat_id, uid))
    elif text == BTN_DELETE:
        if not u.get("script"):
            await plain_send(chat_id, "📭 اسکریپتی برای حذف نداری.", reply_markup=kb_user_menu(uid))
        else:
            confirm_state[uid] = "delete"
            await plain_send(chat_id, "⚠️ اسکریپت و همه‌ی فایل‌هات پاک بشه؟\nاین کار برگشت نداره.", reply_markup=kb_confirm())
    elif text == BTN_HELP:
        await plain_send(chat_id, txt_help(), reply_markup=kb_user_menu(uid))
    else:
        await plain_send(chat_id, "از منوی پایین یکی از گزینه‌ها رو انتخاب کن 👇", reply_markup=kb_user_menu(uid))


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
                await plain_send(u["chat_id"], "♻️ سرور دوباره بالا اومد و اسکریپتت خودکار استارت شد ✅",
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
    detect_sandbox()
    harden_core()
    for _uid in list(users.keys()):
        try:
            prepare_user_dir(_uid)
        except Exception as e:
            print(f"⚠️ prepare_user_dir({_uid}): {type(e).__name__}: {e}")
    if SANDBOX_MODE == "none":
        print("🚨 ایزوله‌سازی در دسترس نیست (نه root هستم نه bwrap نصبه)."
              + (" ALLOW_UNSANDBOXED فعاله؛ اسکریپت‌ها بدون ایزوله اجرا میشن!" if ALLOW_UNSANDBOXED
                 else " اجرای اسکریپت کاربرها بسته شد."))
    else:
        print(f"🔒 ایزوله‌سازی فعال: {SANDBOX_MODE}")

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
