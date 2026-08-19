"""Однократная подписка вебхука Авито на этот приёмник.

Usage: PUBLIC_URL=https://bots.client.ru python examples/register_avito_webhook.py
"""
import asyncio
import os

from growo_edge.avito.client import AvitoClient
from growo_edge.config import Config


async def main():
    cfg = Config()
    avito = AvitoClient(cfg.avito_client_id, cfg.avito_client_secret,
                        cfg.avito_user_id)
    public = (os.getenv("PUBLIC_URL") or "http://localhost:8080").rstrip("/")
    r = await avito.subscribe_webhook(f"{public}/webhook/avito")
    print("subscribed:", r)
    await avito.aclose()


asyncio.run(main())
