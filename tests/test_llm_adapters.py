"""Verifica il formato delle richieste verso Claude e Ollama, senza chiamare servizi reali."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx2 as httpx
import pytest

from app import models as m
from app.analysis.llm import ClaudeLLM, user_message
from app.analysis.ollama import OllamaLLM
from app.errors import AnalysisError


def _sse(events):
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)


def _claude_stream(text, stop_reason="end_turn"):
    return _sse([
        {"type": "message_start", "message": {"id": "msg_1", "type": "message", "role": "assistant",
                                              "model": "claude-opus-5-5", "content": [], "stop_reason": None,
                                              "stop_sequence": None,
                                              "usage": {"input_tokens": 10, "output_tokens": 0}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
         "usage": {"output_tokens": 5}},
        {"type": "message_stop"},
    ])


def _claude(handler):
    llm = ClaudeLLM(api_key="sk-test")
    llm.client = llm.client.with_options(http_client=httpx.Client(transport=httpx.MockTransport(handler)),
                                         max_retries=0)
    return llm


def test_claude_request_shape_and_parsing():
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta")
        seen["key"] = request.headers.get("x-api-key") or request.headers.get("authorization")
        body = _claude_stream(json.dumps({"title": "Titolo", "markdown": "## A"}))
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    out = _claude(handler).structured("sistema", [user_message("domanda", context="TRASCRIZIONE")], m.SummaryOut)
    assert out == m.SummaryOut(title="Titolo", markdown="## A")
    body = seen["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"]["effort"] == "medium"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in seen["beta"]
    assert body["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert "sk-test" in seen["key"]


def test_claude_errors_are_translated():
    def unauthorized(request):
        return httpx.Response(401, json={"type": "error", "error": {"type": "authentication_error",
                                                                     "message": "invalid x-api-key"}})

    with pytest.raises(AnalysisError, match="Chiave API"):
        _claude(unauthorized).structured("s", [user_message("x")], m.SummaryOut)

    def refusal(request):
        return httpx.Response(200, text=_claude_stream("", "refusal"), headers={"content-type": "text/event-stream"})

    with pytest.raises(AnalysisError, match="rifiutato"):
        _claude(refusal).structured("s", [user_message("x")], m.SummaryOut)


def test_claude_requires_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(AnalysisError, match="ANTHROPIC_API_KEY"):
        ClaudeLLM()


@pytest.fixture
def ollama_server():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append(body)
            if body["model"] == "mancante":
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'{"error":"model not found"}')
                return
            content = json.dumps({"answer": "Sì [#3].", "citations": [3]})
            payload = json.dumps({"message": {"role": "assistant", "content": content}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", received
    server.shutdown()


def test_ollama_adapter(ollama_server):
    url, received = ollama_server
    out = OllamaLLM("gemma3:4b", url).structured("sistema", [user_message("domanda", context="CTX")], m.ChatAnswer)
    assert out.citations == [3]
    body = received[0]
    assert body["messages"][0] == {"role": "system", "content": "sistema"}
    assert body["messages"][1]["content"] == "CTX\n\ndomanda"
    assert body["format"]["properties"]["citations"]["type"] == "array"
    assert body["options"]["num_ctx"] == 16384

    with pytest.raises(AnalysisError, match="ollama pull mancante"):
        OllamaLLM("mancante", url).structured("s", [user_message("x")], m.ChatAnswer)


def test_ollama_not_running():
    with pytest.raises(AnalysisError, match="Ollama non risponde"):
        OllamaLLM(url="http://127.0.0.1:9").structured("s", [user_message("x")], m.ChatAnswer)


@pytest.fixture
def gemini_server():
    state = {"requests": [], "fail_first": 1}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append((self.path, self.headers.get("x-goog-api-key"), body))
            if state["fail_first"]:
                state["fail_first"] -= 1
                self.send_response(429)
                self.end_headers()
                self.wfile.write(b'{"error":{"code":429}}')
                return
            parts = [{"text": "ragionamento", "thought": True},
                     {"text": json.dumps({"title": "T", "markdown": "## A"})}]
            payload = json.dumps({"candidates": [{"content": {"parts": parts}, "finishReason": "STOP"}]})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload.encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", state
    server.shutdown()


def test_gemini_adapter_retries_and_parses(gemini_server):
    from app.analysis.gemini import GeminiLLM

    url, state = gemini_server
    llm = GeminiLLM("gemini-3.8-flash", api_key="g-key", retry_delay=0.01, base_url=url)
    history = [user_message("prima", context="CTX"), {"role": "assistant", "content": "risposta"},
               user_message("seconda")]
    out = llm.structured("sistema", history, m.SummaryOut)
    assert out.title == "T"
    assert len(state["requests"]) == 2  # primo tentativo 429, poi riuscito
    path, key, body = state["requests"][-1]
    assert path == "/v1beta/models/gemini-3.8-flash:generateContent" and key == "g-key"
    assert body["systemInstruction"]["parts"][0]["text"] == "sistema"
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    assert body["contents"][0]["parts"][0]["text"] == "CTX\n\nprima"
    assert body["generationConfig"]["responseJsonSchema"]["required"] == ["title", "markdown"]


def test_gemini_requires_key():
    from app.analysis.gemini import GeminiLLM

    with pytest.raises(AnalysisError, match="GEMINI_API_KEY"):
        GeminiLLM(api_key="")


def test_inline_schema_keeps_title_fields():
    from app.analysis.schema import inline_schema

    s = inline_schema(m.KeywordsOut)
    assert "$defs" not in s
    topic = s["properties"]["topics"]["items"]
    assert set(topic["properties"]) == {"title", "description", "segment_ids"}
    assert inline_schema(m.SummaryOut)["properties"]["title"] == {"description": m.SummaryOut.model_fields["title"].description, "type": "string"}
