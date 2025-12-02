from __future__ import annotations

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from db.db import get_db


router = Router()


class LinkStates(StatesGroup):
    waiting_proof = State()


@router.callback_query(F.data.startswith("link:"))
async def link_start(call: CallbackQuery, state: FSMContext):
    bid = int(call.data.split(":", 1)[1])
    await state.set_state(LinkStates.waiting_proof)
    await state.update_data(bid=bid, have_tg=False, have_phone=False)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Готово", callback_data="link_done"), InlineKeyboardButton(text="Отмена", callback_data="link_cancel")]
    ])
    msg = await call.message.answer(
        "Привязка контакта: отправьте одно или несколько действий —\n"
        "1) Перешлите сообщение от человека (подтяну @username).\n"
        "2) Отправьте его контакт (подтяну телефон и, если есть, TG id).\n"
        "Также можно написать @username или номер текстом.\n"
        "Когда закончите — нажмите ‘Готово’.",
        reply_markup=kb,
    )
    await state.update_data(control_mid=msg.message_id, control_mids=[msg.message_id])
    await call.answer()


@router.message(LinkStates.waiting_proof)
async def link_apply(message: Message, state: FSMContext):
    data = await state.get_data()
    bid = int(data["bid"]) 
    uid = message.from_user.id
    db = get_db()

    updated_tg = False
    updated_phone = False

    # 1) Пересланное сообщение с видимым источником
    origin = getattr(message, "forward_origin", None)
    user = getattr(origin, "sender_user", None) if origin else None
    if not user:
        # Совместимость со старыми пересылками
        user = getattr(message, "forward_from", None)
    if user:
        try:
            await db.update_birthday_field(uid, bid, "tg_id", int(user.id))
            if getattr(user, "username", None):
                await db.update_birthday_field(uid, bid, "tg_nic", user.username)
            updated_tg = True
        except Exception:
            pass

    # 2) Контакт
    if message.contact:
        try:
            phone = message.contact.phone_number
            if phone:
                await db.update_birthday_field(uid, bid, "phone", phone)
                updated_phone = True
            if message.contact.user_id:
                await db.update_birthday_field(uid, bid, "tg_id", int(message.contact.user_id))
                updated_tg = True
        except Exception:
            pass

    # 3) Текст: @username или телефон
    if message.text and not message.contact and not user:
        text = message.text.strip()
        # username
        if text.startswith("@") or (text.replace("_", "").isalnum() and len(text) >= 5):
            uname = text[1:] if text.startswith("@") else text
            try:
                await db.update_birthday_field(uid, bid, "tg_nic", uname)
                updated_tg = True
            except Exception:
                pass
        # phone heuristic
        digits = "+" + "".join(ch for ch in text if ch.isdigit()) if text.strip().startswith("+") else "".join(ch for ch in text if ch.isdigit())
        if len(digits) >= 7:  # naive length check
            try:
                await db.update_birthday_field(uid, bid, "phone", digits)
                updated_phone = True
            except Exception:
                pass

    # Track user message id to optionally delete on completion
    mids = list(data.get("user_mids", []))
    if message.message_id not in mids:
        mids.append(message.message_id)

    # Update state flags
    have_tg = data.get("have_tg", False) or updated_tg
    have_phone = data.get("have_phone", False) or updated_phone
    await state.update_data(have_tg=have_tg, have_phone=have_phone, user_mids=mids)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Готово", callback_data="link_done"), InlineKeyboardButton(text="Отмена", callback_data="link_cancel")]
    ])
    control_mid = data.get("control_mid")
    control_mids = list(data.get("control_mids", []))
    status_text = (
        ("username привязан" if have_tg else "username не найден") + "; " +
        ("телефон привязан" if have_phone else "телефон не найден") +
        ". Можете добавить недостающее или нажмите ‘Готово’."
    ) if (updated_tg or updated_phone or have_tg or have_phone) else (
        "Не распознал ни username, ни телефон. Перешлите сообщение, отправьте контакт или введите @username/номер."
    )
    try:
        if control_mid:
            await message.bot.edit_message_text(
                chat_id=uid,
                message_id=int(control_mid),
                text=status_text,
                reply_markup=kb,
            )
        else:
            # На случай отсутствия control_mid создадим новый контрол-сообщение
            msg = await message.answer(status_text, reply_markup=kb)
            control_mids.append(msg.message_id)
            await state.update_data(control_mid=msg.message_id, control_mids=control_mids)
    except TelegramBadRequest as e:
        # Если "message is not modified" — тихо игнорируем
        if "message is not modified" in str(e).lower():
            pass
        else:
            # Иначе создаём новое контрол-сообщение
            msg = await message.answer(status_text, reply_markup=kb)
            control_mids.append(msg.message_id)
            await state.update_data(control_mid=msg.message_id, control_mids=control_mids)
    except Exception:
        msg = await message.answer(status_text, reply_markup=kb)
        control_mids.append(msg.message_id)
        await state.update_data(control_mid=msg.message_id, control_mids=control_mids)


@router.callback_query(LinkStates.waiting_proof, F.data == "link_done")
async def link_done(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    control_mid = data.get("control_mid")
    user_mids = data.get("user_mids", []) or []
    control_mids = data.get("control_mids", []) or []
    try:
        if control_mid:
            await call.bot.delete_message(chat_id=call.from_user.id, message_id=int(control_mid))
    except TelegramBadRequest:
        pass
    try:
        # Удалим и текущее, если это другое сообщение
        if call.message and (not control_mid or call.message.message_id != int(control_mid)):
            await call.message.delete()
    except TelegramBadRequest:
        pass
    # Try to delete user's forwarded/contact messages for cleanliness
    for mid in user_mids:
        try:
            await call.bot.delete_message(chat_id=call.from_user.id, message_id=int(mid))
        except TelegramBadRequest:
            pass
    # Try delete all tracked control messages
    for mid in control_mids:
        try:
            await call.bot.delete_message(chat_id=call.from_user.id, message_id=int(mid))
        except TelegramBadRequest:
            pass
    await state.clear()
    await call.answer()


@router.callback_query(LinkStates.waiting_proof, F.data == "link_cancel")
async def link_cancel(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    control_mid = data.get("control_mid")
    user_mids = data.get("user_mids", []) or []
    control_mids = data.get("control_mids", []) or []
    try:
        if control_mid:
            await call.bot.delete_message(chat_id=call.from_user.id, message_id=int(control_mid))
    except TelegramBadRequest:
        pass
    try:
        if call.message and (not control_mid or call.message.message_id != int(control_mid)):
            await call.message.delete()
    except TelegramBadRequest:
        pass
    for mid in user_mids:
        try:
            await call.bot.delete_message(chat_id=call.from_user.id, message_id=int(mid))
        except TelegramBadRequest:
            pass
    for mid in control_mids:
        try:
            await call.bot.delete_message(chat_id=call.from_user.id, message_id=int(mid))
        except TelegramBadRequest:
            pass
    await state.clear()
    await call.answer()
