"""REPL stage 2 (PRASH_V2.md §6b): free-text intent -> command resolution.

Stage 1 made the REPL a persistent session with context; stage 2 lets the
user type the way they'd talk to a person instead of the way they'd call a
CLI: "my api pod is sick, fix it" -> `fix prash-demo/api-...`. Deliberately
narrow and honest: if intent can't be resolved with real confidence, this
module says so and the caller asks a clarifying question rather than guessing
and running the wrong command against real infrastructure.

Two-stage by design:
    resolve(text, session) -> Suggestion | Clarify | None
        Suggestion  -> argv to run (already context-resolved) + an explanation
        Clarify     -> a question to ask, with concrete known options
        None        -> genuinely couldn't resolve it, fast or otherwise

The fast path (_verb_hit + the target regexes below) is pure and free --
zero latency, zero API cost, unit-testable headlessly. When it doesn't
recognize the text at all (Milestone 2, 2026-08-24), resolve() falls back
to routing it through the same tool-calling brain the diagnosis pipeline
uses (prash/brain/kimi_client.py's call_with_tool), built dynamically from
the real provider/action registries so a new connector never needs a
hand-added verb here. That fallback does real I/O and can fail (missing
credentials, model/network trouble) -- it degrades to None on any failure,
same contract as the fast path, never a crash.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

# A pod-ish token: lowercase start, dashes allowed, not too long. Anything
# containing "/" is treated as an already-qualified target (ns/pod or
# owner/repo) and never needs resolving.
_TARGETISH = re.compile(r"^[a-z0-9][a-z0-9-_.]{1,60}/[a-z0-9][a-z0-9-_.]{1,60}$")

# A bare resource name must look like one -- k8s names are dash-y/nummer-y
# (api-7f9d, broken-app, web-3). Plain words like "api", "fix" or "pr" are
# talk, not targets; treating them as targets produces wrong guesses.
_BAREISH = re.compile(r"^[a-z0-9][a-z0-9-]{2,40}$")


def _looks_like_bare_resource(w: str) -> bool:
    return bool(_BAREISH.fullmatch(w)) and ("-" in w or any(c.isdigit() for c in w))

# Words that are talk, not entity. Everything else that looks podish and
# isn't on this list is a candidate target.
_STOPWORDS = {
    "the", "a", "an", "my", "your", "is", "are", "was", "were", "be",
    "pod", "pods", "app", "application", "service", "deployment", "cluster",
    "broken", "sick", "down", "stuck", "crash", "crashing", "crashlooping",
    "failed", "failing", "and", "or", "but", "please", "can", "could", "you",
    "it", "that", "this", "with", "from", "for", "now", "quickly", "again",
}


@dataclass
class Clarify:
    """A question to ask the user, with concrete known options."""

    question: str
    options: list[str] = field(default_factory=list)


@dataclass
class Suggestion:
    """A resolved command line, ready to run."""

    argv: list[str]
    explain: str


class _Context:
    """The slice of REPL session state intent parsing needs."""

    def __init__(self, namespace: str | None = None, pod: str | None = None,
                 last_target: str | None = None) -> None:
        self.namespace = namespace
        self.pod = pod
        self.last_target = last_target

    @classmethod
    def from_session(cls, session) -> _Context:
        return cls(session.namespace, session.pod, session.last_target)


def _words(text: str) -> list[str]:
    return [w.lower().strip(".,;:!?") for w in text.split()]


def _targets_in(text: str) -> list[str]:
    """Candidate target tokens, in the order they appeared. Qualified
    ns/pod and owner/repo targets win outright; bare podish words are the
    raw material for resolving against the session."""
    qualified, bare = [], []
    for w in _words(text):
        if _TARGETISH.fullmatch(w):
            qualified.append(w)
        elif _looks_like_bare_resource(w) and w not in _STOPWORDS:
            bare.append(w)
    return qualified + bare


def _verb_hit(text: str) -> str | None:
    """Return the intent verb, or None if the text doesn't read as intent."""
    low = text.lower()
    # Longer phrases first so "open a pr" wins over a bare "pr".
    if "open a pr" in low or "open pr" in low or "open a pull request" in low:
        return "open-pr"
    if "apply the ci fix" in low or "apply the fix" in low or "apply ci fix" in low:
        return "apply-ci-fix"
    if "what can you do" in low or "what do you do" in low or "list actions" in low:
        return "actions"
    for word, verb in (
        ("restart", "restart"), ("reboot", "restart"), ("fix", "fix"),
        ("diagnose", "fix"), ("watch", "watch"), ("monitor", "watch"),
        ("rollback", "rollback"), ("revert", "rollback"),
        ("audit", "audit"), ("actions", "actions"), ("config", "config"),
        ("circuit", "circuit"),
    ):
        if word in low:
            return verb
    return None


