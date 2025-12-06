import os
import sqlite3
import threading
import time
import requests
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

API_KEY = "api key"
BOT_TOKEN = "token"
MODEL = "gpt-3.5-turbo"
#dont take my codeeeeee
#dont take my codeeeeee
#dont take my codeeeeee
#dont take my codeeeeee
#dont take my codeeeeee
BOT_PERSONALITY = """
botunuzun şəxsiyyəti burada təsvir ediləcək."""

MY_CHAT_ID = "chat id"

def init_db():
    
    if os.path.exists("bot.db"):
        os.remove("bot.db")
        logging.info("Köhnə bot.db faylı silindi.")

    with sqlite3.connect("bot.db") as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            user_msg TEXT,
            bot_reply TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()
        logging.info("Yeni bot.db və messages cədvəli yaradıldı.")

def save_conversation(chat_id, username, first_name, last_name, user_msg, bot_reply):
    try:
        with sqlite3.connect("bot.db") as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO messages (chat_id, username, first_name, last_name, user_msg, bot_reply) VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, username, first_name, last_name, user_msg, bot_reply)
            )
            conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Verilənlər bazasına yazma xətası: {e}")

def clean_reply(text):
    lines = text.split('\n')
    unique_lines = []
    for line in lines:
        line = line.strip()
        if line and line not in unique_lines:
            unique_lines.append(line)
    return '\n'.join(unique_lines)

def ask_openai(prompt):
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": BOT_PERSONALITY},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.5,
                "max_tokens": 150
            },
            timeout=20
        )
        resp.raise_for_status()
        reply = resp.json()["choices"][0]["message"]["content"]
        return clean_reply(reply)
    except requests.exceptions.RequestException as e:
        logging.error(f"OpenAI API-yə qoşulma xətası: {e}")
    except (KeyError, IndexError) as e:
        logging.error(f"OpenAI API cavabını anlamaq mümkün olmadı: {e}")
    return "Üzr istəyirəm, hal-hazırda bir problem var. Bir az sonra yenidən cəhd edin."

def telegram_send(text, chat_id, reply_to=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_to:
        data["reply_to_message_id"] = reply_to
    try:
        response = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=data, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error(f"Telegrama mesaj göndərmə xətası: {e}")

def generate_daily_summary():
    try:
        with sqlite3.connect("bot.db") as conn:
            c = conn.cursor()
            c.execute("""
                SELECT chat_id, user_msg
                FROM messages
                WHERE DATE(timestamp) = DATE('now', 'localtime')
            """)
            rows = c.fetchall()
    except sqlite3.Error as e:
        logging.error(f"Özət üçün bazadan oxuma xətası: {e}")
        return None

    if not rows:
        return None

    summary = "📋 Günün Özet Raporu\n"
    convs = {}
    for chat_id, user_msg in rows:
        convs.setdefault(chat_id, []).append(user_msg)

    for chat_id, msgs in convs.items():
        summary += f"\n👤 İstifadəçi ID: {chat_id}\n"
        for m in list(dict.fromkeys(msgs))[-3:]:
            summary += f"   - {m}\n"
    return summary

def reset_database():
    try:
        with sqlite3.connect("bot.db") as conn:
            c = conn.cursor()
            c.execute("DELETE FROM messages")
            conn.commit()
            logging.info("Verilənlər bazası sıfırlandı.")
    except sqlite3.Error as e:
        logging.error(f"Verilənlər bazasını sıfırlama xətası: {e}")

def send_and_reset_summary():
    summ = generate_daily_summary()
    if summ:
        telegram_send(summ, MY_CHAT_ID)
    else:
        telegram_send("📋 Bu gün heç bir danışıq olmadı.", MY_CHAT_ID)
    reset_database()

def process_updates(last_update):
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={last_update+1}&timeout=30", timeout=35
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Telegram-dan yeniləmələri almaq mümkün olmadı: {e}")
        return last_update

    new_last_update = last_update
    for res in data.get("result", []):
        new_last_update = max(new_last_update, res["update_id"])
        msg = res.get("message")
        if not msg or msg.get("from", {}).get("is_bot"):
            continue

        chat_id = str(msg["chat"]["id"])
        user_info = msg["from"]
        username = user_info.get("username")
        first_name = user_info.get("first_name", "")
        last_name = user_info.get("last_name", "")
        text = msg.get("text", "").strip()
        if not text:
            continue

        if username is None:
            username = ""

        logging.info(f"Yeni mesaj alındı - İstifadəçi: @{username}, Mesaj: '{text}'")
        reply = ask_openai(text)
        telegram_send(reply, chat_id, msg["message_id"])
        save_conversation(chat_id, username, first_name, last_name, text, reply)

    return new_last_update

def main():
    init_db()

    last_update = 0
    if os.path.exists("last_update.txt"):
        try:
            with open("last_update.txt", "r") as f:
                last_update = int(f.read().strip())
        except (ValueError, FileNotFoundError):
            last_update = 0

    summary_sent_today = False

    logging.info("Bot işə düşdü...")

    while True:
        last_update = process_updates(last_update)

        with open("last_update.txt", "w") as f:
            f.write(str(last_update))

        now_utc = time.gmtime()
        # 4saat geri yaddan çıxartma 0 falanda yazılmır
        if now_utc.tm_hour == 20 and now_utc.tm_min == 0 and not summary_sent_today:
            logging.info("Günün özəti göndərilir...")
            send_and_reset_summary()
            summary_sent_today = True

        if (now_utc.tm_hour != 20 or now_utc.tm_min != 0) and summary_sent_today:
            summary_sent_today = False

        time.sleep(3)

if __name__ == "__main__":
    main()
