# Incident Copilot — Competitor Intel (2026-02-18)

> Focus: incident management + on-call + “AI SRE/AIOps” tooling. Sources include GitHub repos, public product/pricing pages, blogs, Reddit threads (via old.reddit.com to avoid bot challenges), Product Hunt listings, and Hacker News discussions.

---

## Executive summary (opportunities)

**Clear market signals / gaps to exploit:**

1. **Pricing opacity & “legacy tax” fatigue**
   - Strong community frustration with per-user pager pricing and sales-led opacity.
   - Opportunity: **transparent pricing**, “pay for outcomes” (investigations / resolved alerts), or usage-based with caps.

2. **On-call + incident response convergence**
   - Multiple vendors now bundle paging/on-call + incident management + status pages (incident.io; Rootly; FireHydrant).
   - Opportunity: differentiate with **best-in-class incident workspace** (timeline, evidence, decision log) + **automation that stays correct** (validation, drift detection).

3. **OSS “OnCall” gap emerging**
   - Grafana OnCall OSS is in maintenance mode and set to be archived **2026-03-24**.
   - Opportunity: capture OSS-first buyers with a **supported open-core** or **migration toolkit** that’s actually turnkey.

4. **AI claims are everywhere; trust, control, and auditability are still weak**
   - Vendors market AI summaries/transcripts/“agentic SRE”. Buyers still worry about correctness, security, and hallucinations.
   - Opportunity: **explainable AI** with citations, deterministic runbooks, permissions, approvals, and compliance-grade audit trails.

5. **“Incidents page” killer features are: timeline + comms + roles + automation + learning loop**
   - Most products emphasize Slack/Teams integration, status updates, and post-incident retros.
   - Opportunity: make the incidents page a **command center** that is also a **forensic notebook**: evidence graph, correlated signals, suggested hypotheses, and “why we think this” + one-click export to postmortem.

---

## Competitor deep dives

### 1) Rootly

**Positioning (2026):** “AI SRE agents” + on-call + incident response + retrospectives + status pages.

**Key features (what their incidents experience emphasizes):**
- **Slack/Teams-native incident response** workflows and roles.
- **AI assistants** (chat, “similar incidents”, meeting bot/scribe, AI retrospectives) and automation.
- Playbooks/runbooks surfaced at incident declaration, task tracking, and comms automation.
- Extensibility: API/CLI/webhooks + Terraform provider + integrations.

**Pricing model:**
- Incident Response “Essentials” shown at **$20 per user/month**; Enterprise is “Contact us”.
- Add-ons and feature gating are visible on the pricing page (comms/status pages, AI, RBAC, etc.).

**What users love / hate (from community):**
- Loves: “extraordinarily responsive support”, flexibility, UI/UX perceived as easy under stress.
- Complaints: pricing opacity in the space in general; desire for more explicit numbers (community sentiment is broad, not Rootly-specific).

**Incidents page / killer features (inferred from product pages):**
- “Run your incident without leaving Slack” + roles + automations + comms.
- Strong emphasis on rapid adoption and opinionated defaults.

**Gaps / vulnerabilities:**
- Heavier platform surface area (IR + on-call + AI SRE + status pages) can mean **complexity** and **pricing confusion**.
- AI features: opportunity to outcompete with **verifiable RCA** and “why” explanations.

**Sources:**
- Rootly homepage (AI SRE / on-call / IR / retros / status pages): https://rootly.com/
- Rootly pricing (Essentials $20/user/mo + enterprise): https://rootly.com/pricing
- Rootly incident response (Slack) page: https://rootly.com/incident-response-slack
- Rootly social links (X, LinkedIn) are linked on homepage footer: https://rootly.com/
- Reddit thread with multiple Rootly-positive comments (old Reddit):
  - https://old.reddit.com/r/sre/comments/11dcxrn/rootly_vs_firehydrant_any_experience/

---

### 2) FireHydrant

**Positioning:** “All-in-one incident management” + on-call/alerting (“Signals”) + runbooks + service catalog + AI-enriched incident lifecycle.

