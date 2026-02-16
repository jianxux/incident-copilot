# Competitor analysis: incident management & on-call automation (2026-02-16)

> **Method note (source coverage constraints):** G2 and Capterra pages were not reliably fetchable in this environment due to anti-bot protections (403 / JS-required). Where possible, I used **first‑party pricing/feature pages**, **official docs**, **Wayback snapshots** (for Opsgenie pricing that is no longer sold), plus **Hacker News / Reddit threads** that were accessible.

---

## 1) incident.io

- **URL:** https://incident.io/

### Pricing (published)
- **Basic:** Free (incident management + “single team on-call”) — [incident.io pricing](https://incident.io/pricing)
- **Team:** **$15/user/month** (annual) for Incident Response; **On-call add-on +$10/user/month** — [incident.io pricing](https://incident.io/pricing)
- **Pro:** **$25/user/month** for Incident Response; **On-call add-on +$20/user/month** — [incident.io pricing](https://incident.io/pricing)
- **Enterprise:** “Let’s talk” (custom) — [incident.io pricing](https://incident.io/pricing)
- **On-call standalone:** **$20/user/month** — [incident.io pricing](https://incident.io/pricing)

### Key features (what they emphasize)
- **Slack/Teams-native incident response** — [incident.io pricing](https://incident.io/pricing)
- **AI capabilities surfaced in plan comparison:** “Suggestions”, “Scribe”, “AI chat agent”, “AI Tooling (Beta)” (higher tiers) — [incident.io pricing](https://incident.io/pricing)
- **Status pages** (incl. custom domain / multiple pages in higher tiers) — [incident.io pricing](https://incident.io/pricing)
- **On-call + alert routing/grouping** — [incident.io pricing](https://incident.io/pricing)
- **Custom post-incident processes / advanced insights** (Pro+) — [incident.io pricing](https://incident.io/pricing)
- **Enterprise security features** (SAML/SCIM, advanced access control, etc.) — [incident.io pricing](https://incident.io/pricing)

### Positioning
- Consolidated “trifecta” story (alerting + response + comms) discussed publicly by leadership: On-call + Response + Status Pages — [HN thread quoting incident.io CEO](https://news.ycombinator.com/item?id=39727079)

### What users complain about (examples)
- **Perception that the product is a “luxury” until paired with paging** (harder to justify incident process tooling alone; easier sell as PagerDuty replacement) — [HN discussion](https://news.ycombinator.com/item?id=39727079)
- **SSO/identity expectations:** a user said **“SSO being locked behind enterprise service levels makes it a non-starter”** — [HN discussion](https://news.ycombinator.com/item?id=39727079)
  - Note: incident.io co-founder replied that **SAML is on Pro+ and SCIM is Enterprise-only** — [HN discussion](https://news.ycombinator.com/item?id=39727079) and plan comparison shows **SCIM only in Enterprise** — [incident.io pricing](https://incident.io/pricing)

### Gaps we can exploit
- **Price stacking**: incident response + on-call add-ons can add up quickly (e.g., Pro $25 + On-call $20) — [incident.io pricing](https://incident.io/pricing)
- **AI appears as “tooling/beta” vs. end-to-end context assembly**: plans list AI features, but mostly framed as in-product assistants (“AI chat agent”, “Scribe”) rather than an autonomous **context-assembling copilot across your toolchain** — [incident.io pricing](https://incident.io/pricing)
- **SaaS + workflow lock-in risk**: the “trifecta” pitch implies replacing multiple tools; opportunity for a tool that integrates without forcing consolidation — [HN thread](https://news.ycombinator.com/item?id=39727079)

---

## 2) FireHydrant

- **URL:** https://firehydrant.com/

### Pricing (published)
- **Trial account:** Free for two weeks (includes limits like “Up to 10 responders”, “2 runbooks”, etc.) — [FireHydrant pricing](https://firehydrant.com/pricing/)
- **Platform Pro:** **$9,600/year** (includes “Up to 20 responders”) — [FireHydrant pricing](https://firehydrant.com/pricing/)
- **Enterprise:** Custom pricing — [FireHydrant pricing](https://firehydrant.com/pricing/)
- **Signals on-call & alerting:** billed based on alerts (“Signals is charged based on the number of alerts you send”) — [FireHydrant pricing](https://firehydrant.com/pricing/)

### Key features
- **Incident management**: runbooks, chatbot, retrospectives, status pages, service catalog, custom fields, integrations — [FireHydrant pricing](https://firehydrant.com/pricing/)
- **On-call scheduling / escalation policies** + multi-channel notifications — [FireHydrant pricing](https://firehydrant.com/pricing/)
- **FireHydrant AI** (Enterprise): “summaries, meeting transcripts, triage, retros, follow ups” — [FireHydrant pricing](https://firehydrant.com/pricing/)
- **SSO / SCIM / audit logs / exports** (Enterprise) — [FireHydrant pricing](https://firehydrant.com/pricing/)
- **Acquisition note:** pricing page banner indicates FireHydrant “has been acquired by Freshworks” — [FireHydrant pricing](https://firehydrant.com/pricing/)

### Positioning
- “All-in-One Incident Management, Without the Legacy Tax” + cost-savings messaging — [FireHydrant pricing](https://firehydrant.com/pricing/)

### What users complain about (examples)
- **Alerting cost model complexity**: on-call/alerting (Signals) billed on alert volume, not purely per-seat — [FireHydrant pricing](https://firehydrant.com/pricing/)
- **Risk of product direction shifts after acquisition** (common buyer concern; not a direct quote complaint here, but acquisition is explicit and may impact procurement comfort) — [FireHydrant pricing](https://firehydrant.com/pricing/)

### Gaps we can exploit
- **Responder-count packaging** (e.g., Pro “Up to 20 responders”) can become awkward for fast-growing orgs — [FireHydrant pricing](https://firehydrant.com/pricing/)
- **AI appears concentrated in Enterprise** (FireHydrant AI only called out there) — [FireHydrant pricing](https://firehydrant.com/pricing/)
- **Alert-volume billing** creates unpredictable spend; opportunity for transparent/self-hostable pricing and better cost control — [FireHydrant pricing](https://firehydrant.com/pricing/)

---

## 3) Rootly

- **URL:** https://rootly.com/

### Pricing (published)
- **Essentials:** **$20/user/month** — [Rootly pricing](https://rootly.com/pricing)
- **Enterprise:** Contact us — [Rootly pricing](https://rootly.com/pricing)
- Startup programs: “save up to 50%” (criteria) and “pay what you can” (<25 employees) — [Rootly pricing FAQ](https://rootly.com/pricing)

### Key features
- “Response with Slack” and “Response with Microsoft Teams” — [Rootly pricing](https://rootly.com/pricing)
- Rootly AI features listed: “@Rootly AI Chat”, “AI Similar Incidents”, “AI Scribe Meeting Bot”, “AI Retrospectives” — [Rootly pricing](https://rootly.com/pricing)
- Status page + mobile app included in Essentials — [Rootly pricing](https://rootly.com/pricing)
- Enterprise features: custom incident types/forms, private incidents, secrets management, audit logs, advanced workflows, SCIM — [Rootly pricing](https://rootly.com/pricing)
- BYO AI Key: “OpenAI, Anthropic, Gemini” (noted in feature comparison) — [Rootly pricing](https://rootly.com/pricing)

### Positioning
- “AI that works across your code, telemetry, and infrastructure” marketing line on the pricing page — [Rootly pricing](https://rootly.com/pricing)

### What users complain about (examples)
- Setup/config as “toolkit” risk: a Reddit comparison post described one competitor in this space as **“a toolkit… tons of configuration options”** (reflects a common market complaint: too much setup/too many knobs vs an opinionated flow) — [r/cybersecurity comparison thread](https://www.reddit.com/r/cybersecurity/comments/1kz9we5/firehydrantblameless_vs_incidentio_thoughts_from/)
  - (Note: this is an adjacent thread and not a verified Rootly review page; included as qualitative signal.)

### Gaps we can exploit
- **Still SaaS-first**; even with “BYO AI key”, workflows and data model live in vendor platform — [Rootly pricing](https://rootly.com/pricing)
- **AI claims are broad**; opportunity for a copilot that *actually assembles context* (logs/metrics/deploy diffs/tickets) automatically and produces actionable briefings without heavy configuration — [Rootly positioning line](https://rootly.com/pricing)

---

## 4) PagerDuty (focus on AI)

- **URL:** https://www.pagerduty.com/

### Pricing (Incident Management plans)
From PagerDuty’s Incident Management pricing page:
- **Free:** **$0/month**, up to 5 users — [PagerDuty IM pricing](https://www.pagerduty.com/pricing/incident-management/)
- **Professional:** **$21/user/month** (annual) (page shows “$25 $21 per user / month”) — [PagerDuty IM pricing](https://www.pagerduty.com/pricing/incident-management/)
- **Business:** **$41/user/month** (annual) (page shows “$49 $41 per user / month”) — [PagerDuty IM pricing](https://www.pagerduty.com/pricing/incident-management/)
- **Enterprise:** Custom pricing — [PagerDuty IM pricing](https://www.pagerduty.com/pricing/incident-management/)

### AI features (PagerDuty Advance / Copilot / Agents)
- PagerDuty Advance described as “generative and agentic AI capabilities” across the Operations Cloud — [PagerDuty Advance docs](https://support.pagerduty.com/main/docs/pagerduty-advance)
- Advance includes: Assistant, AI Agents, “Status Updates”, “Post‑Incident Reviews”, “Automation Digest”, “AI Generated Runbooks” — [PagerDuty Advance docs](https://support.pagerduty.com/main/docs/pagerduty-advance)
- Public feature list includes **persona-based status updates**, **in-chat assistant for Slack/Teams**, and **AI Agents** (SRE Agent, Insights Agent, Shift Agent) — [PagerDuty Generative AI / Advance page](https://www.pagerduty.com/platform/generative-ai/)
- “Professional” plan includes **“PagerDuty Advance (1,000 one-time credits)”** — [PagerDuty IM pricing](https://www.pagerduty.com/pricing/incident-management/) and packaging announcement reiterates **“1,000 PagerDuty Advance Credits”** in Professional — [PagerDuty blog (packaging)](https://www.pagerduty.com/blog/product/new-incident-management-csops-plans-entitlements/)

### Positioning
- “single platform” consolidation value called out by analyst quote (IDC) as a differentiator in coverage: AIOps + automation + root causes etc. — [CIO coverage](https://www.cio.com/article/2119456/pagerduty-seeks-to-ease-incident-response-with-generative-ai.html)

### What users complain about (examples)
- **Cost sensitivity / value mismatch** is a recurring theme: “PagerDuty is too expensive” — [r/devops thread](https://old.reddit.com/r/devops/comments/xl1tjy/pagerduty_is_too_expensive/)

### Gaps we can exploit
- **Complexity / platform breadth → bloat risk** (large suite; many teams only want a context copilot + routing) — implied by packaging breadth and add-ons like AIOps / Stakeholder licenses — [PagerDuty IM pricing](https://www.pagerduty.com/pricing/incident-management/) and AI credits/add-ons language — [PagerDuty Generative AI page](https://www.pagerduty.com/platform/generative-ai/)
- **AI as metered “credits”**: usage-based add-on model creates budgeting friction; opportunity for predictable/self-hosted AI costs — [PagerDuty IM pricing](https://www.pagerduty.com/pricing/incident-management/) and “add on credits for AI consumption” — [PagerDuty Generative AI page](https://www.pagerduty.com/platform/generative-ai/)

---

## 5) Opsgenie (Atlassian)

- **URL:** https://www.atlassian.com/software/opsgenie

### Status / lifecycle
- Atlassian states Opsgenie is **no longer available for purchase** effective **June 4, 2025**, and **end of support April 5, 2027** — [Atlassian Opsgenie pricing/migration notice](https://www.atlassian.com/software/opsgenie/pricing) and [Atlassian licensing notice](https://www.atlassian.com/licensing/opsgenie)

### Pricing tiers (historical; Wayback snapshot)
Because Atlassian’s current Opsgenie pricing page is now a migration notice, the **latest public per-user pricing** I could reliably cite comes from an archived snapshot:
- **Free:** $0 up to 5 users — [Wayback snapshot of Atlassian Opsgenie pricing (2024-02-08)](https://web.archive.org/web/20240208183210/https://www.atlassian.com/software/opsgenie/pricing)
- **Essentials:** **$9/user/month billed annually** (or **$11** billed monthly) — [Wayback snapshot](https://web.archive.org/web/20240208183210/https://www.atlassian.com/software/opsgenie/pricing)
- **Standard:** **$19/user/month billed annually** (or **$23** billed monthly) — [Wayback snapshot](https://web.archive.org/web/20240208183210/https://www.atlassian.com/software/opsgenie/pricing)
- **Enterprise:** **$29/user/month billed annually** (or **$35** billed monthly) — [Wayback snapshot](https://web.archive.org/web/20240208183210/https://www.atlassian.com/software/opsgenie/pricing)

### Key features (from archived comparison)
- On-call management (routing rules, schedules, escalations), integrations, incident features, reporting, etc. — [Wayback snapshot (feature comparison table)](https://web.archive.org/web/20240208183210/https://www.atlassian.com/software/opsgenie/pricing)

### What users complain about (examples)
- **Migration anxiety / loss of feature parity** moving into Jira Service Management: concerns about Slack alert delivery and fine-grained on-call permissions — [r/jira thread](https://old.reddit.com/r/jira/comments/1eaxyw4/frustrated_with_the_migration_of_opsgenie_to_jira/)
- **Product shutdown uncertainty**: community discussing end-of-support timeline — [r/sysadmin thread quoting Atlassian email](https://old.reddit.com/r/sysadmin/comments/1j53j60/atlassian_shutting_down_opsgenie/)

### Gaps we can exploit
- **Forced migration / vendor strategy risk**: end-of-sale and shutdown dates create churn opportunity — [Atlassian notice](https://www.atlassian.com/software/opsgenie/pricing)
- **Teams want on-call tooling without switching ticketing/workflow stacks** (explicit in migration threads) — [r/jira thread](https://old.reddit.com/r/jira/comments/1eaxyw4/frustrated_with_the_migration_of_opsgenie_to_jira/)

---

## 6) Grafana OnCall (OSS + Cloud)

- **URL (Cloud product):** https://grafana.com/products/cloud/oncall/
- **URL (OSS repo):** https://github.com/grafana/oncall

### Pricing (Grafana Cloud IRM / OnCall)
- **Free:** $0, limited to **3 active IRM users per month** — [Grafana OnCall product page](https://grafana.com/products/cloud/oncall/)
- **Pro:** **$20 / active IRM user** (pay-as-you-go) + **$19/month platform fee** — [Grafana OnCall product page](https://grafana.com/products/cloud/oncall/)
- **Enterprise:** Custom; minimum **$25,000/year** commit — [Grafana OnCall product page](https://grafana.com/products/cloud/oncall/)

### Key features (Cloud)
- “Context-rich notifications” (metrics/logs/related info), escalation chains, schedules, multiple notification channels (Slack/Teams/Telegram/SMS/phone/email), mobile app, integrations with observability/ITSM tools — [Grafana OnCall product page](https://grafana.com/products/cloud/oncall/)

### OSS limitations (important)
- Grafana OnCall OSS entered **maintenance mode** (2025-03-11) and will be **archived on 2026-03-24**; no new features, only critical fixes/CVEs — [Grafana docs: maintenance mode notice](https://grafana.com/docs/oncall/latest/set-up/open-source/)
- After 2026-03-24, OSS users lose **Cloud Connection** support including **mobile push notifications** and **SMS/phone** if relying on Grafana Cloud connection — [Grafana docs](https://grafana.com/docs/oncall/latest/set-up/open-source/)

### Gaps we can exploit
- **OSS is effectively end-of-innovation**; a new open source (BSL) alternative can capture teams that want self-hosting without a dead-end roadmap — [Grafana docs](https://grafana.com/docs/oncall/latest/set-up/open-source/)
- **Active-user pricing + platform fee** can be confusing; opportunity for simple pricing and self-hosted option — [Grafana OnCall product page](https://grafana.com/products/cloud/oncall/)

---

## 7) Squadcast (SolarWinds IT Incident Response)

- **URL:** https://www.squadcast.com/pricing

### Pricing (published)
From the pricing page (rendered text):
- **Pro:** **$9/user/month** (billed annually) — [Squadcast pricing](https://www.squadcast.com/pricing)
- **Premium:** **$16/user/month** (billed annually) — [Squadcast pricing](https://www.squadcast.com/pricing)
- **Enterprise:** Custom — [Squadcast pricing](https://www.squadcast.com/pricing)
- **Free plan:** supports up to **5 users** — [Squadcast pricing](https://www.squadcast.com/pricing)

### Key features
- Pro includes: RBAC, custom integrations via API, alerting (email/push/SMS/voice), schedules & escalations, postmortems with templates, automation rules, mobile apps — [Squadcast pricing](https://www.squadcast.com/pricing)
- Premium adds: stakeholders roles, data retention, advanced escalations, runbooks, incident workflows, outgoing webhooks, SLO tracker, status pages — [Squadcast pricing](https://www.squadcast.com/pricing)
- Enterprise adds: audit logs, “AI Generated Incident Summaries”, “Incident Suggestions”, “Past Incident Insights”, ServiceNow bi-directional sync — [Squadcast pricing](https://www.squadcast.com/pricing)

### What users complain about (examples)
- **Webhook integration constraints:** one user noted Squadcast “only accepts specific JSON format” for webhook ingestion to create a ticket/alert — [r/nutanix thread](https://old.reddit.com/r/nutanix/comments/1cgivr3/nutanix_squadcast_integration/)
- **Notifications are metered/charged in lower tiers** (potential cost surprises): additional SMS/calls billed (e.g., $0.10 per additional SMS/call in certain regions; $0.35 elsewhere) — [Squadcast pricing FAQ](https://www.squadcast.com/pricing)

### Gaps we can exploit
- **AI features appear Enterprise-only** (incident summaries/suggestions) — [Squadcast pricing](https://www.squadcast.com/pricing)
- **Integration friction** (strict webhook payload format) → opportunity for “bring your data” ingestion adapters and LLM-based normalization — [r/nutanix thread](https://old.reddit.com/r/nutanix/comments/1cgivr3/nutanix_squadcast_integration/)

---

# Where Incident Copilot Wins

## 1) AI-first: auto-assembles context (not just workflow automation)
Most competitors’ AI is packaged as:
- **In-product assistants** (chat agent / scribe / summaries) — e.g., incident.io (“AI chat agent”, “Scribe”) — [incident.io pricing](https://incident.io/pricing)
- **Platform AI bundles with usage credits** (PagerDuty Advance credits, add-on consumption model) — [PagerDuty IM pricing](https://www.pagerduty.com/pricing/incident-management/) and [PagerDuty Generative AI page](https://www.pagerduty.com/platform/generative-ai/)

**Incident Copilot differentiation:** focus on **automatic, cross-tool context assembly** (deploy diffs, alerts, logs, traces, tickets, ownership, recent changes) with human-in-the-loop outputs.

## 2) Open source (BSL) vs closed SaaS
- Grafana OnCall OSS has entered maintenance mode and is scheduled for archival — [Grafana OSS maintenance notice](https://grafana.com/docs/oncall/latest/set-up/open-source/)

**Incident Copilot differentiation:** “open core” (BSL) gives teams a credible self-host story and an escape hatch.

## 3) No vendor lock-in
- Market discussions explicitly raise workflow/tool lock-in concerns in incident response platforms — [HN incident.io thread](https://news.ycombinator.com/item?id=39727079)
- Opsgenie shutdown/migration reinforces ecosystem risk — [Atlassian Opsgenie notice](https://www.atlassian.com/software/opsgenie/pricing)

**Incident Copilot differentiation:** keep the data + decisioning portable; operate as a layer over existing systems.

## 4) Integrates with existing tools rather than replacing them
- Competitors often pitch “replace PagerDuty + status pages + incident tool” bundles — [incident.io CEO on trifecta](https://news.ycombinator.com/item?id=39727079)

**Incident Copilot differentiation:** integrate into Slack/Teams + observability + ticketing + CMDB/service catalog, without forcing a consolidated vendor suite.
