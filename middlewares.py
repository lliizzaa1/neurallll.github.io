from aiogram import BaseMiddleware
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from utils.access import check_user_access
from bot.states import AccessRequestState

class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message):
            user_id = event.from_user.id
            state: FSMContext = data['state']
            current_state = await state.get_state()
            
            if current_state == AccessRequestState.waiting_for_full_name.state:
                return await handler(event, data)
            
            if not check_user_access(user_id) and event.text != "/start":
                await event.answer("У вас нет доступа к этому боту. Пожалуйста, используйте команду /start для подачи заявки на доступ.")
                return
        return await handler(event, data)