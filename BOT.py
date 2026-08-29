import os
TOKEN = os.environ.get("BOT_TOKEN", "")
if not TOKEN:
    raise RuntimeError("ضع متغير البيئة BOT_TOKEN (توكن البوت) قبل التشغيل.")
BOT_USERNAME = "NOP3bot"

ADMIN_IDS = [123456789]
POINTS_ADMIN_ID = 7638322813

OWNER_IDS = [POINTS_ADMIN_ID, 8676850552]


def is_owner(user_id: int) -> bool:
    """يتحقق مما إذا كان المستخدم أحد مالكي البوت (OWNER_IDS)."""
    return user_id in OWNER_IDS


async def global_ban_gate(update: "Update", context) -> None:
    """بوابة عامة تمنع أي مستخدم محظور (من قسم إدارة المستخدمين) من استخدام
    البوت إطلاقًا — تعمل على كل الرسائل والأزرار قبل وصولها لأي معالج آخر."""
    user = update.effective_user
    if not user or is_owner(user.id):
        return
    try:
        banned = is_user_banned(user.id)
    except Exception:
        return
    if not banned:
        return
    try:
        if update.callback_query:
            await update.callback_query.answer("🚫 تم حظرك من استخدام هذا البوت.", show_alert=True)
        elif update.message:
            await update.message.reply_text("🚫 تم حظرك من استخدام هذا البوت.")
    except Exception:
        pass
    raise ApplicationHandlerStop


REQUIRED_CHANNEL_USERNAME = "w33lv"
REQUIRED_CHANNEL_URL = "https://t.me/w33lv"
REQUIRED_CHANNEL_BUTTON_TEXT = "VORTEX  𓏺"
REQUIRED_CHANNEL_DEFAULT_TARGET = "1000"

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


import asyncio
import json
import logging
import random
import secrets
import sqlite3
import threading
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
_boot_logger = logging.getLogger("contest_bot.bootstrap")

try:
    import apscheduler
except ImportError:
    _boot_logger.warning("مكتبة JobQueue غير مثبّتة — جارٍ تثبيتها تلقائيًا الآن (مرة واحدة فقط)...")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "--quiet",
            "python-telegram-bot[job-queue]",
        ])
        _boot_logger.warning(
            "تم تثبيت المكتبة بنجاح! سيتابع البوت الإقلاع الآن مباشرة بدون الحاجة لإعادة "
            "التشغيل يدويًا (وإن ظهر خطأ JobQueue رغم هذا، أعد تشغيل السكربت مرة واحدة)."
        )
    except Exception as _exc:
        _boot_logger.error(
            "فشل التثبيت التلقائي (%s). ثبّت يدويًا عبر: "
            "pip install \"python-telegram-bot[job-queue]\" ثم أعد التشغيل.",
            _exc,
        )

try:
    import firebase_admin
except ImportError:
    _boot_logger.warning("مكتبة firebase-admin غير مثبّتة — جارٍ تثبيتها تلقائيًا الآن (مرة واحدة فقط)...")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "--quiet", "firebase-admin",
        ])
        _boot_logger.warning("تم تثبيت firebase-admin بنجاح! يتابع البوت الإقلاع الآن مباشرة.")
    except Exception as _exc:
        _boot_logger.error(
            "فشل التثبيت التلقائي لـ firebase-admin (%s). ثبّت يدويًا عبر: "
            "pip install firebase-admin ثم أعد التشغيل.",
            _exc,
        )

import firebase_admin
from firebase_admin import credentials, firestore

logger = logging.getLogger("contest_bot")

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQueryResultArticle,
    InputTextMessageContent,
    SwitchInlineQueryChosenChat,
    MessageEntity,
    CopyTextButton,
    LabeledPrice,
    BotCommand,
    LinkPreviewOptions,
)
from telegram.error import RetryAfter
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    InlineQueryHandler,
    ChosenInlineResultHandler,
    MessageHandler,
    ChatMemberHandler,
    ContextTypes,
    PreCheckoutQueryHandler,
    ApplicationHandlerStop,
    filters,
)
from telegram.request import HTTPXRequest

DEFAULT_POINTS_TITLE = "🎁 ربح من البوت"
DEFAULT_POINTS_CONDITIONS = (
    "الربح يكون فقط من قسم «إنشاء سحب».\n"
    "كل مستخدم جديد يجتاز منع الرشق ويشارك في السحب يمنح صاحب السحب نقاطًا مرة واحدة فقط."
)
TECH_SUPPORT_USERNAME = "y66vlBOT"
SUPPORT_BOT_STARS_AMOUNT = 5

BRAND_NAME = "𝚁𝙾𝚄𝙻𝙴𝚃𝚃𝙴 𝚅𝙾𝚁𝚃𝙴𝚇"
BRAND_URL = "https://t.me/e_ggf"

GIVEAWAYS_LINK_TEXT = "السحوبات"
GIVEAWAYS_CHANNEL_URL = "https://t.me/n_bbo"

ANNOUNCE_CHANNEL_USERNAME = "n_bbo"
ANNOUNCE_CHANNEL_URL = "https://t.me/n_bbo"
ANNOUNCE_CHANNEL_CHAT_ID = f"@{ANNOUNCE_CHANNEL_USERNAME}"


ROULETTE_COUNTS = [5, 10, 15, 20, 25, 30, 50, 100]

DEFAULT_HIDE_PARTICIPANTS = "1"
DEFAULT_GAME_CLICHE = f"أهلا وسهلا بكم في {BRAND_NAME}"

ROULETTE_THUMBS = {
    n: f"https://wsrv.nl/?url=raw.githubusercontent.com/SAMSAMYTFF33/WEB/main/assets/Number{n}.png&w=100&h=100&output=jpg&q=60&v=2" for n in ROULETTE_COUNTS
}

EMOJI = {
    "trophy_create_draw": "5429387503129875330",
    "roulette": "5102856631562011824",
    "draws_check": "5843596438373667352",
    "chart": "5940378308003762340",
    "doc": "5334882760735598374",
    "remind_check": "5954244021508380732",
    "star": "5346309121794659890",
    "tech": "5814558770075803439",
    "trophy_contest": "5789577921727307070",
    "gear": "5341715473882955310",
    "hand": "5940774295398521609",
    "buoy": "6008036485436022431",
    "arrow_down": "5208903445729266755",
    "remind_on": "5206607081334906820",
    "remind_off": "5210952531676504517",
    "hide_participants_btn": "5332724926216428039",
    "cliche_btn": "5841360920781002031",
    "restore_defaults_btn": "6012661228910939253",
    "back_section_btn": "6039539366177541657",
    "register_plus": "5226945370684140473",
    "target_pin": "5310278924616356636",
    "num_one": "5260562728249996728",
    "num_two": "5260273822979863490",
    "pin_note": "5769520351440540688",
    "arrow_left": "5769534112515756980",
    "envelope_klesha": "5406631276042002796",
    "new_badge": "5895669571058142797",
    "end_question": "5208748474719293821",
    "alarm_clock": "5208413342716153772",
    "votes_chart_btn": "5429651785352501917",
    "alarm_clock_btn": "6217487596486922033",
    "people": "5769289664452104963",
    "bullet_point": "5769338979266597469",
    "target": "5965522064461799191",
    "party": "5370870691140737817",
    "medal": "5789703004059868939",
    "trophy_win": "5789577921727307070",
    "alarm_clock_title": "5215394081911351762",
    "time_option_btn": "5764762214871343251",
    "time_manual_btn": "6046294958892129907",
    "time_custom_btn": "5850317551090800862",
    "back_time_menu_btn": "5390885122775985914",
    "trophy_winners_title": "5429387503129875330",
    "back_winners_btn": "6039539366177541657",
    "confirm_check": "5429381339851796035",
    "notify_win_btn": "5458603043203327669",
    "no_btn": "5954244021508380732",
    "announce_results_btn": "5789428375261023681",
    "approve_participants_label_btn": "6026257381678124710",
    "yes_btn": "5852544431504234283",
    "premium_vote_btn": "5942584147372413048",
    "publish_btn": "5258332798409783582",
    "join_accept_btn": "5767193595857606245",
    "withdraw_btn": "5967594648175121607",
    "sub_laptop": "5769469013696451511",
    "sub_alert": "5769630100739854545",
    "sub_check": "5767193595857606245",
    "recent_contests_btn": "5213334816891631245",
    "seats_change_btn": "5429651785352501917",
    "pause_toggle_btn": "5852544431504234283",
    "edit_settings_refresh_btn": "6012661228910939253",
    "remove_contestant_btn": "5967594648175121607",
    "delete_all_btn": "5913597928487784523",
    "cross_flag_off": "5954244021508380732",
    "check_flag_on": "5429381339851796035",
    "num_three": "5260650672000348972",
    "num_four": "5260544569128269433",
    "num_five": "5260655426529146332",
    "num_six": "5260604105964926035",
    "gw_condition_channel": "6039381989985882045",
    "gw_vote_icon": "5895428924040548238",
    "gw_new_participant": "6032994772321309200",
    "gw_view_profile": "5904630315946611415",
    "gw_kick_btn": "5240241223632954241",
    "gw_atime_lightning": "5965286318001889755",
    "gw_atime_clock": "5852614259082530343",
}

CAPTCHA_EMOJIS = [
    "5402477260982731644",
    "5449449325434266744",
    "5438496463044752972",
    "5456140674028019486",
    "5447410659077661506",
    "5453976908159016299",
    "5454206993852029667",
    "5253984341591076047",
    "5253861243533406038",
    "5408850391154569842",
    "5019726470101075726",
    "5145427681680032825",
]

CAPTCHA_OPTIONS_COUNT = 3
CAPTCHA_SESSION_TTL_SECONDS = 10 * 60

CONTEST_TIME_OPTIONS = [
    [(5, "بعد 5 دقايق"), (1, "بعد 1 دقيقة")],
    [(30, "بعد 30 دقيقة"), (60, "بعد 1 ساعة")],
    [(120, "بعد 2 ساعات"), (180, "بعد 3 ساعات")],
    [(240, "بعد 4 ساعات"), (300, "بعد 5 ساعات")],
    [(360, "بعد 6 ساعات"), (720, "بعد 12 ساعات")],
    [(1440, "بعد 24 ساعة"), (2880, "بعد 48 ساعات")],
    [(4320, "بعد 3 ايام"), (10080, "بعد 1 اسبوع")],
]

def _build_single_back_keyboard(text: str, callback_data: str, style: str, emoji_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            text, callback_data=callback_data,
            style=style, **emoji_kwargs(emoji_key),
        )],
    ])


def build_text_with_emojis(parts) -> tuple:
    """
    تقوم ببناء النص والكيانات (entities) لدعم التنسيقات المتداخلة:
    - كيان CUSTOM_EMOJI للإيموجيات المخصصة.
    - كيان TEXT_MENTION للإشارة إلى مستخدم (عبر user object).
    - كيان TEXT_LINK لإنشاء اسم أزرق قابل للضغط (باستخدام tg://user?id=).
    - كيان BOLD للخط العريض.
    - كيان BLOCKQUOTE للاقتباس الجانبي مع علامة ”.
    جميع الكيانات يمكن دمجها داخل بعضها (مثلاً اسم أزرق داخل اقتباس).
    """
    text = ""
    entities = []

    def add_bold(start_offset: int, end_offset: int):
        """إضافة كيان عريض للنص مع الحفاظ على الكيانات المتداخلة."""
        if end_offset > start_offset:
            entities.append(MessageEntity(
                type=MessageEntity.BOLD,
                offset=start_offset,
                length=end_offset - start_offset,
            ))

    def append_text(value: str, make_bold: bool = True):
        nonlocal text
        start_offset = len(text.encode("utf-16-le")) // 2
        text += str(value)
        end_offset = len(text.encode("utf-16-le")) // 2
        if make_bold:
            add_bold(start_offset, end_offset)

    def process_part(p, inside_bold: bool = False):
        nonlocal text, entities
        if isinstance(p, tuple):
            if len(p) == 3 and p[1] == "mention":
                display_name, _, user_obj = p
                offset = len(text.encode("utf-16-le")) // 2
                length = len(display_name.encode("utf-16-le")) // 2
                entities.append(MessageEntity(type=MessageEntity.TEXT_MENTION, offset=offset, length=length, user=user_obj))
                text += display_name
                if not inside_bold:
                    add_bold(offset, offset + length)
            elif len(p) == 3 and p[1] == "mention_id":
                display_name, _, user_id = p
                offset = len(text.encode("utf-16-le")) // 2
                length = len(display_name.encode("utf-16-le")) // 2
                entities.append(MessageEntity(type=MessageEntity.TEXT_LINK, offset=offset, length=length, url=f"tg://user?id={user_id}"))
                text += display_name
                if not inside_bold:
                    add_bold(offset, offset + length)
            elif len(p) == 2:
                placeholder, custom_emoji_id = p
                offset = len(text.encode("utf-16-le")) // 2
                length = len(placeholder.encode("utf-16-le")) // 2
                entities.append(MessageEntity(type=MessageEntity.CUSTOM_EMOJI, offset=offset, length=length, custom_emoji_id=custom_emoji_id))
                text += placeholder
            elif len(p) == 3 and p[1] in ["bold", "blockquote", "italic", "spoiler"]:
                content, ent_type, _ = p
                start_offset = len(text.encode("utf-16-le")) // 2
                if isinstance(content, list):
                    for sub in content:
                        process_part(sub, inside_bold or ent_type == "bold")
                else:
                    append_text(content, make_bold=inside_bold or ent_type != "bold")
                end_offset = len(text.encode("utf-16-le")) // 2
                length = end_offset - start_offset
                t_type = {
                    "bold": MessageEntity.BOLD,
                    "blockquote": MessageEntity.BLOCKQUOTE,
                    "italic": MessageEntity.ITALIC,
                    "spoiler": MessageEntity.SPOILER,
                }[ent_type]
                entities.append(MessageEntity(type=t_type, offset=start_offset, length=length))
            elif len(p) == 3 and p[1] == "link":
                content, _, url = p
                start_offset = len(text.encode("utf-16-le")) // 2
                if isinstance(content, list):
                    for sub in content:
                        process_part(sub, inside_bold)
                else:
                    append_text(content, make_bold=not inside_bold)
                end_offset = len(text.encode("utf-16-le")) // 2
                length = end_offset - start_offset
                entities.append(MessageEntity(type=MessageEntity.TEXT_LINK, offset=start_offset, length=length, url=url))
            else:
                append_text(p, make_bold=not inside_bold)
        else:
            append_text(p, make_bold=not inside_bold)

    for part in parts:
        process_part(part)

    return text, entities


