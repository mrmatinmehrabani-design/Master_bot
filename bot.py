import telebot
import sqlite3
import random
import string
import time
import threading
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict
from telebot import apihelper

# ═══════════════════════════════════════════
#  تنظیمات اصلی
# ═══════════════════════════════════════════
BOT_TOKEN = "8862870173:AAF_2YN96PKzM8HtPFrjKufQA6DGHJnedN4"
OWNER_ID = 5824863957
CARD_NUMBER = "6037-9917-9367-9279"
CARD_OWNER = "متین فقیه"
CHANNEL_ID = "@matstarvpn"
PANEL_PASSWORD_HASH = hashlib.sha256("Matin1388".encode()).hexdigest()

# ═══════════════════════════════════════════
#  تنظیمات پروکسی و اتصال پایدار
# ═══════════════════════════════════════════
#
#  گزینه ۱ — بهترین راه: سرور خارج ایران (هتزنر، اوراکل، ...)
#             در این صورت همه تنظیمات پروکسی رو خالی بذار
#
#  گزینه ۲ — سرور ایران با SOCKS5 لوکال:
#             مثلاً Xray/V2ray روی همون سرور نصب کن و پورت socks بده
#             PROXY_TYPE = "socks5"
#             PROXY_HOST = "127.0.0.1"
#             PROXY_PORT = 10808   # پورت socks خودت
#
#  گزینه ۳ — سرور ایران با HTTP proxy:
#             PROXY_TYPE = "http"
#             PROXY_HOST = "127.0.0.1"
#             PROXY_PORT = 10809
#
PROXY_TYPE = None   # "socks5" | "http" | None
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 10808

apihelper.ENABLE_MIDDLEWARE = False

if PROXY_TYPE == "socks5":
    apihelper.proxy = {
        "https": f"socks5h://{PROXY_HOST}:{PROXY_PORT}",
        "http":  f"socks5h://{PROXY_HOST}:{PROXY_PORT}",
    }
    print(f"🔌 SOCKS5 proxy فعال: {PROXY_HOST}:{PROXY_PORT}")
elif PROXY_TYPE == "http":
    apihelper.proxy = {
        "https": f"http://{PROXY_HOST}:{PROXY_PORT}",
        "http":  f"http://{PROXY_HOST}:{PROXY_PORT}",
    }
    print(f"🔌 HTTP proxy فعال: {PROXY_HOST}:{PROXY_PORT}")
else:
    print("🔌 بدون پروکسی (سرور خارج یا مستقیم)")

# تنظیم timeout برای جلوگیری از hang شدن
apihelper.SESSION_TIME_TO_LIVE = 5 * 60  # هر ۵ دقیقه session refresh

bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode=None,
    num_threads=8,
    skip_pending=True,          # پیام‌های قدیمی موقع restart نادیده گرفته بشن
)

# ═══════════════════════════════════════════
#  ضد اسپم
# ═══════════════════════════════════════════
spam_lock = threading.Lock()
spam_tracker = defaultdict(list)
SPAM_LIMIT = 8
SPAM_WINDOW = 10

def is_spam(user_id):
    if is_admin(user_id):
        return False
    now = time.time()
    with spam_lock:
        spam_tracker[user_id] = [t for t in spam_tracker[user_id] if now - t < SPAM_WINDOW]
        spam_tracker[user_id].append(now)
        return len(spam_tracker[user_id]) > SPAM_LIMIT

# ═══════════════════════════════════════════
#  دیتابیس
# ═══════════════════════════════════════════
db_lock = threading.Lock()

