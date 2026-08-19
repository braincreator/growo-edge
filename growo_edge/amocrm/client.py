"""amoCRM API v4 client — standalone, no platform dependencies.

Auth: long-lived access token (integration token). Получите в amoCRM:
Настройки → Интеграции → ваша интеграция → «Получить токен для API».
Токен живёт ~год, обновляется там же (amoCRM не ратацирует его автоматически
для private-интеграций).

Проверено в бою: паттерн contact-dedup → deal → note → task используется
в продакшене Growo (sync_lead), здесь — очищенная версия для внедрений.
"""
from __future__ import annotations

import httpx


class AmoCrmError(RuntimeError):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        super().__init__(f"amoCRM HTTP {status_code}: {body[:300]}")


class AmoCrmClient:
    """Минимальный, но полный клиент amoCRM API v4.

    >>> amo = AmoCrmClient(subdomain="mycompany", access_token="eyJ...")
    >>> await amo.test_connection()
    """

    def __init__(self, subdomain: str, access_token: str, timeout: float = 15.0):
        self._base = f"https://{subdomain}.amocrm.ru"
        self._token = access_token
        self._http = httpx.AsyncClient(
            base_url=self._base, timeout=timeout,
            headers={"Authorization": f"Bearer {access_token}",
                     "User-Agent": "GrowoEdge/1.0",
                     "Content-Type": "application/json"})

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── низкий уровень ─────────────────────────────────────────────

    async def _request(self, method: str, path: str, *,
                       params: dict | None = None, json=None) -> dict | list:
        resp = await self._http.request(method, path, params=params, json=json)
        if resp.status_code >= 400:
            raise AmoCrmError(resp.status_code, resp.text)
        if not resp.content:
            return {}
        return resp.json()

    @staticmethod
    def _embedded(resp: dict | list, key: str) -> list[dict]:
        """amoCRM отдаёт created-объекты в _embedded."""
        if isinstance(resp, dict):
            return resp.get("_embedded", {}).get(key, [])
        return []

    # ── account / пайплайны ────────────────────────────────────────

    async def test_connection(self) -> dict:
        return await self._request("GET", "/api/v4/account")

    async def list_pipelines(self) -> list[dict]:
        resp = await self._request("GET", "/api/v4/leads/pipelines")
        return self._embedded(resp, "pipelines")

    async def resolve_default_stage(self) -> tuple[int | None, int | None]:
        """(pipeline_id, status_id) первой воронки и её первого этапа."""
        pipes = await self.list_pipelines()
        if not pipes:
            return None, None
        p = pipes[0]
        statuses = p.get("_embedded", {}).get("statuses", [])
        stage = next((s for s in statuses if s.get("sort") == 10), None) \
            or (statuses[0] if statuses else None)
        return p.get("id"), (stage or {}).get("id")

    # ── сделки ─────────────────────────────────────────────────────

    async def list_leads(self, limit: int = 50, query: str = "") -> list[dict]:
        params = {"limit": limit, "with": "contacts"}
        if query:
            params["query"] = query
        resp = await self._request("GET", "/api/v4/leads", params=params)
        return self._embedded(resp, "leads")

    async def get_lead(self, lead_id: int) -> dict:
        return await self._request("GET", f"/api/v4/leads/{lead_id}")

    async def create_lead(self, deal: dict) -> int:
        """Создать сделку (полный dict API v4: name, pipeline_id, status_id,
        _embedded.contacts/tags, custom_fields_values...). Возвращает id."""
        resp = await self._request("POST", "/api/v4/leads", json=[deal])
        leads = self._embedded(resp, "leads")
        if not leads:
            raise AmoCrmError(200, f"no deal_id in response: {resp}")
        return leads[0]["id"]

    async def update_lead(self, lead_id: int, **fields) -> None:
        await self._request("PATCH", "/api/v4/leads",
                            json=[{"id": lead_id, **fields}])

    # ── контакты ───────────────────────────────────────────────────

    async def find_contact(self, phone: str = "", email: str = "") -> int | None:
        for q in (phone, email):
            if not q:
                continue
            resp = await self._request(
                "GET", "/api/v4/contacts", params={"query": q, "limit": 1})
            contacts = self._embedded(resp, "contacts")
            if contacts:
                return contacts[0]["id"]
        return None

    async def create_contact(self, name: str, phone: str = "",
                             email: str = "") -> int | None:
        contact: dict = {"name": name or "Контакт без имени"}
        fields = []
        if phone:
            fields.append({"field_code": "PHONE",
                           "values": [{"value": phone, "enum_code": "WORK"}]})
        if email:
            fields.append({"field_code": "EMAIL",
                           "values": [{"value": email, "enum_code": "WORK"}]})
        if fields:
            contact["custom_fields_values"] = fields
        resp = await self._request("POST", "/api/v4/contacts", json=[contact])
        contacts = self._embedded(resp, "contacts")
        return contacts[0]["id"] if contacts else None

    # ── примечания и задачи ────────────────────────────────────────

    async def add_note(self, entity_type: str, entity_id: int, text: str) -> None:
        await self._request(
            "POST", f"/api/v4/{entity_type}/{entity_id}/notes",
            json=[{"note_type": "common", "params": {"text": text}}])

    async def create_task(self, entity_id: int, text: str,
                          entity_type: str = "leads",
                          responsible_user_id: int = 0,
                          delay_hours: int = 24) -> None:
        import time
        task = {
            "text": text, "entity_id": entity_id, "entity_type": entity_type,
            "complete_till": int(time.time()) + delay_hours * 3600,
            "task_type_id": 1,  # звонок/связаться
        }
        if responsible_user_id:
            task["responsible_user_id"] = responsible_user_id
        await self._request("POST", "/api/v4/tasks", json=[task])

    # ── вебхуки ────────────────────────────────────────────────────

    async def subscribe_webhook(self, destination_url: str,
                                events: list[str] | None = None) -> dict:
        """Зарегистрировать URL приёма событий amoCRM (сделки/контакты)."""
        settings = {
            "destination": destination_url,
            "settings": events or [
                "add_lead", "update_lead", "status_lead",
                "add_contact", "update_contact",
            ],
        }
        return await self._request("POST", "/api/v4/webhooks",
                                   json=[settings])

    async def unsubscribe_webhook(self, destination_url: str) -> None:
        await self._request("POST", "/api/v4/webhooks/unsubscribe",
                            json=[{"destination": destination_url}])

    # ── высокоуровневый сценарий: пуш лида ─────────────────────────

    async def push_lead(self, *, name: str, phone: str = "", email: str = "",
                        intent: str = "", note: str = "",
                        auto_task: bool = True,
                        task_text: str = "Связаться с клиентом",
                        tags: list[str] | None = None) -> dict:
        """Контакт (с дедупликацией) → сделка → примечание → задача.

        Боевой паттерн: тот же порядок операций, что в проде Growo.
        Возвращает {deal_id, contact_id, deduped}.
        """
        if not any([phone, email]):
            return {"status": "skipped", "reason": "no_contact_data"}

        contact_id = await self.find_contact(phone=phone, email=email)
        deduped = contact_id is not None
        if not contact_id:
            contact_id = await self.create_contact(name, phone, email)

        pipeline_id, status_id = await self.resolve_default_stage()
        deal: dict = {"name": f"{name or 'Лид'}{f' · {intent}' if intent else ''}"}
        if pipeline_id:
            deal["pipeline_id"] = pipeline_id
        if status_id:
            deal["status_id"] = status_id
        if contact_id:
            deal["_embedded"] = {"contacts": [{"id": contact_id}]}
        all_tags = list(dict.fromkeys(list(tags or []) + ["GrowoAI"]
                                      + ([intent] if intent else [])))
        deal.setdefault("_embedded", {})["tags"] = [{"name": t} for t in all_tags]

        deal_id = await self.create_lead(deal)
        if note:
            await self.add_note("leads", deal_id, note)
        if auto_task:
            await self.create_task(deal_id, task_text)

        return {"status": "synced", "deal_id": deal_id,
                "contact_id": contact_id, "deduped": deduped}
