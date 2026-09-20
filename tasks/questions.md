# Meeting Questions — AWS Engineer & DevOps Engineer (Hong Kong)

**Context:** Lear is an AI DevOps agent (local-first, credentials never leave the user's machine) that watches infrastructure (K8s, CI, cloud), diagnoses failures, and acts with human approval. We're a 3-person startup building this. 20-25 min per meeting — every question must earn its time.

---

## For the AWS Engineer

### Escalation Management (5 min)

1. **When an automated system (like Lear) triggers a wrong action in prod — what does AWS's internal escalation chain actually look like in the first 5 minutes?** We have a circuit breaker (5 actions/60s cap) and a permission-tier system, but we've never had a real mis-action in prod. What do teams that handle this well do that we might not be thinking about?

2. **How does AWS decide which automated remediations are safe to run without human approval vs. which always need a human?** We have a SAFE/APPROVAL/NEVER tier system — is there a framework or set of heuristics your teams use that we should steal?

3. **When an AI agent has access to write to prod (restart pods, scale, exec, rollback) — what's the minimum telemetry/audit trail you'd want to see before you'd trust it?** Our audit log records every action, tier, approval status, and outcome — is that enough, or are we missing something critical?

### Architecture & Infrastructure (5 min)

4. **We run entirely local-first — credentials never touch our servers. If a startup customer wants Lear running 24/7 as "autopilot" (watching prod while the team sleeps), what's the cheapest reliable way to host a lightweight Python polling agent in AWS?** Fargate? A t3.micro? Lambda on a schedule? What would you actually recommend for a team of 5 that doesn't want to babysit infra for their infra tool?

5. **Our watcher polls K8s/cloud APIs on intervals (5s-60s). At what scale does polling become a problem, and what's the migration path?** We're targeting startups (5-50 engineers, a few clusters). Is there a threshold where we'd need to move to event-driven (CloudWatch Events, K8s informers)?

### Moat & What AWS Won't Build (7-8 min — the most important section)

6. **AWS has re:Invent every year. What's the realistic version of "Amazon builds this"?** Is an AI agent that diagnoses and acts on your own infrastructure something AWS would productize — or does their business model (you use more services = they earn more) structurally prevent them from building something that *reduces* cloud resource consumption by fixing problems faster? Where's the ceiling on what Amazon actually has incentive to solve for a startup?

7. **AWS DevOps Guru exists. Amazon Q for DevOps exists. In your experience using these — what do they not do?** We're not trying to beat AWS at observability. We're trying to be the thing that *acts* after they've told you something is wrong. Is that gap real in practice, or does AWS already close it for most teams?

8. **What's a problem your team hits with AWS infrastructure that you'd never expect AWS to build a product for — because it's too specific to your stack, your team's processes, or your own internal systems?** These are the exact cracks Lear can fill. A platform vendor builds for the median user; an agent configured by your team acts for *you*. We want to know what the median misses.

9. **The "credentials never leave your machine" model is our core trust argument. Does that actually matter to you, or is it just good marketing?** If you had to choose between a product that's slightly better but holds your keys, vs. a product that's slightly worse but you hold your own keys — how do you actually make that call? What's the real weight of that tradeoff for a startup vs. an enterprise?

10. **What's something you've automated internally that no vendor tool could've done for you — because it required knowing your specific team's runbook, your naming conventions, your blast radius?** That's the kind of customization Lear is built to support (the brain can be taught your environment). Is that actually valuable, or does it just shift the config burden onto the customer?

### Product/Trust (2-3 min)

11. **If you were evaluating Lear for your own team — what would make you say "no" in the first 5 minutes of a demo?** What's the trust-killer for an AI agent that touches infra?

---

## For the DevOps Engineer (Hong Kong Company)

### How Escalations Actually Work (5 min)

1. **Walk me through your last real production incident — from the first alert to resolution. What were the handoff points, and where did time get wasted?** We're building Lear to compress that timeline. Knowing where the real friction is tells us where to focus.

2. **When your monitoring (Datadog/Grafana/PagerDuty) fires an alert at 3am — what's the actual human workflow?** Who gets paged? What do they check first? What tools do they open? How long before they know if it's real or noise? Lear is supposed to do that first-pass triage automatically.

3. **How many of your incidents in a typical month could have been fixed by a restart, a rollback, or a config change — vs. needing a real engineer to think?** We're trying to validate our bet that most DevOps incidents are rote actions wrapped in diagnosis time.

### Team & Tooling Reality (5 min)

4. **What's your DevOps team's actual daily workflow?** Not the org chart — the actual tools open on your screen, the Slack channels, the dashboards. What's manual that shouldn't be?

5. **If an AI agent could do 3 things for your team tomorrow — what would they be?** Not a wish list — the 3 things that would actually save your team hours this week.

6. **What's the hardest part about onboarding a new DevOps tool?** We need near-zero setup friction (we have `prash setup` wizard, local `.env`, no hosted dependencies). What usually kills adoption at your company?

### Where AI Actually Fits in Your Team (7-8 min — go deep here)

7. **Honestly — where in your team's hierarchy would an AI agent like Lear sit?** Not where it *should* sit in theory. In practice, if Lear existed today: would it be something your senior engineers trust and use, or something your junior engineers use while seniors supervise? Or does it sit below both — handling the stuff nobody wants to touch at 3am?

8. **What's your gut reaction to "the AI agent will restart your pod without asking"?** We have a permission system (you choose: always ask / auto-safe / environment-scoped). But we want to know: where is your team's actual comfort line? Is it namespace-level? Is it "yes in staging, never in prod"? Is it "only if it's a restart, never if it's a rollback"? What's the real line?

9. **Has your team ever had an incident that was purely rote — you knew exactly what to do, it just needed a human to pull the trigger at 3am?** Walk me through it. That's the exact scenario Lear is built for. If the answer is "yes that happens every month" — that's product-market fit. If the answer is "we automate those already" — we need to know what you use.

10. **DevOps engineers often see automation as a threat to job security. How does your team actually feel about that?** We think the framing is wrong — a team of 3 engineers running an AI agent should be able to manage infrastructure that would normally need 8. Does that land as a feature or a threat from where you sit?

11. **What would it take for you to actually trust an AI agent's diagnosis over your own first instinct?** Not a policy-level answer — the real answer. Is it a track record? A confidence score? The ability to see the exact reasoning? Something else? This matters enormously for how we design the interface.

### Trust & Adoption (2-3 min)

7. **Would you let an AI agent restart a pod in staging without asking? What about prod?** We have an environment-scoped permission mode (auto on staging, always ask on prod). Does that map to how your team would actually want to use it?

8. **Do you currently have any automation that takes action without human approval?** If yes — what earned that trust? If no — what would it take?

---

## Questions to Ask BOTH (if time permits)

- **What's the single biggest lie vendor tools tell you about "automated remediation"?** Help us avoid the same trap.
- **If Lear's audit log showed you every action it took, its reasoning, and whether it was right — would that change your willingness to let it act?** We're betting on transparency as the trust mechanism.

---

> **Prep note:** Bring a 90-second live demo of `prash fix` on a crash-looping pod if possible — showing diagnosis → recommendation → approval → action → verification. Don't explain architecture; let them react to the product first, then ask the questions.
