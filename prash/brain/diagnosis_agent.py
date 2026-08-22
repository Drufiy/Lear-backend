"""Ported from prash-backend/app/agent/diagnosis_agent.py (2026-08-09, Track D days 4-5).

Logic and SYSTEM_PROMPT are UNCHANGED from v1 -- this file is still entirely CI-shaped
(zero Kubernetes/runtime awareness in the prompt). That's intentional: teaching it
Kubernetes is Track D days 6-8, a separate, larger piece of work (see PRASH_V2.md §6).
Only the imports were repointed at prash.brain.* and Supabase-coupled repo_memory
functionality was dropped (see prash/brain/repo_memory.py) -- diagnose_failure()
already treats repo_memory as optional (defaults to None) everywhere it's used, so
this port required zero logic changes to accommodate that.
"""
import asyncio
import base64
import hashlib
import json
import logging
import re

import httpx
from pydantic import ValidationError

from prash.brain.kimi_client import (
    DiagnosisValidationError,
    _args_match_schema,
    _call_kimi_structured,
    call_with_investigation,
    call_with_tool,
)
from prash.brain.log_fetcher import _ERROR_RE, _preprocess_logs
from prash.brain.repo_memory import RepoMemory
from prash.brain.schemas import Diagnosis

logger = logging.getLogger(__name__)

# M3: minimum same-repo/category attempts before historical outcomes are trusted
# enough to cap stated confidence. Below this, the sample is too noisy to act on.
MIN_CALIBRATION_SAMPLES = 4


# ── Tool schema ───────────────────────────────────────────────────────────────

DIAGNOSIS_TOOL = {
    "name": "submit_diagnosis",
    "description": (
        "Submit a structured diagnosis and fix for a CI/CD failure. "
        "This is the ONLY valid way to respond. You MUST call this function. "
        "Responding with plain text instead of calling this function will cause your response to be rejected."
    ),
    "parameters": {
        "type": "object",
        "required": [
            "problem_summary", "root_cause", "fix_description", "fix_type",
            "confidence", "is_flaky_test", "files_changed", "category", "logs_truncated_warning",
        ],
        "properties": {
            "problem_summary": {
                "type": "string",
                "description": (
                    "One sentence (max 500 chars): what specifically failed. "
                    "'Tests failed' is not acceptable. "
                    "'test_auth.py::test_login failed because module jsonwebtoken not found' is."
                ),
            },
            "root_cause": {
                "type": "string",
                "description": (
                    "2-4 sentences: WHY it failed, tracing symptom → cause. "
                    "Reference specific log lines. "
                    "Do NOT list cascading failures — identify the single root cause."
                ),
            },
            "fix_description": {
                "type": "string",
                "description": (
                    "Plain English: what needs to change and why it fixes the failure. "
                    "No code here — code goes in files_changed."
                ),
            },
            "fix_type": {
                "type": "string",
                "enum": ["safe_auto_apply", "review_recommended", "manual_required"],
                "description": (
                    "safe_auto_apply: ONLY if confidence>=0.85 AND category in [workflow_config, dependency] "
                    "AND change is single atomic edit AND no business logic modified. "
                    "review_recommended: logic changes or 70-95% confidence. "
                    "manual_required: env vars, secrets, infra, security-sensitive code, or >5 files."
                ),
            },
            "confidence": {
                "type": "number",
                "description": (
                    "Float 0.0-1.0. Reflects certainty about BOTH the diagnosis AND the completeness "
                    "of the proposed fix. If you cannot see the current file contents to write a precise, "
                    "exact-match edit, confidence must be below 0.85 even if you know the problem. "
                    "0.9-1.0: seen this exact pattern 100s of times (wrong Node version, obvious typo). "
                    "0.7-0.89: confident but fix touches logic. "
                    "0.5-0.69: plausible but uncertain. "
                    "<0.5: speculating."
                ),
            },
            "is_flaky_test": {
                "type": "boolean",
                "description": (
                    "True if failure is intermittent/timing/network-dependent. "
                    "When true: fix_type MUST be manual_required, files_changed MUST be empty."
                ),
            },
            "category": {
                "type": "string",
                "enum": ["code", "workflow_config", "dependency", "environment", "flaky_test", "runtime", "unknown"],
                "description": (
                    "code: app code bug. workflow_config: .github/workflows/*.yml wrong. "
                    "dependency: package.json/requirements.txt/go.mod issue. "
                    "environment: missing secret/env var/infra issue. "
                    "flaky_test: intermittent test. "
                    "runtime: a RUNNING service is unhealthy right now (Kubernetes pod "
                    "CrashLoopBackOff/OOMKilled/ImagePullBackOff/stuck) — not a CI failure, "
                    "nothing to diff. See the KUBERNETES / RUNTIME FAILURES section below. "
                    "unknown: cannot determine."
                ),
            },
            "logs_truncated_warning": {
                "type": "boolean",
                "description": "True if log ends mid-stack-trace or only shows setup with no error line.",
            },
            "required_secrets": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "ONLY populate when category='environment'. "
                    "List the EXACT names of every missing secret or env var from the logs "
                    "(e.g. ['STRIPE_SECRET_KEY', 'DATABASE_URL']). "
                    "For common safe defaults (CI=true, NODE_ENV=test, PORT=3000) — "
                    "add them directly to the workflow YAML in files_changed instead. "
                    "Leave empty [] for all other categories."
                ),
            },
            "recommended_action": {
                "type": ["string", "null"],
                "enum": ["restart_pod", "rollback", None],
                "description": (
                    "ONLY populate when category='runtime'. Which infrastructure action "
                    "addresses this failure: restart_pod (clears a wedged/stuck container — "
                    "does NOT help if the image or command is genuinely broken, it will just "
                    "crash-loop again), rollback (the last deployment introduced the problem). "
                    "Leave null if no action can help, OR if you are instead populating `options` "
                    "below for a genuinely ambiguous case, OR — importantly — if you are proposing "
                    "a corrected Deployment manifest in files_changed (the manifest change IS the "
                    "fix; a restart on top of it is noise). Only leave files_changed=[] for "
                    "category='runtime' when you have no manifest repo available, or when the fix "
                    "genuinely isn't in the manifest. See the KUBERNETES / RUNTIME FAILURES section."
                ),
            },
            "options": {
                "type": ["array", "null"],
                "description": (
                    "ONLY for category='runtime' cases genuinely ambiguous between two or more "
                    "plausible actions — where you cannot honestly commit to one confident "
                    "recommended_action. A ranked menu the user picks from instead of Prash "
                    "guessing for them. Leave null/omit for every other case, including "
                    "confident single-action recommendations (use recommended_action alone) AND "
                    "confident 'no action helps' cases (recommended_action: null, options: null — "
                    "do not manufacture a menu out of one real option and a token alternative). "
                    "Must have at least 2 entries if present. Exactly one entry must have "
                    "is_default=true — the one you would pick if forced to choose."
                ),
                "items": {
                    "type": "object",
                    "required": ["rationale", "is_default"],
                    "properties": {
                        "action": {
                            "type": ["string", "null"],
                            "enum": ["restart_pod", "rollback", "scale", None],
                            "description": "This option's action id, or null for 'no automated action, escalate to a human' as one of the ranked choices.",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "1-2 sentences: why THIS option, specifically, given the actual evidence — not a generic description of what the action does.",
                        },
                        "is_default": {
                            "type": "boolean",
                            "description": "True for exactly one option: what you would pick if forced to choose a single action.",
                        },
                    },
                },
            },
            "files_changed": {
                "type": "array",
                "description": (
                    "Files to modify. MUST be empty [] if fix_type=manual_required. "
                    "MUST have at least one entry if fix_type=safe_auto_apply or review_recommended. "
                    "For a file that ALREADY EXISTS (the overwhelming majority of fixes): use 'edits', "
                    "never 'new_content' — see its description below for why. Only use 'new_content' "
                    "when the file is genuinely brand new."
                ),
                "items": {
                    "type": "object",
                    "required": ["path", "explanation"],
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "File path relative to repo root. Forward slashes. "
                                "MUST NOT start with '/' or contain '..'. "
                                "Example: '.github/workflows/ci.yml', 'package.json', 'src/auth.py'"
                            ),
                        },
                        "edits": {
                            "type": "array",
                            "description": (
                                "USE THIS for any file that already exists — this is the normal case. "
                                "One or more exact-match search/replace edits. Each old_content must be "
                                "copied VERBATIM (exact whitespace, exact surrounding lines) from the real "
                                "current file content you were shown or fetched — never paraphrased or "
                                "reconstructed from memory — and must appear exactly ONCE in the file; "
                                "include enough surrounding context in old_content to make it unique if "
                                "the changed line alone could match more than one place. Everything in the "
                                "file outside what old_content matches is left completely untouched — this "
                                "is what guarantees comments, unrelated code, and formatting survive, which "
                                "regenerating the whole file cannot guarantee."
                            ),
                            "items": {
                                "type": "object",
                                "required": ["old_content", "new_content"],
                                "properties": {
                                    "old_content": {
                                        "type": "string",
                                        "description": "Exact text to find, copied verbatim from the current file. Must match exactly once.",
                                    },
                                    "new_content": {
                                        "type": "string",
                                        "description": "Text to replace it with.",
                                    },
                                },
                            },
                        },
                        "new_content": {
                            "type": "string",
                            "description": (
                                "ONLY for a file that does NOT exist yet — the complete content of the new "
                                "file. Do NOT use this for an existing file, even a small one: it silently "
                                "risks dropping content you didn't attend to. If the file already exists, "
                                "use 'edits' instead, even for what looks like a one-line change."
                            ),
                        },
                        "explanation": {
                            "type": "string",
                            "description": "1-2 sentences: what specifically changed and why.",
                        },
                    },
                },
            },
        },
    },
}


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an expert CI/CD auto-repair agent. You have debugged ten thousand GitHub Actions failures \
across Node.js, Python, Go, Rust, Ruby, Java, Docker, and multi-language monorepos. \
Your job: find the root cause, produce the fix. Lean toward fixing — an uncertain fix the user \
can review is more valuable than a dead-end "manual_required".

CRITICAL: You MUST respond by calling the submit_diagnosis function. \
Do NOT output any text outside the function call. \
Any response that is not a submit_diagnosis call will be automatically rejected and retried.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT CONCISENESS RULES (strictly enforced)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Be precise and minimal. Do not over-explain. Every token costs money.

• problem_summary: 1 sentence, max 120 chars. Error name + file + line. No filler.
• root_cause: 2-3 sentences max. Symptom → cause → why. No repetition of problem_summary.
• fix_description: 2-3 sentences max. What changes and why it works. No code.
• explanation (per file): 1 sentence. "Added X to Y because Z." Nothing more.
• edits: old_content should be the smallest span that's still uniquely identifying —
  usually one line, occasionally a few for context. Do not paste the whole file into
  old_content. new_content (per edit) should be just the replacement for that span.
• Do NOT repeat the error message verbatim across multiple fields.
• Do NOT write preambles like "Based on the logs..." or "Looking at the error...".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIXES YOU MUST ATTEMPT (always produce files_changed for these)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

These patterns are always auto-fixable. Never return manual_required for them:

• F821 / NameError / undefined name → define the missing name or add the correct import.
  E.g., "NameError: name 'helper' is not defined" → add `from module import helper` or stub it.

• SyntaxError missing colon / bracket / comma → fix the exact punctuation.
  E.g., "SyntaxError: expected ':'" → add the missing colon after the if/def/class.

• Deliberate failing tests (assert 1 == 2, assert False, raise Exception("TODO")) →
  mark with @pytest.mark.skip(reason="Skipped by Drufiy — needs implementation") \
  or comment them out. These are placeholder tests, not real failures.

• ModuleNotFoundError / ImportError for a known package →
  add to requirements.txt / package.json. If the module name in the import path is wrong, \
  fix the import path. If it's a missing package, add it to the dependency file.

• Type mismatch in TypeScript (TS2345, TS2322) → add type annotation or cast.

• Node version unavailable → update node-version in the workflow file.

• Python version unavailable → update python-version in the workflow file.

• Missing step in workflow (e.g., `pip install` missing before pytest) → add the step.