def build_brand_giveaways_parts(prefix: str = "• "):
    """يبني جزء الجملة الموحّد: «BRAND_NAME < السحوبات» — يُستخدم في القائمة
    الرئيسية وفي منشورات السحوبات والمسابقات. اسم العلامة رابط أزرق يفتح
    {BRAND_URL}، وكلمة «السحوبات» رابط أزرق عريض يفتح {GIVEAWAYS_CHANNEL_URL}.
    كلا الرابطين يُنشئان معاينة رابط صغيرة تلقائيًا من تيليجرام (صورة القناة)."""
    parts = []
    if prefix:
        parts.append(prefix)
    parts.append((BRAND_NAME, "link", BRAND_URL))
    parts.append(" < ")
    parts.append((GIVEAWAYS_LINK_TEXT, "link", GIVEAWAYS_CHANNEL_URL))
    return parts


def bold_notice(message: str) -> tuple:
    """يبني رسالة تنبيه/تأكيد قصيرة بخط عريض — يُستخدم لتوحيد شكل رسائل النظام في البوت."""
    return build_text_with_emojis([([message], "bold", None)])


def emoji_kwargs(key: str) -> dict:
    value = EMOJI.get(key, "0")
    if value and value != "0":
        return {"icon_custom_emoji_id": value}
    return {}

def build_welcome_message(user) -> tuple:
    """
    رسالة الترحيب بالقائمة الرئيسية.

    كلمة VORTEX داخل الجملة الأولى رابط نصي أزرق قابل للضغط يفتح قناة
    العلامة (BRAND_URL)، وكلمة «السحوبات» رابط نصي أزرق قابل للضغط يفتح
    قناة السحوبات المحددة مسبقًا (GIVEAWAYS_CHANNEL_URL) — مدمجتان داخل
    نص الجملة نفسها بدل عرضهما كسطر منفصل («• ROULETTE VORTEX < السحوبات»)
    أعلى الجملتين. الجملتان قريبتان من بعضهما (سطر واحد بينهما) لتظهرا
    متلاصقتين كما في الصورة المرجعية.
    """
    user_name = user.first_name or user.username or "صديقنا"
    vortex_word = BRAND_NAME.split(" ", 1)[-1]  # "𝚅𝙾𝚁𝚃𝙴𝚇"
    parts = [
        ([
            ("👋", EMOJI["hand"]),
            " : أهلاً بك - ",
            (user_name, "mention", user),
            "\n\n",
            ([
                "روليت ", (vortex_word, "link", BRAND_URL),
                " لإنشاء ", (GIVEAWAYS_LINK_TEXT, "link", GIVEAWAYS_CHANNEL_URL),
                " والمسابقات والروليت السريع",
            ], "blockquote", None),
            "\n",
            ([
                "استمتع وابدأ الآن بالاختيار من القائمة أدناه ",
                ("⏬", EMOJI["arrow_down"]),
            ], "blockquote", None),
        ], "bold", None),
    ]
    return build_text_with_emojis(parts)


def build_terms_message() -> tuple:
    """
    رسالة «سياسة الاستخدام والخصوصية»:
    - كامل النص بخط عريض (Bold).
    - السطرين الأخيرين («أي مخالفة = حظر دائم» / «ثقتكم هي أولويتنا») داخل
      اقتباس وردي (Blockquote) منتهي بعلامة ”، تمامًا كما في الصورة المرفقة.
    """
    parts = [
        ([
            ("📜", EMOJI["doc"]),
            " : سياسة الاستخدام والخصوصية",
            "\n\n",
            "ثقتكم هي أولويتنا",
            "\n\n",
            "✅ : المسموح به:\n",
            "├ تنظيم سحوبات حقيقية وواضحة\n",
            "├ تقديم جوائز حقيقية وموثوقة\n",
            "└ احترام جميع المشاركين",
            "\n\n",
            "❌ : الممنوع:\n",
            "├ سحوبات وهمية أو مضللة\n",
            "├ خداع المستخدمين\n",
            "└ التلاعب بالنتائج",
            "\n\n",
            ([
                "🚨 : أي مخالفة = حظر دائم\n",
                "ثقتكم هي أولويتنا",
            ], "blockquote", None),
        ], "bold", None),
    ]
    return build_text_with_emojis(parts)


def build_terms_keyboard() -> InlineKeyboardMarkup:
    """كيبورد رسالة الشروط والأحكام: زر «رجوع» أحمر يعيد للقائمة الرئيسية."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "رجوع", callback_data="back_main_menu",
            style="danger", **emoji_kwargs("back_section_btn"),
        )],
    ])


def build_support_bot_message() -> tuple:
    """رسالة قائمة «دعم البوت» — نفس نص وتنسيق الصورة المرفقة."""
    parts = [
        ([
            ("⭐", EMOJI["star"]),
            " دعم البوت",
        ], "bold", None),
        "\n\n",
        f"ادفع {SUPPORT_BOT_STARS_AMOUNT} نجوم تيليجرام لدعم تطوير البوت 💖",
        "\n\n",
        "كل نجمة تساعدنا في الاستمرار وتطوير ميزات جديدة!",
        "\n\n",
        "👇 اضغط على الزر أدناه للدفع:",
    ]
    return build_text_with_emojis(parts)


def build_support_bot_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"ادفع {SUPPORT_BOT_STARS_AMOUNT} نجوم", callback_data="support_pay_stars",
            style="success", **emoji_kwargs("star"),
        )],
        [InlineKeyboardButton(
            "رجوع", callback_data="back_main_menu",
            style="danger", **emoji_kwargs("back_section_btn"),
        )],
    ])


def get_required_channel_username() -> str:
    """اسم يوزر قناة الاشتراك الإجباري الحالية (بدون @) — قابل للتغيير من قسم المالك."""
    return (get_setting("required_channel_username") or REQUIRED_CHANNEL_USERNAME).lstrip("@")


def get_required_channel_url() -> str:
    """رابط قناة الاشتراك الإجباري الحالية."""
    custom_url = get_setting("required_channel_url")
    if custom_url:
        return custom_url
    return f"https://t.me/{get_required_channel_username()}"


def get_required_channel_next_username() -> str:
    """اسم يوزر القناة التالية (بدون @) التي سيتم التحويل إليها تلقائيًا، أو فارغ إن لم تُحدَّد."""
    return (get_setting("required_channel_next_username") or "").lstrip("@")


def get_required_channel_auto_target() -> int:
    """عدد المشتركين المطلوب للتحويل التلقائي للقناة التالية."""
    raw = get_setting("required_channel_auto_target") or REQUIRED_CHANNEL_DEFAULT_TARGET
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(REQUIRED_CHANNEL_DEFAULT_TARGET)


def _normalize_channel_username(raw: str) -> str:
    """يستخرج اسم اليوزر من نص قد يكون @username أو t.me/username أو مجرد username."""
    value = (raw or "").strip()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/", "@"):
        if value.lower().startswith(prefix):
            value = value[len(prefix):]
            break
    value = value.strip().strip("/")
    return value


def build_subscription_required_message() -> tuple:
    """رسالة تطلب من المستخدم الاشتراك في القناة قبل استخدام البوت."""
    parts = [
        "عليك الأشتراك في القناة اولاً",
        "\n",
        "- لتتمكن من أستخدام البوت : ",
        ("💻", EMOJI["sub_laptop"]),
        "\n",
        ([
            ("‼️", EMOJI["sub_alert"]),
            " | اشترك ثم اضغط تحقق",
            ("✅", EMOJI["sub_check"]),
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_subscription_required_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(REQUIRED_CHANNEL_BUTTON_TEXT, url=get_required_channel_url())],
        [InlineKeyboardButton("تحقق من الاشتراك", callback_data="check_sub_status")],
    ])


_SUBSCRIPTION_CACHE = {}
SUBSCRIPTION_CACHE_TTL = 60
SUBSCRIPTION_NEGATIVE_CACHE_TTL = 3


async def is_user_subscribed(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, force_refresh: bool = False
) -> bool:
    """يتحقق مما إذا كان المستخدم عضوًا في قناة الاشتراك الإجباري، مع كاش مؤقت
    لكل مستخدم لتجنب نداء تليجرام (get_chat_member) في كل ضغطة/فتح رابط —
    وهو السبب الرئيسي لبطء رد الأزرار وتأخر ظهور الكابتشا بعد إعادة التوجيه."""
    cached = _SUBSCRIPTION_CACHE.get(user_id)
    if not force_refresh and cached is not None:
        age = time.time() - cached["ts"]
        ttl = SUBSCRIPTION_CACHE_TTL if cached["value"] else SUBSCRIPTION_NEGATIVE_CACHE_TTL
        if age < ttl:
            return cached["value"]
    channel_username = get_required_channel_username()
    result = False
    for attempt in range(2):
        try:
            member = await context.bot.get_chat_member(
                chat_id=f"@{channel_username}", user_id=user_id
            )
            result = (
                member.status in ("member", "administrator", "creator")
                or (member.status == "restricted" and bool(getattr(member, "is_member", False)))
            )
            break
        except RetryAfter as exc:
            if attempt == 0 and exc.retry_after <= 5:
                logger.warning(
                    "تيليجرام حدّد عدد الطلبات أثناء التحقق من اشتراك %s في @%s — "
                    "إعادة محاولة واحدة بعد %s ثانية بدل رفض المستخدم فورًا",
                    user_id, channel_username, exc.retry_after,
                )
                await asyncio.sleep(exc.retry_after)
                continue
            logger.warning(
                "تيليجرام حدّد عدد الطلبات أثناء التحقق من اشتراك %s في @%s "
                "(retry_after=%s) — تعذّر إعادة المحاولة الآن، سيُعامَل كغير مشترك مؤقتًا",
                user_id, channel_username, exc.retry_after,
            )
            result = False
            break
        except Exception:
            logger.exception(
                "تعذّر التحقق من اشتراك المستخدم %s في القناة @%s",
                user_id, channel_username,
            )
            result = False
            break
    _SUBSCRIPTION_CACHE[user_id] = {"value": result, "ts": time.time()}
    return result


_GW_CONDITION_SUB_CACHE = {}


async def is_user_subscribed_to_chat(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_ref,
    force_refresh: bool = False,
) -> bool:
    """يتحقق من اشتراك المستخدم في أي قناة يتم تمريرها (chat_ref: يوزر بصيغة
    "@username" أو معرّف الشات الرقمي)، بنفس منطق/كاش is_user_subscribed لكن
    لقنوات «شرط السحب» الديناميكية بدل قناة الاشتراك الإجباري الثابتة. تُستخدم
    هذه الدالة للتحقق الداخلي دون تحويل المستخدم لأي بوت آخر."""
    cache_key = (user_id, str(chat_ref))
    cached = _GW_CONDITION_SUB_CACHE.get(cache_key)
    if not force_refresh and cached is not None:
        age = time.time() - cached["ts"]
        ttl = SUBSCRIPTION_CACHE_TTL if cached["value"] else SUBSCRIPTION_NEGATIVE_CACHE_TTL
        if age < ttl:
            return cached["value"]

    result = False
    for attempt in range(2):
        try:
            member = await context.bot.get_chat_member(chat_id=chat_ref, user_id=user_id)
            result = (
                member.status in ("member", "administrator", "creator")
                or (member.status == "restricted" and bool(getattr(member, "is_member", False)))
            )
            break
        except RetryAfter as exc:
            if attempt == 0 and exc.retry_after <= 5:
                await asyncio.sleep(exc.retry_after)
                continue
            result = False
            break
        except Exception:
            logger.exception(
                "تعذّر التحقق من اشتراك المستخدم %s في قناة الشرط %s", user_id, chat_ref,
            )
            result = False
            break
    _GW_CONDITION_SUB_CACHE[cache_key] = {"value": result, "ts": time.time()}
    return result


async def check_contest_channel_subscription(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, contest, force_refresh: bool = False,
) -> bool:
    """يتحقق تلقائيًا (في الخلفية) من عضوية المستخدم في القناة التي نُشرت فيها
    المسابقة تحديدًا (contest['chat_id']) — بصرف النظر عن كيفية وصوله لرسالة
    المسابقة (حتى لو من خارج القناة). هذا شرط ضمني دائم لكل مسابقة، ولا يُعرض
    للمستخدم أي شيء بخصوصه إلا إذا تبيّن أنه غير مشترك فعلاً."""
    chat_id = contest.get("chat_id") if hasattr(contest, "get") else contest["chat_id"]
    if not chat_id:
        return True
    return await is_user_subscribed_to_chat(context, user_id, chat_id, force_refresh=force_refresh)


async def build_contest_channel_join_link(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> str:
    """يبني رابط انضمام لقناة المسابقة: يوزر عام إن وُجد، وإلا رابط دعوة لقناة
    خاصة. يُستخدم في زر «انضم إلى القناة» ببوابة شرط قناة المسابقة."""
    try:
        chat = await context.bot.get_chat(chat_id)
        if chat.username:
            return f"https://t.me/{chat.username}"
    except Exception:
        logger.exception("تعذّر جلب معلومات قناة المسابقة %s لبناء رابط الانضمام", chat_id)
    try:
        invite_link = await context.bot.create_chat_invite_link(chat_id)
        return invite_link.invite_link
    except Exception:
        try:
            return await context.bot.export_chat_invite_link(chat_id)
        except Exception:
            logger.exception("تعذّر بناء رابط دعوة لقناة المسابقة %s", chat_id)
            return ""


_CHAT_TITLE_CACHE = {}
CHAT_TITLE_CACHE_TTL = 3600


async def get_chat_title_cached(context: ContextTypes.DEFAULT_TYPE, chat_id) -> str:
    """يجلب عنوان أي محادثة (قناة/قروب) مع كاش لمدة ساعة، لتفادي نداء get_chat
    المتكرر عند بناء بوابات الشروط ورسائل التنبيه في كل ضغطة مشاركة."""
    cached = _CHAT_TITLE_CACHE.get(chat_id)
    if cached is not None and time.time() - cached["ts"] < CHAT_TITLE_CACHE_TTL:
        return cached["title"]
    title = ""
    try:
        chat = await context.bot.get_chat(chat_id)
        title = chat.title or ""
    except Exception:
        logger.exception("تعذّر جلب عنوان القناة %s", chat_id)
    _CHAT_TITLE_CACHE[chat_id] = {"title": title, "ts": time.time()}
    return title


async def check_giveaway_host_channel_subscription(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, giveaway, force_refresh: bool = False,
) -> bool:
    """يتحقق من اشتراك المستخدم في القناة التي استُضيف فيها السحب نفسه
    (giveaway['chat_id']) — شرط ضمني دائم لكل سحب، بنفس منطق
    check_contest_channel_subscription المستخدمة للمسابقات، وبمعزل تام عن
    قنوات الشرط الإضافية الاختيارية التي يضيفها المالك يدويًا
    (condition_channels). دون هذا الشرط يمكن للمستخدم المشاركة في السحب دون
    أن يكون منضمًا إطلاقًا إلى القناة التي نُشر فيها."""
    chat_id = giveaway.get("chat_id") if hasattr(giveaway, "get") else giveaway["chat_id"]
    if not chat_id:
        return True
    return await is_user_subscribed_to_chat(context, user_id, chat_id, force_refresh=force_refresh)


async def build_giveaway_gate_context(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, giveaway,
) -> dict:
    """يجهّز حالة «البوابة الموحّدة» لسحب معيّن: هل يلزم عرض شرط الاشتراك في
    قناة VORTEX، وهل يلزم عرض شرط الاشتراك في قناة استضافة السحب نفسها (مع
    رابط وعنوان تلك القناة عند الحاجة) — بحيث يُبنى الزرّان معًا في شاشة واحدة
    بدل بوابتين متتاليتين منفصلتين."""
    need_vortex = not await is_user_subscribed(context, user_id)
    host_channel_link = ""
    host_channel_title = ""
    if not await check_giveaway_host_channel_subscription(context, user_id, giveaway):
        host_channel_link = await build_contest_channel_join_link(context, giveaway["chat_id"])
        host_channel_title = await get_chat_title_cached(context, giveaway["chat_id"]) or "قناة السحب"
    return {
        "need_vortex": need_vortex,
        "host_channel_link": host_channel_link,
        "host_channel_title": host_channel_title,
    }


async def check_giveaway_condition_channels(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, giveaway,
) -> bool:
    """يتحقق من اشتراك المستخدم في جميع قنوات شرط السحب (واحدة أو قناتين).
    يُعيد True فقط إذا لم توجد قنوات شرط أصلاً، أو كان مشتركًا في جميعها."""
    channels = giveaway.get("condition_channels") or []
    for channel in channels:
        ref = channel.get("ref")
        if not ref:
            continue
        if not await is_user_subscribed_to_chat(context, user_id, ref):
            return False
    return True


async def check_giveaway_boost(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int,
) -> bool:
    """يتحقق مما إذا كان المستخدم قد عزّز (Boost) قناة السحب فعليًا، عبر
    استدعاء getUserChatBoosts الأصلي في تيليجرام (يُستخدم عند تفعيل خيار
    «تعزيز القناة» — Image A1/A2). يُعيد True فقط إذا كانت لدى المستخدم
    تعزيزة واحدة على الأقل مسجّلة على هذه القناة تحديدًا (Image A4/A5)."""
    try:
        result = await context.bot.get_user_chat_boosts(chat_id=chat_id, user_id=user_id)
        return bool(result.boosts)
    except Exception:
        logger.exception(
            "تعذّر التحقق من تعزيز المستخدم %s للقناة %s", user_id, chat_id,
        )
        return False


async def check_giveaway_requirements(context: ContextTypes.DEFAULT_TYPE, user, giveaway) -> tuple:
    """يتحقق من جميع شروط الدخول في السحب (بريميوم / قنوات الاشتراك / تعزيز /
    تصويت لمتسابق) بترتيب واحد موحّد، ويُستخدم في كل نقاط الدخول (زر المشاركة
    المباشر، بوابة الاشتراك قبل الكابتشا، والتحقق النهائي بعد الكابتشا) حتى لا
    تتكرر نفس الشروط بصيغ مختلفة في أكثر من مكان.
    يُعيد (True, "") عند اجتياز كل الشروط، أو (False, نص التنبيه المناسب لأول شرط لم يتحقق)."""
    if giveaway.get("premium_only") and not user.is_premium:
        return False, "💎 هذا السحب للأشخاص المفعلين مميز فقط!"

    if not await check_giveaway_host_channel_subscription(context, user.id, giveaway):
        host_title = await get_chat_title_cached(context, giveaway["chat_id"])
        return False, build_giveaway_host_channel_subscribe_alert(host_title)

    if not await check_giveaway_condition_channels(context, user.id, giveaway):
        return False, build_giveaway_condition_subscribe_alert()

    if giveaway.get("boost_required") and not await check_giveaway_boost(
        context, user.id, giveaway["chat_id"],
    ):
        return False, "❌ يجب عليك تعزيز القناة اولا"

    vote_contest_code = giveaway.get("vote_contest_code")
    vote_participant_id = giveaway.get("vote_participant_id")
    if vote_contest_code and vote_participant_id and not has_voted_for(
        vote_contest_code, user.id, vote_participant_id,
    ):
        return False, "❌ يجب عليك التصويت للمتسابق أولاً قبل المشاركة في السحب"

    return True, ""


async def build_giveaway_gate_links(context: ContextTypes.DEFAULT_TYPE, giveaway) -> tuple:
    """يبني رابط التعزيز (إن كان السحب يتطلب Boost) ورابط التصويت (إن كان
    مشروطًا بالتصويت لمتسابق)، لعرضهما كأزرار داخل بوابة شروط السحب."""
    boost_link = (
        await build_giveaway_boost_link(context, giveaway["chat_id"])
        if giveaway.get("boost_required") else ""
    )
    vote_contest_code = giveaway.get("vote_contest_code")
    vote_participant_id = giveaway.get("vote_participant_id")
    vote_link = (
        build_giveaway_vote_condition_link(vote_contest_code, vote_participant_id)
        if vote_contest_code and vote_participant_id else ""
    )
    return boost_link, vote_link


async def _check_bot_can_verify_channel(context: ContextTypes.DEFAULT_TYPE, username: str) -> str:
    """يتحقق من أن البوت نفسه مُضاف كمشرف (Admin) في قناة الاشتراك الإجباري
    الجديدة. هذا شرط ضروري لعمل get_chat_member بشكل صحيح — إن لم يكن البوت
    مشرفًا هناك، ستفشل عملية التحقق من الاشتراك لكل المستخدمين (حتى المشتركين
    الحقيقيين فعليًا)، وهو ما يظهر للمستخدم كخطأ "لم يتم العثور على اشتراكك"
    رغم أنه مشترك فعلاً. تُعيد نص تحذير جاهزًا للإرسال للمالكين، أو '' إن كان
    كل شيء سليمًا."""
    try:
        me = await context.bot.get_chat_member(chat_id=f"@{username}", user_id=context.bot.id)
    except Exception as exc:
        return (
            f"⚠️ تنبيه: تعذّر على البوت الوصول إلى @{username} ({exc}).\n"
            f"على الأغلب البوت غير مُضاف لهذه القناة إطلاقًا. أضِف البوت إليها كمشرف "
            f"(Admin) فورًا، وإلا فسيفشل التحقق من اشتراك جميع المستخدمين ويظهر لهم "
            f"خطأ «لم يتم العثور على اشتراكك» حتى لو كانوا مشتركين بالفعل."
        )
    if me.status not in ("administrator", "creator"):
        return (
            f"⚠️ تنبيه: البوت عضو في @{username} لكنه ليس مشرفًا (Admin) فيها.\n"
            f"يجب ترقية البوت إلى مشرف في هذه القناة الآن، وإلا فسيفشل التحقق من "
            f"اشتراك جميع المستخدمين ويظهر لهم خطأ «لم يتم العثور على اشتراكك» حتى "
            f"لو كانوا مشتركين بالفعل."
        )
    return ""


async def check_required_channel_auto_switch(context: ContextTypes.DEFAULT_TYPE):
    """
    مهمة دورية: تتحقق من عدد مشتركي قناة الاشتراك الإجباري الحالية، وإن وصلت
    (أو تجاوزت) العدد المطلوب وكانت هناك قناة تالية محددة من المالك، يتم تبديل
    قناة الاشتراك الإجباري تلقائيًا إليها. إن لم تُحدَّد قناة تالية فلا يحدث أي
    تغيير أبدًا مهما بلغ عدد المشتركين.
    """
    next_username = get_required_channel_next_username()
    if not next_username:
        return

    target = get_required_channel_auto_target()
    current_username = get_required_channel_username()
    try:
        count = await context.bot.get_chat_member_count(chat_id=f"@{current_username}")
    except Exception:
        logger.exception(
            "تعذّر جلب عدد مشتركي قناة الاشتراك الإجباري @%s للتحقق من التغيير التلقائي",
            current_username,
        )
        return

    if count < target:
        return

    set_setting("required_channel_username", next_username)
    set_setting("required_channel_url", f"https://t.me/{next_username}")
    set_setting("required_channel_next_username", "")
    _SUBSCRIPTION_CACHE.clear()
    logger.info(
        "تم تغيير قناة الاشتراك الإجباري تلقائيًا من @%s إلى @%s بعد وصول عدد المشتركين إلى %s",
        current_username, next_username, count,
    )
    warning = await _check_bot_can_verify_channel(context, next_username)
    for owner_id in OWNER_IDS:
        try:
            await context.bot.send_message(
                chat_id=owner_id,
                text=(
                    f"✅ تم تغيير قناة الاشتراك الإجباري تلقائيًا\n"
                    f"من: @{current_username}\n"
                    f"إلى: @{next_username}\n"
                    f"(بعد وصولها إلى {count} مشترك)"
                    + (f"\n\n{warning}" if warning else "")
                ),
            )
        except Exception:
            pass


def build_contest_section_message() -> tuple:
    """
    رسالة قسم إنشاء المسابقات:
    - العنوان بخط عريض (Bold) + إيموجي الكأس.
    - سطر التوجيه داخل اقتباس وردي (Blockquote) منتهي بعلامة ” + إيموجي السهم.
    """
    parts = [
        ([
            ("🏆", EMOJI["trophy_create_draw"]),
            " قسم إنشاء المسابقات",
        ], "bold", None),
        "\n\n",
        ([
            "• اختر ما تريدمن القائمة أدناه ",
            ("⏬", EMOJI["arrow_down"]),
            "  ”",
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_contest_section_keyboard() -> InlineKeyboardMarkup:
    """
    كيبورد قسم إنشاء المسابقات بنفس ألوان الصورة:
    - أخضر (success) لزر «انشاء مسابقة».
    - أزرق/سماوي (primary) لزري «تسجيل قروب» و«تسجيل قناة».
    - أحمر (danger) لزر «رجوع».
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "انشاء مسابقة", callback_data="comp_start_create",
            style="success", **emoji_kwargs("trophy_contest"),
        )],
        [
            InlineKeyboardButton(
                "تسجيل قروب", callback_data="comp_reg_group",
                style="primary", **emoji_kwargs("register_plus"),
            ),
            InlineKeyboardButton(
                "تسجيل قناة", callback_data="comp_reg_channel",
                style="primary", **emoji_kwargs("register_plus"),
            ),
        ],
        [InlineKeyboardButton(
            "المسابقات الحديثة", callback_data="comp_recent",
            style="primary", **emoji_kwargs("recent_contests_btn"),
        )],
        [InlineKeyboardButton(
            "رجوع", callback_data="back_main_menu",
            style="danger", **emoji_kwargs("back_section_btn"),
        )],
    ])


