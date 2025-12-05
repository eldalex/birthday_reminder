from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton


router = Router()


_ADMIN_UID: int | None = None


def set_admin_uid(uid: int | None) -> None:
    global _ADMIN_UID
    _ADMIN_UID = uid


def main_keyboard(uid: int | None = None) -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="Добавить день рождения")],
        [KeyboardButton(text="Список друзей")],
        [KeyboardButton(text="Дни рождения на сегодня")],
        [KeyboardButton(text="Массовый импорт")],
        [KeyboardButton(text="Настройки")],
    ]
    if _ADMIN_UID is not None and uid == _ADMIN_UID:
        kb.append([KeyboardButton(text="Пользователи")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


@router.message(F.text == "/start")
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я бот-напоминалка о днях рождениях.\n"
        "- Нажми ‘Добавить день рождения’, чтобы сохранить дату.\n"
        "- ‘Список друзей’ — посмотреть и отредактировать записи.\n"
        "- ‘Настройки’ — часовой пояс и время начала напоминаний.",
        reply_markup=main_keyboard(message.from_user.id),
    )
