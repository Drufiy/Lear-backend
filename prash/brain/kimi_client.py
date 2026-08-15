"""Ported from prash-backend/app/agent/kimi_client.py (2026-08-09, Track D days 4-5).

All model-calling logic (the two-step Kimi reasoning/structured flow, DeepSeek's
single-call native-thinking pattern, cross-provider fallback chain, transient-error
retries) is UNCHANGED from v1 -- that's the valuable IP, zero coupling to the hosted
stack, confirmed by reading the file, not just PRASH_V2.md's earlier assessment.

Two plumbing changes, per PRASH_V2.md §6's "port after a trivial fix" note --
turned out to be a bit more than trivial, but contained to this file:

1. No Supabase. v1's `_log_agent_call`/`mark_agent_run_outcome` wrote to an
   `agent_calls` table; v2 has no database by design (§4/§7). Ported as local
   logger calls instead of no-ops, so call detail isn't silently discarded --
   same signatures, so diagnosis_agent.py needed zero changes to keep calling them.
2. Lazy client construction. v1 built `kimi`/`deepseek` as AsyncOpenAI clients at
   MODULE IMPORT TIME from a pydantic Settings object that requires the env vars
   to exist. v2 has no such Settings class (CredentialStore is deliberately
   dependency-free, see prash/credentials.py), and eager construction would crash
   on import in any environment without KIMI_API_KEY set -- including every test
   run. Replaced with lazy singleton getters reading os.environ directly, matching
   the exact pattern prash/connectors/kubernetes.py's _client() already uses.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


# ── Client setup (lazy — see module docstring point 2) ─────────────────────────

_kimi: AsyncOpenAI | None = None
_deepseek: AsyncOpenAI | None = None
_deepseek_checked = False


def _kimi_model() -> str:
    return os.environ.get("KIMI_MODEL", "kimi-k2.6")


def _deepseek_model() -> str:
    return os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")


def _primary_model() -> str:
    return os.environ.get("PRIMARY_MODEL", "deepseek")


def _kimi_client() -> AsyncOpenAI:
    global _kimi
    if _kimi is None:
        api_key = os.environ.get("KIMI_API_KEY")
        if not api_key:
            # Real bug, caught live (2026-08-15): a blank KIMI_API_KEY reached
            # here through the DeepSeek-failed -> Kimi-fallback path and the
            # bare AsyncOpenAI(api_key=None, ...) construction raised the
            # SDK's own generic error ("Missing credentials... set
            # OPENAI_API_KEY") -- true, but useless, since the actual gap is
            # KIMI_API_KEY specifically and that name never appeared anywhere
            # in the message. See PRASH_V2.md §10, issue #5.
            raise DiagnosisValidationError(
                "KIMI_API_KEY is not set in your local .env -- needed for Kimi calls "
                "(as the primary model, or as DeepSeek's fallback)."
            )
        _kimi = AsyncOpenAI(
            api_key=api_key,
            base_url=os.environ.get("KIMI_BASE_URL", "https://api.moonshot.ai/v1"),
            timeout=90.0,
        )
    return _kimi


def _deepseek_client() -> AsyncOpenAI | None:
    """None if no key is configured — every call site already handles that as
    'DeepSeek not configured, fall back to Kimi', matching v1's behavior."""
    global _deepseek, _deepseek_checked
    if not _deepseek_checked:
        _deepseek_checked = True
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if api_key:
            _deepseek = AsyncOpenAI(
                api_key=api_key,
                base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
                timeout=90.0,
            )
    return _deepseek


class DiagnosisValidationError(Exception):
    pass


# ── Internal helpers ─────────────────────────────────────────────────────────

def _is_recoverable_model_error(error: Exception) -> bool:
    err_str = str(error).lower()
    return any(
        marker in err_str
        for marker in (
            "402",
            "429",
            "503",
            "insufficient",
            "rate limit",
            "timeout",
            "timed out",
            "temporarily unavailable",
            "connection",
        )
    )