def build_contest_target_message() -> tuple:
    """
    شاشة «يرجى تحديد القناة أو القروب لـ المسابقة»:
    - العنوان بخط عريض (Bold) + إيموجي الهدف.
    - الجملتين التوجيهيتين داخل اقتباس وردي (Blockquote) — نفس نظام التلوين
      المستخدم سابقًا (تليجرام بيرسم كيان الـ blockquote بلون وردي/أحمر فاتح تلقائيًا
      مع علامة ” الجانبية، فهو نفس اللون المطلوب).
    """
    parts = [
        ([
            "يرجى تحديد القناة أو القروب لـ المسابقة ",
            ("🎯", EMOJI["target_pin"]),
        ], "bold", None),
        "\n\n",
        ([
            "تأكد أولا انك مشرف في القناة او القروب وان البوت أيضا مشرف",
        ], "blockquote", None),
        "\n\n",
        ([
            "إذا لم تظهر القناة أو الجروب وتأكدت ان البوت بها كمشرف وأنت كمشرف إذا يمكنك تسجيله يدويا من الأسفل",
            ("⏬", EMOJI["arrow_down"]),
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_contest_target_keyboard(owner_id: int = None) -> InlineKeyboardMarkup:
    """
    كيبورد شاشة تحديد القناة/القروب:
    - زر شفاف (بدون لون/بدون إيموجي) لكل قناة أو جروب تمت إضافة البوت كمشرف
      فيه لنفس صاحب الطلب — يظهر تلقائيًا فوق صف التسجيل، تمامًا مثل شكل
      الزر الشفاف في الصورة المرفقة.
    - أزرق/سماوي (primary) لزري «تسجيل قروب» و«تسجيل قناة» بجانب بعض.
    - أحمر (danger) لزر «رجوع» اللي بيرجّع لقسم إنشاء المسابقات.
    """
    rows = []

    if owner_id is not None:
        for chat in get_registered_chats(owner_id):
            title = chat["chat_title"] or str(chat["chat_id"])
            rows.append([InlineKeyboardButton(
                title, callback_data=f"comp_pick_chat_{chat['chat_id']}",
            )])

    rows.append([
        InlineKeyboardButton(
            "تسجيل قروب", callback_data="comp_reg_group",
            style="primary", **emoji_kwargs("register_plus"),
        ),
        InlineKeyboardButton(
            "تسجيل قناة", callback_data="comp_reg_channel",
            style="primary", **emoji_kwargs("register_plus"),
        ),
    ])
    rows.append([InlineKeyboardButton(
        "رجوع", callback_data="section_competition",
        style="danger", **emoji_kwargs("back_section_btn"),
    )])
    return InlineKeyboardMarkup(rows)


def build_back_to_competition_keyboard() -> InlineKeyboardMarkup:
    """كيبورد موحّد لزر «رجوع» اللي بيرجّع لقسم إنشاء المسابقات."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "رجوع", callback_data="section_competition",
            style="danger", **emoji_kwargs("back_section_btn"),
        )],
    ])


def build_recent_contests_list_message() -> tuple:
    """شاشة اختيار القناة عند وجود أكثر من مسابقة جارية."""
    parts = [
        ([
            "📢 اختر القناة التي تريد التعديل على مسابقتها :",
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_recent_contests_list_keyboard(contests) -> InlineKeyboardMarkup:
    """أزرار شفافة (بدون لون/إيموجي مخصص) بعدد المسابقات الجارية، باسم كل قناة."""
    rows = []
    for c in contests:
        title = get_chat_title_by_id(c["chat_id"])
        rows.append([InlineKeyboardButton(
            f"📢 {title}", callback_data=f"comp_detail:{c['contest_code']}",
        )])
    rows.append([InlineKeyboardButton(
        "رجوع", callback_data="section_competition",
        style="danger", **emoji_kwargs("back_section_btn"),
    )])
    return InlineKeyboardMarkup(rows)


def build_contest_detail_message(contest, channel_title: str, post_link, participants_count: int) -> tuple:
    """شاشة إعدادات مسابقة واحدة — تطابق تنسيق الصورة المرفقة."""
    name = contest_display_name(contest)
    status_line = "🟢 نشطة" if contest["status"] == "open" else "🔴 متوقفة"

    def flag(value):
        return ("✅", EMOJI["check_flag_on"]) if value else ("❌", EMOJI["cross_flag_off"])

    channel_line = ["📢 القناة : ", channel_title, " | "]
    if post_link:
        channel_line.append(("رابط منشور المسابقة", "link", post_link))
    else:
        channel_line.append("رابط منشور المسابقة")

    parts = [
        ([
            "📋 المسابقة :\n",
            name,
            "\n\n",
            *channel_line,
            "\n\n",
            f"📊 الحالة : {status_line}",
            "\n\n",
            f"👥 المتسابقون : {participants_count} / {contest['target_count']}",
            "\n\n",
            "⚙️ إعدادات المسابقة :",
            "\n\n",
            "🔔 تنبيه الفوز | ", flag(contest["notify_win"]), "\n",
            "📣 إعلان النتائج | ", flag(contest["announce_results"]), "\n",
            "🧩 موافقة المشاركات | ", flag(contest["approve_participants"]), "\n",
            "💎 تصويت بريميوم | ", flag(contest["premium_only"]),
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_contest_detail_keyboard(contest) -> InlineKeyboardMarkup:
    code = contest["contest_code"]
    toggle_label = "⏸ إيقاف المسابقة" if contest["status"] == "open" else "▶️ استئناف المسابقة"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "تغيير عدد المقاعد", callback_data=f"comp_change_seats:{code}",
            style="primary", **emoji_kwargs("seats_change_btn"),
        )],
        [InlineKeyboardButton(
            toggle_label, callback_data=f"comp_toggle_active:{code}",
            style="primary", **emoji_kwargs("pause_toggle_btn"),
        )],
        [InlineKeyboardButton(
            "تغيير إعدادات المسابقة", callback_data=f"comp_edit_settings:{code}",
            style="primary", **emoji_kwargs("edit_settings_refresh_btn"),
        )],
        [InlineKeyboardButton(
            "إزالة متسابق", callback_data=f"comp_remove_contestant:{code}",
            style="danger", **emoji_kwargs("remove_contestant_btn"),
        )],
        [InlineKeyboardButton(
            "حذف المسابقة بالكامل", callback_data=f"comp_delete_all:{code}",
            style="danger", **emoji_kwargs("delete_all_btn"),
        )],
        [InlineKeyboardButton(
            "رجوع", callback_data="section_competition",
            style="danger", **emoji_kwargs("back_section_btn"),
        )],
    ])


def build_channel_registration_message() -> tuple:
    """

    شاشة «لـ اضافة قناة اتبع الخطوات التالية»:
    - العنوان الرئيسي وعنوان «ملاحظة» بخط عريض (Bold).
    - الخطوتين بأرقام مخصصة (1️⃣ / 2️⃣) كنص عادي.
    - جملة الملاحظة داخل اقتباس وردي (Blockquote) منتهية بعلامة ”.
    """
    parts = [
        ("لـ اضافة قناة اتبع الخطوات التالية:", "bold", None),
        "\n\n",
        ("1️⃣", EMOJI["num_one"]),
        f"أضف البوت @{BOT_USERNAME} كمشرف في قناتك.",
        "\n\n",
        ("2️⃣", EMOJI["num_two"]),
        "قم بإعادة توجيه أي رسالة من قناتك إلى البوت",
        "\n\n",
        ([("📌", EMOJI["pin_note"]), "ملاحظة:"], "bold", None),
        "\n",
        ([
            "جميع المشرفين الآخرين في القناة سيتمكنون أيضًا من استخدام البوت بعد إضافته  ”",
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_group_registration_message() -> tuple:
    """
    شاشة «لـ اضافة جروب اتبع الخطوات التالية»:
    - العنوان الرئيسي بخط عريض (Bold).
    - الخطوتين بأرقام مخصصة (1️⃣ / 2️⃣) كنص عادي.
    """
    parts = [
        ("لـ اضافة جروب اتبع الخطوات التالية:", "bold", None),
        "\n\n",
        ("1️⃣", EMOJI["num_one"]),
        f"أضف البوت @{BOT_USERNAME} كمشرف في الجروب الخاص بك",
        "\n\n",
        ("2️⃣", EMOJI["num_two"]),
        "إذهب للجروب الخاص بك بعد إضافة البوت و اكتب ",
        ("◀️", EMOJI["arrow_left"]),
        "تفعيل روليت",
    ]
    return build_text_with_emojis(parts)


def build_contest_cliche_message() -> tuple:
    """
    شاشة «أرسل كليشة المسابقة»:
    - العنوان بخط عريض (Bold) + إيموجي الظرف.
    - أمثلة توضيحية فعلية لتنسيقات تيليجرام (عريض/مائل/مشوش/رابط).
    - سطر ختامي داخل اقتباس وردي (Blockquote) بعلامة ” كنموذج «نص مقتبس».
    """
    parts = [
        ([
            ("📨", EMOJI["envelope_klesha"]),
            " أرسل كليشة المسابقة",
        ], "bold", None),
        "\n\n",
        "اكتب نص المسابقة الذي تريد نشره في القناة.\n"
        "يمكنك استخدام تنسيقات تيليجرام، مثل:\n",
        "• ", ("نص عريض", "bold", None), "\n",
        "• ", ("نص مائل", "italic", None), "\n",
        "• ", ("نص مشوش", "spoiler", None), "\n",
        ([("🆕", EMOJI["new_badge"]), " يمكنك وضع رابط داخل النص"], "link", "https://t.me"),
        "\n",
        (["نص مقتبس  ”"], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_contest_cliche_keyboard() -> InlineKeyboardMarkup:
    return _build_single_back_keyboard("رجوع", "comp_start_create", "danger", "back_section_btn")


def build_contest_count_message() -> tuple:
    """شاشة «أرسل عدد المتسابقين المطلوب 🎯:» — عنوان واحد بخط عريض."""
    parts = [
        ([
            "أرسل عدد المتسابقين المطلوب ",
            ("🎯", EMOJI["target_pin"]),
            ":",
        ], "bold", None),
    ]
    return build_text_with_emojis(parts)


def build_contest_count_keyboard() -> InlineKeyboardMarkup:
    return _build_single_back_keyboard("رجوع", "comp_back_to_klesha", "danger", "back_section_btn")


def build_contest_end_method_message() -> tuple:
    """
    شاشة «اختر طريقة انتهاء المسابقة»:
    - العنوان بخط عريض.
    - كل خيار داخل اقتباس وردي (Blockquote) منفصل.
    """
    parts = [
        ([" اختر طريقة انتهاء المسابقة:", ("❓", EMOJI["end_question"])], "bold", None),
        "\n\n",
        ([
            ("🎯", EMOJI["target_pin"]),
            "   عدد اصوات محدده: تنتهي المسابقة عند وصول المتسابقين عدد الاصوات الذي تحددها",
        ], "blockquote", None),
        "\n\n",
        ([
            ("⏰", EMOJI["alarm_clock"]),
            "   وقت محدد : تنتهي المسابقة تلقائياً عند انقضاء الوقت الذي تحدده ويفوز صاحب الاصوات الأعلى",
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_contest_end_method_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "عدد اصوات محدده", callback_data="comp_end_votes",
                style="primary", **emoji_kwargs("votes_chart_btn"),
            ),
            InlineKeyboardButton(
                "وقت محدد", callback_data="comp_end_time",
                style="primary", **emoji_kwargs("alarm_clock_btn"),
            ),
        ],
        [InlineKeyboardButton(
            "رجوع", callback_data="comp_back_to_count",
            style="danger", **emoji_kwargs("back_section_btn"),
        )],
    ])


def build_contest_time_menu_message(selected_label: str = "غير محدد") -> tuple:
    """
    شاشة «⏰ وقت محدد للمسابقة»:
    - العنوان بخط عريض (Bold) + إيموجي الساعة.
    - القيمة الحالية في سطر مستقل.
    - جملة التوجيه.
    """
    parts = [
        ([
            ("⏰", EMOJI["alarm_clock_title"]),
            "وقت محدد للمسابقة",
        ], "bold", None),
        f"\nالوقت المختار: {selected_label}",
        "\n\n",
        "استخدم الأزرار أدناه لتحديد الوقت المطلوب لانتهاء المسابقة تلقائياً:",
    ]
    return build_text_with_emojis(parts)


def build_contest_time_menu_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for row in CONTEST_TIME_OPTIONS:
        rows.append([
            InlineKeyboardButton(
                label, callback_data=f"comp_atime_set_{minutes}",
                style="primary", **emoji_kwargs("time_option_btn"),
            )
            for minutes, label in row
        ])
    rows.append([
        InlineKeyboardButton(
            "وقت مخصص", callback_data="comp_atime_show_custom",
            style="primary", **emoji_kwargs("time_manual_btn"),
        ),
    ])
    rows.append([
        InlineKeyboardButton(
            "رجوع", callback_data="comp_back_to_end_type",
            style="danger", **emoji_kwargs("back_time_menu_btn"),
        )
    ])
    return InlineKeyboardMarkup(rows)


CONTEST_TIME_CUSTOM_STEPS = [
    [(-1, "- 1 دقيقة"), (1, "+ 1 دقيقة")],
    [(-5, "- 5 دقيقة"), (5, "+ 5 دقيقة")],
    [(-10, "- 10 دقايق"), (10, "+ 10 دقايق")],
    [(-60, "- 1 ساعة"), (60, "+ 1 ساعة")],
    [(-1440, "- 1 يوم"), (1440, "+ 1 يوم")],
]


def build_contest_time_custom_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for row in CONTEST_TIME_CUSTOM_STEPS:
        rows.append([
            InlineKeyboardButton(
                label, callback_data=f"comp_atime_custom_delta:{delta}",
                style="primary", **emoji_kwargs("time_option_btn"),
            )
            for delta, label in row
        ])
    rows.append([InlineKeyboardButton(
        "تأكيد الوقت", callback_data="comp_atime_custom_confirm",
        style="success", **emoji_kwargs("yes_btn"),
    )])
    rows.append([
        InlineKeyboardButton(
            "إعادة تعيين", callback_data="comp_atime_custom_reset",
            style="success", **emoji_kwargs("restore_defaults_btn"),
        ),
        InlineKeyboardButton(
            "رجوع للخيارات", callback_data="comp_back_to_end_type",
            style="danger", **emoji_kwargs("back_section_btn"),
        ),
    ])
    return InlineKeyboardMarkup(rows)


def build_contest_votes_target_message() -> tuple:
    """شاشة «أرسل عدد الأصوات المطلوب» لتفعيل إنهاء المسابقة تلقائيًا عند وصول
    أحد المتسابقين لعدد الأصوات المحدد."""
    parts = [
        ([
            ("🎯", EMOJI["votes_chart_btn"]), " عدد أصوات محدد",
        ], "bold", None),
        "\n\n",
        "أرسل عدد الأصوات المطلوب لإنهاء المسابقة تلقائيًا عند وصول أحد المتسابقين إليه",
        "\n\n",
        ([
            "مثال: إذا أردت إنهاء المسابقة عند وصول أحد المتسابقين إلى 100 صوت "
            "أرسل الرقم 100",
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_contest_votes_target_keyboard() -> InlineKeyboardMarkup:
    return _build_single_back_keyboard("رجوع", "comp_back_to_end_type", "danger", "back_section_btn")


def build_contest_winners_message() -> tuple:
    """شاشة «أرسل عدد الفائزين المطلوب 🏆:»."""
    parts = [
        ([
            "أرسل عدد الفائزين المطلوب ",
            ("🏆", EMOJI["trophy_winners_title"]),
            ":",
        ], "bold", None),
    ]
    return build_text_with_emojis(parts)


def build_contest_winners_keyboard() -> InlineKeyboardMarkup:
    return _build_single_back_keyboard("رجوع", "comp_back_to_end_type", "danger", "back_winners_btn")


def build_contest_winners_confirm_message() -> tuple:
    """رسالة تأكيد «✅ تم تحديد عدد الفائزين» — تُرسل قبل شاشة إعدادات المسابقة."""
    parts = [
        ([
            ("✅", EMOJI["confirm_check"]),
            " تم تحديد عدد الفائزين",
        ], "bold", None),
    ]
    return build_text_with_emojis(parts)


CONTEST_SETTINGS_DEFAULTS = {
    "contest_notify_win": False,
    "contest_announce_results": False,
    "contest_approve_participants": True,
    "contest_premium_only": False,
}


def build_contest_settings_message() -> tuple:
    """
    شاشة «• اعدادات المسابقة الحالية:»:
    - عنوان بخط عريض.
    - كل إعداد: تسمية بخط عريض + شرح عادي.
    - سطر ختامي داخل اقتباس وردي (Blockquote).
    """
    parts = [
        (["• اعدادات المسابقة الحالية:"], "bold", None),
        "\n\n",
        (["- تنبيه الفوز"], "bold", None),
        " : ارسال اشعار تلقائي عند فوز احد المتسابقين",
        "\n\n",
        (["- اعلان النتائج"], "bold", None),
        " : اعلان نتائج المتسابقين وعدد اصواتهم",
        "\n\n",
        (["- موافقة المشاركات"], "bold", None),
        " : نشر أسماء المشاركين تلقائيا أو مراجعتها قبل الموافقة",
        "\n\n",
        (["- اصوات لـ المميزين"], "bold", None),
        " : التصويت متاحا فقط لمستخدمي تيليجرام المميز Premium.",
        "\n\n",
        ([
            ("✅", EMOJI["confirm_check"]),
            " الميزات المفعّلة تظهر بعلامة  ”",
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_contest_settings_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    def yn_button(flag: bool, callback_data: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            "نعم" if flag else "لا",
            callback_data=callback_data,
            style="success" if flag else "danger",
            **emoji_kwargs("yes_btn" if flag else "no_btn"),
        )

    notify = user_data.get("contest_notify_win", CONTEST_SETTINGS_DEFAULTS["contest_notify_win"])
    announce = user_data.get("contest_announce_results", CONTEST_SETTINGS_DEFAULTS["contest_announce_results"])
    approve = user_data.get("contest_approve_participants", CONTEST_SETTINGS_DEFAULTS["contest_approve_participants"])
    premium = user_data.get("contest_premium_only", CONTEST_SETTINGS_DEFAULTS["contest_premium_only"])

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("تنبيه الفوز", callback_data="comp_toggle_notify_win",
                                  style="primary", **emoji_kwargs("notify_win_btn")),
            yn_button(notify, "comp_toggle_notify_win"),
        ],
        [
            InlineKeyboardButton("اعلان النتائج", callback_data="comp_toggle_announce_results",
                                  style="primary", **emoji_kwargs("announce_results_btn")),
            yn_button(announce, "comp_toggle_announce_results"),
        ],
        [
            InlineKeyboardButton("موافقة المشاركات", callback_data="comp_toggle_approve_participants",
                                  style="primary", **emoji_kwargs("approve_participants_label_btn")),
            yn_button(approve, "comp_toggle_approve_participants"),
        ],
        [
            InlineKeyboardButton("تصويت بريميوم", callback_data="comp_toggle_premium_only",
                                  style="primary", **emoji_kwargs("premium_vote_btn")),
            yn_button(premium, "comp_toggle_premium_only"),
        ],
        [InlineKeyboardButton(
            "نشر المسابقة", callback_data="comp_publish",
            style="primary", **emoji_kwargs("publish_btn"),
        )],
        [InlineKeyboardButton(
            "رجوع", callback_data="comp_back_to_winners",
            style="danger", **emoji_kwargs("back_section_btn"),
        )],
    ])


def build_publish_success_message() -> tuple:
    """رسالة «✅ تم نشر المسابقة بنجاح!» — تحل محل قائمة الإعدادات فورًا عند الضغط على نشر."""
    parts = [
        (["✅ تم نشر المسابقة بنجاح !"], "bold", None),
    ]
    return build_text_with_emojis(parts)


def format_minutes_label(minutes: int) -> str:
    """يحوّل عدد الدقائق إلى تسمية عربية مقروءة (يوم/ساعة/دقيقة)."""
    if minutes >= 1440 and minutes % 1440 == 0:
        days = minutes // 1440
        if days == 1:
            return "يوم واحد"
        if days == 2:
            return "يومين"
        if days <= 10:
            return f"{days} أيام"
        return f"{days} يوم"
    if minutes >= 60 and minutes % 60 == 0:
        hours = minutes // 60
        if hours == 1:
            return "ساعة واحدة"
        if hours == 2:
            return "ساعتين"
        if hours <= 10:
            return f"{hours} ساعات"
        return f"{hours} ساعة"
    if minutes == 1:
        return "دقيقة واحدة"
    if minutes == 2:
        return "دقيقتين"
    if minutes <= 10:
        return f"{minutes} دقائق"
    return f"{minutes} دقيقة"


def _duration_unit_label(n: int, one: str, two: str, few: str, many: str) -> str:
    """صيغة عربية مختصرة لوحدة زمنية ضمن تسمية مركّبة (يوم/ساعة/دقيقة معًا) —
    بدون «واحد/واحدة» كي لا تتكرر عبر كل وحدة (مثال: «يوم و ساعة و 11 دقيقة»)."""
    if n == 1:
        return one
    if n == 2:
        return two
    if n <= 10:
        return f"{n} {few}"
    return f"{n} {many}"


def format_duration_label(total_minutes) -> str:
    """يحوّل عدد الدقائق المتراكم (من قائمة «وقت مخصص» التراكمية) إلى تسمية عربية
    مقروءة. عند وجود وحدة واحدة فقط (مثلاً 60 دقيقة بالضبط) تُستخدم نفس صيغة
    format_minutes_label الكاملة («ساعة واحدة»)، وعند تركيب أكثر من وحدة تُستخدم
    صيغة مختصرة متسلسلة بـ«و» (مثال: «يوم و ساعة و 11 دقيقة»)، مطابقةً لتصميم
    قائمة «وقت مخصص» (Image 7/8)."""
    if not total_minutes or total_minutes <= 0:
        return "غير محدد"
    total_minutes = int(total_minutes)
    days, rem = divmod(total_minutes, 1440)
    hours, minutes = divmod(rem, 60)
    units_present = sum(1 for x in (days, hours, minutes) if x)
    if units_present <= 1:
        return format_minutes_label(total_minutes)
    parts = []
    if days:
        parts.append(_duration_unit_label(days, "يوم", "يومين", "أيام", "يوم"))
    if hours:
        parts.append(_duration_unit_label(hours, "ساعة", "ساعتين", "ساعات", "ساعة"))
    if minutes:
        parts.append(_duration_unit_label(minutes, "دقيقة", "دقيقتين", "دقائق", "دقيقة"))
    return " و ".join(parts)


def utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def shift_entities(entities, shift: int):
    shifted = []
    for e in entities or []:
        shifted.append(MessageEntity(
            type=e.type,
            offset=e.offset + shift,
            length=e.length,
            url=getattr(e, "url", None),
            user=getattr(e, "user", None),
            language=getattr(e, "language", None),
            custom_emoji_id=getattr(e, "custom_emoji_id", None),
        ))
    return shifted


def build_brand_footer() -> tuple:
    """يبني تذييل العلامة التجارية (اسم أزرق قابل للضغط + رابط «السحوبات» بجانبه)
    المستخدم في نهاية منشورات القناة (السحب والمسابقة)."""
    return build_text_with_emojis([
        "\n\n",
        *build_brand_giveaways_parts(),
    ])


def build_contest_channel_message(cliche_text: str, cliche_entities, target_count: int,
                                   end_type: str, time_minutes: int, votes_target: int = None) -> tuple:
    """
    منشور المسابقة الذي يُنشر في القناة/القروب المحدد (صورة image 2):
    - كليشة المسابقة كما أرسلها صاحب المسابقة (بتنسيقاتها الأصلية).
    - عدد المشاركين المسموح بخط عريض.
    - تعليمات التسجيل داخل اقتباس ملوّن منفصل.
    - وقت انتهاء المسابقة تلقائيًا داخل اقتباس ملوّن منفصل (إذا كان معتمدًا على الوقت)،
      أو عدد الأصوات الذي تنتهي عنده المسابقة (إذا كان معتمدًا على عدد الأصوات).
    - تذييل باسم العلامة التجارية بلون أزرق قابل للضغط.
    """
    extra_parts = [
        "\n\n",
        ([f"عدد المشاركين المسموح : {target_count}"], "bold", None),
        "\n\n",
        (["لتسجيل اسمك في المسابقة اضغط على زر المشاركة في المسابقة بأسفل المنشور  ”"], "blockquote", None),
    ]
    if end_type == "time" and time_minutes:
        extra_parts.append("\n\n")
        extra_parts.append(([f"سيتم انتهاء المسابقة بعد {format_minutes_label(time_minutes)}  ”"], "blockquote", None))
    elif end_type == "votes" and votes_target:
        extra_parts.append("\n\n")
        extra_parts.append(([
            f"ستنتهي المسابقة عند وصول أحد المتسابقين إلى {votes_target} صوت  ”",
        ], "blockquote", None))

    extra_text, extra_entities = build_text_with_emojis(extra_parts)
    footer_text, footer_entities = build_brand_footer()

    base_text = cliche_text or ""
    base_entities = list(cliche_entities or [])
    shift = utf16_len(base_text)
    footer_shift = utf16_len(base_text + extra_text)

    combined_text = base_text + extra_text + footer_text
    combined_entities = (
        base_entities
        + shift_entities(extra_entities, shift)
        + shift_entities(footer_entities, footer_shift)
    )
    return combined_text, combined_entities


def build_contest_channel_keyboard(contest_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "✅ المشاركة في المسابقة",
            url=f"https://t.me/{BOT_USERNAME}?start=compjoin_{contest_code}",
            style="success",
        )],
    ])


ARABIC_ORDINALS = [
    "الأول", "الثاني", "الثالث", "الرابع", "الخامس",
    "السادس", "السابع", "الثامن", "التاسع", "العاشر",
]

MEDAL_EMOJI_BY_RANK = {1: EMOJI["medal"], 2: EMOJI["medal"], 3: EMOJI["medal"]}


def format_votes_label(votes: int) -> str:
    return f"{votes} صوت"


def build_contest_ended_message(cliche_text: str, cliche_entities, winners: list) -> tuple:
    """
    رسالة نهاية المسابقة — تُنشر كمنشور جديد منفصل (لا تُستبدل الرسالة القديمة):
    - عنوان «🏆 انتهت المسابقة!» داخل اقتباس (بخط عريض).
    - سطر لكل فائز: «الفائز 🥇 : [الاسم بلون أزرق قابل للضغط]  (X صوت)» — كل شيء بخط عريض،
      واسم الفائز رابط أزرق (TEXT_LINK) يشير إلى حساب الفائز الفعلي (وليس @يوزرنيم).
    winners: قائمة (user_id, display_name, participant_code, votes).
    """
    parts = [
        ([("🏆", EMOJI["trophy_win"]), " انتهت المسابقة!  ”"], "blockquote", None),
    ]

    if not winners:
        parts.append("\n\n")
        parts.append((["⚠️ لم يشارك أحد في هذه المسابقة، لم يتم اختيار فائز."], "bold", None))
    elif len(winners) == 1:
        user_id, name, _, votes = winners[0]
        parts.append("\n\n")
        parts.append(([
            "الفائز ",
            ("🥇", EMOJI["medal"]),
            " : ",
            (name, "mention_id", user_id),
            f"  ({format_votes_label(votes)})",
        ], "bold", None))
    else:
        for i, (user_id, name, _, votes) in enumerate(winners):
            ordinal = ARABIC_ORDINALS[i] if i < len(ARABIC_ORDINALS) else f"رقم {i + 1}"
            parts.append("\n\n")
            parts.append(([
                f"الفائز {ordinal} ",
                ("🥇", EMOJI["medal"]),
                " : ",
                (name, "mention_id", user_id),
                f"  ({format_votes_label(votes)})",
            ], "bold", None))

    combined_text, combined_entities = build_text_with_emojis(parts)
    return combined_text, combined_entities


def build_contest_ended_keyboard(contest_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "عرض النتائج", callback_data=f"comp_view_results:{contest_code}",
            style="success",
        )],
    ])


def build_contest_results_message(leaderboard: list, winners_count: int) -> tuple:
    """رسالة النتائج الكاملة (ترتيب جميع المتسابقين) — تُعرض عند الضغط على «عرض النتائج»."""
    parts = [
        ([("📊", EMOJI["chart"]), " النتائج الكاملة للمسابقة"], "bold", None),
    ]
    if not leaderboard:
        parts.append("\n\n")
        parts.append((["⚠️ لا يوجد أي متسابق مسجّل في هذه المسابقة."], "bold", None))
    else:
        bq_parts = []
        for i, (user_id, name, _, votes) in enumerate(leaderboard):
            rank = i + 1
            crown = "🏆 " if rank <= winners_count else ""
            bq_parts.append(f"{crown}({rank}) ")
            bq_parts.append((name, "mention_id", user_id))
            bq_parts.append(f" — {format_votes_label(votes)}")
            if i == 0:
                bq_parts.append("  ”\n")
            elif i != len(leaderboard) - 1:
                bq_parts.append("\n")
        parts.append("\n\n")
        parts.append(([(bq_parts, "bold", None)], "blockquote", None))
    return build_text_with_emojis(parts)


def build_contest_join_confirm_message(display_name: str) -> tuple:
    """رسالة «🎯 تأكيد المشاركة في المسابقة» (صورة image 3)."""
    parts = [
        ([("🎯", EMOJI["target_pin"]), " تأكيد المشاركة في المسابقة"], "bold", None),
        "\n\n",
        f"تريد المشاركة في المسابقة باسم: {display_name}",
        "\n\n",
        "هل أنت متأكد؟",
    ]
    return build_text_with_emojis(parts)


def build_contest_join_confirm_keyboard(contest_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "رفض", callback_data=f"comp_reject_join:{contest_code}",
                style="danger", **emoji_kwargs("remind_off"),
            ),
            InlineKeyboardButton(
                "قبول", callback_data=f"comp_confirm_join:{contest_code}",
                style="success", **emoji_kwargs("join_accept_btn"),
            ),
        ],
    ])


def build_contest_channel_gate_message() -> tuple:
    """رسالة «يجب الانضمام إلى قناة المسابقة أولاً» — لا تُعرض إلا عند اكتشاف
    أن المستخدم غير مشترك فعليًا في القناة التي نُشرت فيها المسابقة (فحص
    خلفي تلقائي)، ولا تظهر أبدًا ضمن رسالة المسابقة أو أي شروط دائمة أخرى."""
    parts = [
        "يجب عليك الانضمام إلى قناة المسابقة أولاً",
        "\n",
        "- لتتمكن من المشاركة في المسابقة : ",
        ("🏁", EMOJI["target_pin"]),
        "\n",
        ([
            ("‼️", EMOJI["sub_alert"]),
            " | انضم ثم اضغط تحقق",
            ("✅", EMOJI["sub_check"]),
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_contest_channel_gate_keyboard(contest_code: str, join_url: str) -> InlineKeyboardMarkup:
    """كيبورد بوابة شرط قناة المسابقة: زر «انضم إلى القناة» (إن توفّر رابط) +
    زر «تحقق ✅» الذي يعيد فحص العضوية فعليًا (بدون كاش) قبل إكمال المشاركة."""
    rows = []
    if join_url:
        rows.append([InlineKeyboardButton("📢 انضم إلى القناة", url=join_url)])
    rows.append([
        InlineKeyboardButton("تحقق ✅", callback_data=f"compjoinchk:{contest_code}"),
    ])
    return InlineKeyboardMarkup(rows)


def build_contest_registered_message(display_name: str, participant_code: str) -> tuple:
    """رسالة تأكيد التسجيل مع كود المتسابق (صورة image 4) — عناوين الأقسام داخل اقتباس ملوّن."""
    parts = [
        ([("✅", EMOJI["confirm_check"]), f" تم تسجيل مشاركتك في المسابقة بإسم : {display_name}"], "bold", None),
        "\n\n",
        (["🎟 كود المتسابق الخاص بك:"], "bold", None),
        f"\n{participant_code}",
        "\n\n",
        (["كيفية استخدام كود المتسابق:  ”"], "blockquote", None),
        "\n\n",
        ("❶", EMOJI["num_one"]),
         " افتح بوت ",
         (BRAND_NAME, "link", BRAND_URL),
         f" @{BOT_USERNAME} وأنشئ روليت جديد.",
        "\n\n",
        ("❷", EMOJI["num_two"]),
        " اختر شرط السحب: التصويت للمتسابق ثم أدخل الكود الخاص بك.",
        "\n\n",
        (["مميزات الكود :  ”"], "blockquote", None),
        "\n\n",
        ("✅", EMOJI["confirm_check"]),
        " يمنع أي شخص من المشاركة في السحب قبل أن يصوّت لك وهذا يزيد عدد المصوتين لصالحك.",
        "\n\n",
        ("✅", EMOJI["confirm_check"]),
        " يمكنك إعطاء الكود لصديق وسيتمكن من عمل سحب في قناته بشرط التصويت لك وسيُسجَّل التصويت باسمك.",
        "\n\n",
        ("✅", EMOJI["confirm_check"]),
        " كل استخدام للكود يرفع فرصك في الفوز بالمسابقة وجميع السحوبات المرتبطة بها.",
    ]
    return build_text_with_emojis(parts)


def build_contest_registered_keyboard(contest_code: str, user_id: int, participant_code: str) -> InlineKeyboardMarkup:
    try:
        copy_btn = InlineKeyboardButton(
            "انسخ كود المسابقة",
            copy_text=CopyTextButton(text=participant_code),
            style="success",
        )
    except Exception:
        copy_btn = InlineKeyboardButton("🎟 كودك: " + participant_code, callback_data="noop")
    return InlineKeyboardMarkup([
        [copy_btn],
        [InlineKeyboardButton(
            "سحب اسمي من المسابقه", callback_data=f"comp_withdraw:{contest_code}:{user_id}",
            style="danger", **emoji_kwargs("withdraw_btn"),
        )],
    ])


def build_contest_vote_post_message(display_name: str) -> tuple:
    """المنشور الذي يُنشر في القناة/القروب عند تسجيل متسابق جديد (صورة image 5)."""
    parts = [f"{display_name} : المتسابق"]
    return build_text_with_emojis(parts)


def build_contest_vote_keyboard(contest_code: str, participant_id: int, votes: int,
                                 participant_code: str) -> InlineKeyboardMarkup:
    try:
        copy_btn = InlineKeyboardButton(
            "نسخ كود المتسابق",
            copy_text=CopyTextButton(text=participant_code),
            style="success",
        )
    except Exception:
        copy_btn = InlineKeyboardButton("🎟 كود المتسابق: " + participant_code, callback_data="noop")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🤍 {votes}",
            url=f"https://t.me/{BOT_USERNAME}?start=compvote_{contest_code}_{participant_id}",
            style="primary",
        )],
        [copy_btn],
    ])


def build_contest_vote_premium_blocked_message() -> tuple:
    """رسالة تُعرض لمستخدم غير مفعّل بريميوم عند محاولته التصويت في مسابقة
    مخصّصة حصريًا لمصوّتي تيليجرام بريميوم."""
    parts = [
        ([("💎", EMOJI.get("premium_vote_btn", "💎")),
          " هذه المسابقة تتيح التصويت فقط لمستخدمي تيليجرام المميز Premium."],
         "bold", None),
    ]
    return build_text_with_emojis(parts)


def build_contest_vote_gate_message() -> tuple:
    """رسالة بوابة الشرط الإلزامي قبل احتساب أي تصويت: يجب الاشتراك في
    القناة الإلزامية أولاً، ثم الضغط على زر «تحقق» لإكمال التصويت."""
    parts = [
        "للتصويت في هذه المسابقة عليك أولاً:",
        "\n\n",
        ([
            (" 1️⃣ ", None), "الاشتراك في القناة الإلزامية أدناه", "\n",
            (" 2️⃣ ", None), "ثم الضغط على زر «تحقق ✅» لإتمام تصويتك",
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_contest_vote_gate_keyboard(contest_code: str, participant_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(REQUIRED_CHANNEL_BUTTON_TEXT, url=get_required_channel_url())],
        [InlineKeyboardButton(
            "تحقق ✅", callback_data=f"compcond:{contest_code}:{participant_id}", style="success",
        )],
    ])


def build_vote_captcha_message(target_emoji_id: str) -> tuple:
    """رسالة الكابتشا التي تُعرض للمستخدم عند محاولة التصويت لمتسابق (تحقق أنك لست روبوت)."""
    parts = [
        "🤖 للتحقق انك لست روبوت للتصويت اضغط على الرمز:",
        "\n\n",
        ("🔘", target_emoji_id),
    ]
    return build_text_with_emojis(parts)


def build_vote_captcha_keyboard(token: str, option_ids: list, correct_index: int,
                                 prefix: str = "compcap") -> InlineKeyboardMarkup:
    """
    يبني صف واحد من 3 أزرار إيموجي عشوائية (مطابق تمامًا لشكل كابتشا تيليجرام)،
    حيث يمثّل كل زر رمزًا مختلفًا وزر واحد فقط (عند correct_index) هو الرمز الصحيح.

    ملاحظة مهمة: هذه الدالة تُستخدم لبناء كابتشا التصويت في المسابقات (compcap)
    وأيضًا كابتشا منع الرشق في السحوبات (gwcap). كانت تُبنى دائمًا ببادئة "compcap"
    ثابتة بغض النظر عن السياق، فكانت أزرار كابتشا السحب تُرسل بيانات "compcap:..."
    فتُعالَج بواسطة hander كابتشا التصويت (الذي يبحث عن الجلسة في
    context.user_data["vote_captchas"]) بدل هاندلر كابتشا السحب (الذي يخزّن
    الجلسة في context.user_data["gw_captchas"]) — فتُعتبر الجلسة "غير موجودة"
    فورًا ويظهر خطأ "انتهت صلاحية هذا التحقق" حتى لو كانت الكابتشا جديدة تمامًا.
    الحل: تمرير بادئة مختلفة (prefix) حسب السياق حتى تُطابق كل كابتشا الهاندلر
    الصحيح الخاص بها.
    """
    row = [
        InlineKeyboardButton(
            "◻️",
            callback_data=f"{prefix}:{token}:{idx}",
            icon_custom_emoji_id=emoji_id,
        )
        for idx, emoji_id in enumerate(option_ids)
    ]
    return InlineKeyboardMarkup([row])


def build_vote_captcha_success_message() -> tuple:
    parts = [
        ([("✅", EMOJI["confirm_check"]), " تم التحقق وتسجيل تصويتك بنجاح!"], "bold", None),
    ]
    return build_text_with_emojis(parts)


def build_vote_captcha_wrong_alert() -> str:
    return "❌ رمز غير صحيح، حاول اختيار الرمز الصحيح مرة أخرى."


QUICK_ROULETTE_TEXT = (
    "🎡 قسم روليت سريع\n\n"
    "• انشاء روليت: انشاء روليت سريع\n"
    "• الاعدادات: تحكم في اعدادة اللعبة\n\n"
    "• اختر ماتريد من الازرار ادناه ⬇️"
)

def _roulette_progress_bar(current: int, target: int, length: int = 10) -> str:
    """يبني شريط تقدّم مرئي بسيط (مربعات ملوّنة) لعدد المشاركين الحاليين
    مقابل العدد المطلوب، يُستخدم في منشور «روليت سريع» ليبدو أكثر احترافية."""
    if target <= 0:
        return ""
    ratio = min(1.0, current / target)
    filled = min(length, round(length * ratio))
    return "🟩" * filled + "⬜️" * (length - filled)


def build_quick_roulette_channel_message(target: int, current: int) -> tuple:
    """رسالة «روليت سريع» الاحترافية التي تُنشر عبر الوضع المضمّن (inline) في
    القناة/القروب، وتُحدَّث في نفس الرسالة عند كل مشاركة جديدة. تتضمّن كليشة
    اللعبة، عداد المشاركين مع شريط تقدّم داخل اقتباس مميّز، وتذييل العلامة
    التجارية الموحّد (نفس تذييل منشورات السحب/المسابقة)."""
    cliche = get_setting("game_cliche") or DEFAULT_GAME_CLICHE
    bar = _roulette_progress_bar(current, target)
    parts = [
        ([("🎡", EMOJI["roulette"]), " روليت سريع"], "bold", None),
        "\n\n",
        cliche,
        "\n\n",
        ([
            ("👥", EMOJI["people"]),
            f" المشاركين: {current}/{target}",
            "\n",
            bar,
        ], "blockquote", None),
    ]
    base_text, base_entities = build_text_with_emojis(parts)
    footer_text, footer_entities = build_brand_footer()
    shift = utf16_len(base_text)
    combined_text = base_text + footer_text
    combined_entities = base_entities + shift_entities(footer_entities, shift)
    return combined_text, combined_entities


def build_quick_roulette_join_notify_message(display_name: str) -> tuple:
    """رسالة مختصرة تُرسل لمالك الروليت السريع فقط عند انضمام مشارك جديد —
    الاسم فقط دون أي تفاصيل إضافية (آيدي/يوزر/عدد المشاركين)."""
    parts = [
        ([("🎡", EMOJI["roulette"]), f" قام شخص بالاشتراك في روليتك: {display_name}"], "bold", None),
    ]
    return build_text_with_emojis(parts)



def build_waiting_spin_message(target: int, current: int, participants: list) -> tuple:
    """
    participants: قائمة من tuples (user_id, display_name)
    """
    hide = get_setting("hide_participants") == "1"
    parts = [
        ("⧉ اكتمل العدد\n\n", "bold", None),
        ([
            ("👥", EMOJI["people"]),
            f" المشاركين: {current}/{target}  ”"
        ], "blockquote", None),
        "\n\n"
    ]

    if not hide and participants:
        parts.append(("🫧 قائمة المشاركين:\n", "bold", None))
        bq_parts = []
        for i, (uid, name) in enumerate(participants):
            suffix = '  ”\n' if i == 0 else '\n'
            if i == len(participants) - 1:
                suffix = suffix.rstrip('\n')
            bq_parts.append(f"- المشارك ({i + 1}) : ")
            bq_parts.append((name, "mention_id", uid))
            bq_parts.append(suffix)
        parts.append((bq_parts, "blockquote", None))
        parts.append("\n\n")

    parts.append(([
        ("🎯", EMOJI["target"]),
        " في انتظار تدوير الروليت  ”"
    ], "blockquote", None))

    return build_text_with_emojis(parts)

def build_result_message(winner_id: int, winner_name: str, participants: list) -> tuple:
    hide = get_setting("hide_participants") == "1"
    parts = [
        ("• تم اختيار الفائز ", "bold", None), ("🥳", EMOJI["party"]), "\n\n",
        ([
            ("🏆", EMOJI["trophy_win"]),
            " الفائز : ",
            (winner_name, "mention_id", winner_id),
            " ",
            ("🥇", EMOJI["medal"]),
            "  ”"
        ], "blockquote", None),
        "\n\n"
    ]

    if not hide and participants:
        parts.append((f"🔹 جميع المشاركين ({len(participants)}):\n", "bold", None))
        bq_parts = []
        for i, (uid, name) in enumerate(participants):
            suffix = '  ”\n' if i == 0 else '\n'
            if i == len(participants) - 1:
                suffix = suffix.rstrip('\n')
            bq_parts.append(f"- المشارك ({i + 1}) : ")
            bq_parts.append((name, "mention_id", uid))
            bq_parts.append(suffix)
        parts.append((bq_parts, "blockquote", None))
        parts.append("\n\n")

    parts += build_brand_giveaways_parts()
    return build_text_with_emojis(parts)

def waiting_spin_keyboard(roulette_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔷 تدوير الروليت 🔷", callback_data=f"rr_spin_{roulette_id}", style="danger")],
    ])

def result_keyboard(roulette_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("↻ اختيار فائز آخر", callback_data=f"rr_respin_{roulette_id}", style="danger")],
        [InlineKeyboardButton("↻ لعب مره اخرى", switch_inline_query="", style="success")],
    ])

def build_giveaway_target_message() -> tuple:
    """شاشة «يرجى تحديد القناة أو القروب للسحب» (Image 1)."""
    parts = [
        ([
            "يرجى تحديد القناة أو القروب للسحب ",
            ("🎯", EMOJI["target_pin"]),
        ], "bold", None),
        "\n\n",
        ([
            "تأكد أولاً أنك مشرف في القناة أو الجروب وأن البوت أيضاً مشرف.",
        ], "blockquote", None),
        "\n\n",
        ([
            "إذا لم تظهر القناة أو الجروب وتأكدت أن البوت موجود كـ «مشرف» وأنت كذلك، يمكنك تسجيله يدوياً من الأسفل ",
            ("⏬", EMOJI["arrow_down"]),
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_giveaway_target_keyboard(owner_id: int = None) -> InlineKeyboardMarkup:
    rows = []
    if owner_id is not None:
        for chat in get_registered_chats(owner_id):
            title = chat["chat_title"] or str(chat["chat_id"])
            rows.append([InlineKeyboardButton(
                title, callback_data=f"gw_sel:{chat['chat_id']}",
            )])
    rows.append([
        InlineKeyboardButton(
            "تسجيل قناة", callback_data="gw_reg_channel",
            style="primary", **emoji_kwargs("register_plus"),
        ),
        InlineKeyboardButton(
            "تسجيل جروب", callback_data="gw_reg_group",
            style="primary", **emoji_kwargs("register_plus"),
        ),
    ])
    rows.append([InlineKeyboardButton(
        "حذف قناة", callback_data="gw_del_channels",
        style="danger", **emoji_kwargs("delete_all_btn"),
    )])
    rows.append([InlineKeyboardButton(
        "رجوع", callback_data="back_main_menu",
        style="danger", **emoji_kwargs("back_section_btn"),
    )])
    return InlineKeyboardMarkup(rows)


def build_giveaway_delete_message() -> tuple:
    parts = [
        (["🗑️ حذف قناة أو مجموعة"], "bold", None),
        "\n\n",
        "اضغط على 🗑️ لحذف:",
    ]
    return build_text_with_emojis(parts)


def build_giveaway_delete_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    rows = []
    for chat in get_registered_chats(owner_id):
        title = chat["chat_title"] or str(chat["chat_id"])
        rows.append([
            InlineKeyboardButton(title, callback_data="gw_noop"),
            InlineKeyboardButton("🗑️", callback_data=f"gw_delc:{chat['chat_id']}"),
        ])
    rows.append([InlineKeyboardButton(
        "رجوع", callback_data="gw_start_create",
        style="danger", **emoji_kwargs("back_section_btn"),
    )])
    return InlineKeyboardMarkup(rows)


def build_back_to_giveaway_keyboard() -> InlineKeyboardMarkup:
    return _build_single_back_keyboard("رجوع", "gw_start_create", "danger", "back_section_btn")


GW_LIST_PAGE_SIZE = 8


def build_my_giveaways_list_message(page: int, total_pages: int) -> tuple:
    """شاشة «سحوباتي»: تعرض رقم الصفحة الحالية من إجمالي الصفحات."""
    parts = [
        ([("🎁", EMOJI["draws_check"]), " سحوباتي"], "bold", None),
        "\n\n",
        ([
            f"كل سحوباتك • صفحة {page}/{total_pages}", "\n",
            "اختر سحبًا لعرض تفاصيله:",
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_my_giveaways_list_keyboard(giveaways, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """
    أزرار مرقّمة (زر لكل سحب) مع نقطة ملوّنة تدل على حالته (🟢 نشط / 🔴 متوقف).
    عند كثرة السحوبات تُقسَّم تلقائيًا إلى صفحات (GW_LIST_PAGE_SIZE في كل صفحة)
    مع صف تنقّل «السابق / التالي» حتى لا تتكدّس القائمة.
    """
    start = (page - 1) * GW_LIST_PAGE_SIZE
    page_items = giveaways[start:start + GW_LIST_PAGE_SIZE]

    rows = []
    for offset, gw in enumerate(page_items):
        index = start + offset + 1
        dot = "🟢" if gw["status"] == "open" else "🔴"
        rows.append([InlineKeyboardButton(
            f"{dot} #{index}", callback_data=f"gwmy_detail:{gw['gw_code']}:{page}",
        )])

    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("◀️ السابق", callback_data=f"gwmy_page:{page - 1}"))
        nav_row.append(InlineKeyboardButton(f"صفحة {page}/{total_pages}", callback_data="gw_noop"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("التالي ▶️", callback_data=f"gwmy_page:{page + 1}"))
        rows.append(nav_row)

    rows.append([InlineKeyboardButton(
        "رجوع", callback_data="back_main_menu",
        style="danger", **emoji_kwargs("back_section_btn"),
    )])
    return InlineKeyboardMarkup(rows)


def build_my_giveaway_detail_message(giveaway, index: int, channel_title: str,
                                      participants_total: int, new_rewarded_count: int) -> tuple:
    """شاشة تفاصيل سحب واحد من «سحوباتي»."""
    status_line = "🟢 نشط" if giveaway["status"] == "open" else "🔴 متوقف"
    parts = [
        ([
            f"🎁 السحب #{index}",
            "\n\n",
            f"👥 عدد المشاركين الكلي : {participants_total}", "\n",
            f"🏆 عدد الفائزين : {giveaway['winners_count']}", "\n",
            f"📊 الحالة : {status_line}", "\n",
            f"✨ مشاركون جدد احتُسبت نقاطهم : {new_rewarded_count}", "\n",
            f"📢 القناة : {channel_title}",
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_my_giveaway_detail_keyboard(page: int) -> InlineKeyboardMarkup:
    """زر «رجوع» فقط، يعيد المستخدم لنفس صفحة القائمة التي جاء منها."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "رجوع", callback_data=f"gwmy_page:{page}",
            style="danger", **emoji_kwargs("back_section_btn"),
        )],
    ])


