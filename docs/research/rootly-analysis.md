# Rootly Open Source Ecosystem Analysis

**Date:** 2026-02-11
**Purpose:** Extract valuable patterns for our Incident Copilot (FastAPI, Python 3.11, Railway)

---

## 1. Executive Summary — What's Worth Borrowing

Rootly's open-source repos reveal a **mature incident management data model** that we should use as our north star for schema design. The key takeaways:

1. **Rich Incident Lifecycle Model** — Their incident struct has ~100 fields covering status progression (in_triage → started → mitigated → resolved → closed), deep Slack integration, and integrations with 20+ external tools. We should model our incident lifecycle similarly but start lean.

2. **Workflow Engine (Trigger → Condition → Action)** — Workflows are first-class resources with `trigger_params`, filtered by severity/service/environment/incident_type IDs. This is the pattern we need for our automation engine.

3. **Service Catalog with Integration IDs** — Services carry `backstage_id`, `pagerduty_id`, `opsgenie_id`, `cortex_id`, `github_repository_name` — they're the glue between external systems. We need this cross-reference pattern.

4. **Deployment Pulses** — Lightweight deployment event tracking (service + environment + labels + refs) that correlates deploys with incidents. Simple and effective — we should implement this.

5. **Python SDK uses httpx + async/sync dual interface** — Auto-generated from OpenAPI spec. Good pattern for our own API client layer.

---

## 2. Per-Repo Findings

