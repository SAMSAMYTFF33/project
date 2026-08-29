# =====================================================================
#  webapp_server.py — سيرفر Web App الكامل لـ VORTEX
#  يخدم: واجهة التطبيق + API كامل (نقاط/سحب/مسابقات/روليت/سحوبات)
#  يستخدم نفس مجموعات Firestore الخاصة بالبوت تمامًا
# =====================================================================

import hashlib
import hmac
import json
import logging
import os
import random
import secrets
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qsl

import aiohttp
from aiohttp import web

import firebase_admin
from firebase_admin import credentials, firestore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vortex_webapp")

# ---------------------------------------------------------------------
# الإعدادات (التوكن + Firebase)
# ---------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError("ضع متغير البيئة BOT_TOKEN (نفس توكن البوت) قبل التشغيل.")

BOT_USERNAME = "NOP3bot"

FIREBASE_PROJECT_ID = "wep-app-1771a"
FIREBASE_PRIVATE_KEY_ID = "4e6f499aee9cf5a54366a87c45b3760782f43b41"
FIREBASE_CLIENT_EMAIL = "firebase-adminsdk-fbsvc@wep-app-1771a.iam.gserviceaccount.com"
FIREBASE_CLIENT_ID = "105199268649045240747"
FIREBASE_CLIENT_CERT_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/"
    "firebase-adminsdk-fbsvc%40wep-app-1771a.iam.gserviceaccount.com"
)

_raw_private_key = os.environ.get("FIREBASE_PRIVATE_KEY", "")
if "\\n" in _raw_private_key and "\n" not in _raw_private_key:
    _raw_private_key = _raw_private_key.replace("\\n", "\n")
if not _raw_private_key:
    raise RuntimeError("متغير البيئة FIREBASE_PRIVATE_KEY غير موجود أو فارغ.")

FIREBASE_SERVICE_ACCOUNT = {
    "type": "service_account",
    "project_id": FIREBASE_PROJECT_ID,
    "private_key_id": FIREBASE_PRIVATE_KEY_ID,
    "private_key": _raw_private_key,
    "client_email": FIREBASE_CLIENT_EMAIL,
    "client_id": FIREBASE_CLIENT_ID,
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": FIREBASE_CLIENT_CERT_URL,
    "universe_domain": "googleapis.com",
}

DEFAULT_POINTS_TITLE = "🎁 ربح من البوت"
DEFAULT_POINTS_CONDITIONS = (
    "الربح يكون فقط من قسم «إنشاء سحب».\n"
    "كل مستخدم جديد يجتاز منع الرشق ويشارك في السحب يمنح صاحب السحب نقاطًا مرة واحدة فقط."
)
REQUIRED_CHANNEL_DEFAULT = "w33lv"
CAPTCHA_TTL_SECONDS = 10 * 60
CAPTCHA_OPTIONS_COUNT = 3
CAPTCHA_EMOJIS = ["🍎", "🍌", "🍇", "🍉", "🍓", "🍒", "🥝", "🍍", "🥭", "🍑", "🌶️", "🥕"]

# ---------------------------------------------------------------------
# الاتصال بالـ Firestore
# ---------------------------------------------------------------------
_FS_CLIENT = None


def fs_db():
    global _FS_CLIENT
    if _FS_CLIENT is None:
        if not firebase_admin._apps:
            cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT)
            firebase_admin.initialize_app(cred)
        _FS_CLIENT = firestore.client()
    return _FS_CLIENT


def get_setting(key: str) -> str:
    doc = fs_db().collection("settings").document(key).get()
    return doc.to_dict().get("value") if doc.exists else None


def _bump_counter(doc_ref, field: str, amount: int, extra: dict = None):
    """زيادة/خصم ذري لعدّاد رقمي (لا ينزل تحت الصفر)."""
    client = fs_db()
    transaction = client.transaction()

    @firestore.transactional
    def _txn(tx):
        snap = doc_ref.get(transaction=tx)
        current = (snap.to_dict().get(field, 0) if snap.exists else 0) or 0
        payload = dict(extra or {})
        payload[field] = max(0, current + amount)
        tx.set(doc_ref, payload, merge=True)

    _txn(transaction)


# ---------------------------------------------------------------------
# المستخدمون Known Users / الحظر (نفس منطق البوت)
# ---------------------------------------------------------------------
def register_known_user(user: dict) -> bool:
    """يسجّل أول ظهور للمستخدم. يعيد True فقط إذا كان جديدًا كليًا."""
    from google.api_core.exceptions import AlreadyExists
    user_id = user["id"]
    now_iso = datetime.now(timezone.utc).isoformat()
    ref = fs_db().collection("known_bot_users").document(str(user_id))
    username = (user.get("username") or "").lower() or None
    payload = {
        "user_id": user_id,
        "username": username,
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "last_seen_at": now_iso,
    }
    try:
        ref.create({**payload, "first_seen_at": now_iso, "banned": False, "banned_at": None})
        return True
    except AlreadyExists:
        try:
            ref.set(payload, merge=True)
        except Exception:
            pass
        return False


