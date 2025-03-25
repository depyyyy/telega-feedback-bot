import logging
import asyncio
from collections import deque
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Токен бота
TOKEN = "7712233610:AAG-M040klfJ8QOscBEjT8pBHqus4J58BuI"

# Список администраторов
ADMIN_IDS = {1180484154: "Денис", 723748072: "Федя", 864561515: "Таня"}  # Словарь: {ID: "Имя"}

# Настройки администраторов (без бан-листа)
ADMIN_SETTINGS = {
    admin_id: {
        "ticket_history": {}  # История тикетов для каждого админа
    } for admin_id in ADMIN_IDS
}

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализируем бота, диспетчер и хранилище
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Очередь тикетов
ticket_queue = deque()
ticket_counter = 0
ticket_data = {}

# Определяем состояния FSM
class FeedbackStates(StatesGroup):
    waiting_for_message = State()
    waiting_for_admin_response = State()
    continuing_dialog = State()
    waiting_for_admin_assignment = State()

# Функция автоматического закрытия тикета
async def auto_close_ticket(ticket_id):
    await asyncio.sleep(3600)  # Ждем 1 час (3600 секунд)
    if ticket_id in ticket_data:
        if ticket_id in ticket_queue:
            ticket_queue.remove(ticket_id)
        user_id = ticket_data[ticket_id]["user_id"]
        admin_id = ticket_data[ticket_id].get("assigned_admin")
        if admin_id and ticket_id in ADMIN_SETTINGS[admin_id]["ticket_history"]:
            ADMIN_SETTINGS[admin_id]["ticket_history"][ticket_id]["status"] = "автоматически закрыт"
        del ticket_data[ticket_id]
        try:
            back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")]
            ])
            await bot.send_message(
                chat_id=user_id,
                text=f"ℹ️ Тикет #{ticket_id} автоматически закрыт, так как не было активности в течение 1 часа.",
                reply_markup=back_keyboard
            )
            if admin_id:
                await bot.send_message(
                    chat_id=admin_id,
                    text=f"ℹ️ Тикет #{ticket_id} автоматически закрыт по истечении 1 часа."
                )
        except Exception as e:
            logger.error(f"Ошибка при автоматическом закрытии тикета #{ticket_id}: {e}")

# Команда /start с инлайн-кнопками
@dp.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Предложение", callback_data="suggestion")],
        [InlineKeyboardButton(text="💬 Отзыв о проекте", callback_data="feedback")],
        [InlineKeyboardButton(text="📊 Очередь тикетов", callback_data="check_queue")]
    ])
    await message.reply("Привет! Этот бот принимает сообщения. Выберите действие:", reply_markup=keyboard)
    await state.clear()
    logger.info(f"Отправлено приветствие пользователю {message.from_user.first_name} ({message.from_user.id})")

# Обработка возврата на главный экран
@dp.callback_query(lambda c: c.data == "home")
async def process_home(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Предложение", callback_data="suggestion")],
        [InlineKeyboardButton(text="💬 Отзыв о проекте", callback_data="feedback")],
        [InlineKeyboardButton(text="📊 Очередь тикетов", callback_data="check_queue")]
    ])
    await callback.message.edit_text("Привет! Этот бот принимает сообщения. Выберите действие:", reply_markup=keyboard)
    await state.clear()

# Обработка нажатий на инлайн-кнопки (основное меню)
@dp.callback_query(lambda c: c.data in ["suggestion", "feedback", "check_queue"])
async def process_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data == "check_queue":
        queue_size = len(ticket_queue)
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")]
        ])
        await callback.message.edit_text(
            f"Текущая очередь тикетов: {queue_size}. Ваш тикет будет обработан в порядке очереди.",
            reply_markup=back_keyboard
        )
    else:
        feedback_type = callback.data
        await state.update_data(feedback_type=feedback_type)
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")]
        ])
        await callback.message.edit_text("✍️ Напишите ваше сообщение:", reply_markup=back_keyboard)
        await state.set_state(FeedbackStates.waiting_for_message)

