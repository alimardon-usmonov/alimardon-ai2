import sqlite3
from datetime import datetime
from typing import List, Tuple, Dict, Any, Optional

DB_PATH = "bot_users.db"

def init_db():
    """Ma'lumotlar bazasini yaratish va yangilash"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Foydalanuvchilar jadvali
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                joined_at TIMESTAMP,
                last_active TIMESTAMP
            )
        """)
        # Sozlamalar jadvali (API kalitlar, faol modellar)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()

def set_setting(key: str, value: str):
    """Sozlamani bazaga saqlash"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        conn.commit()

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Sozlamani bazadan olish"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

def add_or_update_user(user_id: int, first_name: str, username: str = None):
    """Foydalanuvchini bazaga kiritish yoki faolligini yangilash"""
    now = datetime.now()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        exists = cursor.fetchone()
        if exists:
            cursor.execute("""
                UPDATE users 
                SET first_name = ?, username = ?, last_active = ?
                WHERE user_id = ?
            """, (first_name, username, now, user_id))
        else:
            cursor.execute("""
                INSERT INTO users (user_id, first_name, username, joined_at, last_active)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, first_name, username, now, now))
        conn.commit()

def get_stats() -> Dict[str, Any]:
    """Admin uchun batafsil statistika"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]
        
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cursor.execute("SELECT COUNT(*) FROM users WHERE joined_at >= ?", (today_start,))
        new_today = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE last_active >= ?", (today_start,))
        active_today = cursor.fetchone()[0]

        return {
            "total": total,
            "new_today": new_today,
            "active_today": active_today
        }

def get_recent_users(limit: int = 10) -> List[Tuple]:
    """Oxirgi qo'shilgan foydalanuvchilar ro'yxati"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, first_name, username, joined_at
            FROM users
            ORDER BY joined_at DESC
            LIMIT ?
        """, (limit,))
        return cursor.fetchall()

def get_all_user_ids() -> List[int]:
    """Barcha foydalanuvchilarning Telegram ID lari"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        return [row[0] for row in cursor.fetchall()]
