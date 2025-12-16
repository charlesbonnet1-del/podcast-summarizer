"""
Telegram Bot for Singular Daily.
Handles user connection and content submission.
"""
import os
import re
import asyncio
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)
import structlog
from dotenv import load_dotenv

from db import (
    get_user_by_connection_code,
    get_user_by_telegram_id,
    link_telegram_to_user,
    add_to_content_queue,
    get_pending_content,
    add_user_interest,
    get_user_interests,
    remove_user_interest,
)
from extractor import detect_source_type
from worker import process_user_queue

load_dotenv()
log = structlog.get_logger()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Conversation states
WAITING_FOR_CODE = 1


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /start command."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    log.info("Start command received", user_id=user.id, username=user.username)
    
    # Check if user is already connected
    existing_user = get_user_by_telegram_id(chat_id)
    
    if existing_user:
        await update.message.reply_text(
            f"👋 Welcome back!\n\n"
            f"Your account is already connected. You can:\n\n"
            f"📎 Send any URL to add it to your queue\n"
            f"🏷️ /add [topic] - Follow a topic (e.g. /add AI)\n"
            f"📋 /topics - View your followed topics\n"
            f"📋 /queue - View your pending content\n"
            f"🎙️ /generate - Create your podcast now\n"
            f"❓ /help - Get help"
        )
        return ConversationHandler.END
    
    # New user - ask for connection code
    await update.message.reply_text(
        f"👋 Welcome to Singular Daily!\n\n"
        f"To connect your account, please enter your 6-digit connection code.\n\n"
        f"You can find this code in your dashboard at singular.daily/dashboard"
    )
    
    return WAITING_FOR_CODE


async def receive_connection_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle connection code input."""
    code = update.message.text.strip()
    chat_id = update.effective_chat.id
    
    # Validate code format
    if not re.match(r'^\d{6}$', code):
        await update.message.reply_text(
            "❌ Invalid code format. Please enter a 6-digit code."
        )
        return WAITING_FOR_CODE
    
    # Find user by code
    user = get_user_by_connection_code(code)
    
    if not user:
        await update.message.reply_text(
            "❌ Code not found. Please check your code and try again.\n\n"
            "You can find your code at singular.daily/dashboard"
        )
        return WAITING_FOR_CODE
    
    # Check if code is already used
    if user.get("telegram_chat_id"):
        await update.message.reply_text(
            "❌ This code has already been used. Please generate a new one in your dashboard."
        )
        return WAITING_FOR_CODE
    
    # Link Telegram to user
    success = link_telegram_to_user(user["id"], chat_id)
    
    if success:
        log.info("Telegram account linked", user_id=user["id"], chat_id=chat_id)
        await update.message.reply_text(
            f"✅ Account connected successfully!\n\n"
            f"You can now send me any URL and I'll add it to your podcast queue.\n\n"
            f"Try it now - send me a YouTube link or article!"
        )
    else:
        await update.message.reply_text(
            "❌ Something went wrong. Please try again or contact support."
        )
    
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    await update.message.reply_text("Operation cancelled. Send /start to begin again.")
    return ConversationHandler.END


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle URL submissions."""
    chat_id = update.effective_chat.id
    text = update.message.text
    
    # Check if user is connected
    user = get_user_by_telegram_id(chat_id)
    
    if not user:
        await update.message.reply_text(
            "❌ Please connect your account first.\n\n"
            "Send /start to begin."
        )
        return
    
    # Extract URLs from message
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)
    
    if not urls:
        await update.message.reply_text(
            "🤔 I couldn't find a valid URL in your message.\n\n"
            "Please send a YouTube link, article URL, or podcast link."
        )
        return
    
    # Process each URL
    added_count = 0
    for url in urls:
        source_type = detect_source_type(url)
        result = add_to_content_queue(user["id"], url, source_type)
        
        if result:
            added_count += 1
            log.info("Content added to queue", user_id=user["id"], url=url, source_type=source_type)
    
    if added_count > 0:
        emoji = "🎬" if "youtube" in source_type else "📰" if source_type == "article" else "🎙️"
        await update.message.reply_text(
            f"{emoji} Added to your queue!\n\n"
            f"Use /generate to create your podcast now, or keep adding more content."
        )
    else:
        await update.message.reply_text(
            "❌ Couldn't add this content. Please try again."
        )


