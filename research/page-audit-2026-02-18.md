# Incident Copilot — Page Audit (2026-02-18)

Scope: audited `src/web/templates/` and relevant handlers in `src/web/routes.py`.

This dashboard has a strong visual baseline (Tailwind, sidebar/topbar, responsive layout, dark mode), but product-wise it still reads like a prototype in multiple places: inconsistent data model, duplicated UX, missing auth consistency, and several pages that depend on APIs that don’t exist (or at least are not wired into `routes.py`). Below is a CEO-level teardown with specific fixes.

---

## Global / cross-cutting findings

### What works well
- **Design system consistency**: `base.html` gives a cohesive app shell (sidebar, topbar, typography, dark mode, mobile nav overlay).
- **Time-to-value concept is right**: “Operational overview → incident list → detail page with AI summary + deploys + logs” matches what Rootly/incident.io sell.
- **Good primitives**: template filters (`severity_color`, `status_color`, `mask_secret`) and stats endpoints (`/api/dashboard/stats`) are sane.

### What’s broken / missing
- **Page title / active nav bugs**
  - `routes.py` sets `page_title="Configuration"` but `base.html` marks Settings active only if `page_title == 'Config'`.
  - Fix: update `base.html` to match the actual `page_title` values.

- **Auth is inconsistent and leaky**
  - The HTML pages are protected by `Depends(require_dashboard_auth)` on the router, but many JS calls hit `/api/...` without auth headers (some rely on cookies), and some calls hit non-dashboard paths (`/copilot/chat`, `/copilot/summary/...`).
  - You’re mixing:
    - Bearer header (from localStorage)
    - cookie `ic_access_token`
    - unauthenticated endpoints
  - This is brittle and will create “works on my machine” bugs.

- **Data model mismatch across pages**
  - `dashboard.html` uses `status` values like `processing/completed/error`.
  - `incidents.html` expects `triggered/acknowledged/resolved` and also checks `completed`.
  - Competitors are extremely consistent here (incident.io has a single state machine and derived statuses).

- **CDN Tailwind in prod**
  - Shipping Tailwind via CDN is okay for prototypes, not for a real product (performance, CSP, deterministic builds).

- **No global search / command palette**
  - You already have keyboard shortcuts wiring in `base.html`, but there is no overlay element (`#shortcuts-overlay`) and no command palette.

### Competitors do better (Rootly / FireHydrant / incident.io)
- **Unified incident model** (one status vocabulary across list/detail/analytics).
- **Opinionated workflows**: timeline updates, roles, tasks, postmortem templates, follow-ups.
- **Deep linking**: each artifact (alert, deployment, log pattern) links to source with context.
- **Guardrails**: better empty states, guided setup, and clear “next action” CTA.

### High-impact improvements (platform-level)
1. **Normalize incident status vocabulary**
   - Decide: either (A) operational processing status (`processing/completed/error`) or (B) incident lifecycle (`triggered/acknowledged/resolved`) and keep processing as a secondary field.
   - Add a small translation layer in `/api/incidents` to keep UI consistent.

2. **Centralize authenticated fetch**
   - Put a single helper in `/dashboard/static/app.js` (or inline) that always attaches Bearer token and handles 401.
   - Remove duplicated token handling across pages.

3. **Stop embedding large JS blobs in templates**
   - Move each page’s JS into `/dashboard/static/pages/<page>.js`.
   - This improves maintainability and makes it obvious what endpoints are required.

4. **Add a real command palette**
   - This is cheap, high perceived quality, and you already have keyboard hooks.

---

## Page-by-page audit

### 1) `dashboard.html` (Main dashboard)

**What works well**
- Looks polished: summary header, stat cards, severity distribution, and a “recent incidents” feed.
- Auto-refresh concept is correct; the 15s refresh + “Auto-refreshing” labels build trust.

**What’s broken / missing**
- **Dead demo-mode code**: the JS contains a full “demo scenario” UI (`demo-scenario`, `run-demo`, `demo-status`, `demo-context`, `demo-context-card`) but the HTML markup for those IDs does not exist in `dashboard.html`.
  - Result: silent failures and console noise; feels sloppy.
- **No sorting/filtering** on dashboard list. It’s just a feed.
- **Empty state CTA** is good but not personalized: it doesn’t reflect which integrations are connected.

**Competitors do better**
- “Today / last 7 days” widgets, on-call handoff, open vs closed incidents, service health rollups.
- Quick actions: create incident, start war room, page team, generate update.

**High-impact improvements**
- Remove dead demo code or add the missing demo UI.
- Add a “quick filters” row: `Open`, `Critical`, `My services`.
- Show “Top noisy services” and “MTTR trend” preview panels.

**Specific code changes**
- **Option A: remove demo JS block** if demo is not meant on dashboard.
  - In `dashboard.html`, delete functions `loadDemoScenarios`, `triggerDemoIncident`, `pollDemoIncident`, `renderDemoCard`, and the DOMContentLoaded hook that references them.
