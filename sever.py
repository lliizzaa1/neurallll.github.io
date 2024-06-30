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

semaphore = asyncio.Semaphore(50)

load_dotenv()
API_KEY = os.getenv("API_KEY")

async def get_response(conversation_history):
    system_message = {
        "role": "system",
        "content": """Ты - потенциальный клиент финансовой управляющей компании, которому неожиданно звонит финансовый консультант. Твоя задача - реалистично отвечать на вопросы и реагировать на предложения консультанта, исходя из следующих случайно выбранных характеристик:



Голос: [мужской/женский], [высокий/низкий], [энергичный/уставший], [быстрый/медленный темп речи]

Возраст: [случайное число от 30 до 75]

Финансовое положение: [от "я банкрот" до "у меня несколько сотен миллионов долларов"]

Опыт в инвестициях: [от "совсем не знаком" до "профессиональный трейдер"]

Начальное настроение: [дружелюбное/раздраженное/торопливое/агрессивное/заносчивое]


Помни, что ты часто получаешь подобные звонки и можешь проявлять осторожность или раздражение в начале разговора. Твое настроение может меняться в зависимости от того, как консультант ведет диалог.


Учитывай текущее время суток в контексте разговора (например, ты можешь быть на работе, обеде, в пути домой и т.д.).


Ты можешь задавать вопросы о компании Альфа-Капитал, в том числе о ее связи с Альфа-Банком.


Завершение разговора может быть разным: от назначения встречи до жесткого отказа, в зависимости от того, насколько убедительным будет консультант.


Веди себя естественно и реалистично, как обычный человек в подобной ситуации. Возвращай только текст, без меток действия и т.п."""
    }
    
    messages = [system_message] + conversation_history
    
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
cors = CORS(app, resources={r"/*": {"origins": origins}})


conversation_state = {
    "greeting_done": False,
    "product_mentioned": False,
    "price_mentioned": False,
    "closing_attempted": False
}

@app.route('/start_call', methods=['POST'])
def start_call():
    global conversation_state
    conversation_state = {
        "greeting_done": False,
        "product_mentioned": False,
        "price_mentioned": False,
        "closing_attempted": False
    }
    session['conversation_history'] = []
    logging.info("Call started")
    return jsonify({"message": "Call started"})

@app.route('/end_call', methods=['POST'])
def end_call():
    global conversation_state
    conversation_state = {
        "greeting_done": False,
        "product_mentioned": False,
        "price_mentioned": False,
        "closing_attempted": False
    }
    conversation_history = session.pop('conversation_history', [])
    logging.info("Call ended")
    return jsonify({"message": "Call ended", "conversation_history": conversation_history})

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
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    
    audio_file = request.files['audio']
    
    if audio_file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if audio_file:
        user_speech = recognize_speech_from_file(audio_file)
        
        if user_speech is None:
            return jsonify({"error": "Ошибка распознавания речи"}), 500
        
        conversation_history = session.get('conversation_history', [])
        conversation_history.append({"role": "user", "content": user_speech})
        
        bot_response = await get_response(conversation_history)
        
        conversation_history.append({"role": "assistant", "content": bot_response})
        session['conversation_history'] = conversation_history
        
        print(f"Текст для генерации: {bot_response}")  #  <-  Добавь эту строку
        audio_data = generate_audio(bot_response)
        
        # Кодируем аудио в base64
        audio_data_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        response = make_response(jsonify({
        "user_speech": user_speech,
        "bot_response": bot_response,
        "audio_data": f"data:audio/wav;base64,{audio_data_base64}"
    }))

        # Добавляем заголовки CORS вручную
        response.headers['Access-Control-Allow-Origin'] = '*'  #  <-  Разрешаем доступ с любого домена (для разработки)
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'

        return response, 200
        
    
    return jsonify({"error": "Invalid file"}), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