def is_user_banned(user_id: int) -> bool:
    doc = fs_db().collection("known_bot_users").document(str(user_id)).get()
    if not doc.exists:
        return False
    return bool(doc.to_dict().get("banned"))


# ---------------------------------------------------------------------
# النقاط وطلبات السحب
# ---------------------------------------------------------------------
def get_points(owner_id: int) -> int:
    doc = fs_db().collection("owner_points").document(str(owner_id)).get()
    if not doc.exists:
        return 0
    return doc.to_dict().get("points", 0) or 0


def get_user_withdraw_requests(user_id: int):
    docs = fs_db().collection("withdraw_requests").where("user_id", "==", user_id).stream()
    rows = []
    for d in docs:
        data = d.to_dict()
        data["request_id"] = d.id
        rows.append(data)
    rows.sort(key=lambda r: r.get("requested_at") or "", reverse=True)
    return rows


def get_user_latest_withdraw_request(user_id: int):
    rows = get_user_withdraw_requests(user_id)
    return rows[0] if rows else None


def has_pending_withdraw_request(user_id: int) -> bool:
    latest = get_user_latest_withdraw_request(user_id)
    return bool(latest and latest.get("status") == "pending")


def create_withdraw_request(user_id: int, display_name: str, username: str, points_amount: int) -> str:
    client = fs_db()
    ref = client.collection("withdraw_requests").document()
    ref.set({
        "request_id": ref.id,
        "user_id": user_id,
        "display_name": display_name,
        "username": username,
        "points_amount": points_amount,
        "status": "pending",
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "source": "webapp",
    })
    owner_ref = client.collection("owner_points").document(str(user_id))
    _bump_counter(owner_ref, "points", -points_amount, extra={"owner_id": user_id})
    return ref.id


def get_top_channel_points(limit: int = 5):
    """أعلى القنوات بالنقاط (نفس منطق البوت)."""
    client = fs_db()
    candidates = []
    for d in client.collection("channel_points").stream():
        data = d.to_dict() or {}
        if (data.get("points") or 0) <= 0:
            continue
        chat_id = data.get("chat_id")
        rc_doc = client.collection("registered_chats").document(str(chat_id)).get()
        if not rc_doc.exists:
            continue
        rc = rc_doc.to_dict()
        if rc.get("chat_type") != "channel":
            continue
        candidates.append({
            "chat_id": chat_id,
            "points": data.get("points"),
            "chat_title": rc.get("chat_title") or f"قناة {chat_id}",
        })
    candidates.sort(key=lambda r: r.get("points") or 0, reverse=True)
    return candidates[:max(1, min(int(limit), 5))]


# ---------------------------------------------------------------------
# استدعاء Telegram Bot API مباشرة (تحقق الاشتراك / التعزيز / إرسال رسائل)
# ---------------------------------------------------------------------
TG_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
_SUBSCRIPTION_CACHE: dict = {}
SUB_CACHE_TTL = 120
SUB_CACHE_NEG_TTL = 20


async def _tg_call(method: str, params: dict) -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{TG_API_BASE}/{method}", params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
        return data if data.get("ok") else None
    except Exception:
        logger.exception("تعذّر استدعاء %s", method)
        return None


async def tg_get_chat_member_status(chat_ref, user_id: int) -> str:
    data = await _tg_call("getChatMember", {"chat_id": chat_ref, "user_id": user_id})
    if not data:
        return ""
    return (data.get("result") or {}).get("status", "")


async def is_subscribed_to_chat(chat_ref, user_id: int, force_refresh: bool = False) -> bool:
    cache_key = (str(chat_ref), user_id)
    cached = _SUBSCRIPTION_CACHE.get(cache_key)
    if not force_refresh and cached is not None:
        ttl = SUB_CACHE_TTL if cached["value"] else SUB_CACHE_NEG_TTL
        if time.time() - cached["ts"] < ttl:
            return cached["value"]
    status = await tg_get_chat_member_status(chat_ref, user_id)
    value = status in ("member", "administrator", "creator") or status == "restricted"
    _SUBSCRIPTION_CACHE[cache_key] = {"value": value, "ts": time.time()}
    return value


async def has_boosted_channel(chat_id, user_id: int) -> bool:
    data = await _tg_call("getUserChatBoosts", {"chat_id": chat_id, "user_id": user_id})
    if not data:
        return False
    return bool((data.get("result") or {}).get("boosts"))


async def tg_send_message(chat_id, text: str):
    await _tg_call("sendMessage", {"chat_id": chat_id, "text": text})


def get_required_channel_username() -> str:
    return (get_setting("required_channel_username") or REQUIRED_CHANNEL_DEFAULT).lstrip("@")