def _extract_json_from_prose(text: str) -> dict | None:
    """
    Last-resort: if the model returned prose instead of a tool call,
    try to extract a JSON object from the response text.
    Handles cases where the model outputs the JSON inline without wrapping it.
    """
    if not text:
        return None
    # Look for the outermost {...} block
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    candidate = json.loads(text[start:i + 1])
                    # Must have at least the core fields to be a valid diagnosis
                    if "fix_type" in candidate and "problem_summary" in candidate:
                        logger.info("Extracted valid JSON from prose response")
                        return candidate
                except json.JSONDecodeError:
                    pass
    return None


def _args_match_schema(args: dict, tool_schema: dict) -> bool:
    """
    A successfully-parsed tool call is not proof the arguments are shaped like the
    tool that was supposedly called — a model under tool_choice="auto" (DeepSeek's
    thinking mode rejects forced tool_choice) can emit valid JSON for a DIFFERENT
    tool's shape under the right function name, e.g. returning a fetch_file-shaped
    {path, line, limit} dict when only submit_diagnosis was offered. json.loads()
    succeeding says nothing about that. Check the required keys actually showed up.
    """
    if not isinstance(args, dict):
        return False
    required = tool_schema.get("parameters", {}).get("required", [])
    return all(key in args for key in required)


def _usage_from_response(response, latency_ms: int) -> dict:
    return {
        "input_tokens": response.usage.prompt_tokens if response.usage else None,
        "output_tokens": response.usage.completion_tokens if response.usage else None,
        "latency_ms": latency_ms,
    }


def _merge_usage(*usages: dict) -> dict:
    input_tokens = 0
    output_tokens = 0
    total_latency = 0
    saw_input = False
    saw_output = False

    for usage in usages:
        if not usage:
            continue
        if usage.get("input_tokens") is not None:
            input_tokens += usage["input_tokens"]
            saw_input = True
        if usage.get("output_tokens") is not None:
            output_tokens += usage["output_tokens"]
            saw_output = True
        total_latency += usage.get("latency_ms") or 0

    return {
        "input_tokens": input_tokens if saw_input else None,
        "output_tokens": output_tokens if saw_output else None,
        "latency_ms": total_latency,
    }


def _is_transient_error(e: Exception) -> bool:
    """Check if an error is transient and worth retrying (timeouts, disconnections, etc.)."""
    err_str = str(e)
    transient_signals = [
        "timed out", "timeout", "TimeoutError",
        "disconnected", "connection", "ConnectionError",
        "RemoteProtocolError", "Server disconnected",
        "502", "503", "504", "529",
    ]
    return any(signal.lower() in err_str.lower() for signal in transient_signals)


async def _create_chat(client, **kwargs):
    """Create a completion, recovering from per-model temperature rules."""
    try:
        return await client.chat.completions.create(**kwargs)
    except Exception as e:
        if "temperature" in str(e).lower() and kwargs.get("temperature") != 1:
            logger.warning("Model rejected temperature=%s — retrying at 1", kwargs.get("temperature"))
            kwargs["temperature"] = 1
            return await client.chat.completions.create(**kwargs)
        raise


async def _call_kimi_reasoning(messages: list):
    """
    First Kimi call: allow thinking and free-form analysis before forcing a tool call.
    Returns (reasoning_text_or_none, raw_content, usage_info).
    Retries once on transient errors (timeouts, disconnections).
    """
    max_attempts = 2
    for attempt in range(max_attempts):
        start = time.time()
        try:
            response = await _create_chat(_kimi_client(),
                model=_kimi_model(),
                messages=messages,
                max_tokens=4000,
                temperature=1,
                extra_body={"thinking": {"type": "enabled", "budget_tokens": 1500}},
            )
        except Exception as e:
            if _is_recoverable_model_error(e) and not _is_transient_error(e):
                err_str = str(e)
                logger.warning(
                    f"Kimi reasoning call recoverable error ({e.__class__.__name__}): "
                    f"{err_str[:200]} — will try fallback"
                )
                return None, "", {"latency_ms": int((time.time() - start) * 1000)}
            if _is_transient_error(e) and attempt < max_attempts - 1:
                logger.warning(
                    f"Kimi reasoning transient error (attempt {attempt + 1}/{max_attempts}): "
                    f"{str(e)[:200]} — retrying after 5s"
                )
                await asyncio.sleep(5)
                continue
            raise

        latency_ms = int((time.time() - start) * 1000)
        msg = response.choices[0].message
        # Kimi thinking responses put the analysis in reasoning_content, content may be empty
        reasoning_content = getattr(msg, "reasoning_content", None) or ""
        content = msg.content or ""
        reasoning = reasoning_content or content  # prefer reasoning_content (the actual thinking)
        logger.info(f"Kimi reasoning: content={len(content)} chars, reasoning_content={len(reasoning_content)} chars")
        return reasoning, reasoning, _usage_from_response(response, latency_ms)

    # Should not reach here, but just in case
    return None, "", {"latency_ms": 0}


async def _call_kimi_structured(messages: list, tool_schema: dict):
    """
    Returns (parsed_args_or_none, raw_content, usage_info).
    Handles 402 (credit exhausted) gracefully — returns None so fallback fires.
    Retries once on transient errors (timeouts, disconnections).

    Note: kimi-k2.6 with thinking disabled requires exactly temperature=0.6.
    Extended thinking is disabled because it is incompatible with forced tool_choice.
    """
    max_attempts = 2
    for attempt in range(max_attempts):
        start = time.time()
        try:
            response = await _create_chat(_kimi_client(),
                model=_kimi_model(),
                messages=messages,
                tools=[{"type": "function", "function": tool_schema}],
                tool_choice={"type": "function", "function": {"name": tool_schema["name"]}},
                temperature=0.6,
                max_tokens=4000,
                extra_body={"thinking": {"type": "disabled"}},
            )
            break
        except Exception as e:
            if _is_recoverable_model_error(e) and not _is_transient_error(e):
                err_str = str(e)
                logger.warning(f"Kimi API recoverable error ({e.__class__.__name__}): {err_str[:200]} — will try fallback")
                return None, "", {"latency_ms": int((time.time() - start) * 1000)}
            if _is_transient_error(e) and attempt < max_attempts - 1:
                logger.warning(
                    f"Kimi structured transient error (attempt {attempt + 1}/{max_attempts}): "
                    f"{str(e)[:200]} — retrying after 5s"
                )
                await asyncio.sleep(5)
                continue
            raise

    latency_ms = int((time.time() - start) * 1000)
    usage = _usage_from_response(response, latency_ms)

    msg = response.choices[0].message

    # ── Path 1: proper tool call ──────────────────────────────────────────────
    if msg.tool_calls:
        raw = msg.tool_calls[0].function.arguments
        try:
            args = json.loads(raw)
        except json.JSONDecodeError:
            # Try to salvage malformed JSON
            extracted = _extract_json_from_prose(raw)
            if extracted:
                return extracted, raw, usage
            logger.warning(
                f"Kimi tool call arguments were not valid JSON and couldn't be salvaged "
                f"— treating as invalid. raw={raw[:300]!r}"
            )
            return None, raw, usage
        if _args_match_schema(args, tool_schema):
            return args, raw, usage
        logger.warning(
            f"Kimi tool call parsed but doesn't match {tool_schema.get('name')} schema "
            f"(missing required keys) — treating as invalid: keys={list(args.keys())}"
        )
        return None, raw, usage

    # ── Path 2: model returned prose — try to extract JSON from it ───────────
    prose = msg.content or ""
    extracted = _extract_json_from_prose(prose)
    if extracted:
        return extracted, prose, usage

    logger.warning(
        f"Kimi ignored the forced tool_choice and returned prose with no extractable "
        f"JSON — treating as invalid. prose={prose[:300]!r}"
    )
    return None, prose, usage


async def _call_kimi(messages: list, tool_schema: dict):
    """
    Two-step Kimi flow:
    1. Run a reasoning pass with thinking enabled.
    2. Feed that analysis back into a forced tool call with thinking disabled.
    """
    reasoning, reasoning_raw, reasoning_usage = await _call_kimi_reasoning(messages)
    if not reasoning:
        logger.info("Empty reasoning — falling through to direct structured call")
        args, structured_raw, structured_usage = await _call_kimi_structured(messages, tool_schema)
        return args, structured_raw, _merge_usage(reasoning_usage, structured_usage)

    structured_messages = [
        *messages,
        {
            "role": "user",
            "content": (
                f"Here is your analysis of the failure:\n\n{reasoning}\n\n"
                "Now submit your structured diagnosis using the tool. Follow the system instructions exactly."
            ),
        },
    ]
    args, structured_raw, structured_usage = await _call_kimi_structured(structured_messages, tool_schema)
    combined_raw = json.dumps(
        {
            "reasoning": reasoning_raw,
            "structured_response": structured_raw,
        }
    )
    return args, combined_raw, _merge_usage(reasoning_usage, structured_usage)


# Budget nesting (must hold): preprocess(~2s) + DEEPSEEK_DIAGNOSIS_BUDGET + Kimi
# fallback must fit inside the processor's 285s outer wall-clock, which in turn must
# fit (with fetch overhead) under the reconciler's 8-min diagnosing cutoff.
#   2 + 240 + ~43 = 285  ✓   |   ~25s fetch + 285 = ~310s << 480s reconciler  ✓
# (The reconciler/processor wall-clock budget is v1's hosted-service context; kept
# here because it's what the timeout constants below were actually tuned against.)
DEEPSEEK_DIAGNOSIS_BUDGET = 240  # seconds — total DeepSeek time across all investigation steps (4 min)
KIMI_FALLBACK_RESERVE = 35       # seconds — real headroom left for Kimi when DeepSeek exhausts its budget
DEEPSEEK_CALL_TIMEOUT = 240      # seconds — default per-call cap (used outside investigation loop)


async def _call_deepseek(model: str, messages: list, tool_schema: dict, timeout: float | None = None):
    """
    Single-call native pattern for DeepSeek V4: thinking is ON by default, and the
    model reasons AND emits the structured tool call in one coherent pass.

    We deliberately do NOT force tool_choice — DeepSeek rejects forced tool_choice in
    thinking mode ("Thinking mode does not support this tool_choice"). tool_choice="auto"
    keeps the reasoning in the model's own context as it produces the diagnosis, which
    is strictly better than splitting reasoning from the decision across two calls.

    The httpx 90s timeout doesn't cap total stream duration — it's a per-read-gap
    timeout, so unbounded thinking streams right past it. The asyncio timeout caps
    the total call duration.
    """
    deepseek = _deepseek_client()
    call_timeout = timeout or DEEPSEEK_CALL_TIMEOUT
    max_attempts = 2
    for attempt in range(max_attempts):
        start = time.time()
        try:
            response = await asyncio.wait_for(
                _create_chat(deepseek,
                    model=model,
                    messages=messages,
                    tools=[{"type": "function", "function": tool_schema}],
                    tool_choice="auto",
                    max_tokens=8000,
                    temperature=1,
                ),
                timeout=call_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"DeepSeek ({model}) exceeded {call_timeout:.0f}s hard cap (attempt {attempt+1})")
            return None, f"DeepSeek call timed out after {call_timeout:.0f}s", {"latency_ms": int((time.time() - start) * 1000)}
        except Exception as e:
            if _is_transient_error(e) and attempt < max_attempts - 1:
                logger.warning(f"DeepSeek ({model}) transient error (attempt {attempt+1}): {str(e)[:200]} — retrying after 5s")
                await asyncio.sleep(5)
                continue
            logger.warning(f"DeepSeek ({model}) call failed: {str(e)[:200]}")
            return None, str(e)[:200], {"latency_ms": int((time.time() - start) * 1000)}

        latency_ms = int((time.time() - start) * 1000)
        usage = _usage_from_response(response, latency_ms)
        msg = response.choices[0].message
        reasoning_content = getattr(msg, "reasoning_content", None) or ""
        logger.info(f"DeepSeek ({model}): reasoning={len(reasoning_content)} chars, tool_calls={len(msg.tool_calls or [])}")

        if msg.tool_calls:
            raw = msg.tool_calls[0].function.arguments
            try:
                args = json.loads(raw)
            except json.JSONDecodeError:
                extracted = _extract_json_from_prose(raw)
                if extracted:
                    return extracted, raw, usage
                return None, raw, usage
            if _args_match_schema(args, tool_schema):
                return args, raw, usage
            # A successful tool call with the right function name is not proof the
            # arguments are shaped right — DeepSeek under tool_choice="auto" (thinking
            # mode rejects forced tool_choice) can emit a different tool's argument
            # shape under the one offered function name, e.g. a fetch_file-shaped
            # {path, line, limit} dict where submit_diagnosis was expected. Treat that
            # as a failed call so the retry/fallback chain handles it instead of a
            # Pydantic crash deep in diagnose_failure().
            logger.warning(
                f"DeepSeek ({model}) tool call parsed but doesn't match {tool_schema.get('name')} "
                f"schema (missing required keys) — treating as invalid: keys={list(args.keys())}"
            )
            return None, raw, usage

        # No tool call — model returned prose; try to recover JSON from it.
        prose = msg.content or ""
        extracted = _extract_json_from_prose(prose)
        if extracted:
            return extracted, prose, usage
        return None, prose, usage

    return None, "", {"latency_ms": 0}