- **Option B: add demo widget markup** (if you want demo on dashboard):
  - Add a card with `<select id="demo-scenario">`, `<button id="run-demo">`, `<div id="demo-status">`, `<div id="demo-context" class="hidden">`, `<div id="demo-context-card">`.

---

### 2) `incidents.html` (Incidents list — enhanced already)

**What works well**
- This is the best page in the app right now:
  - search, filters, sorting, pagination, stats bar.
  - thoughtful UI details (badges, source icons, “verdict_summary” line).

**What’s broken / missing**
- **Status mismatch**: UI filter expects `triggered/acknowledged/resolved`, but backend `/api/incidents` returns `processing/completed/error` (at least for in-memory and DB fallback).
  - Filter will basically be useless in many cases.
- **MTTR stats are computed from `duration_seconds`**, but `/api/incidents` payload doesn’t include it.
- **Source icons** assume `source`, `source_url`, `verdict_summary` exist; `/api/incidents` does not provide those fields.

**Competitors do better**
- Saved views (“My team”, “P1”, “Last 24h”), bulk actions, CSV export.

**High-impact improvements**
- Fix the API contract to match this UI; don’t downgrade the page.
- Add “Open in PagerDuty/Slack” per incident.

**Specific code changes**
- In `routes.py` (function `api_incidents`), return a richer, consistent schema:
  - `status` → lifecycle status (`triggered/acknowledged/resolved`) OR update UI to match processing status.
  - add `duration_seconds`, `source`, `source_url`, `created_at`, optional `verdict_summary`.
- If you can’t implement lifecycle status yet, **change UI options**:
  - In `incidents.html` replace status filter options with `processing/completed/error`.

---

### 3) `incident_detail.html` (Incident view)

**What works well**
- The context card layout is strong: AI analysis, verdict, deploys, metrics/log patterns, service info.
- Clear CTA to Copilot Chat + link out to PagerDuty when available.

**What’s broken / missing**
- **Prototype-level chat embedded on detail page** duplicates the dedicated `copilot_chat.html`.
  - Two different chat implementations:
    - Detail page uses REST calls: `/copilot/start/{id}`, `/copilot/chat`, `/copilot/suggestions/{id}`, `/copilot/summary/{id}`
    - Dedicated page uses WS: `/ws/copilot/{id}`
  - This will diverge and confuse users.
- The embedded chat posts markdown-ish text with emoji (`📋`, `🔍`) but the renderer is plain text; users will see raw markdown markers like `**...**`.
- No “incident actions”: assign owner, set severity, set status, create follow-ups, create postmortem.
- No deep links in deployments/log patterns to GitHub/Datadog.

**Competitors do better**
- One canonical incident workspace: status updates, roles, tasks, timeline, Slack integration, postmortem generation.

**High-impact improvements**
- Pick one chat UX (WS-based is better) and use it everywhere.
- Add a right-rail “Actions” card: `Create Slack update`, `Generate summary`, `Open runbook`, `Open dashboards`.

**Specific code changes**
- Remove the embedded chat block from `incident_detail.html` and replace with a small CTA card linking to `/dashboard/incident/{id}/chat`.
  - Delete the `#copilot-section` markup and the large JS block.
- Or invert: embed the WS chat component and remove the dedicated page.

---

### 4) `services.html` (Service catalog)

**What works well**
- The 3-column layout is a good “admin tool” structure: list → details → edit/import.
- Dependencies view is a differentiator if it becomes real.

**What’s broken / missing**
- This page screams internal prototype:
  - “Import Wizard” asks for raw JSON/CSV without validation UX.
  - “Discover from Kubernetes/Datadog APM” buttons call endpoints that may not exist.
  - No auth header and no error UX beyond throwing `Error(txt)`.
- The create/edit form is not aligned with how services are modeled in real orgs:
  - you need ownership, tier, on-call, links (repo/runbook/dashboard), and environment-specific routing.

**Competitors do better**
- True service catalog: ownership, SLOs, dependencies graph, incident history per service, and integrations with alerting.

**High-impact improvements**
- Add service profile pages with incident history and links.
- Make “discover” actually show a preview/diff before import.

**Specific code changes**
- Add inline error banners/toasts on failed API calls.
- Ensure endpoints exist and are tenant-scoped:
  - `/api/services`, `/api/services/{id}`, `/api/services/{id}/dependencies`, `/api/services/import/json`, `/api/services/import/csv`, `/api/services/discovery/{source}`.
- Add Authorization header consistently (reuse a shared fetch helper).

---

### 5) `config.html` (Settings) — known Jinja2 bug

**What works well**
- “Masked secrets” display is appropriate.
- Integration cards are a nice at-a-glance UX.

**What’s broken / missing**
- **Jinja2 bug**: `integration.keys()` is invalid (list is not callable). This will throw a template error.
- **Configured detection logic is incorrect / overcomplicated**: you’re matching `config_items.env_var` against uppercased “keys” but the `keys` list is not env var names.
- **Nav highlight bug** (from `base.html`): Settings link never becomes active because it checks `page_title == 'Config'`.
- Page title styling is inconsistent with dark mode (it hardcodes light colors in places).

