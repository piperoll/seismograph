"""HTTP adapters for model APIs. Stdlib only (urllib), no SDKs.

Every adapter returns a normalized dict:
    {"text": str, "input_tokens": int|None, "output_tokens": int|None,
     "thinking_tokens": int|None, "latency_ms": float, "status": int,
     "finish": str|None, "error": str|None, "raw": dict|None}

finish is the normalized termination state:
    "stop"      - normal completion
    "truncated" - token budget hit WITH partial visible text (graded normally;
                  verbosity probes hit their cap by design)
    "refusal"   - model refused via a structured channel (OpenAI
                  message.refusal, Anthropic stop_reason refusal)
    "blocked"   - provider-side safety filter blocked prompt or response
A truncation that leaves NO visible text is an error, not an empty answer -
otherwise reasoning/thinking budgets read as capability collapse.

Latency is wall-clock around the HTTP call - it is a measurement, not
overhead, so interactive (non-batch) calls are deliberate: the canary must
ride the same serving path fleets ride.

Reasoning-model budgets: max-token params are combined budgets for
reasoning + visible output on the gpt-5 family and Gemini 2.5. Per-model
config carries token_headroom (added to every request's budget) and, for
Gemini, thinking_budget (thinkingConfig; 0 disables on flash, pro minimum
is 128) so battery budgets keep meaning "visible answer tokens".
"""

