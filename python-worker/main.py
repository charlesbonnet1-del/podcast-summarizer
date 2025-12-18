"""
Main entry point for the Singular Daily worker.
Runs both the Telegram bot and HTTP server concurrently.
"""
import os
import threading
import structlog
from dotenv import load_dotenv

load_dotenv()
log = structlog.get_logger()


def run_telegram_bot():
    """Run the Telegram bot."""
    from bot import main as bot_main
    log.info("Starting Telegram bot...")
    bot_main()


def run_http_server():
    """Run the HTTP server for Dashboard requests."""
    from server import run_server
    port = int(os.getenv("PORT", 8080))
    log.info("Starting HTTP server...", port=port)
    run_server(port)


def main():
    """Main entry point - run both services."""
    log.info("Starting Singular Daily Worker")
    
    # Check required env vars
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    supabase_url = os.getenv("SUPABASE_URL")
    
    if not supabase_url:
        log.error("Missing SUPABASE_URL")
        return
    
    # Determine what to run
    run_bot = bool(telegram_token)
    run_http = True  # Always run HTTP for health checks
    
    if run_bot and run_http:
        # Run both: HTTP in background, bot in foreground
        http_thread = threading.Thread(target=run_http_server, daemon=True)
        http_thread.start()
        log.info("HTTP server started in background")
        
        # Run bot in main thread (it uses asyncio)
        run_telegram_bot()
    
    elif run_http:
        # Only HTTP server
        log.warning("No TELEGRAM_BOT_TOKEN - running HTTP server only")
        run_http_server()
    
    else:
        log.error("No services to run - check configuration")


if __name__ == "__main__":
    main()