def _needs_target(verb: str) -> str | None:
    """What kind of target each verb needs: 'pod', 'repo', or None."""
    return {
        "fix": "pod",
        "restart": "pod",
        "rollback": "pod",
        "open-pr": "repo",
        "apply-ci-fix": "repo",
    }.get(verb)


def _resolve_target(kind: str, targets: list[str], ctx: _Context) -> str | None:
    """Turn raw candidate tokens into one concrete target, or None."""
    for t in targets:
        if "/" in t:
            return t
    if not targets:
        # No explicit entity: a remembered target is the only safe default.
        if kind == "repo":
            return None  # never guess a repo
        return ctx.last_target or (f"{ctx.namespace}/{ctx.pod}" if ctx.namespace and ctx.pod else None)
    # Bare name: qualify with the remembered namespace if we have one.
    if ctx.namespace:
        return f"{ctx.namespace}/{targets[0]}"
    return targets[0]


def _known_options(ctx: _Context) -> list[str]:
    opts: list[str] = []
    for t in (ctx.last_target, f"{ctx.namespace}/{ctx.pod}" if ctx.namespace and ctx.pod else None):
        if t and t not in opts:
            opts.append(t)
    return opts


def resolve(text: str, ctx: _Context) -> Suggestion | Clarify | None:
    """Parse free text into a command suggestion, a clarifying question, or
    None (genuinely couldn't resolve it, fast or otherwise)."""
    verb = _verb_hit(text)
    if verb is None:
        # Milestone 2 (2026-08-24): the fast path only recognizes ~12
        # hardcoded verbs and fix/restart/rollback/open-pr targets -- it has
        # no idea Datadog, Grafana, PagerDuty, Snyk, Gitleaks, Azure, or GCP
        # exist. "what's wrong with our grafana alerts" landed here and
        # died with "I didn't get that", live, 2026-08-23. Route anything
        # the keyword table doesn't recognize through the same tool-calling
        # brain the diagnosis pipeline already uses, instead of adding verb
        # #13 by hand -- that's the whole reason this needed a second stage
        # instead of a bigger keyword table.
        return _resolve_via_llm(text, ctx)

    if verb == "watch":
        return Suggestion(["watch"], "watching the remembered namespace")
    if verb == "actions":
        return Suggestion(["actions"], "listing registered actions")
    if verb == "config":
        return Suggestion(["config"], "showing local config")
    if verb == "circuit":
        return Suggestion(["circuit", "status"], "showing circuit breaker state")
    if verb == "audit":
        return Suggestion(["audit", "--tail", "20"], "showing the latest audit entries")

    kind = _needs_target(verb)
    targets = _targets_in(text)
    target = _resolve_target(kind, targets, ctx)

    if kind == "repo" and not target:
        known = _known_options(ctx)
        return Clarify(
            f"Which repository should I {verb}? (e.g. `acme/widget`)",
            known,
        )
    if kind == "pod" and not target:
        known = _known_options(ctx)
        return Clarify(
            f"Which pod should I {verb}? (I know: {', '.join(known) or 'none yet — use `fix <ns>/<pod>` first'})",
            known,
        )

    if verb == "fix":
        return Suggestion(["fix", target], f"fixing {target}")
    if verb == "restart":
        return Suggestion(["run", "restart-pod", target], f"restarting {target}")
    if verb == "rollback":
        return Suggestion(["run", "rollback", target], f"rolling back {target}")
    if verb == "open-pr":
        return Suggestion(["run", "open-pr", target], f"opening a PR against {target}")
    if verb == "apply-ci-fix":
        return Suggestion(["fix", target, "--ci"], f"diagnosing + fixing CI on {target}")
    return None


def complete(verb: str, choice: str, ctx: _Context) -> Suggestion | None:
    """Turn a clarifying answer into a concrete suggestion. `choice` is the
    user's raw answer to a Clarify (a number picking a listed option, a bare
    pod name, or a qualified target)."""
    choice = choice.strip()
    if _TARGETISH.fullmatch(choice):
        target = choice
    elif _looks_like_bare_resource(choice):
        target = f"{ctx.namespace}/{choice}" if ctx.namespace else choice
    else:
        return None
    if verb == "fix":
        return Suggestion(["fix", target], f"fixing {target}")
    if verb == "restart":
        return Suggestion(["run", "restart-pod", target], f"restarting {target}")
    if verb == "rollback":
        return Suggestion(["run", "rollback", target], f"rolling back {target}")
    if verb == "open-pr":
        return Suggestion(["run", "open-pr", target], f"opening a PR against {target}")
    return None