async def _call_openai_compatible_fallback(
    client: AsyncOpenAI,
    model: str,
    messages: list,
    tool_schema: dict,
    label: str,
) -> tuple:
    """
    Generic fallback for any OpenAI-compatible endpoint.
    Returns (parsed_args_or_none, raw_content, usage_info).
    """
    if not client:
        return None, "", {}
    start = time.time()
    try:
        # DeepSeek V4 models have thinking mode on by default; forced tool_choice
        # is incompatible with thinking mode — disable it explicitly.
        extra = {"extra_body": {"thinking": {"type": "disabled"}}} if model.startswith("deepseek-") else {}
        response = await _create_chat(client,
            model=model,
            messages=messages,
            tools=[{"type": "function", "function": tool_schema}],
            tool_choice={"type": "function", "function": {"name": tool_schema["name"]}},
            max_tokens=4000,
            temperature=1,
            **extra,
        )
    except Exception as e:
        logger.error(f"{label} fallback failed: {e}")
        return None, str(e)[:200], {"latency_ms": int((time.time() - start) * 1000)}

    latency_ms = int((time.time() - start) * 1000)
    usage = {
        "input_tokens": response.usage.prompt_tokens if response.usage else None,
        "output_tokens": response.usage.completion_tokens if response.usage else None,
        "latency_ms": latency_ms,
    }

    msg = response.choices[0].message

    if msg.tool_calls:
        raw = msg.tool_calls[0].function.arguments
        try:
            args = json.loads(raw)
        except json.JSONDecodeError:
            extracted = _extract_json_from_prose(raw)
            if extracted:
                return extracted, raw, usage
            return None, raw, usage
        if _args_match_schema(args, tool_schema):
            return args, raw, usage
        logger.warning(
            f"{label} tool call parsed but doesn't match {tool_schema.get('name')} schema "
            f"(missing required keys) — treating as invalid: keys={list(args.keys())}"
        )
        return None, raw, usage

    prose = msg.content or ""
    extracted = _extract_json_from_prose(prose)
    if extracted:
        return extracted, prose, usage

    return None, prose, usage


