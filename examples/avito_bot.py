"""Авито-бот на Growo: вебхук → ассистент → ответ в чат Авито.

Запуск: python examples/avito_bot.py (порт из WEBHOOK_PORT, default 8080).
Перед стартом: python examples/register_avito_webhook.py — подписать URL
на события Авито (однократно).
"""
import asyncio
import os

from fastapi import FastAPI, Request

from growo_edge.avito.client import AvitoClient
from growo_edge.channels.webhook import Dedup, extract_text
from growo_edge.config import Config
from growo_edge.growo import GrowoClient

cfg = Config()
avito = AvitoClient(cfg.avito_client_id, cfg.avito_client_secret,
                    cfg.avito_user_id)
growo = GrowoClient(cfg.growo_api_base, cfg.growo_tenant, cfg.growo_api_key)
dedup = Dedup()
app = FastAPI(title="Growo Edge — Avito bot")


@app.get("/webhook/avito")
async def verify():
    """Проверка URL вебхука Авито (GET с empty 200)."""
    return {"status": "ok"}


@app.post("/webhook/avito")
async def avito_webhook(req: Request):
    payload = await req.json()
    chat_id, text = extract_text(payload)
    msg_id = str(((payload.get("payload") or {}).get("message") or {}).get("id") or "")
    if not text or dedup.seen(msg_id or chat_id + ":" + text[:32]):
        return {"status": "ignored"}

    asyncio.create_task(reply(chat_id, text))
    return {"status": "ok"}


async def reply(chat_id: str, text: str):
    """Боевой порядок: ассистент Growo (session = chat_id — контекст живёт)
    → ответ в Авито."""
    try:
        r = await growo.chat(text, visitor_id=f"avito-{chat_id}",
                             channel="avito", session_id=f"avito-{chat_id}")
        answer = (r.get("response") or "").strip()
        if answer and not r.get("degraded"):
            await avito.send_chat_message(chat_id, answer[:4000])
    except Exception as e:  # канал не должен падать от одного диалога
        print(f"reply failed chat={chat_id}: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=cfg.webhook_port)
