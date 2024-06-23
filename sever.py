import hashlib
import hmac
from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
from main import TOKEN
# Настройка логирования
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
CORS(app)  # Добавляем CORS для разрешения междоменных запросов

BOT_TOKEN = TOKEN

def validate_telegram_data(init_data):
    try:
        data_check_string = '\n'.join([f"{k}={v}" for k, v in sorted(init_data.items()) if k != 'hash'])
        secret_key = hmac.new("WebAppData".encode(), BOT_TOKEN.encode(), hashlib.sha256).digest()
        data_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return data_hash == init_data['hash']
    except Exception as e:
        logging.error(f"Validation error: {e}")
        return False

@app.route('/validate', methods=['POST'])
def validate():
    init_data = request.json
    if validate_telegram_data(init_data):
        return jsonify({"valid": True})
    else:
        return jsonify({"valid": False}), 403

if __name__ == '__main__':
    app.run(debug=True)