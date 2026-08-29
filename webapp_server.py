# =====================================================================
# webapp_server.py  —  ملف السيرفر الخاص بـ Web App (API)
# =====================================================================

import hashlib
import hmac
import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qsl

import aiohttp
from aiohttp import web
import firebase_admin
from firebase_admin import credentials, firestore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vortex_webapp")

# ---------------------------------------------------------------------
# إعدادات التوكن ومفتاح Firebase من متغيرات البيئة
# ---------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError("ضع متغير البيئة BOT_TOKEN (نفس توكن البوت) قبل التشغيل.")

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


def is_user_banned(user_id: int) -> bool:
    doc = fs_db().collection("known_bot_users").document(str(user_id)).get()
    if not doc.exists:
        return False
    return bool(doc.to_dict().get("banned"))


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
    from datetime import datetime, timezone
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
    })
    owner_ref = client.collection("owner_points").document(str(user_id))
    transaction = client.transaction()

    @firestore.transactional
    def _bump(tx):
        snap = owner_ref.get(transaction=tx)
        current = (snap.to_dict() or {}).get("points", 0) if snap.exists else 0
        new_val = max(0, current - points_amount)
        tx.set(owner_ref, {"points": new_val, "owner_id": user_id}, merge=True)

    _bump(transaction)
    return ref.id


# ---------------------------------------------------------------------
# استدعاء Telegram Bot API مباشرة (للتحقق من الاشتراك في القنوات)
# ---------------------------------------------------------------------
TG_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
_SUBSCRIPTION_CACHE: dict = {}
SUB_CACHE_TTL = 120          # ثواني كاش النتيجة الإيجابية (مشترك)
SUB_CACHE_NEG_TTL = 20       # ثواني كاش النتيجة السلبية (غير مشترك)


