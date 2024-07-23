from aiogram.fsm.state import State, StatesGroup

class AccessRequestState(StatesGroup):
    waiting_for_full_name = State()