"""
Keernel Email Digest V19

Sends daily email digest with:
- Link to the podcast
- Written summary of 3 segments
- Direct link to listen

Environment Variables Required:
- RESEND_API_KEY: Resend API key
- APP_URL: Base URL for the app (default: https://singular.daily)
- RESEND_FROM_EMAIL: From email address (default: podcast@keernel.ai)
"""

import os
from datetime import datetime, date, timezone
from typing import Optional

import structlog
from dotenv import load_dotenv

from db import supabase

load_dotenv()
log = structlog.get_logger()

# ============================================
# CONFIGURATION
# ============================================

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
APP_URL = os.getenv("APP_URL", "https://singular.daily")
FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "Keernel <podcast@keernel.ai>")

# Initialize Resend client
resend = None
if RESEND_API_KEY:
    try:
        import resend as resend_lib
        resend_lib.api_key = RESEND_API_KEY
        resend = resend_lib
        log.info("✅ Resend email client initialized")
    except ImportError:
        log.warning("⚠️ Resend SDK not installed")
else:
    log.warning("⚠️ RESEND_API_KEY not set - email digest disabled")


# ============================================
# EMAIL TEMPLATE
# ============================================

def generate_email_html(
    first_name: str,
    episode_title: str,
    episode_summary: str,
    listen_url: str,
    segments: list[dict]
) -> str:
    """Generate HTML email content for digest."""

    # Generate segments HTML
    segments_html = ""
    for i, segment in enumerate(segments[:3], 1):
        topic_name = segment.get("topic_name", segment.get("topic_slug", ""))
        headline = segment.get("headline", segment.get("title", ""))
        summary = segment.get("summary", "")[:200]
        if len(segment.get("summary", "")) > 200:
            summary += "..."

        segments_html += f"""
        <div style="margin-bottom: 16px; padding: 16px; background: #f8f9fa; border-radius: 8px;">
            <div style="font-size: 12px; color: #00F0FF; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px;">
                {topic_name}
            </div>
            <div style="font-weight: 600; font-size: 16px; margin-bottom: 8px; color: #1a1a1a;">
                {headline}
            </div>
            <div style="font-size: 14px; color: #666; line-height: 1.5;">
                {summary}
            </div>
        </div>
        """

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background: #f5f5f5;">
    <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
        <!-- Header -->
        <div style="text-align: center; margin-bottom: 32px;">
            <div style="display: inline-block; width: 48px; height: 48px; background: linear-gradient(135deg, rgba(0, 240, 255, 0.2), rgba(0, 122, 255, 0.15)); border-radius: 12px; line-height: 48px; margin-bottom: 16px;">
                <span style="font-size: 24px;">🎙️</span>
            </div>
            <h1 style="margin: 0; font-size: 24px; font-weight: 600; color: #1a1a1a;">
                Keernel
            </h1>
        </div>

        <!-- Main Content -->
        <div style="background: white; border-radius: 16px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
            <p style="font-size: 18px; color: #1a1a1a; margin: 0 0 8px 0;">
                Bonjour {first_name} !
            </p>
            <p style="font-size: 16px; color: #666; margin: 0 0 24px 0;">
                Votre podcast quotidien est prêt.
            </p>

            <!-- Episode Title -->
            <h2 style="font-size: 20px; font-weight: 600; color: #1a1a1a; margin: 0 0 16px 0;">
                {episode_title}
            </h2>

            <!-- CTA Button -->
            <a href="{listen_url}" style="display: block; text-align: center; padding: 16px 32px; background: #1a1a1a; color: white; text-decoration: none; border-radius: 12px; font-weight: 600; font-size: 16px; margin-bottom: 32px;">
                🎧 Écouter maintenant
            </a>

            <!-- Segments Preview -->
            <div style="margin-top: 24px;">
                <h3 style="font-size: 14px; text-transform: uppercase; letter-spacing: 1px; color: #999; margin: 0 0 16px 0;">
                    Au programme
                </h3>
                {segments_html}
            </div>
        </div>

        <!-- Footer -->
        <div style="text-align: center; margin-top: 24px; padding: 0 20px;">
            <p style="font-size: 12px; color: #999; margin: 0 0 8px 0;">
                Vous recevez cet email car vous êtes abonné aux digests quotidiens.
            </p>
            <p style="font-size: 12px; color: #999; margin: 0;">
                <a href="{APP_URL}/settings" style="color: #00F0FF; text-decoration: none;">
                    Modifier vos préférences
                </a>
            </p>
        </div>
    </div>
</body>
</html>
"""


def generate_email_text(
    first_name: str,
    episode_title: str,
    episode_summary: str,
    listen_url: str,
    segments: list[dict]
) -> str:
    """Generate plain text email content for digest."""

    segments_text = ""
    for i, segment in enumerate(segments[:3], 1):
        topic_name = segment.get("topic_name", segment.get("topic_slug", ""))
        headline = segment.get("headline", segment.get("title", ""))
        summary = segment.get("summary", "")[:200]

        segments_text += f"""
{i}. [{topic_name}] {headline}
{summary}
"""

    return f"""Bonjour {first_name} !

Votre podcast quotidien est prêt.

📰 {episode_title}

🎧 Écouter: {listen_url}

---
AU PROGRAMME
{segments_text}
---