def get_conn():
    conn = sqlite3.connect("bot.db", check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def init_db():
    with db_lock:
        conn = get_conn()
        c = conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance INTEGER DEFAULT 0,
                is_blocked INTEGER DEFAULT 0,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, amount INTEGER,
                type TEXT, status TEXT,
                receipt_file_id TEXT, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, subject TEXT,
                message TEXT, status TEXT DEFAULT 'open', created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS discount_codes (
                code TEXT PRIMARY KEY,
                percent INTEGER, used INTEGER DEFAULT 0, max_use INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, config_name TEXT,
                config_text TEXT, amount_paid INTEGER,
                expire_date TEXT, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_key TEXT, config_text TEXT,
                is_used INTEGER DEFAULT 0,
                used_by INTEGER DEFAULT NULL, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS plans (
                plan_key TEXT PRIMARY KEY,
                name TEXT, gb INTEGER, price INTEGER,
                days INTEGER, plan_type TEXT DEFAULT 'single',
                is_active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT
            );
            CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_text TEXT, sent_count INTEGER DEFAULT 0, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS broadcast_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                broadcast_id INTEGER, user_id INTEGER, message_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS test_server (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_text TEXT, is_active INTEGER DEFAULT 1, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT, first_name TEXT,
                password_hash TEXT, permissions TEXT DEFAULT 'all',
                added_by INTEGER, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS panel_sessions (
                user_id INTEGER PRIMARY KEY,
                logged_in INTEGER DEFAULT 0, login_time TEXT
            );
        """)
        defaults = [
            ("shop_open", "1"),
            ("card_payment_open", "1"),
            ("test_server_enabled", "0"),
            ("maintenance_mode", "0"),
            ("auto_approve", "0"),
        ]
        for k, v in defaults:
            c.execute("INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)", (k, v))
        default_plans = [
            ("1gb",  "1️⃣ ۱ گیگابایت",  1,  15000,  30, "single"),
            ("2gb",  "2️⃣ ۲ گیگابایت",  2,  30000,  30, "single"),
            ("3gb",  "3️⃣ ۳ گیگابایت",  3,  45000,  30, "single"),
            ("5gb",  "5️⃣ ۵ گیگابایت",  5,  75000,  30, "single"),
            ("10gb", "🔟 ۱۰ گیگابایت", 10, 150000, 30, "single"),
            ("multi_15gb", "🌍 مولتی ۱۵ گیگ", 15, 180000, 30, "multi"),
            ("multi_20gb", "🌍 مولتی ۲۰ گیگ", 20, 220000, 30, "multi"),
        ]
        for p in default_plans:
            c.execute("INSERT OR IGNORE INTO plans (plan_key,name,gb,price,days,plan_type) VALUES (?,?,?,?,?,?)", p)
        conn.commit()
        conn.close()

init_db()

# ═══════════════════════════════════════════
#  توابع DB عمومی
# ═══════════════════════════════════════════
def db_exec(query, params=(), fetch=None):
    with db_lock:
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute(query, params)
            conn.commit()
            if fetch == "one": return c.fetchone()
            if fetch == "all": return c.fetchall()
            return c.lastrowid
        finally:
            conn.close()

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def fp(p):
    return f"{int(p):,} تومان"

# ── کاربران ──
def get_user(uid):
    return db_exec("SELECT * FROM users WHERE user_id=?", (uid,), "one")

def register_user(uid, username, first_name):
    db_exec("INSERT OR IGNORE INTO users (user_id,username,first_name,balance,created_at) VALUES (?,?,?,0,?)",
            (uid, username or "ندارد", first_name or "کاربر", now_str()))

def get_balance(uid):
    r = db_exec("SELECT balance FROM users WHERE user_id=?", (uid,), "one")
    return r[0] if r else 0

def update_balance(uid, amount):
    db_exec("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, uid))

def get_all_users():
    return db_exec("SELECT user_id,username,first_name,balance,is_blocked FROM users ORDER BY created_at DESC", fetch="all")

def search_user(query):
    try:
        return db_exec("SELECT * FROM users WHERE user_id=?", (int(query),), "one")
    except ValueError:
        return db_exec("SELECT * FROM users WHERE username LIKE ?", (f"%{query}%",), "one")

def block_user(uid, block=True):
    db_exec("UPDATE users SET is_blocked=? WHERE user_id=?", (1 if block else 0, uid))

def is_blocked(uid):
    r = db_exec("SELECT is_blocked FROM users WHERE user_id=?", (uid,), "one")
    return bool(r and r[0])

# ── تراکنش و خرید ──
def add_transaction(uid, amount, ttype, status, file_id=None):
    return db_exec(
        "INSERT INTO transactions (user_id,amount,type,status,receipt_file_id,created_at) VALUES (?,?,?,?,?,?)",
        (uid, amount, ttype, status, file_id, now_str()))

def update_transaction(tid, status):
    db_exec("UPDATE transactions SET status=? WHERE id=?", (status, tid))

def add_purchase(uid, cfg_name, cfg_text, amount, days=30):
    expire = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    db_exec("INSERT INTO purchases (user_id,config_name,config_text,amount_paid,expire_date,created_at) VALUES (?,?,?,?,?,?)",
            (uid, cfg_name, cfg_text, amount, expire, now_str()))

def get_purchases(uid):
    return db_exec("SELECT id,config_name,config_text,amount_paid,expire_date,created_at FROM purchases WHERE user_id=? ORDER BY created_at DESC", (uid,), "all")

def get_today_sales():
    today = datetime.now().strftime("%Y-%m-%d")
    r = db_exec("SELECT COUNT(*),SUM(amount_paid) FROM purchases WHERE created_at LIKE ?", (f"{today}%",), "one")
    return (r[0] or 0, r[1] or 0)

def get_total_sales():
    r = db_exec("SELECT COUNT(*),SUM(amount_paid) FROM purchases", fetch="one")
    return (r[0] or 0, r[1] or 0)

# ── پلن‌ها ──
def get_plans(plan_type=None):
    if plan_type:
        return db_exec("SELECT * FROM plans WHERE plan_type=? AND is_active=1 ORDER BY gb", (plan_type,), "all")
    return db_exec("SELECT * FROM plans WHERE is_active=1 ORDER BY plan_type,gb", fetch="all")

def get_plan(key):
    return db_exec("SELECT * FROM plans WHERE plan_key=?", (key,), "one")

def add_plan(key, name, gb, price, days, ptype):
    db_exec("INSERT OR REPLACE INTO plans (plan_key,name,gb,price,days,plan_type,is_active) VALUES (?,?,?,?,?,?,1)",
            (key, name, gb, price, days, ptype))

def toggle_plan(key):
    r = db_exec("SELECT is_active FROM plans WHERE plan_key=?", (key,), "one")
    if r:
        db_exec("UPDATE plans SET is_active=? WHERE plan_key=?", (0 if r[0] else 1, key))
        return not r[0]

def delete_plan(key):
    db_exec("DELETE FROM plans WHERE plan_key=?", (key,))

# ── کانفیگ‌ها ──
def add_config(key, text):
    db_exec("INSERT INTO configs (plan_key,config_text,is_used,created_at) VALUES (?,?,0,?)", (key, text, now_str()))

def get_available_config(key):
    return db_exec("SELECT id,config_text FROM configs WHERE plan_key=? AND is_used=0 LIMIT 1", (key,), "one")

def mark_config_used(cid, uid):
    db_exec("UPDATE configs SET is_used=1,used_by=? WHERE id=?", (uid, cid))

def get_config_stock(key):
    r = db_exec("SELECT COUNT(*) FROM configs WHERE plan_key=? AND is_used=0", (key,), "one")
    return r[0] if r else 0

def get_all_stock():
    rows = db_exec("SELECT plan_key,COUNT(*) FROM configs WHERE is_used=0 GROUP BY plan_key", fetch="all")
    return {r[0]: r[1] for r in rows} if rows else {}

def get_unused_configs(key):
    return db_exec("SELECT id,config_text,created_at FROM configs WHERE plan_key=? AND is_used=0 ORDER BY id", (key,), "all")

def delete_config_by_id(cid):
    with db_lock:
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("DELETE FROM configs WHERE id=? AND is_used=0", (cid,))
            affected = c.rowcount
            conn.commit()
            return affected > 0
        finally:
            conn.close()

# ── کد تخفیف ──
def add_discount(code, percent, max_use=1):
    db_exec("INSERT OR REPLACE INTO discount_codes (code,percent,used,max_use) VALUES (?,?,0,?)", (code, percent, max_use))

def delete_discount(code):
    db_exec("DELETE FROM discount_codes WHERE code=?", (code.upper(),))

def get_all_discounts():
    return db_exec("SELECT code,percent,used,max_use FROM discount_codes ORDER BY rowid DESC", fetch="all")

def check_discount(code):
    r = db_exec("SELECT percent,used,max_use FROM discount_codes WHERE code=?", (code.upper(),), "one")
    return r[0] if r and r[1] < r[2] else None

def use_discount(code):
    db_exec("UPDATE discount_codes SET used=used+1 WHERE code=?", (code.upper(),))

# ── تیکت ──
def add_ticket(uid, subject, message):
    return db_exec("INSERT INTO tickets (user_id,subject,message,created_at) VALUES (?,?,?,?)",
                   (uid, subject, message, now_str()))

# ── سرور تست ──
def get_test_server():
    return db_exec("SELECT * FROM test_server WHERE is_active=1 ORDER BY id DESC LIMIT 1", fetch="one")

def set_test_server(text):
    db_exec("UPDATE test_server SET is_active=0")
    db_exec("INSERT INTO test_server (config_text,is_active,created_at) VALUES (?,1,?)", (text, now_str()))

def delete_test_server():
    db_exec("UPDATE test_server SET is_active=0")

# ── تنظیمات ──
def get_setting(key):
    r = db_exec("SELECT value FROM settings WHERE key=?", (key,), "one")
    return r[0] if r else None

def set_setting(key, value):
    db_exec("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, str(value)))

def shop_is_open():       return get_setting("shop_open") == "1"
def card_is_open():       return get_setting("card_payment_open") == "1"
def test_enabled():       return get_setting("test_server_enabled") == "1"
def maintenance_mode():   return get_setting("maintenance_mode") == "1"
def auto_approve_enabled(): return get_setting("auto_approve") == "1"

# ── پیام همگانی ──
def save_broadcast(text, sent_count):
    return db_exec("INSERT INTO broadcasts (message_text,sent_count,created_at) VALUES (?,?,?)",
                   (text, sent_count, now_str()))

def save_broadcast_msg(bid, uid, mid):
    db_exec("INSERT INTO broadcast_messages (broadcast_id,user_id,message_id) VALUES (?,?,?)", (bid, uid, mid))

def get_broadcast_msgs(bid):
    return db_exec("SELECT user_id,message_id FROM broadcast_messages WHERE broadcast_id=?", (bid,), "all")

# ── ادمین‌ها ──
def is_owner(uid): return uid == OWNER_ID

def is_admin(uid):
    if uid == OWNER_ID: return True
    r = db_exec("SELECT user_id FROM admins WHERE user_id=?", (uid,), "one")
    return r is not None

def get_admins():
    return db_exec("SELECT * FROM admins ORDER BY created_at DESC", fetch="all")

def add_admin(uid, username, first_name, password, permissions="all", added_by=None):
    ph = hashlib.sha256(password.encode()).hexdigest()
    db_exec("INSERT OR REPLACE INTO admins (user_id,username,first_name,password_hash,permissions,added_by,created_at) VALUES (?,?,?,?,?,?,?)",
            (uid, username or "ندارد", first_name or "ادمین", ph, permissions, added_by, now_str()))

def remove_admin(uid):
    db_exec("DELETE FROM admins WHERE user_id=?", (uid,))

def verify_admin_password(uid, password):
    if uid == OWNER_ID:
        return hashlib.sha256(password.encode()).hexdigest() == PANEL_PASSWORD_HASH
    r = db_exec("SELECT password_hash FROM admins WHERE user_id=?", (uid,), "one")
    if not r: return False
    return hashlib.sha256(password.encode()).hexdigest() == r[0]

def is_panel_logged_in(uid):
    r = db_exec("SELECT logged_in FROM panel_sessions WHERE user_id=?", (uid,), "one")
    return bool(r and r[0])

def set_panel_login(uid, status):
    db_exec("INSERT OR REPLACE INTO panel_sessions (user_id,logged_in,login_time) VALUES (?,?,?)",
            (uid, 1 if status else 0, now_str()))

# ═══════════════════════════════════════════
#  State Machine
# ═══════════════════════════════════════════
state_lock = threading.Lock()
_user_state = {}

def set_state(uid, state):
    with state_lock: _user_state[uid] = state

def get_state(uid):
    with state_lock: return _user_state.get(uid, {})

def clear_state(uid):
    with state_lock: _user_state.pop(uid, None)

# ═══════════════════════════════════════════
#  ابزارهای کمکی
# ═══════════════════════════════════════════
def is_member(uid):
    try:
        m = bot.get_chat_member(CHANNEL_ID, uid)
        return m.status in ["member","administrator","creator"]
    except Exception as e:
        print(f"[channel err]: {e}")
        return True

def safe_send(uid, text, **kw):
    try: return bot.send_message(uid, text, **kw)
    except Exception as e: print(f"[send err {uid}]: {e}")

def safe_edit(uid, mid, text, **kw):
    try: return bot.edit_message_text(text, uid, mid, **kw)
    except Exception as e: print(f"[edit err]: {e}")

def notify_admins(text, markup=None):
    for adm in (get_admins() or []):
        if markup: safe_send(adm['user_id'], text, reply_markup=markup)
        else: safe_send(adm['user_id'], text)
    if markup: safe_send(OWNER_ID, text, reply_markup=markup)
    else: safe_send(OWNER_ID, text)

# ═══════════════════════════════════════════
#  کیبوردها
# ═══════════════════════════════════════════
def reply_keyboard():
    m = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    m.add(
        telebot.types.KeyboardButton("🏠 خانه"),
        telebot.types.KeyboardButton("🛒 خرید"),
        telebot.types.KeyboardButton("👛 کیف پول"),
    )
    m.add(
        telebot.types.KeyboardButton("👤 پروفایل"),
        telebot.types.KeyboardButton("📂 کانفیگ‌های من"),
        telebot.types.KeyboardButton("🎫 تیکت"),
    )
    m.add(
        telebot.types.KeyboardButton("🆓 سرور تست"),
        telebot.types.KeyboardButton("ℹ️ درباره ما"),
        telebot.types.KeyboardButton("🎟 کد تخفیف"),
    )
    return m

def admin_reply_keyboard():
    m = reply_keyboard()
    m.add(telebot.types.KeyboardButton("👑 پنل ادمین"))
    return m

def main_menu():
    m = telebot.types.InlineKeyboardMarkup(row_width=2)
    m.add(
        telebot.types.InlineKeyboardButton("🛒 خرید کانفیگ", callback_data="buy_menu"),
        telebot.types.InlineKeyboardButton("💰 کیف پول", callback_data="wallet_menu"),
    )
    m.add(
        telebot.types.InlineKeyboardButton("👤 حساب کاربری", callback_data="profile"),
        telebot.types.InlineKeyboardButton("📂 کانفیگ‌های من", callback_data="my_configs"),
    )
    m.add(
        telebot.types.InlineKeyboardButton("🎫 تیکت پشتیبانی", callback_data="ticket_menu"),
        telebot.types.InlineKeyboardButton("🎟 کد تخفیف", callback_data="discount_info"),
    )
    m.add(telebot.types.InlineKeyboardButton("ℹ️ درباره ما", callback_data="about_us"))
    if test_enabled() and get_test_server():
        m.add(telebot.types.InlineKeyboardButton("🆓 سرور تست رایگان", callback_data="get_test"))
    return m

def admin_menu():
    shop  = "🟢 باز"     if shop_is_open()         else "🔴 بسته"
    card  = "🟢 فعال"    if card_is_open()          else "🔴 غیرفعال"
    tst   = "🟢 فعال"    if test_enabled()           else "🔴 غیرفعال"
    maint = "🟢 روشن"    if maintenance_mode()       else "⚫ خاموش"
    auto  = "🟢 فعال"    if auto_approve_enabled()   else "🔴 غیرفعال"
    m = telebot.types.InlineKeyboardMarkup(row_width=1)
    m.add(
        telebot.types.InlineKeyboardButton("📦 مدیریت کانفیگ‌ها",      callback_data="adm_cfgs"),
        telebot.types.InlineKeyboardButton("📐 مدیریت پلن‌ها",          callback_data="adm_plans"),
        telebot.types.InlineKeyboardButton("👥 مدیریت کاربران",         callback_data="adm_users"),
        telebot.types.InlineKeyboardButton("🎟 مدیریت کدهای تخفیف",    callback_data="adm_discount_mgr"),
        telebot.types.InlineKeyboardButton("📊 آمار فروش",              callback_data="adm_stats"),
        telebot.types.InlineKeyboardButton("📢 ارسال همگانی",           callback_data="adm_broadcast"),
        telebot.types.InlineKeyboardButton("💬 پیام به کاربر",          callback_data="adm_dm"),
        telebot.types.InlineKeyboardButton("🆓 مدیریت سرور تست",        callback_data="adm_test"),
    )
    m.add(
        telebot.types.InlineKeyboardButton(f"🛒 فروشگاه: {shop}",       callback_data="adm_toggle_shop"),
        telebot.types.InlineKeyboardButton(f"💳 کارت: {card}",          callback_data="adm_toggle_card"),
    )
    m.add(
        telebot.types.InlineKeyboardButton(f"🤖 تأیید خودکار: {auto}",  callback_data="adm_toggle_auto"),
        telebot.types.InlineKeyboardButton(f"🆓 سرور تست: {tst}",       callback_data="adm_toggle_test"),
    )
    m.add(telebot.types.InlineKeyboardButton(f"🔧 حالت تعمیر: {maint}", callback_data="adm_toggle_maintenance"))
    if True:  # همیشه نشون بده چون is_owner چک میشه داخل handler
        m.add(telebot.types.InlineKeyboardButton("👑 مدیریت ادمین‌ها",  callback_data="adm_manage_admins"))
    m.add(telebot.types.InlineKeyboardButton("🔒 خروج از پنل",          callback_data="adm_logout"))
    return m

# ═══════════════════════════════════════════
#  /start و کیبورد پایین
# ═══════════════════════════════════════════
@bot.message_handler(commands=["start"])
def start(message):
    uid = message.from_user.id
    if is_spam(uid): return
    register_user(uid, message.from_user.username, message.from_user.first_name)
    clear_state(uid)
    if is_blocked(uid):
        safe_send(uid, "🚫 دسترسی شما مسدود شده است.")
        return
    if maintenance_mode() and not is_admin(uid):
        safe_send(uid,
            "🔧 ربات در حال بروزرسانی است\n\n"
            "⏳ به زودی برمی‌گردیم...\n"
            "از صبر شما متشکریم 🙏")
        return
    if not is_member(uid):
        mk = telebot.types.InlineKeyboardMarkup()
        mk.add(telebot.types.InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{CHANNEL_ID.lstrip('@')}"))
        mk.add(telebot.types.InlineKeyboardButton("✅ عضو شدم، بررسی کن", callback_data="check_join"))
        safe_send(uid,
            "👋 سلام! به ربات Mat Star VPN خوش آمدید!\n\n"
            f"🔒 برای استفاده باید در {CHANNEL_ID} عضو شوید.\n\n"
            "⬇️ پس از عضویت روی «✅ عضو شدم» بزنید.", reply_markup=mk)
        return
    name = message.from_user.first_name or "کاربر"
    kb = admin_reply_keyboard() if is_admin(uid) else reply_keyboard()
    safe_send(uid,
        f"✨ سلام {name} عزیز!\n"
        "🌟 به ربات Mat Star VPN خوش آمدید\n"
        "🚀 سرعت بالا | 🔐 امنیت | 💎 کیفیت\n\n"
        "از منوی زیر انتخاب کنید 👇",
        reply_markup=main_menu())
    safe_send(uid, "⌨️ دسترسی سریع:", reply_markup=kb)

REPLY_BUTTONS = [
    "🏠 خانه","🛒 خرید","👛 کیف پول","👤 پروفایل",
    "📂 کانفیگ‌های من","🎫 تیکت","🆓 سرور تست",
    "ℹ️ درباره ما","🎟 کد تخفیف","👑 پنل ادمین"
]

@bot.message_handler(func=lambda m: m.text in REPLY_BUTTONS)
def handle_reply(message):
    uid = message.from_user.id
    if is_spam(uid) or is_blocked(uid): return
    if maintenance_mode() and not is_admin(uid):
        safe_send(uid, "🔧 ربات در حال بروزرسانی است...")
        return
    t = message.text

    if t == "🏠 خانه":
        clear_state(uid)
        safe_send(uid, "🏠 منوی اصلی:", reply_markup=main_menu())

    elif t == "🛒 خرید":
        if not shop_is_open():
            safe_send(uid, "🔴 فروش فعلاً متوقف است.")
            return
        mk = telebot.types.InlineKeyboardMarkup(row_width=1)
        mk.add(
            telebot.types.InlineKeyboardButton("🖥 سرور تک لوکیشن",    callback_data="single_server"),
            telebot.types.InlineKeyboardButton("🌍 سرور مولتی لوکیشن", callback_data="multi_server"),
        )
        safe_send(uid, f"🛒 خرید کانفیگ\n\n💰 موجودی: {fp(get_balance(uid))}\n\nنوع سرور:", reply_markup=mk)

    elif t == "👛 کیف پول":
        balance = get_balance(uid)
        mk = telebot.types.InlineKeyboardMarkup(row_width=1)
        if card_is_open():
            mk.add(telebot.types.InlineKeyboardButton("➕ شارژ کیف پول", callback_data="charge_wallet"))
        else:
            mk.add(telebot.types.InlineKeyboardButton("🔴 شارژ (غیرفعال)", callback_data="charge_disabled"))
        mk.add(telebot.types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu"))
        safe_send(uid, f"💰 کیف پول\n\n💵 موجودی: {fp(balance)}", reply_markup=mk)

    elif t == "👤 پروفایل":
        user = get_user(uid)
        purchases = get_purchases(uid) or []
        uname = f"@{user['username']}" if user and user['username'] != "ندارد" else "—"
        role = "👑 رئیس" if is_owner(uid) else ("🛡 ادمین" if is_admin(uid) else "👤 کاربر")
        mk = telebot.types.InlineKeyboardMarkup()
        mk.add(telebot.types.InlineKeyboardButton("📂 کانفیگ‌های من", callback_data="my_configs"))
        safe_send(uid,
            f"👤 حساب کاربری\n\n🆔 {uid}\n👤 {uname}\n"
            f"💰 {fp(get_balance(uid))}\n📦 {len(purchases)} خرید\n🏷 {role}", reply_markup=mk)

    elif t == "📂 کانفیگ‌های من":
        purchases = get_purchases(uid) or []
        mk = telebot.types.InlineKeyboardMarkup(row_width=1)
        if not purchases:
            mk.add(telebot.types.InlineKeyboardButton("🛒 خرید کانفیگ", callback_data="buy_menu"))
            safe_send(uid, "📂 کانفیگ‌های من\n\n❌ هنوز کانفیگی ندارید.", reply_markup=mk)
            return
        text = f"📂 کانفیگ‌های من ({len(purchases)} عدد)\n\n"
        for i, p in enumerate(purchases[:5], 1):
            text += f"{'─'*18}\n#{i} {p[1]}\n📅 انقضا: {p[4] or '—'}\n"
        for i, p in enumerate(purchases[:5], 1):
            mk.add(telebot.types.InlineKeyboardButton(f"🔑 #{i} — {p[1]}", callback_data=f"view_cfg_{p[0]}"))
        safe_send(uid, text, reply_markup=mk)

    elif t == "🎫 تیکت":
        mk = telebot.types.InlineKeyboardMarkup()
        mk.add(telebot.types.InlineKeyboardButton("📝 ارسال تیکت جدید", callback_data="new_ticket"))
        safe_send(uid, "🎫 تیکت پشتیبانی\n\n📞 تیکت بزنید تا پاسخ بگیرید!", reply_markup=mk)

    elif t == "🆓 سرور تست":
        if not test_enabled():
            safe_send(uid, "❌ سرور تست فعال نیست!")
            return
        ts = get_test_server()
        if not ts:
            safe_send(uid, "❌ سرور تست موجود نیست!")
            return
        safe_send(uid, f"🆓 سرور تست رایگان\n\n📋 کانفیگ:\n{ts['config_text']}\n\n⚠️ موقت و برای تست")

    elif t == "ℹ️ درباره ما":
        mk = telebot.types.InlineKeyboardMarkup()
        mk.add(telebot.types.InlineKeyboardButton("📢 کانال ما", url=f"https://t.me/{CHANNEL_ID.lstrip('@')}"))
        safe_send(uid,
            "ℹ️ درباره Mat Star VPN\n\n🌐 VPN با کیفیت بالا\n"
            f"🔐 پروتکل‌های امن | ⚡ اتصال پایدار\n📢 {CHANNEL_ID}", reply_markup=mk)

    elif t == "🎟 کد تخفیف":
        set_state(uid, {"action": "enter_discount_check"})
        mk = telebot.types.InlineKeyboardMarkup()
        mk.add(telebot.types.InlineKeyboardButton("❌ انصراف", callback_data="main_menu"))
        safe_send(uid, "🎟 کد تخفیف خود را وارد کنید:", reply_markup=mk)

    elif t == "👑 پنل ادمین":
        if not is_admin(uid): return
        if not is_panel_logged_in(uid):
            set_state(uid, {"action": "panel_login"})
            safe_send(uid, "🔐 رمز عبور پنل را وارد کنید:")
        else:
            safe_send(uid, "👑 پنل ادمین:", reply_markup=admin_menu())

# ── ورود پنل ──
@bot.message_handler(func=lambda m: get_state(m.from_user.id).get("action") == "panel_login")
def panel_login_handler(message):
    uid = message.from_user.id
    if not is_admin(uid): return
    try: bot.delete_message(uid, message.message_id)
    except Exception: pass
    if verify_admin_password(uid, message.text.strip()):
        set_panel_login(uid, True)
        clear_state(uid)
        safe_send(uid, "✅ ورود موفق!", reply_markup=admin_menu())
    else:
        clear_state(uid)
        safe_send(uid, "❌ رمز اشتباه!")

# ── بررسی عضویت ──
@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def check_join(call):
    uid = call.from_user.id
    bot.answer_callback_query(call.id, "⏳ در حال بررسی...")
    if is_member(uid):
        name = call.from_user.first_name or "کاربر"
        try:
            bot.edit_message_text(
                f"✅ عضویت تأیید شد!\n✨ سلام {name} عزیز! 👇",
                uid, call.message.message_id, reply_markup=main_menu())
        except Exception: pass
        kb = admin_reply_keyboard() if is_admin(uid) else reply_keyboard()
        safe_send(uid, "⌨️ دسترسی سریع:", reply_markup=kb)
    else:
        bot.answer_callback_query(call.id, "❌ هنوز عضو نشدید!", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data == "main_menu")
def go_main(call):
    uid = call.from_user.id
    clear_state(uid)
    try:
        bot.edit_message_text("🏠 منوی اصلی 👇", uid, call.message.message_id, reply_markup=main_menu())
    except Exception:
        safe_send(uid, "🏠 منوی اصلی:", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda c: c.data == "about_us")
def about_us(call):
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("📢 کانال ما", url=f"https://t.me/{CHANNEL_ID.lstrip('@')}"))
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu"))
    safe_edit(call.from_user.id, call.message.message_id,
        f"ℹ️ Mat Star VPN\n\n🌐 VPN با کیفیت بالا\n🔐 امن | ⚡ سریع\n📢 {CHANNEL_ID}", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == "discount_info")
def discount_info(call):
    uid = call.from_user.id
    set_state(uid, {"action": "enter_discount_check"})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu"))
    safe_edit(uid, call.message.message_id, "🎟 کد تخفیف خود را وارد کنید:", reply_markup=mk)

@bot.message_handler(func=lambda m: get_state(m.from_user.id).get("action") == "enter_discount_check")
def check_discount_msg(message):
    uid = message.from_user.id
    code = message.text.strip().upper()
    percent = check_discount(code)
    clear_state(uid)
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🛒 خرید", callback_data="buy_menu"))
    mk.add(telebot.types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu"))
    if percent:
        safe_send(uid, f"✅ کد معتبر!\n🎟 {code}\n💯 تخفیف: {percent}%\n\nهنگام خرید استفاده کنید.", reply_markup=mk)
    else:
        safe_send(uid, "❌ کد نامعتبر یا استفاده شده.", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == "get_test")
def get_test(call):
    uid = call.from_user.id
    if not test_enabled():
        bot.answer_callback_query(call.id, "❌ سرور تست فعال نیست!", show_alert=True); return
    ts = get_test_server()
    if not ts:
        bot.answer_callback_query(call.id, "❌ سرور تست موجود نیست!", show_alert=True); return
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu"))
    safe_edit(uid, call.message.message_id,
        f"🆓 سرور تست رایگان\n\n📋 کانفیگ:\n{ts['config_text']}\n\n⚠️ موقت و برای تست.", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == "profile")
def profile(call):
    uid = call.from_user.id
    user = get_user(uid)
    purchases = get_purchases(uid) or []
    uname = f"@{user['username']}" if user and user['username'] != "ندارد" else "—"
    role = "👑 رئیس" if is_owner(uid) else ("🛡 ادمین" if is_admin(uid) else "👤 کاربر")
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("📂 کانفیگ‌های من", callback_data="my_configs"))
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu"))
    safe_edit(uid, call.message.message_id,
        f"👤 حساب کاربری\n\n🆔 {uid}\n👤 {uname}\n"
        f"💰 {fp(get_balance(uid))}\n📦 {len(purchases)} خرید\n"
        f"🏷 {role}\n📅 {user['created_at'] if user else '—'}", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == "my_configs")
def my_configs(call):
    uid = call.from_user.id
    purchases = get_purchases(uid) or []
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    if not purchases:
        mk.add(telebot.types.InlineKeyboardButton("🛒 خرید", callback_data="buy_menu"))
        mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu"))
        safe_edit(uid, call.message.message_id, "📂 کانفیگ‌های من\n\n❌ هنوز کانفیگی ندارید.", reply_markup=mk)
        return
    text = f"📂 کانفیگ‌های من ({len(purchases)} عدد)\n\n"
    for i, p in enumerate(purchases[:5], 1):
        text += f"{'─'*18}\n#{i} {p[1]}\n📅 انقضا: {p[4] or '—'}\n"
    for i, p in enumerate(purchases[:5], 1):
        mk.add(telebot.types.InlineKeyboardButton(f"🔑 #{i} — {p[1]}", callback_data=f"view_cfg_{p[0]}"))
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu"))
    safe_edit(uid, call.message.message_id, text, reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("view_cfg_"))
def view_cfg(call):
    uid = call.from_user.id
    pid = int(call.data[9:])
    r = db_exec("SELECT config_name,config_text,amount_paid,expire_date,created_at FROM purchases WHERE id=? AND user_id=?", (pid, uid), "one")
    if not r:
        bot.answer_callback_query(call.id, "❌ پیدا نشد!", show_alert=True); return
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="my_configs"))
    safe_edit(uid, call.message.message_id,
        f"🔑 {r[0]}\n📅 خرید: {r[4]}\n⏰ انقضا: {r[3]}\n💰 {fp(r[2])}\n\n📋 کانفیگ:\n{r[1]}", reply_markup=mk)

# ═══════════════════════════════════════════
#  خرید
# ═══════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data == "buy_menu")
def buy_menu(call):
    uid = call.from_user.id
    if not shop_is_open():
        mk = telebot.types.InlineKeyboardMarkup()
        mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu"))
        safe_edit(uid, call.message.message_id, "🔴 فروش فعلاً متوقف است.\nبه زودی برمی‌گردیم! 🙏", reply_markup=mk)
        return
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    mk.add(
        telebot.types.InlineKeyboardButton("🖥 سرور تک لوکیشن",    callback_data="single_server"),
        telebot.types.InlineKeyboardButton("🌍 سرور مولتی لوکیشن", callback_data="multi_server"),
        telebot.types.InlineKeyboardButton("🔙 بازگشت",            callback_data="main_menu"),
    )
    safe_edit(uid, call.message.message_id,
        f"🛒 خرید کانفیگ\n\n💰 موجودی: {fp(get_balance(uid))}\n\nنوع سرور:", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == "single_server")
def single_server(call):
    plans = get_plans("single")
    stock = get_all_stock()
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    for p in plans:
        s = stock.get(p['plan_key'], 0)
        mk.add(telebot.types.InlineKeyboardButton(
            f"{'✅' if s>0 else '❌'} {p['name']} — {fp(p['price'])} | موجودی: {s}",
            callback_data=f"cfg_{p['plan_key']}"))
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy_menu"))
    safe_edit(call.from_user.id, call.message.message_id,
        "🖥 سرور تک لوکیشن\n\nپلن را انتخاب کنید:", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == "multi_server")
def multi_server(call):
    plans = get_plans("multi")
    stock = get_all_stock()
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    for p in plans:
        s = stock.get(p['plan_key'], 0)
        mk.add(telebot.types.InlineKeyboardButton(
            f"{'✅' if s>0 else '❌'} {p['name']} — {fp(p['price'])} | موجودی: {s}",
            callback_data=f"cfg_{p['plan_key']}"))
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy_menu"))
    safe_edit(call.from_user.id, call.message.message_id,
        "🌍 سرور مولتی لوکیشن\n\nپلن را انتخاب کنید:", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("cfg_"))
def select_cfg(call):
    uid = call.from_user.id
    key = call.data[4:]
    p = get_plan(key)
    if not p:
        bot.answer_callback_query(call.id, "❌ پلن پیدا نشد!"); return
    stock = get_config_stock(key)
    text = (
        f"📦 مشخصات پلن\n{'═'*20}\n"
        f"🏷 {p['name']}\n💾 {p['gb']} گیگ | 📅 {p['days']} روز\n"
        f"💰 {fp(p['price'])}\n"
        f"📦 {'✅ موجود' if stock>0 else '❌ ناموجود'}\n{'═'*20}\n"
        f"👛 موجودی شما: {fp(get_balance(uid))}\n"
    )
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    if stock > 0:
        mk.add(
            telebot.types.InlineKeyboardButton("👛 پرداخت از کیف پول", callback_data=f"pay_w_{key}"),
            telebot.types.InlineKeyboardButton(
                "💳 کارت به کارت" + ("" if card_is_open() else " (غیرفعال)"),
                callback_data=f"pay_c_{key}"),
            telebot.types.InlineKeyboardButton("🎟 کد تخفیف دارم", callback_data=f"pay_d_{key}"),
        )
    else:
        text += "\n⚠️ این پلن موجود نیست."
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy_menu"))
    safe_edit(uid, call.message.message_id, text, reply_markup=mk)

# ── پرداخت کیف پول ──
@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_w_"))
def pay_wallet(call):
    uid = call.from_user.id
    key = call.data[6:]
    p = get_plan(key)
    if not p: return
    balance = get_balance(uid)
    if balance < p['price']:
        mk = telebot.types.InlineKeyboardMarkup()
        mk.add(telebot.types.InlineKeyboardButton("💰 شارژ کیف پول", callback_data="wallet_menu"))
        mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"cfg_{key}"))
        bot.answer_callback_query(call.id, "❌ موجودی کافی نیست!", show_alert=True)
        safe_edit(uid, call.message.message_id,
            f"❌ موجودی کافی نیست!\n💰 موجودی: {fp(balance)}\n"
            f"💸 قیمت: {fp(p['price'])}\n⚠️ کمبود: {fp(p['price']-balance)}", reply_markup=mk)
        return
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(
        telebot.types.InlineKeyboardButton("✅ تأیید خرید", callback_data=f"cw_{key}"),
        telebot.types.InlineKeyboardButton("❌ انصراف",    callback_data=f"cfg_{key}"),
    )
    safe_edit(uid, call.message.message_id,
        f"✅ تأیید خرید\n📦 {p['name']}\n💰 {fp(p['price'])}\n"
        f"👛 موجودی پس از خرید: {fp(balance-p['price'])}\n\nمطمئنید؟", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("cw_"))
def confirm_wallet(call):
    uid = call.from_user.id
    key = call.data[3:]
    p = get_plan(key)
    if not p: return
    balance = get_balance(uid)
    if balance < p['price']:
        bot.answer_callback_query(call.id, "❌ موجودی کافی نیست!", show_alert=True); return
    if get_config_stock(key) == 0:
        bot.answer_callback_query(call.id, "❌ این پلن تمام شد!", show_alert=True); return
    cfg_row = get_available_config(key)
    update_balance(uid, -p['price'])
    mark_config_used(cfg_row[0], uid)
    add_purchase(uid, p['name'], cfg_row[1], p['price'], p['days'])
    user = get_user(uid)
    safe_send(OWNER_ID,
        f"🛒 خرید جدید!\n👤 {user['first_name']} | @{user['username']}\n"
        f"🆔 {uid}\n📦 {p['name']}\n💰 {fp(p['price'])}\n💳 کیف پول ✅")
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("📂 کانفیگ‌های من", callback_data="my_configs"))
    mk.add(telebot.types.InlineKeyboardButton("🏠 منوی اصلی",     callback_data="main_menu"))
    safe_edit(uid, call.message.message_id,
        f"🎉 خرید موفق!\n📦 {p['name']}\n💰 {fp(p['price'])} کسر شد\n\n"
        f"📋 کانفیگ:\n{cfg_row[1]}\n\n"
        f"📅 انقضا: {(datetime.now()+timedelta(days=p['days'])).strftime('%Y-%m-%d')}",
        reply_markup=mk)

# ── پرداخت کارت به کارت ──
@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_c_"))
def pay_card(call):
    uid = call.from_user.id
    key = call.data[6:]
    p = get_plan(key)
    if not p: return
    if not card_is_open():
        mk = telebot.types.InlineKeyboardMarkup()
        mk.add(telebot.types.InlineKeyboardButton("👛 کیف پول", callback_data=f"pay_w_{key}"))
        mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"cfg_{key}"))
        safe_edit(uid, call.message.message_id, "🔴 کارت به کارت غیرفعال است.", reply_markup=mk)
        return
    set_state(uid, {"action": "card_receipt", "key": key})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"cfg_{key}"))
    safe_edit(uid, call.message.message_id,
        f"💳 پرداخت کارت به کارت\n📦 {p['name']}\n💰 {fp(p['price'])}\n\n"
        f"{'─'*22}\n🔹 شماره کارت:\n{CARD_NUMBER}\n"
        f"👤 به نام: {CARD_OWNER}\n{'─'*22}\n\n✅ رسید را ارسال کنید:", reply_markup=mk)

@bot.message_handler(content_types=["photo"],
    func=lambda m: get_state(m.from_user.id).get("action") == "card_receipt")
def card_receipt_handler(message):
    uid = message.from_user.id
    state = get_state(uid)
    key = state.get("key")
    p = get_plan(key)
    if not p: return
    file_id = message.photo[-1].file_id
    tid = add_transaction(uid, p['price'], "card_buy", "pending", file_id)
    user = get_user(uid)
    clear_state(uid)
    mk2 = telebot.types.InlineKeyboardMarkup()
    mk2.add(telebot.types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu"))

    if auto_approve_enabled():
        if get_config_stock(key) == 0:
            safe_send(uid, f"❌ موجودی پلن تمام شد.\n🔖 #{tid}", reply_markup=mk2); return
        cfg_row = get_available_config(key)
        mark_config_used(cfg_row[0], uid)
        add_purchase(uid, p['name'], cfg_row[1], p['price'], p['days'])
        update_transaction(tid, "auto_approved")
        safe_send(uid,
            f"🎉 خرید تأیید شد! (خودکار)\n📦 {p['name']}\n🔖 #{tid}\n\n"
            f"📋 کانفیگ:\n{cfg_row[1]}\n\n"
            f"📅 انقضا: {(datetime.now()+timedelta(days=p['days'])).strftime('%Y-%m-%d')}",
            reply_markup=mk2)
        safe_send(OWNER_ID,
            f"🤖 تأیید خودکار!\n👤 {user['first_name']} | {uid}\n📦 {p['name']}\n💰 {fp(p['price'])}\n🔖 #{tid}")
    else:
        adm_mk = telebot.types.InlineKeyboardMarkup(row_width=2)
        adm_mk.add(
            telebot.types.InlineKeyboardButton("✅ تأیید", callback_data=f"acard_{tid}_{uid}_{key}"),
            telebot.types.InlineKeyboardButton("❌ رد",    callback_data=f"rcard_{tid}_{uid}"),
        )
        caption = (f"🧾 رسید خرید کانفیگ\n👤 {user['first_name']} | @{user['username']}\n"
                   f"🆔 {uid}\n📦 {p['name']}\n💰 {fp(p['price'])}\n🔖 #{tid}")
        for adm in (get_admins() or []):
            try: bot.send_photo(adm['user_id'], file_id, caption=caption, reply_markup=adm_mk)
            except Exception: pass
        try: bot.send_photo(OWNER_ID, file_id, caption=caption, reply_markup=adm_mk)
        except Exception: pass
        safe_send(uid,
            f"✅ رسید دریافت شد!\n📦 {p['name']}\n🔖 #{tid}\n⏳ پس از تأیید کانفیگ ارسال می‌شود.",
            reply_markup=mk2)

@bot.callback_query_handler(func=lambda c: c.data.startswith("acard_"))
def approve_card(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ دسترسی ندارید!"); return
    try:
        parts = call.data.split("_")
        tid, uid, key = int(parts[1]), int(parts[2]), parts[3]
        p = get_plan(key)
        if not p:
            bot.answer_callback_query(call.id, "❌ پلن پیدا نشد!", show_alert=True); return
        if get_config_stock(key) == 0:
            bot.answer_callback_query(call.id, "❌ موجودی تمام!", show_alert=True); return
        cfg_row = get_available_config(key)
        mark_config_used(cfg_row[0], uid)
        add_purchase(uid, p['name'], cfg_row[1], p['price'], p['days'])
        update_transaction(tid, "approved")
        safe_send(uid,
            f"🎉 خرید تأیید شد!\n📦 {p['name']}\n🔖 #{tid}\n\n"
            f"📋 کانفیگ:\n{cfg_row[1]}\n\n"
            f"📅 انقضا: {(datetime.now()+timedelta(days=p['days'])).strftime('%Y-%m-%d')}\nممنون! 🙏")
        bot.edit_message_caption(caption=f"✅ تأیید | {p['name']} | {uid}",
            chat_id=call.from_user.id, message_id=call.message.message_id)
        bot.answer_callback_query(call.id, "✅ ارسال شد")
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ {e}", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rcard_"))
def reject_card(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ دسترسی ندارید!"); return
    try:
        parts = call.data.split("_")
        tid, uid = int(parts[1]), int(parts[2])
        update_transaction(tid, "rejected")
        safe_send(uid, f"❌ رسید تأیید نشد.\n🔖 #{tid}\nبرای پیگیری تیکت بزنید.")
        bot.edit_message_caption(caption=f"❌ رد | {uid}",
            chat_id=call.from_user.id, message_id=call.message.message_id)
        bot.answer_callback_query(call.id, "❌ رد شد")
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ {e}", show_alert=True)

# ── کد تخفیف هنگام خرید ──
@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_d_"))
def pay_discount(call):
    uid = call.from_user.id
    key = call.data[6:]
    p = get_plan(key)
    if not p: return
    set_state(uid, {"action": "enter_discount", "key": key})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"cfg_{key}"))
    safe_edit(uid, call.message.message_id,
        f"🎟 کد تخفیف\n📦 {p['name']}\n💰 قیمت اصلی: {fp(p['price'])}\n\nکد تخفیف را وارد کنید:",
        reply_markup=mk)

@bot.message_handler(func=lambda m: get_state(m.from_user.id).get("action") == "enter_discount")
def apply_discount(message):
    uid = message.from_user.id
    state = get_state(uid)
    key = state.get("key")
    p = get_plan(key)
    if not p: return
    code = message.text.strip().upper()
    percent = check_discount(code)
    if not percent:
        mk = telebot.types.InlineKeyboardMarkup()
        mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"cfg_{key}"))
        safe_send(uid, "❌ کد تخفیف نامعتبر یا استفاده شده.", reply_markup=mk)
        return
    final = int(p['price'] * (1 - percent/100))
    saved = p['price'] - final
    set_state(uid, {"action": "discount_confirm", "key": key, "code": code, "final": final})
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    mk.add(
        telebot.types.InlineKeyboardButton("👛 پرداخت از کیف پول", callback_data=f"dw_{key}_{code}_{final}"),
        telebot.types.InlineKeyboardButton("💳 کارت به کارت",      callback_data=f"dc_{key}_{code}_{final}"),
        telebot.types.InlineKeyboardButton("🔙 بازگشت",            callback_data=f"cfg_{key}"),
    )
    safe_send(uid,
        f"✅ کد اعمال شد!\n📦 {p['name']}\n"
        f"💰 قیمت اصلی: {fp(p['price'])}\n"
        f"🎟 تخفیف: {percent}% ({fp(saved)} صرفه‌جویی)\n"
        f"✅ قیمت نهایی: {fp(final)}\n👛 موجودی: {fp(get_balance(uid))}\n\nروش پرداخت:",
        reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("dw_"))
def discount_wallet(call):
    uid = call.from_user.id
    parts = call.data.split("_")
    key, code, final = parts[1], parts[2], int(parts[3])
    p = get_plan(key)
    if not p: return
    if get_balance(uid) < final:
        bot.answer_callback_query(call.id, "❌ موجودی کافی نیست!", show_alert=True); return
    if get_config_stock(key) == 0:
        bot.answer_callback_query(call.id, "❌ پلن تمام شد!", show_alert=True); return
    cfg_row = get_available_config(key)
    use_discount(code)
    update_balance(uid, -final)
    mark_config_used(cfg_row[0], uid)
    add_purchase(uid, p['name'], cfg_row[1], final, p['days'])
    clear_state(uid)
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("📂 کانفیگ‌های من", callback_data="my_configs"))
    mk.add(telebot.types.InlineKeyboardButton("🏠 منوی اصلی",     callback_data="main_menu"))
    safe_edit(uid, call.message.message_id,
        f"🎉 خرید موفق با تخفیف!\n📦 {p['name']}\n💰 {fp(final)} کسر شد\n\n📋 کانفیگ:\n{cfg_row[1]}",
        reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("dc_"))
def discount_card(call):
    uid = call.from_user.id
    parts = call.data.split("_")
    key, code, final = parts[1], parts[2], int(parts[3])
    p = get_plan(key)
    if not p: return
    if not card_is_open():
        bot.answer_callback_query(call.id, "❌ کارت به کارت غیرفعال!", show_alert=True); return
    set_state(uid, {"action": "discount_card_receipt", "key": key, "code": code, "final": final})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"cfg_{key}"))
    safe_edit(uid, call.message.message_id,
        f"💳 پرداخت کارت به کارت\n📦 {p['name']}\n💰 مبلغ نهایی: {fp(final)}\n\n"
        f"🔹 {CARD_NUMBER}\n👤 {CARD_OWNER}\n\n✅ رسید ارسال کنید:", reply_markup=mk)

@bot.message_handler(content_types=["photo"],
    func=lambda m: get_state(m.from_user.id).get("action") == "discount_card_receipt")
def discount_card_receipt(message):
    uid = message.from_user.id
    state = get_state(uid)
    key, code, final = state.get("key"), state.get("code"), state.get("final")
    p = get_plan(key)
    if not p: return
    file_id = message.photo[-1].file_id
    tid = add_transaction(uid, final, "discount_card", "pending", file_id)
    user = get_user(uid)
    clear_state(uid)
    mk2 = telebot.types.InlineKeyboardMarkup()
    mk2.add(telebot.types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu"))

    if auto_approve_enabled():
        if get_config_stock(key) == 0:
            safe_send(uid, f"❌ موجودی پلن تمام شد.\n🔖 #{tid}", reply_markup=mk2); return
        cfg_row = get_available_config(key)
        use_discount(code)
        mark_config_used(cfg_row[0], uid)
        add_purchase(uid, p['name'], cfg_row[1], final, p['days'])
        update_transaction(tid, "auto_approved")
        safe_send(uid,
            f"🎉 خرید تأیید شد! (خودکار)\n📦 {p['name']}\n\n📋 کانفیگ:\n{cfg_row[1]}",
            reply_markup=mk2)
    else:
        adm_mk = telebot.types.InlineKeyboardMarkup(row_width=2)
        adm_mk.add(
            telebot.types.InlineKeyboardButton("✅ تأیید", callback_data=f"adcard_{tid}_{uid}_{key}_{code}_{final}"),
            telebot.types.InlineKeyboardButton("❌ رد",    callback_data=f"rcard_{tid}_{uid}"),
        )
        caption = (f"🧾 رسید خرید با تخفیف\n👤 {user['first_name']} | 🆔 {uid}\n"
                   f"📦 {p['name']}\n🎟 {code}\n💰 {fp(final)}\n🔖 #{tid}")
        for adm in (get_admins() or []):
            try: bot.send_photo(adm['user_id'], file_id, caption=caption, reply_markup=adm_mk)
            except Exception: pass
        try: bot.send_photo(OWNER_ID, file_id, caption=caption, reply_markup=adm_mk)
        except Exception: pass
        safe_send(uid, f"✅ رسید دریافت شد!\n🔖 #{tid}\n⏳ پس از تأیید کانفیگ ارسال می‌شود.", reply_markup=mk2)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adcard_"))
def approve_dcard(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ دسترسی ندارید!"); return
    try:
        parts = call.data.split("_")
        tid, uid, key, code, final = int(parts[1]), int(parts[2]), parts[3], parts[4], int(parts[5])
        p = get_plan(key)
        if get_config_stock(key) == 0:
            bot.answer_callback_query(call.id, "❌ موجودی تمام!", show_alert=True); return
        cfg_row = get_available_config(key)
        use_discount(code)
        mark_config_used(cfg_row[0], uid)
        add_purchase(uid, p['name'], cfg_row[1], final, p['days'])
        update_transaction(tid, "approved")
        safe_send(uid, f"🎉 خرید تأیید شد!\n📦 {p['name']}\n📋 کانفیگ:\n{cfg_row[1]}\nممنون! 🙏")
        bot.edit_message_caption(caption=f"✅ تأیید | {p['name']} | {uid}",
            chat_id=call.from_user.id, message_id=call.message.message_id)
        bot.answer_callback_query(call.id, "✅ ارسال شد")
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ {e}", show_alert=True)

# ═══════════════════════════════════════════
#  کیف پول
# ═══════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data == "wallet_menu")
def wallet_menu(call):
    uid = call.from_user.id
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    if card_is_open():
        mk.add(telebot.types.InlineKeyboardButton("➕ شارژ کیف پول", callback_data="charge_wallet"))
    else:
        mk.add(telebot.types.InlineKeyboardButton("🔴 شارژ (غیرفعال)", callback_data="charge_disabled"))
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu"))
    safe_edit(uid, call.message.message_id,
        f"💰 کیف پول\n\n💵 موجودی: {fp(get_balance(uid))}", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == "charge_disabled")
def charge_disabled(call):
    bot.answer_callback_query(call.id, "🔴 شارژ فعلاً غیرفعال است.", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data == "charge_wallet")
def charge_wallet(call):
    uid = call.from_user.id
    if not card_is_open():
        bot.answer_callback_query(call.id, "🔴 غیرفعال است.", show_alert=True); return
    set_state(uid, {"action": "charge_amount"})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="wallet_menu"))
    safe_edit(uid, call.message.message_id,
        "➕ شارژ کیف پول\n\n💰 مبلغ را به تومان وارد کنید:\n(حداقل: ۵۰٬۰۰۰)\n\nمثال: 100000",
        reply_markup=mk)

@bot.message_handler(func=lambda m: get_state(m.from_user.id).get("action") == "charge_amount")
def charge_amount_handler(message):
    uid = message.from_user.id
    try:
        amount = int(message.text.replace(",","").replace("،","").strip())
        if amount < 50000:
            safe_send(uid, "❌ حداقل ۵۰٬۰۰۰ تومان."); return
        if amount > 100000000:
            safe_send(uid, "❌ حداکثر ۱۰۰٬۰۰۰٬۰۰۰ تومان."); return
        set_state(uid, {"action": "charge_receipt", "amount": amount})
        mk = telebot.types.InlineKeyboardMarkup()
        mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="wallet_menu"))
        safe_send(uid,
            f"✅ مبلغ: {fp(amount)}\n\n💳 واریز به:\n🔹 {CARD_NUMBER}\n👤 {CARD_OWNER}\n\n📸 رسید را ارسال کنید:",
            reply_markup=mk)
    except ValueError:
        safe_send(uid, "❌ فقط عدد وارد کنید. مثال: 100000")

@bot.message_handler(content_types=["photo"],
    func=lambda m: get_state(m.from_user.id).get("action") == "charge_receipt")
def charge_receipt_handler(message):
    uid = message.from_user.id
    state = get_state(uid)
    amount = state.get("amount", 0)
    file_id = message.photo[-1].file_id
    tid = add_transaction(uid, amount, "charge", "pending", file_id)
    user = get_user(uid)
    clear_state(uid)
    mk2 = telebot.types.InlineKeyboardMarkup()
    mk2.add(telebot.types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu"))

    if auto_approve_enabled():
        update_transaction(tid, "auto_approved")
        update_balance(uid, amount)
        safe_send(uid,
            f"✅ کیف پول شارژ شد! (خودکار)\n💚 {fp(amount)} اضافه شد\n"
            f"💰 موجودی: {fp(get_balance(uid))}\n🔖 #{tid}", reply_markup=mk2)
        safe_send(OWNER_ID,
            f"🤖 شارژ خودکار!\n👤 {user['first_name']} | {uid}\n💰 {fp(amount)}\n🔖 #{tid}")
    else:
        adm_mk = telebot.types.InlineKeyboardMarkup(row_width=2)
        adm_mk.add(
            telebot.types.InlineKeyboardButton("✅ تأیید", callback_data=f"apay_{tid}_{uid}_{amount}"),
            telebot.types.InlineKeyboardButton("❌ رد",    callback_data=f"rpay_{tid}_{uid}"),
        )
        caption = (f"🧾 شارژ کیف پول\n👤 {user['first_name']} | @{user['username']}\n"
                   f"🆔 {uid}\n💰 {fp(amount)}\n🔖 #{tid}")
        for adm in (get_admins() or []):
            try: bot.send_photo(adm['user_id'], file_id, caption=caption, reply_markup=adm_mk)
            except Exception: pass
        try: bot.send_photo(OWNER_ID, file_id, caption=caption, reply_markup=adm_mk)
        except Exception: pass
        safe_send(uid,
            f"✅ رسید دریافت شد!\n💰 {fp(amount)}\n🔖 #{tid}\n⏳ پس از تأیید موجودی اضافه می‌شود.",
            reply_markup=mk2)

@bot.callback_query_handler(func=lambda c: c.data.startswith("apay_"))
def approve_pay(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ دسترسی ندارید!"); return
    try:
        parts = call.data.split("_")
        tid, uid, amount = int(parts[1]), int(parts[2]), int(parts[3])
        update_transaction(tid, "approved")
        update_balance(uid, amount)
        safe_send(uid,
            f"✅ کیف پول شارژ شد!\n💚 {fp(amount)} اضافه شد\n"
            f"💰 موجودی کل: {fp(get_balance(uid))}\n🔖 #{tid}")
        bot.edit_message_caption(caption=f"✅ تأیید | {fp(amount)} | {uid}",
            chat_id=call.from_user.id, message_id=call.message.message_id)
        bot.answer_callback_query(call.id, "✅ تأیید شد")
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ {e}", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rpay_"))
def reject_pay(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ دسترسی ندارید!"); return
    try:
        parts = call.data.split("_")
        tid, uid = int(parts[1]), int(parts[2])
        update_transaction(tid, "rejected")
        safe_send(uid, f"❌ رسید تأیید نشد.\n🔖 #{tid}\nبرای پیگیری تیکت بزنید.")
        bot.edit_message_caption(caption=f"❌ رد | {uid}",
            chat_id=call.from_user.id, message_id=call.message.message_id)
        bot.answer_callback_query(call.id, "❌ رد شد")
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ {e}", show_alert=True)

# ═══════════════════════════════════════════
#  تیکت
# ═══════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data == "ticket_menu")
def ticket_menu(call):
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    mk.add(
        telebot.types.InlineKeyboardButton("📝 ارسال تیکت جدید", callback_data="new_ticket"),
        telebot.types.InlineKeyboardButton("🔙 بازگشت",          callback_data="main_menu"),
    )
    safe_edit(call.from_user.id, call.message.message_id,
        "🎫 تیکت پشتیبانی\n\n📞 پشتیبانی آماده کمک است!\nتیکت بزنید و پاسخ می‌گیرید 💬", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == "new_ticket")
def new_ticket(call):
    uid = call.from_user.id
    set_state(uid, {"action": "ticket_subject"})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="ticket_menu"))
    safe_edit(uid, call.message.message_id, "📝 تیکت جدید\n\nموضوع تیکت را بنویسید:", reply_markup=mk)

@bot.message_handler(func=lambda m: get_state(m.from_user.id).get("action") == "ticket_subject")
def ticket_subject(message):
    uid = message.from_user.id
    set_state(uid, {"action": "ticket_message", "subject": message.text})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="ticket_menu"))
    safe_send(uid, f"✅ موضوع: {message.text}\n\nپیام خود را بنویسید:", reply_markup=mk)

@bot.message_handler(func=lambda m: get_state(m.from_user.id).get("action") == "ticket_message")
def ticket_message(message):
    uid = message.from_user.id
    subject = get_state(uid).get("subject", "")
    tid = add_ticket(uid, subject, message.text)
    user = get_user(uid)
    adm_mk = telebot.types.InlineKeyboardMarkup(row_width=2)
    adm_mk.add(
        telebot.types.InlineKeyboardButton("✅ پاسخ", callback_data=f"rt_{uid}_{tid}"),
        telebot.types.InlineKeyboardButton("🔒 بستن", callback_data=f"ct_{tid}_{uid}"),
    )
    ticket_text = (f"🎫 تیکت #{tid}\n👤 {user['first_name']} | @{user['username']}\n"
                   f"🆔 {uid}\n📌 {subject}\n💬 {message.text}")
    for adm in (get_admins() or []):
        safe_send(adm['user_id'], ticket_text, reply_markup=adm_mk)
    safe_send(OWNER_ID, ticket_text, reply_markup=adm_mk)
    clear_state(uid)
    mk2 = telebot.types.InlineKeyboardMarkup()
    mk2.add(telebot.types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu"))
    safe_send(uid, f"✅ تیکت #{tid} ثبت شد!\n⏳ پشتیبانی به زودی پاسخ می‌دهد.", reply_markup=mk2)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rt_") and is_admin(c.from_user.id))
def reply_ticket(call):
    parts = call.data.split("_")
    uid, tid = int(parts[1]), int(parts[2])
    set_state(call.from_user.id, {"action": "replying_ticket", "target": uid, "tid": tid})
    safe_send(call.from_user.id, f"✏️ پاسخ به تیکت #{tid} — کاربر {uid}:\n\nپیام را بنویسید:")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("ct_") and is_admin(c.from_user.id))
def close_ticket(call):
    parts = call.data.split("_")
    tid, uid = int(parts[1]), int(parts[2])
    db_exec("UPDATE tickets SET status='closed' WHERE id=?", (tid,))
    safe_send(uid, f"🔒 تیکت #{tid} بسته شد.\nاگر مشکل دیگری دارید تیکت جدید بزنید.")
    bot.answer_callback_query(call.id, "✅ تیکت بسته شد")

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "replying_ticket" and is_admin(m.from_user.id))
def send_reply(message):
    adm_uid = message.from_user.id
    state = get_state(adm_uid)
    uid, tid = state.get("target"), state.get("tid")
    safe_send(uid, f"📩 پاسخ پشتیبانی — تیکت #{tid}:\n\n{message.text}")
    clear_state(adm_uid)
    safe_send(adm_uid, f"✅ پاسخ به کاربر {uid} ارسال شد.")

# ═══════════════════════════════════════════
#  پنل ادمین — دکمه‌های toggle
# ═══════════════════════════════════════════
@bot.message_handler(commands=["admin"])
def admin_cmd(message):
    uid = message.from_user.id
    if not is_admin(uid): return
    if not is_panel_logged_in(uid):
        set_state(uid, {"action": "panel_login"})
        safe_send(uid, "🔐 رمز عبور پنل را وارد کنید:")
    else:
        safe_send(uid, "👑 پنل ادمین:", reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda c: c.data == "adm_logout" and is_admin(c.from_user.id))
def adm_logout(call):
    set_panel_login(call.from_user.id, False)
    bot.answer_callback_query(call.id, "✅ از پنل خارج شدید", show_alert=True)
    try: bot.delete_message(call.from_user.id, call.message.message_id)
    except Exception: pass

@bot.callback_query_handler(func=lambda c: c.data == "adm_back" and is_admin(c.from_user.id))
def adm_back(call):
    safe_edit(call.from_user.id, call.message.message_id, "👑 پنل ادمین:", reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda c: c.data == "adm_toggle_shop" and is_admin(c.from_user.id))
def toggle_shop(call):
    set_setting("shop_open", "0" if shop_is_open() else "1")
    bot.answer_callback_query(call.id, f"✅ فروشگاه {'بسته' if not shop_is_open() else 'باز'} شد", show_alert=True)
    safe_edit(call.from_user.id, call.message.message_id, "👑 پنل ادمین:", reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda c: c.data == "adm_toggle_card" and is_admin(c.from_user.id))
def toggle_card(call):
    set_setting("card_payment_open", "0" if card_is_open() else "1")
    bot.answer_callback_query(call.id, "✅ وضعیت کارت تغییر کرد", show_alert=True)
    safe_edit(call.from_user.id, call.message.message_id, "👑 پنل ادمین:", reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda c: c.data == "adm_toggle_test" and is_admin(c.from_user.id))
def toggle_test(call):
    set_setting("test_server_enabled", "0" if test_enabled() else "1")
    bot.answer_callback_query(call.id, "✅ وضعیت سرور تست تغییر کرد", show_alert=True)
    safe_edit(call.from_user.id, call.message.message_id, "👑 پنل ادمین:", reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda c: c.data == "adm_toggle_auto" and is_admin(c.from_user.id))
def toggle_auto(call):
    set_setting("auto_approve", "0" if auto_approve_enabled() else "1")
    bot.answer_callback_query(call.id, "✅ وضعیت تأیید خودکار تغییر کرد", show_alert=True)
    safe_edit(call.from_user.id, call.message.message_id, "👑 پنل ادمین:", reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda c: c.data == "adm_toggle_maintenance" and is_admin(c.from_user.id))
def toggle_maintenance(call):
    set_setting("maintenance_mode", "0" if maintenance_mode() else "1")
    bot.answer_callback_query(call.id, "✅ حالت تعمیر تغییر کرد", show_alert=True)
    safe_edit(call.from_user.id, call.message.message_id, "👑 پنل ادمین:", reply_markup=admin_menu())

# ═══════════════════════════════════════════
#  مدیریت ادمین‌ها (فقط رئیس)
# ═══════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data == "adm_manage_admins" and is_owner(c.from_user.id))
def adm_manage_admins(call):
    admins_list = get_admins() or []
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    for adm in admins_list:
        mk.add(telebot.types.InlineKeyboardButton(
            f"🛡 {adm['first_name']} | @{adm['username']} | {adm['user_id']}",
            callback_data=f"adm_admin_detail_{adm['user_id']}"))
    mk.add(
        telebot.types.InlineKeyboardButton("➕ اضافه کردن ادمین", callback_data="adm_add_admin"),
        telebot.types.InlineKeyboardButton("🔙 بازگشت",           callback_data="adm_back"),
    )
    safe_edit(OWNER_ID, call.message.message_id,
        f"👑 مدیریت ادمین‌ها\n\nتعداد: {len(admins_list)}", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_admin_detail_") and is_owner(c.from_user.id))
def adm_admin_detail(call):
    adm_uid = int(call.data[17:])
    adm = db_exec("SELECT * FROM admins WHERE user_id=?", (adm_uid,), "one")
    if not adm:
        bot.answer_callback_query(call.id, "❌ پیدا نشد!"); return
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    mk.add(
        telebot.types.InlineKeyboardButton("🔑 تغییر رمز عبور", callback_data=f"adm_change_pass_{adm_uid}"),
        telebot.types.InlineKeyboardButton("🗑 حذف ادمین",       callback_data=f"adm_remove_admin_{adm_uid}"),
        telebot.types.InlineKeyboardButton("🔙 بازگشت",          callback_data="adm_manage_admins"),
    )
    safe_edit(OWNER_ID, call.message.message_id,
        f"🛡 {adm['first_name']} | @{adm['username']}\n🆔 {adm_uid}\n📅 {adm['created_at']}",
        reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_remove_admin_") and is_owner(c.from_user.id))
def adm_remove_admin(call):
    adm_uid = int(call.data[17:])
    remove_admin(adm_uid)
    set_panel_login(adm_uid, False)
    safe_send(adm_uid, "⚠️ دسترسی ادمین شما توسط رئیس حذف شد.")
    bot.answer_callback_query(call.id, "✅ ادمین حذف شد", show_alert=True)
    safe_edit(OWNER_ID, call.message.message_id, "👑 پنل ادمین:", reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_change_pass_") and is_owner(c.from_user.id))
def adm_change_pass(call):
    adm_uid = int(call.data[16:])
    set_state(OWNER_ID, {"action": "changing_admin_pass", "tuid": adm_uid})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_manage_admins"))
    safe_edit(OWNER_ID, call.message.message_id, f"🔑 رمز جدید برای ادمین {adm_uid}:", reply_markup=mk)

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "changing_admin_pass" and is_owner(m.from_user.id))
def change_admin_pass(message):
    state = get_state(OWNER_ID)
    adm_uid = state.get("tuid")
    try: bot.delete_message(OWNER_ID, message.message_id)
    except Exception: pass
    ph = hashlib.sha256(message.text.strip().encode()).hexdigest()
    db_exec("UPDATE admins SET password_hash=? WHERE user_id=?", (ph, adm_uid))
    set_panel_login(adm_uid, False)
    clear_state(OWNER_ID)
    safe_send(OWNER_ID, f"✅ رمز ادمین {adm_uid} تغییر کرد.")
    safe_send(adm_uid, "🔑 رمز عبور پنل شما تغییر کرد. لطفاً دوباره وارد شوید.")

@bot.callback_query_handler(func=lambda c: c.data == "adm_add_admin" and is_owner(c.from_user.id))
def adm_add_admin(call):
    set_state(OWNER_ID, {"action": "adding_admin_uid"})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_manage_admins"))
    safe_edit(OWNER_ID, call.message.message_id, "➕ آیدی عددی کاربر جدید را وارد کنید:", reply_markup=mk)

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "adding_admin_uid" and is_owner(m.from_user.id))
def adding_admin_uid(message):
    try:
        adm_uid = int(message.text.strip())
        user = get_user(adm_uid)
        if not user:
            safe_send(OWNER_ID, "❌ این کاربر ثبت نشده. اول باید /start بزند."); return
        set_state(OWNER_ID, {"action": "adding_admin_pass", "tuid": adm_uid,
                              "username": user['username'], "first_name": user['first_name']})
        safe_send(OWNER_ID, f"✅ کاربر: {user['first_name']} | @{user['username']}\n\nرمز عبور تعیین کنید:")
    except ValueError:
        safe_send(OWNER_ID, "❌ آیدی معتبر وارد کنید.")

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "adding_admin_pass" and is_owner(m.from_user.id))
def adding_admin_pass(message):
    state = get_state(OWNER_ID)
    adm_uid = state.get("tuid")
    try: bot.delete_message(OWNER_ID, message.message_id)
    except Exception: pass
    add_admin(adm_uid, state.get("username"), state.get("first_name"), message.text.strip(), "all", OWNER_ID)
    clear_state(OWNER_ID)
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_manage_admins"))
    safe_send(OWNER_ID, f"✅ ادمین {adm_uid} اضافه شد!", reply_markup=mk)
    safe_send(adm_uid,
        "🎉 شما به عنوان ادمین اضافه شدید!\n\nبرای ورود به پنل روی 👑 پنل ادمین بزنید.",
        reply_markup=admin_reply_keyboard())

# ═══════════════════════════════════════════
#  سرور تست (ادمین)
# ═══════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data == "adm_test" and is_admin(c.from_user.id))
def adm_test(call):
    ts = get_test_server()
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    mk.add(
        telebot.types.InlineKeyboardButton("➕ تنظیم کانفیگ تست", callback_data="adm_set_test"),
        telebot.types.InlineKeyboardButton("🗑 حذف کانفیگ تست",   callback_data="adm_del_test"),
        telebot.types.InlineKeyboardButton("🔙 بازگشت",           callback_data="adm_back"),
    )
    text = f"🆓 سرور تست\n\nوضعیت: {'🟢 فعال' if test_enabled() else '🔴 غیرفعال'}\n\n"
    text += f"کانفیگ:\n{ts['config_text']}" if ts else "❌ کانفیگ تنظیم نشده."
    safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == "adm_set_test" and is_admin(c.from_user.id))
def adm_set_test(call):
    set_state(call.from_user.id, {"action": "setting_test_server"})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_test"))
    safe_edit(call.from_user.id, call.message.message_id, "🆓 متن کانفیگ تست را وارد کنید:", reply_markup=mk)

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "setting_test_server" and is_admin(m.from_user.id))
def save_test_server_handler(message):
    set_test_server(message.text.strip())
    clear_state(message.from_user.id)
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="adm_back"))
    safe_send(message.from_user.id, "✅ کانفیگ تست تنظیم شد!", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == "adm_del_test" and is_admin(c.from_user.id))
def del_test(call):
    delete_test_server()
    bot.answer_callback_query(call.id, "✅ کانفیگ تست حذف شد", show_alert=True)
    safe_edit(call.from_user.id, call.message.message_id, "👑 پنل ادمین:", reply_markup=admin_menu())

# ═══════════════════════════════════════════
#  مدیریت کدهای تخفیف (ادمین)
# ═══════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data == "adm_discount_mgr" and is_admin(c.from_user.id))
def adm_discount_mgr(call):
    discounts = get_all_discounts() or []
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    for d in discounts[:10]:
        remaining = d[3] - d[2]
        mk.add(telebot.types.InlineKeyboardButton(
            f"🎟 {d[0]} — {d[1]}% — مانده: {remaining}/{d[3]}",
            callback_data=f"adm_disc_det_{d[0]}"))
    mk.add(
        telebot.types.InlineKeyboardButton("➕ کد خودکار",  callback_data="adm_discount_auto"),
        telebot.types.InlineKeyboardButton("✏️ کد دستی",   callback_data="adm_discount_manual"),
        telebot.types.InlineKeyboardButton("🔙 بازگشت",    callback_data="adm_back"),
    )
    safe_edit(call.from_user.id, call.message.message_id,
        f"🎟 مدیریت کدهای تخفیف\n\nتعداد: {len(discounts)}", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_disc_det_") and is_admin(c.from_user.id))
def adm_disc_det(call):
    code = call.data[13:]
    d = db_exec("SELECT * FROM discount_codes WHERE code=?", (code,), "one")
    if not d:
        bot.answer_callback_query(call.id, "❌ پیدا نشد!"); return
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(
        telebot.types.InlineKeyboardButton("🗑 حذف این کد", callback_data=f"adm_del_disc_{code}"),
        telebot.types.InlineKeyboardButton("🔙 بازگشت",    callback_data="adm_discount_mgr"),
    )
    safe_edit(call.from_user.id, call.message.message_id,
        f"🎟 کد: {d['code']}\n💯 تخفیف: {d['percent']}%\n"
        f"🔢 استفاده: {d['used']}/{d['max_use']}\n✅ مانده: {d['max_use']-d['used']}",
        reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_del_disc_") and is_admin(c.from_user.id))
def adm_del_disc(call):
    code = call.data[13:]
    delete_discount(code)
    bot.answer_callback_query(call.id, f"✅ کد {code} حذف شد", show_alert=True)
    safe_edit(call.from_user.id, call.message.message_id, "👑 پنل ادمین:", reply_markup=admin_menu())

# کد خودکار
@bot.callback_query_handler(func=lambda c: c.data == "adm_discount_auto" and is_admin(c.from_user.id))
def adm_discount_auto(call):
    set_state(call.from_user.id, {"action": "discount_percent"})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_discount_mgr"))
    safe_edit(call.from_user.id, call.message.message_id,
        "🎟 کد تخفیف خودکار\n\nدرصد تخفیف (۱-۱۰۰):", reply_markup=mk)

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "discount_percent" and is_admin(m.from_user.id))
def discount_percent(message):
    uid = message.from_user.id
    try:
        p = int(message.text.strip())
        if not 1 <= p <= 100:
            safe_send(uid, "❌ بین ۱ تا ۱۰۰."); return
        set_state(uid, {"action": "discount_maxuse", "percent": p})
        safe_send(uid, f"✅ {p}%\n\nحداکثر تعداد استفاده:")
    except ValueError:
        safe_send(uid, "❌ عدد معتبر.")

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "discount_maxuse" and is_admin(m.from_user.id))
def discount_maxuse(message):
    uid = message.from_user.id
    state = get_state(uid)
    try:
        max_use = int(message.text.strip())
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        add_discount(code, state.get("percent"), max_use)
        clear_state(uid)
        mk = telebot.types.InlineKeyboardMarkup()
        mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_discount_mgr"))
        safe_send(uid,
            f"✅ کد تخفیف ساخته شد!\n\n🎟 کد: {code}\n💯 {state.get('percent')}%\n🔢 حداکثر: {max_use}",
            reply_markup=mk)
    except ValueError:
        safe_send(uid, "❌ عدد معتبر.")

# کد دستی
@bot.callback_query_handler(func=lambda c: c.data == "adm_discount_manual" and is_admin(c.from_user.id))
def adm_discount_manual(call):
    set_state(call.from_user.id, {"action": "discount_manual_code"})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_discount_mgr"))
    safe_edit(call.from_user.id, call.message.message_id,
        "✏️ کد تخفیف دستی\n\nمتن کد را وارد کنید:\n(مثال: SUMMER20)", reply_markup=mk)

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "discount_manual_code" and is_admin(m.from_user.id))
def discount_manual_code(message):
    uid = message.from_user.id
    code = message.text.strip().upper()
    if not code.replace("_","").isalnum():
        safe_send(uid, "❌ فقط حروف انگلیسی و عدد."); return
    set_state(uid, {"action": "discount_manual_percent", "code": code})
    safe_send(uid, f"✅ کد: {code}\n\nدرصد تخفیف (۱-۱۰۰):")

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "discount_manual_percent" and is_admin(m.from_user.id))
def discount_manual_percent(message):
    uid = message.from_user.id
    try:
        p = int(message.text.strip())
        if not 1 <= p <= 100:
            safe_send(uid, "❌ بین ۱ تا ۱۰۰."); return
        state = get_state(uid)
        set_state(uid, {**state, "action": "discount_manual_maxuse", "percent": p})
        safe_send(uid, f"✅ {p}%\n\nحداکثر تعداد استفاده:")
    except ValueError:
        safe_send(uid, "❌ عدد معتبر.")

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "discount_manual_maxuse" and is_admin(m.from_user.id))
def discount_manual_maxuse(message):
    uid = message.from_user.id
    state = get_state(uid)
    try:
        max_use = int(message.text.strip())
        add_discount(state.get("code"), state.get("percent"), max_use)
        clear_state(uid)
        mk = telebot.types.InlineKeyboardMarkup()
        mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_discount_mgr"))
        safe_send(uid,
            f"✅ کد ساخته شد!\n🎟 {state.get('code')}\n💯 {state.get('percent')}%\n🔢 {max_use}",
            reply_markup=mk)
    except ValueError:
        safe_send(uid, "❌ عدد معتبر.")

# ═══════════════════════════════════════════
#  مدیریت پلن‌ها
# ═══════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data == "adm_plans" and is_admin(c.from_user.id))
def adm_plans(call):
    all_plans = db_exec("SELECT * FROM plans ORDER BY plan_type,gb", fetch="all")
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    for p in all_plans:
        mk.add(telebot.types.InlineKeyboardButton(
            f"{'✅' if p['is_active'] else '❌'} {p['name']} — {fp(p['price'])}",
            callback_data=f"adm_plan_{p['plan_key']}"))
    mk.add(
        telebot.types.InlineKeyboardButton("➕ پلن جدید", callback_data="adm_add_plan"),
        telebot.types.InlineKeyboardButton("🔙 بازگشت",  callback_data="adm_back"),
    )
    safe_edit(call.from_user.id, call.message.message_id, "📐 مدیریت پلن‌ها:", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_plan_") and is_admin(c.from_user.id))
def adm_plan_detail(call):
    key = call.data[9:]
    p = db_exec("SELECT * FROM plans WHERE plan_key=?", (key,), "one")
    if not p: return
    mk = telebot.types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        telebot.types.InlineKeyboardButton(
            "❌ غیرفعال کن" if p['is_active'] else "✅ فعال کن",
            callback_data=f"adm_toggle_plan_{key}"),
        telebot.types.InlineKeyboardButton("✏️ ویرایش قیمت", callback_data=f"adm_edit_price_{key}"),
        telebot.types.InlineKeyboardButton("🗑 حذف پلن",     callback_data=f"adm_del_plan_{key}"),
    )
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_plans"))
    safe_edit(call.from_user.id, call.message.message_id,
        f"📐 {p['name']}\n💰 {fp(p['price'])}\n💾 {p['gb']} گیگ | 📅 {p['days']} روز\n"
        f"نوع: {'تک' if p['plan_type']=='single' else 'مولتی'}\n"
        f"وضعیت: {'✅ فعال' if p['is_active'] else '❌ غیرفعال'}",
        reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_edit_price_") and is_admin(c.from_user.id))
def adm_edit_price(call):
    key = call.data[15:]
    set_state(call.from_user.id, {"action": "editing_plan_price", "plan_key": key})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_plans"))
    safe_edit(call.from_user.id, call.message.message_id, f"✏️ قیمت جدید پلن {key} (تومان):", reply_markup=mk)

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "editing_plan_price" and is_admin(m.from_user.id))
def editing_plan_price(message):
    uid = message.from_user.id
    key = get_state(uid).get("plan_key")
    try:
        price = int(message.text.strip().replace(",",""))
        db_exec("UPDATE plans SET price=? WHERE plan_key=?", (price, key))
        clear_state(uid)
        mk = telebot.types.InlineKeyboardMarkup()
        mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_plans"))
        safe_send(uid, f"✅ قیمت پلن به {fp(price)} تغییر کرد.", reply_markup=mk)
    except ValueError:
        safe_send(uid, "❌ عدد معتبر.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_toggle_plan_") and is_admin(c.from_user.id))
def toggle_plan_btn(call):
    key = call.data[16:]
    new_status = toggle_plan(key)
    bot.answer_callback_query(call.id, f"✅ پلن {'فعال' if new_status else 'غیرفعال'} شد", show_alert=True)
    all_plans = db_exec("SELECT * FROM plans ORDER BY plan_type,gb", fetch="all")
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    for p in all_plans:
        mk.add(telebot.types.InlineKeyboardButton(
            f"{'✅' if p['is_active'] else '❌'} {p['name']} — {fp(p['price'])}",
            callback_data=f"adm_plan_{p['plan_key']}"))
    mk.add(
        telebot.types.InlineKeyboardButton("➕ پلن جدید", callback_data="adm_add_plan"),
        telebot.types.InlineKeyboardButton("🔙 بازگشت",  callback_data="adm_back"),
    )
    safe_edit(call.from_user.id, call.message.message_id, "📐 مدیریت پلن‌ها:", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_del_plan_") and is_admin(c.from_user.id))
def del_plan_btn(call):
    key = call.data[13:]
    delete_plan(key)
    bot.answer_callback_query(call.id, "✅ پلن حذف شد", show_alert=True)
    safe_edit(call.from_user.id, call.message.message_id, "👑 پنل ادمین:", reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda c: c.data == "adm_add_plan" and is_admin(c.from_user.id))
def adm_add_plan(call):
    set_state(call.from_user.id, {"action": "adding_plan_name"})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_plans"))
    safe_edit(call.from_user.id, call.message.message_id,
        "➕ پلن جدید\n\nنام پلن را وارد کنید:\nمثال: ۲۵ گیگابایت", reply_markup=mk)

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "adding_plan_name" and is_admin(m.from_user.id))
def adding_plan_name(message):
    set_state(message.from_user.id, {"action": "adding_plan_gb", "name": message.text.strip()})
    safe_send(message.from_user.id, f"✅ نام: {message.text}\n\nحجم (گیگابایت):")

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "adding_plan_gb" and is_admin(m.from_user.id))
def adding_plan_gb(message):
    uid = message.from_user.id
    try:
        gb = int(message.text.strip())
        state = get_state(uid)
        set_state(uid, {**state, "action": "adding_plan_price", "gb": gb})
        safe_send(uid, f"✅ حجم: {gb} گیگ\n\nقیمت (تومان):")
    except ValueError:
        safe_send(uid, "❌ عدد معتبر.")

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "adding_plan_price" and is_admin(m.from_user.id))
def adding_plan_price(message):
    uid = message.from_user.id
    try:
        price = int(message.text.strip().replace(",",""))
        state = get_state(uid)
        set_state(uid, {**state, "action": "adding_plan_days", "price": price})
        safe_send(uid, f"✅ قیمت: {fp(price)}\n\nمدت اعتبار (روز) — پیش‌فرض 30:")
    except ValueError:
        safe_send(uid, "❌ عدد معتبر.")

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "adding_plan_days" and is_admin(m.from_user.id))
def adding_plan_days(message):
    uid = message.from_user.id
    days = int(message.text.strip()) if message.text.strip().isdigit() else 30
    state = get_state(uid)
    set_state(uid, {**state, "action": "adding_plan_type", "days": days})
    mk = telebot.types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        telebot.types.InlineKeyboardButton("🖥 تک لوکیشن",    callback_data="aplan_single"),
        telebot.types.InlineKeyboardButton("🌍 مولتی لوکیشن", callback_data="aplan_multi"),
    )
    safe_send(uid, f"✅ {days} روز\n\nنوع سرور:", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("aplan_") and is_admin(c.from_user.id))
def finish_add_plan(call):
    uid = call.from_user.id
    ptype = call.data[6:]
    state = get_state(uid)
    key = f"custom_{state.get('gb')}gb_{random.randint(100,999)}"
    add_plan(key, state.get("name"), state.get("gb"), state.get("price"), state.get("days", 30), ptype)
    clear_state(uid)
    bot.answer_callback_query(call.id, "✅ پلن اضافه شد!", show_alert=True)
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_plans"))
    safe_edit(uid, call.message.message_id,
        f"✅ پلن جدید!\n🏷 {state.get('name')}\n💾 {state.get('gb')} گیگ\n"
        f"💰 {fp(state.get('price'))}\n📅 {state.get('days',30)} روز\n"
        f"نوع: {'تک' if ptype=='single' else 'مولتی'}", reply_markup=mk)

# ═══════════════════════════════════════════
#  مدیریت کانفیگ‌ها
# ═══════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data == "adm_cfgs" and is_admin(c.from_user.id))
def adm_cfgs(call):
    plans = db_exec("SELECT * FROM plans WHERE is_active=1 ORDER BY plan_type,gb", fetch="all")
    stock = get_all_stock()
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    for p in plans:
        s = stock.get(p['plan_key'], 0)
        mk.add(telebot.types.InlineKeyboardButton(
            f"{'✅' if s>0 else '❌'} {p['name']} — موجودی: {s}",
            callback_data=f"adm_cfg_{p['plan_key']}"))
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_back"))
    safe_edit(call.from_user.id, call.message.message_id, "📦 مدیریت کانفیگ‌ها:", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_cfg_") and is_admin(c.from_user.id))
def adm_cfg_detail(call):
    key = call.data[8:]
    p = get_plan(key)
    if not p: return
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    mk.add(
        telebot.types.InlineKeyboardButton("➕ اضافه کانفیگ", callback_data=f"adm_add_cfg_{key}"),
        telebot.types.InlineKeyboardButton("🗑 حذف کانفیگ",   callback_data=f"adm_del_cfg_{key}"),
        telebot.types.InlineKeyboardButton("🔙 بازگشت",       callback_data="adm_cfgs"),
    )
    safe_edit(call.from_user.id, call.message.message_id,
        f"📦 {p['name']}\n💰 {fp(p['price'])}\n📦 موجودی: {get_config_stock(key)}", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_add_cfg_") and is_admin(c.from_user.id))
def adm_add_cfg(call):
    key = call.data[12:]
    p = get_plan(key)
    set_state(call.from_user.id, {"action": "adm_saving_config", "plan_key": key})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"adm_cfg_{key}"))
    safe_edit(call.from_user.id, call.message.message_id,
        f"➕ افزودن کانفیگ — {p['name']}\n\nمتن کانفیگ:\n(هر خط = یک کانفیگ)", reply_markup=mk)

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "adm_saving_config" and is_admin(m.from_user.id))
def adm_save_config(message):
    uid = message.from_user.id
    key = get_state(uid).get("plan_key")
    p = get_plan(key)
    cfgs = [l.strip() for l in message.text.strip().split("\n") if l.strip()]
    for c in cfgs:
        add_config(key, c)
    clear_state(uid)
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_cfgs"))
    safe_send(uid,
        f"✅ {len(cfgs)} کانفیگ برای {p['name']} اضافه شد!\n📦 موجودی: {get_config_stock(key)}",
        reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_del_cfg_") and is_admin(c.from_user.id))
def adm_del_cfg(call):
    key = call.data[12:]
    p = get_plan(key)
    cfgs = get_unused_configs(key)
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    if not cfgs:
        mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"adm_cfg_{key}"))
        safe_edit(call.from_user.id, call.message.message_id,
            f"📦 {p['name']}\n\n❌ کانفیگی برای حذف نیست.", reply_markup=mk)
        return
    for i, (cid, ctxt, cdate) in enumerate(cfgs[:10], 1):
        short = ctxt[:30] + "..." if len(ctxt) > 30 else ctxt
        mk.add(telebot.types.InlineKeyboardButton(f"🗑 #{i} — {short}", callback_data=f"adm_do_del_{cid}_{key}"))
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"adm_cfg_{key}"))
    safe_edit(call.from_user.id, call.message.message_id,
        f"🗑 حذف کانفیگ — {p['name']}\nموجودی: {len(cfgs)}", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_do_del_") and is_admin(c.from_user.id))
def adm_do_del(call):
    parts = call.data.split("_")
    cid, key = int(parts[3]), parts[4]
    p = get_plan(key)
    ok = delete_config_by_id(cid)
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"adm_del_cfg_{key}"))
    if ok:
        safe_edit(call.from_user.id, call.message.message_id,
            f"✅ کانفیگ حذف شد.\n📦 موجودی {p['name']}: {get_config_stock(key)}", reply_markup=mk)
    else:
        safe_edit(call.from_user.id, call.message.message_id, "❌ خطا در حذف.", reply_markup=mk)

# ═══════════════════════════════════════════
#  مدیریت کاربران
# ═══════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data == "adm_users" and is_admin(c.from_user.id))
def adm_users(call):
    users = get_all_users()
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    mk.add(
        telebot.types.InlineKeyboardButton("🔍 سرچ کاربر",    callback_data="adm_search"),
        telebot.types.InlineKeyboardButton("📋 لیست کاربران", callback_data="adm_list_users"),
        telebot.types.InlineKeyboardButton("🔙 بازگشت",       callback_data="adm_back"),
    )
    safe_edit(call.from_user.id, call.message.message_id,
        f"👥 مدیریت کاربران\n\nتعداد کل: {len(users)} نفر", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == "adm_list_users" and is_admin(c.from_user.id))
def adm_list_users(call):
    users = get_all_users()
    text = f"👥 کاربران ({len(users)}):\n\n"
    for u in users[:15]:
        blocked = "🚫" if u[4] else ""
        uname = f"@{u[1]}" if u[1] and u[1] != "ندارد" else "—"
        text += f"{blocked} {u[0]} | {uname} | {fp(u[3])}\n"
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_users"))
    safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == "adm_search" and is_admin(c.from_user.id))
def adm_search(call):
    set_state(call.from_user.id, {"action": "searching_user"})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_users"))
    safe_edit(call.from_user.id, call.message.message_id,
        "🔍 آیدی یا یوزرنیم کاربر را وارد کنید:", reply_markup=mk)

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "searching_user" and is_admin(m.from_user.id))
def search_result(message):
    adm_uid = message.from_user.id
    user = search_user(message.text.strip().lstrip("@"))
    clear_state(adm_uid)
    if not user:
        mk = telebot.types.InlineKeyboardMarkup()
        mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_users"))
        safe_send(adm_uid, "❌ کاربر پیدا نشد.", reply_markup=mk); return
    uid = user['user_id']
    purchases = get_purchases(uid) or []
    mk2 = telebot.types.InlineKeyboardMarkup(row_width=2)
    mk2.add(
        telebot.types.InlineKeyboardButton("➕ افزایش موجودی", callback_data=f"abal_{uid}"),
        telebot.types.InlineKeyboardButton("➖ کاهش موجودی",  callback_data=f"sbal_{uid}"),
        telebot.types.InlineKeyboardButton("🚫 بلاک/آنبلاک",  callback_data=f"tblock_{uid}"),
        telebot.types.InlineKeyboardButton("📦 خریدها",        callback_data=f"upurchases_{uid}"),
        telebot.types.InlineKeyboardButton("✏️ تغییر نام",    callback_data=f"edit_name_{uid}"),
    )
    mk2.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_users"))
    safe_send(adm_uid,
        f"👤 {user['first_name']} | @{user['username']}\n🆔 {uid}\n"
        f"💰 {fp(user['balance'])}\n📦 {len(purchases)} خرید\n"
        f"🚫 بلاک: {'بله' if user['is_blocked'] else 'خیر'}\n📅 {user['created_at']}",
        reply_markup=mk2)

@bot.callback_query_handler(func=lambda c: c.data.startswith("edit_name_") and is_admin(c.from_user.id))
def edit_name(call):
    uid = int(call.data[10:])
    set_state(call.from_user.id, {"action": "editing_name", "tuid": uid})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_users"))
    safe_edit(call.from_user.id, call.message.message_id, f"✏️ نام جدید برای کاربر {uid}:", reply_markup=mk)

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "editing_name" and is_admin(m.from_user.id))
def do_edit_name(message):
    adm_uid = message.from_user.id
    uid = get_state(adm_uid).get("tuid")
    db_exec("UPDATE users SET first_name=? WHERE user_id=?", (message.text.strip(), uid))
    clear_state(adm_uid)
    safe_send(adm_uid, f"✅ نام کاربر {uid} تغییر کرد.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("abal_") and is_admin(c.from_user.id))
def abal(call):
    uid = int(call.data[5:])
    set_state(call.from_user.id, {"action": "adding_bal", "tuid": uid})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_users"))
    safe_edit(call.from_user.id, call.message.message_id,
        f"➕ افزایش موجودی کاربر {uid}\n\nمبلغ (تومان):", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("sbal_") and is_admin(c.from_user.id))
def sbal(call):
    uid = int(call.data[5:])
    set_state(call.from_user.id, {"action": "subtracting_bal", "tuid": uid})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_users"))
    safe_edit(call.from_user.id, call.message.message_id,
        f"➖ کاهش موجودی کاربر {uid}\n\nمبلغ (تومان):", reply_markup=mk)

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") in ["adding_bal","subtracting_bal"] and is_admin(m.from_user.id))
def change_bal(message):
    adm_uid = message.from_user.id
    state = get_state(adm_uid)
    target = state.get("tuid")
    try:
        amount = int(message.text.strip().replace(",",""))
        if state.get("action") == "subtracting_bal": amount = -amount
        update_balance(target, amount)
        clear_state(adm_uid)
        word = "افزایش" if amount > 0 else "کاهش"
        mk = telebot.types.InlineKeyboardMarkup()
        mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_users"))
        safe_send(adm_uid,
            f"✅ موجودی کاربر {target} {word} یافت.\n{fp(abs(amount))}\nموجودی جدید: {fp(get_balance(target))}",
            reply_markup=mk)
        safe_send(target,
            f"💰 موجودی شما {word} یافت.\n{'💚' if amount>0 else '🔴'} {fp(abs(amount))}\n💵 موجودی کل: {fp(get_balance(target))}")
    except ValueError:
        safe_send(adm_uid, "❌ عدد معتبر.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("tblock_") and is_admin(c.from_user.id))
def tblock(call):
    uid = int(call.data[7:])
    user = get_user(uid)
    if not user:
        bot.answer_callback_query(call.id, "❌ کاربر پیدا نشد!"); return
    new_block = not user['is_blocked']
    block_user(uid, new_block)
    bot.answer_callback_query(call.id, f"✅ کاربر {'بلاک' if new_block else 'آنبلاک'} شد", show_alert=True)
    if new_block:
        safe_send(uid, "🚫 دسترسی شما مسدود شده است.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("upurchases_") and is_admin(c.from_user.id))
def user_purchases(call):
    uid = int(call.data[11:])
    purchases = get_purchases(uid) or []
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_users"))
    if not purchases:
        safe_edit(call.from_user.id, call.message.message_id,
            f"📦 کاربر {uid} هیچ خریدی ندارد.", reply_markup=mk); return
    text = f"📦 خریدهای کاربر {uid}:\n\n"
    for p in purchases:
        text += f"• {p[1]} — {fp(p[2])} — {p[4]}\n"
    safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=mk)

# ═══════════════════════════════════════════
#  آمار
# ═══════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data == "adm_stats" and is_admin(c.from_user.id))
def adm_stats(call):
    tc, ta = get_today_sales()
    ac, aa = get_total_sales()
    users = get_all_users()
    stock = get_all_stock()
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_back"))
    safe_edit(call.from_user.id, call.message.message_id,
        f"📊 آمار\n{'═'*22}\n\n"
        f"📅 امروز:\n🛒 {tc} فروش | 💰 {fp(ta)}\n\n"
        f"📈 کل:\n🛒 {ac} فروش | 💰 {fp(aa)}\n\n"
        f"👥 کاربران: {len(users)}\n"
        f"🛡 ادمین‌ها: {len(get_admins() or [])}\n"
        f"📦 موجودی: {sum(stock.values())} کانفیگ\n\n"
        f"🤖 تأیید خودکار: {'✅' if auto_approve_enabled() else '❌'}\n"
        f"🔧 حالت تعمیر: {'✅' if maintenance_mode() else '❌'}",
        reply_markup=mk)

# ═══════════════════════════════════════════
#  ارسال همگانی
# ═══════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data == "adm_broadcast" and is_admin(c.from_user.id))
def adm_broadcast(call):
    set_state(call.from_user.id, {"action": "broadcasting"})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_back"))
    safe_edit(call.from_user.id, call.message.message_id, "📢 ارسال همگانی\n\nپیام را بنویسید:", reply_markup=mk)

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "broadcasting" and is_admin(m.from_user.id))
def do_broadcast(message):
    uid = message.from_user.id
    users = get_all_users()
    text = f"📢 پیام از Mat Star VPN:\n\n{message.text}"
    success, fail, msg_ids = 0, 0, []
    for u in users:
        if not u[4]:
            r = safe_send(u[0], text)
            if r: success += 1; msg_ids.append((u[0], r.message_id))
            else: fail += 1
    bid = save_broadcast(message.text, success)
    for uid2, mid2 in msg_ids:
        save_broadcast_msg(bid, uid2, mid2)
    clear_state(uid)
    mk = telebot.types.InlineKeyboardMarkup(row_width=1)
    mk.add(
        telebot.types.InlineKeyboardButton("🗑 حذف همگانی", callback_data=f"del_broadcast_{bid}"),
        telebot.types.InlineKeyboardButton("🔙 بازگشت",     callback_data="adm_back"),
    )
    safe_send(uid,
        f"✅ ارسال تمام شد!\n✅ موفق: {success}\n❌ ناموفق: {fail}\n🔖 #{bid}",
        reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("del_broadcast_") and is_admin(c.from_user.id))
def del_broadcast(call):
    bid = int(call.data[14:])
    msgs = get_broadcast_msgs(bid)
    deleted = 0
    for uid2, mid2 in msgs:
        try: bot.delete_message(uid2, mid2); deleted += 1
        except Exception: pass
    bot.answer_callback_query(call.id, f"✅ {deleted} پیام حذف شد", show_alert=True)
    safe_edit(call.from_user.id, call.message.message_id, "👑 پنل ادمین:", reply_markup=admin_menu())

# ═══════════════════════════════════════════
#  پیام شخصی به کاربر
# ═══════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data == "adm_dm" and is_admin(c.from_user.id))
def adm_dm(call):
    set_state(call.from_user.id, {"action": "dm_uid"})
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_back"))
    safe_edit(call.from_user.id, call.message.message_id,
        "💬 پیام به کاربر\n\nآیدی کاربر را وارد کنید:", reply_markup=mk)

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "dm_uid" and is_admin(m.from_user.id))
def dm_uid_handler(message):
    adm_uid = message.from_user.id
    try:
        uid = int(message.text.strip())
        user = get_user(uid)
        if not user:
            safe_send(adm_uid, "❌ کاربر پیدا نشد."); return
        set_state(adm_uid, {"action": "dm_text", "tuid": uid})
        safe_send(adm_uid, f"✅ {user['first_name']} | @{user['username']}\n\nپیام را بنویسید:")
    except ValueError:
        safe_send(adm_uid, "❌ آیدی معتبر.")

@bot.message_handler(
    func=lambda m: get_state(m.from_user.id).get("action") == "dm_text" and is_admin(m.from_user.id))
def dm_text_handler(message):
    adm_uid = message.from_user.id
    uid = get_state(adm_uid).get("tuid")
    r = safe_send(uid, f"📩 پیام از پشتیبانی:\n\n{message.text}")
    clear_state(adm_uid)
    mk = telebot.types.InlineKeyboardMarkup()
    mk.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_back"))
    safe_send(adm_uid,
        f"✅ پیام ارسال شد." if r else "❌ ارسال ناموفق (شاید بلاک کرده).",
        reply_markup=mk)

# ═══════════════════════════════════════════
#  پیام‌های ناشناخته
# ═══════════════════════════════════════════
@bot.message_handler(func=lambda m: True)
def unknown(message):
    uid = message.from_user.id
    if is_blocked(uid) or is_spam(uid): return
    if maintenance_mode() and not is_admin(uid):
        safe_send(uid, "🔧 ربات در حال بروزرسانی است. به زودی برمی‌گردیم..."); return
    if not get_state(uid):
        mk = telebot.types.InlineKeyboardMarkup()
        mk.add(telebot.types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu"))
        safe_send(uid, "برای شروع /start بزنید:", reply_markup=mk)

# ═══════════════════════════════════════════
#  اجرا با reconnect خودکار
# ═══════════════════════════════════════════
def run_bot():
    print("✅ ربات شروع به کار کرد!")
    print(f"👑 رئیس: {OWNER_ID}")
    print(f"🤖 تأیید خودکار: {'فعال' if auto_approve_enabled() else 'غیرفعال'}")
    print(f"🔧 حالت تعمیر: {'فعال' if maintenance_mode() else 'غیرفعال'}")

    while True:
        try:
            print("🔄 در حال اتصال به تلگرام...")
            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=60,
                allowed_updates=["message", "callback_query"],
                restart_on_change=False,
                logger_level=None,
            )
        except Exception as e:
            print(f"❌ خطای اتصال: {e}")
            print("⏳ ۱۵ ثانیه صبر می‌کنم و دوباره وصل می‌شم...")
            time.sleep(15)
            continue

if __name__ == "__main__":
    run_bot()

