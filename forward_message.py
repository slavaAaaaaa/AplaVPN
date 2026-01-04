from flask import Flask, request, jsonify
import requests
import os
import logging
from datetime import datetime, timezone

# === Google Sheets (опционально, но включено) ===
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    GOOGLE_ENABLED = True
except ImportError:
    GOOGLE_ENABLED = False
    logging.warning("❌ gspread не установлен — баланс не будет сохраняться")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

# === Функция для доступа к Google Таблице ===
def get_balance_sheet():
    if not GOOGLE_ENABLED:
        return None
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client = gspread.authorize(creds)
        return client.open("Balances").sheet1
    except Exception as e:
        logger.error(f"Ошибка подключения к Google Таблице: {e}")
        return None

# === Функция пополнения баланса ===
def add_balance(user_id, username, amount):
    sheet = get_balance_sheet()
    if not sheet:
        return float(amount)  # эмуляция, если нет Google

    try:
        records = sheet.get_all_records()
        for i, row in enumerate(records, start=2):
            if str(row.get("user_id", "")) == str(user_id):
                old_balance = float(row.get("balance", 0))
                new_balance = old_balance + float(amount)
                sheet.update_cell(i, 3, str(new_balance))
                sheet.update_cell(i, 4, datetime.now(timezone.utc).isoformat())
                return new_balance

        # Новый пользователь
        new_balance = float(amount)
        sheet.append_row([str(user_id), username or "", str(new_balance), datetime.now(timezone.utc).isoformat()])
        return new_balance
    except Exception as e:
        logger.error(f"Ошибка обновления баланса: {e}")
        return float(amount)

# === Отправка запроса админу ===
def send_payment_request_to_admin(user_id, username, amount, file_id):
    timestamp = datetime.now().strftime("%d.%m %H:%M")
    user_link = f'<a href="tg://user?id={user_id}">@{username}</a>' if username and username != "unknown" else f"<code>{user_id}</code>"

    caption = (
        "📥 <b>НОВОЕ ПОПОЛНЕНИЕ</b>\n\n"
        f"👤 Пользователь: {user_link}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"💰 Сумма: <b>{amount} ₽</b>\n"
        f"🕒 Время: {timestamp}\n\n"
        "📎 <i>Файл чека прикреплён ниже</i>"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"  # ✅ УБРАНЫ ПРОБЕЛЫ!
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

# === Обработка webhook ===
@app.route('/webhook', methods=['POST'])
def main_webhook():
    data = request.get_json()
    logger.info(f"📥 Получен webhook: {data}")

    if not data:
        return jsonify({"error": "empty body"}), 400

    if "callback_query" in data:
        return handle_callback(data)

    user_id = str(data.get("user_id", "")).strip()
    username = str(data.get("username", "")).strip() or "unknown"
    file_id = data.get("file_url")
    amount = str(data.get("amount", "")).strip()

    if not user_id or not amount or not file_id:
        logger.error("❌ Не хватает данных")
        return jsonify({"error": "missing user_id, amount or file"}), 400

    success = send_payment_request_to_admin(user_id, username, amount, file_id)
    return jsonify({"status": "ok" if success else "failed"}), 200 if success else 500

# === Обработка кнопок ===
def handle_callback(update):
    callback = update["callback_query"]
    user_id = callback["from"]["id"]
    message_id = callback["message"]["message_id"]
    chat_id = callback["message"]["chat"]["id"]
    data = callback["data"]

    if str(user_id) != str(ADMIN_ID):
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",  # ✅ Без пробелов
            json={"callback_query_id": callback["id"], "text": "❌ Только админ!", "show_alert": True}
        )
        return jsonify({"ok": True})

    if data.startswith("confirm_"):
        try:
            _, target_user_id, amount = data.split("_", 2)
            username = ""  # можно передавать, но для простоты — опционально
            new_balance = add_balance(target_user_id, username, amount)

            # Обновить сообщение админа
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
        except Exception as e:
            logger.error(f"Ошибка подтверждения: {e}")

    elif data.startswith("reject_"):
        _, target_user_id, amount = data.split("_", 2)
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

# === Health check ===
@app.route('/', methods=['GET'])
def health():
    return "✅ Server is running!", 200

# === Запуск ===
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)