def build_giveaway_cliche_message() -> tuple:
    parts = [
        ([
            ("📨", EMOJI["envelope_klesha"]),
            " أرسل كليشة السحب",
        ], "bold", None),
        "\n\n",
        "اكتب نص السحب الذي تريد نشره في القناة.\n"
        "يمكنك استخدام تنسيقات تيليجرام مثل:\n",
        "• ", ("نص عريض", "bold", None), "\n",
        "• ", ("نص مائل", "italic", None), "\n",
        "• ", ("نص مشوش", "spoiler", None), "\n",
        ([("🆕", EMOJI["new_badge"]), " يمكنك وضع رابط داخل النص"], "link", "https://t.me"),
        "\n",
        (["نص مقتبس  ”"], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_giveaway_cliche_keyboard() -> InlineKeyboardMarkup:
    return build_back_to_giveaway_keyboard()


GIVEAWAY_SETTINGS_DEFAULTS = {
    "gw_boost": False,
    "gw_premium": False,
    "gw_antispam": False,
    "gw_vote_contest_code": None,
    "gw_vote_participant_id": None,
    "gw_vote_participant_code": None,
    "gw_vote_display_name": None,
    "gw_condition_channels": [],
    "gw_autospin_mode": None,
    "gw_autospin_target": None,
    "gw_autospin_minutes": None,
}

GW_CONDITION_CHANNELS_MAX = 2
GW_CONDITION_CIRCLE_NUMS = ["❶", "❷", "❸"]


def build_giveaway_settings_message() -> tuple:
    parts = [
        ([("⚙️", EMOJI["target"]), " إعدادات السحب"], "bold", None),
        "\n\n",
        (["اختر شرطًا لتحسين السحب:"], "blockquote", None),
        "\n\n",
        ("1️⃣", EMOJI["num_one"]), " قناة شرط: الاشتراك في قناة محددة", "\n",
        ("2️⃣", EMOJI["num_two"]), " تعزيز القناة: تعزيز قناتك", "\n",
        ("3️⃣", EMOJI["num_three"]), " التصويت: التصويت لمتسابق معين", "\n",
        ("4️⃣", EMOJI["num_four"]), " مشتركون مميزون: للمشتركين المميزين", "\n",
        ("5️⃣", EMOJI["num_five"]), " منع الرشق: حماية السحب من الرشق", "\n",
        ("6️⃣", EMOJI["num_six"]), " سحب تلقائي: عند اكتمال العدد أو انتهاء الوقت",
        "\n\n",
        ([
            "• اختر الشرط الذي تريده من الأزرار أدناه ",
            ("⏬", EMOJI["arrow_down"]),
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_giveaway_settings_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    def toggle_btn(label: str, flag: bool, callback_data: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            f"{label} : {'نعم' if flag else 'لا'}",
            callback_data=callback_data,
            style="success" if flag else "danger",
            **emoji_kwargs("yes_btn" if flag else "no_btn"),
        )

    boost = user_data.get("gw_boost", GIVEAWAY_SETTINGS_DEFAULTS["gw_boost"])
    premium = user_data.get("gw_premium", GIVEAWAY_SETTINGS_DEFAULTS["gw_premium"])
    antispam = user_data.get("gw_antispam", GIVEAWAY_SETTINGS_DEFAULTS["gw_antispam"])

    vote_contest_code = user_data.get("gw_vote_contest_code")
    vote_participant_id = user_data.get("gw_vote_participant_id")
    if vote_contest_code and vote_participant_id:
        vote_display_name = user_data.get("gw_vote_display_name") or "متسابق"
        votes = get_participant_votes(vote_contest_code, vote_participant_id)
        vote_btn = InlineKeyboardButton(
            f"🤍 {votes}   {vote_display_name}", callback_data="gw_opt_vote",
            style="success", **emoji_kwargs("gw_vote_icon"),
        )
    else:
        vote_btn = InlineKeyboardButton("تصويت متسابق", callback_data="gw_opt_vote",
                                         style="primary", **emoji_kwargs("gw_vote_icon"))

    condition_channels = user_data.get("gw_condition_channels") or []
    if condition_channels:
        label = condition_channels[0]["title"]
        extra = len(condition_channels) - 1
        if extra > 0:
            label = f"{label} +{extra}"
        condition_btn = InlineKeyboardButton(
            label, callback_data="gw_opt_condition",
            style="success", **emoji_kwargs("gw_condition_channel"),
        )
    else:
        condition_btn = InlineKeyboardButton(
            "قناة شرط", callback_data="gw_opt_condition",
            style="primary", **emoji_kwargs("gw_condition_channel"),
        )

    autospin_mode = user_data.get("gw_autospin_mode", GIVEAWAY_SETTINGS_DEFAULTS["gw_autospin_mode"])
    if autospin_mode == "count" and user_data.get("gw_autospin_target"):
        autospin_label = f"سحب تلقائي: {user_data['gw_autospin_target']} مشترك"
        autospin_btn = InlineKeyboardButton(
            autospin_label, callback_data="gw_opt_autospin",
            style="success", **emoji_kwargs("target_pin"),
        )
    elif autospin_mode == "time" and user_data.get("gw_autospin_minutes"):
        autospin_label = f"سحب تلقائي: {format_duration_label(user_data['gw_autospin_minutes'])}"
        autospin_btn = InlineKeyboardButton(
            autospin_label, callback_data="gw_opt_autospin",
            style="success", **emoji_kwargs("gw_atime_clock"),
        )
    else:
        autospin_btn = InlineKeyboardButton(
            "سحب تلقائي", callback_data="gw_opt_autospin",
            style="primary", **emoji_kwargs("draws_check"),
        )

    return InlineKeyboardMarkup([
        [
            toggle_btn("تعزيز القناة", boost, "gw_toggle_boost"),
            condition_btn,
        ],
        [
            toggle_btn("مشتركين المميز", premium, "gw_toggle_premium"),
            vote_btn,
        ],
        [
            toggle_btn("منع الرشق", antispam, "gw_toggle_antispam"),
            autospin_btn,
        ],
        [InlineKeyboardButton(
            "نشر السحب", callback_data="gw_opt_create",
            style="success", **emoji_kwargs("yes_btn"),
        )],
        [InlineKeyboardButton(
            "رجوع", callback_data="gw_back_main",
            style="danger", **emoji_kwargs("back_section_btn"),
        )],
    ])


def build_giveaway_autospin_end_method_message() -> tuple:
    """شاشة «اختر طريقة انتهاء السحب» الخاصة بالسحب التلقائي (Image 2)."""
    parts = [
        (["اختر طريقة انتهاء السحب", ("❓", EMOJI["end_question"])], "bold", None),
        "\n\n",
        ([
            ("🎯", EMOJI["target_pin"]), " عدد محدد ", ("⚡️", EMOJI["gw_atime_lightning"]),
            " : ينتهي السحب تلقائيًا عند وصول عدد المشاركين إلى الرقم الذي تحدده",
        ], "blockquote", None),
        "\n\n",
        ([
            ("🕖", EMOJI["gw_atime_clock"]), " وقت محدد : ينتهي السحب عند انتهاء الوقت الذي "
            "تحدده ويتم اختيار الفائزين ", ("🏆", EMOJI["trophy_win"]),
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_giveaway_autospin_end_method_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "عدد محدد", callback_data="gw_atime_end_count",
                style="primary", **emoji_kwargs("target_pin"),
            ),
            InlineKeyboardButton(
                "وقت محدد", callback_data="gw_atime_end_time",
                style="primary", **emoji_kwargs("gw_atime_clock"),
            ),
        ],
        [InlineKeyboardButton(
            "رجوع للخيارات", callback_data="gw_back_to_options",
            style="danger", **emoji_kwargs("back_section_btn"),
        )],
    ])


def build_giveaway_autospin_count_message() -> tuple:
    """شاشة «أرسل عدد المشاركين المطلوب» لتفعيل السحب التلقائي لعدد محدد (Image 3)."""
    parts = [
        ([
            ("🎯", EMOJI["target_pin"]), " السحب التلقائي لـ عدد محدد",
        ], "bold", None),
        "\n\n",
        "أرسل عدد المشاركين المطلوب لبدء السحب تلقائياً",
        "\n\n",
        ([
            "مثال: إذا أردت تفعيل السحب التلقائي عند وصول عدد المشاركين إلى 100 "
            "أرسل الرقم 100",
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_giveaway_autospin_count_keyboard() -> InlineKeyboardMarkup:
    return _build_single_back_keyboard("رجوع للخيارات", "gw_atime_back", "danger", "back_section_btn")


def build_giveaway_autospin_time_message(selected_label: str = "غير محدد") -> tuple:
    """شاشة «السحب التلقائي لـ وقت محدود» بعرض قائمة الأوقات الجاهزة (Image 4)."""
    parts = [
        ([
            ("🕖", EMOJI["gw_atime_clock"]), " السحب التلقائي لـ وقت محدود",
        ], "bold", None),
        f"\nالوقت المختار: {selected_label}",
        "\n\n",
        "استخدم الأزرار أدناه لتحديد الوقت المطلوب لبدء السحب تلقائياً:",
    ]
    return build_text_with_emojis(parts)


def build_giveaway_autospin_time_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for row in CONTEST_TIME_OPTIONS:
        rows.append([
            InlineKeyboardButton(
                label, callback_data=f"gw_atime_set_{minutes}",
                style="primary", **emoji_kwargs("time_option_btn"),
            )
            for minutes, label in row
        ])
    rows.append([
        InlineKeyboardButton(
            "وقت مخصص", callback_data="gw_atime_show_custom",
            style="primary", **emoji_kwargs("time_manual_btn"),
        ),
    ])
    rows.append([
        InlineKeyboardButton(
            "رجوع", callback_data="gw_atime_back",
            style="danger", **emoji_kwargs("back_time_menu_btn"),
        )
    ])
    return InlineKeyboardMarkup(rows)


GW_AUTOSPIN_CUSTOM_STEPS = [
    [(-1, "- 1 دقيقة"), (1, "+ 1 دقيقة")],
    [(-5, "- 5 دقيقة"), (5, "+ 5 دقيقة")],
    [(-10, "- 10 دقايق"), (10, "+ 10 دقايق")],
    [(-60, "- 1 ساعة"), (60, "+ 1 ساعة")],
    [(-1440, "- 1 يوم"), (1440, "+ 1 يوم")],
]


def build_giveaway_autospin_custom_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for row in GW_AUTOSPIN_CUSTOM_STEPS:
        rows.append([
            InlineKeyboardButton(
                label, callback_data=f"gw_atime_custom_delta:{delta}",
                style="primary", **emoji_kwargs("time_option_btn"),
            )
            for delta, label in row
        ])
    rows.append([InlineKeyboardButton(
        "تأكيد الوقت", callback_data="gw_atime_custom_confirm",
        style="success", **emoji_kwargs("yes_btn"),
    )])
    rows.append([
        InlineKeyboardButton(
            "إعادة تعيين", callback_data="gw_atime_custom_reset",
            style="success", **emoji_kwargs("restore_defaults_btn"),
        ),
        InlineKeyboardButton(
            "رجوع للخيارات", callback_data="gw_back_to_options",
            style="danger", **emoji_kwargs("back_section_btn"),
        ),
    ])
    return InlineKeyboardMarkup(rows)


def build_giveaway_vote_code_message() -> tuple:
    """شاشة طلب كود المتسابق لجعل التصويت له شرطًا للمشاركة في السحب (Image 2)."""
    parts = [
        ([("📌", EMOJI["pin_note"]), " يرجى ارسال كود المتسابق الذي تريد جعله شرطًا"], "bold", None),
        "\n\n",
        ("📌", EMOJI["pin_note"]), " مثال على الكود: C12345678",
        "\n\n",
        (["⚠️ ملاحظة: لن يتمكن أي شخص من المشاركة في السحب قبل إتمام التصويت للمتسابق المحدد"],
         "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_giveaway_vote_code_keyboard() -> InlineKeyboardMarkup:
    return _build_single_back_keyboard("رجوع", "gw_back_to_options", "danger", "back_section_btn")


def build_giveaway_vote_code_error_message() -> tuple:
    """رسالة الخطأ عند إرسال كود متسابق غير صحيح أو مسابقة منتهية (Image 5)."""
    parts = [
        (["❌ كود المتسابق غير صحيح أو المسابقة انتهت!"], "bold", None),
        "\n\n",
        "تأكد من الكود وحاول مجدداً.",
    ]
    return build_text_with_emojis(parts)


def build_giveaway_vote_code_error_keyboard() -> InlineKeyboardMarkup:
    return build_giveaway_vote_code_keyboard()


def build_giveaway_vote_linked_message(participant_code: str) -> tuple:
    """رسالة تأكيد ربط كود المتسابق بشرط السحب بنجاح (Image 4)."""
    parts = [
        (["✅ تم ربط كود المتسابق:"], "bold", None),
        f"\n{participant_code}",
        "\n\n",
        "كل مشارك سيتحقق من تصويته قبل المشاركة في السحب.",
    ]
    return build_text_with_emojis(parts)


def build_giveaway_condition_type_message() -> tuple:
    """شاشة اختيار نوع «قناة الشرط»: عامة أو خاصة (Image 2)."""
    parts = [
        ([("📢", EMOJI["gw_condition_channel"]), " قناة الشرط"], "bold", None),
        "\n\n",
        "اختر نوع قناة الشرط:",
    ]
    return build_text_with_emojis(parts)


def build_giveaway_condition_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌐 قناة عامة", callback_data="gw_cond_public", style="primary"),
            InlineKeyboardButton("🔒 قناة خاصة", callback_data="gw_cond_private", style="primary"),
        ],
        [InlineKeyboardButton(
            "رجوع للخيارات", callback_data="gw_back_to_options",
            style="danger", **emoji_kwargs("back_section_btn"),
        )],
    ])


def build_giveaway_condition_public_message() -> tuple:
    """شاشة طلب يوزر القناة العامة (أو قناتين) لجعلها شرط اشتراك للمشاركة (Image 3)."""
    parts = [
        ([("📢", EMOJI["gw_condition_channel"]), " قناة الشرط العامة"], "bold", None),
        "\n\n",
        "الان ارسل لي يوزر قناة الشرط", "\n",
        "مثال @e_ggf",
        "\n\n",
        "لا تضف أي نص إضافي مع اليوزر",
        "\n\n",
        (["تأكد من إضافة البوت كمشرف في قناة الشرط مع صلاحية إدارة الأعضاء"],
         "blockquote", None),
        "\n\n",
        ([
            "يمكنك إضافة قناتين كحد أقصى، ويتم إدخال الأسماء بهذا الشكل:", "\n",
            "@e_ggf", "\n",
            "@n_bbo",
        ], "blockquote", None),
    ]
    return build_text_with_emojis(parts)


def build_giveaway_condition_public_keyboard() -> InlineKeyboardMarkup:
    return _build_single_back_keyboard("رجوع للخيارات", "gw_opt_condition", "danger", "back_section_btn")


def build_giveaway_condition_private_message(added_count: int = 0) -> tuple:
    """شاشة طلب توجيه رسالة من القناة الخاصة لجعلها شرط اشتراك للمشاركة.
    عند added_count == 1 (بعد إضافة أول قناة) تتحول الرسالة لعرض إمكانية إضافة
    قناة ثانية اختيارية أو إنهاء الآن بقناة واحدة فقط."""
    if added_count >= 1:
        parts = [
            ([("✅", EMOJI["sub_check"]), f" تم إضافة القناة الخاصة رقم {added_count} بنجاح"], "bold", None),
            "\n\n",
            "يمكنك إعادة توجيه رسالة من قناة خاصة ثانية (اختياري)، أو الضغط على «إنهاء» للاكتفاء بالقناة الحالية.",
        ]
    else:
        parts = [
            ([("📢", EMOJI["gw_condition_channel"]), " قناة الشرط الخاصة"], "bold", None),
            "\n\n",
            "الان قم بإعادة توجيه أي رسالة من قناتك الخاصة إلى هنا",
            "\n\n",
            (["تأكد من إضافة البوت كمشرف في القناة مع صلاحية إدارة الأعضاء، وأن تكون أنت مشرفًا فيها أيضًا"],
             "blockquote", None),
            "\n\n",
            (["يمكنك إضافة قناتين خاصتين كحد أقصى، بتوجيه رسالة من كل قناة على حدة"],
             "blockquote", None),
        ]
    return build_text_with_emojis(parts)


def build_giveaway_condition_private_keyboard(added_count: int = 0) -> InlineKeyboardMarkup:
    if added_count >= 1:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "إنهاء ✅", callback_data="gw_cond_private_done",
                style="success", **emoji_kwargs("yes_btn"),
            )],
            [InlineKeyboardButton(
                "رجوع للخيارات", callback_data="gw_opt_condition",
                style="danger", **emoji_kwargs("back_section_btn"),
            )],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "رجوع للخيارات", callback_data="gw_opt_condition",
            style="danger", **emoji_kwargs("back_section_btn"),
        )],
    ])


