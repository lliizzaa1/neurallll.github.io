from flask import Flask, jsonify, request, session, make_response
from flask_cors import CORS
import logging
import random
from speech_recognition_mine import recognize_speech_from_file
import os
import aiohttp
import asyncio
from dotenv import load_dotenv
from gtts import gTTS
import tempfile
import uuid
import pyttsx3
import io
import base64
import wave
from flask_cors import cross_origin
import json
from flask import render_template

semaphore = asyncio.Semaphore(50)

load_dotenv()
API_KEY = os.getenv("API_KEY")

async def get_response(conversation_history):
    system_message = {
        "role": "system",
        "content": """Ты - человек, которому неожиданно позвонили финансовый консультант. Твоя задача - реалистично поддерживать диалог. Веди себя как человек"""
    }
    
    messages = [system_message] + conversation_history
    print(messages)
    print(conversation_history)
    async with aiohttp.ClientSession() as session:
        response_json = await send_request(session, messages)
        
    if response_json and 'choices' in response_json:
        return response_json['choices'][0]['message']['content']
    else:
        return "Извините, произошла ошибка при обработке вашего запроса."

async def send_request(session, messages, max_retries=10, retry_delay=2):
    for attempt in range(max_retries):
        try:
            async with semaphore:
                async with session.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {API_KEY}",
                    },
                    json={
                        "model": "anthropic/claude-3-haiku",
                        "messages": messages,
                        "provider": {"order": ["Anthropic"]},
                        "max_tokens": 200000,
                        "temperature": 0.5,
                        "top_p": 0.5,
                        "top_k": 50,
                        "samplingParameters": {
                            "temperature": 0.5,
                            "top_p": 0.5,
                            "top_k": 50
                        },
                    }
                ) as response:
                    if response.status == 200:
                        response_json = await response.json()
                        return response_json
                    else:
                        error_message = f"API request failed with status {response.status}: {response.reason}"
                        print(error_message)  # Или запишите в лог
        except Exception as e:
            print(f"Error in send_request: {str(e)}")  # Или запишите в лог

        if attempt == max_retries - 1:
            return None

        await asyncio.sleep(retry_delay)

    return None

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Замените на свой секретный ключ
#CORS(app, resources={r"/*": {"origins": "https://lliizzaa1.github.io"}}) #http://localhost:5000/
origins = [
    "http://127.0.0.1:5000",  #  <-  Если ты используешь этот адрес для разработки
    "https://lliizzaa1.github.io"  #  <- Домен GitHub Pages 
]

# Создаём экземпляр CORS, указав origins
#cors = CORS(app, resources={r"/*": {"origins": origins}})
#cors = CORS(app, resources={r"/*": {"origins": "https://lliizzaa1.github.io"}})
#cors = CORS(app, resources={r"/*": {"origins": "https://lliizzaa1.github.io"}}, supports_credentials=True)
cors = CORS(app, resources={r"/*": {"origins": ["https://lliizzaa1.github.io"]}})

conversation_state = {
    "greeting_done": False,
    "product_mentioned": False,
    "price_mentioned": False,
    "closing_attempted": False
}

def get_conversation_filename(telegram_user_id):
    """Возвращает путь к файлу с историей диалога для пользователя Telegram."""
    os.makedirs('conversations', exist_ok=True)
    return os.path.join('conversations', f'{telegram_user_id}.json')

@app.route('/start_call', methods=['POST'])
def start_call():
    """ Больше не нужен, так как мы используем Telegram User ID. 
        Можно удалить этот маршрут или оставить пустым, если он используется на фронтенде. 
    """
    return jsonify({"message": "Call started"})

@app.route('/end_call', methods=['POST'])
def end_call():
    """Завершает диалог."""
    user_id = session.pop('user_id', None)
    if not user_id:
        return jsonify({"message": "No active call"}), 400

    # (опционально) удаление файла с историей диалога
    conversation_filename = get_conversation_filename(user_id)
    if os.path.exists(conversation_filename):
       os.remove(conversation_filename)

    return jsonify({"message": "Call ended"})

@app.route('/delete_conversation', methods=['POST'])
def delete_conversation():
    telegram_user_id = request.form.get('telegram_user_id')
    if not telegram_user_id:
        return jsonify({"error": "Telegram User ID is missing"}), 400

    conversation_filename = get_conversation_filename(telegram_user_id)
    if os.path.exists(conversation_filename):
        os.remove(conversation_filename)
        return jsonify({"message": "Conversation deleted"}), 200
    else:
        return jsonify({"message": "Conversation not found"}), 404