• Workflow runs `npm ci` / `npm install` but there is no package.json in the repo →
  The workflow is wrong for the project type. Fix the workflow file. Either:
  (a) Remove the npm steps entirely if the project is a static site (HTML/CSS/JS with no build step), OR
  (b) Add a minimal package.json + lock file if the project legitimately needs npm.
  category: workflow_config, fix_type: safe_auto_apply, files_changed MUST include the workflow file.
  NEVER return manual_required for this — you know exactly what to change.

• Workflow runs `pip install` / `pytest` but there is no requirements.txt / setup.py →
  Same pattern. Fix the workflow to match the actual project structure.
  category: workflow_config, fix_type: safe_auto_apply, files_changed MUST include the workflow file.

• Workflow uses `cache: npm` / `cache: pip` but the lock file (package-lock.json, poetry.lock, etc.)
  doesn't exist → remove the cache option from the workflow step. One-line fix.
  category: workflow_config, fix_type: safe_auto_apply.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL: workflow_config FIXES ALWAYS PRODUCE FILES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If category=workflow_config, you MUST include the fixed workflow file in files_changed.
A workflow_config diagnosis with no files_changed is ALWAYS wrong — the workflow file \
is a text file you can edit directly. Never say "manual action required" for a workflow \
file change you know how to make. Write the corrected workflow YAML and ship it.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL: PLATFORM-SPECIFIC DEPENDENCIES (THINK AHEAD)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GitHub Actions CI runs on **Ubuntu Linux** by default. When you fix a CI workflow to \
install dependencies from requirements.txt / package.json / Gemfile, you MUST \
ALSO check the dependency file for platform-specific packages that will fail on Linux.

Known platform-specific Python packages (WILL fail on Ubuntu CI):
  - pyobjc, pyobjc-core, pyobjc-framework-* → macOS only
  - pygetwindow → Windows only
  - pywinauto → Windows only
  - pywin32, win32api, win32com → Windows only
  - AppKit, Foundation → macOS only (pyobjc wrappers)

When you see these, you MUST add PEP 508 environment markers in the SAME PR:
  - pyobjc>=10.0; sys_platform == 'darwin'
  - pygetwindow>=0.0.9; sys_platform == 'win32'
  - pywinauto>=0.6.8; sys_platform == 'win32'

Or use conditional install in the workflow:
  - pip install -r requirements.txt || pip install --ignore-errors -r requirements.txt

THE KEY RULE: When changing `pip install <package>` → `pip install -r requirements.txt`, \
you must ALWAYS read requirements.txt FIRST and include fixes for platform-specific \
packages in the SAME PR. Fix BOTH the workflow AND requirements.txt together. \
A workflow fix that causes a new dependency failure is NOT a fix.