Vous recevez cet email car vous êtes abonné aux digests quotidiens.
Modifier vos préférences: {APP_URL}/settings
"""


# ============================================
# SEND EMAIL
# ============================================

def send_digest_email(
    to_email: str,
    first_name: str,
    episode_title: str,
    episode_summary: str,
    listen_url: str,
    segments: list[dict]
) -> bool:
    """Send digest email to user."""

    if not resend:
        log.warning("📧 Email not sent - Resend not configured", email=to_email[:20])
        return False

    try:
        html_content = generate_email_html(
            first_name=first_name,
            episode_title=episode_title,
            episode_summary=episode_summary,
            listen_url=listen_url,
            segments=segments
        )

        text_content = generate_email_text(
            first_name=first_name,
            episode_title=episode_title,
            episode_summary=episode_summary,
            listen_url=listen_url,
            segments=segments
        )

        result = resend.Emails.send({
            "from": FROM_EMAIL,
            "to": [to_email],
            "subject": f"🎙️ {episode_title}",
            "html": html_content,
            "text": text_content,
        })

        log.info("📧 Digest email sent", email=to_email[:20], id=result.get("id"))
        return True

    except Exception as e:
        log.error("📧 Failed to send digest email", email=to_email[:20], error=str(e))
        return False


# ============================================
# CRON: SEND ALL PENDING DIGESTS
# ============================================

def send_pending_digests(target_date: date = None) -> dict:
    """
    Send email digests for all users with:
    - email_digest_enabled = true
    - Episode created today (or target_date)
    - Email not yet sent for this episode

    Returns:
        dict with sent, skipped, failed counts
    """
    target_date = target_date or date.today()
    stats = {"sent": 0, "skipped": 0, "failed": 0, "users": []}

    log.info("📧 Starting digest send job", date=str(target_date))

    try:
        # Get users with digest enabled
        users_result = supabase.table("users") \
            .select("id, email, first_name, email_digest_enabled") \
            .eq("email_digest_enabled", True) \
            .execute()

        if not users_result.data:
            log.info("📧 No users with digest enabled")
            return stats

        log.info(f"📧 Found {len(users_result.data)} users with digest enabled")

        for user in users_result.data:
            user_id = user["id"]
            email = user.get("email")
            first_name = user.get("first_name", "")

            if not email:
                log.warning("📧 User has no email", user_id=user_id[:8])
                stats["skipped"] += 1
                continue

            # Get today's episode for this user
            episode_result = supabase.table("episodes") \
                .select("id, title, summary_text, audio_url, sources_data, digest_sent_at") \
                .eq("user_id", user_id) \
                .gte("created_at", f"{target_date}T00:00:00Z") \
                .lt("created_at", f"{target_date}T23:59:59Z") \
                .order("created_at", desc=True) \
                .limit(1) \
                .execute()

            if not episode_result.data:
                log.debug("📧 No episode today for user", user_id=user_id[:8])
                stats["skipped"] += 1
                continue

            episode = episode_result.data[0]

            # Check if already sent
            if episode.get("digest_sent_at"):
                log.debug("📧 Digest already sent", user_id=user_id[:8])
                stats["skipped"] += 1
                continue

            # Get segments from sources_data
            segments = episode.get("sources_data", []) or []

            # Build listen URL
            listen_url = f"{APP_URL}/dashboard"

            # Send email
            success = send_digest_email(
                to_email=email,
                first_name=first_name or "there",
                episode_title=episode.get("title", "Votre podcast du jour"),
                episode_summary=episode.get("summary_text", ""),
                listen_url=listen_url,
                segments=segments
            )

            if success:
                # Mark as sent
                supabase.table("episodes") \
                    .update({"digest_sent_at": datetime.now(timezone.utc).isoformat()}) \
                    .eq("id", episode["id"]) \
                    .execute()

                stats["sent"] += 1
                stats["users"].append(email[:20])
            else:
                stats["failed"] += 1

        log.info("📧 Digest job complete", **stats)
        return stats

    except Exception as e:
        log.error("📧 Digest job failed", error=str(e))
        raise


# ============================================
# CLI
# ============================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Keernel Email Digest")
    parser.add_argument("--send", action="store_true", help="Send pending digests")
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD)")
    parser.add_argument("--test", type=str, metavar="EMAIL", help="Send test email")

    args = parser.parse_args()

    if args.test:
        print(f"Sending test email to {args.test}...")
        success = send_digest_email(
            to_email=args.test,
            first_name="Test User",
            episode_title="Votre briefing du 8 janvier",
            episode_summary="Test summary",
            listen_url=f"{APP_URL}/dashboard",
            segments=[
                {"topic_name": "IA", "headline": "GPT-5 annoncé", "summary": "OpenAI annonce la prochaine génération..."},
                {"topic_name": "Crypto", "headline": "Bitcoin à 100k", "summary": "Le Bitcoin atteint un nouveau record..."},
                {"topic_name": "Space", "headline": "SpaceX Starship", "summary": "Nouveau lancement réussi..."},
            ]
        )
        print("✅ Sent" if success else "❌ Failed")

    elif args.send:
        target = None
        if args.date:
            target = date.fromisoformat(args.date)

        stats = send_pending_digests(target_date=target)
        print(f"📧 Results: {stats['sent']} sent, {stats['skipped']} skipped, {stats['failed']} failed")

    else:
        parser.print_help()
