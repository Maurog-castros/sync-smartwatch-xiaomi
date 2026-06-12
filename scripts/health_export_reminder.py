from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo


DEFAULT_MESSAGE = (
    "Recordatorio salud: exporta Apple Health en el iPhone, enviate el ZIP "
    "(exportar.zip) por WhatsApp a tu chat personal. El servidor lo descargara "
    "automaticamente a las 19:00."
)


def send_ntfy(message: str, topic: str, server: str) -> None:
    request = urllib.request.Request(
        f"{server.rstrip('/')}/{urllib.parse.quote(topic)}",
        data=message.encode("utf-8"),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20):
        return


def send_telegram(message: str, bot_token: str, chat_id: str) -> None:
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=payload,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20):
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Send Apple Health export reminder.")
    parser.add_argument("--timezone", default=os.environ.get("HEALTH_BRIDGE_TIMEZONE", "America/Santiago"))
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    parser.add_argument("--ntfy-topic", default=os.environ.get("HEALTH_EXPORT_NTFY_TOPIC"))
    parser.add_argument("--ntfy-server", default=os.environ.get("HEALTH_EXPORT_NTFY_SERVER", "https://ntfy.sh"))
    parser.add_argument("--telegram-bot-token", default=os.environ.get("HEALTH_EXPORT_TELEGRAM_BOT_TOKEN"))
    parser.add_argument("--telegram-chat-id", default=os.environ.get("HEALTH_EXPORT_TELEGRAM_CHAT_ID"))
    args = parser.parse_args()

    now = datetime.now(ZoneInfo(args.timezone))
    message = f"{args.message}\n\nHora local: {now.strftime('%Y-%m-%d %H:%M')}"
    channels: list[str] = []

    if args.ntfy_topic:
        send_ntfy(message, args.ntfy_topic, args.ntfy_server)
        channels.append(f"ntfy:{args.ntfy_topic}")

    if args.telegram_bot_token and args.telegram_chat_id:
        send_telegram(message, args.telegram_bot_token, args.telegram_chat_id)
        channels.append(f"telegram:{args.telegram_chat_id}")

    if not channels:
        print(message, file=sys.stderr)
        print(
            json.dumps(
                {
                    "sent": False,
                    "reason": "no_channels_configured",
                    "hint": (
                        "Configura HEALTH_EXPORT_TELEGRAM_BOT_TOKEN y "
                        "HEALTH_EXPORT_TELEGRAM_CHAT_ID o HEALTH_EXPORT_NTFY_TOPIC"
                    ),
                },
                ensure_ascii=True,
                indent=2,
            )
        )
        return

    print(
        json.dumps(
            {
                "sent": True,
                "channels": channels,
                "timezone": args.timezone,
                "message_preview": message[:160],
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
