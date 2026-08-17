"""HTTP adapters for model APIs. Stdlib only (urllib), no SDKs.

Every adapter returns a normalized dict:
    {"text": str, "input_tokens": int|None, "output_tokens": int|None,
     "latency_ms": float, "status": int, "error": str|None, "raw": dict|None}

Latency is wall-clock around the HTTP call - it is a measurement, not
overhead, so interactive (non-batch) calls are deliberate: the canary must
ride the same serving path fleets ride.
"""

import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_TIMEOUT = 120
RETRY_STATUSES = {429, 500, 502, 503, 529}
MAX_RETRIES = 3


class ProviderError(Exception):
    pass


def _post_json(url, headers, payload, timeout=DEFAULT_TIMEOUT):
    """POST with retries on transient statuses. Returns (status, body_dict, latency_ms).

    latency_ms is for the final (successful or last) attempt only, so retries
    never inflate the latency measurement.
    """
    body = json.dumps(payload).encode("utf-8")
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(url, data=body, method="POST")
        for k, v in headers.items():
            req.add_header(k, v)
        req.add_header("Content-Type", "application/json")
        start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                latency = (time.monotonic() - start) * 1000
                return resp.status, json.loads(resp.read().decode("utf-8")), latency
        except urllib.error.HTTPError as e:
            latency = (time.monotonic() - start) * 1000
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:500]
            except Exception:
                pass
            if e.code in RETRY_STATUSES and attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
                last_err = f"HTTP {e.code}: {detail}"
                continue
            return e.code, {"error": detail}, latency
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            latency = (time.monotonic() - start) * 1000
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
                last_err = str(e)
                continue
            return 0, {"error": str(e)}, latency
    raise ProviderError(last_err or "unreachable")


def _result(text=None, in_tok=None, out_tok=None, latency=0.0, status=0,
            error=None, raw=None):
    return {"text": text, "input_tokens": in_tok, "output_tokens": out_tok,
            "latency_ms": round(latency, 1), "status": status,
            "error": error, "raw": raw}


def _api_key(model_cfg):
    key = os.environ.get(model_cfg["env_key"], "")
    if not key:
        raise ProviderError(f"missing env {model_cfg['env_key']}")
    return key


def _merge_overrides(payload, model_cfg):
    """Apply per-model request_overrides; a null value deletes the field
    (e.g. gpt-5 rejects explicit temperature)."""
    for k, v in model_cfg.get("request_overrides", {}).items():
        if v is None:
            payload.pop(k, None)
        else:
            payload[k] = v
    return payload


def call_anthropic(model_cfg, messages, system, params):
    payload = {
        "model": model_cfg["model"],
        "max_tokens": params.get("max_tokens", 512),
        "messages": messages,
    }
    if system:
        payload["system"] = system
    if params.get("temperature") is not None:
        payload["temperature"] = params["temperature"]
    _merge_overrides(payload, model_cfg)
    status, body, latency = _post_json(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": _api_key(model_cfg), "anthropic-version": "2023-06-01"},
        payload)
    if status != 200:
        return _result(latency=latency, status=status,
                       error=str(body.get("error", body))[:500])
    text = "".join(b.get("text", "") for b in body.get("content", [])
                   if b.get("type") == "text")
    usage = body.get("usage", {})
    return _result(text, usage.get("input_tokens"), usage.get("output_tokens"),
                   latency, status, raw=body)


def _call_openai_style(model_cfg, messages, system, params, base_url):
    msgs = ([{"role": "system", "content": system}] if system else []) + messages
    max_tok_param = model_cfg.get("max_tokens_param", "max_tokens")
    payload = {
        "model": model_cfg["model"],
        max_tok_param: params.get("max_tokens", 512),
        "messages": msgs,
    }
    if params.get("temperature") is not None:
        payload["temperature"] = params["temperature"]
    _merge_overrides(payload, model_cfg)
    status, body, latency = _post_json(
        base_url.rstrip("/") + "/chat/completions",
        {"Authorization": f"Bearer {_api_key(model_cfg)}"},
        payload)
    if status != 200:
        return _result(latency=latency, status=status,
                       error=str(body.get("error", body))[:500])
    choices = body.get("choices") or [{}]
    text = (choices[0].get("message") or {}).get("content") or ""
    usage = body.get("usage", {})
    return _result(text, usage.get("prompt_tokens"),
                   usage.get("completion_tokens"), latency, status, raw=body)


def call_openai(model_cfg, messages, system, params):
    return _call_openai_style(model_cfg, messages, system, params,
                              "https://api.openai.com/v1")


def call_openai_compat(model_cfg, messages, system, params):
    return _call_openai_style(model_cfg, messages, system, params,
                              model_cfg["base_url"])


def call_google(model_cfg, messages, system, params):
    contents = [{"role": "model" if m["role"] == "assistant" else "user",
                 "parts": [{"text": m["content"]}]} for m in messages]
    payload = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": params.get("max_tokens", 512)},
    }
    if params.get("temperature") is not None:
        payload["generationConfig"]["temperature"] = params["temperature"]
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    _merge_overrides(payload, model_cfg)
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model_cfg['model']}:generateContent")
    status, body, latency = _post_json(
        url, {"x-goog-api-key": _api_key(model_cfg)}, payload)
    if status != 200:
        return _result(latency=latency, status=status,
                       error=str(body.get("error", body))[:500])
    cands = body.get("candidates") or [{}]
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    usage = body.get("usageMetadata", {})
    return _result(text, usage.get("promptTokenCount"),
                   usage.get("candidatesTokenCount"), latency, status, raw=body)


class MockProvider:
    """Deterministic offline provider for tests and dry runs.

    responses: optional {probe_id: text} lookup; falls back to echoing the
    last user message. Latency is synthetic but stable.
    """

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def call(self, model_cfg, messages, system, params, probe_id=None):
        self.calls.append({"model": model_cfg["id"], "probe": probe_id})
        text = self.responses.get(probe_id)
        if text is None:
            last_user = next((m["content"] for m in reversed(messages)
                              if m["role"] == "user"), "")
            text = f"MOCK: {last_user[:200]}"
        return _result(text, len(str(messages)) // 4, len(text) // 4,
                       latency=42.0, status=200)


ADAPTERS = {
    "anthropic": call_anthropic,
    "openai": call_openai,
    "openai_compat": call_openai_compat,
    "google": call_google,
}


def call_model(model_cfg, messages, system, params, mock=None, probe_id=None):
    """Route one request. mock (a MockProvider) short-circuits all providers."""
    if mock is not None:
        return mock.call(model_cfg, messages, system, params, probe_id=probe_id)
    provider = model_cfg["provider"]
    if provider not in ADAPTERS:
        raise ProviderError(f"unknown provider: {provider}")
    return ADAPTERS[provider](model_cfg, messages, system, params)