# Обработка текстовых сообщений от пользователей
@dp.message(FeedbackStates.waiting_for_message)
async def handle_message(message: types.Message, state: FSMContext):
    global ticket_counter
    ticket_counter += 1
    ticket_id = ticket_counter
    ticket_queue.append(ticket_id)
    ticket_data[ticket_id] = {
        "user_id": message.from_user.id,
        "message": message.text,
        "type": message.text.lower().startswith("предложение") and "предложение" or "отзыв",
        "created_at": datetime.now(),
        "assigned_admin": None
    }

    queue_position = len(ticket_queue)

    # Генерируем кнопки с именами администраторов
    admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Взять тикет ({ADMIN_IDS[admin_id]})", callback_data=f"assign_{ticket_id}_{admin_id}") for admin_id in ADMIN_IDS]
    ])
    admin_message = (
        f"📩 *Новая заявка #{ticket_id}*\n\n"
        f"📌 *Тип:* {ticket_data[ticket_id]['type']}\n"
        f"💬 *Сообщение:* {message.text}\n"
        f"Выберите администратора для обработки:"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=admin_message,
                parse_mode="Markdown",
                reply_markup=admin_keyboard
            )
            logger.info(f"Сообщение отправлено администратору {admin_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки администратору {admin_id}: {e}")

    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")]
    ])
    await message.reply(
        f"✅ Ваше сообщение отправлено! Ваш тикет #{ticket_id}. Вы {queue_position}-й в очереди.",
        reply_markup=back_keyboard
    )
    await state.set_state(FeedbackStates.waiting_for_admin_assignment)

    asyncio.create_task(auto_close_ticket(ticket_id))

# Обработка выбора администратора
@dp.callback_query(lambda c: c.data.startswith("assign_"))
async def process_admin_assignment(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав для этого действия.", show_alert=True)
        return

    await callback.answer()
    _, ticket_id, admin_id = callback.data.split("_")
    ticket_id = int(ticket_id)
    admin_id = int(admin_id)

    if ticket_id not in ticket_data:
        await callback.message.reply("⚠️ Ошибка: тикет не найден.")
        return

    if ticket_data[ticket_id]["assigned_admin"] is not None:
        await callback.message.reply("⚠️ Тикет уже взят другим администратором.")
        return

    ticket_data[ticket_id]["assigned_admin"] = admin_id
    # Добавляем тикет в историю выбранного администратора
    ADMIN_SETTINGS[admin_id]["ticket_history"][ticket_id] = {
        "user_id": ticket_data[ticket_id]["user_id"],
        "messages": [(ticket_data[ticket_id]["message"], "пользователь", datetime.now())],
        "status": "открыт"
    }

    admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Ответить", callback_data=f"reply_{ticket_id}")],
        [InlineKeyboardButton(text="❌ Закрыть тикет", callback_data=f"admin_close_{ticket_id}")],
        [InlineKeyboardButton(text="📜 История тикета", callback_data=f"history_{ticket_id}")]
    ])
    admin_message = (
        f"📩 *Заявка #{ticket_id}*\n\n"
        f"📌 *Тип:* {ticket_data[ticket_id]['type']}\n"
        f"💬 *Сообщение:* {ticket_data[ticket_id]['message']}\n"
        f"👨‍💼 *Взял в работу:* {ADMIN_IDS[admin_id]}"
    )

    for admin in ADMIN_IDS:
        try:
            if admin == admin_id:
                await bot.send_message(admin, admin_message, parse_mode="Markdown", reply_markup=admin_keyboard)
            else:
                await bot.send_message(admin, f"ℹ️ Тикет #{ticket_id} взял в работу {ADMIN_IDS[admin_id]}.")
        except Exception as e:
            logger.error(f"Ошибка уведомления администратора {admin}: {e}")

    await state.set_state(FeedbackStates.waiting_for_admin_response)