# ---------------------------------------------------------------------
# المسابقات (contests) — نفس مجموعات Firestore التي يستخدمها البوت
# ---------------------------------------------------------------------
def get_contest(contest_code: str):
    doc = fs_db().collection("contests").document(str(contest_code)).get()
    return doc.to_dict() if doc.exists else None


def count_contest_participants(contest_code: str) -> int:
    docs = fs_db().collection("contest_participants").where("contest_code", "==", contest_code).stream()
    return sum(1 for _ in docs)


def contest_participant_doc_id(contest_code: str, user_id: int) -> str:
    return f"{contest_code}{user_id}"


def get_contest_participant(contest_code: str, user_id: int):
    doc = fs_db().collection("contest_participants").document(
        contest_participant_doc_id(contest_code, user_id)).get()
    return doc.to_dict() if doc.exists else None


def get_participant_by_code(participant_code: str):
    docs = fs_db().collection("contest_participants").where(
        "participant_code", "==", participant_code).limit(1).stream()
    for d in docs:
        return d.to_dict()
    return None


def generate_participant_code(contest_code: str) -> str:
    while True:
        suffix = str(random.randint(1000, 9999))
        code = f"C{contest_code}{suffix}"
        if not get_participant_by_code(code):
            return code


def add_contest_participant(contest_code: str, user_id: int, display_name: str, participant_code: str):
    from google.api_core.exceptions import AlreadyExists
    ref = fs_db().collection("contest_participants").document(
        contest_participant_doc_id(contest_code, user_id))
    try:
        ref.create({
            "contest_code": contest_code,
            "user_id": user_id,
            "display_name": display_name,
            "participant_code": participant_code,
            "channel_message_id": None,
            "joined_at": datetime.now(timezone.utc).isoformat(),
        })
        return True
    except AlreadyExists:
        return False


def get_contest_leaderboard(contest_code: str):
    client = fs_db()
    participants = list(client.collection("contest_participants")
                        .where("contest_code", "==", contest_code).stream())
    votes = list(client.collection("contest_votes")
                 .where("contest_code", "==", contest_code).stream())
    vote_counts: dict = {}
    for v in votes:
        vd = v.to_dict()
        if vd.get("status", "confirmed") != "confirmed":
            continue
        pid = vd.get("participant_user_id")
        vote_counts[pid] = vote_counts.get(pid, 0) + 1
    rows = []
    for p in participants:
        data = p.to_dict()
        uid = data.get("user_id")
        rows.append({
            "user_id": uid,
            "display_name": data.get("display_name") or str(uid),
            "participant_code": data.get("participant_code"),
            "votes": vote_counts.get(uid, 0),
            "joined_at": data.get("joined_at") or "",
        })
    rows.sort(key=lambda r: (-r["votes"], r["joined_at"]))
    return rows


def has_voted(contest_code: str, voter_id: int) -> bool:
    doc = fs_db().collection("contest_votes").document(f"{contest_code}_{voter_id}").get()
    if not doc.exists:
        return False
    return doc.to_dict().get("status", "confirmed") == "confirmed"


def has_voted_for(contest_code: str, voter_id: int, participant_user_id: int) -> bool:
    doc = fs_db().collection("contest_votes").document(f"{contest_code}_{voter_id}").get()
    if not doc.exists:
        return False
    data = doc.to_dict()
    return (data.get("status", "confirmed") == "confirmed"
            and data.get("participant_user_id") == participant_user_id)


def award_contest_owner_points(owner_id: int) -> int:
    if get_setting("points_enabled") != "1":
        return 0
    raw_value = get_setting("points_per_user")
    amount = max(int(raw_value) if raw_value and str(raw_value).isdigit() else 1, 0)
    if amount <= 0:
        return 0
    owner_ref = fs_db().collection("owner_points").document(str(owner_id))
    _bump_counter(owner_ref, "points", amount, extra={"owner_id": owner_id})
    return amount


def register_confirmed_contest_vote(contest_code: str, voter_id: int,
                                    participant_user_id: int, owner_id: int) -> bool:
    ref = fs_db().collection("contest_votes").document(f"{contest_code}_{voter_id}")
    snap = ref.get()
    if snap.exists and snap.to_dict().get("status", "confirmed") == "confirmed":
        return False
    ref.set({
        "contest_code": contest_code,
        "voter_id": voter_id,
        "participant_user_id": participant_user_id,
        "owner_id": owner_id,
        "voted_at": datetime.now(timezone.utc).isoformat(),
        "status": "confirmed",
        "points_awarded": 0,
        "source": "webapp",
    })
    amount = award_contest_owner_points(owner_id)
    if amount:
        ref.update({"points_awarded": amount})
    return True


def contest_display_name(contest: dict) -> str:
    text = (contest.get("cliche_text") or "").strip()
    if text:
        first_line = text.splitlines()[0].strip()
        if len(first_line) > 40:
            first_line = first_line[:40].rstrip() + "…"
        return first_line
    return f"مسابقة #{contest.get('contest_code')}"


