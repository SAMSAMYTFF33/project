# =====================================================================
# webapp_server.py  —  ملف السيرفر الخاص بـ Web App (API)
# =====================================================================

import hashlib
import hmac
import json
import logging
import os
from urllib.parse import parse_qsl

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


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/api/points", handle_points)
    app.router.add_post("/api/withdraw", handle_withdraw)
    app.router.add_route("OPTIONS", "/api/points", handle_options)
    app.router.add_route("OPTIONS", "/api/withdraw", handle_options)
    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8081"))
    logger.info(f"Web App (API) يعمل على المنفذ {port}")
    web.run_app(build_app(), host="0.0.0.0", port=port)