async def _call_with_tools(messages: list, tools: list[dict], model: str = "auto", timeout: float | None = None):
    """Single call with multiple investigation tools enabled and native thinking.
    Works with both Kimi and DeepSeek. Retries once on transient errors."""
    deepseek = _deepseek_client()
    use_deepseek = model.startswith("deepseek-") or (model == "auto" and _primary_model() == "deepseek")
    client = deepseek if use_deepseek else _kimi_client()
    model_id = (model if model.startswith("deepseek-") else _deepseek_model()) if use_deepseek else _kimi_model()

    if use_deepseek and not client:
        logger.warning("DeepSeek client not configured — falling back to Kimi for investigation")
        client = _kimi_client()
        model_id = _kimi_model()
        use_deepseek = False

    # DeepSeek: thinking is on by default, tool_choice="auto" is compatible.
    # Kimi: thinking via extra_body.
    extra = {} if use_deepseek else {"extra_body": {"thinking": {"type": "enabled", "budget_tokens": 1500}}}

    per_call_timeout = timeout or (DEEPSEEK_CALL_TIMEOUT if use_deepseek else 90)
    max_attempts = 2
    for attempt in range(max_attempts):
        start = time.time()
        try:
            response = await asyncio.wait_for(
                _create_chat(client,
                    model=model_id,
                    messages=messages,
                    tools=[{"type": "function", "function": tool} for tool in tools],
                    tool_choice="auto",
                    max_tokens=8000 if use_deepseek else 4000,
                    temperature=1,
                    **extra,
                ),
                timeout=per_call_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"{model_id} investigation call exceeded {per_call_timeout}s hard cap (attempt {attempt+1})")
            return None, "", {"latency_ms": int((time.time() - start) * 1000)}
        except Exception as e:
            if _is_recoverable_model_error(e) and not _is_transient_error(e):
                logger.warning(f"{model_id} investigation call recoverable error: {str(e)[:200]}")
                return None, "", {"latency_ms": int((time.time() - start) * 1000)}
            if _is_transient_error(e) and attempt < max_attempts - 1:
                logger.warning(f"{model_id} investigation transient error (attempt {attempt+1}): {str(e)[:200]} — retrying after 5s")
                await asyncio.sleep(5)
                continue
            raise

        latency_ms = int((time.time() - start) * 1000)
        msg = response.choices[0].message
        return msg, json.dumps(msg.model_dump(), default=str), _usage_from_response(response, latency_ms)

    return None, "", {"latency_ms": 0}


def _log_agent_call(run_id, call_type, model, messages, raw, parsed, usage, valid, error=None):
    """v1 wrote this to a Supabase agent_calls table; v2 has no DB (§4/§7).
    Logged locally instead of a silent no-op, so call detail survives in the
    process's own logs. Same signature as v1 -- diagnosis_agent.py and this
    file's own investigation loop call this unconditionally throughout, so
    keeping the shape identical meant zero changes to those call sites."""
    try:
        logger.info(
            "agent_call run_id=%s type=%s model=%s valid=%s error=%s cost_usd=%s tokens_in=%s tokens_out=%s latency_ms=%s",
            run_id, call_type, model, valid, error,
            _estimate_cost_usd(model, usage or {}),
            (usage or {}).get("input_tokens"),
            (usage or {}).get("output_tokens"),
            (usage or {}).get("latency_ms"),
        )
    except Exception as e:
        logger.error(f"Failed to log agent call: {e}")
        # Never propagate — logging must not break the pipeline


_PRICES_PER_1M = {
    # model_name: (input_price, output_price) — matches v1's config.py defaults
    "kimi-k2.6": (0.60, 2.50),
    "deepseek-v4-flash": (0.14, 0.28),
}


def _estimate_cost_usd(model: str, usage: dict) -> float | None:
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if input_tokens is None and output_tokens is None:
        return None

    rates = _PRICES_PER_1M.get(model)
    if not rates:
        return None
    input_rate, output_rate = rates

    estimated = 0.0
    if input_tokens is not None and input_rate is not None:
        estimated += (input_tokens / 1_000_000) * input_rate
    if output_tokens is not None and output_rate is not None:
        estimated += (output_tokens / 1_000_000) * output_rate
    return round(estimated, 6)