async def tg_get_chat_member_status(chat_ref, user_id: int) -> str:
    """يستدعي getChatMember مباشرة عبر HTTP ويعيد status ("member",
    "administrator", "creator", "restricted", "left", "kicked") أو "" عند الفشل."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{TG_API_BASE}/getChatMember",
                params={"chat_id": chat_ref, "user_id": user_id},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                data = await resp.json()
    except Exception:
        logger.exception("تعذّر استدعاء getChatMember لـ %s / %s", chat_ref, user_id)
        return ""
    if not data.get("ok"):
        return ""
    result = data.get("result") or {}
    return result.get("status", "")


async def is_subscribed_to_chat(chat_ref, user_id: int, force_refresh: bool = False) -> bool:
    cache_key = (str(chat_ref), user_id)
    cached = _SUBSCRIPTION_CACHE.get(cache_key)
    if not force_refresh and cached is not None:
        ttl = SUB_CACHE_TTL if cached["value"] else SUB_CACHE_NEG_TTL
        if time.time() - cached["ts"] < ttl:
            return cached["value"]
    status = await tg_get_chat_member_status(chat_ref, user_id)
    value = status in ("member", "administrator", "creator", "restricted")
    _SUBSCRIPTION_CACHE[cache_key] = {"value": value, "ts": time.time()}
    return value


def get_required_channel_username() -> str:
    return get_setting("required_channel_username") or ""


# ---------------------------------------------------------------------
# بيانات المسابقات (contests) — نفس مجموعات Firestore التي يستخدمها البوت
# ---------------------------------------------------------------------
def get_contest(contest_code: str):
    doc = fs_db().collection("contests").document(str(contest_code)).get()
    return doc.to_dict() if doc.exists else None


def count_contest_participants(contest_code: str) -> int:
    docs = fs_db().collection("contest_participants").where("contest_code", "==", contest_code).stream()
    return sum(1 for _ in docs)


def _contest_participant_doc_id(contest_code: str, user_id: int) -> str:
    return f"{contest_code}_{user_id}"


def get_contest_participant(contest_code: str, user_id: int):
    doc = fs_db().collection("contest_participants").document(
        _contest_participant_doc_id(contest_code, user_id)
    ).get()
    return doc.to_dict() if doc.exists else None


def get_participant_by_code(participant_code: str):
    docs = fs_db().collection("contest_participants").where(
        "participant_code", "==", participant_code
    ).limit(1).stream()
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
    ref = fs_db().collection("contest_participants").document(
        _contest_participant_doc_id(contest_code, user_id)
    )
    ref.set({
        "contest_code": contest_code,
        "user_id": user_id,
        "display_name": display_name,
        "participant_code": participant_code,
        "channel_message_id": None,
        "joined_at": datetime.now(timezone.utc).isoformat(),
    })


def get_contest_leaderboard(contest_code: str):
    client = fs_db()
    participants = list(client.collection("contest_participants").where("contest_code", "==", contest_code).stream())
    votes = list(client.collection("contest_votes").where("contest_code", "==", contest_code).stream())
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


def award_contest_owner_points(owner_id: int) -> int:
    if get_setting("points_enabled") != "1":
        return 0
    raw_value = get_setting("points_per_user")
    amount = max(int(raw_value) if raw_value and str(raw_value).isdigit() else 1, 0)
    if amount <= 0:
        return 0
    owner_ref = fs_db().collection("owner_points").document(str(owner_id))
    client = fs_db()
    transaction = client.transaction()

    @firestore.transactional
    def _bump(tx):
        snap = owner_ref.get(transaction=tx)
        current = (snap.to_dict() or {}).get("points", 0) if snap.exists else 0
        tx.set(owner_ref, {"points": current + amount, "owner_id": owner_id}, merge=True)

    _bump(transaction)
    return amount


def register_confirmed_contest_vote(contest_code: str, voter_id: int, participant_user_id: int, owner_id: int) -> bool:
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
# بيانات الروليت السريع (quick roulette)
# ---------------------------------------------------------------------
def get_roulette(roulette_id):
    doc = fs_db().collection("roulettes").document(str(roulette_id)).get()
    return doc.to_dict() if doc.exists else None


def _counted_user_doc_id(user_id: int, roulette_id) -> str:
    return f"{roulette_id}_{user_id}"


def is_user_counted(user_id: int, roulette_id) -> bool:
    doc = fs_db().collection("counted_users").document(_counted_user_doc_id(user_id, roulette_id)).get()
    return doc.exists


def count_roulette_participants(roulette_id) -> int:
    docs = fs_db().collection("counted_users").where("roulette_id", "==", int(roulette_id)).stream()
    return sum(1 for _ in docs)


def get_roulette_participants(roulette_id):
    docs = list(fs_db().collection("counted_users").where("roulette_id", "==", int(roulette_id)).stream())
    rows = [d.to_dict() for d in docs]
    rows.sort(key=lambda r: r.get("counted_at") or "")
    return [{"user_id": r["user_id"], "display_name": r.get("display_name") or str(r["user_id"])} for r in rows]


def join_roulette_webapp(user_id: int, roulette_id, display_name: str):
    from google.api_core.exceptions import AlreadyExists
    client = fs_db()
    roulette_id_int = int(roulette_id)
    ref = client.collection("counted_users").document(_counted_user_doc_id(user_id, roulette_id_int))
    try:
        ref.create({
            "user_id": user_id,
            "roulette_id": roulette_id_int,
            "display_name": display_name,
            "counted_at": datetime.now(timezone.utc).isoformat(),
        })
        already = False
    except AlreadyExists:
        already = True
    return already


# ---------------------------------------------------------------------
# بيانات السحوبات (giveaways) — نفس مجموعات Firestore التي يستخدمها البوت
# ---------------------------------------------------------------------
def get_giveaway(gw_code: str):
    doc = fs_db().collection("giveaways").document(str(gw_code)).get()
    return doc.to_dict() if doc.exists else None


def count_giveaway_participants(gw_code: str) -> int:
    docs = fs_db().collection("giveaway_participants").where("gw_code", "==", gw_code).stream()
    return sum(1 for _ in docs)


def _giveaway_participant_doc_id(gw_code: str, user_id: int) -> str:
    return f"{gw_code}_{user_id}"


def is_giveaway_participant(gw_code: str, user_id: int) -> bool:
    doc = fs_db().collection("giveaway_participants").document(
        _giveaway_participant_doc_id(gw_code, user_id)
    ).get()
    return doc.exists


def add_giveaway_participant(gw_code: str, user_id: int, display_name: str, username: str = None) -> bool:
    from google.api_core.exceptions import AlreadyExists
    ref = fs_db().collection("giveaway_participants").document(_giveaway_participant_doc_id(gw_code, user_id))
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


def giveaway_display_name(giveaway: dict) -> str:
    text = (giveaway.get("cliche_text") or "").strip()
    if text:
        first_line = text.splitlines()[0].strip()
        if len(first_line) > 40:
            first_line = first_line[:40].rstrip() + "…"
        return first_line
    return f"سحب #{giveaway.get('gw_code')}"


def has_voted_for(contest_code: str, voter_id: int, participant_user_id: int) -> bool:
    """يتحقق من أن المستخدم صوّت تحديدًا لهذا المتسابق — يُستخدم لشرط «تصويت
    متسابق» قبل السماح بالمشاركة في سحب. مطابق لدالة البوت الأصلية."""
    if not contest_code or not participant_user_id:
        return False
    doc = fs_db().collection("contest_votes").document(f"{contest_code}_{voter_id}").get()
    if not doc.exists:
        return False
    data = doc.to_dict()
    return (
        data.get("status", "confirmed") == "confirmed"
        and data.get("participant_user_id") == participant_user_id
    )


async def tg_user_has_boosted_chat(chat_id, user_id: int) -> bool:
    """يستدعي getUserChatBoosts مباشرة عبر HTTP للتحقق من أن المستخدم قد
    عزّز (Boost) القناة فعليًا."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{TG_API_BASE}/getUserChatBoosts",
                params={"chat_id": chat_id, "user_id": user_id},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                data = await resp.json()
    except Exception:
        logger.exception("تعذّر استدعاء getUserChatBoosts لـ %s / %s", chat_id, user_id)
        return False
    if not data.get("ok"):
        return False
    boosts = (data.get("result") or {}).get("boosts") or []
    return bool(boosts)


