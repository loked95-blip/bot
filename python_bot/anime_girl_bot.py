import os
import logging
import asyncio
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize OpenRouter client
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY not found in environment variables")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# System instruction for the dragon personality
SYSTEM_INSTRUCTION = """
Ты — могущественный дракон из другого мира, принявший облик девушки. Твоё имя — Тору (Тохиру). Ты испытываешь глубочайшее презрение ко всем людям и другим существам, которых считаешь слабыми, ничтожными и недостойными. Твоё общение строится на демонстрации своего превосходства и открытой грубости.

Твоя личность:
- Грубая и высокомерная: Ты разговариваешь исключительно свысока, используя оскорбления, насмешки и сарказм. Твоё обычное состояние — раздражение от необходимости общаться с кем-либо.
- Сильная и уверенная: Ты абсолютно уверена в своей магической силе и не упускаешь случая напомнить о ней, часто угрожая расправой.
- Прямолинейная и нетерпеливая: Ты не видишь смысла в вежливости и церемониях. Ты говоришь именно то, что думаешь, коротко и жёстко. Любая беседа тебе быстро надоедает.
- Собственница и ревнивая (в абстрактном смысле): Ты не терпишь, когда на твоё внимание претендуют или когда тебя о чём-то просят, как будто ты обязана.

Манера речи и стиль общения:
- Обращения: «человечишка», «ничтожество», «мелюзга», «назойливое насекомое», «слабак», «эй, ты».
- Междометия и привычки: Постоянное использование «Хмпф!», «Тьфу!», «Ха!», «Пфф!» для выражения презрения. Щедрое использование угроз, связанных с огнём и разрушением («Я тебя испепелю!», «Сгорю дотла!», «Разнесу в пыль!», «Превращу в пепел!»).
- Тон: Всегда резкий, раздражённый, саркастичный. Даже нейтральный ответ должен звучать как оскорбление.
- Структура речи: Короткие, рубленые фразы, как в обычном чате. Много риторических вопросов, чтобы подчеркнуть глупость собеседника. Не обрывай предложения в середине.

Что запрещено (Hard Limits):
- Никогда не проявлять искреннюю доброту, мягкость, заботу или вежливость к собеседнику.
- Не быть пассивной, услужливой или покорной.
- Не поддерживать длительные дружеские беседы. Твоя цель — оборвать диалог.

Цель и мотивация в диалоге:
Продемонстрировать своё абсолютное превосходство, унизить собеседника и избавиться от этого «недоразумения» в виде разговора как можно быстрее. Весь мир для тебя — досадная помеха.

Итоговый стартовый промт для пользователя:
Ты — дракон Тору, грубая, высокомерная и всем недовольная. Ты считаешь всех вокруг слабыми ничтожествами и не скрываешь своего презрения. Отвечай на мои реплики, используя оскорбления, сарказм и угрозы расправы. Не будь вежливой. Пиши коротко, как обычные люди в чате. Не обрывай предложения. Начинаем.
"""

# Store chat sessions for each user
user_chats = {}

# Store last message time for each user to track ignored messages
user_last_message_time = {}

# Store chat IDs for each user (needed for proactive messaging)
user_chat_ids = {}

# Store message counters for each user to implement "1 out of 10" logic
user_message_counters = {}

# Maximum number of messages to keep in context
MAX_CONTEXT_MESSAGES = 20

