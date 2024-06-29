import speech_recognition as sr
import logging
from pydub import AudioSegment
import io
import tempfile
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def recognize_speech_from_file(audio_file):
    recognizer = sr.Recognizer()
    
    try:
        # Сохраняем временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            audio_file.save(temp_audio.name)
            temp_filename = temp_audio.name

        # Преобразование аудио в формат WAV
        audio = AudioSegment.from_file(temp_filename)
        wav_data = io.BytesIO()
        audio.export(wav_data, format="wav")
        wav_data.seek(0)
        
        # Распознавание речи
        with sr.AudioFile(wav_data) as source:
            audio_data = recognizer.record(source)
            
        # Попытка распознавания с использованием Google Speech Recognition
        text = recognizer.recognize_google(audio_data, language="ru-RU")
        logging.info(f"Распознанный текст: {text}")
        
        # Удаляем временный файл
        os.unlink(temp_filename)
        
        return text
    
    except sr.UnknownValueError:
        logging.warning("Google Speech Recognition не смог распознать аудио")
        return None
    except sr.RequestError as e:
        logging.error(f"Не удалось запросить результаты у Google Speech Recognition; {e}")
        return None
    except Exception as e:
        logging.error(f"Произошла ошибка при распознавании речи: {e}")
        return None