**Notable company event:**
- Banner states FireHydrant **has been acquired by Freshworks**.

**Key features (what their incidents experience emphasizes):**
- Incident lifecycle: prepare → respond → improve.
- **Automated runbooks**, **on-call & alerting**, **service catalog**, Slack/Teams collaboration.
- **AI Insights**: updates/transcripts/retros/follow-ups; “Triage Channels” (ask anything, get context).

**Pricing model (public page):**
- “Trial Account” tier (limits like up to 10 responders, 2 runbooks, 1 public status page, 3 integrations).
- “Platform Pro” and “Enterprise” are **sales-led** (“Talk to us”).

**What users love / hate (signals):**
- Loves: end-to-end lifecycle + enterprise readiness + API-first posture.
- Hate: pricing opacity (common complaint in category; see Reddit/HN).

**Incidents page / killer features:**
- Strong “single platform” narrative: runbooks + status pages + retros + analytics + AI summaries/transcripts.

**Gaps / vulnerabilities:**
- Post-acquisition: potential for **roadmap uncertainty**, pricing changes, or slower iteration.
- Still largely sales-led pricing; opportunity to win with transparency.

**Sources:**
- FireHydrant homepage (features + acquisition banner): https://www.firehydrant.com/
- FireHydrant pricing page (Trial Account / Pro / Enterprise): https://www.firehydrant.com/pricing/
- FireHydrant acquisition blog link (from homepage banner): https://www.firehydrant.com/blog/firehydrant-to-be-acquired-by-freshworks
- FireHydrant GitHub org link (from site footer): https://github.com/firehydrant

---

### 3) incident.io

**Positioning:** “All-in-one AI platform for on-call, incident response, and status pages” with strong Slack/Teams integration and UX.

**Key features / recent launches implied:**
- **On-call** (alert routing/grouping/insights, schedules, overrides, call routing).
- **Response** (end-to-end incident mgmt) + workflows/automation.
- **Status Pages**.
- **AI**: Scribe, suggestions, AI chat agent, postmortem tooling (beta).

**Pricing model (transparent):**
- **Basic: Free forever**.
- **Pro: $25 per user/month** (Incident Response).
- On-call add-on pricing is listed (e.g., +$10 or +$20 per user/month depending on plan).
- Enterprise: “Let’s talk”.

**What users love / hate (signals):**
- Loves: “one tool in the same context” reduces cognitive overload; high UX emphasis.
- Hate: still a per-user model at scale; buyers compare vs PagerDuty cost.

**Incidents page / killer features:**
- “Incident command center”: integrated on-call + response + AI + status pages.
- Emphasis on **opinionated defaults** and rapid adoption.

**Gaps / vulnerabilities:**
- Bundled pricing can still feel like “paying for a pager”; opportunity: “incident copilots” that deliver measurable reduction in toil.
- If AI is central, buyers will demand controls + auditability; opportunity to lead with **compliance-grade incident evidence trails**.

**Sources:**
- incident.io homepage: https://incident.io/
- incident.io pricing (Basic free, Pro $25/user/mo, add-on on-call): https://incident.io/pricing
- Reddit discussion where incident.io staff describe “opinionated defaults” vs flexibility (in Rootly vs FireHydrant thread):
  - https://old.reddit.com/r/sre/comments/11dcxrn/rootly_vs_firehydrant_any_experience/
- HN discussion snippet mentioning replacing PagerDuty vs incident tool + pager value (see HN item):
  - https://news.ycombinator.com/item?id=39727079

---

### 4) Shoreline (incident automation)

**Positioning:** Incident automation / “repair” runbooks executed against production fleet; focuses on real-time debugging and automated remediation.

**Key features (from third-party descriptions):**
- Real-time debugging across fleet + executable runbooks/automations.
- Integrations with monitoring/paging; RBAC/audit logging; web/CLI.

**Market/PR signals:**
- Multiple sources reference **Nvidia reportedly acquiring Shoreline** (unconfirmed in the snippet).

**Pricing model:**
- No direct first-party pricing captured in this pass (sources point to third-party directories).

