import asyncio
import logging
import sqlite3
import time

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup,
)

# ===================== SOZLAMALAR =====================
TOKEN = "8790357902:AAFkyvhROq6aBHOOetGfkhn9fVJavRG0tU0"
ADMINS = [6177091474, 7447535432]          # 2 ta admin Telegram ID si

CARDS = [                                 # 2 ta karta
    "💳 4067 0700 0670 2752\n👤 NAMAZOVA Z (Humo)",
    "💳 4067 0700 0943 5236\n👤 RUSTAM S (Humo)",
]
CONTACTS = ["@sfrvvvv7", "@NAMAZOVw"]   # Aloqa uchun 2 ta username

# Hisob to'ldirilgach yuboriladigan havola (skin qo'yish yo'riqnomasi)
SKIN_GUIDE_LINK = "https://t.me/@skin_qoyish/1"

# Gold paketlari: nomi -> narxi (so'm)
PACKS = {
    100: 14990,
    500: 7000,
    1000: 145000,
}
MIN_TOPUP = 5000
DB_FILE = "bot.db"
# ======================================================

logging.basicConfig(level=logging.INFO)
router = Router()


# ----------------------- DATABASE -----------------------
db = sqlite3.connect(DB_FILE, check_same_thread=False)
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY, name TEXT, username TEXT,
    balance INTEGER DEFAULT 0, created INTEGER
);
CREATE TABLE IF NOT EXISTS topups(
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER,
    status TEXT DEFAULT 'pending', admin_id INTEGER, created INTEGER
);
CREATE TABLE IF NOT EXISTS orders(
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, gold INTEGER,
    price INTEGER, status TEXT DEFAULT 'waiting_skin',
    admin_id INTEGER, created INTEGER
);
""")
db.commit()


def q(sql, args=(), one=False):
    cur = db.execute(sql, args)
    db.commit()
    return cur.fetchone() if one else cur.fetchall()


def ensure_user(u):
    q("INSERT OR IGNORE INTO users(id,name,username,created) VALUES(?,?,?,?)",
      (u.id, u.full_name, u.username, int(time.time())))


def fmt(n):
    return f"{n:,}".replace(",", " ")


# ----------------------- KLAVIATURALAR -----------------------
MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💳 Hisobni to'ldirish"), KeyboardButton(text="🪙 Gold sotib olish")],
        [KeyboardButton(text="👤 Hisobim"), KeyboardButton(text="📞 Aloqa")],
    ],
    resize_keyboard=True,
)


def admin_kb(prefix, obj_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"{prefix}_ok_{obj_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"{prefix}_no_{obj_id}"),
    ]])


# ----------------------- HOLATLAR -----------------------
class TopUp(StatesGroup):
    amount = State()
    check = State()


class Buy(StatesGroup):
    skin = State()


# ----------------------- ASOSIY MENYU -----------------------
@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    ensure_user(m.from_user)
    await m.answer(
        "🔥 Standoff 2 Gold do'koniga xush kelibsiz!\nKerakli bo'limni tanlang 👇",
        reply_markup=MENU,
    )


# ----------------------- XABAR YUBORISH (faqat adminlar) -----------------------
@router.message(Command("xabar"), F.from_user.id.in_(ADMINS))
async def broadcast(m: Message, command: CommandObject, state: FSMContext, bot: Bot):
    """
    Ishlatish:
      /xabar Salom hammaga!        -> matn yuboradi
      (rasm/video/xabarga reply qilib) /xabar  -> o'sha xabarni nusxalab yuboradi
    """
    await state.clear()
    src = m.reply_to_message
    text = (command.args or "").strip()
    if not src and not text:
        return await m.answer("ℹ️ /xabar matn yozing yoki biror xabarga reply qilib /xabar yuboring.")

    users = q("SELECT id FROM users")
    total = len(users)
    status = await m.answer(f"📤 Yuborish boshlandi... 0/{total}")
    sent = blocked = failed = 0

    for i, row in enumerate(users, 1):
        uid = row["id"]
        for _ in range(2):  # flood bo'lsa bir marta qayta urinadi
            try:
                if src:
                    await bot.copy_message(uid, src.chat.id, src.message_id)
                else:
                    await bot.send_message(uid, text)
                sent += 1
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                continue
            except TelegramForbiddenError:
                blocked += 1   # foydalanuvchi botni bloklagan
            except Exception as e:
                failed += 1
                logging.warning("Xabar yuborilmadi %s: %s", uid, e)
            break
        await asyncio.sleep(0.05)  # ~20 xabar/soniya (Telegram limiti ichida)
        if i % 50 == 0:
            try:
                await status.edit_text(f"📤 Yuborilmoqda... {i}/{total}")
            except Exception:
                pass

    await status.edit_text(
        "✅ Xabar yuborish tugadi\n\n"
        f"👥 Jami foydalanuvchi: {total}\n"
        f"✅ Yetib bordi: {sent}\n"
        f"🚫 Botni bloklaganlar: {blocked}\n"
        f"❌ Boshqa xato: {failed}"
    )


@router.message(F.text == "📞 Aloqa")
async def contact(m: Message):
    await m.answer("📞 Aloqa uchun:\n" + "\n".join(CONTACTS))


@router.message(F.text == "👤 Hisobim")
async def profile(m: Message):
    ensure_user(m.from_user)
    u = q("SELECT * FROM users WHERE id=?", (m.from_user.id,), one=True)
    cnt = q("SELECT COUNT(*) c FROM orders WHERE user_id=? AND status='delivered'",
            (m.from_user.id,), one=True)["c"]
    await m.answer(
        f"👤 Hisobim\n\n🆔 ID: {u['id']}\n💰 Balans: {fmt(u['balance'])} so'm\n"
        f"📦 Yetkazilgan buyurtmalar: {cnt}"
    )


# ----------------------- HISOBNI TO'LDIRISH -----------------------
@router.message(F.text == "💳 Hisobni to'ldirish")
async def topup_start(m: Message, state: FSMContext):
    ensure_user(m.from_user)
    await state.set_state(TopUp.amount)
    await m.answer(f"💳 Qancha so'm to'ldirmoqchisiz? (kamida {fmt(MIN_TOPUP)})\n"
                   "Faqat raqam yozing. Bekor qilish: /start")


@router.message(TopUp.amount)
async def topup_amount(m: Message, state: FSMContext):
    if not (m.text and m.text.replace(" ", "").isdigit()):
        return await m.answer("❗ Faqat raqam yozing.")
    amount = int(m.text.replace(" ", ""))
    if amount < MIN_TOPUP:
        return await m.answer(f"❗ Minimal summa {fmt(MIN_TOPUP)} so'm.")
    await state.update_data(amount=amount)
    await state.set_state(TopUp.check)
    await m.answer(
        f"✅ Summa: {fmt(amount)} so'm\n\nQuyidagi kartalardan biriga o'tkazing:\n\n"
        + "\n\n".join(CARDS)
        + "\n\n📸 To'lov chekini (skrinshot) shu yerga yuboring."
    )


@router.message(TopUp.check, F.photo)
async def topup_check(m: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    amount = data["amount"]
    cur = db.execute("INSERT INTO topups(user_id,amount,created) VALUES(?,?,?)",
                     (m.from_user.id, amount, int(time.time())))
    db.commit()
    tid = cur.lastrowid
    caption = (f"💳 Yangi to'ldirish #{tid}\n👤 {m.from_user.full_name} "
               f"(@{m.from_user.username}) | ID: {m.from_user.id}\n"
               f"💰 Summa: {fmt(amount)} so'm")
    for admin in ADMINS:
        try:
            await bot.send_photo(admin, m.photo[-1].file_id, caption=caption,
                                 reply_markup=admin_kb("top", tid))
        except Exception as e:
            logging.warning("Adminga yuborilmadi %s: %s", admin, e)
    await state.clear()
    await m.answer("⏳ Chekingiz adminga yuborildi. Tasdiqlanishini kuting.", reply_markup=MENU)


@router.message(TopUp.check)
async def topup_check_bad(m: Message):
    await m.answer("❗ Iltimos, chekni rasm (skrinshot) ko'rinishida yuboring.")


@router.callback_query(F.data.startswith("top_"))
async def topup_admin(c: CallbackQuery, bot: Bot):
    if c.from_user.id not in ADMINS:
        return await c.answer("Siz admin emassiz", show_alert=True)
    _, action, tid = c.data.split("_")
    t = q("SELECT * FROM topups WHERE id=?", (tid,), one=True)
    if not t or t["status"] != "pending":
        return await c.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)

    if action == "ok":
        q("UPDATE topups SET status='approved', admin_id=? WHERE id=?", (c.from_user.id, tid))
        q("UPDATE users SET balance=balance+? WHERE id=?", (t["amount"], t["user_id"]))
        status = f"✅ Tasdiqlandi ({c.from_user.full_name})"
        await bot.send_message(
            t["user_id"],
            f"✅ Hisobingiz {fmt(t['amount'])} so'mga to'ldirildi!\n\n"
            f"📖 Skin qo'yish yo'riqnomasi:\n{SKIN_GUIDE_LINK}\n\n"
            "Endi «🪙 Gold sotib olish» bo'limiga o'ting.",
        )
    else:
        q("UPDATE topups SET status='rejected', admin_id=? WHERE id=?", (c.from_user.id, tid))
        status = f"❌ Rad etildi ({c.from_user.full_name})"
        await bot.send_message(t["user_id"], "❌ To'ldirish so'rovingiz rad etildi. "
                               "Muammo bo'lsa: " + ", ".join(CONTACTS))

    # Ikkala adminda ham tugmalar o'chadi / yangilanadi
    try:
        await c.message.edit_caption(caption=(c.message.caption or "") + f"\n\n{status}")
    except Exception:
        pass
    await c.answer("Bajarildi")


# ----------------------- GOLD SOTIB OLISH -----------------------
@router.message(F.text == "🪙 Gold sotib olish")
async def buy_menu(m: Message):
    ensure_user(m.from_user)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🪙 {g} gold — {fmt(p)} so'm", callback_data=f"buy_{g}")]
        for g, p in PACKS.items()
    ])
    await m.answer("🪙 Gold miqdorini tanlang:", reply_markup=kb)


@router.callback_query(F.data.startswith("buy_"))
async def buy_pick(c: CallbackQuery, state: FSMContext):
    gold = int(c.data.split("_")[1])
    price = PACKS.get(gold)
    if price is None:
        return await c.answer("Xato paket", show_alert=True)
    u = q("SELECT balance FROM users WHERE id=?", (c.from_user.id,), one=True)
    if not u or u["balance"] < price:
        return await c.answer("❗ Balans yetarli emas. Avval hisobni to'ldiring.", show_alert=True)

    q("UPDATE users SET balance=balance-? WHERE id=?", (price, c.from_user.id))
    cur = db.execute("INSERT INTO orders(user_id,gold,price,created) VALUES(?,?,?,?)",
                     (c.from_user.id, gold, price, int(time.time())))
    db.commit()
    oid = cur.lastrowid
    await state.set_state(Buy.skin)
    await state.update_data(order_id=oid)
    await c.message.answer(
        f"✅ Buyurtma #{oid}: {gold} gold ({fmt(price)} so'm)\n\n"
        f"📖 Yo'riqnoma: {SKIN_GUIDE_LINK}\n\n"
        "Skiningizni marketga qo'ying va uning skrinshotini shu yerga yuboring 📸"
    )
    await c.answer()


@router.message(Buy.skin, F.photo)
async def buy_skin(m: Message, state: FSMContext, bot: Bot):
    oid = (await state.get_data())["order_id"]
    o = q("SELECT * FROM orders WHERE id=?", (oid,), one=True)
    caption = (f"🛒 Buyurtma #{oid}\n👤 {m.from_user.full_name} (@{m.from_user.username}) "
               f"| ID: {m.from_user.id}\n🪙 {o['gold']} gold | 💰 {fmt(o['price'])} so'm\n"
               "Skin qo'yildi, tekshirib tasdiqlang.")
    q("UPDATE orders SET status='pending_admin' WHERE id=?", (oid,))
    for admin in ADMINS:
        try:
            await bot.send_photo(admin, m.photo[-1].file_id, caption=caption,
                                 reply_markup=admin_kb("ord", oid))
        except Exception as e:
            logging.warning("Adminga yuborilmadi %s: %s", admin, e)
    await state.clear()
    await m.answer("⏳ Skin adminga yuborildi. Tasdiqlangach gold yetkaziladi.", reply_markup=MENU)


@router.message(Buy.skin)
async def buy_skin_bad(m: Message):
    await m.answer("❗ Skin skrinshotini rasm ko'rinishida yuboring.")


@router.callback_query(F.data.startswith("ord_"))
async def order_admin(c: CallbackQuery, bot: Bot):
    if c.from_user.id not in ADMINS:
        return await c.answer("Siz admin emassiz", show_alert=True)
    _, action, oid = c.data.split("_")
    o = q("SELECT * FROM orders WHERE id=?", (oid,), one=True)
    if not o or o["status"] != "pending_admin":
        return await c.answer("Bu buyurtma allaqachon ko'rib chiqilgan.", show_alert=True)

    if action == "ok":
        q("UPDATE orders SET status='delivered', admin_id=? WHERE id=?", (c.from_user.id, oid))
        status = f"✅ Yetkazildi ({c.from_user.full_name})"
        await bot.send_message(o["user_id"],
                               f"🎉 Buyurtma #{oid}: {o['gold']} gold yetkazildi! Rahmat.")
    else:
        # Rad etilsa pul balansga qaytariladi
        q("UPDATE orders SET status='rejected', admin_id=? WHERE id=?", (c.from_user.id, oid))
        q("UPDATE users SET balance=balance+? WHERE id=?", (o["price"], o["user_id"]))
        status = f"❌ Rad etildi ({c.from_user.full_name})"
        await bot.send_message(o["user_id"],
                               f"❌ Buyurtma #{oid} rad etildi, pul balansingizga qaytarildi.\n"
                               "Aloqa: " + ", ".join(CONTACTS))
    try:
        await c.message.edit_caption(caption=(c.message.caption or "") + f"\n\n{status}")
    except Exception:
        pass
    await c.answer("Bajarildi")


# ----------------------- ISHGA TUSHIRISH -----------------------
async def main():
    bot = Bot(TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