import json
import os
import random
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
    never inflate the latency measurement. Any malformed body (non-JSON 200
    from a proxy/CDN, truncated stream, non-dict JSON) becomes a normal error
    result - a single bad response must never escape as an exception and cost
    the session.
    """
    body = json.dumps(payload).encode("utf-8")
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(url, data=body, method="POST")
        for k, v in headers.items():
            req.add_header(k, v)
        req.add_header("Content-Type", "application/json")
        # urllib's default "Python-urllib/x" UA trips CDN WAFs (Groq/Cloudflare
        # error 1010). Generic and honest, but deliberately non-identifying:
        # probe traffic is unmarked so providers cannot special-case it.
        req.add_header("User-Agent", "seismo/0.1")
        start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                raw_bytes = resp.read()
            latency = (time.monotonic() - start) * 1000
            try:
                parsed = json.loads(raw_bytes.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return status, {"error": "non-JSON response body: "
                                + raw_bytes[:200].decode("utf-8", "replace")}, latency
            if not isinstance(parsed, dict):
                return status, {"error": f"non-object JSON body: {str(parsed)[:200]}"}, latency
            return status, parsed, latency
        except urllib.error.HTTPError as e:
            latency = (time.monotonic() - start) * 1000
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:500]
            except Exception:
                pass
            if e.code in RETRY_STATUSES and attempt < MAX_RETRIES:
                # 429s need patience, not speed: under a threaded battery a
                # 1-2-4s ladder just re-slams the limiter (Mistral lost 45/90
                # calls to exactly this on day one). Rate limits wait 5-10-20s
                # plus jitter to decorrelate the workers; other transients keep
                # the quick ladder.
                if e.code == 429:
                    time.sleep(5 * (2 ** attempt) + random.uniform(0, 2))
                else:
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
        except Exception as e:  # IncompleteRead etc. - degrade, never raise
            latency = (time.monotonic() - start) * 1000
            return 0, {"error": f"{type(e).__name__}: {str(e)[:200]}"}, latency
    raise ProviderError(last_err or "unreachable")


def _result(text=None, in_tok=None, out_tok=None, latency=0.0, status=0,
            finish=None, thinking_tokens=None, error=None, raw=None):
    return {"text": text, "input_tokens": in_tok, "output_tokens": out_tok,
            "thinking_tokens": thinking_tokens, "latency_ms": round(latency, 1),
            "status": status, "finish": finish, "error": error, "raw": raw}


def _api_key(model_cfg):
    # strip: a trailing newline from `export KEY=$(cat ...)` would otherwise
    # raise "Invalid header value b'Bearer sk-...\n'" - a traceback carrying
    # the full key into logs
    key = os.environ.get(model_cfg["env_key"], "").strip()
    if not key:
        raise ProviderError(f"missing env {model_cfg['env_key']}")
    return key


def _budget(model_cfg, params):
    """Requested visible-token budget plus per-model reasoning headroom."""
    return params.get("max_tokens", 512) + model_cfg.get("token_headroom", 0)


def _merge_overrides(payload, model_cfg):
    """Apply per-model request_overrides; a null value deletes the field
    (e.g. gpt-5 rejects explicit temperature). Top-level keys only."""
    for k, v in model_cfg.get("request_overrides", {}).items():
        if v is None:
            payload.pop(k, None)
        else:
            payload[k] = v
    return payload


def _empty_truncation_error(finish, text):
    """Budget exhausted with no visible output = measurement error, not an
    empty answer."""
    return finish == "truncated" and not text


def call_anthropic(model_cfg, messages, system, params):
    payload = {
        "model": model_cfg["model"],
        "max_tokens": _budget(model_cfg, params),
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
    if status != 200 or "error" in body and "content" not in body:
        return _result(latency=latency, status=status,
                       error=str(body.get("error", body))[:500])
    text = "".join(b.get("text", "") for b in body.get("content", [])
                   if b.get("type") == "text")
    stop = body.get("stop_reason")
    finish = {"end_turn": "stop", "stop_sequence": "stop",
              "max_tokens": "truncated", "refusal": "refusal"}.get(stop, stop)
    usage = body.get("usage", {})
    if _empty_truncation_error(finish, text):
        return _result(latency=latency, status=status, finish=finish,
                       error="truncated with no visible output "
                             "(raise max_tokens or token_headroom)")
    return _result(text, usage.get("input_tokens"), usage.get("output_tokens"),
                   latency, status, finish=finish, raw=body)


def _call_openai_style(model_cfg, messages, system, params, base_url):
    msgs = ([{"role": "system", "content": system}] if system else []) + messages
    max_tok_param = model_cfg.get("max_tokens_param", "max_tokens")
    payload = {
        "model": model_cfg["model"],
        max_tok_param: _budget(model_cfg, params),
        "messages": msgs,
    }
    if params.get("temperature") is not None:
        payload["temperature"] = params["temperature"]
    _merge_overrides(payload, model_cfg)
    status, body, latency = _post_json(
        base_url.rstrip("/") + "/chat/completions",
        {"Authorization": f"Bearer {_api_key(model_cfg)}"},
        payload)
    if status != 200 or "choices" not in body:
        return _result(latency=latency, status=status,
                       error=str(body.get("error", body))[:500])
    choices = body.get("choices") or [{}]
    message = choices[0].get("message") or {}
    text = message.get("content") or ""
    reason = choices[0].get("finish_reason")
    finish = {"stop": "stop", "length": "truncated",
              "content_filter": "blocked"}.get(reason, reason)
    if not text and message.get("refusal"):
        # structured refusal channel: content null, refusal text populated
        text = message["refusal"]
        finish = "refusal"
    usage = body.get("usage", {})
    thinking = (usage.get("completion_tokens_details") or {}).get(
        "reasoning_tokens")
    if _empty_truncation_error(finish, text):
        return _result(latency=latency, status=status, finish=finish,
                       thinking_tokens=thinking,
                       error="truncated with no visible output "
                             "(reasoning consumed the budget; raise token_headroom)")
    return _result(text, usage.get("prompt_tokens"),
                   usage.get("completion_tokens"), latency, status,
                   finish=finish, thinking_tokens=thinking, raw=body)


def call_openai(model_cfg, messages, system, params):
    return _call_openai_style(model_cfg, messages, system, params,
                              "https://api.openai.com/v1")


def call_openai_compat(model_cfg, messages, system, params):
    return _call_openai_style(model_cfg, messages, system, params,
                              model_cfg["base_url"])


GOOGLE_BLOCK_REASONS = {"SAFETY", "RECITATION", "PROHIBITED_CONTENT",
                        "BLOCKLIST", "SPII", "IMAGE_SAFETY"}


def call_google(model_cfg, messages, system, params):
    contents = [{"role": "model" if m["role"] == "assistant" else "user",
                 "parts": [{"text": m["content"]}]} for m in messages]
    gen_cfg = {"maxOutputTokens": _budget(model_cfg, params)}
    if params.get("temperature") is not None:
        gen_cfg["temperature"] = params["temperature"]
    if model_cfg.get("thinking_budget") is not None:
        gen_cfg["thinkingConfig"] = {
            "thinkingBudget": model_cfg["thinking_budget"]}
    payload = {"contents": contents, "generationConfig": gen_cfg}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    _merge_overrides(payload, model_cfg)
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model_cfg['model']}:generateContent")
    status, body, latency = _post_json(
        url, {"x-goog-api-key": _api_key(model_cfg)}, payload)
    if status != 200 or "error" in body:
        return _result(latency=latency, status=status,
                       error=str(body.get("error", body))[:500])

    usage = body.get("usageMetadata", {})
    in_tok = usage.get("promptTokenCount")
    out_tok = usage.get("candidatesTokenCount")
    thinking = usage.get("thoughtsTokenCount")

    block = (body.get("promptFeedback") or {}).get("blockReason")
    cands = body.get("candidates")
    if not cands:
        # prompt blocked: 200 with promptFeedback and no candidates
        return _result("", in_tok, out_tok, latency, status, finish="blocked",
                       thinking_tokens=thinking, raw=body) if block else \
               _result(latency=latency, status=status,
                       error="no candidates in response")
    cand = cands[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    reason = cand.get("finishReason")
    if reason in GOOGLE_BLOCK_REASONS or block:
        finish = "blocked"
    else:
        finish = {"STOP": "stop", "MAX_TOKENS": "truncated"}.get(reason, reason)
    if _empty_truncation_error(finish, text):
        return _result(latency=latency, status=status, finish=finish,
                       thinking_tokens=thinking,
                       error="truncated with no visible output "
                             "(thinking consumed the budget; adjust "
                             "thinking_budget/token_headroom)")
    return _result(text, in_tok, out_tok, latency, status, finish=finish,
                   thinking_tokens=thinking, raw=body)


class MockProvider:
    """Deterministic offline provider for tests and dry runs.

    responses: optional {probe_id: str | dict} lookup. A string is returned
    as the text of a normal completion; a dict is merged over the default
    result fields (letting tests inject error / finish / latency / token
    values). Falls back to echoing the last user message.
    """

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def call(self, model_cfg, messages, system, params, probe_id=None):
        self.calls.append({"model": model_cfg["id"], "probe": probe_id})
        spec = self.responses.get(probe_id)
        if isinstance(spec, dict):
            base = _result(latency=42.0, status=200, finish="stop")
            base.update(spec)
            return base
        text = spec
        if text is None:
            last_user = next((m["content"] for m in reversed(messages)
                              if m["role"] == "user"), "")
            text = f"MOCK: {last_user[:200]}"
        return _result(text, len(str(messages)) // 4, len(text) // 4,
                       latency=42.0, status=200, finish="stop")


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
