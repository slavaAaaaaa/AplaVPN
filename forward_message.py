from flask import Flask, request, jsonify
import requests
import os
import logging
from datetime import datetime, timezone
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

# === GOOGLE SHEETS ===
def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    return client.open("Balances").sheet1  # Название таблицы

def get_or_create_user(user_id, username):
    sheet = get_sheet()
    records = sheet.get_all_records()
    for i, row in enumerate(records, start=2):  # строки начинаются с 2 (1 — заголовок)
        if str(row["user_id"]) == str(user_id):
            return i, row
    # Если нет — создаём
    sheet.append_row([str(user_id), username or "", "0", ""])
    return len(records) + 2, {"user_id": user_id, "balance": "0"}

def update_balance(user_id, amount):
    sheet = get_sheet()
    row_index, user = get_or_create_user(user_id, None)
    new_balance = float(user["balance"]) + float(amount)
    sheet.update_cell(row_index, 3, str(new_balance))  # колонка "balance"
    sheet.update_cell(row_index, 4, datetime.now(timezone.utc).isoformat())
    return new_balance

# === ОТПРАВКА С УВЕДОМЛЕНИЕМ И КНОПКОЙ ===
def send_payment_request_to_admin(user_id, username, amount, file_id):
    timestamp = datetime.now().strftime("%d.%m %H:%M")
    user_link = f'<a href="tg://user?id={user_id}">@{username}</a>' if username else f"<code>{user_id}</code>"

    caption = (
        "📥 <b>НОВОЕ ПОПОЛНЕНИЕ</b>\n\n"
        f"👤 Пользователь: {user_link}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"💰 Сумма: <b>{amount} ₽</b>\n"
        f"🕒 Время: {timestamp}\n\n"
        "📎 <i>Файл чека прикреплён ниже</i>"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    response = requests.post(url, json={
        "chat_id": ADMIN_ID,
        "document": file_id,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "✅ Подтвердить", "callback_data": f"confirm_{user_id}_{amount}"},
                {"text": "❌ Отклонить", "callback_data": f"reject_{user_id}_{amount}"}
            ]]
        }
    })
    return response.status_code == 200

# === ОБРАБОТКА WEBHOOK ОТ PUZZLE BOT ===
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    logger.info(f"📥 Получен webhook: {data}")

    user_id = data.get("user_id")
    username = data.get("username")
    file_id = data.get("file_url")  # Puzzle Bot присылает file_id под именем file_url
    amount = data.get("AMOUNT_DEPOSIT")

    if not all([user_id, amount, file_id]):
        return jsonify({"error": "missing data"}), 400

    success = send_payment_request_to_admin(user_id, username, amount, file_id)
    if success:
        return jsonify({"status": "ok"})
    else:
        return jsonify({"status": "failed"}), 500

# === ОБРАБОТКА НАЖАТИЯ КНОПКИ ===
@app.route(f'/webhook', methods=['POST'])  # Telegram webhook будет сюда
def telegram_webhook():
    update = request.get_json()
    logger.info(f"📥 Telegram update: {update}")

    if "callback_query" in update:
        callback = update["callback_query"]
        user_id = callback["from"]["id"]
        message_id = callback["message"]["message_id"]
        chat_id = callback["message"]["chat"]["id"]
        data = callback["data"]

        # Только админ может подтверждать
        if str(user_id) != str(ADMIN_ID):
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
                json={"callback_query_id": callback["id"], "text": "❌ Только админ может подтверждать!", "show_alert": True}
            )
            return jsonify({"ok": True})

        if data.startswith("confirm_"):
            _, target_user_id, amount = data.split("_")
            new_balance = update_balance(target_user_id, amount)

            # Уведомить админа
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageCaption",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "caption": f"✅ <b>ПОПОЛНЕНИЕ ПОДТВЕРЖДЕНО</b>\n\n"
                               f"👤 ID: <code>{target_user_id}</code>\n"
                               f"💰 Сумма: {amount} ₽\n"
                               f"📊 Новый баланс: {new_balance} ₽",
                    "parse_mode": "HTML"
                }
            )

            # Уведомить пользователя
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": target_user_id,
                    "text": f"✅ Ваш баланс пополнен на <b>{amount} ₽</b>!\n"
                            f"Текущий баланс: <b>{new_balance} ₽</b>",
                    "parse_mode": "HTML"
                }
            )

        elif data.startswith("reject_"):
            _, target_user_id, amount = data.split("_")
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageCaption",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "caption": f"❌ <b>ПОПОЛНЕНИЕ ОТКЛОНЕННО</b>\n\n"
                               f"👤 ID: <code>{target_user_id}</code>\n"
                               f"💰 Сумма: {amount} ₽",
                    "parse_mode": "HTML"
                }
            )

        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
            json={"callback_query_id": callback["id"]}
        )

    return jsonify({"ok": True})

# === HEALTH CHECK ===
@app.route('/', methods=['GET'])
def health():
    return "✅ Server is running!", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))