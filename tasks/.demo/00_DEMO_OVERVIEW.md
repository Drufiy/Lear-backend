# Demo — Master Overview

**Meeting:** Gradup Capital MD  
**Date:** Tomorrow morning  
**Duration:** ~15 minutes (12 min demo + 3 min Q&A)  

---

## Demo Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  AWS EKS Cluster (lear-demo)            Fallback: local Kind        │
│                                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ frontend │→│ checkout  │→│ payment   │→│ postgres  │            │
│  │ (nginx)  │  │   api     │  │ service   │  │          │            │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │
│        ↑                                                             │
│  ┌──────────┐  ┌──────────┐                                         │
│  │ loadgen  │  │ shipping  │                                         │
│  │ (k6/ab)  │  │ service   │                                         │
│  └──────────┘  └──────────┘                                         │
└──────────────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
┌─────────────────┐          ┌──────────────────────┐
│  Datadog         │          │  Lear Desktop App     │
│  Container Mon.  │          │  Dashboard + Watcher   │
│  Synthetic Mon.  │          │  Chat + Audit          │
└─────────────────┘          └──────────────────────┘
```

---

## Pre-Demo Checklist (Night Before)

- [x] EKS cluster created and healthy (`01_INFRASTRUCTURE.md` — Mumbai ap-south-1, 2x t3.medium nodes Ready)
- [x] All 5 services deployed and running (`02_MICROSERVICES.md` — 5/5 pods 1/1 Running on live ELB)
- [x] Load generator running — 200-500 concurrent users (`03_LOAD_GENERATOR.md` — in-cluster + local script tested)
- [x] Datadog agent deployed, container metrics flowing (`07_DATADOG_SETUP.md`)
- [x] Failure injection scripts tested — each failure → recovery verified (`04_FAILURE_INJECTION.md` — CrashLoopBackOff & reset verified)
- [x] Episodic memory seeded with previous fix history (`05_EPISODIC_MEMORY.md` — local_memory.py tested)
- [x] Full rehearsal run: inject → detect → diagnose → fix → verify → audit (`06_DEMO_SCRIPT.md` — complete cycle under 60s)
- [x] Lear Desktop app connected to backend, showing live widgets
- [x] Fallback Kind cluster tested (same manifests, `kind create cluster`)

## Day-Of Checklist (30 min before meeting)

- [ ] `kubectl get pods -n lear-demo` — all Running
- [ ] Load generator active (check request rate)
- [ ] `prash watch` started in terminal
- [ ] Desktop app open, dashboard showing green
- [ ] Datadog dashboard tab open in browser
- [ ] Terminal + Desktop visible (split screen or dual monitor)
- [ ] `inject-failure.sh` ready to run (one keystroke)
- [ ] `reset-demo.sh` ready (for between demo runs)

---

## Task Files

| # | File | What it covers |
|---|---|---|
| 01 | [`01_INFRASTRUCTURE.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/.demo/01_INFRASTRUCTURE.md) | EKS cluster + Kind fallback |
| 02 | [`02_MICROSERVICES.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/.demo/02_MICROSERVICES.md) | 5 services + manifests |
| 03 | [`03_LOAD_GENERATOR.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/.demo/03_LOAD_GENERATOR.md) | Simulated user traffic |
| 04 | [`04_FAILURE_INJECTION.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/.demo/04_FAILURE_INJECTION.md) | Pre-scripted breaks + resets |
| 05 | [`05_EPISODIC_MEMORY.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/.demo/05_EPISODIC_MEMORY.md) | RepoMemory seeding |
| 06 | [`06_DEMO_SCRIPT.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/.demo/06_DEMO_SCRIPT.md) | Minute-by-minute presenter script |
| 07 | [`07_DATADOG_SETUP.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/.demo/07_DATADOG_SETUP.md) | Datadog agent + monitors |

---

## Abort Procedures

| Problem | Recovery | Time |
|---|---|---|
| EKS unreachable | Switch to Kind: `kind create cluster --name lear-demo`, reapply manifests | 60s |
| Datadog API slow | Skip correlation act, do K8s-only demo | 0s |
| AI model API timeout | Fallback chain handles it (DeepSeek → Kimi → Gemini) | Auto |
| Pod won't recover after fix | `./reset-demo.sh` hard-resets everything | 15s |
| Desktop app won't connect | Fall back to pure CLI: `prash fix` + `prash audit` | 0s |