def mark_agent_run_outcome(run_id: str | None, outcome: str):
    """v1 wrote this to Supabase; v2 logs locally. See _log_agent_call docstring."""
    if not run_id:
        return
    logger.info("agent_run_outcome run_id=%s outcome=%s", run_id, outcome)


async def call_with_investigation(
    system_prompt: str,
    user_prompt: str,
    diagnosis_tool_schema: dict,
    investigation_tools: list[dict],
    execute_tool,
    run_id: str | None = None,
    call_type: str = "diagnosis",
    max_steps: int = 2,
    model: str = "auto",
) -> dict:
    use_deepseek = model.startswith("deepseek-") or (model == "auto" and _primary_model() == "deepseek")
    model_id = (model if model.startswith("deepseek-") else _deepseek_model()) if use_deepseek else _kimi_model()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    all_tools = investigation_tools + [diagnosis_tool_schema]

    # Single shared deadline: DeepSeek gets DEEPSEEK_DIAGNOSIS_BUDGET seconds total
    # across ALL steps. Whatever time remains goes to each successive call.
    # If DeepSeek exhausts the budget or fails, Kimi gets KIMI_FALLBACK_RESERVE.
    diagnosis_start = time.time()
    deepseek_budget = DEEPSEEK_DIAGNOSIS_BUDGET if use_deepseek else float("inf")
    deepseek_failed = False

    for step in range(max_steps):
        elapsed = time.time() - diagnosis_start
        remaining = deepseek_budget - elapsed

        if use_deepseek and remaining < 15:
            logger.warning(
                f"DeepSeek budget nearly exhausted ({remaining:.0f}s left) at step {step + 1} "
                f"for run {run_id} — breaking to final call"
            )
            deepseek_failed = True
            break

        step_timeout = remaining if use_deepseek else None
        message, raw, usage = await _call_with_tools(messages, all_tools, model=model, timeout=step_timeout)

        if message is None:
            logger.warning(
                f"Primary model returned None on investigation step {step + 1} for run {run_id} "
                f"— skipping remaining steps"
            )
            _log_agent_call(
                run_id, f"{call_type}_step_{step + 1}", model_id,
                messages, raw or "", None, usage, valid=False,
                error="primary model timeout/disconnect",
            )
            deepseek_failed = True
            break

        if not message.tool_calls:
            _log_agent_call(
                run_id, f"{call_type}_step_{step + 1}", model_id,
                messages, raw, None, usage, valid=False,
                error="no tool call — nudging",
            )
            messages.append({"role": "assistant", "content": (message.content if message else "") or "(no content)"})
            messages.append({"role": "user", "content":
                "You did not call a tool. Either call an investigation tool to gather "
                "what you still need, or call submit_diagnosis now with your best fix."})
            continue

        tool_call = message.tool_calls[0]
        tool_name = tool_call.function.name
        try:
            tool_args = json.loads(tool_call.function.arguments or "{}")
        except json.JSONDecodeError:
            tool_args = {}

        if tool_name == diagnosis_tool_schema["name"]:
            _log_agent_call(
                run_id, f"{call_type}_step_{step + 1}", model_id,
                messages, raw, tool_args, usage, valid=True,
            )
            return tool_args

        tool_result = await execute_tool(tool_name, tool_args)
        assistant_msg = {
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [{
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": tool_call.function.arguments,
                },
            }],
        }
        reasoning = getattr(message, "reasoning_content", None)
        if reasoning:
            assistant_msg["reasoning_content"] = reasoning
        messages.append(assistant_msg)
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": tool_result,
        })
        _log_agent_call(
            run_id, f"{call_type}_step_{step + 1}", model_id,
            messages, raw, {"tool": tool_name}, usage, valid=True,
        )

    # Force a final structured call with whatever budget remains.
    final_messages = messages + [{"role": "user", "content":
        "Investigation complete. Submit your structured diagnosis now using submit_diagnosis."}]

    if use_deepseek and not deepseek_failed:
        elapsed = time.time() - diagnosis_start
        remaining = deepseek_budget - elapsed
        if remaining > 15:
            args, raw, usage = await _call_deepseek(model_id, final_messages, diagnosis_tool_schema, timeout=remaining)
        else:
            deepseek_failed = True
            args = None

        if args is not None:
            _log_agent_call(
                run_id, f"{call_type}_final", model_id,
                final_messages, raw, args, usage, valid=True,
            )
            return args
        else:
            deepseek_failed = True
            _log_agent_call(
                run_id, f"{call_type}_final", model_id,
                final_messages, raw or "", args, usage if not deepseek_failed else {"latency_ms": 0},
                valid=False, error="DeepSeek final call failed — trying Kimi",
            )

    if not use_deepseek or deepseek_failed:
        fallback_model = _kimi_model() if use_deepseek else model_id
        if use_deepseek:
            logger.warning(f"DeepSeek exhausted {time.time() - diagnosis_start:.0f}s — falling back to Kimi for final call")
        args, raw, usage = await _call_kimi_structured(final_messages, diagnosis_tool_schema)
        _log_agent_call(
            run_id, f"{call_type}_final{'_fallback' if use_deepseek else ''}", fallback_model,
            final_messages, raw, args, usage,
            valid=(args is not None),
            error=None if args else "Kimi final call produced no tool call",
        )
        if args is not None:
            return args

    raise DiagnosisValidationError("Investigation loop did not yield a final diagnosis (both models failed).")


