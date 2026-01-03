from flask import Flask, request, jsonify
import requests
import os
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

logger.info(f"🟢 Запуск сервера...")
logger.info(f"BOT_TOKEN установлен: {'Да' if BOT_TOKEN else 'Нет'}")
logger.info(f"ADMIN_ID: {ADMIN_ID}")

def send_to_admin(text, file_url=None, file_type="document"):
    if not BOT_TOKEN or not ADMIN_ID:
        logger.error("❌ BOT_TOKEN или ADMIN_ID не заданы!")
        return False

    base_url = f"https://api.telegram.org/bot{BOT_TOKEN}/"

    try:
        # Отправка текста
        logger.info(f"📤 Отправляю текст админу {ADMIN_ID}: {text}")
        requests.post(
            base_url + "sendMessage",
            json={
                "chat_id": ADMIN_ID,
                "text": text,
                "parse_mode": "HTML"
            },
            timeout=10
        )

        # Отправка файла
        if file_url:
            if file_type == "photo":
                logger.info(f"🖼️ Отправляю как фото: {file_url}")
                requests.post(
                    base_url + "sendPhoto",
                    json={"chat_id": ADMIN_ID, "photo": file_url},
                    timeout=10
                )
            else:
                logger.info(f"📎 Отправляю как документ: {file_url}")
                requests.post(
                    base_url + "sendDocument",
                    json={"chat_id": ADMIN_ID, "document": file_url},
                    timeout=10
                )

        return True
    except Exception as e:
        logger.exception(f"💥 Ошибка при отправке: {e}")
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

        message = f"📎 Новый чек!\nПользователь: @{username} (ID: {user_id})"

        success = send_to_admin(message, file_url)

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