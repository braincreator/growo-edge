# Growo Edge SDK

**Клиентский клей для внедрений [платформы ИИ-сотрудников Growo](https://growoai.ru)**: интеграции amoCRM и Авито, загрузка базы знаний (RAG) и каркас вебхук-каналов — поверх HTTP API платформы.

[![CI](https://github.com/braincreator/growo-edge/actions/workflows/ci.yml/badge.svg)](https://github.com/braincreator/growo-edge/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)

## Что это

Это **передаваемые исходники для проектов под ключ**: форк этого репо отдаётся
клиенту или его подрядчику целиком. В форке живёт только «клей» — адаптеры
каналов, вебхуки, скрипты загрузки данных. Вся AI-логика (ответы, RAG, скоринг
лидов, промпты, базы знаний) работает на платформе Growo и в исходники клиента
не попадает.

| | Где живёт |
|---|---|
| Мозг: LLM, RAG, скоринг, синк в CRM | платформа Growo (`GROWO_API_BASE`) |
| Клей: вебхуки, кастомные правила, формы | этот SDK (у клиента) |

Через клиентскую коробку проходят только текст сообщения и готовый ответ:
никакой бизнес-логики, никаких данных на диске. Каналы, которые платформа
поддерживает нативно (виджет на сайт, amoCRM, Telegram/WhatsApp/VK/MAX), SDK
сознательно не дублирует — подробнее в [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Быстрый старт за 3 минуты

```bash
git clone https://github.com/braincreator/growo-edge.git
cd growo-edge
pip install -e .            # единственная зависимость — httpx
cp .env.example .env        # укажите GROWO_TENANT (слаг тенанта, выдаёт Growo)
```

Первый ответ ассистента:

```python
import asyncio
from growo_edge.growo import GrowoClient

async def main():
    g = GrowoClient(base="https://growoai.ru/platform", tenant="mytenant")
    r = await g.chat("Сколько стоит доставка?", visitor_id="demo-1", channel="api")
    print(r["response"])     # ответ, intent, lead_score, handoff...
    await g.aclose()

asyncio.run(main())
```

Для админ-операций (загрузка файлов в базу знаний, поиск, `/ask`) добавьте в
`.env` ключ `GROWO_API_KEY` — admin-токен тенанта, его выдаёт Growo при внедрении.

## Примеры использования

### Спящий ответ ассистента (SSE-стрим)

```python
async for chunk in g.chat_stream("Что по срокам?", visitor_id="demo-1"):
    print(chunk["text"], end="")   # чанки ответа по мере генерации
```

### База знаний (RAG): загрузка и ответ по документам

```python
# массовая загрузка файлов из консоли (txt/md/pdf/docx)
# python examples/kb_upload.py ./docs/*.pdf

await g.kb_import_text("Прайс-лист", "Текст документа...")       # публичный эндпоинт
r = await g.kb_upload_file("./price_2026.pdf")                   # админ (Bearer)
res = await g.kb_search("гарантия на фасады", top_k=5)           # векторный поиск
a = await g.kb_ask("Какая гарантия?")                            # RAG + LLM
print(a["answer"], a["sources"])
```

### Лид в amoCRM одной командой

Боевой паттерн sync_lead из продакшена Growo: контакт с дедупликацией →
сделка → примечание → задача.

```bash
python examples/amo_push_lead.py --name "Иван" --phone "+7999..." \
    --intent фасады --note "Хочет расчёт на 200 м²"
# → {'status': 'synced', 'deal_id': 77, 'contact_id': 42, 'deduped': False}
```

Или из кода:

```python
from growo_edge.amocrm.client import AmoCrmClient

amo = AmoCrmClient(subdomain="mycompany", access_token="eyJ...")
r = await amo.push_lead(name="Иван", phone="+7999...", intent="фасады",
                        note="Хочет расчёт на 200 м²")
```

### Авито-бот: вебхук → ассистент → ответ в чат

Приёмник на FastAPI (стратегия: дедуп по id → `GrowoClient.chat` с
`session_id = chat_id`, контекст переписки живёт на платформе → ответ в чат
Авито, токен обновляется автоматически):

```bash
pip install fastapi uvicorn
python examples/register_avito_webhook.py   # однократно: подписать PUBLIC_URL
python examples/avito_bot.py                # приёмник на :8080
```

## Состав

| Модуль | Что делает |
|---|---|
| `growo_edge.growo` | Клиент платформы Growo: чат/стрим, база знаний (импорт, загрузка, поиск, `/ask`) |
| `growo_edge.amocrm` | Клиент amoCRM API v4: сделки/контакты/задачи/вебхуки, сценарий `push_lead` |
| `growo_edge.avito` | Клиент Авито: OAuth2 с автообновлением токена, чаты messenger, отзывы, вебхуки |
| `growo_edge.channels` | Каркас приёма вебхуков: HMAC-проверка, дедупликация событий, парсинг сообщений |
| `growo_edge.config` | Конфигурация из `.env` — единственный источник кредов |
| `examples/` | amo→Growo синк, бот Авито, загрузка базы знаний, регистрация вебхука |

## Как это работает

Edge-реле: коробка у клиента, мозг — на платформе.

```
Авито ──webhook──► [сервер клиента: docker compose]
                      │ parse → dedup → кастомные правила
                      ▼
                GROWO_API_BASE/api/v1/chat   (X-Tenant-Slug)
                      │ ответ ассистента
                      ▼
                  Avito API ◄── ответ в чат
```

Возможны и другие топологии — чистый SaaS без SDK и полный on-premise
(`GROWO_API_BASE` указывает на локальную инсталляцию платформы, LLM через
ключи клиента): разбор с матрицей покрытия — в [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Платформа Growo

SDK — тонкий адаптер поверх платформы [Growo](https://growoai.ru) —
ИИ-сотрудников для бизнеса: ассистент с RAG по базе знаний, ML-скоринг лидов,
автосинк в amoCRM, нативные каналы (виджет на сайт, Telegram, WhatsApp, VK, MAX)
и админка с биллингом. Тенант, тариф, промпты и база знаний настраиваются на
платформе; поведение ассистента меняется без изменения кода внедрения.

Плейбук проекта под ключ на базе этого SDK — [docs/TURNKEY.md](docs/TURNKEY.md).

## Развёртывание у клиента

```bash
cp .env.example .env    # заполнить креды
docker compose up -d    # webhook-приёмник (FastAPI) на :8080
```

## Разработка

```bash
pip install -e ".[dev]"
pytest          # 7 тестов, сеть не нужна (httpx.MockTransport)
ruff check .    # style: pycodestyle + pyflakes + isort
```

## Лицензия

[Apache-2.0](LICENSE) — исходники можно использовать, модифицировать и
передавать клиенту/подрядчику в рамках внедрения.