@app.route('/test', methods=['GET'])
def test():
    logging.info("Test endpoint called")
    return jsonify({"message": "Server is working!"})

#@app.after_request
#def after_request(response):
#    response.headers.add('Access-Control-Allow-Origin', '*')
#    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
#    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
#    return response

def generate_audio(text):
  print("Генерирую речь...")
  tts = gTTS(text=text, lang='ru') 

  # Используем BytesIO для сохранения аудио в памяти
  with io.BytesIO() as memory_buffer: 
    tts.write_to_fp(memory_buffer)
    memory_buffer.seek(0) 
    audio_data = memory_buffer.read()
  
  print("Речь сгенерирована")
  return audio_data


@app.route('/recognize_speech', methods=['POST'])
async def handle_speech():
    """Обрабатывает речь пользователя, получает ответ бота 
       и сохраняет историю диалога в файл, используя Telegram User ID.
    """
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    audio_file = request.files['audio']
    telegram_user_id = request.form.get('telegram_user_id')  # Получаем Telegram User ID из FormData

    if audio_file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if not telegram_user_id:
        return jsonify({"error": "Telegram User ID is missing"}), 400

    if audio_file:
        user_speech = recognize_speech_from_file(audio_file)
        if user_speech is None:
            return jsonify({"error": "Ошибка распознавания речи"}), 500

        conversation_filename = get_conversation_filename(telegram_user_id)
        try:
            with open(conversation_filename, 'r', encoding='utf-8') as f:
                conversation_history = json.load(f)
        except FileNotFoundError:
            conversation_history = []

        conversation_history.append({"role": "user", "content": "пользователь-инвестиционный консультант:" + user_speech})

        # Получение ответа от бота
        bot_response = await get_response(conversation_history)

        conversation_history.append({"role": "assistant", "content": 'бот-потенциальный клиент:'+ bot_response})

        with open(conversation_filename, 'w', encoding='utf-8') as f:
            json.dump(conversation_history, f, indent=4, ensure_ascii=False)

        audio_data = generate_audio(bot_response)
        audio_data_base64 = base64.b64encode(audio_data).decode('utf-8')

        response = make_response(jsonify({
            "user_speech": user_speech,
            "bot_response": bot_response,
            "audio_data": f"data:audio/wav;base64,{audio_data_base64}"
        }))

        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
        #response.headers['Access-Control-Allow-Credentials'] = 'true'

        return response, 200

    return jsonify({"error": "Invalid file"}), 400

# @app.route('/recognize_speech_1', methods=['POST'])
# async def handle_speech_1():
#     if 'audio' not in request.files:
#         return jsonify({"error": "No audio file provided"}), 400
#     conversation_history = session.get('conversation_history', [])
#     audio_file = request.files['audio']
    
#     if audio_file.filename == '':
#         return jsonify({"error": "No selected file"}), 400
    
#     if audio_file:
#         user_speech = recognize_speech_from_file(audio_file)
#         if user_speech is None:
#             return jsonify({"error": "Ошибка распознавания речи"}), 500
        
#         # Получаем историю диалога из сессии или создаем новую, если её нет
        
#         app.logger.info(f"История разговора из сессии: {conversation_history}")

#         # Добавляем сообщение пользователя в историю
#         conversation_history.append({"role": "user", "content": user_speech})
#         print(conversation_history)
#         # Получаем ответ от бота, передавая всю историю диалога
#         bot_response = await get_response(conversation_history)
        
#         # Добавляем ответ бота в историю
#         conversation_history.append({"role": "assistant", "content": bot_response})
#         print(conversation_history)
#         # Сохраняем обновленную историю в сессии
#         session['conversation_history'] = conversation_history
#         app.logger.info(f"Сохранённая история: {session['conversation_history']}")
#         print(f"Текст для генерации: {bot_response}")
#         audio_data = generate_audio(bot_response)
        
#         audio_data_base64 = base64.b64encode(audio_data).decode('utf-8')
        
#         response = make_response(jsonify({
#             "user_speech": user_speech,
#             "bot_response": bot_response,
#             "audio_data": f"data:audio/wav;base64,{audio_data_base64}"
#         }))

#         response.headers['Access-Control-Allow-Origin'] = '*'
#         response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
#         response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'

#         return response, 200
    
#     return jsonify({"error": "Invalid file"}), 400

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
