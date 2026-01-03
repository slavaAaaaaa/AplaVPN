from flask import Flask, request, jsonify
import requests
import os
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

logger.info(f"🟢 Запуск сервера...")
logger.info(f"BOT_TOKEN установлен: {'Да' if BOT_TOKEN else 'Нет'}")
logger.info(f"ADMIN_ID: {ADMIN_ID}")


def send_to_admin(user_id, username, file_url=None):
    if not BOT_TOKEN or not ADMIN_ID:
        logger.error("❌ BOT_TOKEN или ADMIN_ID не заданы!")
        return False

    # Форматируем время
    timestamp = datetime.now().strftime("%d.%m %H:%M")

    # Формируем ссылку на пользователя
    if username and username != "неизвестен":
        user_link = f'<a href="tg://user?id={user_id}">@{username}</a>'
    else:
        user_link = f"<code>{user_id}</code>"

    # Красивое сообщение в HTML
    caption = (
        "📥 <b>НОВЫЙ ЧЕК ПОЛУЧЕН</b>\n\n"
        f"👤 Пользователь: {user_link}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"🕒 Время: {timestamp}\n\n"
        "📎 <i>Файл чека прикреплён ниже</i>"
    )

    base_url = f"https://api.telegram.org/bot{BOT_TOKEN}/"

    try:
        if file_url:
            # ✅ Отправляем по file_id — без скачивания
            logger.info(f"📤 Отправляю документ админу {ADMIN_ID} по file_id: {file_url}")
            response = requests.post(
                base_url + "sendDocument",
                json={
                    "chat_id": ADMIN_ID,
                    "document": file_url,  # ✅ Это file_id — работает!
                    "caption": caption,
                    "parse_mode": "HTML"
                },
                timeout=15
            )
            logger.info(f"📤 Ответ Telegram API: {response.status_code} {response.text[:200]}")
        else:
            # Если файла нет — отправляем только текст
            logger.info("📤 Отправляю текстовое уведомление (без файла)")
            response = requests.post(
                base_url + "sendMessage",
                json={
                    "chat_id": ADMIN_ID,
                    "text": caption,
                    "parse_mode": "HTML"
                },
                timeout=10
            )
            logger.info(f"📤 Ответ Telegram API: {response.status_code} {response.text[:200]}")

        return response.status_code == 200

    except Exception as e:
        logger.exception(f"💥 Ошибка при отправке в Telegram: {e}")
        return False


@app.route('/webhook', methods=['POST'])
def webhook():
    logger.info("📥 Получен POST-запрос на /webhook")

    try:
        data = request.get_json()
        logger.info(f"📨 Полученные данные: {data}")

        if not data:
            logger.warning("⚠️ Пустой JSON")
            return jsonify({"error": "empty body"}), 400

        user_id = data.get("user_id", "неизвестен")
        username = data.get("username", "неизвестен")
        file_url = data.get("file_url")

        success = send_to_admin(user_id, username, file_url)

        if success:
            logger.info("✅ Чек успешно отправлен админу")
            return jsonify({"status": "ok"})
        else:
            logger.error("❌ Не удалось отправить чек")
            return jsonify({"status": "failed"}), 500

    except Exception as e:
        logger.exception(f"💥 Критическая ошибка в /webhook: {e}")
        return jsonify({"error": str(e)}), 500


# Health-check для Render
@app.route('/', methods=['GET'])
def health():
    return "✅ Webhook server is running!\n", 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Локальный запуск на порту {port}")
    app.run(host='0.0.0.0', port=port)