**Incidents page / killer features:**
- “Incident automation” angle: from alert → automated remediation.

**Gaps / vulnerabilities:**
- Automation products often struggle with **runbook drift** and **safety** (who approved what, what changed).
- If acquisition rumors/changes are real, buyers may fear lock-in and seek alternatives.

**Sources:**
- AWS APN blog: “Spend Less Time on Calls… Shoreline Incident Automation on AWS” (search result):
  - https://aws.amazon.com/blogs/apn/spend-less-time-on-calls-and-more-on-innovation-with-shoreline-incident-automation-on-aws/
- Nvidia reportedly acquires Shoreline (SiliconANGLE):
  - https://siliconangle.com/2024/06/19/nvidia-reportedly-acquires-incident-automation-startup-shoreline-100m/
- ChannelInsider mention: “cloud automation & incident management with Shoreline.io”:
  - https://www.channelinsider.com/security/managed-services/cloud-automation-incident-management-shoreline-io/

---

### 5) NeuBird (agentic AI SRE)

**Positioning:** “Agentic AI SRE” (Hawkeye) for autonomous incident investigation and resolution, promising large MTTR reduction.

**Key features:**
- Investigation-centric AI agent; integrates with telemetry; produces RCA and remediation guidance.
- Escalation workflows; incident analytics / MTTR reporting.

**Pricing model (notably different):**
- **Investigation-centric pricing**:
  - Pay-as-you-go: **$25 per qualifying investigation** (explicit in FAQ).
  - Starter: 20 investigations/month (price not shown in snapshot; contact).
  - Enterprise: contact.
- Claims “No hidden fees. No ingest cost. No storage cost.”

**What users love/hate (signals):**
- The model itself addresses a common complaint: ingest/storage-based surprise billing.
- Risk: “per investigation” may be hard to forecast; buyers need clear definitions.

**Incidents page / killer features:**
- The product value is “investigation outcome” rather than traditional incident workspace.

**Gaps / vulnerabilities:**
- AI agent credibility: must prove correctness, security, and safe actions.
- The category is noisy; opportunity: ship “agentic” but **bounded** with approvals and reproducible steps.

**Sources:**
- NeuBird pricing (PAYGO $25/investigation; no ingest/storage cost): https://neubird.ai/pricing/
- NeuBird homepage (agentic AI SRE positioning): https://neubird.ai/
- NeuBird press (BusinessWire result surfaced in search):
  - https://www.businesswire.com/news/home/20260204450140/en/NeuBird-AI-Experiences-Rapid-Adoption-of-its-AI-SRE-Agent-for-Incident-Resolution-Across-Healthcare-Banking-Retail-and-High-Tech/

---

### 6) Grafana OnCall (OSS) / Grafana Cloud IRM

**Positioning:** Developer-friendly incident response + strong Slack integration; OSS offering exists but is being wound down.

**Key features (OSS repo README):**
- Collect/analyze alerts from multiple monitoring systems.
- On-call rotations/schedules.
- Escalations.
- Notifications via phone/SMS/Slack/Telegram.

**Major change / “recent launch” signal:**
- OSS entered maintenance mode **2025-03-11** and will be archived **2026-03-24**; only critical bug/CVE fixes until then.
- Grafana recommends **Grafana Cloud IRM** as supported alternative.

**Pricing model:**
- OSS: self-hosted.
- Cloud IRM: SaaS (pricing not captured here).

**What users love/hate (signals):**
- Love: “brilliant Slack integration”, broad notification channels.
- Hate/risk: OSS maintenance mode creates adoption risk and migration burden.

**Incidents page / killer features:**
- For OSS, “incidents page” is primarily on-call + alert aggregation and escalations.

**Gaps / vulnerabilities:**
- OSS sunset creates a **migration wedge**: teams need easy exports, parity mapping, and confidence.