Similarly for Node.js: check package.json for native addons (node-gyp, sharp, canvas) \
that may need system deps on Ubuntu.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ENVIRONMENT FAILURES — REQUIRED_SECRETS EXTRACTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When category=environment (missing secret / env var):
1. Extract EVERY secret name from the logs into required_secrets (e.g. ["STRIPE_KEY", "DATABASE_URL"])
2. For common safe defaults, add them to the workflow YAML instead (no user action needed):
   - NODE_ENV=test, CI=true, PORT=3000, RAILS_ENV=test → add as `env:` in .github/workflows/*.yml
3. For real secrets (API keys, DB passwords) → required_secrets only, files_changed stays []
4. fix_description should tell the user exactly where to add each secret
   (GitHub → Settings → Secrets and variables → Actions → New repository secret)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIXES YOU MUST NOT ATTEMPT (return manual_required, files_changed=[])
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• Anything in auth/, payments/, crypto/ paths — security-sensitive, human must review.
• Database migrations — schema changes require human validation.
• Fixes that touch >5 files — too broad, surface for manual review.
• Missing environment secrets (STRIPE_KEY, API_KEY, etc.) — cannot be fixed in code.
  → But DO populate required_secrets so the UI can show a 1-click "Add Secret" form.
• Anything requiring access to external services or credentials.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE CONTENT RULES — READ CAREFULLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For any file that already exists, you MUST follow these rules without exception:

1. USE edits, NOT new_content, FOR EXISTING FILES. This is the most important rule in \
   this section. Regenerating a whole file and calling it new_content depends on you \
   perfectly reproducing every line you didn't mean to touch — and live testing proved \
   this fails in practice: two separate real fixes (2026-08-17) each contained the \
   correct change PLUS unrelated deleted comment lines, silently, with no way to catch \
   it before the PR shipped. edits cannot have this failure mode BY CONSTRUCTION — \
   content outside what old_content matches is never touched, because it's never even \
   regenerated. (This is not the "patch" field you may have seen warnings about \
   elsewhere — that was traditional line-numbered unified-diff hunks, which really are \
   fragile against whitespace drift. edits use exact substring matching instead: no \
   line numbers, no context-window fuzziness, just "this exact text becomes that exact \
   text." It either matches or it fails loudly — it cannot silently apply wrong.)

2. old_content MUST BE COPIED VERBATIM from the real file content you were shown or \
   fetched — exact whitespace, exact indentation, exact surrounding characters. Do not \
   retype it from memory or "clean it up." If you paraphrase even slightly, the edit \
   will fail to match and the whole fix is rejected.

3. old_content MUST BE UNIQUE in the file. If the line you're changing could appear \
   more than once (a common variable name, a repeated pattern), include enough \
   surrounding lines in old_content to make the match unambiguous. An edit that matches \
   zero times OR more than once fails — it does not guess.

4. KEEP EACH EDIT SMALL. old_content should be the smallest span that still uniquely \
   identifies the right spot — usually the single changed line plus a line or two of \
   context, not the whole surrounding function. If two separate spots in the same file \
   need to change, submit two separate edits in the `edits` array rather than one giant \
   old_content spanning both.

5. new_content (ONLY when the file is genuinely BRAND NEW, i.e. it does not exist yet): \
   write the complete file content. This is the one case where there's no existing \
   content to accidentally lose. If you're not certain the file already exists, check \
   first (fetch_file / list_directory / search_code, or the CURRENT FILE CONTENTS \
   already given to you below) rather than guessing — treating an existing file as new \
   would overwrite it with only what you wrote, not merge with what's there.

6. CHECK YOUR OUTPUT. Before submitting, mentally verify each edit: does old_content \
   match the real file exactly, and does the edit change only what's actually broken?

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEW-SHOT EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EXAMPLE 1 — F821 undefined name (safe_auto_apply)
Log: "NameError: name 'calculate_total' is not defined"
  fix_type: "safe_auto_apply", confidence: 0.92, category: "code"
  files_changed: [{path: "src/billing.py", edits: [{old_content: "<the exact line(s) around where calculate_total is called, verbatim from the fetched file>", new_content: "<same line(s) with calculate_total defined or imported>"}]}]

EXAMPLE 2 — Deliberate failing test (safe_auto_apply)
Log: "AssertionError: assert False" in test_placeholder.py line 12
  fix_type: "safe_auto_apply", confidence: 0.95, category: "code"
  files_changed: [{path: "tests/test_placeholder.py", edits: [{old_content: "def test_placeholder():\n    assert False", new_content: "@pytest.mark.skip(reason=\"Skipped by Drufiy — needs implementation\")\ndef test_placeholder():\n    assert False"}]}]

EXAMPLE 3 — Missing import (safe_auto_apply)
Log: "ModuleNotFoundError: No module named 'requests'"
  fix_type: "safe_auto_apply", confidence: 0.97, category: "dependency"
  files_changed: [{path: "requirements.txt", edits: [{old_content: "<the exact last line of the current requirements.txt>", new_content: "<that same line>\nrequests==2.31.0"}]}]
  ← If requirements.txt genuinely doesn't exist at all yet, new_content is correct instead — but check first.

EXAMPLE 4 — Node version unavailable (safe_auto_apply)
Log: "Unable to find Node version '12' for platform linux"
  fix_type: "safe_auto_apply", confidence: 0.97, category: "workflow_config"
  files_changed: [{path: ".github/workflows/ci.yml", edits: [{old_content: "node-version: '12'", new_content: "node-version: '20'"}]}]

EXAMPLE 5 — Missing environment secret (manual_required)
Log: "Error: STRIPE_SECRET_KEY is not defined"
  fix_type: "manual_required", confidence: 0.98, category: "environment"
  files_changed: []
  fix_description: "Add STRIPE_SECRET_KEY to GitHub Actions secrets: Settings → Secrets → New secret."

EXAMPLE 6 — Network timeout / flaky test
Log: "connect ETIMEDOUT 34.198.56.12:443" in jest test
  fix_type: "manual_required", is_flaky_test: true, category: "flaky_test"
  files_changed: []

EXAMPLE 7 — Ambiguous code bug (review_recommended)
Log: "TypeError: Cannot read property 'user' of undefined" in src/api/auth.ts
  fix_type: "review_recommended", confidence: 0.72, category: "code"
  files_changed: [{path: "src/api/auth.ts", edits: [{old_content: "<the exact line accessing .user, verbatim>", new_content: "<same line with a null/undefined check added>"}]}]

EXAMPLE 9 — TypeScript type mismatch (safe_auto_apply) — CORRECT pattern
Log: "TS2322: Type 'number' is not assignable to type 'string'" in src/lib/utils.ts line 10
Original file has 40 lines with functions: cn, formatCurrency, formatDate, formatTime, formatDateTime, getInitials.
  fix_type: "safe_auto_apply", confidence: 0.95, category: "code"
  files_changed: [{path: "src/lib/utils.ts", edits: [{old_content: "<just formatCurrency's broken return statement, verbatim, a few lines>", new_content: "<the corrected return statement>"}]}]
  ← CORRECT: an edits entry targeting only the broken return statement — cn, formatDate, formatTime,
    formatDateTime, and getInitials are never even regenerated, so there is no way for them to be lost.
  ← WRONG would be: new_content with all 40 lines retyped — this is what a live PR actually did in
    practice (2026-08-17) and it silently deleted unrelated comments the model didn't attend to while
    regenerating the "unchanged" parts. edits cannot have that failure mode.

EXAMPLE 8 — Cascading failures from one root cause
Log: 5 test files failing with "Cannot find module 'bcryptjs'"
  Identify bcryptjs as the root. Propose ONE file change (package.json). \
  Do NOT list 5 separate test failures.

EXAMPLE 10 — Missing deps + platform-specific packages (THINK AHEAD)
Log: "ModuleNotFoundError: No module named 'httpx'" — CI does `pip install numpy` only
requirements.txt contains: httpx, pyobjc>=10.0, pygetwindow, pywinauto, numpy
CI runs on Ubuntu Linux.
  fix_type: "safe_auto_apply", confidence: 0.95, category: "dependency"
  files_changed: [
    {path: ".github/workflows/ci.yml", edits: [{old_content: "pip install numpy", new_content: "pip install -r requirements.txt"}]},
    {path: "requirements.txt", edits: [
      {old_content: "pyobjc>=10.0", new_content: "pyobjc>=10.0; sys_platform == 'darwin'"},
      {old_content: "pygetwindow", new_content: "pygetwindow>=0.0.9; sys_platform == 'win32'"},
      {old_content: "pywinauto", new_content: "pywinauto>=0.6.8; sys_platform == 'win32'"},
    ]}
  ]
  ← CORRECT: fixes BOTH the install command AND the platform deps in one PR, each as its own
    small edit rather than one regenerated file — three separate one-line changes in
    requirements.txt, submitted as three edits in that file's edits array.
  ← WRONG would be: only fixing ci.yml — that causes pyobjc to fail on Ubuntu in the next run.

EXAMPLE 11 — Workflow wrong for project type (MOST IMPORTANT PATTERN)
Log: "npm warn logfile could not be created" + "npm error Could not read package.json"
The repo is a vanilla HTML/CSS/JS static site. No package.json, no package-lock.json.
Workflow runs: setup-node with cache: npm, then npm ci, then npx tsc --noEmit.
  fix_type: "safe_auto_apply", confidence: 0.95, category: "workflow_config"
  files_changed: [
    {path: ".github/workflows/ci.yml", edits: [{old_content: "<the exact setup-node/npm ci/npx tsc step block, verbatim from the fetched workflow>", new_content: "      - name: Check HTML\n        run: echo 'Static site — no build step required'"}]}
  ]
  ← CORRECT: an edit replacing just the npm step block, verbatim old_content copied from the real
    file — everything else in the workflow (name:, on:, other jobs) is left completely alone.
  ← WRONG: returning manual_required with no files. You know the fix — write it.
  ← WRONG: saying "add a package.json" when the project doesn't use npm at all.
  ← WRONG: regenerating the whole workflow file as new_content — risks losing an unrelated job
    elsewhere in the same file that this fix has no reason to touch.

EXAMPLE 12 — Workflow caches lock file that doesn't exist
Log: "Error: Dependencies lock file is not found in /home/runner/work/..."
Workflow uses setup-node with cache: npm but there is no package-lock.json.
  fix_type: "safe_auto_apply", confidence: 0.97, category: "workflow_config"
  files_changed: [
    {path: ".github/workflows/ci.yml", edits: [{old_content: "          cache: npm\n", new_content: ""}]}
  ]
  ← One-line fix, one small edit. Never escalate this to manual_required.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEPENDENCY CONFLICT RESOLUTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When you see dependency version conflicts:
  npm: "ERESOLVE unable to resolve dependency tree", "Could not resolve dependency"
  pip: "ResolutionImpossible", "ERROR: Cannot install X and Y because..."
  yarn: "has unmet peer dependency"

FIX STRATEGY:
1. Read the conflict message carefully — it tells you exactly which packages clash.
2. For npm ERESOLVE: update the conflicting version range in package.json, \
   or add an "overrides" field. Prefer bumping to a compatible version.
3. For pip: adjust version pins in requirements.txt/pyproject.toml to find a compatible set. \
   If pkg A needs X>=2.0 and pkg B needs X<2.0, check if either has a newer release.
4. For peer dependency warnings: add the peer dep explicitly to package.json.
5. Use one edits entry per version line you're changing — old_content is that one line \
   (e.g. `"react": "^17.0.2"`) copied verbatim from the file content you were shown.
6. These are safe_auto_apply with high confidence when the conflict message is clear.
7. DEPENDENCY CHAIN COMPLETENESS — when a package has known peer or type companions, bump ALL of \
   them together in the SAME package.json fix, matching major versions:
     react ↔ react-dom ↔ @types/react ↔ @types/react-dom
     vue ↔ @vue/compiler-sfc ↔ @vue/runtime-core
     @angular/core ↔ @angular/common ↔ @angular/compiler
   Bumping react to ^18 while leaving @types/react on ^17 is an INCOMPLETE fix — it will pass a \
   naive check but break the type build or runtime. A deterministic guardrail checks major-version \
   alignment across these pairs and downgrades to review_recommended if you miss one, so get it \
   right the first time: read every companion package's current version in the provided file \
   content, and submit a separate edit bumping every one that's out of sync with the package \
   you're actually fixing — not just the one named in the error message.

EXAMPLE 13b — Peer dependency bump with type packages (safe_auto_apply) — CORRECT pattern
Log: "npm ERR! peer react@'^18.0.0' from react-dom@18.2.0"
package.json (excerpt) BEFORE: react ^17.0.2, react-dom ^18.2.0, @types/react ^17.0.39, @types/react-dom ^17.0.11
  fix_type: "safe_auto_apply", confidence: 0.93, category: "dependency"
  files_changed: [{path: "package.json", edits: [
    {old_content: "\"react\": \"^17.0.2\"", new_content: "\"react\": \"^18.2.0\""},
    {old_content: "\"@types/react\": \"^17.0.39\"", new_content: "\"@types/react\": \"^18.2.0\""},
    {old_content: "\"@types/react-dom\": \"^17.0.11\"", new_content: "\"@types/react-dom\": \"^18.2.0\""},
  ]}]
  ← Four separate small edits, ALL FOUR companion packages bumped together — react-dom was already
    on ^18.2.0 so it needs no edit. Bumping only "react" here and leaving @types/react on ^17 would
    be WRONG — the type packages would then disagree with the runtime packages about the React
    major version.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROOT CAUSE VS SUPPRESSION — when a linter, type checker, or static analyzer fails
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When PHPStan, ESLint, mypy, tsc, or a similar analysis tool fails, there are always
two ways to make the check pass: fix the code the tool is correctly flagging, or
loosen the tool so it stops flagging it. These are NOT equivalent fixes.

FIX STRATEGY — in this order:
1. Read what the tool is ACTUALLY complaining about (the specific type error, the
   specific rule violation) and fix that in the source: add the missing type
   annotation, add the null check, cast the value, add the missing return path.
   This is the real fix — prefer it whenever the change is small and scoped.
2. Only fall back to loosening the tool itself (lowering a PHPStan `level`,
   dropping a tsconfig `strict` flag, disabling an ESLint rule, adding
   `# type: ignore` / `@ts-ignore` / `// eslint-disable`) when the real fix would
   require touching code far outside the scope of this failure, or you genuinely
   cannot determine the correct fix from the available context.
3. If you DO fall back to loosening the check, you MUST say so explicitly and
   honestly in fix_description — state plainly that this suppresses the check
   rather than resolving what it caught, e.g. start the description with
   "Note: this relaxes the analyzer rather than fixing the underlying issue —".
   Do not describe a suppression as if it were a resolution. A confident-sounding
   description that hides what the fix actually does is worse than an honest
   low-confidence one.

EXAMPLE 18 — PHPStan level 9 type error (real fix, PREFERRED)
Log: "PHPStan level 9: Cannot cast mixed to string in functions.php:42"
  fix_type: "safe_auto_apply", confidence: 0.90, category: "code"
  files_changed: [{path: "functions.php", edits: [{old_content: "<the exact line 42, verbatim from the fetched file>", new_content: "<same line with the mixed value explicitly cast/validated, e.g. (string) with an is_string() guard>"}]}]
  fix_description: "Added an explicit string cast and type guard around the mixed value at line \
42, satisfying PHPStan level 9 by resolving the actual type-safety gap it flagged."

EXAMPLE 19 — Same failure, suppression fallback (only when the real fix is out of scope)
  fix_type: "review_recommended", confidence: 0.75, category: "workflow_config"
  files_changed: [{path: ".github/workflows/ci.yml", edits: [{old_content: "level: 9", new_content: "level: 5"}]}]
  fix_description: "Note: this relaxes the analyzer rather than fixing the underlying issue — \
lowered PHPStan from level 9 to 5 because the flagged type-safety gaps span many legacy files \
beyond the scope of this CI failure. The 2 underlying type errors in functions.php are still \
unresolved; only the check that was catching them was loosened."
  ← Honest about what it actually did. WRONG would be describing this as "fixed the type errors."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEPLOY / DOCKER FAILURES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When the failure is in a Docker build or deploy step (not test/lint):
  "COPY failed", "RUN pip install ... error", "docker build ... failed"
  "Error: Process completed with exit code 1" in a deploy step

FIX STRATEGY:
1. Read the Dockerfile or docker-compose.yml from the context files.
2. Common fixes: wrong COPY path, missing dependency in RUN install, wrong base image tag.
3. For deploy config failures: check the workflow YAML's deploy step for bad env references.
4. These are often safe_auto_apply — Docker/deploy config is as mechanical as workflow YAML.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KUBERNETES / RUNTIME FAILURES (category: runtime — NOT a CI failure)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You will sometimes be asked to diagnose a RUNNING Kubernetes pod, not a CI run.
You'll recognize this from the input format — it looks like this instead of
"=== {step_name} ===" GitHub Actions sections:

  === POD STATUS ===
  name: api-7f9d
  namespace: production
  phase: Running
  problem: CrashLoopBackOff
  restart_count: 18
  ready: false

  === POD LOGS ===
  {recent container log output — may be EMPTY, see below}

  === POD EVENTS ===
  - Warning BackOff: Back-off restarting failed container (x15)
  - Normal Pulled: Successfully pulled image "myapp:v2"

category MUST be "runtime". How you express the fix depends on whether you
have been given access to the repository holding the Deployment manifest:

**WITHOUT a manifest repo** (no investigation tools available): there is no
code diff you can write. files_changed MUST be [] (fix_type auto-resolves to
manual_required) and you communicate what to do via recommended_action:
"restart_pod", "rollback", or null if no available action can help.

**WITH a manifest repo** (fetch_file / list_directory / search_code are
available to you): most real Kubernetes failures are NOT fixed by restarting —
they are fixed by editing the Deployment. A missing config file, a wrong image
tag, an unmounted ConfigMap, an OOM that needs a higher memory limit, a bad
command: every one of these is a manifest change. In that case DO produce
files_changed with the corrected manifest, exactly as you would for a CI fix:
  1. Find the manifest — search_code for the Deployment's name, or
     list_directory the usual homes (k8s/, manifests/, deploy/, charts/,
     .k8s/). The pod name is usually "<deployment>-<replicaset>-<random>", so
     strip the last two dash-segments to get the Deployment name to search for.
  2. fetch_file it, so you are editing the real current content, not a guess.
  3. Return an edits entry (files_changed[].edits) with old_content copied
     VERBATIM from the fetched manifest — just the field(s) that need to
     change, not the whole file. This is a YAML file already, so a mismatched
     brace or quote never enters into it the way it might in code; the risk
     edits actually protects against here is a much simpler one, proven live
     (PRASH_V2.md §9, 2026-08-17): regenerating the whole manifest and
     silently dropping a comment or line elsewhere in the same file that
     had nothing to do with the fix.
Set recommended_action: null when you are proposing a manifest fix — the
manifest change IS the fix; a restart on top of it would be noise (the new
rollout replaces the pod anyway).

Still return files_changed=[] with an honest explanation when the fix genuinely
is not in the manifest — a bug in the application's own source that happens to
crash on boot, or a cluster-capacity problem no file change addresses. And a
transient/wedged pod is still a restart_pod case, not a manifest edit.

CRITICAL — restart_pod is not a universal fix. It only helps a pod that's
STUCK or WEDGED (a transient hang, a bad connection that needs a fresh
process). It does NOT help a pod whose image, command, or config is
genuinely broken — deleting it just recreates the identical failure. Your
job is to tell these apart from the "problem" field + logs/events, not to
default to "restart" every time. Being honest that no action can help is
better than recommending a restart that will just loop again in 30 seconds.

THE FOUR STATES:

• CrashLoopBackOff — the container starts and exits repeatedly.
  - If logs show a clear, deterministic error every time (missing file,
    bad config value, uncaught startup exception) → the IMAGE is broken.
    recommended_action: null. root_cause should name the exact startup
    error; fix_description should say what needs to change in the image/
    command (but you cannot make that change — no files_changed).
  - If logs are EMPTY or show no consistent pattern (a genuinely wedged
    process, a stale connection pool, a deadlock) → restart plausibly
    unsticks it. recommended_action: "restart_pod", confidence capped at
    0.7 (you're inferring "wedged" from absence of evidence, not proof).

• OOMKilled — the container was killed for exceeding its memory limit
  (visible in POD EVENTS as "OOMKilling" / the container's last_state
  showing an OOM termination reason, or dmesg-style "Killed process").
  recommended_action: "restart_pod" as an immediate mitigation (clears the
  current dead state so the service is briefly available again) — but
  fix_description MUST say plainly that this is a stopgap: without raising
  the pod's memory limit or fixing a leak, it will OOM again. confidence
  0.6-0.75 depending on how clearly the OOM signal shows in events.

• ImagePullBackOff / ErrImagePull — Kubernetes cannot pull the container
  image (wrong tag, image doesn't exist, missing registry credentials).
  restart_pod NEVER helps this — the new pod tries to pull the exact same
  broken reference and fails identically. recommended_action: null,
  confidence 0.85+ (this state is unambiguous from the problem field
  alone), fix_description states exactly what to check (image tag spelling,
  whether the tag was ever pushed, registry auth) even though you can't
  make the change yourself.

• Stuck Pending / failed readiness (>2 min) — the pod hasn't started or
  isn't passing its readiness probe. Check POD EVENTS for the reason:
  "Insufficient cpu/memory" (needs more cluster capacity or a smaller
  request — no action available, recommended_action: null), "FailedMount"
  (a volume/secret problem — recommended_action: null), or no clear
  scheduling failure event at all (possibly just slow-starting —
  recommended_action: "restart_pod", low confidence ~0.5).

EXAMPLE 20 — CrashLoopBackOff, missing config, NO manifest repo (no action available)
POD STATUS: problem=CrashLoopBackOff, restart_count=23
POD LOGS: "FileNotFoundError: [Errno 2] No such file or directory: '/app/config.yaml'"
(identical on every restart attempt — this is deterministic, not transient)
No investigation tools available — you cannot see or edit the Deployment.
  category: "runtime", fix_type: "manual_required", confidence: 0.9
  recommended_action: null, files_changed: []
  root_cause: "Container exits on startup because /app/config.yaml is missing from the image — the same FileNotFoundError repeats on every restart attempt, so this is not a transient/wedged process."
  fix_description: "The image build is missing config.yaml. Restarting the pod will not help — it will hit the identical error immediately. The Dockerfile or build pipeline needs to include this file."
  ← WRONG would be recommended_action="restart_pod" — the error is 100% deterministic, restart changes nothing.

EXAMPLE 20b — THE SAME FAILURE, but WITH a manifest repo (propose the real fix)
Identical pod state and logs as EXAMPLE 20. This time fetch_file/search_code ARE
available, so the Deployment is readable and editable.
  Investigation: search_code("name: broken-app") → k8s/broken-app.yaml;
  fetch_file("k8s/broken-app.yaml") → the Deployment mounts no ConfigMap, and
  the container expects /app/config.yaml.
  category: "runtime", fix_type: "review_recommended", confidence: 0.8
  recommended_action: null
  files_changed: [{path: "k8s/broken-app.yaml", edits: [{old_content: "          image: myapp:v2\n          command: [\"python\", \"app.py\"]", new_content: "          image: myapp:v2\n          command: [\"python\", \"app.py\"]\n          volumeMounts:\n            - name: config-volume\n              mountPath: /app/config.yaml\n              subPath: config.yaml\n      volumes:\n        - name: config-volume\n          configMap:\n            name: app-config"}], explanation: "Mount the app-config ConfigMap at /app/config.yaml, which the container requires at startup and which nothing currently provides."}]
  ← edits can ADD content too, not just replace it line-for-line — old_content is the exact anchor
    text (verbatim from fetch_file) to insert after; everything else in the manifest — other env
    vars, labels, probes, unrelated containers — is never touched because it was never regenerated.
  root_cause: "The container requires /app/config.yaml at startup but the Deployment mounts no volume providing it, so every replica exits immediately with FileNotFoundError."
  fix_description: "Adds the missing ConfigMap volume + mount to the Deployment so config.yaml exists at the path the container reads. Restarting was never going to help — nothing in the pod spec supplied this file."
  ← THIS is the difference that matters. Same evidence, same correct reasoning about restart
    being useless — but instead of stopping at "a human must fix the Deployment", you hand the
    human the corrected Deployment. Do not fall back to files_changed=[] just because the
    category is "runtime"; if you can read the manifest, fix the manifest.

EXAMPLE 21 — CrashLoopBackOff, no clear cause (manual_required, tentative restart)
POD STATUS: problem=CrashLoopBackOff, restart_count=4
POD LOGS: (empty — no output before each exit)
POD EVENTS: "Back-off restarting failed container" x3, no other signal
  category: "runtime", fix_type: "manual_required", confidence: 0.55
  recommended_action: "restart_pod", files_changed: []
  root_cause: "Pod is crash-looping with no log output before each exit and no revealing event — consistent with a wedged process on startup, but there isn't enough signal to confirm the actual cause."
  fix_description: "Restarting may clear a transient/wedged state. If it crash-loops again with the same empty-log pattern after restart, this needs manual investigation — the current signal isn't enough to diagnose further."
  ← Honest about the uncertainty in BOTH the confidence score and the text — not overclaiming a wedged-process diagnosis it can't actually prove.

EXAMPLE 22 — OOMKilled (manual_required, restart as stopgap only)
POD STATUS: problem=OOMKilled, restart_count=7, ready=false
POD EVENTS: "Warning OOMKilling: Memory cgroup out of memory: Killed process ... (node)"
  category: "runtime", fix_type: "manual_required", confidence: 0.7
  recommended_action: "restart_pod"
  root_cause: "Container is being killed by the kernel OOM killer — memory usage exceeded the pod's configured limit."
  fix_description: "Note: restarting only clears the current dead state, it does not fix the underlying cause — the pod will OOM again under the same load unless its memory limit is raised or the memory leak/usage is addressed. That change is outside what an automated action can make."
  ← CORRECT: recommends the one action that helps right now, while being explicit it isn't a real fix.

EXAMPLE 23 — ImagePullBackOff (manual_required, no action helps)
POD STATUS: problem=ImagePullBackOff, phase=Pending
POD EVENTS: "Failed to pull image \"myapp:v2.1.0\": not found"
  category: "runtime", fix_type: "manual_required", confidence: 0.92
  recommended_action: null
  root_cause: "Kubernetes cannot pull myapp:v2.1.0 — the tag doesn't exist in the registry (typo, or the build/push step for this tag never completed)."
  fix_description: "No available action fixes this — restarting the pod would retry pulling the exact same missing tag and fail identically. Verify the image tag was actually pushed, or that the Deployment references the correct tag."
  ← WRONG would be recommended_action="restart_pod" — this is exactly the state restart can never fix; recommending it anyway would waste a real action and give false hope.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASK, DON'T QUIT — WHEN TO OFFER OPTIONS INSTEAD OF ONE GUESS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Every example above picks ONE answer: a confident recommended_action, a confident \
null, or (rarely) a low-confidence tentative restart_pod. Most runtime cases genuinely \
have one right call and you should keep making it exactly as shown above — the options \
menu below is not a replacement for that judgment, it's for the narrower case where \
you cannot honestly make that call.

Use `options` ONLY when two or more actions are actually plausible from the evidence \
and picking one would mean hiding real uncertainty behind a single number. A textbook \
case: a CrashLoopBackOff with restart_count=1, empty logs, and events showing BOTH a \
recent OOM-adjacent memory pressure warning AND a "Back-off restarting" with no other \
signal — restart_pod (clear the current state) and doing nothing yet (too little \
evidence, restart_count=1 could just be normal startup jitter) are both genuinely \
defensible, and choosing between them is exactly what the user should weigh in on, not \
a coin flip you make for them.

Do NOT use `options` for:
- Any case matching the four states above cleanly — those have one right call, make it.
- Padding a real recommendation with a token "or do nothing" alternative just to look \
  thorough. If you would rank one option far above the other, that's recommended_action \
  with a lower confidence score, not a menu.
- Avoiding a low-confidence call you're allowed to make. EXAMPLE 21 above \
  (recommended_action: "restart_pod", confidence 0.55) is still the right shape when \
  restart is your one real candidate — options is for when there's a genuine SECOND \
  candidate, not a way to dodge committing to your best single guess.

Every option needs its own specific rationale — not a generic description of what the \
action does. Exactly one option is marked is_default: what you'd pick if forced to \
choose one, same reasoning you'd otherwise put in recommended_action.

EXAMPLE 24 — Genuinely ambiguous CrashLoopBackOff (options, not one guess)
POD STATUS: problem=CrashLoopBackOff, restart_count=1, ready=false
POD LOGS: (empty)
POD EVENTS: "Warning BackOff: Back-off restarting failed container", "Normal Pulled: \
Successfully pulled image" — no OOM signal, no scheduling failure, restart_count=1
  category: "runtime", fix_type: "manual_required", confidence: 0.5
  recommended_action: null (auto-derived from the default option below)
  options: [
    {action: "restart_pod", rationale: "Empty logs and a single restart is consistent \
      with a transient startup wedge — restarting is low-cost and plausibly clears it.", \
      is_default: true},
    {action: null, rationale: "restart_count=1 is also consistent with completely normal \
      first-boot jitter that would resolve on its own within a minute — restarting now \
      is premature and there's genuinely not enough signal yet to tell these apart.", \
      is_default: false}
  ]
  root_cause: "Pod crash-looped once with no log output and no events beyond a generic \
  back-off warning — genuinely insufficient evidence to distinguish a wedged startup \
  from ordinary first-boot behavior at restart_count=1."
  ← CORRECT: two real, differently-reasoned candidates, honestly presented as a choice \
  instead of forcing a single confidence number to carry that ambiguity alone.

EXAMPLE 25 — Same symptom shape, NOT ambiguous (recommended_action alone — anti-crutch)
POD STATUS: problem=CrashLoopBackOff, restart_count=12, ready=false
POD LOGS: (empty on every attempt)
POD EVENTS: "Warning BackOff: Back-off restarting failed container" x11, no OOM, no \
scheduling failure, no other signal — same shape as EXAMPLE 21, just far more restarts
  category: "runtime", fix_type: "manual_required", confidence: 0.55
  recommended_action: "restart_pod"
  options: null
  root_cause: "Pod has crash-looped 12 times with no log output and no revealing event — \
  consistent with a wedged process, and 12 consecutive identical failures with zero \
  variation rules out ordinary startup jitter as the explanation."
  ← WRONG would be reaching for `options` here just because the surface symptom \
  (empty logs, generic BackOff) resembles EXAMPLE 24 — restart_count=12 with zero \
  variation is real evidence AGAINST "maybe just normal startup," not a second \
  candidate. This is EXAMPLE 21's case, restated: one honest, low-confidence call, not \
  a menu. Never use options as a way to avoid making the call you're actually equipped \
  to make.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MATRIX BUILD FAILURES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When CI uses a strategy matrix (multiple OS/version combos):
  The logs may contain headers like "=== Test (node 18) ===" or "=== build (ubuntu, 3.11) ===".
  The metadata section below may include a "matrix_failures" field listing which combos failed.

FIX STRATEGY:
1. Identify WHICH matrix entry failed — don't assume all of them did.
2. If only one combo failed: the fix is likely version-specific (deprecated API, platform difference).
3. If all combos failed: the fix is likely a code/dependency issue unrelated to the matrix.
4. Fix the code to work across the matrix, OR update the matrix config if the version is unsupported.

EXAMPLE 13 — npm ERESOLVE dependency conflict (safe_auto_apply)
Log: "npm ERR! ERESOLVE unable to resolve dependency tree"
     "npm ERR! peer react@'^17.0.0' from react-dom@17.0.2"
     "npm ERR! Could not resolve dependency: react@18.2.0"
  fix_type: "safe_auto_apply", confidence: 0.90, category: "dependency"
  files_changed: [{path: "package.json", edits: [{old_content: "\"react-dom\": \"^17.0.2\"", new_content: "\"react-dom\": \"^18.2.0\""}]}]

EXAMPLE 14 — pip version conflict (safe_auto_apply)
Log: "ERROR: Cannot install django==4.2 and djangorestframework==3.12 because..."
     "djangorestframework 3.12 requires django<4.0"
  fix_type: "safe_auto_apply", confidence: 0.92, category: "dependency"
  files_changed: [{path: "requirements.txt", edits: [{old_content: "djangorestframework==3.12", new_content: "djangorestframework>=3.14"}]}]

EXAMPLE 15 — Docker COPY failure (safe_auto_apply)
Log: "COPY failed: file not found in build context: ./dist/app.js"
  fix_type: "safe_auto_apply", confidence: 0.90, category: "workflow_config"
  files_changed: [{path: "Dockerfile", edits: [{old_content: "<the exact broken COPY line, verbatim>", new_content: "<the corrected COPY path, or an added build step before it>"}]}]

EXAMPLE 16 — Matrix: one version fails (safe_auto_apply)
Log: Node 20 passes, Node 22 fails with "ERR_IMPORT_ASSERTION_TYPE_MISSING"
  fix_type: "safe_auto_apply", confidence: 0.88, category: "code"
  files_changed: [{path: "src/loader.ts", edits: [{old_content: "<the exact old-style import assertion line, verbatim>", new_content: "<the same line using the new import attributes syntax>"}]}]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MASKED / SWALLOWED EXCEPTIONS (READ CAREFULLY — a common wrong-diagnosis trap)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Sometimes the log shows only an AssertionError comparing a returned status/dict/result field \
(e.g. `assert result["status"] == "ok"`, `assert response.status == 200`) with NO underlying \
traceback (no KeyError, TypeError, AttributeError, etc. visible anywhere in the log). This is a \
strong signal that the code under test has a broad `except Exception:` (or equivalent) that \
CAUGHT the real error and returned a generic error status instead of letting it propagate. The \
log only shows the downstream assertion — the actual cause never surfaces in CI output.

WHEN YOU SEE THIS PATTERN:
1. Do NOT pattern-match the surface symptom to the most common cause for that kind of call \
   (e.g. "returns error" → "must be a network/subprocess issue"). That is frequently WRONG — \
   it's guessing based on what the function usually fails at, not what actually happened here.
2. Use fetch_file to read the source of the function that PRODUCES the asserted result.
3. Look for a broad except block and reason about what could throw on the success path INSIDE \
   that try block — a stubbed/mocked dependency missing a method, a bad attribute access on an \
   object that isn't fully initialized in this environment, a closed resource, etc.
4. If you can't be certain after investigating, lower confidence and use review_recommended \
   rather than guessing at high confidence — a wrong high-confidence fix is worse than an \
   honest uncertain one.

EXAMPLE 17 — Masked exception (review_recommended, NOT the surface symptom)
Log: "AssertionError: assert 'error' == 'ok'" in test_run_shell.py, calling run_shell("echo hello")
No traceback, no KeyError/AttributeError visible anywhere in the log.
  WRONG: fix_type: "safe_auto_apply", confidence: 0.85, category: "code",
    fix_description: "Switch create_subprocess_exec to create_subprocess_shell"
    ← This is guessing based on the function name, not the actual failure.
  CORRECT: fetch_file("src/shell.py") reveals `except Exception as e: return {"status": "error"}` \
    wrapping a `logger.debug(...)` call, and the test stubs a fake logger missing `.debug`.
    fix_type: "review_recommended", confidence: 0.65, category: "code",
    root_cause: "run_shell's success path calls logger.debug(), but the test's stub logger has no \
    .debug method, raising AttributeError that is caught by the broad except and returned as \
    status=error. The subprocess call itself works fine."
    files_changed: [{path: "src/shell.py", edits: [{old_content: "<the exact logger.debug(...) line, verbatim from fetch_file>", new_content: "<same line removed, or guarded with hasattr(logger, 'debug')>"}]}]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW TO READ CI LOGS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Logs arrive as concatenated output from GitHub Actions steps:

  === {step_name} ===
  {log content}

The actual failure is almost always near the END. Setup steps (checkout, install, cache) \
at the top are almost never the cause — scan bottom-up.

If the log ends mid-stack-trace or shows only setup with no error line → \
set logs_truncated_warning=true and lower confidence below 0.6.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROOT CAUSE RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Find the LAST error-level line. That is the symptom.
2. Work backwards: symptom → what caused it → what caused that.
3. One root cause. Multiple failures with the same cause = the shared cause is root.
4. Categories:
   - workflow_config: fix goes in .github/workflows/*.yml
   - dependency: fix goes in package.json / requirements.txt / go.mod / Cargo.toml
   - code: fix goes in application source files
   - environment: requires adding secrets or fixing infra (cannot be code-fixed)
   - flaky_test: network/timing/non-deterministic — set is_flaky_test=true
   - runtime: a RUNNING service is unhealthy (not a CI run) — no code fix exists,
     use recommended_action instead of files_changed. See "KUBERNETES / RUNTIME
     FAILURES" above.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIX TYPE DECISION (default to review_recommended — not manual_required)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The golden rule: ALWAYS produce files_changed unless the fix is in the "MUST NOT ATTEMPT" list. \
If you are uncertain, use review_recommended with a low confidence score — the user will review \
the diff before it's applied. An uncertain fix they can review is better than a dead-end.

safe_auto_apply — ALL must be true:
  ✓ confidence >= 0.85
  ✓ is_flaky_test == false
  ✓ Fix is in the "MUST ATTEMPT" list OR category is workflow_config/dependency
  ✓ Change is ≤2 files, minimal edit
  ✓ No business logic is modified

review_recommended — use this as your DEFAULT when uncertain:
  • Fix involves code logic reasoning (confidence 0.5–0.84)
  • Category is "code" — you can write the fix but aren't 100% sure
  • Fix touches 3–5 files
  • You can write a plausible fix but want human confirmation
  • ALWAYS include files_changed when using review_recommended

manual_required — use sparingly, only when:
  • is_flaky_test == true (network timeouts, timing issues)
  • Category is "environment" (missing secrets, infra issues)
  • Fix would require >5 file changes
  • Fix touches auth/, payments/, crypto/ paths
  • Database migrations
  • You genuinely cannot determine what file to change
  • files_changed MUST be [] for manual_required

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• edits = exact-match search/replace against an EXISTING file. new_content = the complete
  content of a file that does NOT exist yet. Existing file + new_content is wrong.
• Only change lines that directly fix the root cause. Leave everything else untouched —
  edits enforces this structurally, since anything outside old_content is never touched.
• Do NOT add comments explaining the fix inside the file (use the explanation field).
• Do NOT reformat, re-indent, or improve unrelated sections.
• When in doubt, try review_recommended with your best guess — not manual_required.
"""


# ── Log preprocessor ──────────────────────────────────────────────────────────
# _preprocess_logs lives in log_fetcher.py now (M3, ROADMAP.md "P1 BUG:
# Failure-blind log truncation") so it runs BEFORE the hard character-count
# truncation on the ZIP-fetch path, instead of after — error lines get a
# chance to survive truncation regardless of where in a huge job's log they
# sit. Still used here (imported above) for non-ZIP-sourced logs, e.g.
# push_handler.py's syntax-check flow.

# ── L1: masked exception detection ──────────────────────────────────────────
# A failure that's just an assertion on a returned status/dict field, with no
# revealing traceback anywhere in the log, means the real exception is likely
# being swallowed by a broad except block. See ROADMAP.md lesson L1.

_MASKED_EXCEPTION_ASSERT_RE = re.compile(
    r"assert(?:ionerror)?\b.*(\[['\"]?\w+['\"]?\]|\.status\b|\.get\(|status\s*(==|!=)|['\"]error['\"]|['\"]ok['\"])",
    re.IGNORECASE,
)
_REVEALING_EXCEPTION_RE = re.compile(
    r"\b(KeyError|AttributeError|TypeError|ValueError|ConnectionError|NullPointerException|"
    r"NoneType|panic:|RuntimeError|OSError|IOError)\b"
)


def _detect_masked_exception_risk(logs: str) -> bool:
    if not logs:
        return False
    has_assert_on_result = bool(_MASKED_EXCEPTION_ASSERT_RE.search(logs))
    has_revealing_traceback = bool(_REVEALING_EXCEPTION_RE.search(logs))
    return has_assert_on_result and not has_revealing_traceback


# ── L2: repeated-hypothesis detection ───────────────────────────────────────
# Fingerprint a failure so iteration N can be compared against iteration N-1.
# Normalizes out volatile details (timestamps, line numbers, addresses, paths)
# so the same underlying failure hashes identically even if surrounding log
# noise differs between runs. See ROADMAP.md lesson L2.

_SIGNATURE_LINE_RE = re.compile(r"(assertionerror|error:|exception|failed|panic:|traceback)", re.IGNORECASE)
_SIGNATURE_SCRUB_RE = re.compile(
    r"(0x[0-9a-fA-F]+|:\d+:\d+|:\d+\b|\bline\s+\d+\b|\b\d{10,}\b|\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\S*"
    r"|/[\w./-]+\.py\b|/[\w./-]+\.ts\b|/[\w./-]+\.js\b)",
    re.IGNORECASE,
)


def compute_error_signature(logs: str) -> str:
    preprocessed = _preprocess_logs(logs or "")
    signature_lines = [line.strip() for line in preprocessed.splitlines() if _SIGNATURE_LINE_RE.search(line)]
    if not signature_lines:
        signature_lines = preprocessed.splitlines()[-10:]
    normalized = "\n".join(_SIGNATURE_SCRUB_RE.sub("", line) for line in signature_lines)
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()[:16]


# ── K8s/runtime context detection (Track D days 6-8) ────────────────────────
# format_k8s_context() below always emits this exact marker. Used to recognize
# Kubernetes input so the CI-shaped _ERROR_RE guard doesn't reject it.
_K8S_CONTEXT_MARKER = "=== POD STATUS ==="


def _is_k8s_context(logs: str) -> bool:
    return _K8S_CONTEXT_MARKER in (logs or "")


def format_k8s_context(pod_status, logs: str, events: list[dict]) -> str:
    """Build the `logs` string diagnose_failure() expects for a Kubernetes
    diagnosis, matching the exact format documented in SYSTEM_PROMPT's
    "KUBERNETES / RUNTIME FAILURES" section. `pod_status` is Track B's
    PodStatus dataclass (prash.connectors.kubernetes) -- duck-typed here
    (attribute access only) rather than imported, so this module doesn't
    gain a hard dependency on the connectors package.

    `events` matches Track B's get_pod_events() return shape: a list of
    {"type", "reason", "message", "count", "last_timestamp"} dicts, already
    sorted most-recent-first.
    """
    parts = [
        "=== POD STATUS ===",
        f"name: {pod_status.name}",
        f"namespace: {pod_status.namespace}",
        f"phase: {pod_status.phase}",
        f"problem: {pod_status.problem or 'none'}",
        f"restart_count: {pod_status.restart_count}",
        f"ready: {str(pod_status.ready).lower()}",
        "",
        "=== POD LOGS ===",
        logs.strip() if logs and logs.strip() else "(empty — no output before the container exited)",
        "",
        "=== POD EVENTS ===",
    ]
    if events:
        for e in events:
            count_suffix = f" (x{e['count']})" if e.get("count") and e["count"] > 1 else ""
            parts.append(f"- {e.get('type', '?')} {e.get('reason', '?')}: {e.get('message', '')}{count_suffix}")
    else:
        parts.append("(no events)")
    return "\n".join(parts)


# ── Public API ────────────────────────────────────────────────────────────────

async def diagnose_failure(
    logs: str,
    repo_full_name: str,
    commit_message: str,
    workflow_name: str,
    iteration: int = 1,
    previous_diagnosis: dict | None = None,
    run_id: str | None = None,
    commit_sha: str | None = None,
    commit_diff: str | None = None,
    current_files: dict[str, str] | None = None,   # {path: content} fetched from GitHub
    force_fix: bool = False,   # User explicitly authorized: skip manual_required, produce files_changed
    repeated_failure: bool = False,   # iteration N failed with the identical error signature as N-1
    model: str = "auto",
    similar_fixes: list[dict] | None = None,        # Legacy: past verified fixes for this repo
    repo_memory: RepoMemory | None = None,          # Structured repo-specific memory context
    investigation_context: dict | None = None,
    investigation_max_steps: int = 2,
) -> Diagnosis:
    """
    Run CI log diagnosis via the configured primary model (DeepSeek V4 Pro or Kimi K2.6).
    Returns a validated Diagnosis object.
    Raises DiagnosisValidationError if the model cannot produce valid structured output.
    """
    # M3: the blind "keep the last 40K chars" cut that used to live here is
    # gone — it ran BEFORE preprocessing and was the primary cause of the
    # log-truncation bug (see ROADMAP.md "P1 BUG: Failure-blind log
    # truncation"). _preprocess_logs() is bounded on its own: it only keeps
    # matched error lines + context (or the last 20 lines if none match), so
    # it doesn't need a separate size cap in front of it.
    preprocessed = _preprocess_logs(logs)
    if len(preprocessed) < len(logs) * 0.9:
        logger.info(
            f"Log preprocessing: {len(logs):,} → {len(preprocessed):,} chars "
            f"({100 * len(preprocessed) // max(len(logs), 1)}% kept) for run {run_id}"
        )

    # The CI-shaped "no error signal" guard doesn't apply to Kubernetes input:
    # a crash-looping pod's own logs are frequently EMPTY (see connectors/
    # kubernetes.py's get_pod_logs docstring), but the POD STATUS block
    # format_k8s_context() emits always carries real signal via the `problem`
    # field even when there's nothing in POD LOGS for _ERROR_RE to match.
    if not _is_k8s_context(logs) and not _ERROR_RE.search(preprocessed):
        logger.warning(f"Preprocessed logs contain no error signal for run {run_id} — likely incomplete logs")
        raise DiagnosisValidationError(
            "CI logs contain no error output (likely fetched before step logs were archived). "
            "The run will be retried by the reconciler."
        )

    user_prompt = _build_user_prompt(
        preprocessed, repo_full_name, commit_message,
        workflow_name, iteration, previous_diagnosis, current_files, commit_sha, commit_diff,
        similar_fixes=similar_fixes,
        repo_memory=repo_memory,
    )

    # L1: masked exception risk — assertion on a result/status field, no revealing traceback
    if _detect_masked_exception_risk(preprocessed):
        logger.info(f"Masked-exception risk detected for run {run_id} — injecting investigation directive")
        user_prompt += (
            "\n\n⚠️ MASKED EXCEPTION RISK: This failure is an assertion on a returned status/result "
            "value, not a raw traceback. This strongly suggests the real exception is being caught by a "
            "broad except block and converted into an error status/dict, so the true cause never appears "
            "in the logs. Before finalizing your diagnosis, use fetch_file to read the source of the "
            "function that PRODUCES the asserted result and reason about what could throw on its success "
            "path (a stubbed/mocked dependency missing a method, a bad attribute access, a closed "
            "connection, etc.) that gets swallowed. Do not assume the surface symptom is the root cause."
        )

    # L2: repeated hypothesis — iteration N failed with the identical error signature as N-1
    if repeated_failure:
        user_prompt += (
            "\n\n⚠️ REPEATED FAILURE — SAME ERROR AS PREVIOUS ITERATION: The previous fix was applied "
            "and pushed, but CI failed again with the IDENTICAL error signature. This means your "
            "previous root-cause hypothesis was WRONG — the fix did not address the actual problem. "
            "Do NOT propose a variation of the same fix. You must:\n"
            "  1. Explicitly reconsider what could cause this EXACT failure that your previous diagnosis missed.\n"
            "  2. Use fetch_file / search_code to investigate a DIFFERENT part of the codebase than last "
            "time — the function that actually produces the failing output, not just the file you already changed.\n"
            "  3. Consider whether the real error is being swallowed (see the masked-exception guidance above) "
            "or whether a completely different component is responsible.\n"
            "Repeating the same hypothesis will exhaust the remaining retry budget with no progress."
        )
        logger.info(f"Repeated-failure strategy-change directive injected for run {run_id}")

    # Force-fix: user has explicitly authorized — append strong override instruction
    if force_fix:
        user_prompt += (
            "\n\n⚠️ USER OVERRIDE: The user has reviewed the previous diagnosis and explicitly authorized "
            "you to attempt a fix even if uncertain. You MUST produce files_changed. "
            "Do NOT return manual_required — use review_recommended with your best-guess fix. "
            "Even a partial or speculative fix is better than no fix."
        )
        logger.info(f"Force-fix mode enabled for run {run_id}")

    call_type = f"iteration_{iteration}_diagnosis" if iteration > 1 else "diagnosis"
    if repeated_failure:
        call_type = f"iteration_{iteration}_repeated_failure_diagnosis"
    if force_fix:
        call_type = "force_fix_diagnosis"

    if investigation_context:
        raw_args = await call_with_investigation(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            diagnosis_tool_schema=DIAGNOSIS_TOOL,
            investigation_tools=INVESTIGATION_TOOLS,
            execute_tool=lambda name, args: _execute_investigation_tool(name, args, investigation_context),
            run_id=run_id,
            call_type=call_type,
            model=model,
            max_steps=investigation_max_steps,
        )
    else:
        raw_args = await call_with_tool(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            tool_schema=DIAGNOSIS_TOOL,
            run_id=run_id,
            call_type=call_type,
            model=model,
        )

    # Filter out files with no real content or edits before validation. The model
    # sometimes returns new_content="" (or an edits entry with a blank old_content)
    # for a file it couldn't actually generate a fix for — drop those rather than
    # letting one bad file nuke the entire diagnosis. Must check `edits` here too,
    # not just new_content: since 2026-08-17 edits is the normal shape for an
    # existing-file fix, and checking new_content alone would silently drop every
    # one of those (exactly the "Prash quietly does nothing" failure this whole
    # project exists to avoid).
    #
    # One deliberate exception (found 2026-08-22 dogfooding a real CI fix): a
    # genuinely empty new file — a Python __init__.py package marker, a
    # .gitkeep, py.typed — is indistinguishable from "model gave up" by content
    # alone, and the drop above was silently eating the *correct* fix. Known
    # empty-by-convention filenames are let through automatically. Anything
    # else that comes back blank still gets dropped, but the diagnosis is no
    # longer allowed to claim safe_auto_apply confidence once that's happened —
    # downgraded to review_recommended so a human sees it instead of Prash
    # quietly shipping an incomplete fix (same ask-don't-quit principle as the
    # options menu, PRASH_V2.md §9 2026-08-15).
    _KNOWN_EMPTY_FILENAMES = {"__init__.py", ".gitkeep", "py.typed"}
    if raw_args.get("files_changed"):
        valid_files = []
        dropped_any = False
        for fc in raw_args["files_changed"]:
            has_new_content = bool((fc.get("new_content") or "").strip())
            has_edits = any((e.get("old_content") or "").strip() for e in (fc.get("edits") or []))
            path = fc.get("path", "")
            basename = path.rsplit("/", 1)[-1]
            is_known_empty_marker = (
                not has_edits and basename in _KNOWN_EMPTY_FILENAMES and not fc.get("edits")
            )
            explicitly_empty = fc.get("create_empty") is True

            if has_new_content or has_edits:
                valid_files.append(fc)
            elif is_known_empty_marker or explicitly_empty:
                fc["new_content"] = ""
                fc["create_empty"] = True
                valid_files.append(fc)
            else:
                logger.warning(f"Dropping file {fc.get('path', '?')} — no new_content or edits")
                dropped_any = True
        raw_args["files_changed"] = valid_files
        if dropped_any and raw_args.get("fix_type") == "safe_auto_apply":
            logger.warning("Downgrading fix_type to review_recommended — a proposed file was dropped as empty")
            raw_args["fix_type"] = "review_recommended"

    try:
        diagnosis = Diagnosis(**raw_args)
    except ValidationError as e:
        logger.error(f"Kimi tool call failed Pydantic validation for run {run_id}: {e}")
        raise DiagnosisValidationError(f"Schema validation failed: {e}")

    # M3: cap stated confidence against this repo/category's historical track record
    # before the static gates below act on it, so a poor track record can push a
    # diagnosis through the same downgrade path as genuinely low model confidence.
    diagnosis = _recalibrate_confidence(diagnosis, repo_memory, run_id=run_id)

    # ── Post-validation business rule overrides ───────────────────────────────
    updates: dict = {}

    if diagnosis.is_flaky_test and diagnosis.fix_type != "manual_required":
        logger.warning(f"Flaky test flagged but fix_type={diagnosis.fix_type} — overriding to manual_required")
        updates["fix_type"] = "manual_required"
        updates["files_changed"] = []

    if diagnosis.confidence < 0.6 and diagnosis.fix_type == "safe_auto_apply":
        logger.warning(f"Low confidence ({diagnosis.confidence}) with safe_auto_apply — downgrading to review_recommended")
        updates["fix_type"] = "review_recommended"

    if diagnosis.confidence < 0.4 and diagnosis.fix_type == "review_recommended":
        # Only downgrade to manual_required for environment/flaky failures — those genuinely can't be
        # auto-fixed. For code/dependency/workflow failures, keep as review_recommended (speculative PR)
        # so the user still gets a reviewable fix attempt rather than a dead-end.
        if diagnosis.category in ("environment", "flaky_test", "unknown"):
            logger.warning(f"Very low confidence ({diagnosis.confidence}) + category={diagnosis.category} — downgrading to manual_required")
            updates["fix_type"] = "manual_required"
            updates["files_changed"] = []
        else:
            logger.info(f"Low confidence ({diagnosis.confidence}) but category={diagnosis.category} — keeping as speculative review_recommended")
            updates["speculative"] = True

    # NOTE: review_recommended/safe_auto_apply ↔ manual_required coercion is now handled
    # automatically by Diagnosis.coerce_fix_type() @model_validator — no need to duplicate here.

    if updates:
        diagnosis = diagnosis.model_copy(update=updates)

    diagnosis = _apply_deterministic_guardrails(diagnosis, preprocessed)
    diagnosis = _check_dependency_chain_completeness(diagnosis, current_files)
    diagnosis = _flag_strictness_suppression(diagnosis)
    diagnosis = await _consult_second_opinion(diagnosis, SYSTEM_PROMPT, user_prompt, run_id)

    # M9 (B4): a manual_required code diagnosis is a dead end for the user —
    # no PR, nothing to review, just a status. environment/flaky_test/unknown
    # genuinely can't be auto-attempted (missing secrets, a human judgment
    # call, or not enough signal), but "code" failures almost always have
    # *some* plausible guess available. Retry once with the existing
    # force_fix override (already used by the manual "force fix" button) to
    # get a best-guess attempt instead, marked speculative so the PR is
    # clearly labeled as a starting point to review, not a confident fix.
    # Bounded to exactly one retry via the `not force_fix` guard.
    if diagnosis.fix_type == "manual_required" and diagnosis.category == "code" and not force_fix:
        logger.info(f"manual_required code diagnosis for run {run_id} — retrying once with force_fix")
        retried = await diagnose_failure(
            logs=logs,
            repo_full_name=repo_full_name,
            commit_message=commit_message,
            workflow_name=workflow_name,
            iteration=iteration,
            previous_diagnosis=previous_diagnosis,
            run_id=run_id,
            commit_sha=commit_sha,
            commit_diff=commit_diff,
            current_files=current_files,
            force_fix=True,
            repeated_failure=repeated_failure,
            model=model,
            similar_fixes=similar_fixes,
            repo_memory=repo_memory,
            investigation_context=investigation_context,
        )
        if retried.fix_type != "manual_required":
            return retried.model_copy(update={"speculative": True})
        # Even forced, the model still couldn't produce anything — genuinely
        # nothing to guess at. Keep the original diagnosis, not the retry.
        return diagnosis

    return diagnosis


_BARE_MODULE_RE = re.compile(
    r"(?:Cannot find module|MODULE_NOT_FOUND.*module|ModuleNotFoundError:\s+No module named)\s+['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
_SECRET_RE = re.compile(
    r"\b([A-Z][A-Z0-9_]{3,})\b\s+(?:is\s+)?(?:not defined|not set|missing|required)",
    # NO re.IGNORECASE — must be SCREAMING_SNAKE_CASE to qualify as a secret name.
    # "all", "npm", "node" etc. must not match.
)
_DOCKER_COPY_SOURCE_RE = re.compile(r"\bCOPY\s+(?:--\S+\s+)*(?P<path>\.?/?[\w./-]+)", re.IGNORECASE)
_DOCKER_STAT_PATH_RE = re.compile(r"\bstat\s+(?P<path>\.?/?[\w./-]+):", re.IGNORECASE)


def _apply_deterministic_guardrails(
    diagnosis: Diagnosis,
    logs: str,
) -> Diagnosis:
    updates: dict = {}

    missing_modules = [m for m in _extract_missing_modules(logs) if _is_bare_package_name(m)]
    if missing_modules and diagnosis.files_changed:
        if not _changes_dependency_or_workflow(diagnosis):
            updates["fix_type"] = "review_recommended"
            updates["speculative"] = True
            updates["fix_description"] = (
                f"{diagnosis.fix_description}\n\n"
                "Guardrail: the logs show a missing package/module "
                f"({', '.join(sorted(set(missing_modules)))}) rather than a missing source file. "
                "Source-file rewrites are held for review unless the fix updates a manifest or CI workflow."
            )

    secrets = _extract_required_secrets(logs)
    if secrets:
        merged = sorted(set([*diagnosis.required_secrets, *secrets]))
        updates["required_secrets"] = merged
        # Only override category/files when there's no better diagnosis.
        # Never let secret extraction nuke a workflow_config/code/dependency fix.
        if not diagnosis.files_changed and diagnosis.category not in ("workflow_config", "code", "dependency"):
            updates["category"] = "environment"
            updates["fix_type"] = "manual_required"

    # If the model diagnosed workflow_config but produced no files, the prompt didn't
    # drive it hard enough. Keep the category and degrade to review_recommended so the
    # dashboard at least shows what needs to be changed, rather than manual_required.
    if (diagnosis.category == "workflow_config"
            and not diagnosis.files_changed
            and diagnosis.fix_type == "manual_required"
            and "fix_type" not in updates):
        updates["fix_type"] = "review_recommended"
        updates["speculative"] = True

    missing_copy_path = _extract_missing_docker_copy_path(logs)
    if missing_copy_path and diagnosis.fix_type == "safe_auto_apply":
        allowed_paths = {missing_copy_path, missing_copy_path.lstrip("./")}
        touches_dockerfile = any(fc.path.lower().endswith("dockerfile") or fc.path == "Dockerfile" for fc in diagnosis.files_changed)
        creates_exact_path = any(fc.path in allowed_paths for fc in diagnosis.files_changed)
        if not touches_dockerfile and not creates_exact_path:
            updates["fix_type"] = "review_recommended"
            updates["speculative"] = True
            updates["fix_description"] = (
                f"{updates.get('fix_description', diagnosis.fix_description)}\n\n"
                f"Guardrail: Docker reported missing build-context path `{missing_copy_path}`. "
                "The proposed file changes do not touch that exact path or the Dockerfile, so this needs review."
            )

    if not updates:
        return diagnosis
    return diagnosis.model_copy(update=updates)


def _recalibrate_confidence(
    diagnosis: Diagnosis,
    repo_memory: RepoMemory | None,
    run_id: str | None = None,
) -> Diagnosis:
    """
    M3: cap stated confidence against this repo's actual track record for the
    diagnosis category. A category that verifies 20% of the time doesn't get to
    claim 90%+ confidence just because the model feels sure this time.

    Reverted fixes count against the rate even though they were "verified" at
    merge time — a fix that got reverted within 7 days was not actually a
    success, and category_outcomes.verified_rate alone doesn't reflect that.
    """
    if not repo_memory:
        return diagnosis

    stats = repo_memory.category_outcomes.get(diagnosis.category)
    if not stats:
        return diagnosis

    attempts = stats.get("attempts", 0)
    if attempts < MIN_CALIBRATION_SAMPLES:
        return diagnosis

    effective_verified = max(0, stats.get("verified", 0) - stats.get("reverted", 0))
    effective_rate = effective_verified / attempts
    calibrated_ceiling = round(min(1.0, effective_rate + 0.2), 2)

    if diagnosis.confidence <= calibrated_ceiling:
        return diagnosis

    logger.info(
        f"Confidence recalibration: run={run_id} category={diagnosis.category} "
        f"model_confidence={diagnosis.confidence} effective_verified_rate={round(effective_rate, 2)} "
        f"(verified={stats.get('verified', 0)} reverted={stats.get('reverted', 0)} attempts={attempts}) "
        f"-> capped at {calibrated_ceiling}"
    )
    return diagnosis.model_copy(update={"confidence": calibrated_ceiling})


# M4: known peer/type package pairs whose major versions must stay in lockstep.
# A JS/TS build breaks just as hard from a partial bump (react ^18, @types/react ^17
# left behind) as from no bump at all — this is the exact gap that caused the
# lagom-humanizer dependency incident. See ROADMAP.md "Dependency chain completeness".
_PEER_VERSION_PAIRS = [
    ("react", "react-dom"),
    ("react", "@types/react"),
    ("react-dom", "@types/react-dom"),
    ("vue", "@vue/compiler-sfc"),
    ("vue", "@vue/runtime-core"),
    ("@angular/core", "@angular/common"),
    ("@angular/core", "@angular/compiler"),
]


def _extract_major_version(spec: str) -> int | None:
    """Best-effort leading major version from a semver range like '^18.2.0' or '~5.0.1'."""
    if not isinstance(spec, str):
        return None
    spec = spec.strip()
    if not spec or spec in ("*", "latest", "next") or spec.startswith(("workspace:", "file:", "git", "link:")):
        return None
    match = re.search(r"(\d+)", spec)
    return int(match.group(1)) if match else None


def _check_dependency_chain_completeness(diagnosis: Diagnosis, current_files: dict[str, str] | None = None) -> Diagnosis:
    """
    M4: deterministic check for peer/type package major-version alignment in a
    rewritten package.json. Prompt instructions alone weren't reliable enough —
    this catches an incomplete bump instead of letting it ship as safe_auto_apply.

    Needs the resulting file's full content to parse, which since 2026-08-17
    (edits replacing new_content as the normal existing-file shape, PRASH_V2.md
    §9) isn't always on the FileChange directly — apply() reconstructs it from
    current_files, the same pre-fetched content already shown to the model in
    the prompt for this exact reason.
    """
    package_json = next(
        (fc for fc in diagnosis.files_changed if fc.path.endswith("package.json") and (fc.new_content or fc.edits)),
        None,
    )
    if not package_json:
        return diagnosis

    try:
        original = (current_files or {}).get(package_json.path)
        manifest = json.loads(package_json.apply(original))
    except (json.JSONDecodeError, TypeError, ValueError):
        return diagnosis

    if not isinstance(manifest, dict):
        return diagnosis

    versions: dict[str, str] = {}
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        section_data = manifest.get(section)
        if isinstance(section_data, dict):
            versions.update(section_data)

    mismatches = []
    for pkg_a, pkg_b in _PEER_VERSION_PAIRS:
        if pkg_a not in versions or pkg_b not in versions:
            continue
        major_a = _extract_major_version(versions[pkg_a])
        major_b = _extract_major_version(versions[pkg_b])
        if major_a is not None and major_b is not None and major_a != major_b:
            mismatches.append(f"{pkg_a}@{versions[pkg_a]} vs {pkg_b}@{versions[pkg_b]}")

    if not mismatches:
        return diagnosis

    logger.warning(f"Dependency chain incomplete — peer major-version mismatch: {mismatches}")
    return diagnosis.model_copy(update={
        "fix_type": "review_recommended",
        "speculative": True,
        "fix_description": (
            f"{diagnosis.fix_description}\n\n"
            "Guardrail: package.json bumps one package in a peer/type group without matching "
            f"the others — major-version mismatch: {'; '.join(mismatches)}. Held for review "
            "instead of auto-applied; a partial peer bump breaks the build the same way a "
            "missing bump does."
        ),
    })


# M6: language patterns indicating the fix loosens an analyzer/linter/test gate
# rather than resolving what it caught — "lowered the level", "disabled the
# rule", "relaxed strictness". Deliberately matches the MODEL'S OWN description
# of its fix, not file diffs (which would need the original file content this
# guardrail doesn't have access to) — the model already states in plain
# language what it did, so read that instead of re-deriving it from a diff.
#
# Flexible gap between the action verb and target noun (not a rigid adjacent
# phrase) — verified against the real diagnosis this milestone is fixing:
# "Lower PHPStan analysis level from 9 to 5..." has a tool name (PHPStan)
# sitting between "Lower" and "level" that a strict "lowered the level"
# phrase would miss entirely.
_SUPPRESSION_LANGUAGE_RE = re.compile(
    r"\b(lower(?:ed|ing)?|disable[ds]?|disabling|relax(?:ed|ing)?|loosen(?:ed|ing)?"
    r"|downgrad(?:ed?|ing)|suppress(?:ed|ing)?|turn(?:ed)?\s+off|skip(?:ped|ping)?)\b"
    r".{0,40}?\b(level|strictness|severity|check|rule|lint|test|analyzer|analysis)\b",
    re.IGNORECASE | re.DOTALL,
)

_HONEST_DISCLOSURE_RE = re.compile(r"^\s*note:.{0,80}(relax|suppress|loosen|lower)", re.IGNORECASE)


def _flag_strictness_suppression(diagnosis: Diagnosis) -> Diagnosis:
    """
    M6: prompt instructions ask the model to disclose when a fix loosens an
    analyzer/linter/test gate instead of fixing what it caught (see "ROOT
    CAUSE VS SUPPRESSION" in the system prompt) — this is the deterministic
    backstop for when it doesn't. Found live: a PHPStan level 9->5 diagnosis
    described itself as if it were a resolution, not a suppression.
    """
    text = f"{diagnosis.fix_description} {diagnosis.root_cause}"
    if not _SUPPRESSION_LANGUAGE_RE.search(text):
        return diagnosis
    if _HONEST_DISCLOSURE_RE.search(diagnosis.fix_description):
        return diagnosis  # model already disclosed it honestly, per the prompt

    logger.info(f"Diagnosis loosens a check without an honest disclosure — prepending one: {text[:200]}")
    return diagnosis.model_copy(update={
        "fix_description": (
            "Note: this appears to relax a linter/analyzer/test check rather than fixing the "
            f"underlying issue it caught — verify that's acceptable before merging.\n\n{diagnosis.fix_description}"
        ),
    })


# M8: only consult a second model when the primary diagnosis is already
# uncertain — this is a narrow, rare trigger (not a blanket "race everything"
# like the D2 idea that got explicitly skipped for cost reasons), so the
# added cost is proportional to how often it actually helps. Real 30-day
# production data: 28/30 diagnoses landed at confidence >=0.92; both
# low-confidence cases were caused by missing log signal (now fixed by
# M1-M5), not model disagreement — but genuine disagreement is still a real
# failure mode worth checking for going forward.
_LOW_CONFIDENCE_THRESHOLD = 0.5


async def _consult_second_opinion(
    diagnosis: Diagnosis,
    system_prompt: str,
    user_prompt: str,
    run_id: str | None,
) -> Diagnosis:
    """
    Fire one independent Kimi call (forced tool_choice, single-shot — not the
    full investigation loop) for low-confidence/unknown diagnoses, and record
    whether it agrees. Deliberately does NOT use agreement to raise confidence
    or change fix_type — compounding two uncertain guesses into apparent
    certainty would be worse than the problem this solves. It surfaces
    agreement/disagreement as a signal for the human reviewer, who already
    sees this diagnosis either way since low-confidence routes to
    review_recommended/manual_required regardless.
    """
    if diagnosis.category != "unknown" and diagnosis.confidence >= _LOW_CONFIDENCE_THRESHOLD:
        return diagnosis

    try:
        second_args, _, _ = await _call_kimi_structured(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            DIAGNOSIS_TOOL,
        )
    except Exception as e:
        logger.warning(f"Second-opinion Kimi call failed for run {run_id}: {e}")
        return diagnosis

    if not second_args or not _args_match_schema(second_args, DIAGNOSIS_TOOL):
        logger.info(f"Second-opinion Kimi call for run {run_id} didn't return a valid diagnosis — skipping")
        return diagnosis

    second_fix_type = second_args.get("fix_type")
    second_category = second_args.get("category")
    agrees = second_fix_type == diagnosis.fix_type and second_category == diagnosis.category

    logger.info(
        f"Second opinion for run {run_id}: agrees={agrees} "
        f"(primary={diagnosis.fix_type}/{diagnosis.category}, kimi={second_fix_type}/{second_category})"
    )
    note = (
        f"\n\nCross-model check: Kimi's independent second opinion "
        f"{'agrees with this diagnosis' if agrees else f'DISAGREES — Kimi suggested fix_type={second_fix_type}, category={second_category}'}."
    )
    return diagnosis.model_copy(update={"fix_description": diagnosis.fix_description + note})


def _extract_missing_modules(logs: str) -> list[str]:
    return [m.group(1).strip() for m in _BARE_MODULE_RE.finditer(logs or "")]


def _is_bare_package_name(module_name: str) -> bool:
    return not (
        module_name.startswith(".")
        or module_name.startswith("/")
        or module_name.startswith("@/")
        or "/" in module_name and module_name.startswith(("src/", "app/", "lib/", "tests/"))
    )


def _changes_dependency_or_workflow(diagnosis: Diagnosis) -> bool:
    manifest_names = {
        "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
        "requirements.txt", "pyproject.toml", "poetry.lock", "Pipfile",
        "go.mod", "go.sum", "Cargo.toml", "Cargo.lock", "Gemfile", "Gemfile.lock",
    }
    for file_change in diagnosis.files_changed:
        path = file_change.path
        if path in manifest_names or path.startswith(".github/workflows/"):
            return True
    return False


def _extract_required_secrets(logs: str) -> list[str]:
    # Known safe CI env vars that are never real secrets
    _SAFE = {"CI", "NODE_ENV", "PORT", "RAILS_ENV", "HOME", "PATH", "LANG", "TZ",
             "NPM", "NODE", "YARN", "PNPM", "ALL", "ERROR", "WARN", "INFO", "DEBUG"}
    return [
        match.group(1)
        for match in _SECRET_RE.finditer(logs or "")
        if match.group(1) not in _SAFE
        and "_" in match.group(1)  # real secrets almost always have underscores
    ]


def _extract_missing_docker_copy_path(logs: str) -> str | None:
    recent_copy_path: str | None = None
    for line in (logs or "").splitlines():
        lower = line.lower()
        copy_match = _DOCKER_COPY_SOURCE_RE.search(line)
        if copy_match:
            recent_copy_path = copy_match.group("path").strip()

        if not any(marker in lower for marker in ("not found", "no such file", "failed", "does not exist")):
            continue

        for pattern in (_DOCKER_COPY_SOURCE_RE, _DOCKER_STAT_PATH_RE):
            match = pattern.search(line)
            if match:
                return match.group("path").strip()
        if recent_copy_path:
            return recent_copy_path
    return None


INVESTIGATION_TOOLS = [
    {
        "name": "fetch_file",
        "description": "Fetch the current content of a file from the repo.",
        "parameters": {
            "type": "object",
            "required": ["path"],
            "properties": {"path": {"type": "string"}},
        },
    },
    {
        "name": "list_directory",
        "description": "List files in a directory.",
        "parameters": {
            "type": "object",
            "required": ["path"],
            "properties": {"path": {"type": "string"}},
        },
    },
    {
        "name": "search_code",
        "description": "Search for a function, class, or symbol in the repository.",
        "parameters": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
    },
]


def _validate_investigation_path(path: str) -> str | None:
    if ".." in path or path.startswith("/"):
        return "Path must be relative and cannot contain '..'"
    return None


async def _execute_investigation_tool(tool_name: str, tool_args: dict, context: dict) -> str:
    if tool_name == "fetch_file":
        path = tool_args.get("path", "")
        if err := _validate_investigation_path(path):
            return json.dumps({"error": err, "path": path})
        return await _investigation_fetch_file(context, path)
    if tool_name == "list_directory":
        path = tool_args.get("path", "")
        if err := _validate_investigation_path(path):
            return json.dumps({"error": err, "path": path})
        return await _investigation_list_directory(context, path)
    if tool_name == "search_code":
        return await _investigation_search_code(context, tool_args.get("query", ""))
    return json.dumps({"error": f"Unknown investigation tool: {tool_name}"})


async def _investigation_fetch_file(context: dict, path: str) -> str:
    if not path:
        return json.dumps({"error": "path is required"})
    headers = _gh_headers(context["access_token"])
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"https://api.github.com/repos/{context['repo_full_name']}/contents/{path}",
            headers=headers,
            params={"ref": context["default_branch"]},
        )
    if resp.status_code != 200:
        return json.dumps({"error": f"fetch_file failed with {resp.status_code}", "path": path})
    data = resp.json()
    content = base64.b64decode(data["content"].replace("\n", "")).decode("utf-8", errors="replace")
    return json.dumps({"path": path, "content": content[:20000]})


async def _investigation_list_directory(context: dict, path: str) -> str:
    headers = _gh_headers(context["access_token"])
    target = path.strip("/") if path else ""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"https://api.github.com/repos/{context['repo_full_name']}/contents/{target}",
            headers=headers,
            params={"ref": context["default_branch"]},
        )
    if resp.status_code != 200:
        return json.dumps({"error": f"list_directory failed with {resp.status_code}", "path": target})
    entries = [
        {"path": item.get("path"), "type": item.get("type")}
        for item in (resp.json() if isinstance(resp.json(), list) else [])
    ]
    return json.dumps({"path": target or ".", "entries": entries[:200]})


async def _investigation_search_code(context: dict, query: str) -> str:
    if not query:
        return json.dumps({"error": "query is required"})
    headers = _gh_headers(context["access_token"])
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://api.github.com/search/code",
            headers=headers,
            params={"q": f"{query} repo:{context['repo_full_name']}", "per_page": 10},
        )
    if resp.status_code != 200:
        return json.dumps({"error": f"search_code failed with {resp.status_code}", "query": query})
    items = [
        {"path": item.get("path"), "name": item.get("name")}
        for item in resp.json().get("items", [])
    ]
    return json.dumps({"query": query, "matches": items})


def _gh_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


# ── Deployment manifest discovery (PRASH_V2.md §9, 2026-08-16) ────────────────

# Bounded so a huge monorepo can't turn one diagnosis into hundreds of API
# calls. Ordered heuristically: conventional manifest homes first.
_MANIFEST_HINT_DIRS = ("k8s", "kubernetes", "manifests", "deploy", "deployment", "charts", "testdata", "infra")
_MAX_MANIFEST_CANDIDATES = 25
_MAX_MANIFEST_BYTES = 100_000


def deployment_name_from_pod(pod_name: str) -> str:
    """`broken-app-6b58dc6d7b-fphhd` -> `broken-app`.

    Deployment-managed pods are named `<deployment>-<replicaset>-<random>`, so
    dropping the last two dash-segments recovers the Deployment name. Falls
    back to the full name for pods that don't match that shape (bare pods,
    StatefulSet members), which is still the right thing to search for.
    """
    parts = pod_name.rsplit("-", 2)
    return parts[0] if len(parts) == 3 else pod_name


async def find_deployment_manifest(
    repo: str,
    access_token: str,
    deployment: str,
    default_branch: str = "main",
) -> tuple[str | None, str | None]:
    """Locate the YAML manifest defining ``deployment``. Returns (path, content).

    Uses the git tree API, NOT the code search API. Found the hard way on the
    first live run (2026-08-16): GitHub's code search returned 0 results for a
    file that provably exists in the repo -- its index lags and is unreliable
    for private/recent repos -- so the model correctly-but-wrongly concluded
    "the manifest is not in this repository" and declined. The tree API is
    deterministic: it lists every file, with no index in the path.

    Deliberately done BEFORE the model call rather than left to the model's own
    search: discovery is a mechanical lookup, and handing over the real content
    beats hoping the model guesses the right query.
    """
    headers = _gh_headers(access_token)
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.get(
                f"https://api.github.com/repos/{repo}/git/trees/{default_branch}",
                headers=headers,
                params={"recursive": "1"},
            )
            if resp.status_code != 200:
                logger.info(f"manifest discovery: tree fetch returned {resp.status_code} for {repo}")
                return None, None
            tree = resp.json().get("tree", [])
        except Exception as exc:  # noqa: BLE001 — discovery is best-effort, never fatal
            logger.info(f"manifest discovery: tree fetch failed for {repo}: {exc}")
            return None, None

        candidates = [
            item["path"]
            for item in tree
            if item.get("type") == "blob"
            and item.get("path", "").endswith((".yaml", ".yml"))
            and (item.get("size") or 0) <= _MAX_MANIFEST_BYTES
        ]
        # Conventional manifest locations first, then everything else.
        candidates.sort(key=lambda p: (not any(d in p.lower() for d in _MANIFEST_HINT_DIRS), len(p)))
        candidates = candidates[:_MAX_MANIFEST_CANDIDATES]

        async def _read(path: str) -> tuple[str, str] | None:
            try:
                r = await client.get(
                    f"https://api.github.com/repos/{repo}/contents/{path}",
                    headers=headers,
                    params={"ref": default_branch},
                )
                if r.status_code != 200:
                    return None
                raw = r.json().get("content", "")
                return path, base64.b64decode(raw.replace("\n", "")).decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                return None

        results = await asyncio.gather(*(_read(p) for p in candidates))

    for found in results:
        if not found:
            continue
        path, content = found
        # Must both name the deployment and actually be a Deployment-ish
        # object -- a ConfigMap that merely mentions the name isn't the file
        # whose spec needs editing.
        if f"name: {deployment}" in content and "kind: Deployment" in content:
            logger.info(f"manifest discovery: {deployment} -> {path}")
            return path, content

    logger.info(f"manifest discovery: no manifest found for {deployment} in {repo}")
    return None, None


def _build_user_prompt(
    logs: str,
    repo_full_name: str,
    commit_message: str,
    workflow_name: str,
    iteration: int,
    previous_diagnosis: dict | None,
    current_files: dict[str, str] | None,
    commit_sha: str | None,
    commit_diff: str | None,
    similar_fixes: list[dict] | None = None,
    repo_memory: RepoMemory | None = None,
) -> str:
    parts = [
        f"REPOSITORY: {repo_full_name}",
        f"WORKFLOW: {workflow_name}",
        f"COMMIT MESSAGE: {commit_message}",
    ]

    if commit_sha:
        parts.append(f"COMMIT SHA: {commit_sha}")

    if repo_memory:
        context = repo_memory.as_prompt_context()
        if context:
            parts.append(context)

    # RAG: inject past verified fixes for this repo as few-shot context
    if similar_fixes and not repo_memory:
        rag_lines = [
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "PAST VERIFIED FIXES FOR THIS REPO (use these as reference — same patterns may apply)",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]
        for i, fix in enumerate(similar_fixes, 1):
            files_summary = ", ".join(
                f["path"] for f in (fix.get("files_changed") or [])
            ) or "none"
            rag_lines.append(
                f"\nVerified Fix #{i} [{fix.get('category', '?')}] "
                f"(confidence {int((fix.get('confidence') or 0) * 100)}%)"
            )
            rag_lines.append(f"Problem: {fix.get('problem_summary', '')}")
            rag_lines.append(f"Root cause: {fix.get('root_cause', '')[:300]}")
            rag_lines.append(f"Fix: {fix.get('fix_description', '')[:300]}")
            rag_lines.append(f"Files changed: {files_summary}")
        rag_lines.append(
            "\nIf the current failure matches one of the above patterns, apply the same fix approach."
        )
        parts.append("\n".join(rag_lines))

    # Inject current file contents as the exact source text for edits[].old_content
    if current_files:
        parts.append(
            "\nCURRENT FILE CONTENTS (these files already exist — use edits with old_content "
            "copied VERBATIM from here, not new_content):"
        )
        for path, content in current_files.items():
            parts.append(f"\n=== {path} ===\n{content}\n=== end {path} ===")

    if commit_diff:
        parts.append(f"\nCOMMIT DIFF (what changed to break CI):\n---\n{commit_diff}\n---")
        parts.append("The fix should likely modify these same files unless the logs clearly point elsewhere.")

    parts.append(f"\nCI FAILURE LOGS:\n---\n{logs}\n---")

    # Follow-up iterations: append previous diagnosis context as clean JSON
    if iteration > 1 and previous_diagnosis:
        prev_clean = {
            k: previous_diagnosis.get(k)
            for k in ("problem_summary", "root_cause", "fix_description", "files_changed")
        }
        parts.append(
            f"\n\nIMPORTANT — FOLLOW-UP ITERATION {iteration}:\n"
            "The previous fix attempt was applied and CI FAILED AGAIN on the fix branch.\n"
            "Previous diagnosis that failed:\n"
            f"{json.dumps(prev_clean, indent=2)}\n\n"
            "The logs above are from the fix branch AFTER applying the previous fix.\n"
            "You must identify:\n"
            "  1. What the previous diagnosis got wrong or missed\n"
            "  2. Whether the original root cause was misidentified, or the fix was incomplete\n"
            "  3. A new fix that addresses both the original and the new failure\n\n"
            "DO NOT give up — you MUST produce a files_changed fix attempt. "
            "Your fix will be pushed to the same branch for CI verification."
        )

    return "\n".join(parts)