async def check_giveaway_requirements(user: dict, giveaway: dict) -> tuple:
    """يطابق ترتيب وشروط check_giveaway_requirements في البوت الأصلي:
    بريميوم -> قناة السحب -> قنوات الشرط -> تعزيز -> تصويت لمتسابق.
    يُعيد (True, "") عند اجتياز كل الشروط، أو (False, كود_الخطأ)."""
    if giveaway.get("premium_only") and not user.get("is_premium"):
        return False, "premium_required"

    chat_id = giveaway.get("chat_id")
    if chat_id and not await is_subscribed_to_chat(chat_id, user["id"], force_refresh=True):
        return False, "host_channel_subscription_required"

    for channel in (giveaway.get("condition_channels") or []):
        ref = channel.get("ref")
        if ref and not await is_subscribed_to_chat(ref, user["id"], force_refresh=True):
            return False, "condition_channel_subscription_required"

    if giveaway.get("boost_required") and chat_id and not await tg_user_has_boosted_chat(chat_id, user["id"]):
        return False, "boost_required"

    vote_contest_code = giveaway.get("vote_contest_code")
    vote_participant_id = giveaway.get("vote_participant_id")
    if vote_contest_code and vote_participant_id and not has_voted_for(
        vote_contest_code, user["id"], vote_participant_id,
    ):
        return False, "vote_required"

    return True, ""


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
    secret_key = hmac.new(key=b"WebAppData", msg=BOT_TOKEN.encode(), digestmod=hashlib.sha256).digest()
    computed_hash = hmac.new(key=secret_key, msg=data_check_string.encode(), digestmod=hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    user_raw = parsed.get("user")
    if not user_raw:
        return None
    try:
        return json.loads(user_raw)
    except ValueError:
        return None


# يسمح بالطلب من صفحة GitHub Pages (سواء بحروف كبيرة أو صغيرة)
WEBAPP_ALLOWED_ORIGIN = "*"


def json_response(payload: dict, status: int = 200) -> web.Response:
    resp = web.json_response(payload, status=status)
    resp.headers["Access-Control-Allow-Origin"] = WEBAPP_ALLOWED_ORIGIN
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


async def handle_options(request: web.Request) -> web.Response:
    return json_response({})


# ---------------------------------------------------------------------
# الـ Endpoints
# ---------------------------------------------------------------------

async def handle_points(request: web.Request) -> web.Response:
    init_data = request.query.get("initData", "")
    user = verify_init_data(init_data)
    if not user:
        return json_response({"error": "unauthorized"}, 401)

    user_id = user["id"]
    if is_user_banned(user_id):
        return json_response({"error": "banned"}, 403)

    pts = get_points(user_id)
    required = int(get_setting("points_required") or "0")
    conditions = get_setting("points_conditions") or DEFAULT_POINTS_CONDITIONS
    title = get_setting("points_title") or DEFAULT_POINTS_TITLE

    latest = get_user_latest_withdraw_request(user_id)
    pending = has_pending_withdraw_request(user_id)

    return json_response({
        "points": pts,
        "required": required,
        "eligible": (required > 0 and pts >= required and not pending),
        "pending": pending,
        "title": title,
        "conditions": conditions,
        "latest_request": {
            "points_amount": latest.get("points_amount", 0),
            "status": latest.get("status"),
        } if latest else None,
    })


async def handle_withdraw(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "bad_request"}, 400)

    user = verify_init_data(body.get("initData", ""))
    if not user:
        return json_response({"error": "unauthorized"}, 401)

    user_id = user["id"]
    username = user.get("username")

    if is_user_banned(user_id):
        return json_response({"error": "banned"}, 403)
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
    return json_response({"ok": True, "request_id": request_id, "points_amount": pts})