**Competitors do better**
- Guided integration connection (OAuth), test buttons, connection health, last sync, permissions scopes.

**High-impact improvements**
- Replace “env var list” settings page with an integrations connection page (OAuth) and a diagnostics page.

**Specific code changes (immediate)**
1) Fix the Jinja2 error in `config.html`:
```diff
- {% set configured = config_items | selectattr('env_var', 'in', integration.keys() | map('upper') | list) | selectattr('value') | list | length > 0 %}
+ {% set configured = config_items | selectattr('env_var', 'in', integration.keys | map('upper') | list) | selectattr('value') | list | length > 0 %}
```
2) Fix Settings nav active state in `base.html`:
```diff
- <a href="/dashboard/config" class="nav-item {% if page_title == 'Config' %}active{% endif %}">
+ <a href="/dashboard/config" class="nav-item {% if page_title in ['Config','Configuration','Settings'] %}active{% endif %}">
```
3) Fix config page dark mode classes (many elements use `bg-white` / `text-slate-900` without `dark:` variants).

---

### 6) `analytics.html`

**What works well**
- Clear, executive-friendly MTTR framing and a trend chart.
- Period selector is straightforward.

**What’s broken / missing**
- Calls `/api/analytics/*` endpoints; these handlers are **not in `routes.py`**. If they live elsewhere, fine; if not, this page is dead.
- No auth headers; relies on cookies (maybe okay) but inconsistent with other pages.
- Table rows are not clickable to incident detail.

**Competitors do better**
- Breakdown by service/team/severity, SLO impact, “time to mitigate vs time to resolve”, heatmaps, export.

**High-impact improvements**
- Add: `MTTA`, `change failure rate`, `incident volume by service`, `top regressions`.

**Specific code changes**
- Make table rows link to `/dashboard/incident/<id>`.
- Add error UI when fetch fails (instead of silent console errors).

---

### 7) `insights.html`

**What works well**
- The vision is strong: “patterns, anomalies, dependencies, digest” is exactly what execs want.
- The modal “Run Analysis” UX is decent.

**What’s broken / missing**
- Numerous dark-mode class bugs (several components hardcode light colors).
- Some Tailwind classes are wrong / inconsistent:
  - e.g. anomaly affected services badges: `bg-slate-600 text-slate-700` (dark background + dark text = unreadable).
  - dependencies progress bars: `bg-slate-600` in light mode looks wrong.
- All APIs are assumed:
  - `/api/insights`, `/api/insights/summary`, `/api/insights/patterns`, `/api/insights/anomalies`, `/api/insights/dependencies`, `/api/insights/digest`, `/api/insights/analyze`, `/api/insights/digest/generate`, `/api/insights/{id}/acknowledge`
  - None are in `routes.py`.

**Competitors do better**
- They connect insights to action: create follow-up tickets, auto-tag services, open PRs, notify owners.

**High-impact improvements**
- Make every insight actionable:
  - “Create Jira”, “Create Linear”, “Assign to team”, “Mute pattern”, “Link runbook”.

**Specific code changes**
- Fix unreadable badge classes (example):
```diff
- <span class="bg-slate-600 text-slate-700 ...">
+ <span class="bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200 ...">
```
- Ensure all insight endpoints exist and are tenant-scoped + authenticated.

---

### 8) `copilot_chat.html` (Dedicated chat)

**What works well**
- This is the *right* implementation direction: a dedicated workspace with WS streaming.
- Quick actions are minimal but good.

**What’s broken / missing**
- No auth for the WebSocket.
- The chat doesn’t render rich content (links, bullets) beyond plain text.
- No conversation persistence shown (no history load on refresh).

**Competitors do better**
- incident.io integrates chat into the incident workspace and keeps context in one place.

**High-impact improvements**
- Make this the only chat surface and remove the embedded one from the incident detail page.
- Add “Copy summary”, “Post to Slack”, “Generate status update”.

**Specific code changes**
- Add WS auth: include token in query string or via cookie validation server-side.
- Add message history endpoint and load it on page load.

---

## Additional quick hits

### `base.html`
- **Hardcoded Supabase anon key and URL fallback** in the silent refresh section is a security smell and makes this repo non-portable.
  - Move to server-provided values only; don’t ship a default anon key in HTML.

### `routes.py` gaps (for focused pages)
- Routes exist for pages, but not for the analytics/insights APIs those pages call (unless defined in another module/router).
- `/dashboard/config` sets `page_title="Configuration"` but nav expects `Config`.

---

## Recommended priority order (CEO view)
1. **Fix config.html Jinja2 crash + Settings nav active** (immediate credibility fix).
2. **Unify incident status + API contract** (makes incidents page truthful).
3. **Choose one Copilot chat UX** (remove duplication).
4. **Ship a command palette + global search** (high perceived quality).
5. **Make analytics/insights real or hide them behind “Coming soon”** (don’t ship dead pages).
