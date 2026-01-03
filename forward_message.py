from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)


BOT_TOKEN = os.getenv("BOT_TOKEN") 
ADMIN_ID = os.getenv("ADMIN_ID")         

def send_to_admin(text, photo_url=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/"

    # Отправка текста
    requests.post(url + "sendMessage", json={
        "chat_id": ADMIN_ID,
        "text": text,
        "parse_mode": "HTML"
    })

    # Если есть фото — отправим
    if photo_url:
        requests.post(url + "sendPhoto", json={
            "chat_id": ADMIN_ID,
            "photo": photo_url
        })

@app.route('/notify', methods=['POST'])
def notify():
    try:
        data = request.get_json()
        message = data.get("message", "Новое уведомление")
        photo = data.get("photo")


        print(f"Отправка сообщения админу: {ADMIN_ID}")
        print(f"Содержимое: {message}")

        send_to_admin(message, photo)
        return jsonify({"ok": True})
    except Exception as e:
        print("Ошибка:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))