# ---------------------------------------------------------------------
# السحوبات (giveaways)
# ---------------------------------------------------------------------
def get_giveaway(gw_code: str):
    doc = fs_db().collection("giveaways").document(str(gw_code)).get()
    return doc.to_dict() if doc.exists else None


def count_giveaway_participants(gw_code: str) -> int:
    docs = fs_db().collection("giveaway_participants").where("gw_code", "==", gw_code).stream()
    return sum(1 for _ in docs)


def is_giveaway_participant(gw_code: str, user_id: int) -> bool:
    doc = fs_db().collection("giveaway_participants").document(f"{gw_code}{user_id}").get()
    return doc.exists


def add_giveaway_participant(gw_code: str, user_id: int, display_name: str, username: str = None) -> bool:
    from google.api_core.exceptions import AlreadyExists
    ref = fs_db().collection("giveaway_participants").document(f"{gw_code}{user_id}")
    try:
        ref.create({
            "gw_code": gw_code,
            "user_id": user_id,
            "display_name": display_name,
            "username": username,
            "joined_at": datetime.now(timezone.utc).isoformat(),
        })
        return True
    except AlreadyExists:
        return False


def reward_giveaway_user(user_id: int, gw_code: str, owner_id: int, chat_id: int) -> bool:
    """منح النقاط مرة واحدة عالميًا لمستخدم جديد (نفس منطق البوت)."""
    from google.api_core.exceptions import AlreadyExists
    if get_setting("points_enabled") != "1":
        return False
    client = fs_db()
    rewarded_ref = client.collection("rewarded_users").document(str(user_id))
    try:
        rewarded_ref.create({
            "user_id": user_id,
            "first_roulette_id": None,
            "first_owner_id": owner_id,
            "first_giveaway_code": gw_code,
            "rewarded_at": datetime.now(timezone.utc).isoformat(),
        })
    except AlreadyExists:
        return False
    raw_value = get_setting("points_per_user")
    amount = max(int(raw_value) if raw_value and str(raw_value).isdigit() else 1, 0)
    _bump_counter(client.collection("owner_points").document(str(owner_id)),
                  "points", amount, extra={"owner_id": owner_id})
    _bump_counter(client.collection("channel_points").document(str(chat_id)),
                  "points", amount, extra={
                      "chat_id": chat_id, "owner_id": owner_id,
                      "updated_at": datetime.now(timezone.utc).isoformat(),
                  })
    return True


async def finish_giveaway_auto(gw_code: str):
    """إنهاء السحب تلقائيًا واختيار الفائزين (نسخة ويب مبسّطة)."""
    giveaway = get_giveaway(gw_code)
    if not giveaway or giveaway.get("status") != "open":
        return None
    docs = list(fs_db().collection("giveaway_participants")
                .where("gw_code", "==", gw_code).stream())
    participants = [(d.to_dict().get("user_id"),
                     d.to_dict().get("display_name") or str(d.to_dict().get("user_id")))
                    for d in docs]
    winners_count = giveaway.get("winners_count") or 1
    winners = random.sample(participants, min(winners_count, len(participants))) if participants else []
    fs_db().collection("giveaways").document(gw_code).update({
        "status": "closed",
        "winners": [{"user_id": w[0], "display_name": w[1]} for w in winners],
        "closed_at": datetime.now(timezone.utc).isoformat(),
    })
    # إشعار الفائزين والمالك
    names = "، ".join(w[1] for w in winners) if winners else "لا أحد"
    for uid, name in winners:
        await tg_send_message(uid, f"🎉 مبروك! لقد فزت في السحب #{gw_code} 🏆")
    owner_id = giveaway.get("owner_id")
    if owner_id:
        await tg_send_message(owner_id, f"🏆 انتهى السحب #{gw_code} تلقائيًا!\nالفائز/ون: {names}")
    return winners


# ---------------------------------------------------------------------
# الروليت السريع
# ---------------------------------------------------------------------
def get_roulette(roulette_id):
    doc = fs_db().collection("roulettes").document(str(roulette_id)).get()
    return doc.to_dict() if doc.exists else None


def counted_user_doc_id(user_id: int, roulette_id) -> str:
    return f"{roulette_id}{user_id}"


def is_user_counted(user_id: int, roulette_id) -> bool:
    doc = fs_db().collection("counted_users").document(
        counted_user_doc_id(user_id, int(roulette_id))).get()
    return doc.exists


def count_roulette_participants(roulette_id) -> int:
    docs = fs_db().collection("counted_users").where("roulette_id", "==", int(roulette_id)).stream()
    return sum(1 for _ in docs)


