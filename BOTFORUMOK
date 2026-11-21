import time
import requests
import random
from bs4 import BeautifulSoup
import threading
import re
import os
import telebot
from telebot import types
import concurrent.futures
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone
import traceback
import sys
import html as html_module

# =======================================
# ⏳ العد التصاعدي
# ==========================================
BOT_START_TIME = time.time()

def get_countdown_text() -> str:
    try:
        elapsed = time.time() - BOT_START_TIME
        total_minutes = int(elapsed) // 60
        total_hours   = total_minutes // 60

        if total_minutes < 60:
            return f"[{total_minutes}mini]"

        if total_hours < 24:
            return f"[{total_hours}h]"

        days  = total_hours // 24
        hours = total_hours % 24
        if hours > 0:
            return f"[{days} يوم {hours}h]"
        return f"[{days} يوم]"
    except Exception:
        return "[--]"

# ==========================================
# الإعدادات الأساسية
# ==========================================
TELEGRAM_TOKEN = "9174113475:AAGMOz__QIC7cbeWIqM_2JcHaOdtHZJhn3U"
bot = telebot.TeleBot(TELEGRAM_TOKEN)

CAPTCHA_ALERT_CHAT_ID = 7638322813

BASE_URL      = "https://forumok.com"
LOGIN_URL     = "https://forumok.com/login"
TARGET_URL    = "https://forumok.com/orders-search/socio"
STATS_URL     = "https://forumok.com/publisher-requests/socio/confirmed"
CONFIRMED_URL = "https://forumok.com/publisher-requests/socio/confirmed"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": BASE_URL
}

TAKE_COOLDOWN = 60

# ==========================================
# البروكسيات الثابتة للحسابات المستثناة
# ==========================================
EXEMPT_ACCOUNTS = [
    "france260026@gmail.com", 
    "rossxpro26@gmail.com", 
    "nurun2363@gmail.com",
    "samsamytff@gmail.com"
]

ACCOUNT_PROXIES = {
    "france260026@gmail.com": [
        "31.59.20.176:6754", "31.56.127.193:7684", "45.38.107.97:6014"
    ],
    "rossxpro26@gmail.com": [
        "198.105.121.200:6462", "64.137.96.74:6641", "198.23.243.226:6361"
    ],
    "nurun2363@gmail.com": [
        "38.154.185.97:6370", "84.247.60.125:6095"
    ],
    "samsamytff@gmail.com": [
        "142.111.67.146:5611", "191.96.254.138:6185"
    ]
}

PROXY_USER = "dwzxxjfl"
PROXY_PASS = "e1in83kj5c8x"

def check_single_exempt_proxy(prx):
    """دالة فرعية لفحص البروكسي الثابت وإرجاع الوقت والـ URL"""
    check_url = "https://api.ipify.org?format=json"
    try:
        if "mnvfoqyw:18kjk2uk8zmh" in prx:
            parts = prx.split(":")
            proxy_url = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        else:
            proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{prx}"

        start = time.time()
        # تم تقليل المهلة هنا إلى 5 ثوانٍ لضمان سرعة الفحص والتنفيذ الفوري عند الحاجة
        r = requests.get(check_url, headers=HEADERS,
                         proxies={"http": proxy_url, "https": proxy_url},
                         timeout=5)
        elapsed = time.time() - start
        if r.status_code == 200:
            return proxy_url, elapsed
    except Exception:
        pass
    return None, float('inf')

# 🚀 تم تعديل الدالة لتقوم بالفحص اللحظي الفوري فائق السرعة بالتوازي عند طلب المهمة مباشرة
def get_fastest_proxy_exempt(email):
    """
    تقوم بفحص جميع البروكسيات الثابتة للحساب بالتوازي فوراً عند استدعائها
    وتحديد الأسرع لتمريره مباشرة دون انتظار مؤقتات أو كاش قديم.
    """
    email_lower = email.lower().strip()
    proxies = ACCOUNT_PROXIES.get(email_lower)
    if not proxies:
        return None

    fastest_url = None
    best_time = float('inf')

    # فحص متوازي فوري لكافة البروكسيات المتاحة للحساب للحصول على أسرع استجابة
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(proxies)) as executor:
        results = executor.map(check_single_exempt_proxy, proxies)

    for proxy_url, elapsed in results:
        if proxy_url and elapsed < best_time:
            best_time = elapsed
            fastest_url = proxy_url

    return fastest_url

def notify_user_no_proxy(chat_id, email):
    try:
        account_label = email.split("@")[0]
        msg = f"⚠️ **تنبيه البروكسي**\n\n" \
              f"👤 الحساب: **{account_label}** (`{email}`)\n" \
              f"🛑 جميع البروكسيات الثابتة ميتة أو معطلة!\n" \
              f"🚫 **تم إلغاء تسجيل الدخول لهذا الحساب — لا يُسمح بالدخول بدون بروكسي إطلاقاً.**"
        bot.send_message(chat_id, msg, parse_mode="Markdown")
    except Exception as e:
        print(f"[NOTIFY] خطأ في إرسال تنبيه البروكسي: {e}")

def _session_has_proxy_attached(session, email):
    email_lower = email.lower().strip()
    if email_lower not in EXEMPT_ACCOUNTS:
        return True

    proxy_dict = getattr(session, 'proxies', {})
    if not proxy_dict:
        return False

    proxy_url = proxy_dict.get("http") or proxy_dict.get("https")
    return bool(proxy_url)

# ==========================================
# التخزين المحلي (بدون سحابة)
# ==========================================
local_multi_accounts = {}   
local_user_settings  = {}   

def get_saved_multi_accounts(chat_id):
    return local_multi_accounts.get(int(chat_id), [])

def save_multi_account(chat_id, email, password):
    cid = int(chat_id)
    if cid not in local_multi_accounts:
        local_multi_accounts[cid] = []
    email_lower = email.lower().strip()
    for acc in local_multi_accounts[cid]:
        if acc['email'] == email_lower:
            acc['password'] = password
            return True
    local_multi_accounts[cid].append({'email': email_lower, 'password': password})
    return True

def delete_multi_account(chat_id, email):
    cid = int(chat_id)
    if cid in local_multi_accounts:
        local_multi_accounts[cid] = [
            a for a in local_multi_accounts[cid]
            if a['email'] != email.lower().strip()
        ]
    return True

# ==========================================
# متغيرات الحالة العامة
# ==========================================
user_sessions           = {}
user_data_store         = {}   
user_numbered_tasks     = {}
user_transient_messages = {}

user_auth_sessions = {}
auth_sessions_lock = threading.Lock()

