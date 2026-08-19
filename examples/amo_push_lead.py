"""Пуш лида в amoCRM из любой формы/скрипта (боевой паттерн Growo sync_lead:
контакт с дедупликацией → сделка → примечание → задача).

Usage: python examples/amo_push_lead.py --name "Иван" --phone "+7..." \
           --intent фасады --note "Хочет расчёт на 200 м²"
"""
import argparse
import asyncio

from growo_edge.amocrm.client import AmoCrmClient
from growo_edge.config import Config


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="")
    ap.add_argument("--phone", default="")
    ap.add_argument("--email", default="")
    ap.add_argument("--intent", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--no-task", action="store_true")
    a = ap.parse_args()

    cfg = Config()
    amo = AmoCrmClient(cfg.amocrm_subdomain, cfg.amocrm_token)
    r = await amo.push_lead(
        name=a.name, phone=a.phone, email=a.email,
        intent=a.intent, note=a.note, auto_task=not a.no_task)
    print(r)
    await amo.aclose()


asyncio.run(main())
