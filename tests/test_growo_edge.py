"""SDK-тесты: клиенты не ходят в сеть — httpx.MockTransport."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
import pytest

from growo_edge.avito.client import AvitoClient
from growo_edge.amocrm.client import AmoCrmClient
from growo_edge.channels.webhook import Dedup, extract_text, verify_hmac_sha256
from growo_edge.growo import GrowoClient


def mock(handler):
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://x.test")
    return client


class TestAvitoClient:

    @pytest.mark.asyncio
    async def test_send_message_nested_body(self):
        seen = {}

        def h(request):
            seen["url"] = str(request.url)
            seen["body"] = request.read().decode()
            return httpx.Response(200, json={"id": "m-1"})

        av = AvitoClient("cid", "csec", 42)
        av._token = "tok"
        av._http = httpx.AsyncClient(
            transport=httpx.MockTransport(h), base_url=AvitoClient.BASE,
            headers={"Authorization": "Bearer tok"})
        mid = await av.send_chat_message("c1", "привет")
        assert mid == "m-1"
        assert "/messenger/v1/accounts/42/chats/c1/messages" in seen["url"]
        assert '"message":{"text":"привет"}' in seen["body"].replace(" ", "")


class TestAmoPushLead:

    @pytest.mark.asyncio
    async def test_push_lead_flow(self):
        calls = []

        def h(request):
            calls.append((request.method, str(request.url)))
            if request.url.path == "/api/v4/leads/pipelines":
                return httpx.Response(200, json={"_embedded": {"pipelines": [
                    {"id": 1, "_embedded": {"statuses": [{"id": 10, "sort": 10}]}}]}})
            if request.url.path == "/api/v4/contacts":
                return httpx.Response(200, json={"_embedded": {"contacts": []}})
            if request.url.path == "/api/v4/leads" and request.method == "POST":
                return httpx.Response(200, json={"_embedded": {"leads": [{"id": 77}]}})
            return httpx.Response(200, json={})

        amo = AmoCrmClient("sub", "tok")
        amo._http = httpx.AsyncClient(transport=httpx.MockTransport(h),
                                      base_url="https://sub.amocrm.ru",
                                      headers={"Authorization": "Bearer tok"})
        r = await amo.push_lead(name="Иван", phone="+7999",
                                intent="фасады", note="тест")
        assert r["deal_id"] == 77 and r["deduped"] is False
        paths = [c[1].split("amocrm.ru")[1] for c in calls]
        assert "/api/v4/contacts" in paths          # дедуп-поиск
        assert "/api/v4/leads" in paths             # сделка
        assert any("/notes" in p for p in paths)    # примечание


class TestChannelSkeleton:

    def test_dedup(self):
        d = Dedup(2)
        assert not d.seen("a") and d.seen("a")
        d.seen("b"); d.seen("c")  # вытесняет a
        assert not d.seen("a")

    def test_extract_text(self):
        cid, text = extract_text({
            "event_type": "message",
            "payload": {"chat_id": "ch-1",
                        "message": {"id": "m9", "content": {"text": "сколько стоит?"}}}})
        assert cid == "ch-1" and text == "сколько стоит?"
        assert extract_text({"event_type": "chat_started", "payload": {}}) == ("", "")

    def test_hmac(self):
        assert verify_hmac_sha256("s", b"body",
                                  "sha256=" + __import__("hmac").new(
                                      b"s", b"body", __import__("hashlib").sha256).hexdigest())
        assert not verify_hmac_sha256("s", b"body", "sha256=bad")


class TestGrowoClient:

    @pytest.mark.asyncio
    async def test_chat_headers_and_path(self):
        seen = {}

        def h(request):
            seen["url"] = str(request.url)
            seen["slug"] = request.headers.get("x-tenant-slug")
            return httpx.Response(200, json={"response": "ок",
                                             "conversation_id": "c"})

        g = GrowoClient("https://growoai.ru/platform", "alexprom", "key-1")
        g._http._transport = httpx.MockTransport(h)
        r = await g.chat("привет", visitor_id="v1")
        assert r["response"] == "ок"
        assert seen["url"].endswith("/api/v1/chat")
        assert seen["slug"] == "alexprom"

    @pytest.mark.asyncio
    async def test_kb_search_admin_bearer(self):
        seen = {}

        def h(request):
            seen["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"results": [{"content": "x"}]})

        g = GrowoClient("https://growoai.ru/platform", "alexprom", "adm-1")
        g._http._transport = httpx.MockTransport(h)
        res = await g.kb_search("цена")
        assert res == [{"content": "x"}] and seen["auth"] == "Bearer adm-1"