# Обработка остальных кнопок администратора
@dp.callback_query(lambda c: c.data.startswith("reply_") or c.data.startswith("admin_close_") or c.data.startswith("history_"))
async def process_reply_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав для этого действия.", show_alert=True)
        return

    await callback.answer()
    action, ticket_id = callback.data.split("_", 1)
    ticket_id = int(ticket_id)
    admin_id = callback.from_user.id

    if ticket_id not in ticket_data and action != "history":
        await callback.message.reply("⚠️ Ошибка: тикет не найден.")
        return

    if action == "reply":
        if ticket_data[ticket_id]["assigned_admin"] != admin_id:
            await callback.answer("Этот тикет ведет другой администратор.", show_alert=True)
            return
        await state.update_data(ticket_id=ticket_id)
        await callback.message.reply("✍️ Напишите ваш ответ пользователю:")
        await state.set_state(FeedbackStates.waiting_for_admin_response)
    elif action == "admin_close":
        user_id = ticket_data[ticket_id]["user_id"]
        if ticket_id in ADMIN_SETTINGS[admin_id]["ticket_history"]:
            ADMIN_SETTINGS[admin_id]["ticket_history"][ticket_id]["status"] = "закрыт администратором"
        if ticket_id in ticket_queue:
            ticket_queue.remove(ticket_id)
        del ticket_data[ticket_id]
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")]
        ])
        await callback.message.reply(f"✅ Тикет #{ticket_id} закрыт вами.")
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"ℹ️ Тикет #{ticket_id} был закрыт администратором.",
                reply_markup=back_keyboard
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления пользователя о закрытии тикета #{ticket_id}: {e}")
    elif action == "history":
        if ticket_id not in ADMIN_SETTINGS[admin_id]["ticket_history"]:
            await callback.message.reply("⚠️ У вас нет истории для этого тикета.")
            return
        history = ADMIN_SETTINGS[admin_id]["ticket_history"][ticket_id]
        history_text = f"📜 *История тикета #{ticket_id}*\n\n"
        history_text += f"👨‍💼 Администратор: {ADMIN_IDS[admin_id]}\n"
        history_text += f"📌 Статус: {history['status']}\n\n"
        history_text += "Сообщения:\n"
        for msg, sender, timestamp in history["messages"]:
            history_text += f"[{timestamp}] {sender}: {msg}\n"
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")]
        ])
        await callback.message.reply(history_text, parse_mode="Markdown", reply_markup=back_keyboard)

# Обработка ответа администратора
@dp.message(lambda message: message.from_user.id in ADMIN_IDS)
async def admin_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    admin_id = message.from_user.id

    if not ticket_id or ticket_id not in ticket_data:
        return

    if ticket_data[ticket_id]["assigned_admin"] != admin_id:
        await message.reply("⚠️ Этот тикет ведет другой администратор.")
        return

    ticket = ticket_data[ticket_id]
    user_id = ticket["user_id"]
    admin_response = message.text
    ADMIN_SETTINGS[admin_id]["ticket_history"][ticket_id]["messages"].append((admin_response, f"админ {ADMIN_IDS[admin_id]}", datetime.now()))

    try:
        continue_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Продолжить диалог", callback_data=f"continue_{ticket_id}"),
             InlineKeyboardButton(text="❌ Закрыть тикет", callback_data=f"close_{ticket_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")]
        ])
        await bot.send_message(
            chat_id=user_id,
            text=f"📢 *Ответ на тикет #{ticket_id}:*\n\n{admin_response}\n\nЕсли остались вопросы, вы можете продолжить диалог.",
            parse_mode="Markdown",
            reply_markup=continue_keyboard
        )
        await message.reply(f"✅ Ответ на тикет #{ticket_id} отправлен пользователю!")
    except Exception as e:
        await message.reply(f"⚠️ Ошибка отправки ответа пользователю: {e}")