# ── Milestone 2: LLM fallback (2026-08-24) ─────────────────────────────────
# Everything below only runs when the fast path above found no verb at all.

import logging  # noqa: E402

logger = logging.getLogger(__name__)

_LLM_INTENT_TOOL_NAME = "resolve_repl_intent"


def _build_intent_tool_schema() -> dict:
    """Built at call time from the real registries (prash/cli.py's PROVIDERS
    dict and the dispatcher's registered actions), not a second hand-written
    list -- the exact thing that let the fast-path table drift out of sync
    with 8 of 10 connectors in the first place. Imports are local: cli.py
    doesn't import this module, but keeping the dependency one-directional
    and deferred avoids ever having to think about it again."""
    from .cli import PROVIDERS, _build_dispatcher
    from .permissions import PermissionMode

    providers = sorted(PROVIDERS.keys()) + ["kubernetes"]
    dispatcher = _build_dispatcher(PermissionMode.ASK)
    action_lines = [
        f"  {aid} ({action.spec.risk_tier.value}): {action.spec.summary}"
        for aid, action in sorted(dispatcher.available.items())
    ]

    return {
        "name": _LLM_INTENT_TOOL_NAME,
        "description": (
            "Decide what a Prash user's free-text request maps to: reading "
            "a resource's state, diagnosing+fixing a Kubernetes pod or CI "
            "run, running one of the registered write actions below, one "
            "of the plain utility commands, or -- if genuinely too "
            "ambiguous to guess -- a clarifying question instead. Never "
            "guess a target that wasn't stated or previously established; "
            "ask instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": ["investigate", "fix", "run", "watch", "audit", "actions", "config", "circuit", "clarify"],
                    "description": (
                        "investigate = read-only state check on any provider. "
                        "fix = diagnose+propose a fix for a k8s pod (provider=kubernetes) "
                        "or a CI run (provider=github/gitlab). "
                        "run = execute one of the registered write actions below. "
                        "clarify = you cannot confidently resolve this -- ask instead."
                    ),
                },
                "provider": {
                    "type": "string",
                    "enum": providers,
                    "description": "which connector this targets. Required for investigate/fix. Omit for run/watch/audit/actions/config/circuit.",
                },
                "resource": {
                    "type": "string",
                    "description": (
                        "the target exactly as it should be typed on the command line: "
                        "a namespace/pod, an owner/repo, a monitor or alert name, a project, etc. "
                        "Only use a target the user actually said or that's already known from context -- never invent one."
                    ),
                },
                "action_id": {
                    "type": "string",
                    "description": "only when command=run: the exact action id from this registered list (never invent one):\n" + "\n".join(action_lines),
                },
                "minutes": {"type": "integer", "description": "only for mute/silence-style actions, if the user gave a duration"},
                "reason": {"type": "string", "description": "only for snyk-ignore-issue: the user's stated reason"},
                "deployment_id": {"type": "string", "description": "only for vercel-rollback/-redeploy, if the user gave one"},
                "explanation": {
                    "type": "string",
                    "description": "one short, plain sentence describing what you're about to do -- shown to the user before it runs.",
                },
                "clarify_question": {
                    "type": "string",
                    "description": "only when command=clarify: the specific question to ask the user.",
                },
            },
            "required": ["command", "explanation"],
        },
    }


_INTENT_SYSTEM_PROMPT = (
    "You are Prash's REPL intent resolver. A user typed a free-text line "
    "that didn't match any known short command. Call resolve_repl_intent "
    "with the single best interpretation. Be conservative: if the target "
    "resource isn't stated and isn't in the remembered context below, use "
    "command=clarify rather than guessing one. Never invent a provider, "
    "action id, or resource that wasn't given to you."
)


def _context_summary(ctx: _Context) -> str:
    known = _known_options(ctx)
    if not known:
        return "No remembered targets yet."
    return "Remembered from this session: " + ", ".join(known)


