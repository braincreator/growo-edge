"""Конфигурация из окружения (.env) — единственный источник кредов."""
from __future__ import annotations

import os


class Config:
    def __init__(self, env: dict | None = None):
        e = env if env is not None else dict(os.environ)

        def g(key: str, default: str = "") -> str:
            return e.get(key, default).strip()

        self.growo_api_base = g("GROWO_API_BASE", "https://growoai.ru/platform").rstrip("/")
        self.growo_tenant = g("GROWO_TENANT")
        self.growo_api_key = g("GROWO_API_KEY")

        self.amocrm_subdomain = g("AMOCRM_SUBDOMAIN")
        self.amocrm_token = g("AMOCRM_TOKEN")

        self.avito_client_id = g("AVITO_CLIENT_ID")
        self.avito_client_secret = g("AVITO_CLIENT_SECRET")
        self.avito_user_id = g("AVITO_USER_ID")

        self.webhook_port = int(g("WEBHOOK_PORT", "8080") or 8080)
        self.webhook_hmac_secret = g("WEBHOOK_HMAC_SECRET")
