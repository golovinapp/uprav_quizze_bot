"""Telegram bot handlers — aiogram 3.x with FSM."""

import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import database as db
from quiz import AGE_GROUPS, LETTER_DISPLAY, compute_result, format_question, format_result_message
from config import BOT_TOKEN

logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)


# ─── FSM States ───────────────────────────────────────────────

class QuizStates(StatesGroup):
    waiting_age = State()
    answering = State()


# ─── Helpers ──────────────────────────────────────────────────

def question_keyboard(q_index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="А", callback_data=f"ans:{q_index}:A"),
            InlineKeyboardButton(text="Б", callback_data=f"ans:{q_index}:B"),
            InlineKeyboardButton(text="В", callback_data=f"ans:{q_index}:C"),
        ]
    ])


def age_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=ag, callback_data=f"age:{ag}")]
        for ag in AGE_GROUPS
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def send_question(target, q_index: int, questions: list[dict]):
    """Send question to chat. target can be Message or CallbackQuery."""
    q = questions[q_index]
    text = format_question(q, q_index)
    kb = question_keyboard(q_index)
    if isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")


# ─── /start ──────────────────────────────────────────────────

WELCOME_TEXT = (
    "Добро пожаловать.\n\n"
    "Данный тест состоит из 6 рабочих ситуаций и поможет определить "
    "ваш управленческий профиль и готовность к работе "
    "с новым поколением Z.\n\n"
    "Пожалуйста, выбирайте вариант ответа, который наиболее точно "
    "отражает вашу реальную реакцию.\n\n"
    "Нажмите <b>«Начать тест»</b>, чтобы приступить."
)


@router.message(CommandStart(deep_link=True))
async def cmd_start_deep(message: Message, state: FSMContext, command: CommandStart):
    """Handle /start with deep link (conference session)."""
    await state.clear()
    session_id = command.args.strip() if command.args else ""

    if session_id and session_id != "free":
        if not await db.session_exists(session_id):
            session_id = "free"
        elif await db.has_session_result(message.from_user.id, session_id):
            await message.answer(
                "Вы уже проходили тест на этом мероприятии. "
                "Запускаю свободное тестирование!"
            )
            session_id = "free"
    else:
        session_id = "free"

    await state.update_data(session_id=session_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Начать тест", callback_data="start_quiz")]
    ])
    await message.answer(WELCOME_TEXT, reply_markup=kb, parse_mode="HTML")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Handle plain /start (free mode)."""
    await state.clear()
    await state.update_data(session_id="free")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Начать тест", callback_data="start_quiz")]
    ])
    await message.answer(WELCOME_TEXT, reply_markup=kb, parse_mode="HTML")


# ─── Begin quiz ───────────────────────────────────────────────

@router.callback_query(F.data == "start_quiz")
async def on_start_quiz(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)

    # Load questions from DB at quiz start (always fresh)
    questions = await db.get_questions()
    if not questions:
        await callback.message.answer("⚠️ Тест ещё не настроен. Обратитесь к администратору.")
        return

    await state.update_data(total_questions=len(questions))
    await state.set_state(QuizStates.waiting_age)
    await callback.message.answer(
        "Для начала, пожалуйста, укажите вашу возрастную группу:",
        reply_markup=age_keyboard(),
    )


# ─── Age selection ────────────────────────────────────────────

@router.callback_query(QuizStates.waiting_age, F.data.startswith("age:"))
async def on_age_selected(callback: CallbackQuery, state: FSMContext):
    age_group = callback.data.split(":", 1)[1]
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)

    await db.upsert_user(callback.from_user.id, age_group)

    # Load questions fresh from DB
    questions = await db.get_questions()

    await state.update_data(
        age_group=age_group,
        q_index=0,
        score_a=0,
        score_b=0,
        score_c=0,
        total_questions=len(questions),
    )
    await state.set_state(QuizStates.answering)
    await send_question(callback, 0, questions)


# ─── Answer handling ──────────────────────────────────────────

@router.callback_query(QuizStates.answering, F.data.startswith("ans:"))
async def on_answer(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    q_index_from_cb = int(parts[1])
    letter = parts[2]  # A, B, or C

    data = await state.get_data()
    current_q = data.get("q_index", 0)
    total_questions = data.get("total_questions", 6)

    # Guard: ignore clicks on old questions
    if q_index_from_cb != current_q:
        await callback.answer("Этот вопрос уже был отвечен.")
        return

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)

    # Increment score
    score_key = f"score_{letter.lower()}"
    new_scores = {
        "score_a": data.get("score_a", 0),
        "score_b": data.get("score_b", 0),
        "score_c": data.get("score_c", 0),
    }
    new_scores[score_key] = new_scores[score_key] + 1

    next_q = current_q + 1
    new_scores["q_index"] = next_q

    await state.update_data(**new_scores)

    if next_q < total_questions:
        questions = await db.get_questions()
        await send_question(callback, next_q, questions)
    else:
        # Quiz complete
        sa, sb, sc = new_scores["score_a"], new_scores["score_b"], new_scores["score_c"]
        final = compute_result(sa, sb, sc)
        session_id = data.get("session_id", "free")

        await db.save_result(
            telegram_id=callback.from_user.id,
            session_id=session_id,
            score_a=sa,
            score_b=sb,
            score_c=sc,
            final_result=final,
        )

        # Load result texts from DB
        result_texts = await db.get_result_texts()
        if final in result_texts:
            result_text = format_result_message(result_texts[final], sa, sb, sc)
        else:
            result_text = f"📊 Ваш результат: {LETTER_DISPLAY.get(final, final)}\n\nА: {sa}  |  Б: {sb}  |  В: {sc}"

        await callback.message.answer(result_text, parse_mode="HTML")

        # Offer to retake
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Пройти ещё раз", callback_data="start_quiz")]
        ])
        await callback.message.answer("Хотите пройти тест ещё раз?", reply_markup=kb)
        await state.clear()
        await state.update_data(session_id="free")


# ─── /delete_data ─────────────────────────────────────────────

@router.message(Command("delete_data"))
async def cmd_delete_data(message: Message, state: FSMContext):
    await state.clear()
    await db.delete_user_data(message.from_user.id)
    await message.answer("✅ Ваши данные успешно удалены из системы.")


# ─── Setup commands menu ──────────────────────────────────────

async def set_bot_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать тест"),
        BotCommand(command="delete_data", description="Удалить мои данные"),
    ])
