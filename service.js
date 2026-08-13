/**
 * TapEarn Backend — Express + Firebase Admin SDK
 * ------------------------------------------------
 * هذا السيرفر هو المكان الوحيد المسموح له بالكتابة على Firestore.
 * الواجهة الأمامية (index.html) لا تكتب على قاعدة البيانات مباشرة أبدًا.
 *
 * متغيرات البيئة المطلوبة على Railway (تبويب Variables):
 *  - BOT_TOKEN                : توكن بوت تيليجرام من BotFather
 *  - FIREBASE_SERVICE_ACCOUNT : محتوى ملف JSON الكامل (كنص) من
 *                                Firebase Console > Project settings > Service accounts
 *  - REWARD_PER_AD            : (اختياري) قيمة المكافأة لكل إعلان، افتراضي 0.002
 *  - DAILY_AD_LIMIT           : (اختياري) الحد اليومي للمشاهدات، افتراضي 20
 *  - MIN_WITHDRAW             : (اختياري) حد أدنى السحب، افتراضي 0.2
 */

const express = require("express");
const cors = require("cors");
const crypto = require("crypto");
const admin = require("firebase-admin");

// ---------- إعداد Firebase Admin ----------
const serviceAccountRaw = process.env.FIREBASE_SERVICE_ACCOUNT;
if (!serviceAccountRaw) {
  console.error("FIREBASE_SERVICE_ACCOUNT env var is missing.");
  process.exit(1);
}
const serviceAccount = JSON.parse(serviceAccountRaw);
admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
});
const db = admin.firestore();

// ---------- إعدادات عامة ----------
const BOT_TOKEN = process.env.BOT_TOKEN;
if (!BOT_TOKEN) {
  console.error("BOT_TOKEN env var is missing.");
  process.exit(1);
}
const REWARD_PER_AD = parseFloat(process.env.REWARD_PER_AD || "0.002");
const DAILY_AD_LIMIT = parseInt(process.env.DAILY_AD_LIMIT || "20", 10);
const MIN_WITHDRAW = parseFloat(process.env.MIN_WITHDRAW || "0.2");

const app = express();
app.use(cors());
app.use(express.json());

// =========================================================
// التحقق من صحة Telegram initData
// المرجع الرسمي: https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
// =========================================================
function verifyInitData(initData) {
  if (!initData) return null;

  const urlParams = new URLSearchParams(initData);
  const hash = urlParams.get("hash");
  if (!hash) return null;
  urlParams.delete("hash");

  const dataCheckArr = [];
  for (const [key, value] of [...urlParams.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    dataCheckArr.push(`${key}=${value}`);
  }
  const dataCheckString = dataCheckArr.join("\n");

  const secretKey = crypto.createHmac("sha256", "WebAppData").update(BOT_TOKEN).digest();
  const computedHash = crypto.createHmac("sha256", secretKey).update(dataCheckString).digest("hex");

  if (computedHash !== hash) return null;

  // تحقق اختياري إضافي: رفض initData أقدم من ساعة (يمنع إعادة استخدام قديمة)
  const authDate = parseInt(urlParams.get("auth_date") || "0", 10);
  const nowSeconds = Math.floor(Date.now() / 1000);
  if (nowSeconds - authDate > 3600) return null;

  const userJson = urlParams.get("user");
  if (!userJson) return null;
  return JSON.parse(userJson); // { id, first_name, username, ... }
}

// Middleware: يتحقق من initData ويحط user بالـ request
function requireTelegramAuth(req, res, next) {
  const initData = req.headers["x-telegram-init-data"] || (req.body && req.body.initData) || "";
  const user = verifyInitData(initData);
  if (!user) {
    return res.status(401).json({ error: "invalid or missing initData" });
  }
  req.tgUser = user;
  next();
}

function todayKey() {
  return new Date().toISOString().slice(0, 10); // YYYY-MM-DD (UTC)
}

// =========================================================
// POST /api/auth/verify
// يتحقق من initData وينشئ مستند المستخدم إذا ما كان موجود
// =========================================================
app.post("/api/auth/verify", requireTelegramAuth, async (req, res) => {
  try {
    const userId = String(req.tgUser.id);
    const ref = db.collection("users").doc(userId);
    const doc = await ref.get();

    if (!doc.exists) {
      await ref.set({
        firstName: req.tgUser.first_name || "",
        username: req.tgUser.username || "",
        balance: 0,
        viewsToday: 0,
        totalViews: 0,
        lastViewDate: todayKey(),
        referredBy: null,
        createdAt: admin.firestore.FieldValue.serverTimestamp(),
      });
    }

    const fresh = await ref.get();
    res.json({ ok: true, user: fresh.data() });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: "internal error" });
  }
});

