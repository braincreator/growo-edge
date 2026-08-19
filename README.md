# Growo Edge SDK

Клиентский клей для внедрений Growo: интеграции amoCRM и Avito, загрузка
базы знаний (RAG), каркас канала. Это исходники, которые можно передавать
клиенту / подрядчику клиента — вся AI-логика (ответы, скоринг, базы знаний,
промпты) работает на платформе Growo по HTTP API и остаётся у вендора.

## Состав

| Модуль | Что делает |
|---|---|
| `growo_edge.growo` | Клиент платформы Growo: чат/ответы ассистента, база знаний |
| `growo_edge.amocrm` | Клиент amoCRM API v4: сделки/контакты/задачи/вебхуки, `push_lead` |
| `growo_edge.avito` | Клиент Авито: чаты messenger, отзывы, вебхук входящих |
| `growo_edge.channels` | Каркас приёма вебхуков канала → вопрос ассистенту → ответ |
| `examples/` | amo→Growo синк, бот Авито, загрузка базы знаний |

## Быстрый старт

```bash
pip install -e ".[dev]"
cp .env.example .env  # заполните креды
python examples/kb_upload.py ./docs
```

## Настройка

`.env`:

```
GROWO_API_BASE=https://growoai.ru/platform   # база платформы
GROWO_TENANT=alexprom                        # слаг тенанта
GROWO_API_KEY=...                            # ключ доступа (выдаёт Growo)
AMOCRM_SUBDOMAIN=mycompany
AMOCRM_TOKEN=eyJ...                          # длинный токен интеграции
AVITO_CLIENT_ID=...
AVITO_CLIENT_SECRET=...
AVITO_USER_ID=123456789
```

## Развёртывание у клиента

```bash
docker compose up -d   # webhook-приёмник (FastAPI) на :8080
```

## Лицензия

Apache-2.0 — можно использовать, модифицировать и передавать
в рамках внедрения (см. LICENSE).