def build_giveaway_condition_error_message() -> tuple:
    """رسالة الخطأ عند تعذّر التحقق من قناة الشرط المُدخلة."""
    parts = [
        (["❌ تعذّر العثور على القناة أو أن البوت ليس مشرفًا فيها!"], "bold", None),
        "\n\n",
        "تأكد من اليوزر وأن البوت مضاف كمشرف بصلاحية إدارة الأعضاء، ثم حاول مجدداً.",
    ]
    return build_text_with_emojis(parts)


def build_giveaway_condition_max_error_message() -> tuple:
    """رسالة الخطأ عند إرسال أكثر من قناتين لشرط السحب."""
    parts = [
        (["❌ يمكنك إضافة قناتين كحد أقصى!"], "bold", None),
        "\n\n",
        "أرسل يوزر قناة واحدة أو قناتين فقط (كل يوزر في سطر منفصل).",
    ]
    return build_text_with_emojis(parts)


def build_giveaway_condition_linked_message(channel_titles) -> tuple:
    """رسالة تأكيد ربط قناة/قنوات الشرط بنجاح (Image 4)."""
    titles_line = "\n".join(channel_titles) if isinstance(channel_titles, (list, tuple)) else str(channel_titles)
    parts = [
        (["✅ تم اضافة قناة الشرط بنجاح"], "bold", None),
        f"\n{titles_line}",
        "\n\n",
        "كل مشارك سيتحقق من اشتراكه في القناة قبل المشاركة في السحب.",
