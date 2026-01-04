from flask import Flask, request, jsonify
import requests
import os
import logging
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")  # ← Токен твоего Puzzle Bot (да, он у тебя есть!)
ADMIN_ID = os.getenv("ADMIN_ID")    # ← Твой ID

# === Google Таблица ===
def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    return client.open("Balances").sheet1

def update_balance(user_id, amount):
    sheet = get_sheet()
    records = sheet.get_all_records()
    for i, row in enumerate(records, start=2):
        if str(row.get("user_id")) == str(user_id):
            new_balance = float(row.get("balance", 0)) + float(amount)
            sheet.update_cell(i, 3, str(new_balance))  # колонка balance
            sheet.update_cell(i, 4, datetime.now().isoformat())  # last_update
            return new_balance
    # Если нет — создаём
    sheet.append_row([str(user_id), "", str(amount), datetime.now().isoformat()])
    return float(amount)

# === Уведомление админу (без файла!) ===
@app.route('/notify_admin', methods=['POST'])
def notify_admin():
    data = request.get_json()
    user_id = data.get("user_id")
    username = data.get("username", "—")
    amount = data.get("amount")

    if not BOT_TOKEN or not ADMIN_ID:
        logger.error("❌ BOT_TOKEN или ADMIN_ID не заданы!")
        return jsonify({"error": "env missing"}), 500

    text = (
        f"📥 <b>Новое пополнение!</b>\n"
        f"👤 @{username} (ID: <code>{user_id}</code>)\n"
        f"💰 Сумма: <b>{amount} ₽</b>\n\n"
        f"Чтобы подтвердить, отправьте:\n"
        f"<code>/confirm {user_id} {amount}</code>"
    )
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": ADMIN_ID,
            "text": text,
            "parse_mode": "HTML"
        }
    )
    return jsonify({"ok": True})

# === Подтверждение баланса ===
@app.route('/confirm_balance', methods=['POST'])
def confirm_balance():
    data = request.get_json()
    user_id = data.get("user_id")
    amount = data.get("amount")

    try:
        new_balance = update_balance(user_id, amount)
        # Уведомляем пользователя
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": user_id,
                "text": f"✅ Ваш баланс пополнен на <b>{amount} ₽</b>!\nТекущий баланс: <b>{new_balance} ₽</b>",
                "parse_mode": "HTML"
            }
        )
        return jsonify({"ok": True})
    except Exception as e:
        logger.exception("Ошибка при подтверждении")
        return jsonify({"error": str(e)}), 500

@app.route('/', methods=['GET'])
def health():
    return "✅ Server is running!", 200

if __name__ == '__main__':
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)