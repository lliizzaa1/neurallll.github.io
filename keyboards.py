from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from config import WEBAPP_URL

def get_simulator_keyboard(message):
    user_id = message.from_user.id
    webapp_url = f"https://lliizzaa1.github.io/neurallll.github.io/?user_id={user_id}"

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Открыть симулятор", web_app=WebAppInfo(url=webapp_url))]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard