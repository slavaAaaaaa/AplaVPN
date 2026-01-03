from flask import Flask, request, jsonify
import requests
import os
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

def send_payment_request_to_admin(user_id, username, amount, file_id):
    timestamp = datetime.now().strftime("%d.%m %H:%M")
    user_link = f'<a href="tg://user?id={user_id}">@{username}</a>' if username and username != "None" else f"<code>{user_id}</code>"

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

@app.route('/webhook', methods=['POST'])
def main_webhook():
    data = request.get_json()
    logger.info(f"📥 Получен webhook: {data}")

    # Проверка: от Puzzle Bot или от Telegram?
    if "callback_query" in data:
        # Это нажатие кнопки — обрабатываем отдельно
        return handle_callback(data)

    # Это запрос от Puzzle Bot
    user_id = str(data.get("user_id", "")).strip()
    username = str(data.get("username", "")).strip() or "unknown"
    file_id = data.get("file_url")  # Puzzle Bot даёт file_id здесь
    amount = str(data.get("amount", "")).strip()

    if not user_id or not amount or not file_id:
        logger.error("❌ Не хватает данных")
        return jsonify({"error": "missing user_id, amount or file"}), 400

    success = send_payment_request_to_admin(user_id, username, amount, file_id)
    if success:
        return jsonify({"status": "ok"})
    else:
        return jsonify({"status": "failed"}), 500

def handle_callback(update):
    callback = update["callback_query"]
    user_id = callback["from"]["id"]
    message_id = callback["message"]["message_id"]
    chat_id = callback["message"]["chat"]["id"]
    data = callback["data"]

    if str(user_id) != str(ADMIN_ID):
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
            json={"callback_query_id": callback["id"], "text": "❌ Только админ!", "show_alert": True}
        )
        return jsonify({"ok": True})

    if data.startswith("confirm_"):
        _, target_user_id, amount = data.split("_", 2)
        # Здесь можно добавить логику баланса (если нужно)
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageCaption",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "caption": f"✅ <b>ПОПОЛНЕНИЕ ПОДТВЕРЖДЕНО</b>\n\n"
                           f"👤 ID: <code>{target_user_id}</code>\n"
                           f"💰 Сумма: {amount} ₽",
                "parse_mode": "HTML"
            }
        )
        # Уведомить пользователя (опционально — если знаешь его ID)
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": target_user_id,
                    "text": f"✅ Баланс пополнен на {amount} ₽!",
                    "parse_mode": "HTML"
                }
            )
        except:
            pass

    elif data.startswith("reject_"):
        _, target_user_id, amount = data.split("_", 2)
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageCaption",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "caption": f"❌ <b>ОТКЛОНЕННО</b>\n\nID: <code>{target_user_id}</code>, Сумма: {amount} ₽",
                "parse_mode": "HTML"
            }
        )

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
        json={"callback_query_id": callback["id"]}
    )
    return jsonify({"ok": True})

@app.route('/', methods=['GET'])
def health():
    return "✅ Server is running!", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))  # Render использует PORT=10000
    app.run(host='0.0.0.0', port=port)