async def show_queue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's pending content queue."""
    chat_id = update.effective_chat.id
    
    user = get_user_by_telegram_id(chat_id)
    if not user:
        await update.message.reply_text("Please connect your account first with /start")
        return
    
    pending = get_pending_content(user["id"])
    
    if not pending:
        await update.message.reply_text(
            "📭 Your queue is empty!\n\n"
            "Send me a URL to add content."
        )
        return
    
    # Build queue message
    message = f"📋 Your queue ({len(pending)} items):\n\n"
    
    for i, item in enumerate(pending[:10], 1):
        source_emoji = "🎬" if item["source_type"] == "youtube" else "📰" if item["source_type"] == "article" else "🎙️"
        title = item.get("title") or item["url"][:50] + "..."
        message += f"{i}. {source_emoji} {title}\n"
    
    if len(pending) > 10:
        message += f"\n... and {len(pending) - 10} more"
    
    message += "\n\nUse /generate to create your podcast!"
    
    await update.message.reply_text(message)


async def generate_podcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trigger podcast generation."""
    chat_id = update.effective_chat.id
    
    user = get_user_by_telegram_id(chat_id)
    if not user:
        await update.message.reply_text("Please connect your account first with /start")
        return
    
    pending = get_pending_content(user["id"])
    
    if not pending:
        await update.message.reply_text(
            "📭 Your queue is empty!\n\n"
            "Send me some URLs first, then use /generate."
        )
        return
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        f"🎙️ Generating your podcast...\n\n"
        f"Processing {len(pending)} items. This may take a few minutes."
    )
    
    try:
        # Process the queue
        episode = await asyncio.to_thread(process_user_queue, user["id"])
        
        if episode:
            await processing_msg.edit_text(
                f"✅ Your podcast is ready!\n\n"
                f"🎧 {episode['title']}\n"
                f"⏱️ {episode['audio_duration'] // 60} minutes\n\n"
                f"Listen in your podcast app or at singular.daily/dashboard"
            )
        else:
            await processing_msg.edit_text(
                "❌ Something went wrong during generation.\n\n"
                "Please try again or contact support."
            )
    
    except Exception as e:
        log.error("Generation failed", error=str(e))
        await processing_msg.edit_text(
            "❌ Generation failed. Please try again later."
        )


# ============================================
# TOPIC/INTEREST MANAGEMENT COMMANDS
# ============================================

async def add_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a topic/keyword to follow. Usage: /add AI or /add Machine Learning"""
    chat_id = update.effective_chat.id
    
    user = get_user_by_telegram_id(chat_id)
    if not user:
        await update.message.reply_text("Please connect your account first with /start")
        return
    
    # Get the keyword from command arguments
    if not context.args:
        await update.message.reply_text(
            "❓ Please specify a topic to follow.\n\n"
            "Example: `/add Artificial Intelligence`\n"
            "Example: `/add Python programming`",
            parse_mode="Markdown"
        )
        return
    
    keyword = " ".join(context.args).strip()
    
    if len(keyword) < 2:
        await update.message.reply_text("❌ Topic must be at least 2 characters.")
        return
    
    if len(keyword) > 50:
        await update.message.reply_text("❌ Topic must be less than 50 characters.")
        return
    
    result = add_user_interest(user["id"], keyword)
    
    if result:
        if isinstance(result, dict) and result.get("error") == "duplicate":
            await update.message.reply_text(
                f"ℹ️ You're already following *{keyword}*",
                parse_mode="Markdown"
            )
        else:
            log.info("Topic added", user_id=user["id"], keyword=keyword)
            await update.message.reply_text(
                f"✅ Now following: *{keyword}*\n\n"
                f"I'll find relevant news for you every day!\n"
                f"Use /topics to see all your topics.",
                parse_mode="Markdown"
            )
    else:
        await update.message.reply_text("❌ Couldn't add this topic. Please try again.")