def get_roulette_participants(roulette_id):
    docs = list(fs_db().collection("counted_users")
                .where("roulette_id", "==", int(roulette_id)).stream())
    rows = [d.to_dict() for d in docs]
    rows.sort(key=lambda r: r.get("counted_at") or "")
    return [{"user_id": r["user_id"],
             "display_name": r.get("display_name") or str(r["user_id"])} for r in rows]


def join_roulette_webapp(user_id: int, roulette_id, display_name: str) -> bool:
    from google.api_core.exceptions import AlreadyExists
    ref = fs_db().collection("counted_users").document(
        counted_user_doc_id(user_id, int(roulette_id)))
    try:
        ref.create({
            "user_id": user_id,
            "roulette_id": int(roulette_id),
            "display_name": display_name,
            "counted_at": datetime.now(timezone.utc).isoformat(),
        })
        return False  # ليس مسجلًا مسبقًا
    except AlreadyExists:
        return True


# ---------------------------------------------------------------------
# نظام الكابتشا (منع الرشق) — إيموجي، جلسات في الذاكرة
# ---------------------------------------------------------------------
_CAPTCHA_SESSIONS: dict = {}


def _cleanup_captchas():
    now = time.time()
    for token in [t for t, s in _CAPTCHA_SESSIONS.items()
                  if now - s.get("created_at", 0) > CAPTCHA_TTL_SECONDS]:
        _CAPTCHA_SESSIONS.pop(token, None)


def create_captcha_session() -> dict:
    _cleanup_captchas()
    correct = random.choice(CAPTCHA_EMOJIS)
    decoys = random.sample([e for e in CAPTCHA_EMOJIS if e != correct], CAPTCHA_OPTIONS_COUNT - 1)
    options = decoys + [correct]
    random.shuffle(options)
    token = secrets.token_hex(6)
    _CAPTCHA_SESSIONS[token] = {
        "correct_index": options.index(correct),
        "created_at": time.time(),
    }
    return {"token": token, "target": correct, "options": options}


def verify_captcha(token: str, chosen_index: int) -> bool:
    session = _CAPTCHA_SESSIONS.get(token)
    if not session:
        return False
    _CAPTCHA_SESSIONS.pop(token, None)  # تُستخدم مرة واحدة فقط
    if time.time() - session.get("created_at", 0) > CAPTCHA_TTL_SECONDS:
        return False
    return chosen_index == session["correct_index"]


# ---------------------------------------------------------------------
# أمان: التحقق من توقيع Telegram initData
# ---------------------------------------------------------------------
def verify_init_data(init_data: str) -> dict | None:
    if not init_data:
        return None
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(key=b"WebAppData", msg=BOT_TOKEN.encode(),
                          digestmod=hashlib.sha256).digest()
    computed_hash = hmac.new(key=secret_key, msg=data_check_string.encode(),
                             digestmod=hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed_hash, received_hash):
        return None
    user_raw = parsed.get("user")
    if not user_raw:
        return None
    try:
        return json.loads(user_raw)
    except ValueError:
        return None


WEBAPP_ALLOWED_ORIGIN = "*"


def json_response(payload: dict, status: int = 200) -> web.Response:
    resp = web.json_response(payload, status=status)
    resp.headers["Access-Control-Allow-Origin"] = WEBAPP_ALLOWED_ORIGIN
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


async def handle_options(request: web.Request) -> web.Response:
    return json_response({})


def _auth(request, body: dict | None = None):
    """تحقق موحّد: يعيد (user, error_response)."""
    init_data = (body or {}).get("initData") or request.query.get("initData", "")
    user = verify_init_data(init_data)
    if not user:
        return None, json_response({"error": "unauthorized"}, 401)
    if is_user_banned(user["id"]):
        return None, json_response({"error": "banned"}, 403)
    register_known_user(user)
    return user, None


# =====================================================================
#  الـ Handlers
# =====================================================================

# ------------------------- الإعدادات العامة -------------------------
async def handle_config(request: web.Request) -> web.Response:
    return json_response({
        "brand": "𝚁𝙾𝚄𝙻𝙴𝚃𝚃𝙴 𝚅𝙾𝚁𝚃𝙴𝚇",
        "required_channel": get_required_channel_username(),
        "points_enabled": get_setting("points_enabled") == "1",
    })


# ------------------------------- النقاط ------------------------------
async def handle_points(request: web.Request) -> web.Response:
    user, err = _auth(request)
    if err:
        return err
    user_id = user["id"]
    pts = get_points(user_id)
    required = int(get_setting("points_required") or "0")
    latest = get_user_latest_withdraw_request(user_id)
    pending = has_pending_withdraw_request(user_id)
    return json_response({
        "points": pts,
        "required": required,
        "eligible": (required > 0 and pts >= required and not pending),
        "pending": pending,
        "title": get_setting("points_title") or DEFAULT_POINTS_TITLE,
        "conditions": get_setting("points_conditions") or DEFAULT_POINTS_CONDITIONS,
        "latest_request": {
            "points_amount": latest.get("points_amount", 0),
            "status": latest.get("status"),
        } if latest else None,
    })


