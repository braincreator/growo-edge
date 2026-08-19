"""Каркас канала: вебхук внешней платформы → вопрос ассистенту Growo → ответ.

Приёмник (FastAPI) разворачивается у клиента (docker compose up). Порядок
обработки — боевой паттерн Growo:
  1. проверка подписи (если платформа её шлёт);
  2. дедупликация по id события (in-memory LRU);
  3. текст сообщения → GrowoClient.chat (session_id = внешний chat_id —
     ассистент держит контекст диалога);
  4. ответ отправляется обратно в канал (код клиента).

Пример полного цикла — examples/avito_bot.py.
"""
from __future__ import annotations

import hashlib
import hmac
from collections import OrderedDict


class Dedup:
    """In-memory дедупликация id событий (webhooks приходят с ретраями)."""

    def __init__(self, capacity: int = 2048):
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._capacity = capacity

    def seen(self, key: str) -> bool:
        if key in self._seen:
            return True
        self._seen[key] = None
        if len(self._seen) > self._capacity:
            self._seen.popitem(last=False)
        return False


def verify_hmac_sha256(secret: str, body: bytes, header: str) -> bool:
    """X-Hub-Signature-256: sha256=<hex> (Meta-стиль, его шлют WhatsApp/другие)."""
    expected = "sha256=" + hmac.new(secret.encode(), body,
                                    hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header or "")


def extract_text(payload: dict) -> tuple[str, str]:
    """(chat_id, text) из вебхука Avito messenger; None-текст = не сообщение."""
    if payload.get("event_type") not in ("message", "chat_started"):
        return "", ""
    p = payload.get("payload") or {}
    msg = (p.get("message") or {})
    text = ((msg.get("content") or {}).get("text") or "").strip()
    return str(p.get("chat_id") or ""), text
