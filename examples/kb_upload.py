"""Загрузка документов в базу знаний Growo.

Usage: python examples/kb_upload.py ./docs/*.pdf
Текстовые файлы до 5К символов идут через публичный импорт (без admin
ключа), крупные/бинарные — через административный upload (нужен admin_token).
"""
import asyncio
import glob
import sys

from growo_edge.config import Config
from growo_edge.growo import GrowoClient


async def main():
    paths: list[str] = []
    for arg in sys.argv[1:]:
        paths.extend(glob.glob(arg))
    if not paths:
        sys.exit("нет файлов: python examples/kb_upload.py ./docs/*.pdf")

    cfg = Config()
    growo = GrowoClient(cfg.growo_api_base, cfg.growo_tenant, cfg.growo_api_key)
    for p in paths:
        try:
            if p.endswith((".txt", ".md")) and not cfg.growo_api_key:
                text = open(p, encoding="utf-8", errors="replace").read()
                r = await growo.kb_import_text(p.rsplit("/", 1)[-1], text[:5000])
            else:
                r = await growo.kb_upload_file(p)
            print(f"✓ {p}: {r}")
        except Exception as e:
            print(f"✗ {p}: {e}")
    await growo.aclose()


asyncio.run(main())