logged_out_accounts = {}
logged_out_lock     = threading.Lock()

_handling_blocked      = set()
_handling_blocked_lock = threading.Lock()

active_accounts      = {}
active_accounts_lock = threading.Lock()

acct_auto_hunt_status = {}
acct_hunt_mode        = {}
auto_hunt_status = {}
hunt_mode        = {}
last_take_time   = {}

# ==========================================
# دوال مساعدة للإعدادات
# ==========================================
def get_email_settings(email):
    e = email.lower().strip()
    return {
        'auto_hunt_status': acct_auto_hunt_status.get(e, False),
        'hunt_mode':        acct_hunt_mode.get(e, 'GTE'),
    }

def sync_chat_settings_to_email(chat_id, email):
    e = email.lower().strip()
    acct_auto_hunt_status[e] = auto_hunt_status.get(chat_id, False)
    acct_hunt_mode[e]        = hunt_mode.get(chat_id, 'GTE')

def sync_email_settings_to_chat(chat_id, email):
    e = email.lower().strip()
    auto_hunt_status[chat_id] = acct_auto_hunt_status.get(e, False)
    hunt_mode[chat_id]        = acct_hunt_mode.get(e, 'GTE')

def register_account_in_active(chat_id, email, password):
    with active_accounts_lock:
        if chat_id not in active_accounts:
            active_accounts[chat_id] = {}
        active_accounts[chat_id][email.lower().strip()] = {
            'email': email, 'password': password
        }

# ==========================================
# 🚨 كشف الحظر والـ CAPTCHA
# ==========================================
def detect_page_state(html_text):
    if not html_text:
        return None
    html_lower = html_text.lower()
    blocked_sigs = ["заблокирован", "аккаунт заблокирован",
                    "account is blocked", "account blocked"]
    for s in blocked_sigs:
        if s in html_lower:
            return "blocked"
    captcha_sigs = ["recaptcha", "g-recaptcha", "captcha",
                    "i am not a robot", "я не робот",
                    "cloudflare", "cf-challenge", "challenge-form"]
    for s in captcha_sigs:
        if s in html_lower:
            return "captcha"
    if "login-box" in html_lower and "Выход" not in html_text:
        return "captcha"
    return None

def handle_blocked_account(email, chat_id_origin=None):
    email_lower = email.lower().strip()
    with _handling_blocked_lock:
        if email_lower in _handling_blocked:
            return
        _handling_blocked.add(email_lower)
    try:
        account_label = email_lower.split("@")[0]
        acct_auto_hunt_status[email_lower] = False
        with auth_sessions_lock:
            user_auth_sessions.pop(email_lower, None)

        affected_chats = []
        with active_accounts_lock:
            for cid, accounts in active_accounts.items():
                if email_lower in accounts:
                    affected_chats.append(cid)

        blocked_msg = (
            f"🚫 **تنبيه: حساب محظور**\n\n"
            f"⛔ الحساب **{account_label}** (`{email_lower}`) تعرّض للحظر.\n"
            f"📌 تم تسجيل الخروج وحذفه تلقائياً."
        )
        for cid in affected_chats:
            with active_accounts_lock:
                if cid in active_accounts:
                    active_accounts[cid].pop(email_lower, None)
            delete_multi_account(cid, email_lower)
            with logged_out_lock:
                if cid not in logged_out_accounts:
                    logged_out_accounts[cid] = set()
                logged_out_accounts[cid].add(email_lower)
            active_email = user_data_store.get(cid, {}).get("email", "").lower().strip()
            if active_email == email_lower:
                for store in [user_data_store, user_sessions, user_numbered_tasks,
                               auto_hunt_status, hunt_mode, last_take_time]:
                    store.pop(cid, None)
            try:
                bot.send_message(cid, blocked_msg, parse_mode="Markdown")
            except Exception:
                pass
    finally:
        def _clear():
            time.sleep(120)
            with _handling_blocked_lock:
                _handling_blocked.discard(email_lower)
        threading.Thread(target=_clear, daemon=True).start()

def handle_captcha_detected(email, context=""):
    email_lower = email.lower().strip()
    account_label = email_lower.split("@")[0]
    acct_auto_hunt_status[email_lower] = False
    with auth_sessions_lock:
        user_auth_sessions.pop(email_lower, None)
    captcha_msg = (
        f"🤖 **تنبيه: CAPTCHA ظهر!**\n\n"
        f"🔐 الحساب: **{account_label}** (`{email_lower}`)\n"
        f"⚠️ يجب حل التحقق يدوياً."
    )
    try:
        bot.send_message(CAPTCHA_ALERT_CHAT_ID, captcha_msg, parse_mode="Markdown")
    except Exception:
        pass

# ==========================================
# إنشاء الجلسات
# ==========================================
def _safe_get(url, session=None, retries=3, **kwargs):
    req = session or requests
    kwargs.setdefault("timeout", 15)
    for i in range(retries):
        try:
            return req.get(url, **kwargs)
        except requests.exceptions.RequestException:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))

def get_authenticated_session(username, password, chat_id=None):
    email_lower = username.lower().strip()

    with auth_sessions_lock:
        cached = user_auth_sessions.get(email_lower)
    if cached:
        try:
            test_r = cached.get(BASE_URL, headers=HEADERS, timeout=8)
            page_state = detect_page_state(test_r.text)
            if page_state == "blocked":
                threading.Thread(target=handle_blocked_account, args=(username,), daemon=True).start()
                with auth_sessions_lock:
                    user_auth_sessions.pop(email_lower, None)
                return None
            if page_state == "captcha":
                threading.Thread(target=handle_captcha_detected,
                                 args=(username, "التحقق من الجلسة"), daemon=True).start()
                with auth_sessions_lock:
                    user_auth_sessions.pop(email_lower, None)
                return None
            if "Выход" in test_r.text:
                return cached
        except Exception:
            pass
        with auth_sessions_lock:
            user_auth_sessions.pop(email_lower, None)

    sess = requests.Session()
    if email_lower in EXEMPT_ACCOUNTS:
        fast_proxy_url = get_fastest_proxy_exempt(email_lower)
        if fast_proxy_url:
            sess.proxies = {"http": fast_proxy_url, "https": fast_proxy_url}
        else:
            print(f"[SESSION] ⚠️ {email_lower}: البروكسيات ميتة! جاري الدخول المباشر بدون بروكسي...")
            if chat_id:
                threading.Thread(target=notify_user_no_proxy, args=(chat_id, username), daemon=True).start()

    login_data = {
        "signin[username]": username,
        "signin[password]": password,
        "signin[remember]": "1",
        "signin[refer_url]": "@office_initial"
    }
    try:
        sess.get(BASE_URL, headers=HEADERS, timeout=12)
        lr = sess.post(LOGIN_URL, data=login_data, headers=HEADERS, timeout=12)
        if lr.status_code == 200:
            page_state = detect_page_state(lr.text)
            if page_state == "blocked":
                threading.Thread(target=handle_blocked_account,
                                 args=(username,), daemon=True).start()
                return None
            if page_state == "captcha":
                threading.Thread(target=handle_captcha_detected,
                                 args=(username, "تسجيل الدخول"), daemon=True).start()
                return None
            if "Выход" in lr.text:
                with auth_sessions_lock:
                    user_auth_sessions[email_lower] = sess
                return sess
    except Exception:
        pass
    return None