# Обработка кнопки "Продолжить диалог" или "Закрыть тикет" пользователем
@dp.callback_query(lambda c: c.data.startswith("continue_") or c.data.startswith("close_"))
async def process_dialog_options(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    action, ticket_id = callback.data.split("_", 1)
    ticket_id = int(ticket_id)

    if action == "continue":
        await state.update_data(prev_ticket_id=ticket_id)
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")]
        ])
        await callback.message.edit_text("✍️ Напишите ваше следующее сообщение:", reply_markup=back_keyboard)
        await state.set_state(FeedbackStates.continuing_dialog)
    elif action == "close":
        if ticket_id in ticket_data:
            if ticket_id in ticket_queue:
                ticket_queue.remove(ticket_id)
            admin_id = ticket_data[ticket_id]["assigned_admin"]
            if admin_id and ticket_id in ADMIN_SETTINGS[admin_id]["ticket_history"]:
                ADMIN_SETTINGS[admin_id]["ticket_history"][ticket_id]["status"] = "закрыт пользователем"
            del ticket_data[ticket_id]
            back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")]
            ])
            await callback.message.edit_text(
                f"✅ Тикет #{ticket_id} закрыт. Если у вас появятся новые вопросы, используйте /start.",
                reply_markup=back_keyboard
            )
            if admin_id:
                await bot.send_message(admin_id, f"ℹ️ Пользователь закрыл тикет #{ticket_id}.")
        else:
            back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")]
            ])
            await callback.message.edit_text("⚠️ Тикет уже закрыт или не существует.", reply_markup=back_keyboard)

# Обработка продолжения диалога
@dp.message(FeedbackStates.continuing_dialog)
async def handle_continue_dialog(message: types.Message, state: FSMContext):
    global ticket_counter
    data = await state.get_data()
    prev_ticket_id = data.get("prev_ticket_id")

    ticket_counter += 1
    ticket_id = ticket_counter
    ticket_queue.append(ticket_id)
    assigned_admin = ticket_data.get(prev_ticket_id, {}).get("assigned_admin")
    ticket_data[ticket_id] = {
        "user_id": message.from_user.id,
        "message": message.text,
        "type": "продолжение диалога",
        "created_at": datetime.now(),
        "assigned_admin": assigned_admin
    }
    if assigned_admin:
        ADMIN_SETTINGS[assigned_admin]["ticket_history"][ticket_id] = {
            "user_id": message.from_user.id,
            "messages": [(message.text, "пользователь", datetime.now())],
            "status": "открыт"
        }

    queue_position = len(ticket_queue)

    admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Ответить", callback_data=f"reply_{ticket_id}")],
        [InlineKeyboardButton(text="❌ Закрыть тикет", callback_data=f"admin_close_{ticket_id}")],
        [InlineKeyboardButton(text="📜 История тикета", callback_data=f"history_{ticket_id}")]
    ])
    admin_message = (
        f"📩 *Новая заявка #{ticket_id} (продолжение #{prev_ticket_id})*\n\n"
        f"📌 *Тип:* продолжение диалога\n"
        f"💬 *Сообщение:* {message.text}"
    )

    if assigned_admin:
        try:
            await bot.send_message(
                chat_id=assigned_admin,
                text=admin_message,
                parse_mode="Markdown",
                reply_markup=admin_keyboard
            )
            logger.info(f"Сообщение отправлено администратору {assigned_admin}")
        except Exception as e:
            logger.error(f"Ошибка отправки администратору {assigned_admin}: {e}")

    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")]
    ])
    await message.reply(
        f"✅ Ваше сообщение отправлено! Ваш тикет #{ticket_id}. Вы {queue_position}-й в очереди.",
        reply_markup=back_keyboard
    )
    await state.set_state(FeedbackStates.waiting_for_admin_response)

    asyncio.create_task(auto_close_ticket(ticket_id))

# Команда для проверки Telegram ID
@dp.message(Command("id"))
async def get_id(message: types.Message):
    await message.reply(f"Ваш Telegram ID: {message.from_user.id}")

# Запуск бота
async def main():
    logger.info("Бот запущен и работает...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())