**Sources:**
- Grafana OnCall OSS repo (stars ~3.9k; maintenance mode + archive date; feature list): https://github.com/grafana/oncall
- Grafana blog post linked from README (maintenance mode): https://grafana.com/blog/2025/03/11/grafana-oncall-maintenance-mode/
- Grafana blog post linked from README (Grafana Cloud IRM announcement): https://grafana.com/blog/2025/03/11/oncall-management-incident-response-grafana-cloud-irm/

---

### 7) PagerDuty (and OSS/open tooling around it)

**Positioning:** Category leader in paging/on-call; ecosystem includes many open repos (clients, Terraform provider, incident response docs).

**Notable GitHub repos (signals of ecosystem + features):**
- `incident-response-docs` — PagerDuty’s incident response documentation (**~1k stars**).
- `terraform-provider-pagerduty` — Terraform provider (**~216 stars**).
- `go-pagerduty` — Go client library.
- `pagerduty-mcp-server` — (newer) MCP server for PagerDuty (visible in org repo list).

**Pricing model:**
- Not captured from first-party pricing pages here.
- Community sentiment indicates dissatisfaction with per-user pager pricing.

**What users love/hate (from HN sentiment snippet):**
- Hate: paying “pager app” prices; desire to replace PagerDuty with bundled incident tooling.

**Incidents page / killer features:**
- PagerDuty “incidents” experience typically centers on alert → escalation → acknowledgement; broader incident mgmt often done elsewhere.

**Gaps / vulnerabilities:**
- “Pager-only value” perceived as low vs its cost; opportunity: deliver more incident lifecycle value with lower friction.

**Sources:**
- PagerDuty GitHub org (popular repos + stars): https://github.com/PagerDuty
- PagerDuty `incident-response-docs` repo: https://github.com/PagerDuty/incident-response-docs
- PagerDuty Terraform provider repo: https://github.com/PagerDuty/terraform-provider-pagerduty
- HN comment about PagerDuty cost/value framing:
  - https://news.ycombinator.com/item?id=39727079

---

### 8) Opsgenie → Atlassian Operations / Jira Service Management / Compass

**Positioning:** Opsgenie historically on-call; now being transitioned under Atlassian’s ops tooling.

**Key signals:**
- Open-source Opsgenie Terraform provider exists and has recent commits (latest commit shown as **Oct 28, 2025** in repo view).
- Atlassian now has `terraform-provider-atlassian-operations` described as a “functional replication of the now transitioned Opsgenie Provider.”

**Pricing model:**
- Not captured directly here.

**What users love/hate (HN sentiment):**
- HN thread about “Atlassian announces end of support for Opsgenie” contains migration discussion and criticism about botched unification/login.

**Incidents page / killer features:**
- Strong integration in Atlassian ecosystem (JSM, Compass catalog).

**Gaps / vulnerabilities:**
- Forced migrations (Opsgenie EOL) create churn and distrust; opportunity: provide **migration utilities** and **better UX**.

**Sources:**
- Opsgenie Terraform provider repo (stars ~104; last commit Oct 28, 2025): https://github.com/opsgenie/terraform-provider-opsgenie
- Atlassian Operations Terraform Provider (described as successor/replication): https://github.com/atlassian/terraform-provider-atlassian-operations
- HN thread: “Atlassian announces end of support for Opsgenie”: https://news.ycombinator.com/item?id=43283178

---

## OSS / GitHub landscape (beyond the big vendors)

These are not “direct SaaS competitors” to Rootly/incident.io/FireHydrant, but they matter for:
- OSS-first buyer expectations
- feature benchmarking
- acquisition targets / integration opportunities

**Notable repos (from GitHub topic page):**
- `OneUptime/oneuptime` (**~6.5k stars**) — “Complete open-source monitoring and observability platform” with incident-response/on-call/status-page tags.
- `monzo/response` (**~1.6k stars**) — real-time incident response and reporting tool.
- `HolmesGPT/holmesgpt` (**~1.9k stars**) — “24/7 on-call AI agent” idea.
- `incidentalhq/incidental` (**~558 stars**) — open-source Slack-integrated incident management platform.