### 2.1 terraform-provider-rootly (⭐ GOLDMINE for data model)
- **URL:** https://github.com/rootlyhq/terraform-provider-rootly
- **Key files:** [`client/incidents.go`](https://github.com/rootlyhq/terraform-provider-rootly/blob/main/client/incidents.go), [`client/workflows.go`](https://github.com/rootlyhq/terraform-provider-rootly/blob/main/client/workflows.go), [`client/services.go`](https://github.com/rootlyhq/terraform-provider-rootly/blob/main/client/services.go), [`client/severities.go`](https://github.com/rootlyhq/terraform-provider-rootly/blob/main/client/severities.go)

**Findings:** Auto-generated Go client from JSON:API schema. The `client/` directory contains one file per resource type, revealing Rootly's complete data model. All code is auto-generated from `tools/generate.js` pulling from Rootly's JSON-API schema.

**Complete resource list from `client/` directory:**
- **Core:** incidents, services, severities, environments, teams, functionalities, causes
- **Alerting:** alert_fields, alert_groups, alert_routes, alert_routing_rules, alert_urgencies, alerts_sources
- **Workflows:** workflows, workflow_groups, workflow_tasks, workflow_custom_field_selections, workflow_form_field_conditions
- **On-Call:** schedules, schedule_rotations, schedule_rotation_users, schedule_rotation_active_days, escalation_policies, escalation_levels, escalation_paths, on_call_roles, on_call_shadows, override_shifts, live_call_routers
- **Incident Details:** incident_types, incident_roles, incident_role_tasks, incident_sub_statuses, incident_permission_sets, incident_permission_set_booleans, incident_permission_set_resources, incident_form_field_selections, incident_post_mortems
- **Retrospectives:** retrospective_configurations, retrospective_processes, retrospective_process_groups, retrospective_process_group_steps, retrospective_steps, post_mortem_templates
- **Customization:** custom_fields, custom_field_options, custom_forms, form_fields, form_field_options, form_field_placements, form_field_placement_conditions, form_field_positions, form_sets, form_set_conditions
- **Communications:** communications_groups, communications_stages, communications_templates, communications_types
- **Infrastructure:** dashboards, dashboard_panels, heartbeats, secrets, status_pages, status_page_templates, webhooks_endpoints, authorizations, playbooks, playbook_tasks, roles, users, ip_ranges

### 2.2 rootly-python (Python SDK)
- **URL:** https://github.com/rootlyhq/rootly-python
- **Key insight:** Auto-generated from OpenAPI spec using `openapi-python-client`. Uses `httpx` for HTTP, Poetry for packaging, published as `rootly_sdk` on PyPI.

**API module structure** (from tree listing — each is a full CRUD module):
`alert_events`, `alert_fields`, `alert_groups`, `alert_routes`, `alert_routing_rules`, `alert_sources`, `alert_urgencies`, `alerts`, `audits`, `authorizations`, `catalog_entities`, `catalog_entity_properties`, and many more.

**Key patterns:**
- Every endpoint has 4 variants: `sync`, `sync_detailed`, `asyncio`, `asyncio_detailed` ([source](https://github.com/rootlyhq/rootly-python/blob/master/README.md))
- Uses `AuthenticatedClient(base_url, token)` pattern
- Supports httpx event hooks for logging/middleware
- Alert operations include: `acknowledge_alert`, `attach_alert`, `resolve_alert` — good action verbs we should adopt

### 2.3 rootly-glean-connector (⭐ Best Python reference code)
- **URL:** https://github.com/rootlyhq/rootly-glean-connector
- **Key files:** [`data_fetchers/enhanced_incidents.py`](https://github.com/rootlyhq/rootly-glean-connector/blob/main/data_fetchers/enhanced_incidents.py), [`document_mappers/incident_mapper.py`](https://github.com/rootlyhq/rootly-glean-connector/blob/main/document_mappers/incident_mapper.py)

**Architecture pattern worth stealing:**
```
data_fetchers/     → API clients per data type (base class with pagination)
document_mappers/  → Transform Rootly data to target format
processors/        → Sync coordination/orchestration
```

**Incident enrichment pattern** (from `enhanced_incidents.py`):
1. Fetch basic incidents (paginated)
2. For each incident, fetch: events (timeline), action_items
3. Fetch severity definitions once (lookup cache)
4. Attach `_enhanced_data` dict to each incident

**Incident fields they extract** (from `incident_mapper.py`):
- `sequential_id` — human-readable incident number (INC-123)
- `title`, `status`, `summary`, `kind`
- `severity` (nested: data.attributes.name, level, description)
- `events` — timeline with `occurred_at`, `event` text, `visibility` (internal/public)
- `action_items` — with title, status, assignee.name, due_date
- Tags pattern: `status:resolved`, `severity:SEV1`, `kind:normal`

### 2.4 backstage-plugin
- **URL:** https://github.com/rootlyhq/backstage-plugin
- **Key insight:** Bridges Backstage service catalog ↔ Rootly. Uses annotations on Backstage entities:

```yaml
rootly.com/service-slug: elasticsearch-staging
rootly.com/service-auto-import: enabled  # Auto-creates Rootly service from Backstage entity
rootly.com/team-slug: infrastructure
rootly.com/functionality-slug: login
```

**Notable:** Supports multi-org configuration. Shows incidents per entity (last 30 days + ongoing). Service, functionality, and team are all first-class linkable entities.

### 2.5 pulse-action (GitHub Action)
- **URL:** https://github.com/rootlyhq/pulse-action
- **Simple but effective deployment tracking:**

```yaml
- uses: rootlyhq/pulse-action@master
  with:
    api_key: ${{ secrets.ROOTLY_API_KEY }}
    summary: Deploy Website
    environments: production
    services: elasticsearch-prod
    labels: platform=ubuntu,version=2
    refs: sha=cd62148,image=registry.rootly.io/my-service:cd6214
```

**Key fields:** summary, services, environments, labels (key=value), source, refs (key=value for SHA, image, etc.)

### 2.6 cli
- **URL:** https://github.com/rootlyhq/cli
- Go CLI focused on sending pulses. `rootly pulse` and `rootly pulse-run` (wraps a command, sends pulse based on exit status). Environment variables: `ROOTLY_API_KEY`, `ROOTLY_API_HOST`.

### 2.7 rootly-go (Go SDK)
- **URL:** https://github.com/rootlyhq/rootly-go
- Auto-generated from OpenAPI spec using `oapi-codegen`. Confirms the API is OpenAPI-first.

### 2.8 terraformer (DEPRECATED)
- **URL:** https://github.com/rootlyhq/terraformer
- Deprecated in favor of Terraform import blocks. Was used to reverse-engineer existing Rootly config into Terraform. Available resources: `environment`, `severity`, `service`, `functionality`, `team`, `workflow`, `workflow_task`, `incident_role`, `custom_field`, `custom_form`, `form_field`, `status_page`.

---

## 3. Data Model Analysis

### 3.1 Incident (the central entity)

From [`client/incidents.go`](https://github.com/rootlyhq/terraform-provider-rootly/blob/main/client/incidents.go):

| Field Group | Fields | Notes |
|---|---|---|
| **Identity** | id, sequential_id, title, slug, kind, summary | `sequential_id` = human-friendly INC-123 |
| **Hierarchy** | parent_incident_id, duplicate_incident_id | Parent/child + dedup support |
| **Status** | status, in_triage_at/by, started_at/by, mitigated_at/by, resolved_at/by, closed_at/by, cancelled_at/by | Full lifecycle with actor tracking |
| **Classification** | severity (obj), environments[], incident_types[], services[], functionalities[], groups[], labels{} | Multi-dimensional classification |
| **Slack** | slack_channel_id, slack_channel_name, slack_channel_url, slack_channel_archived, slack_last_message_ts | Dedicated Slack channel per incident |
| **Video** | zoom_meeting_id/url/password, google_meeting_id/url | War room support |
| **Integrations** | jira_issue_*, github_issue_*, gitlab_issue_*, asana_task_*, linear_issue_*, trello_card_*, zendesk_ticket_*, pagerduty_incident_*, opsgenie_*, service_now_*, mattermost_*, confluence_*, datadog_notebook_*, shortcut_*, motion_task_*, clickup_task_*, victor_ops_*, quip_page_*, sharepoint_page_*, airtable_*, freshservice_* | ~20 integration link fields |
| **Resolution** | mitigation_message, resolution_message, cancellation_message | Structured resolution notes |
| **Scheduling** | scheduled_for, scheduled_until | Maintenance window support |
| **Retro** | retrospective_progress_status | Post-mortem tracking |
| **Access** | private, public_title | Privacy controls |

### 3.2 Service

From [`client/services.go`](https://github.com/rootlyhq/terraform-provider-rootly/blob/main/client/services.go):

- Core: name, slug, description, public_description, color, position
- External IDs: backstage_id, external_id, pagerduty_id, opsgenie_id, cortex_id, service_now_ci_sys_id
- Repository: github_repository_name/branch, gitlab_repository_name/branch
- Ownership: owner_group_ids[], owner_user_ids[]
- Alerting: alert_urgency_id, alerts_email_enabled/address, alert_broadcast_enabled/channel
- Slack: slack_channels[], slack_aliases[], incident_broadcast_enabled/channel

### 3.3 Severity

From [`client/severities.go`](https://github.com/rootlyhq/terraform-provider-rootly/blob/main/client/severities.go):

- name, slug, description, severity (level string), color, position
- notify_emails[], slack_channels[], slack_aliases[]

### 3.4 Workflow

From [`client/workflows.go`](https://github.com/rootlyhq/terraform-provider-rootly/blob/main/client/workflows.go):

- name, slug, description, command (slash command trigger), enabled, locked, position
- **Trigger:** trigger_params (map — the flexible trigger configuration)
- **Filters:** environment_ids[], severity_ids[], incident_type_ids[], incident_role_ids[], service_ids[], functionality_ids[], group_ids[], cause_ids[], sub_status_ids[]
- **Scheduling:** wait, repeat_every_duration, repeat_on[], continuously_repeat, repeat_condition_*
- **Organization:** workflow_group_id
- **Related:** workflow_tasks (child resource), workflow_form_field_conditions (child)

---

## 4. Feature Ideas We Should Steal

### 4.1 Incident Lifecycle State Machine (HIGH PRIORITY)
**Source:** Incident model timestamps
```
detected → in_triage → started → mitigated → resolved → closed
                                                       → cancelled
```
Each transition records who + when. Implement as a state machine with transition hooks.

### 4.2 Sequential Incident IDs (HIGH PRIORITY)
**Source:** `sequential_id` field
Human-readable `INC-123` format alongside UUIDs. Essential for Slack conversations.

### 4.3 Deployment Pulse Tracking (MEDIUM)
**Source:** pulse-action
Simple webhook/API endpoint: `POST /pulses` with service, environment, labels, refs (git SHA, image tag). Correlate with incidents for "what changed?" analysis.

### 4.4 Workflow Engine Pattern (HIGH PRIORITY)
**Source:** Workflow model
```python
class Workflow:
    trigger_params: dict  # Flexible trigger config
    filters: dict  # severity_ids, service_ids, etc.
    wait: str  # Delay before execution  
    repeat_every_duration: str  # Recurring execution
    tasks: list[WorkflowTask]  # Ordered actions
```
Start simple: trigger on incident creation → filter by severity → execute actions (Slack message, page on-call, create Jira ticket).

### 4.5 Multi-Dimensional Incident Classification (HIGH PRIORITY)
**Source:** Incident model
Every incident has: severity, environment(s), service(s), functionality(s), incident_type(s), group(s), cause(s), labels. We should support at least severity + services + environment.

### 4.6 Dedicated Slack Channel per Incident (MEDIUM)
**Source:** Incident Slack fields
Auto-create a Slack channel for each incident (or thread in an existing channel for smaller incidents). Track `slack_channel_id`, `slack_last_message_ts`.

### 4.7 Action Items with Assignees (MEDIUM)
**Source:** Glean connector's incident_mapper.py
Action items per incident: title, status, assignee, due_date. Lightweight task tracking without needing Jira for everything.

### 4.8 Service Catalog Cross-References (LOW initially)
**Source:** Service model
Store external IDs (PagerDuty, Backstage, GitHub repo) per service. Makes integrations plug-and-play.

### 4.9 Incident Roles (MEDIUM)
**Source:** incident_roles resource
Define roles like "Incident Commander", "Communications Lead", "Scribe" and assign users to them per incident. Important for larger orgs.

### 4.10 Communications Templates (LOW)
**Source:** communications_templates, communications_stages
Pre-built templates for status updates at different stages. "We're investigating" → "We've identified the issue" → "Fix deployed, monitoring".

---

## 5. What They Do That We Should NOT Copy

### 5.1 ❌ 20+ Integration Link Fields on Incident
The Incident model has dedicated fields for Jira, GitHub, GitLab, Asana, Linear, Trello, Zendesk, PagerDuty, OpsGenie, ServiceNow, Confluence, Datadog, Shortcut, Motion, ClickUp, VictorOps, Quip, SharePoint, Airtable, Freshservice... This is a maintenance nightmare. 

**Better approach:** Use a generic `incident_links` table: `(incident_id, provider, external_id, url, metadata_json)`.

### 5.2 ❌ JSON:API Format
Their API uses JSON:API (evidenced by `jsonapi` Go tags). This format is overly complex for most use cases. **Use standard REST with JSON** — simpler, better tooling, easier for LLM consumption.

### 5.3 ❌ Auto-Generated SDKs as Primary Interface
Both Python and Go SDKs are auto-generated from OpenAPI. The resulting code is verbose and not idiomatic. **Build a thin, hand-crafted Python client** that's pleasant to use, and generate OpenAPI docs from FastAPI (not the other way around).

### 5.4 ❌ Over-Complex Form/Field System
They have: custom_fields, custom_field_options, form_fields, form_field_options, form_field_placements, form_field_placement_conditions, form_field_positions, form_sets, form_set_conditions. That's 9 resources just for custom forms. **Start with JSON schema-based custom fields** — much simpler.

### 5.5 ❌ Terraform-First Configuration
Great for enterprise, unnecessary complexity for us. **Use API + config files**.

---

## 6. Concrete Next Steps for Incident Copilot

### Phase 1: Core Data Model (Week 1-2)
1. **Define SQLAlchemy models** based on Rootly's schema (simplified):
   - `Incident` — id, sequential_id, title, summary, status, severity_id, kind, private, source
   - `Service` — id, name, slug, description, github_repo, owner_team_id
   - `Severity` — id, name, slug, description, level, color, position
   - `Environment` — id, name, slug, description
   - `Team` — id, name, slug, description
   - `IncidentService` (M2M), `IncidentEnvironment` (M2M)
   - `IncidentLink` — id, incident_id, provider, external_id, url (replaces 20+ dedicated fields)
   - `IncidentEvent` — id, incident_id, event_text, occurred_at, visibility, user_id (timeline)
   - `ActionItem` — id, incident_id, title, status, assignee_id, due_date

2. **Implement incident state machine:**
   ```python
   STATES = ["detected", "in_triage", "started", "mitigated", "resolved", "closed", "cancelled"]
   TRANSITIONS = {
       "detected": ["in_triage", "started", "cancelled"],
       "in_triage": ["started", "cancelled"],
       "started": ["mitigated", "resolved", "cancelled"],
       "mitigated": ["resolved", "cancelled"],
       "resolved": ["closed"],
   }
   ```

### Phase 2: API Layer (Week 2-3)
3. **FastAPI endpoints** following Rootly's resource patterns:
   - `POST /incidents` — create with severity, services, environment
   - `PATCH /incidents/{id}` — update status (triggers state machine)
   - `GET /incidents` — list with filters (status, severity, service, date range)
   - `POST /incidents/{id}/events` — add timeline entry
   - `POST /incidents/{id}/action_items` — add action item
   - `POST /pulses` — deployment tracking (steal from pulse-action)

### Phase 3: Workflow Engine (Week 3-4)
4. **Simple workflow engine** inspired by Rootly's model:
   ```python
   class Workflow:
       trigger: str  # "incident.created", "incident.status_changed", etc.
       conditions: dict  # {"severity_ids": ["sev1", "sev2"], "service_ids": [...]}
       actions: list[WorkflowAction]  # Sequential actions to execute
   ```

### Phase 4: Slack Integration (Week 4-5)
5. **Slack bot** with patterns from Rootly:
   - Create dedicated channel or thread per incident
   - Post timeline updates automatically
   - Slash command to declare incidents: `/incident "DB is down" --severity sev1 --service postgres`
   - Track `slack_channel_id` and `slack_last_message_ts` on incident

---

## Appendix: Source URLs Index

| Resource | URL |
|---|---|
| Incident data model | https://github.com/rootlyhq/terraform-provider-rootly/blob/main/client/incidents.go |
| Service data model | https://github.com/rootlyhq/terraform-provider-rootly/blob/main/client/services.go |
| Severity data model | https://github.com/rootlyhq/terraform-provider-rootly/blob/main/client/severities.go |
| Workflow data model | https://github.com/rootlyhq/terraform-provider-rootly/blob/main/client/workflows.go |
| All client resources | https://github.com/rootlyhq/terraform-provider-rootly/tree/main/client |
| Python SDK structure | https://github.com/rootlyhq/rootly-python/tree/master/rootly_sdk/api |
| Glean connector (Python reference) | https://github.com/rootlyhq/rootly-glean-connector |
| Enhanced incident fetcher | https://github.com/rootlyhq/rootly-glean-connector/blob/main/data_fetchers/enhanced_incidents.py |
| Incident document mapper | https://github.com/rootlyhq/rootly-glean-connector/blob/main/document_mappers/incident_mapper.py |
| Backstage plugin annotations | https://github.com/rootlyhq/backstage-plugin/blob/master/README.md |
| Pulse action (deploy tracking) | https://github.com/rootlyhq/pulse-action/blob/main/README.md |
| CLI (pulse commands) | https://github.com/rootlyhq/cli/blob/main/README.md |
| Terraformer resource list | https://github.com/rootlyhq/terraformer/blob/master/README.md |
