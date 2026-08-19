"""Avito API client — standalone, no platform dependencies.

Auth: OAuth2 client_credentials (client_id + client_secret → access_token,
токен короткоживущий ~24ч, обновляется повторным запросом — refresh_token
у Авито НЕТ).

Эндпоинты проверены на живом API (август 2026): странные версии v2/v1
в messenger-путях — так у Авито и есть, не «чинить».
"""
from __future__ import annotations

import httpx


class AvitoError(RuntimeError):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        super().__init__(f"Avito HTTP {status_code}: {body[:300]}")


class AvitoClient:
    """Клиент Авито: токен, товары, чаты messenger, отзывы.

    >>> av = AvitoClient(client_id="...", client_secret="...", user_id=123)
    >>> await av.get_token()
    >>> chats = await av.get_chats()
    """

    TOKEN_URL = "https://api.avito.ru/token"
    BASE = "https://api.avito.ru"

    def __init__(self, client_id: str, client_secret: str,
                 user_id: int | str, timeout: float = 15.0):
        self._client_id = client_id
        self._client_secret = client_secret
        self.user_id = str(user_id)
        self._token = ""
        self._http = httpx.AsyncClient(
            base_url=self.BASE, timeout=timeout,
            headers={"User-Agent": "GrowoEdge/1.0"})

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── auth ───────────────────────────────────────────────────────

    async def get_token(self) -> str:
        """client_credentials: новый токен по требованию (старый протух)."""
        resp = await self._http.post(
            self.TOKEN_URL,
            data={"grant_type": "client_credentials",
                  "client_id": self._client_id,
                  "client_secret": self._client_secret})
        if resp.status_code != 200:
            raise AvitoError(resp.status_code, resp.text)
        self._token = resp.json()["access_token"]
        self._http.headers["Authorization"] = f"Bearer {self._token}"
        return self._token

    async def _request(self, method: str, path: str, *, params=None,
                       json=None) -> dict | list:
        if not self._token:
            await self.get_token()
        resp = await self._http.request(method, path, params=params, json=json)
        if resp.status_code == 401:  # токен истёк — перевыпуск и ретрай
            await self.get_token()
            resp = await self._http.request(method, path, params=params, json=json)
        if resp.status_code >= 400:
            raise AvitoError(resp.status_code, resp.text)
        if not resp.content:
            return {}
        return resp.json()

    # ── messenger: чаты (проверено на живом API) ───────────────────

    async def get_chats(self, unread_only: bool = True) -> list[dict]:
        """GET /messenger/v2/accounts/{user_id}/chats — чаты продавца."""
        resp = await self._request(
            "GET", f"/messenger/v2/accounts/{self.user_id}/chats",
            params={"unread_only": str(unread_only).lower()})
        chats = []
        for chat in (resp.get("chats", []) if isinstance(resp, dict) else []):
            last_msg = chat.get("last_message") or {}
            ctx_val = (chat.get("context") or {}).get("value") or {}
            buyer = next((u for u in chat.get("users") or []
                          if str(u.get("id")) != self.user_id), {})
            chats.append({
                "id": chat.get("id", ""),
                "item_id": str(ctx_val.get("id", "")),
                "item_title": ctx_val.get("title", ""),
                "item_url": ctx_val.get("url", ""),
                "buyer_id": str(buyer.get("id", "")),
                "buyer_name": buyer.get("name", ""),
                "last_message": (last_msg.get("content") or {}).get("text", ""),
                "updated": chat.get("updated", 0),
            })
        return chats

    async def get_chat_messages(self, chat_id: str) -> list[dict]:
        """GET /messenger/v2/.../messages — сообщения чата."""
        resp = await self._request(
            "GET",
            f"/messenger/v2/accounts/{self.user_id}/chats/{chat_id}/messages")
        return [{
            "id": m.get("id", ""),
            "author_id": m.get("author_id", ""),
            "is_mine": str(m.get("author_id")) == self.user_id,
            "text": (m.get("content") or {}).get("text", ""),
            "created": m.get("created", ""),
            "read": m.get("is_read", False),
        } for m in (resp if isinstance(resp, list) else [])]

    async def send_chat_message(self, chat_id: str, text: str) -> str:
        """POST /messenger/v1/.../messages — body ВЛОЖЕННЫЙ:
        {"message": {"text": ...}}, не плоский. Возвращает message_id."""
        resp = await self._request(
            "POST",
            f"/messenger/v1/accounts/{self.user_id}/chats/{chat_id}/messages",
            json={"message": {"text": text}})
        return resp.get("id", "") if isinstance(resp, dict) else ""

    # ── отзывы ─────────────────────────────────────────────────────

    async def get_reviews(self, limit: int = 50) -> list[dict]:
        resp = await self._request(
            "GET", "/ratings/v1/reviews", params={"per_page": min(limit, 100)})
        return [{
            "id": str(r.get("id", "")),
            "author": r.get("author_name", ""),
            "rating": r.get("rating", 0),
            "text": r.get("text", ""),
            "answered": r.get("is_answered", False),
        } for r in (resp.get("reviews", []) if isinstance(resp, dict) else [])]

    async def answer_review(self, review_id: str, text: str) -> None:
        await self._request("POST", f"/ratings/v1/reviews/{review_id}/answer",
                            params={"text": text})

    # ── вебхук входящих сообщений ──────────────────────────────────

    async def subscribe_webhook(self, url: str) -> dict:
        """Зарегистрировать URL приёма событий messenger.
        Формат событий см. examples/avito_bot.py (verify + message)."""
        return await self._request("POST", "/messenger/v3/webhook",
                                   json={"url": url})
