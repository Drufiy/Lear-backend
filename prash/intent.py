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
        None        -> not free-text intent at all; fall back to the argparse
                       parser (an exact command line always wins)

Every function here is pure (takes a small context object, returns a
decision) so stage 2 is unit-testable headlessly on all three OSes.
"""

from __future__ import annotations

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
    None (not intent — let the argparse parser handle it)."""
    verb = _verb_hit(text)
    if verb is None:
        return None

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