async def list_topics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all followed topics."""
    chat_id = update.effective_chat.id
    
    user = get_user_by_telegram_id(chat_id)
    if not user:
        await update.message.reply_text("Please connect your account first with /start")
        return
    
    interests = get_user_interests(user["id"])
    
    if not interests:
        await update.message.reply_text(
            "📭 You're not following any topics yet!\n\n"
            "Add topics with: `/add [topic]`\n"
            "Example: `/add Artificial Intelligence`",
            parse_mode="Markdown"
        )
        return
    
    # Build list message
    message = f"🏷️ *Your Topics* ({len(interests)}):\n\n"
    
    for i, interest in enumerate(interests, 1):
        message += f"{i}. {interest['keyword']}\n"
    
    message += "\n📰 I'll fetch news on these topics daily!\n"
    message += "Remove with: `/remove [topic]`"
    
    await update.message.reply_text(message, parse_mode="Markdown")


async def remove_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a followed topic. Usage: /remove AI"""
    chat_id = update.effective_chat.id
    
    user = get_user_by_telegram_id(chat_id)
    if not user:
        await update.message.reply_text("Please connect your account first with /start")
        return
    
    # Get the keyword from command arguments
    if not context.args:
        await update.message.reply_text(
            "❓ Please specify a topic to remove.\n\n"
            "Example: `/remove AI`\n"
            "Use /topics to see your list.",
            parse_mode="Markdown"
        )
        return
    
    keyword = " ".join(context.args).strip()
    
    success = remove_user_interest(user["id"], keyword)
    
    if success:
        log.info("Topic removed", user_id=user["id"], keyword=keyword)
        await update.message.reply_text(
            f"✅ Removed: *{keyword}*\n\n"
            f"Use /topics to see your remaining topics.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"❌ Topic *{keyword}* not found in your list.\n"
            f"Use /topics to see your current topics.",
            parse_mode="Markdown"
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help message."""
    await update.message.reply_text(
        "🎙️ *TLDL Bot*\n\n"
        "*📎 Manual Content:*\n"
        "Send me any URL (YouTube, articles)\n\n"
        "*🏷️ Auto Topics:*\n"
        "/add [topic] - Follow a topic\n"
        "/topics - View your topics\n"
        "/remove [topic] - Unfollow a topic\n\n"
        "*📋 Queue & Generate:*\n"
        "/queue - View pending content\n"
        "/generate - Create your podcast\n\n"
        "*🔧 Account:*\n"
        "/start - Connect your account\n"
        "/help - Show this help\n\n"
        "💡 *Tip:* Add topics like 'AI', 'Startup', 'Tech' and I'll fetch news for you daily!",
        parse_mode="Markdown"
    )


async def setup_commands(app: Application) -> None:
    """Set up bot commands for the menu."""
    commands = [
        BotCommand("start", "Connect your account"),
        BotCommand("add", "Follow a topic (e.g. /add AI)"),
        BotCommand("topics", "View your followed topics"),
        BotCommand("remove", "Unfollow a topic"),
        BotCommand("queue", "View your content queue"),
        BotCommand("generate", "Create your podcast now"),
        BotCommand("help", "Get help"),
    ]
    await app.bot.set_my_commands(commands)


def main():
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    
    log.info("Starting Telegram bot")
    
    # Create application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Conversation handler for connection flow
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_connection_code)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Add handlers
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("queue", show_queue))
    app.add_handler(CommandHandler("generate", generate_podcast))
    app.add_handler(CommandHandler("help", help_command))
    
    # Topic management commands
    app.add_handler(CommandHandler("add", add_topic))
    app.add_handler(CommandHandler("topics", list_topics))
    app.add_handler(CommandHandler("list", list_topics))  # Alias
    app.add_handler(CommandHandler("remove", remove_topic))
    
    # URL handler (must be after conversation handler)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(r'https?://'),
        handle_url
    ))
    
    # Setup commands on startup
    app.post_init = setup_commands
    
    # Start polling
    log.info("Bot is running")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