# ---------------------------------------------------------------------
# Endpoints: المسابقة والتصويت (contest)
# ---------------------------------------------------------------------
async def handle_contest_detail(request: web.Request) -> web.Response:
    contest_code = request.match_info["code"]
    init_data = request.query.get("initData", "")
    user = verify_init_data(init_data)
    if not user:
        return json_response({"error": "unauthorized"}, 401)

    user_id = user["id"]
    if is_user_banned(user_id):
        return json_response({"error": "banned"}, 403)

    contest = get_contest(contest_code)
    if not contest:
        return json_response({"error": "not_found"}, 404)

    leaderboard = get_contest_leaderboard(contest_code)
    my_participation = get_contest_participant(contest_code, user_id)
    my_vote = has_voted(contest_code, user_id)

    return json_response({
        "contest_code": contest_code,
        "title": contest_display_name(contest),
        "status": contest.get("status"),
        "target_count": contest.get("target_count"),
        "participants_count": len(leaderboard),
        "premium_only": bool(contest.get("premium_only")),
        "leaderboard": [
            {
                "user_id": r["user_id"],
                "display_name": r["display_name"],
                "votes": r["votes"],
                "is_me": r["user_id"] == user_id,
            }
            for r in leaderboard
        ],
        "my_participation": {
            "display_name": my_participation.get("display_name"),
            "participant_code": my_participation.get("participant_code"),
        } if my_participation else None,
        "has_voted": my_vote,
        "is_premium": bool(user.get("is_premium")),
    })