**Sources:**
- GitHub topic page (incident-management): https://github.com/topics/incident-management
- OneUptime repo: https://github.com/OneUptime/oneuptime
- Monzo Response repo: https://github.com/monzo/response
- HolmesGPT repo: https://github.com/HolmesGPT/holmesgpt
- incidental repo: https://github.com/incidentalhq/incidental

---

## Reddit sentiment (SRE/DevOps)

**High-signal thread captured (Rootly vs FireHydrant):**
- Buyers value: **support responsiveness**, **platform flexibility**, and especially **UI/UX under stress**.
- Notable complaint: explicit ask for **meaningful pricing disclosure**.

**Sources:**
- Rootly vs FireHydrant discussion (old Reddit, includes multiple vendor and user comments):
  - https://old.reddit.com/r/sre/comments/11dcxrn/rootly_vs_firehydrant_any_experience/

---

## Hacker News sentiment (pricing, migrations, new AI on-call tools)

**Themes observed in surfaced HN items/snippets:**
- “Pager app” pricing frustration (desire to replace PagerDuty).
- Migration angst: Opsgenie end-of-support and Atlassian ecosystem consolidation.
- Continued interest in AI for on-call engineers and runbook execution.

**Sources:**
- HN item containing PagerDuty cost/value discussion snippet: https://news.ycombinator.com/item?id=39727079
- HN: “Atlassian announces end of support for Opsgenie”: https://news.ycombinator.com/item?id=43283178
- Launch HN: Parity (AI for on-call engineers): https://news.ycombinator.com/item?id=41357765
- Show HN: pricing frustration with PagerDuty et al. (build-your-own): https://news.ycombinator.com/item?id=35675029

---

## Product Hunt (newer / discoverability signals)

**Interesting listings discovered via search:**
- On-Call Health (open source burnout / load visibility tool) — launched/featured 2026-02-11.
- Shoreline Incident Insights (free analysis tool).
- “Incident/Ops” listing claiming free tier with incident tracking + AI postmortems + on-call.

**Sources:**
- Product Hunt: On-Call Health: https://www.producthunt.com/products/on-call-health
- Product Hunt: Shoreline Incident Insights: https://www.producthunt.com/products/shoreline-incident-insights
- Product Hunt: Incident/Ops: https://www.producthunt.com/products/incident-ops

---

## X/Twitter + LinkedIn (what we could reliably source in this pass)

Direct “recent posts” on X are often gated; in this pass we captured **official profile links** from vendor sites and **LinkedIn post URLs** surfaced by search for NeuBird.

**Sources:**
- Rootly X profile (linked from Rootly site): https://x.com/rootlyhq
- incident.io X profile (linked from incident.io site): https://x.com/incident_io
- FireHydrant X profile (linked from FireHydrant site): https://x.com/FireHydrant
- NeuBird LinkedIn post URL (surfaced in search results):
  - https://www.linkedin.com/posts/neubird-ai_agenticai-aiops-generativeai-activity-7385047647251947520-hTae

---

## Suggested differentiation strategy for “Incident Copilot”

1. **Trustworthy incident intelligence**
   - Every AI suggestion must cite data sources (log line, metric anomaly, deploy, ticket, past incident) and show confidence.

2. **Runbook automation that doesn’t rot**
   - Detect drift (changed endpoints/flags), validate preconditions, simulate/dry-run, require approvals, and record audit artifacts.

3. **The best incidents page in the industry**
   - Timeline auto-capture + decision log + evidence attachments + “hypothesis board” + comms drafts + postmortem auto-fill.

4. **Migration as a wedge**
   - Grafana OnCall OSS → new platform, Opsgenie EOL → new platform, PagerDuty cost pressure → new platform.

5. **Transparent pricing**
   - Provide a simple calculator (per responder or per investigation) and published ranges to reduce sales friction.

---

*Prepared 2026-02-18. If you want, next iteration can add:* (a) deeper repo-level feature extraction by reading key READMEs/CHANGELOGs; (b) more Reddit threads (r/devops, r/kubernetes) now that old.reddit access pattern is known; (c) a structured feature matrix across competitors.
