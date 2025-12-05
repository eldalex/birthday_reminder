from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from db.db import get_db
from handlers.start import main_keyboard
from services.utils import parse_date_input


router = Router()


class AddStates(StatesGroup):
    friend = State()
    date = State()
    phone = State()


@router.message(F.text == "/add")
@router.message(F.text == "Добавить день рождения")
async def add_start(message: Message, state: FSMContext):
    await state.set_state(AddStates.friend)
    await message.answer("Как зовут друга?")


@router.message(AddStates.friend)
async def add_friend(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Имя не может быть пустым. Введите ещё раз.")
        return
    await state.update_data(friend=name)
    await state.set_state(AddStates.date)
    await message.answer("Дата рождения (ДД.ММ или ДД.ММ.ГГГГ)")


@router.message(AddStates.date)
async def add_date(message: Message, state: FSMContext):
    try:
        norm, disp = parse_date_input(message.text)
    except ValueError as e:
        await message.answer(str(e))
        return
    await state.update_data(date=norm)
    await state.set_state(AddStates.phone)
    await message.answer("Телефон (можно пропустить)")


@router.message(AddStates.phone)
async def add_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    phone = phone if phone else None
    await state.update_data(phone=phone)
    data = await state.get_data()
    await state.clear()

    uid = message.from_user.id
    db = get_db()
    _id = await db.add_birthday(
        uid=uid,
        date=data["date"],
        friend=data["friend"],
        phone=data.get("phone"),
    )
    from services.utils import human_date_short
    await message.answer(
        f"Добавлено: {data['friend']} — {human_date_short(data['date'])}",
        reply_markup=main_keyboard(message.from_user.id),
    )
    await message.answer("Хотите добавить ещё? Нажмите ‘Добавить день рождения’.")