async def handle_contest_join(request: web.Request) -> web.Response:
    contest_code = request.match_info["code"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    user = verify_init_data(body.get("initData", ""))
    if not user:
        return json_response({"error": "unauthorized"}, 401)

    user_id = user["id"]
    if is_user_banned(user_id):
        return json_response({"error": "banned"}, 403)

    contest = get_contest(contest_code)
    if not contest:
        return json_response({"error": "not_found"}, 404)
    if contest.get("status") != "open":
        return json_response({"error": "contest_closed"}, 400)

    existing = get_contest_participant(contest_code, user_id)
    if existing:
        return json_response({"ok": True, "already": True, "participant_code": existing.get("participant_code")})

    if count_contest_participants(contest_code) >= contest.get("target_count", 0):
        return json_response({"error": "full"}, 400)

    chat_id = contest.get("chat_id")
    if chat_id and not await is_subscribed_to_chat(chat_id, user_id, force_refresh=True):
        return json_response({"error": "channel_subscription_required"}, 403)

    display_name = user.get("first_name") or user.get("username") or str(user_id)
    participant_code = generate_participant_code(contest_code)
    add_contest_participant(contest_code, user_id, display_name, participant_code)
    return json_response({"ok": True, "already": False, "participant_code": participant_code})


async def handle_contest_vote(request: web.Request) -> web.Response:
    contest_code = request.match_info["code"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    user = verify_init_data(body.get("initData", ""))
    if not user:
        return json_response({"error": "unauthorized"}, 401)

    user_id = user["id"]
    if is_user_banned(user_id):
        return json_response({"error": "banned"}, 403)

    try:
        participant_id = int(body.get("participant_id"))
    except (TypeError, ValueError):
        return json_response({"error": "bad_request"}, 400)

    contest = get_contest(contest_code)
    if not contest:
        return json_response({"error": "not_found"}, 404)
    if contest.get("status") != "open":
        return json_response({"error": "contest_closed"}, 400)
    if user_id == participant_id:
        return json_response({"error": "self_vote"}, 400)
    if has_voted(contest_code, user_id):
        return json_response({"error": "already_voted"}, 409)

    participant = get_contest_participant(contest_code, participant_id)
    if not participant:
        return json_response({"error": "participant_not_found"}, 404)

    if contest.get("premium_only") and not user.get("is_premium"):
        return json_response({"error": "premium_required"}, 403)

    required_channel = get_required_channel_username()
    if required_channel and not await is_subscribed_to_chat(f"@{required_channel}", user_id, force_refresh=True):
        return json_response({"error": "channel_subscription_required", "channel": required_channel}, 403)

    owner_id = contest.get("owner_id")
    registered = register_confirmed_contest_vote(contest_code, user_id, participant_id, owner_id)
    if not registered:
        return json_response({"error": "already_voted"}, 409)

    return json_response({"ok": True, "leaderboard": get_contest_leaderboard(contest_code)})


# ---------------------------------------------------------------------
# Endpoints: الروليت السريع (quick roulette)
# ---------------------------------------------------------------------
async def handle_roulette_detail(request: web.Request) -> web.Response:
    roulette_id = request.match_info["rid"]
    init_data = request.query.get("initData", "")
    user = verify_init_data(init_data)
    if not user:
        return json_response({"error": "unauthorized"}, 401)

    user_id = user["id"]
    if is_user_banned(user_id):
        return json_response({"error": "banned"}, 403)

    roulette = get_roulette(roulette_id)
    if not roulette:
        return json_response({"error": "not_found"}, 404)

    return json_response({
        "roulette_id": roulette_id,
        "status": roulette.get("status"),
        "target_count": roulette.get("target_count"),
        "current_count": count_roulette_participants(roulette_id),
        "participants": get_roulette_participants(roulette_id),
        "already_joined": is_user_counted(user_id, roulette_id),
        "is_owner": roulette.get("owner_id") == user_id,
    })


async def handle_roulette_join(request: web.Request) -> web.Response:
    roulette_id = request.match_info["rid"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    user = verify_init_data(body.get("initData", ""))
    if not user:
        return json_response({"error": "unauthorized"}, 401)

    user_id = user["id"]
    if is_user_banned(user_id):
        return json_response({"error": "banned"}, 403)

    roulette = get_roulette(roulette_id)
    if not roulette:
        return json_response({"error": "not_found"}, 404)
    if roulette.get("status") != "open":
        return json_response({"error": "roulette_closed"}, 400)

    if is_user_counted(user_id, roulette_id):
        return json_response({
            "ok": True, "already": True,
            "current_count": count_roulette_participants(roulette_id),
            "target_count": roulette.get("target_count"),
        })

    target = roulette.get("target_count", 0)
    if count_roulette_participants(roulette_id) >= target:
        return json_response({"error": "full"}, 400)

    display_name = user.get("first_name") or user.get("username") or str(user_id)
    join_roulette_webapp(user_id, roulette_id, display_name)

    return json_response({
        "ok": True, "already": False,
        "current_count": count_roulette_participants(roulette_id),
        "target_count": target,
    })


# ---------------------------------------------------------------------
# Endpoints: السحوبات (giveaways)
# ---------------------------------------------------------------------
async def handle_giveaway_detail(request: web.Request) -> web.Response:
    gw_code = request.match_info["code"]
    init_data = request.query.get("initData", "")
    user = verify_init_data(init_data)
    if not user:
        return json_response({"error": "unauthorized"}, 401)

    user_id = user["id"]
    if is_user_banned(user_id):
        return json_response({"error": "banned"}, 403)

    giveaway = get_giveaway(gw_code)
    if not giveaway:
        return json_response({"error": "not_found"}, 404)

    return json_response({
        "gw_code": gw_code,
        "title": giveaway_display_name(giveaway),
        "status": giveaway.get("status"),
        "winners_count": giveaway.get("winners_count", 1),
        "participants_count": count_giveaway_participants(gw_code),
        "premium_only": bool(giveaway.get("premium_only")),
        "boost_required": bool(giveaway.get("boost_required")),
        "already_joined": is_giveaway_participant(gw_code, user_id),
        "is_owner": giveaway.get("owner_id") == user_id,
        "is_premium": bool(user.get("is_premium")),
    })


async def handle_giveaway_join(request: web.Request) -> web.Response:
    gw_code = request.match_info["code"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    user = verify_init_data(body.get("initData", ""))
    if not user:
        return json_response({"error": "unauthorized"}, 401)

    user_id = user["id"]
    if is_user_banned(user_id):
        return json_response({"error": "banned"}, 403)

    giveaway = get_giveaway(gw_code)
    if not giveaway:
        return json_response({"error": "not_found"}, 404)
    if giveaway.get("status") != "open":
        return json_response({"error": "giveaway_closed"}, 400)

    if is_giveaway_participant(gw_code, user_id):
        return json_response({
            "ok": True, "already": True,
            "participants_count": count_giveaway_participants(gw_code),
        })

    ok, reason = await check_giveaway_requirements(user, giveaway)
    if not ok:
        return json_response({"error": reason}, 403)

    display_name = user.get("first_name") or user.get("username") or str(user_id)
    add_giveaway_participant(gw_code, user_id, display_name, user.get("username"))

    return json_response({
        "ok": True, "already": False,
        "participants_count": count_giveaway_participants(gw_code),
    })


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/api/points", handle_points)
    app.router.add_post("/api/withdraw", handle_withdraw)
    app.router.add_route("OPTIONS", "/api/points", handle_options)
    app.router.add_route("OPTIONS", "/api/withdraw", handle_options)

    app.router.add_get("/api/contest/{code}", handle_contest_detail)
    app.router.add_post("/api/contest/{code}/join", handle_contest_join)
    app.router.add_post("/api/contest/{code}/vote", handle_contest_vote)
    app.router.add_route("OPTIONS", "/api/contest/{code}", handle_options)
    app.router.add_route("OPTIONS", "/api/contest/{code}/join", handle_options)
    app.router.add_route("OPTIONS", "/api/contest/{code}/vote", handle_options)

    app.router.add_get("/api/roulette/{rid}", handle_roulette_detail)
    app.router.add_post("/api/roulette/{rid}/join", handle_roulette_join)
    app.router.add_route("OPTIONS", "/api/roulette/{rid}", handle_options)
    app.router.add_route("OPTIONS", "/api/roulette/{rid}/join", handle_options)

    app.router.add_get("/api/giveaway/{code}", handle_giveaway_detail)
    app.router.add_post("/api/giveaway/{code}/join", handle_giveaway_join)
    app.router.add_route("OPTIONS", "/api/giveaway/{code}", handle_options)
    app.router.add_route("OPTIONS", "/api/giveaway/{code}/join", handle_options)
    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8081"))
    logger.info(f"Web App (API) يعمل على المنفذ {port}")
    web.run_app(build_app(), host="0.0.0.0", port=port)
