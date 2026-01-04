import os
import logging
from datetime import datetime
from flask import Flask, request, jsonify
import requests


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


app = Flask(__name__)


BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
PORT = int(os.getenv("PORT", 10000))

logger.info("🟢 Запуск сервера...")
logger.info(f"BOT_TOKEN задан: {'✅ Да' if BOT_TOKEN else '❌ Нет'}")
logger.info(f"ADMIN_ID: {ADMIN_ID}")
logger.info(f"Порт: {PORT}")


def send_payment_request_to_admin(user_id, username, amount, file_id):
    logger.info(f"📤 Формируем уведомление для админа. user_id={user_id}, amount={amount}")

    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не задан! Проверьте Environment Variables.")
        return False
    if not ADMIN_ID:
        logger.error("❌ ADMIN_ID не задан! Проверьте Environment Variables.")
        return False

    timestamp = datetime.now().strftime("%d.%m %H:%M")


    if username and username not in ("None", "неизвестен", ""):
        user_link = f'<a href="tg://user?id={user_id}">@{username}</a>'
    else:
        user_link = f"<code>{user_id}</code>"

    caption = (
        "📥 <b>НОВОЕ ПОПОЛНЕНИЕ</b>\n\n"
        f"👤 Пользователь: {user_link}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"💰 Сумма: <b>{amount} ₽</b>\n"
        f"🕒 Время: {timestamp}\n\n"
        "📎 <i>Файл чека прикреплён ниже</i>"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    payload = {
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
    }

    try:
        logger.info(f"📤 Отправка запроса в Telegram API: {url}")
        response = requests.post(url, json=payload, timeout=15)
        logger.info(f"✅ Ответ от Telegram: {response.status_code} | {response.text[:200]}")

        if response.status_code == 200:
            return True
        else:
            logger.error(f"❌ Telegram API вернул ошибку: {response.status_code} {response.text}")
            return False
    except Exception as e:
        logger.exception(f"💥 Исключение при отправке в Telegram: {e}")
        return False


def handle_callback(update):
    logger.info("🔄 Обработка нажатия инлайн-кнопки")
    callback = update["callback_query"]
    user_id = str(callback["from"]["id"])
    message = callback["message"]
    chat_id = message["chat"]["id"]
    message_id = message["message_id"]
    data = callback["data"]

    logger.info(f"Нажата кнопка: {data} | Пользователь ID: {user_id}")

    # Проверка: только админ может подтверждать
    if user_id != str(ADMIN_ID):
        logger.warning(f"⚠️ Попытка подтверждения от не-админа: {user_id}")
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
            json={"callback_query_id": callback["id"], "text": "❌ Только админ может подтверждать!", "show_alert": True}
        )
        return

    try:
        if data.startswith("confirm_"):
            parts = data.split("_")
            if len(parts) < 3:
                raise ValueError("Неверный формат callback_data")
            _, target_user_id, amount = parts[0], parts[1], "_".join(parts[2:])  # на случай, если сумма с точкой

            # Редактируем сообщение у админа
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

            # Уведомляем пользователя (если бот может ему писать)
            try:
                requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": target_user_id,
                        "text": f"✅ Ваш баланс пополнен на <b>{amount} ₽</b>!",
                        "parse_mode": "HTML"
                    }
                )
                logger.info(f"📤 Уведомление отправлено пользователю {target_user_id}")
            except Exception as e2:
                logger.warning(f"⚠️ Не удалось уведомить пользователя {target_user_id}: {e2}")

        elif data.startswith("reject_"):
            parts = data.split("_")
            if len(parts) < 3:
                raise ValueError("Неверный формат callback_data")
            _, target_user_id, amount = parts[0], parts[1], "_".join(parts[2:])

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

        # Подтверждаем нажатие кнопки
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
            json={"callback_query_id": callback["id"]}
        )

    except Exception as e:
        logger.exception(f"💥 Ошибка при обработке callback: {e}")


@app.route("/webhook", methods=["POST"])
def main_webhook():
    logger.info("📥 Получен POST-запрос на /webhook")

    try:
        data = request.get_json()
        if not data:
            logger.warning("⚠️ Пустое тело запроса")
            return jsonify({"error": "empty body"}), 400

        logger.info(f"📨 Данные от Puzzle Bot: {data}")

        # Определяем: от Puzzle Bot или от Telegram?
        if "callback_query" in data:
            logger.info("➡️ Это callback от Telegram")
            handle_callback(data)
            return jsonify({"ok": True})

        # Обработка от Puzzle Bot
        user_id = str(data.get("user_id", "")).strip()
        username = str(data.get("username", "")).strip() or "unknown"
        file_id = data.get("file_url")  # Puzzle Bot даёт file_id под этим именем
        amount = str(data.get("amount", "")).strip()

        logger.info(f"🔍 Извлечены данные: user_id='{user_id}', username='{username}', amount='{amount}', file_id существует: {bool(file_id)}")

        if not user_id or not amount or not file_id:
            logger.error("❌ Отсутствуют обязательные поля: user_id, amount или file_url")
            return jsonify({"error": "missing user_id, amount or file_url"}), 400

        success = send_payment_request_to_admin(user_id, username, amount, file_id)
        if success:
            logger.info("✅ Уведомление успешно отправлено админу")
            return jsonify({"status": "ok"})
        else:
            logger.error("❌ Не удалось отправить уведомление")
            return jsonify({"status": "failed"}), 500

    except Exception as e:
        logger.exception(f"💥 Критическая ошибка в /webhook: {e}")
        return jsonify({"error": "internal server error"}), 500


@app.route("/", methods=["GET"])
def health():
    logger.info("🫀 Health-check запрошен")
    return "✅ Webhook server is running!\n", 200


if __name__ == "__main__":
    logger.info(f"🚀 Запуск Flask-сервера на порту {PORT}")
    app.run(host="0.0.0.0", port=PORT)