// =========================================================
// POST /api/ads/confirm
// ⚠️ هذا endpoint مؤقت للتطوير. بالنشر الفعلي، يُستحسن استبداله
// أو تعزيزه بـ Reward Postback URL من AdsGram (server-to-server)
// حتى لا يعتمد منح المكافأة على حدث المتصفح فقط.
// =========================================================
app.post("/api/ads/confirm", requireTelegramAuth, async (req, res) => {
  try {
    const userId = String(req.tgUser.id);
    const ref = db.collection("users").doc(userId);

    await db.runTransaction(async (tx) => {
      const doc = await tx.get(ref);
      if (!doc.exists) throw new Error("user not found");
      const data = doc.data();

      // إعادة تصفير العداد اليومي إذا تغير اليوم
      const today = todayKey();
      let viewsToday = data.viewsToday || 0;
      if (data.lastViewDate !== today) viewsToday = 0;

      if (viewsToday >= DAILY_AD_LIMIT) {
        throw new Error("daily limit reached");
      }

      tx.update(ref, {
        balance: admin.firestore.FieldValue.increment(REWARD_PER_AD),
        viewsToday: viewsToday + 1,
        totalViews: admin.firestore.FieldValue.increment(1),
        lastViewDate: today,
      });
    });

    res.json({ ok: true });
  } catch (e) {
    console.error(e);
    res.status(400).json({ error: e.message || "could not confirm ad view" });
  }
});

// =========================================================
// POST /api/withdraw/request
// ينشئ طلب سحب بحالة "pending" فقط — لا تحويل تلقائي هنا.
// التنفيذ الفعلي (إرسال TON) يجب أن يتم يدويًا أو بمنطق منفصل
// تراجعه بنفسك قبل التنفيذ.
// =========================================================
app.post("/api/withdraw/request", requireTelegramAuth, async (req, res) => {
  try {
    const userId = String(req.tgUser.id);
    const { wallet, amount } = req.body;

    if (!wallet || typeof wallet !== "string") {
      return res.status(400).json({ error: "invalid wallet address" });
    }
    const amt = parseFloat(amount);
    if (!amt || amt < MIN_WITHDRAW) {
      return res.status(400).json({ error: `minimum withdraw is ${MIN_WITHDRAW} TON` });
    }

    const userRef = db.collection("users").doc(userId);

    await db.runTransaction(async (tx) => {
      const doc = await tx.get(userRef);
      if (!doc.exists) throw new Error("user not found");
      const balance = doc.data().balance || 0;
      if (amt > balance) throw new Error("insufficient balance");

      // خصم فوري لمنع طلبات سحب مكررة لنفس الرصيد
      tx.update(userRef, { balance: admin.firestore.FieldValue.increment(-amt) });

      const withdrawRef = db.collection("withdrawals").doc();
      tx.set(withdrawRef, {
        userId,
        wallet,
        amount: amt,
        status: "pending",
        createdAt: admin.firestore.FieldValue.serverTimestamp(),
      });
    });

    res.json({ ok: true, message: "withdraw request submitted" });
  } catch (e) {
    console.error(e);
    res.status(400).json({ error: e.message || "could not submit withdraw request" });
  }
});

// ---------- health check ----------
app.get("/", (req, res) => res.send("TapEarn backend is running."));

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Server listening on port ${PORT}`));
