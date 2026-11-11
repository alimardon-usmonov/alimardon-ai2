# 🤖 Telegram AI Bot (Gemini 2.0 Flash)

Telegram orqali foydalanuvchilar bilan xuddi ChatGPT kabi suhbatlashuvchi sun'iy intellekt boti.

---

## ⚙️ Loyiha tarkibi
- `bot.py` — Botning asosiy kodi (AI, xotira, admin paneli)
- `database.py` — Foydalanuvchilarni saqlash uchun SQLite bazasi
- `.env` — Maxfiy tokenlar va sozlamalar (tayyor holatda kiritilgan)
- `start_bot.bat` — Kompyuterda (Windows) 1 ta klik bilan ishga tushirish fayli
- `Dockerfile` & `docker-compose.yml` — Docker orqali hostingga qo'yish uchun
- `Procfile` — Railway / Render kabi bulutli xizmatlar uchun
- `telegram-bot.service` — Linux VPS (Ubuntu/Debian) uchun 24/7 avtomatik xizmat

---

## 🖥 1. Kompyuterda ishga tushirish (Windows)

Juda oson! Papkadagi **`start_bot.bat`** faylini ikki marta bosing (Double click).
U avtomatik ravishda:
1. Kerakli kutubxonalarni o'rnatadi.
2. Botni ishga tushiradi.
3. Telegramingizga: *"🚀 Bot muvaffaqiyatli ishga tushdi!"* deb xabar yuboradi.

Yoki terminal orqali:
```bash
pip install -r requirements.txt
python bot.py
```

---

## 🌐 2. Hostingga joylashtirish (24/7 ishlashi uchun)

### Variant A: Railway / Render (Eng oson bulutli hosting)
1. Kodlarni GitHub-dagi shaxsiy repositoriyingizga yuklang (push qiling).
2. [Railway.app](https://railway.app/) yoki [Render.com](https://render.com/) saytiga kiring.
3. **"New Project"** -> **"Deploy from GitHub repo"** ni tanlang.
4. **Environment Variables** bo'limiga `.env` dagi qiymatlarni kiriting:
   - `BOT_TOKEN`
   - `GEMINI_API_KEY`
   - `ADMIN_ID`
5. Loyiha avtomatik tarzda `Procfile` yoki `Dockerfile` orqali ishga tushadi.

---

### Variant B: Linux VPS (Ubuntu / Debian server)

Serveringizga ulaning (SSH orqali):

```bash
# 1. Loyihani yuklab oling yoki fayllarni serverga tashlang
git clone <sizning-repo> /root/Alimardon
cd /root/Alimardon

# 2. Virtual muhit va kutubxonalarni o'rnating
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Systemd xizmatini sozlash (bot server o'chib-yonsa ham avtomatik 24/7 ishlaydi)
cp telegram-bot.service /etc/systemd/system/telegram-bot.service
systemctl daemon-reload
systemctl enable telegram-bot
systemctl start telegram-bot

# Holatini tekshirish:
systemctl status telegram-bot
```

### Variant C: Docker orqali (VPS serverda)
```bash
docker compose up -d --build
```

---

## 👑 Admin imkoniyatlari
Siz admin sifatida botga kirganingizda quyidagi maxsus buyruqlardan foydalanishingiz mumkin:
- `/stats` — Botdan foydalanayotgan odamlar soni va statistikasini ko'rish.
- `/broadcast <xabar>` — Barcha foydalanuvchilarga umumiy e'lon yuborish.
- `/clear` — O'zingizning suhbat tarixingizni tozalash.