async def handle_withdraw(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        body = {}
    user, err = _auth(request, body)
    if err:
        return err
    user_id = user["id"]
    username = user.get("username")
    if not username:
        return json_response({"error": "username_required"}, 400)
    if has_pending_withdraw_request(user_id):
        return json_response({"error": "already_pending"}, 409)
    required = int(get_setting("points_required") or "0")
    pts = get_points(user_id)
    if required <= 0 or pts < required:
        return json_response({"error": "not_eligible"}, 400)
    display_name = user.get("first_name") or username
    request_id = create_withdraw_request(user_id, display_name, username, pts)
    await tg_send_message(
        7638322813,  # POINTS_ADMIN_ID
        f"💳 طلب سحب جديد من الويب\n👤 {display_name} (ID: {user_id})\n"
        f"🔗 @{username}\n💎 النقاط: {pts}",
    )
    return json_response({"ok": True, "request_id": request_id, "points_amount": pts})


# ----------------------------- لوحة الترتيب --------------------------
async def handle_leaderboard(request: web.Request) -> web.Response:
    user, err = _auth(request)
    if err:
        return err
    return json_response({"channels": get_top_channel_points(5)})


# ------------------------------ الكابتشا -----------------------------
async def handle_captcha_new(request: web.Request) -> web.Response:
    user, err = _auth(request)
    if err:
        return err
    return json_response(create_captcha_session())


# ------------------------------ المسابقات ----------------------------
async def handle_contest_detail(request: web.Request) -> web.Response:
    user, err = _auth(request)
    if err:
        return err
    user_id = user["id"]
    contest = get_contest(request.match_info["code"])
    if not contest:
        return json_response({"error": "not_found"}, 404)
    leaderboard = get_contest_leaderboard(contest["contest_code"])
    my_participation = get_contest_participant(contest["contest_code"], user_id)
    return json_response({
        "contest_code": contest["contest_code"],
        "title": contest_display_name(contest),
        "status": contest.get("status"),
        "target_count": contest.get("target_count"),
        "participants_count": len(leaderboard),
        "premium_only": bool(contest.get("premium_only")),
        "leaderboard": [
            {"user_id": r["user_id"], "display_name": r["display_name"],
             "votes": r["votes"], "is_me": r["user_id"] == user_id}
            for r in leaderboard
        ],
        "my_participation": {
            "display_name": my_participation.get("display_name"),
            "participant_code": my_participation.get("participant_code"),
        } if my_participation else None,
        "has_voted": has_voted(contest["contest_code"], user_id),
        "is_premium": bool(user.get("is_premium")),
    })


async def handle_contest_join(request: web.Request) -> web.Response:
    code = request.match_info["code"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    user, err = _auth(request, body)
    if err:
        return err
    user_id = user["id"]
    contest = get_contest(code)
    if not contest:
        return json_response({"error": "not_found"}, 404)
    if contest.get("status") != "open":
        return json_response({"error": "contest_closed"}, 400)
    existing = get_contest_participant(code, user_id)
    if existing:
        return json_response({"ok": True, "already": True,
                              "participant_code": existing.get("participant_code")})
    if count_contest_participants(code) >= contest.get("target_count", 0):
        return json_response({"error": "full"}, 400)
    # شرط ضمني: الاشتراك في قناة المسابقة نفسها
    chat_id = contest.get("chat_id")
    if chat_id and not await is_subscribed_to_chat(chat_id, user_id, force_refresh=True):
        return json_response({"error": "channel_subscription_required"}, 403)
    display_name = user.get("first_name") or user.get("username") or str(user_id)
    participant_code = generate_participant_code(code)
    add_contest_participant(code, user_id, display_name, participant_code)
    return json_response({"ok": True, "already": False, "participant_code": participant_code})


async def handle_contest_vote(request: web.Request) -> web.Response:
    code = request.match_info["code"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    user, err = _auth(request, body)
    if err:
        return err
    user_id = user["id"]
    try:
        participant_id = int(body.get("participant_id"))
    except (TypeError, ValueError):
        return json_response({"error": "bad_request"}, 400)
    contest = get_contest(code)
    if not contest:
        return json_response({"error": "not_found"}, 404)
    if contest.get("status") != "open":
        return json_response({"error": "contest_closed"}, 400)
    if user_id == participant_id:
        return json_response({"error": "self_vote"}, 400)
    if has_voted(code, user_id):
        return json_response({"error": "already_voted"}, 409)
    participant = get_contest_participant(code, participant_id)
    if not participant:
        return json_response({"error": "participant_not_found"}, 404)
    if contest.get("premium_only") and not user.get("is_premium"):
        return json_response({"error": "premium_required"}, 403)
    # القناة الإلزامية
    required_channel = get_required_channel_username()
    if required_channel and not await is_subscribed_to_chat(
            f"@{required_channel}", user_id, force_refresh=True):
        return json_response({"error": "channel_subscription_required",
                              "channel": required_channel}, 403)
    # قناة المسابقة نفسها
    chat_id = contest.get("chat_id")
    if chat_id and not await is_subscribed_to_chat(chat_id, user_id, force_refresh=True):
        return json_response({"error": "contest_channel_required"}, 403)
    # الكابتشا إلزامية قبل احتساب الصوت
    if not verify_captcha(body.get("captcha_token", ""), int(body.get("captcha_index", -1))):
        return json_response({"error": "captcha_failed"}, 400)
    registered = register_confirmed_contest_vote(
        code, user_id, participant_id, contest.get("owner_id"))
    if not registered:
        return json_response({"error": "already_voted"}, 409)
    return json_response({"ok": True, "leaderboard": get_contest_leaderboard(code)})


# ------------------------------- السحوبات ----------------------------
def _giveaway_public(giveaway: dict, user_id: int) -> dict:
    code = giveaway["gw_code"]
    return {
        "gw_code": code,
        "status": giveaway.get("status"),
        "winners_count": giveaway.get("winners_count") or 1,
        "participants_count": count_giveaway_participants(code),
        "premium_only": bool(giveaway.get("premium_only")),
        "boost_required": bool(giveaway.get("boost_required")),
        "antispam": bool(giveaway.get("antispam")),
        "has_conditions": bool(giveaway.get("condition_channels")),
        "vote_required": bool(giveaway.get("vote_contest_code") and giveaway.get("vote_participant_id")),
        "cliche_text": giveaway.get("cliche_text") or "",
        "already_joined": is_giveaway_participant(code, user_id),
    }


async def handle_giveaway_detail(request: web.Request) -> web.Response:
    user, err = _auth(request)
    if err:
        return err
    giveaway = get_giveaway(request.match_info["code"])
    if not giveaway:
        return json_response({"error": "not_found"}, 404)
    return json_response(_giveaway_public(giveaway, user["id"]))


async def handle_giveaway_join(request: web.Request) -> web.Response:
    code = request.match_info["code"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    user, err = _auth(request, body)
    if err:
        return err
    user_id = user["id"]
    giveaway = get_giveaway(code)
    if not giveaway or giveaway.get("status") != "open":
        return json_response({"error": "giveaway_closed"}, 400)
    if is_giveaway_participant(code, user_id):
        return json_response({"ok": True, "already": True})
    # 1) بريميوم
    if giveaway.get("premium_only") and not user.get("is_premium"):
        return json_response({"error": "premium_required"}, 403)
    # 2) قناة استضافة السحب
    host_chat = giveaway.get("chat_id")
    if host_chat and not await is_subscribed_to_chat(host_chat, user_id, force_refresh=True):
        return json_response({"error": "host_channel_required"}, 403)
    # 3) قنوات الشرط الإضافية
    for ch in (giveaway.get("condition_channels") or [])[:2]:
        ref = ch.get("ref")
        if ref and not await is_subscribed_to_chat(ref, user_id, force_refresh=True):
            return json_response({"error": "condition_channel_required",
                                  "channel": ch.get("title") or str(ref)}, 403)
    # 4) تعزيز القناة
    if giveaway.get("boost_required") and host_chat:
        if not await has_boosted_channel(host_chat, user_id):
            return json_response({"error": "boost_required"}, 403)
    # 5) شرط التصويت لمتسابق
    vote_code = giveaway.get("vote_contest_code")
    vote_pid = giveaway.get("vote_participant_id")
    if vote_code and vote_pid and not has_voted_for(vote_code, user_id, vote_pid):
        return json_response({"error": "vote_required"}, 403)
    # 6) الكابتشا (منع الرشق)
    is_new_user = register_known_user(user)
    if giveaway.get("antispam"):
        if not verify_captcha(body.get("captcha_token", ""), int(body.get("captcha_index", -1))):
            return json_response({"error": "captcha_failed"}, 400)
    display_name = user.get("first_name") or user.get("username") or str(user_id)
    added = add_giveaway_participant(code, user_id, display_name, user.get("username"))
    if not added:
        return json_response({"ok": True, "already": True})
    # منح النقاط لمستخدم جديد
    if giveaway.get("antispam") and is_new_user:
        reward_giveaway_user(user_id, code, giveaway.get("owner_id"), host_chat)
    total = count_giveaway_participants(code)
    # إشعار المالك
    owner_id = giveaway.get("owner_id")
    if owner_id:
        await tg_send_message(
            owner_id,
            f"👤 مشارك جديد في سحبك #{code} (ويب)\n"
            f"الاسم: {display_name}\nإجمالي المشاركين: {total}",
        )
    # سحب تلقائي عند اكتمال العدد
    if (giveaway.get("autospin_mode") == "count" and giveaway.get("autospin_target")
            and total >= giveaway["autospin_target"]):
        await finish_giveaway_auto(code)
    return json_response({"ok": True, "already": False, "total": total})


# ---------------------------- الروليت السريع -------------------------
async def handle_roulette_detail(request: web.Request) -> web.Response:
    user, err = _auth(request)
    if err:
        return err
    user_id = user["id"]
    roulette = get_roulette(request.match_info["rid"])
    if not roulette:
        return json_response({"error": "not_found"}, 404)
    rid = roulette.get("roulette_id")
    return json_response({
        "roulette_id": rid,
        "status": roulette.get("status"),
        "target_count": roulette.get("target_count"),
        "current_count": count_roulette_participants(rid),
        "participants": get_roulette_participants(rid),
        "already_joined": is_user_counted(user_id, rid),
        "is_owner": roulette.get("owner_id") == user_id,
        "winner": roulette.get("winner"),
    })


async def handle_roulette_join(request: web.Request) -> web.Response:
    rid_raw = request.match_info["rid"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    user, err = _auth(request, body)
    if err:
        return err
    user_id = user["id"]
    roulette = get_roulette(rid_raw)
    if not roulette:
        return json_response({"error": "not_found"}, 404)
    rid = roulette.get("roulette_id")
    if roulette.get("status") not in ("open", "waiting_spin"):
        return json_response({"error": "roulette_closed"}, 400)
    if is_user_counted(user_id, rid):
        return json_response({"ok": True, "already": True,
                              "current_count": count_roulette_participants(rid),
                              "target_count": roulette.get("target_count")})
    if count_roulette_participants(rid) >= roulette.get("target_count", 0):
        return json_response({"error": "full"}, 400)
    display_name = user.get("first_name") or user.get("username") or str(user_id)
    join_roulette_webapp(user_id, rid, display_name)
    return json_response({"ok": True, "already": False,
                          "current_count": count_roulette_participants(rid),
                          "target_count": roulette.get("target_count")})


async def handle_roulette_spin(request: web.Request) -> web.Response:
    rid_raw = request.match_info["rid"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    user, err = _auth(request, body)
    if err:
        return err
    roulette = get_roulette(rid_raw)
    if not roulette:
        return json_response({"error": "not_found"}, 404)
    rid = roulette.get("roulette_id")
    if roulette.get("owner_id") != user["id"]:
        return json_response({"error": "forbidden"}, 403)
    if roulette.get("status") == "closed" and not body.get("respin"):
        return json_response({"error": "already_spun"}, 400)
    participants = get_roulette_participants(rid)
    if len(participants) < 2:
        return json_response({"error": "need_two"}, 400)
    winner = random.choice(participants)
    fs_db().collection("roulettes").document(str(rid)).update({
        "status": "closed",
        "winner": {"user_id": winner["user_id"], "display_name": winner["display_name"]},
        "spun_at": datetime.now(timezone.utc).isoformat(),
    })
    return json_response({"ok": True, "winner": winner})


# =====================================================================
#  بناء التطبيق + الـ Routes
# =====================================================================
def build_app() -> web.Application:
    app = web.Application()

    # واجهة التطبيق
    static_dir = os.path.dirname(os.path.abspath(__file__))
    app.router.add_get("/", lambda r: web.FileResponse(os.path.join(static_dir, "index.html")))
    app.router.add_static("/static/", static_dir)

    # عام
    app.router.add_get("/api/config", handle_config)
    app.router.add_get("/api/captcha/new", handle_captcha_new)
    app.router.add_get("/api/leaderboard", handle_leaderboard)

    # النقاط والسحب
    app.router.add_get("/api/points", handle_points)
    app.router.add_post("/api/withdraw", handle_withdraw)

    # المسابقات
    app.router.add_get("/api/contest/{code}", handle_contest_detail)
    app.router.add_post("/api/contest/{code}/join", handle_contest_join)
    app.router.add_post("/api/contest/{code}/vote", handle_contest_vote)

    # السحوبات
    app.router.add_get("/api/giveaway/{code}", handle_giveaway_detail)
    app.router.add_post("/api/giveaway/{code}/join", handle_giveaway_join)

    # الروليت
    app.router.add_get("/api/roulette/{rid}", handle_roulette_detail)
    app.router.add_post("/api/roulette/{rid}/join", handle_roulette_join)
    app.router.add_post("/api/roulette/{rid}/spin", handle_roulette_spin)

    # OPTIONS لكل الـ POST
    for path in ("/api/withdraw", "/api/contest/{code}/join", "/api/contest/{code}/vote",
                 "/api/giveaway/{code}/join", "/api/roulette/{rid}/join", "/api/roulette/{rid}/spin"):
        app.router.add_route("OPTIONS", path, handle_options)

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8081"))
    logger.info(f"VORTEX Web App يعمل على المنفذ {port}")
    web.run_app(build_app(), host="0.0.0.0", port=port)