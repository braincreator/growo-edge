"""Клиент платформы Growo — чат, база знаний, синк в amoCRM.

Аутентификация: X-Tenant-Slug для публичных v4-эндпоинтов (чат, текстовый
импорт KB) и Bearer <admin_token> для административных (загрузка файлов,
поиск /ask, коннекторы). admin_token выдаёт Growo при внедрении.
"""
from __future__ import annotations

import httpx


class GrowoError(RuntimeError):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        super().__init__(f"Growo HTTP {status_code}: {body[:300]}")


class GrowoClient:
    """Клиент платформы.

    >>> g = GrowoClient(base="https://growoai.ru/platform",
    ...                 tenant="alexprom", api_key="<admin_token>")
    >>> r = await g.chat("Сколько стоит доставка?", visitor_id="avito-123",
    ...                  channel="api")
    >>> print(r["response"])
    """

    def __init__(self, base: str, tenant: str, api_key: str = "",
                 timeout: float = 60.0):
        self._base = base.rstrip("/")
        self._tenant = tenant
        self._api_key = api_key
        self._http = httpx.AsyncClient(
            base_url=self._base, timeout=timeout,
            headers={"X-Tenant-Slug": tenant, "User-Agent": "GrowoEdge/1.0"})

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, *, admin=False,
                       params=None, json=None, data=None, files=None) -> httpx.Response:
        headers = {}
        if admin:
            if not self._api_key:
                raise GrowoError(0, "api_key (admin_token) не задан")
            headers["Authorization"] = f"Bearer {self._api_key}"
        resp = await self._http.request(method, path, headers=headers,
                                        params=params, json=json,
                                        data=data, files=files)
        if resp.status_code >= 400:
            raise GrowoError(resp.status_code, resp.text)
        return resp

    # ── чат / ассистент ────────────────────────────────────────────

    async def chat(self, message: str, *, visitor_id: str = "",
                   channel: str = "api", session_id: str = "") -> dict:
        """Ответ ассистента. Возвращает полный ответ платформы:
        {response, conversation_id, intent, lead_score, handoff, tokens, ...}."""
        resp = await self._request("POST", "/api/v1/chat", json={
            "message": message, "visitor_id": visitor_id,
            "channel": channel, "session_id": session_id,
        })
        return resp.json()

    async def chat_stream(self, message: str, *, visitor_id: str = "",
                          channel: str = "api", session_id: str = ""):
        """SSE-стрим чанков ответа: yield dict(text=..., type=...)."""
        async with self._http.stream(
            "POST", "/api/v1/chat/stream",
            headers={"X-Tenant-Slug": self._tenant},
            json={"message": message, "visitor_id": visitor_id,
                  "channel": channel, "session_id": session_id},
        ) as resp:
            if resp.status_code >= 400:
                raise GrowoError(resp.status_code, (await resp.aread()).decode())
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    import json as _json
                    try:
                        yield _json.loads(line[6:])
                    except ValueError:
                        pass

    # ── база знаний (RAG) ──────────────────────────────────────────

    async def kb_import_text(self, title: str, content: str) -> dict:
        """Текстовый документ → база знаний (публичный v4-эндпоинт)."""
        resp = await self._request("POST", "/api/v1/knowledge/import",
                                   json={"title": title, "content": content})
        return resp.json()

    async def kb_upload_file(self, path: str, collection: str = "default") -> dict:
        """Файл (txt/md/pdf/docx) → база знаний (админ, Bearer)."""
        with open(path, "rb") as f:
            resp = await self._request(
                "POST", "/platform/admin/api/v1/knowledge/documents/import",
                admin=True, data={"collection": collection},
                files={"file": (path.rsplit("/", 1)[-1], f)})
        return resp.json()

    async def kb_search(self, query: str, top_k: int = 5) -> list[dict]:
        """Векторный поиск по базе знаний (админ, Bearer)."""
        resp = await self._request(
            "POST", "/platform/admin/api/v1/knowledge/search", admin=True,
            json={"query": query, "top_k": top_k})
        return resp.json().get("results", [])

    async def kb_ask(self, query: str, top_k: int = 5) -> dict:
        """RAG + LLM: ответ по документам базы (админ, Bearer).
        Возвращает {answer, sources[], model}."""
        resp = await self._request(
            "POST", "/platform/admin/api/v1/knowledge/ask", admin=True,
            json={"query": query, "top_k": top_k})
        return resp.json()
