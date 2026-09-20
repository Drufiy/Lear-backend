# Hosting & Deployment Strategy — Autopilot Mode

**Owner:** TBD  
**Status:** Not started  
**Priority:** Tier 3  

---

## Problem

§2 of PRASH_V2.md describes Autopilot mode: Lear runs 24/7 watching prod while the team sleeps. But §7 explicitly says "no hosted layer for v2 this sprint." This needs a deployment strategy for startups that don't want to babysit infra for their infra tool.

---

## Tasks

### T1. Self-hosted deployment options
- [ ] Docker image for Lear agent (lightweight Python container)
- [ ] `docker-compose.yml` for single-machine deployment
- [ ] Helm chart for K8s-hosted Lear agent (watch K8s from inside K8s)
- [ ] Systemd service file for bare-metal Linux

### T2. Cloud-hosted lightweight options
- [ ] AWS Fargate task definition (no server to manage)
- [ ] AWS Lambda on CloudWatch Events schedule (cheapest, 5-min poll)
- [ ] GCP Cloud Run (serverless, scales to zero)
- [ ] Azure Container Instances

### T3. Credential management in hosted mode
- [ ] Credentials must still be local-to-the-deployment (not Drufiy servers)
- [ ] Secrets Manager integration (AWS Secrets Manager, GCP Secret Manager)
- [ ] Environment variable injection (ECS task definitions, K8s Secrets)
- [ ] `.env` file mounted as volume

### T4. Near-zero onboarding (§2 hard requirement)
- [ ] `curl -sSL https://get.lear.dev | sh` → installs and starts
- [ ] `prash setup` wizard runs during deployment
- [ ] No platform-engineer-required install

---

## Acceptance Criteria

- [ ] At least one self-hosted option (Docker) documented and working
- [ ] Credential security maintained in all deployment modes
- [ ] Onboarding takes < 5 minutes for a startup engineer