# ==========================================
# استخراج البيانات
# ==========================================
def translate_and_parse_duration(duration_text):
    duration_text = duration_text.strip().lower()
    try:
        m = re.search(r"(\d+)", duration_text)
        if not m:
            return 120, "2 ساعات"
        number = int(m.group(1))
        if any(x in duration_text for x in ["день", "дня", "дней"]):
            total_minutes = number * 24 * 60
            text = "1 يوم" if number == 1 else f"{number} أيام"
        elif any(x in duration_text for x in ["час", "часа", "часов"]):
            total_minutes = number * 60
            text = "1 ساعة" if number == 1 else f"{number} ساعات"
        elif any(x in duration_text for x in ["минут", "минуты", "минутку"]):
            total_minutes = number
            text = "1 دقيقة" if number == 1 else f"{number} دقائق"
        else:
            total_minutes = number * 60
            text = f"{number} ساعات"
        return total_minutes, text
    except Exception:
        return 120, "2 ساعات"

def fetch_publisher_stats(session):
    stats = {"to_execute": "0", "on_check": "0", "completed": "0"}
    try:
        r = session.get(STATS_URL, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            page_text = r.text
            m = re.search(r"Выполнить\s+(\d+)", page_text)
            if m:
                stats["to_execute"] = m.group(1)
            m = re.search(r"На проверке\s+(\d+)", page_text)
            if m:
                stats["on_check"] = m.group(1)
            m = re.search(r"Выполнено\s+(\d+)", page_text)
            if m:
                stats["completed"] = m.group(1)
    except Exception:
        pass
    return stats

def get_site_data(username, password, chat_id):
    session = get_authenticated_session(username, password, chat_id)
    if not session:
        return None, "AUTH_FAILED"
    try:
        r = _safe_get(TARGET_URL, session=session, headers=HEADERS, timeout=12)
        page_state = detect_page_state(r.text)
        if page_state == "blocked":
            threading.Thread(target=handle_blocked_account,
                             args=(username,), daemon=True).start()
            return None, "BLOCKED"
        if page_state == "captcha":
            threading.Thread(target=handle_captcha_detected,
                             args=(username, "جلب المهام"), daemon=True).start()
            return None, "CAPTCHA"
        if "Выход" not in r.text:
            return None, "SESSION_EXPIRED"

        soup = BeautifulSoup(r.text, "html.parser")
        page_text = soup.get_text(separator="\n")

        balance = "0.0"
        m = re.search(r"Доступно:\s*([\d.,\s]+)\s*р\.", page_text)
        if m:
            balance = m.group(1).strip()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            stats_future = ex.submit(fetch_publisher_stats, session)

            PLATFORM_MAP = {
                "youtube": "YouTube", "telegram": "Telegram",
                "yandex": "Yandex", "google": "Google",
                "vkontakte": "VKontakte", "vk": "VKontakte",
                "instagram": "Instagram", "tiktok": "TikTok",
                "twitter": "Twitter", "facebook": "Facebook", "ok": "OK",
            }

            tasks_list = []
            tbody = soup.find("tbody", class_="td-order-search")
            rows = tbody.find_all("tr", id=re.compile(r"^tr\d+")) if tbody else []

            for row in rows:
                try:
                    row_classes = row.get("class", []) or []
                    if "taken-list" in row_classes or "gray-list" in row_classes:
                        continue

                    cells = row.find_all("td")
                    if len(cells) < 9:
                        continue

                    action_cell = cells[-1]
                    take_link = action_cell.find("a", href=True)
                    if not take_link or action_cell.find("img", alt="take") is None:
                        continue

                    take_href = take_link.get("href", "")
                    task_page_url = (take_href if take_href.startswith("http")
                                     else BASE_URL + take_href)
                    if "?ok=1" not in task_page_url:
                        task_page_url += ("?ok=1" if "?" not in task_page_url
                                          else "&ok=1")

                    price_raw = cells[3].get_text(strip=True).replace(",", ".").replace(" ", "")
                    try:
                        real_price = float(price_raw)
                    except ValueError:
                        continue

                    country_img = cells[4].find("img")
                    country_code = country_img.get("alt", "--") if country_img else "--"

                    raw_duration = "2 часа"
                    task_desc = ""
                    info_img = cells[2].find("img", class_="cursor-help")
                    if info_img:
                        raw_content = html_module.unescape(info_img.get("content", ""))
                        mini = BeautifulSoup(raw_content, "html.parser")
                        for small in mini.find_all("small"):
                            if "Время на выполнение" in small.get_text():
                                b = small.find("b")
                                if b:
                                    raw_duration = b.get_text(strip=True)
                        parts = [tag.get_text(separator=" ", strip=True)
                                 for tag in mini.find_all(["p", "li"])
                                 if tag.get_text(strip=True)]
                        task_desc = " ".join(parts)

                    task_minutes, arabic_duration = translate_and_parse_duration(raw_duration)

                    plat_img = cells[1].find("img")
                    platform_key = plat_img.get("alt", "").lower().strip() if plat_img else ""
                    app_name = PLATFORM_MAP.get(platform_key, "منصة أخرى")

                    is_restricted = "غير مقيدة"
                    restrictions_details = ""
                    task_desc_check = task_desc.lower()
                    if country_code not in ("", "--", "---"):
                        is_restricted = "مقيدة"
                        restrictions_details = country_code
                    elif any(x in task_desc_check for x in
                             ["россия", "russia", "только для рф", "рф"]):
                        is_restricted = "مقيدة"
                        restrictions_details = "روسيا"

                    tasks_list.append({
                        "price": f"{real_price:.2f}",
                        "task_page": task_page_url,
                        "duration": arabic_duration,
                        "minutes": task_minutes,
                        "description": task_desc,
                        "app_name": app_name,
                        "is_restricted": is_restricted,
                        "restrictions": restrictions_details,
                    })
                except Exception:
                    continue

            try:
                stats_data = stats_future.result(timeout=8)
            except Exception:
                stats_data = {"to_execute": "0", "on_check": "0", "completed": "0"}

        user_numbered_tasks[chat_id] = tasks_list
        return {"balance": balance, "stats": stats_data, "tasks": tasks_list}, "SUCCESS"
    except Exception:
        return None, "ERROR"

def take_task_via_post(session, task_page_url):
    try:
        response = session.get(task_page_url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return "FAILED"

        soup = BeautifulSoup(response.text, "html.parser")
        page_text = soup.get_text()

        not_available = ["нет заданий", "no tasks", "задание недоступно",
                         "order not found", "not found", "404"]
        for sig in not_available:
            if sig in page_text.lower():
                return "FAILED"

        form = soup.find("form", action=re.compile(r"batch|order_request"))
        if not form:
            return "FAILED"

        post_action_url = f"{BASE_URL}/order_request_socio/batch"
        if form.get('action'):
            act = form.get('action')
            post_action_url = act if act.startswith("http") else BASE_URL + act

        post_data = {"batch_action": "batchConfirm"}
        for hidden_input in form.find_all("input", type="hidden"):
            if hidden_input.get("name"):
                post_data[hidden_input.get("name")] = hidden_input.get("value", "")

        account_checkboxes = form.find_all("input", class_="batch_checkbox")
        account_ids = [cb.get("value") for cb in account_checkboxes if cb.get("value")]
        if account_ids:
            post_data["ids[]"] = account_ids
        elif form.find("input", name="ids[]"):
            post_data["ids[]"] = [form.find("input", name="ids[]").get("value", "")]
        else:
            return "FAILED"

        res = session.post(post_action_url, data=post_data, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return "FAILED"

        response_text = res.text

        if "задание уже выполняется" in response_text:
            return "SAME_IP"

        if "Аккаунты не выбраны" in response_text:
            return "ALREADY_TAKEN"

        if "взяли задание в работу" in response_text:
            return "SUCCESS"

        return "FAILED"
    except Exception:
        return "FAILED"

# ==========================================
# 🔥 الواجهات
# ==========================================
def get_auth_menu(chat_id=None):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if chat_id:
        saved = get_saved_multi_accounts(chat_id)
        for i, acc in enumerate(saved, 1):
            label = acc['email'].split('@')[0]
            markup.add(types.InlineKeyboardButton(
                f"⚡ الدخول المباشر: الحساب {i} ({label})",
                callback_data=f"switch_acc_{i-1}"
            ))
    markup.add(types.InlineKeyboardButton(
        "🔐 تسجيل الدخول بحساب جديد", callback_data="login_start"
    ))
    return markup

def get_main_menu_text() -> str:
    return f"🏠 القائمة الرئيسية  {get_countdown_text()}\nــــــــــــــــــ"

def get_main_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    user_label = "غير محدد"
    if chat_id in user_data_store:
        email = user_data_store[chat_id].get('email', '')
        if "@" in email:
            user_label = email.split('@')[0]
    markup.add(types.InlineKeyboardButton(
        f"👤 الحساب الحالي: {user_label} 🔄",
        callback_data="switch_account_menu"
    ))
    markup.add(types.InlineKeyboardButton(
        "📋 عرض المهام المتاحة وتحديثها", callback_data="view_tasks"
    ))
    markup.add(types.InlineKeyboardButton(
        "🎯 اصطحاب للعمل (GT / GTE)", callback_data="take_work_menu"
    ))
    # ✅ الزر الجديد
    markup.add(types.InlineKeyboardButton(
        "🔑 USER - PROXY", callback_data="proxy_info"
    ))
    return markup

def get_switch_account_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    saved = get_saved_multi_accounts(chat_id)
    current_email = user_data_store.get(chat_id, {}).get('email', '').lower().strip()
    with logged_out_lock:
        lo_set = set(logged_out_accounts.get(chat_id, set()))
    for i, acc in enumerate(saved, 1):
        email = acc['email']
        label = email.split('@')[0]
        e = email.lower().strip()
        if e == current_email:
            icon = "✅"
        elif e in lo_set:
            icon = "💤"
        else:
            icon = "⚡" if acct_auto_hunt_status.get(e, False) else "🔘"
        markup.add(types.InlineKeyboardButton(
            f"{icon} الحساب {i}: {label}",
            callback_data=f"switch_acc_{i-1}"
        ))
    markup.add(types.InlineKeyboardButton("➕ إضافة حساب جديد", callback_data="add_new_account"))
    markup.add(types.InlineKeyboardButton("🗑️ حذف حساب", callback_data="delete_account_start"))
    markup.add(types.InlineKeyboardButton("🚪 تسجيل الخروج", callback_data="logout"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
    return markup

def get_take_work_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    current_mode = hunt_mode.get(chat_id, "GTE")
    is_active    = auto_hunt_status.get(chat_id, False)
    icon_gt  = "🟢" if (is_active and current_mode == "GT")  else "🔴"
    icon_gte = "🟢" if (is_active and current_mode == "GTE") else "🔴"
    markup.add(types.InlineKeyboardButton(
        f"اصطحاب > 2 ساعات  {icon_gt}", callback_data="toggle_gt"
    ))
    markup.add(types.InlineKeyboardButton(
        f"اصطحاب >= 2 ساعات  {icon_gte}", callback_data="toggle_gte"
    ))
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
    return markup

# ==========================================
# 🔄 الخيط الخلفي
# ==========================================
_bg_last_hunt = {}
_bg_last_take = {}

_same_ip_blocked_tasks = {}
_same_ip_blocked_lock  = threading.Lock()
SAME_IP_BLOCK_EXPIRY   = 12 * 3600  


def _is_task_blocked(email_lower, task_id):
    now = time.time()
    with _same_ip_blocked_lock:
        acc_map = _same_ip_blocked_tasks.get(email_lower)
        if not acc_map:
            return False

        expired = [tid for tid, added_at in acc_map.items()
                   if now - added_at >= SAME_IP_BLOCK_EXPIRY]
        for tid in expired:
            acc_map.pop(tid, None)
        if not acc_map:
            _same_ip_blocked_tasks.pop(email_lower, None)
            return False

        return task_id in acc_map


def _add_blocked_task(email_lower, task_id):
    with _same_ip_blocked_lock:
        _same_ip_blocked_tasks.setdefault(email_lower, {})[task_id] = time.time()


def _extract_task_id(task_page_url):
    m = re.search(r"/create-request/(\d+)", task_page_url)
    if m:
        return m.group(1)
    m = re.search(r"/order[_/](\d+)", task_page_url)
    if m:
        return m.group(1)
    m = re.search(r"/(\d+)/?(?:\?|$)", task_page_url)
    if m:
        return m.group(1)
    return task_page_url  

def _bg_process_one_account_inner(chat_id, email, password, current_time):
    key = (chat_id, email)
    e = email.lower().strip()
    settings = get_email_settings(email)

    if settings['auto_hunt_status']:
        last_take = _bg_last_take.get(key, 0)
        if current_time - last_take >= TAKE_COOLDOWN:
            if current_time - _bg_last_hunt.get(key, 0) >= 80:
                _bg_last_hunt[key] = current_time
                data, status = get_site_data(email, password, chat_id)
                if status == "SUCCESS" and data and data['tasks']:
                    mode = settings['hunt_mode']
                    for target_task in data['tasks']:
                        task_id = _extract_task_id(target_task['task_page'])
                        if _is_task_blocked(e, task_id):
                            continue  

                        task_minutes = target_task.get('minutes', 120)
                        should_take = ((mode == "GT"  and task_minutes > 120) or
                                       (mode == "GTE" and task_minutes >= 120))
                        if should_take:
                            session = get_authenticated_session(email, password, chat_id)
                            if session:
                                # تحديث البروكسي لحظياً بالتوازي فوراً عند استلام المهمة لضمان السرعة القصوى وعدم هروبها
                                if e in EXEMPT_ACCOUNTS:
                                    fast_proxy_url = get_fastest_proxy_exempt(e)
                                    if fast_proxy_url:
                                        session.proxies = {"http": fast_proxy_url, "https": fast_proxy_url}

                                if not _session_has_proxy_attached(session, email):
                                    try:
                                        bot.send_message(
                                            chat_id,
                                            f"🚫 **تنبيه: تعذّر الاصطحاب**\n\n"
                                            f"👤 الحساب: {e.split('@')[0]}\n"
                                            f"🛑 لا يوجد اتصال ناجح بأي بروكسي حالياً، ولن يتم الاصطحاب بالـ IP الأصلي إطلاقاً.\n"
                                            f"🔁 سيُعاد المحاولة تلقائياً عند توفر بروكسي شغّال."
                                        )
                                    except Exception:
                                        pass
                                    break

                                take_status = take_task_via_post(session, target_task['task_page'])
                                if take_status == "SUCCESS":
                                    _bg_last_take[key] = time.time()
                                    try:
                                        bot.send_message(
                                            chat_id,
                                            f"⚡ تم اصطحاب مهمة تلقائياً!\n"
                                            f"👤 الحساب: {e.split('@')[0]}\n"
                                            f"💰 السعر: {target_task['price']} RUB\n"
                                            f"⏱️ الوقت: {target_task['duration']}"
                                        )
                                    except Exception:
                                        pass
                                elif take_status == "SAME_IP":
                                    _add_blocked_task(e, task_id)
                                    try:
                                        bot.send_message(
                                            chat_id,
                                            f"⚠️ **تنبيه: نفس عنوان IP**\n\n"
                                            f"👤 الحساب: {e.split('@')[0]}\n"
                                            f"🆔 رقم المهمة: {task_id}\n"
                                            f"🛑 الموقع رفض الاصطحاب لأن نفس الـ IP يستخدمه حساب آخر لديك في مهمة قيد التنفيذ حالياً.\n"
                                            f"🚫 لن يُعاد تجربة هذه المهمة من هذا الحساب لمدة 12 ساعة."
                                        )
                                    except Exception:
                                        pass
                                elif take_status == "ALREADY_TAKEN":
                                    _add_blocked_task(e, task_id)
                                    try:
                                        bot.send_message(
                                            chat_id,
                                            f"⚠️ **تنبيه: هذه المهمة نُفّذت من قبل**\n\n"
                                            f"👤 الحساب: {e.split('@')[0]}\n"
                                            f"🆔 رقم المهمة: {task_id}\n"
                                            f"🛑 الموقع لم يعرض أي حساب للاختيار، لأن هذا الحساب سبق ونفّذ هذه المهمة تحديداً من قبل.\n"
                                            f"🚫 لن يُعاد تجربة هذه المهمة من هذا الحساب لمدة 12 ساعة."
                                        )
                                    except Exception:
                                        pass
                            break

def global_background_worker():
    while True:
        try:
            current_time = time.time()
            with active_accounts_lock:
                snapshot = {cid: dict(accs) for cid, accs in active_accounts.items()}
            for chat_id, accounts in snapshot.items():
                for email_key, creds in accounts.items():
                    try:
                        _bg_process_one_account_inner(
                            chat_id, creds['email'], creds['password'], current_time
                        )
                    except Exception as ex:
                        print(f"[BG] خطأ في {email_key}: {ex}")
        except Exception as e:
            print(f"[BG] خطأ عام: {e}")
        time.sleep(5)

# ==========================================
# 📞 معالجة Callbacks
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_all_inline_callbacks(call):
    try:
        _handle_callback_inner(call)
    except Exception as err:
        print(f"[CALLBACK] خطأ: {err}")
        try:
            bot.answer_callback_query(call.id, "⚠️ حدث خطأ.")
        except Exception:
            pass

def _handle_callback_inner(call):
    chat_id    = call.message.chat.id
    data       = call.data
    message_id = call.message.message_id

    # إلغاء أي جلسة لتغيير البروكسي إذا ضغط المستخدم على أي زر آخر
    if chat_id in user_sessions:
        step = user_sessions[chat_id].get('step', '')
        if step in ['WAITING_EMAIL', 'WAITING_PASSWORD', 'WAITING_DELETE_ACCOUNT',
                    'CHANGE_PROXY_USER', 'CHANGE_PROXY_PASS']:
            del user_sessions[chat_id]

    if data.startswith("switch_acc_"):
        idx  = int(data.replace("switch_acc_", ""))
        saved = get_saved_multi_accounts(chat_id)
        if 0 <= idx < len(saved):
            acc = saved[idx]
            new_email_lower = acc['email'].lower().strip()
            old_email = user_data_store.get(chat_id, {}).get('email', '')
            if old_email:
                sync_chat_settings_to_email(chat_id, old_email)
            user_data_store[chat_id] = {'email': acc['email'], 'password': acc['password']}
            register_account_in_active(chat_id, acc['email'], acc['password'])
            with logged_out_lock:
                if chat_id in logged_out_accounts:
                    logged_out_accounts[chat_id].discard(new_email_lower)
            sync_email_settings_to_chat(chat_id, acc['email'])
            with auth_sessions_lock:
                cached = user_auth_sessions.get(new_email_lower)
            if not cached:
                threading.Thread(
                    target=lambda: get_authenticated_session(acc['email'], acc['password'], chat_id),
                    daemon=True
                ).start()
            bot.answer_callback_query(call.id)
            try:
                bot.edit_message_text(
                    get_main_menu_text(), chat_id, message_id,
                    reply_markup=get_main_menu(chat_id)
                )
            except Exception:
                bot.send_message(chat_id, get_main_menu_text(),
                                 reply_markup=get_main_menu(chat_id))
        else:
            bot.answer_callback_query(call.id, "⚠️ خطأ.", show_alert=True)

    elif data == "switch_account_menu":
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(
                "🔄 **إدارة الحسابات**\nاختر حساباً أو أضف جديداً:\nــــــــــــــــــ",
                chat_id, message_id,
                reply_markup=get_switch_account_menu(chat_id),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif data == "add_new_account":
        bot.answer_callback_query(call.id)
        if chat_id in user_transient_messages:
            try:
                bot.delete_message(chat_id, user_transient_messages[chat_id])
            except Exception:
                pass
        msg = bot.send_message(chat_id, "📥 أدخل البريد الإلكتروني للحساب الجديد:")
        user_transient_messages[chat_id] = msg.message_id
        user_sessions[chat_id] = {'step': 'WAITING_EMAIL'}

    elif data == "delete_account_start":
        bot.answer_callback_query(call.id)
        saved = get_saved_multi_accounts(chat_id)
        if not saved:
            bot.answer_callback_query(call.id, "⚠️ لا توجد حسابات.", show_alert=True)
            return
        lines = ["🗑️ **حذف حساب**\n\nأرسل **رقم الحساب** للحذف:\n"]
        for i, acc in enumerate(saved, 1):
            lines.append(f"  {i}. {acc['email'].split('@')[0]}")
        lines.append("\nأو أرسل **إلغاء** للرجوع.")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="switch_account_menu"))
        if chat_id in user_transient_messages:
            try:
                bot.delete_message(chat_id, user_transient_messages[chat_id])
            except Exception:
                pass
        msg = bot.send_message(chat_id, "\n".join(lines),
                               parse_mode="Markdown", reply_markup=markup)
        user_transient_messages[chat_id] = msg.message_id
        user_sessions[chat_id] = {'step': 'WAITING_DELETE_ACCOUNT'}

    elif data == "login_start":
        bot.answer_callback_query(call.id)
        if chat_id in user_transient_messages:
            try:
                bot.delete_message(chat_id, user_transient_messages[chat_id])
            except Exception:
                pass
        msg = bot.send_message(chat_id, "📥 أدخل البريد الإلكتروني:")
        user_transient_messages[chat_id] = msg.message_id
        user_sessions[chat_id] = {'step': 'WAITING_EMAIL'}

    elif data == "logout":
        bot.answer_callback_query(call.id)
        creds = user_data_store.get(chat_id, {})
        email_to_logout = creds.get('email', '').lower().strip()
        if email_to_logout:
            with auth_sessions_lock:
                user_auth_sessions.pop(email_to_logout, None)
            acct_auto_hunt_status[email_to_logout] = False
            with logged_out_lock:
                if chat_id not in logged_out_accounts:
                    logged_out_accounts[chat_id] = set()
                logged_out_accounts[chat_id].add(email_to_logout)
        for store in [user_data_store, user_sessions, user_numbered_tasks,
                      auto_hunt_status, hunt_mode, last_take_time]:
            store.pop(chat_id, None)
        try:
            bot.edit_message_text(
                "🚪 **تم تسجيل الخروج بنجاح**",
                chat_id, message_id,
                reply_markup=get_auth_menu(chat_id),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif data == "back_main":
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(
                get_main_menu_text(), chat_id, message_id,
                reply_markup=get_main_menu(chat_id)
            )
        except Exception:
            pass

    elif data == "view_tasks":
        bot.answer_callback_query(call.id)
        creds = user_data_store.get(chat_id)
        if not creds:
            try:
                bot.edit_message_text(
                    "⚠️ يرجى تسجيل الدخول أولاً.",
                    chat_id, message_id,
                    reply_markup=get_auth_menu(chat_id)
                )
            except Exception:
                pass
            return
        try:
            bot.edit_message_text("⏳ جارٍ جلب المهام...", chat_id, message_id)
        except Exception:
            pass

        def _do_view():
            result, status = get_site_data(creds['email'], creds['password'], chat_id)
            if status == "SUCCESS":
                msg = (f"💰 **الرصيد:** `{result['balance']}` RUB\n\n"
                       f"📌 **المهام الصالحة:**\n")
                if result['tasks']:
                    for i, t in enumerate(result['tasks'][:10], 1):
                        restricted_icon = "🔒" if t['is_restricted'] == "مقيدة" else "🌐"
                        msg += (f"🔢 {i} ➖ {t['price']} RUB"
                                f" | {t['duration']}"
                                f" | {t['app_name']}"
                                f" {restricted_icon}\n")
                else:
                    msg += "🟢 لا توجد مهام صالحة حالياً.\n"
                msg += (f"\n📊 **الإحصائيات:**\n"
                        f"🟡 قيد التنفيذ: {result['stats']['to_execute']}\n"
                        f"🔵 قيد المراجعة: {result['stats']['on_check']}\n"
                        f"✅ مكتملة: {result['stats']['completed']}")
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔄 تحديث", callback_data="view_tasks"))
                markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
                try:
                    bot.edit_message_text(msg, chat_id, message_id,
                                         parse_mode="Markdown", reply_markup=markup)
                except Exception:
                    bot.send_message(chat_id, msg,
                                     parse_mode="Markdown", reply_markup=markup)
            else:
                err_markup = types.InlineKeyboardMarkup()
                err_markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
                try:
                    bot.edit_message_text("⚠️ فشل جلب البيانات.",
                                          chat_id, message_id, reply_markup=err_markup)
                except Exception:
                    pass

        threading.Thread(target=_do_view, daemon=True).start()

    elif data == "take_work_menu":
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(
                "⚡ **خيارات اصطحاب المهام**\nــــــــــــــــــ",
                chat_id, message_id,
                reply_markup=get_take_work_menu(chat_id),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif data == "toggle_gt":
        bot.answer_callback_query(call.id)
        current_active = auto_hunt_status.get(chat_id, False)
        current_mode   = hunt_mode.get(chat_id, "")

        if current_active and current_mode == "GT":
            auto_hunt_status[chat_id] = False
            status_msg = "🔴 تم إيقاف تصيد (أكبر من ساعتين) لجميع الحسابات المحفوظة"
        else:
            auto_hunt_status[chat_id] = True
            hunt_mode[chat_id] = "GT"
            status_msg = "✅ تم تفعيل تصيد (أكبر من ساعتين) لجميع الحسابات المحفوظة"

        saved_accounts = get_saved_multi_accounts(chat_id)
        for acc in saved_accounts:
            sync_chat_settings_to_email(chat_id, acc['email'])

        try:
            bot.edit_message_text(
                f"⚡ **اصطحاب العمل**\n{status_msg}\nــــــــــــــــــ",
                chat_id, message_id,
                reply_markup=get_take_work_menu(chat_id),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif data == "toggle_gte":
        bot.answer_callback_query(call.id)
        current_active = auto_hunt_status.get(chat_id, False)
        current_mode   = hunt_mode.get(chat_id, "")

        if current_active and current_mode == "GTE":
            auto_hunt_status[chat_id] = False
            status_msg = "🔴 تم إيقاف تصيد (ساعتين فما فوق) لجميع الحسابات المحفوظة"
        else:
            auto_hunt_status[chat_id] = True
            hunt_mode[chat_id] = "GTE"
            status_msg = "✅ تم تفعيل تصيد (ساعتين فما فوق) لجميع الحسابات المحفوظة"

        saved_accounts = get_saved_multi_accounts(chat_id)
        for acc in saved_accounts:
            sync_chat_settings_to_email(chat_id, acc['email'])

        try:
            bot.edit_message_text(
                f"⚡ **اصطحاب العمل**\n{status_msg}\nــــــــــــــــــ",
                chat_id, message_id,
                reply_markup=get_take_work_menu(chat_id),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    # ✅ معالجة زر USER - PROXY
    elif data == "proxy_info":
        bot.answer_callback_query(call.id)
        msg = (
            "🔑 **معلومات البروكسي الحالية**\n\n"
            f"👤 **اسم المستخدم:** `{PROXY_USER}`\n"
            f"🔒 **كلمة المرور:** `{PROXY_PASS}`\n"
            "ــــــــــــــــــ"
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("✏️ تغيير البيانات", callback_data="change_proxy"))
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
        try:
            bot.edit_message_text(msg, chat_id, message_id,
                                  parse_mode="Markdown", reply_markup=markup)
        except Exception:
            pass

    # ✅ معالجة زر تغيير البروكسي
    elif data == "change_proxy":
        bot.answer_callback_query(call.id)
        if chat_id in user_transient_messages:
            try:
                bot.delete_message(chat_id, user_transient_messages[chat_id])
            except Exception:
                pass
        msg = bot.send_message(chat_id, "📝 أدخل **اسم المستخدم الجديد** للبروكسي:")
        user_transient_messages[chat_id] = msg.message_id
        user_sessions[chat_id] = {'step': 'CHANGE_PROXY_USER'}

# ==========================================
# 📨 معالجة الرسائل
# ==========================================
@bot.message_handler(func=lambda message: True)
def handle_bot_logic(message):
    try:
        _handle_message_inner(message)
    except Exception as err:
        print(f"[MESSAGE] خطأ: {err}")
        try:
            bot.send_message(message.chat.id, "⚠️ حدث خطأ، حاول مجدداً.")
        except Exception:
            pass

def _handle_message_inner(message):
    chat_id = message.chat.id
    text    = message.text.strip() if message.text else ""

    if text.lower() not in ["/start", "start"]:
        try:
            bot.delete_message(chat_id, message.message_id)
        except Exception:
            pass

    if text.lower() in ["/start", "start"]:
        remove_kb = types.ReplyKeyboardRemove()
        if chat_id in user_data_store or get_saved_multi_accounts(chat_id):
            bot.send_message(chat_id, "مرحباً ⚙️", reply_markup=remove_kb)
            bot.send_message(chat_id, get_main_menu_text(),
                             reply_markup=get_main_menu(chat_id))
        else:
            bot.send_message(chat_id, "مرحباً.", reply_markup=remove_kb)
            bot.send_message(chat_id, "⚙️ سجّل الدخول للبدء:",
                             reply_markup=get_auth_menu(chat_id))
        return

    if chat_id in user_sessions:
        step = user_sessions[chat_id]['step']

        if step == 'WAITING_EMAIL':
            if chat_id in user_transient_messages:
                try:
                    bot.delete_message(chat_id, user_transient_messages[chat_id])
                except Exception:
                    pass
            user_sessions[chat_id]['email'] = text
            user_sessions[chat_id]['step']  = 'WAITING_PASSWORD'
            msg = bot.send_message(chat_id, "🔐 أدخل كلمة المرور:")
            user_transient_messages[chat_id] = msg.message_id
            return

        elif step == 'WAITING_PASSWORD':
            if chat_id in user_transient_messages:
                try:
                    bot.delete_message(chat_id, user_transient_messages[chat_id])
                except Exception:
                    pass
            email    = user_sessions[chat_id]['email']
            password = text
            del user_sessions[chat_id]
            email_lower = email.lower().strip()

            status_msg = bot.send_message(chat_id, "⏳ جاري التحقق من الحساب...")
            session = get_authenticated_session(email, password, chat_id)
            try:
                bot.delete_message(chat_id, status_msg.message_id)
            except Exception:
                pass

            if session:
                user_data_store[chat_id] = {'email': email, 'password': password}
                save_multi_account(chat_id, email, password)
                register_account_in_active(chat_id, email, password)
                sync_chat_settings_to_email(chat_id, email)
                with auth_sessions_lock:
                    user_auth_sessions[email_lower] = session
                with logged_out_lock:
                    if chat_id in logged_out_accounts:
                        logged_out_accounts[chat_id].discard(email_lower)
                remove_kb = types.ReplyKeyboardRemove()
                bot.send_message(chat_id, "✅", reply_markup=remove_kb)
                bot.send_message(
                    chat_id,
                    "🎉 **تم تسجيل الدخول بنجاح!**\nــــــــــــــــــ",
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(chat_id)
                )
            else:
                bot.send_message(
                    chat_id,
                    "❌ فشل تسجيل الدخول، تأكد من بياناتك.",
                    reply_markup=get_auth_menu(chat_id)
                )
            return

        elif step == 'WAITING_DELETE_ACCOUNT':
            if chat_id in user_transient_messages:
                try:
                    bot.delete_message(chat_id, user_transient_messages[chat_id])
                except Exception:
                    pass
            if text.strip().lower() in ['إلغاء', 'الغاء', 'cancel', 'لا']:
                del user_sessions[chat_id]
                bot.send_message(chat_id, "↩️ تم الإلغاء.",
                                 reply_markup=get_switch_account_menu(chat_id))
                return
            if not text.strip().isdigit():
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ إلغاء",
                                                      callback_data="switch_account_menu"))
                bot.send_message(chat_id, "⚠️ أرسل رقم الحساب فقط:",
                                 parse_mode="Markdown", reply_markup=markup)
                return
            idx   = int(text.strip()) - 1
            saved = get_saved_multi_accounts(chat_id)
            if idx < 0 or idx >= len(saved):
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ إلغاء",
                                                      callback_data="switch_account_menu"))
                bot.send_message(
                    chat_id,
                    f"⚠️ أدخل رقماً بين 1 و {len(saved)}:",
                    parse_mode="Markdown", reply_markup=markup
                )
                return
            del user_sessions[chat_id]
            acc_to_delete = saved[idx]
            email_del     = acc_to_delete['email'].lower().strip()
            label_del     = email_del.split('@')[0]

            with active_accounts_lock:
                if chat_id in active_accounts:
                    active_accounts[chat_id].pop(email_del, None)
            threading.Thread(target=delete_multi_account,
                             args=(chat_id, email_del), daemon=True).start()
            with auth_sessions_lock:
                user_auth_sessions.pop(email_del, None)

            active_email = user_data_store.get(chat_id, {}).get('email', '').lower().strip()
            if active_email == email_del:
                for store in [user_data_store, user_sessions, user_numbered_tasks,
                               auto_hunt_status, hunt_mode, last_take_time]:
                    store.pop(chat_id, None)

            bot.send_message(
                chat_id,
                f"✅ **تم حذف الحساب {label_del} نهائياً**",
                parse_mode="Markdown",
                reply_markup=get_switch_account_menu(chat_id)
            )
            return

        # ✅ معالجة خطوة تغيير اسم مستخدم البروكسي
        elif step == 'CHANGE_PROXY_USER':
            if chat_id in user_transient_messages:
                try:
                    bot.delete_message(chat_id, user_transient_messages[chat_id])
                except Exception:
                    pass
            new_proxy_user = text.strip()
            if not new_proxy_user:
                bot.send_message(chat_id, "⚠️ يجب إدخال اسم مستخدم غير فارغ.")
                return
            user_sessions[chat_id]['new_proxy_user'] = new_proxy_user
            user_sessions[chat_id]['step'] = 'CHANGE_PROXY_PASS'
            msg = bot.send_message(chat_id, "🔐 الآن أدخل **كلمة المرور الجديدة** للبروكسي:")
            user_transient_messages[chat_id] = msg.message_id
            return

        # ✅ معالجة خطوة تغيير كلمة مرور البروكسي
        elif step == 'CHANGE_PROXY_PASS':
            if chat_id in user_transient_messages:
                try:
                    bot.delete_message(chat_id, user_transient_messages[chat_id])
                except Exception:
                    pass
            new_proxy_pass = text.strip()
            if not new_proxy_pass:
                bot.send_message(chat_id, "⚠️ يجب إدخال كلمة مرور غير فارغة.")
                return
            new_proxy_user = user_sessions[chat_id].get('new_proxy_user')
            del user_sessions[chat_id]

            # ✅ تحديث المتغيرات العامة فعلياً
            global PROXY_USER, PROXY_PASS
            PROXY_USER = new_proxy_user
            PROXY_PASS = new_proxy_pass

            bot.send_message(
                chat_id,
                f"✅ **تم تحديث بيانات البروكسي بنجاح!**\n\n"
                f"👤 **اسم المستخدم الجديد:** `{PROXY_USER}`\n"
                f"🔒 **كلمة المرور الجديدة:** `{PROXY_PASS}`",
                parse_mode="Markdown",
                reply_markup=get_main_menu(chat_id)
            )
            return

    if "@" in text and chat_id not in user_data_store:
        if chat_id in user_transient_messages:
            try:
                bot.delete_message(chat_id, user_transient_messages[chat_id])
            except Exception:
                pass
        user_sessions[chat_id] = {'step': 'WAITING_PASSWORD', 'email': text}
        msg = bot.send_message(chat_id, "🔐 أدخل كلمة المرور:")
        user_transient_messages[chat_id] = msg.message_id

# ==========================================
# 🖥️ السيرفر المساعد
# ==========================================
class KeepAliveServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("Bot Running".encode("utf-8"))
    def log_message(self, format, *args):
        pass

def run_uptime_server():
    port = int(os.environ.get("PORT", 10000))
    httpd = HTTPServer(('', port), KeepAliveServer)
    httpd.serve_forever()

def send_crash_alert(reason: str):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    msg = f"🚨 *توقف البوت* 🚨\n🕐 الوقت: `{now}`\n❌ السبب:\n{reason}"
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CAPTCHA_ALERT_CHAT_ID, "text": msg,
                  "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception:
        pass

def watchdog_thread():
    global t_worker
    while True:
        time.sleep(60)
        if not t_worker.is_alive():
            print("[WATCHDOG] background_worker مات — إعادة تشغيل...")
            send_crash_alert("background_worker توقف — تمت إعادة التشغيل")
            t_worker = threading.Thread(target=global_background_worker, daemon=True)
            t_worker.start()

# ==========================================
# 🚀 نقطة الانطلاق
# ==========================================
if __name__ == "__main__":
    print("🚀 تشغيل البوت...")

    t_worker = threading.Thread(target=global_background_worker, daemon=True)
    t_worker.start()

    t_server = threading.Thread(target=run_uptime_server, daemon=True)
    t_server.start()

    t_watchdog = threading.Thread(target=watchdog_thread, daemon=True)
    t_watchdog.start()

    print("✅ البوت يعمل الآن...")
    consecutive_errors = 0

    while True:
        try:
            bot.infinity_polling(
                timeout=30, long_polling_timeout=30,
                restart_on_change=False, none_stop=True,
                interval=0, allowed_updates=None
            )
            consecutive_errors = 0
        except KeyboardInterrupt:
            send_crash_alert("تم إيقاف البوت يدوياً")
            sys.exit(0)
        except Exception as _poll_err:
            consecutive_errors += 1
            error_details = traceback.format_exc()
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            print(f"[POLLING] {now_str} — خطأ #{consecutive_errors}: {_poll_err}")
            send_crash_alert(f"خطأ في polling (#{consecutive_errors}):\n{error_details}")
            wait_time = min(5 * consecutive_errors, 60)
            time.sleep(wait_time)