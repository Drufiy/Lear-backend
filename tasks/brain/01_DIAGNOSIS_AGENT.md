# Diagnosis Agent — `brain/diagnosis_agent.py`

**Owner:** Aradhya  
**Status:** Core built (146K, 69 CI refs + K8s taught), domain expansion needed  
**Priority:** Tier 1  

---

## Current State

- System prompt covers: CI failures (GitHub/GitLab Actions), Kubernetes runtime (`CrashLoopBackOff`, `OOMKilled`, `ImagePullBackOff`, stuck Pending)
- 19 worked examples (EXAMPLES 1-19 for CI, 20b for K8s manifest fix)
- "Ask, don't quit" section with EXAMPLES 24-25 (ambiguity vs. confidence)
- `Diagnosis` tool schema with `options` field
- `files_changed` permitted for runtime when manifest repo available
- Investigation budget: `max_steps=2` for CI, `max_steps=5` for K8s

---

## Tasks

### T1. Add domain-specific context formatters for new connectors
- [ ] `format_datadog_context(events: list[ConnectorEvent]) -> str` — monitor alerts, metric spikes
- [ ] `format_grafana_context(events: list[ConnectorEvent]) -> str` — alert rules, panel anomalies
- [ ] `format_pagerduty_context(events: list[ConnectorEvent]) -> str` — incident timeline
- [ ] `format_aws_context()` — already exists, verify works with new `get_stats()` output
- [ ] `format_terraform_context()` — drift detection output
- [ ] `format_vercel_context()` — deployment failures

### T2. Add worked examples for new domains
- [ ] Datadog: monitor alert → diagnosis → mute or investigate
- [ ] Grafana: alert firing → diagnosis → silence or investigate
- [ ] PagerDuty: incident triggered → diagnosis → acknowledge or escalate
- [ ] AWS: instance status check failed → diagnosis → execute command or reboot
- [ ] Multi-source: K8s pod crash + Datadog metric spike → correlated diagnosis

### T3. Extend `category` enum for new failure types
- [ ] Current: `code`, `dependency`, `workflow_config`, `environment`, `flaky_test`, `runtime`, `infra_as_code`, `unknown`
- [ ] Add: `monitoring` (Datadog/Grafana alerts), `incident` (PagerDuty), `security` (Snyk/Gitleaks), `deployment` (Vercel)
- [ ] Update prompt instructions for each new category

### T4. Multi-connector context assembly
- [ ] When multiple connectors provide context, assemble into one prompt
- [ ] Cross-reference: K8s pod crash + Datadog CPU spike = "OOMKilled, CPU exceeded limit"
- [ ] Order: most-relevant connector first, supporting evidence second

### T5. `max_steps` tuning per domain
- [ ] CI: keep `max_steps=2` (logs already in prompt)
- [ ] K8s: keep `max_steps=5` (search → fetch → submit)
- [ ] Datadog/Grafana: `max_steps=3` (query metrics, check related monitors)
- [ ] Cloud VMs: `max_steps=4` (instance state + logs + metrics)

### T6. Fix eval harness `.env` loading
- [ ] `evals/run_eval.py` must load `.env` (currently depends on shell having keys exported)
- [ ] Add `dotenv.load_dotenv()` at startup
- [ ] Test: eval harness works from clean shell without pre-exported keys

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_format_datadog_context` | `tests/test_brain_datadog_context.py` | Correct prompt format |
| `test_format_grafana_context` | `tests/test_brain_grafana_context.py` | Correct prompt format |
| `test_format_pagerduty_context` | `tests/test_brain_pagerduty_context.py` | Correct prompt format |
| `test_format_k8s_context` | `tests/test_brain_k8s_context.py` | Existing, must not regress |
| `test_new_categories` | `tests/test_brain_schemas.py` | New category values accepted |
| `test_multi_connector_context` | `tests/test_correlation.py` | Multi-source context assembly |
| `test_eval_harness_env` | `tests/test_eval_env_loading.py` | `.env` loaded automatically |
| `test_eval_no_regression` | Run `evals/run_eval.py --baseline` | No regression vs. baseline |

---

## Acceptance Criteria

- [ ] Context formatters exist for every connector with `get_stats()`
- [ ] At least 2 worked examples per new domain
- [ ] Eval baseline not regressed (94.7% valid, 100% category, 1.0 recall)
- [ ] Eval harness loads `.env` on its own
- [ ] Multi-connector context produces correct diagnosis