def _args_to_suggestion_or_clarify(args: dict) -> Suggestion | Clarify | None:
    command = args.get("command")
    explanation = args.get("explanation", "").strip() or "doing that"

    if command == "clarify":
        question = args.get("clarify_question", "").strip() or "Which resource should I target?"
        return Clarify(question)

    if command in ("watch", "audit", "actions", "config", "circuit"):
        argv = {"watch": ["watch"], "audit": ["audit", "--tail", "20"],
                "actions": ["actions"], "config": ["config"],
                "circuit": ["circuit", "status"]}[command]
        return Suggestion(argv, explanation)

    resource = (args.get("resource") or "").strip()

    if command == "investigate":
        if not resource:
            return Clarify("Which resource should I investigate?")
        provider = args.get("provider") or "github"
        if provider == "kubernetes":
            return None  # investigate has no kubernetes provider today (a real, separate gap)
        return Suggestion(["investigate", resource, "--provider", provider], explanation)

    if command == "fix":
        if not resource:
            return Clarify("Which pod or repo should I fix?")
        provider = args.get("provider")
        if provider in ("github", "gitlab"):
            return Suggestion(["fix", resource, "--ci", "--provider", provider], explanation)
        return Suggestion(["fix", resource], explanation)

    if command == "run":
        action_id = (args.get("action_id") or "").strip()
        if not action_id or not resource:
            return Clarify(f"Run which action, on what? ({explanation})")
        argv = ["run", action_id, resource]
        if args.get("minutes") is not None:
            argv += ["--minutes", str(args["minutes"])]
        if args.get("reason"):
            argv += ["--reason", str(args["reason"])]
        if args.get("deployment_id"):
            argv += ["--deployment-id", str(args["deployment_id"])]
        return Suggestion(argv, explanation)

    return None


async def _call_llm_intent(user_prompt: str) -> Suggestion | Clarify | None:
    from .brain.kimi_client import call_with_tool

    args = await call_with_tool(
        system_prompt=_INTENT_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        tool_schema=_build_intent_tool_schema(),
        call_type="repl_intent",
    )
    return _args_to_suggestion_or_clarify(args)


async def _resolve_via_llm_async(text: str, ctx: _Context) -> Suggestion | Clarify | None:
    return await _call_llm_intent(f'User said: "{text}"\n\n{_context_summary(ctx)}')


async def _resolve_clarify_answer_async(original_text: str, question: str, answer: str, ctx: _Context) -> Suggestion | Clarify | None:
    return await _call_llm_intent(
        f'User said: "{original_text}"\n'
        f'You asked: "{question}"\n'
        f'User answered: "{answer}"\n\n'
        f"{_context_summary(ctx)}\n\n"
        "You now have enough information to resolve this fully -- do not ask another clarifying question unless the answer was itself unusable."
    )


# call_with_tool's retry chain (DeepSeek -> Kimi -> Kimi retry -> DeepSeek
# fallback, each with their own internal retries and `asyncio.sleep(5)`
# backoffs on transient errors) is right for a CI diagnosis a human is
# already waiting minutes for. It is NOT right for an interactive REPL
# prompt -- found live, 2026-08-24: an unmocked call in the test suite sat
# for 40+ seconds with the worker's CPU time never advancing (asleep in a
# retry backoff, not stuck). A REPL fallback needs to fail fast and say so,
# not silently run a multi-attempt chain a person is sitting at a prompt
# waiting on.
_LLM_INTENT_TIMEOUT_SECONDS = 12


def _run_llm_intent_sync(coro) -> Suggestion | Clarify | None:
    """Sync bridge -- repl.py and tui.py's worker thread both call resolve()/
    complete_clarify() synchronously, and neither is already inside a
    running asyncio loop (run_repl is a plain blocking loop; tui.py's chat
    handler runs in a plain OS thread via @work(thread=True), not on
    Textual's event loop), so asyncio.run() here is safe. Degrades to None
    on any failure -- missing credentials, model/network trouble, a
    timeout, an unparseable response -- same honest contract as the fast
    path, never a crash or an indefinite hang mid-session."""
    try:
        return asyncio.run(asyncio.wait_for(coro, timeout=_LLM_INTENT_TIMEOUT_SECONDS))
    except TimeoutError:
        logger.warning(f"REPL intent LLM call timed out after {_LLM_INTENT_TIMEOUT_SECONDS}s")
        return None
    except Exception as exc:  # noqa: BLE001 — a bad LLM call must not kill the session
        logger.warning(f"REPL intent LLM call failed: {exc}")
        return None


def _resolve_via_llm(text: str, ctx: _Context) -> Suggestion | Clarify | None:
    return _run_llm_intent_sync(_resolve_via_llm_async(text, ctx))


def resolve_clarify_answer(original_text: str, question: str, answer: str, ctx: _Context) -> Suggestion | Clarify | None:
    """Completes an LLM-originated Clarify. The fast path's complete() only
    knows fix/restart/rollback/open-pr -- an LLM-sourced clarifying question
    (any command, e.g. investigate/run) had no way to receive its own
    answer and always failed with a generic "no targets known" message.
    Found live, 2026-08-25: asked "what's wrong with our grafana alerts"
    -> got a real clarifying question -> answering it just broke. Feeds the
    original text + question + answer back through the same brain rather
    than a second answer-parsing implementation."""
    return _run_llm_intent_sync(_resolve_clarify_answer_async(original_text, question, answer, ctx))