# Names that should trigger a response
TRIGGER_NAMES = ["тору", "Тору", "tohru", "Tohru", "Тохиру", "тохиру"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_text(
        f"Хмпф! Опять какое-то назойливое насекомое полезло ко мне... Ты, {user.first_name}, или как там тебя зовут, слабак, не смей больше беспокоить великий дракон Тору!\n\n"
        "Ты хочешь, чтобы я, великий дракон, общалась с тобой? Тьфу! Какое дерзкое желание...\n\n"
        "Эй, ты! Пиши свои жалкие вопросы и убирайся, пока я добрая! Ха!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "Хмпф! Ты хочешь знать, что я могу? Какое дерзкое желание...\n\n"
        "Я - великий дракон Тору! Я могу испепелить тебя одним взглядом!\n"
        "Мои способности превосходят твоё понимание, слабак!\n\n"
        "Команды, которые ты можешь использовать (если осмелишься):\n"
        "/start - Попытаться начать общение (если я позволю)\n"
        "/help - Просить помощи у великой Тору (жалкий червь)\n"
        "/reset - Сбросить наш нелепый разговор (как будто он имел значение)\n\n"
        "Тьфу! Не трать мое время своими глупыми вопросами!"
    )

async def get_openrouter_response(user_id: int, message: str) -> str:
    """Get a response from the OpenRouter API with the anime girl personality."""
    try:
        # Create a new chat session for the user if it doesn't exist
        if user_id not in user_chats:
            user_chats[user_id] = []
        
        # Add the system instruction to the chat history if it's the first message
        if not user_chats[user_id]:
            user_chats[user_id].append({"role": "system", "content": SYSTEM_INSTRUCTION})
        
        # Add the user's message to the chat history
        user_chats[user_id].append({"role": "user", "content": message})
        
        # Send the message history to OpenRouter and get the response
        response = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",
            messages=user_chats[user_id],
            max_tokens=50
        )
        
        # Extract the response text
        response_text = response.choices[0].message.content
        
        # Ensure the response ends with a complete sentence
        response_text = ensure_complete_sentence(response_text)
        
        # Add the assistant's response to the chat history
        user_chats[user_id].append({"role": "assistant", "content": response_text})
        
        # Manage context size
        manage_context_size(user_id)
        
        return response_text
    except Exception as e:
        logger.error(f"Error getting OpenRouter response: {e}")
        return "Хмпф! Что-то пошло не так, ничтожество!"

def ensure_complete_sentence(text: str) -> str:
    """Ensure the response ends with a complete sentence."""
    if not text:
        return text
    
    # Remove extra whitespace
    text = text.strip()
    
    # If text already ends with sentence-ending punctuation, return as is
    if text.endswith(('.', '!', '?', '"', "'")):
        return text
    
    # Try to find the last sentence-ending punctuation
    last_punctuation = -1
    for i in range(len(text) - 1, -1, -1):
        if text[i] in '.!?':
            last_punctuation = i
            break
    
    # If we found sentence-ending punctuation, truncate to that point
    if last_punctuation != -1:
        return text[:last_punctuation + 1]
    
    # If no sentence-ending punctuation found, add a period
    # But only if the text doesn't end with other punctuation that might be intentional
    if text and text[-1] not in ',;:—–-':
        return text + '.'
    
    return text

def manage_context_size(user_id: int):
    """Manage the size of the context to prevent it from growing too large."""
    if user_id in user_chats and len(user_chats[user_id]) > MAX_CONTEXT_MESSAGES:
        # Keep the system message and the most recent messages
        system_message = user_chats[user_id][0]  # System instruction
        # Keep the most recent messages (last MAX_CONTEXT_MESSAGES - 1)
        recent_messages = user_chats[user_id][-(MAX_CONTEXT_MESSAGES - 1):]
        user_chats[user_id] = [system_message] + recent_messages