# ── Public API ────────────────────────────────────────────────────────────────

async def call_with_tool(
    system_prompt: str,
    user_prompt: str,
    tool_schema: dict,
    run_id: str | None = None,
    call_type: str = "diagnosis",
    temperature: float = 0.6,   # 0.6 required when thinking disabled on kimi-k2.6
    model: str = "auto",
) -> dict:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # Resolve "auto" to the configured primary model
    if model == "auto":
        model = _deepseek_model() if _primary_model() == "deepseek" else "kimi"

    # DeepSeek primary path — single-call native thinking
    if model.startswith("deepseek-"):
        args, raw, usage = await _call_deepseek(model, messages, tool_schema)
        _log_agent_call(run_id, call_type, model, messages, raw, args, usage,
                        valid=(args is not None), error="No tool call" if args is None else None)
        if args is not None:
            return args
        # DeepSeek failed — fall through to Kimi as cross-provider fallback
        logger.warning(f"DeepSeek {model} returned no valid tool call — trying Kimi fallback")

    # Kimi path (primary if configured, or fallback if DeepSeek failed)
    args, raw, usage = await _call_kimi(messages, tool_schema)
    _log_agent_call(run_id, call_type, _kimi_model(), messages, raw, args, usage,
                    valid=(args is not None), error="No tool call in response" if args is None else None)
    if args is not None:
        return args
    logger.warning("Kimi attempt 1: no valid tool call — retrying")

    # Attempt 2: Kimi retry
    args, raw, usage = await _call_kimi(messages, tool_schema)
    _log_agent_call(run_id, call_type, _kimi_model(), messages, raw, args, usage,
                    valid=(args is not None), error="No tool call after retry" if args is None else None)
    if args is not None:
        return args

    deepseek = _deepseek_client()
    if deepseek:
        logger.warning("Kimi returned no valid tool call after retry — trying DeepSeek fallback")
        args, raw, usage = await _call_openai_compatible_fallback(
            deepseek,
            _deepseek_model(),
            messages,
            tool_schema,
            "DeepSeek",
        )
        _log_agent_call(
            run_id,
            f"{call_type}_fallback",
            _deepseek_model(),
            messages,
            raw,
            args,
            usage,
            valid=(args is not None),
            error="No tool call from fallback" if args is None else None,
        )
        if args is not None:
            return args

    raise DiagnosisValidationError(
        "Kimi returned no valid tool call after 2 attempts. "
        "Fallback was unavailable or also failed. Check logs for raw responses."
    )
