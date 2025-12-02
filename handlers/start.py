from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton


router = Router()


def main_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="Добавить день рождения")],
        [KeyboardButton(text="Список друзей")],
        [KeyboardButton(text="Массовый импорт")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


@router.message(F.text == "/start")
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я бот-напоминалка о днях рождениях.\n"
        "- Нажми ‘Добавить день рождения’, чтобы сохранить дату.\n"
        "- ‘Список друзей’ — посмотреть и отредактировать записи.",
        reply_markup=main_keyboard(),
    )