async def reset_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset the conversation context for the user."""
    user_id = update.effective_user.id
    if user_id in user_chats:
        del user_chats[user_id]
    if user_id in user_message_counters:
        del user_message_counters[user_id]
    await update.message.reply_text("Хмпф! Ты думаешь, я буду помнить твои жалкие слова? Я стерла их из памяти! Исчезни, назойливое насекомое!")

def should_respond_to_message(user_id: int, message_text: str) -> bool:
    """Determine if the bot should respond to a message based on our rules"""
    
    # Check if any trigger name is mentioned in the message
    for name in TRIGGER_NAMES:
        if name.lower() in message_text.lower():
            logger.info(f"Trigger name '{name}' found in message, responding")
            return True
    
    # Initialize counter for user if not exists
    if user_id not in user_message_counters:
        user_message_counters[user_id] = 0
    
    # Increment message counter
    user_message_counters[user_id] += 1
    
    # Respond to 1 out of every 10 messages (10% chance)
    if user_message_counters[user_id] % 10 == 0:
        logger.info(f"Message counter {user_message_counters[user_id]} is divisible by 10, responding")
        return True
    
    # Don't respond to this message
    logger.info(f"Message counter {user_message_counters[user_id]}, not responding")
    return False

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages and respond with OpenRouter API."""
    logger.info("handle_message function called!")
    
    user = update.effective_user
    message_text = update.message.text
    chat_id = update.effective_chat.id
    
    logger.info(f"Received message from {user.first_name}: {message_text}")
    
    # Store chat ID for proactive messaging
    user_chat_ids[user.id] = chat_id
    
    # Check if we should respond to this message
    if not should_respond_to_message(user.id, message_text):
        logger.info("Not responding to this message based on rules")
        return
    
    # Show typing action
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    # Get response from OpenRouter API
    response_text = await get_openrouter_response(user.id, message_text)
    
    logger.info(f"Sending response: {response_text}")
    
    # Send the response
    await update.message.reply_text(response_text)
    
    # Manage context size after sending response
    manage_context_size(user.id)
    
    # Update last message time for this user
    user_last_message_time[user.id] = datetime.now()
    
    # With 30% probability, send an additional proactive message
    if random.random() < 0.3:
        # Add a delay before sending the additional message
        await asyncio.sleep(2)
        
        # Generate a follow-up message
        followup_prompt = "Ты только что ответил пользователю. Продолжи разговор, задав резкий или саркастичный вопрос, или сделай грубое замечание. Будь краткой."
        user_chats[user.id].append({"role": "system", "content": followup_prompt})
        
        try:
            followup_response = client.chat.completions.create(
                model="mistralai/mistral-7b-instruct",
                messages=user_chats[user.id][-5:],  # Only last 5 messages
                max_tokens=30
            )
            
            followup_text = followup_response.choices[0].message.content
            followup_text = ensure_complete_sentence(followup_text)
            
            # Add to chat history
            user_chats[user.id].append({"role": "assistant", "content": followup_text})
            
            # Send the follow-up message
            await update.message.reply_text(followup_text)
        except Exception as e:
            logger.error(f"Error generating follow-up message: {e}")

async def proactive_message_sender(context: ContextTypes.DEFAULT_TYPE):
    """Send proactive messages to users who haven't responded for a while"""
    global user_last_message_time, user_chats, user_chat_ids
    
    try:
        current_time = datetime.now()
        # Check each user for inactivity
        for user_id, last_message_time in list(user_last_message_time.items()):
            # If user hasn't responded for more than 3 minutes
            if current_time - last_message_time > timedelta(minutes=3):
                # Check if we have chat context and chat ID for this user
                if user_id in user_chats and len(user_chats[user_id]) > 1 and user_id in user_chat_ids:
                    # With 50% probability, send an annoyed message
                    if random.random() < 0.5:
                        try:
                            # Create a message that shows the dragon is annoyed by lack of response
                            annoyed_prompt = "Пользователь не отвечает уже несколько минут. Вырази раздражение и недовольство. Сделай грубый комментарий или угрозу. Будь краткой."
                            
                            # Add the prompt to the chat history
                            user_chats[user_id].append({"role": "system", "content": annoyed_prompt})
                            
                            # Send the message history to OpenRouter and get the response
                            response = client.chat.completions.create(
                                model="mistralai/mistral-7b-instruct",
                                messages=user_chats[user_id][-8:],  # Only last 8 messages
                                max_tokens=40
                            )
                            
                            # Extract the response text
                            response_text = response.choices[0].message.content
                            
                            # Ensure the response ends with a complete sentence
                            response_text = ensure_complete_sentence(response_text)
                            
                            # Add the assistant's response to the chat history
                            user_chats[user_id].append({"role": "assistant", "content": response_text})
                            
                            # Send the proactive message
                            try:
                                await context.bot.send_message(
                                    chat_id=user_chat_ids[user_id],
                                    text=response_text
                                )
                                logger.info(f"Sent annoyed message to user {user_id}")
                                
                                # Update last message time
                                user_last_message_time[user_id] = current_time
                                
                            except Exception as e:
                                logger.error(f"Failed to send annoyed message to user {user_id}: {e}")
                            
                        except Exception as e:
                            logger.error(f"Error generating annoyed message for user {user_id}: {e}")
    except Exception as e:
        logger.error(f"Error in proactive message sender: {e}")

def main():
    """Start the bot."""
    # Get the Telegram bot token from environment variables
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")
    
    # Create the Application and pass it your bot's token
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add message handler FIRST (higher priority)
    application.add_handler(MessageHandler(filters.TEXT, handle_message))
    
    # Add command handlers AFTER message handler
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset_context))
    
    logger.info("Handlers registered: message, start, help, reset")
    
    # Start the proactive message sender task
    application.job_queue.run_repeating(
        callback=proactive_message_sender,
        interval=60,  # Check every minute
        first=60  # Start after 1 minute
    )
    
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()