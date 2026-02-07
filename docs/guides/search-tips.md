# Advanced Search Guide

This guide covers advanced search techniques in Incident Copilot to help you find incidents, patterns, and insights quickly.

## Overview

Incident Copilot search supports:
- **Full-text search** - Search across all text fields
- **Structured queries** - Filter by specific fields
- **Saved searches** - Reusable query templates
- **Search alerts** - Get notified when new matches appear

---

## Basic Search

### Quick Search

Type in the search bar to search across all fields:

```
payment timeout
```

This searches:
- Incident title
- Description
- Comments
- Tags
- Service names

### Search Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `AND` | Both terms must match | `payment AND timeout` |
| `OR` | Either term matches | `payment OR checkout` |
| `NOT` | Exclude term | `payment NOT test` |
| `"..."` | Exact phrase | `"connection refused"` |
| `*` | Wildcard | `pay*` matches payment, payout |
| `~` | Fuzzy match | `paymnet~` matches payment |

### Example Searches

```
# Find incidents about payment timeouts
"payment timeout"

# Find critical or high severity incidents
severity:critical OR severity:high

# Exclude test incidents
payment NOT tag:test

# Fuzzy search for typos
databse~ connection~
```

---

## Structured Queries

### Field-Specific Search

Search within specific fields:

```
# By field name
title:payment
description:"connection refused"
service:checkout
tag:security

# By severity
severity:critical
severity:high

# By status
status:open
status:resolved
```

### Comparison Operators

```
# Numeric comparisons
duration:>60        # Longer than 60 minutes
cost:>=1000         # Cost $1000 or more
comments_count:<5   # Fewer than 5 comments

# Date comparisons
created:>2024-01-01
resolved:<2024-03-15
```

### Range Queries

```
# Date ranges
created:[2024-01-01 TO 2024-03-31]
resolved:[2024-03-01 TO *]  # Resolved after March 1

# Numeric ranges
duration:[30 TO 120]  # 30-120 minutes
severity_score:[7 TO 10]
```

### Field Existence

```
# Has a value
_exists_:assigned_to
_exists_:resolved_at

# Does not have a value
NOT _exists_:postmortem
NOT _exists_:root_cause
```

---

## Advanced Filters

### Filter by Time

```
# Relative time
created:today
created:yesterday
created:this_week
created:last_7_days
created:last_30_days
created:this_month
created:this_quarter
created:this_year

# Specific time range
created:[2024-03-01T00:00:00 TO 2024-03-15T23:59:59]

# Before/after
created:>2024-03-01
resolved:<2024-03-15
```

### Filter by People

```
# Assigned to specific person
assigned_to:alice@company.com

# Created by
created_by:bob@company.com

# Mentioned in comments
mentions:carol@company.com

# Acknowledged by
acknowledged_by:dave@company.com

# Any involvement
involved:alice@company.com
```

### Filter by Team/Service

```
# By team
team:platform
team:payments
team:"SRE Team"

# By service
service:checkout
service:user-auth
service:api-gateway

# By environment
environment:production
environment:staging
```

### Filter by Tags

```
# Single tag
tag:security
tag:customer-facing

# Multiple tags (AND)
tag:security AND tag:urgent

# Multiple tags (OR)
tag:security OR tag:compliance

# Exclude tag
NOT tag:test
```

---

## Combining Searches

### Complex Queries

```
# Critical payment incidents from last week, excluding tests
severity:critical AND service:payments AND created:last_7_days NOT tag:test

# Open incidents assigned to me or my team
status:open AND (assigned_to:me OR team:my_team)

# High-cost incidents that took over an hour
cost:>5000 AND duration:>60

# Security incidents without postmortem
tag:security AND resolved:last_30_days AND NOT _exists_:postmortem
```

### Query Precedence

Use parentheses for complex logic:

```
# Wrong: might match unintended results
severity:critical OR severity:high AND status:open

# Correct: explicitly group conditions
(severity:critical OR severity:high) AND status:open
```

---

## Saved Searches

### Create a Saved Search

```bash
# Via CLI
incident-copilot search save \
  --name "My Critical Incidents" \
  --query "severity:critical AND assigned_to:me AND status:open" \
  --visibility private

# Output:
# Saved search created: search_abc123
```

### Via UI

1. Enter your search query
2. Click **Save Search**
3. Enter a name and description
4. Choose visibility:
   - **Private**: Only you can see
   - **Team**: Your team members can see
   - **Public**: Everyone can see

<!-- Diagram: Save Search Modal -->
<!-- Shows form with name, description, visibility options -->

### Manage Saved Searches

```bash
# List your saved searches
incident-copilot search list

# Edit a saved search
incident-copilot search edit search_abc123 \
  --query "severity:critical AND assigned_to:me"

# Delete a saved search
incident-copilot search delete search_abc123
```

### Saved Search Examples

| Name | Query | Use Case |
|------|-------|----------|
| My Open | `assigned_to:me AND status:open` | Daily work |
| Team Backlog | `team:my_team AND status:open` | Team standup |
| SLA At Risk | `sla_status:at_risk AND status:open` | SLA monitoring |
| Needs Postmortem | `status:resolved AND NOT _exists_:postmortem AND severity:critical` | Follow-up |
| Recent Customer Impact | `tag:customer-impact AND created:last_7_days` | Customer review |

---

## Search Alerts

### Create a Search Alert

Get notified when new incidents match your search:

```yaml
# config/search-alerts.yaml
alerts:
  - name: "Critical Production Incidents"
    query: "severity:critical AND environment:production"
    notify:
      - type: slack
        channel: "#sre-alerts"
      - type: email
        recipients: [sre-leads@company.com]
    frequency: immediate
    
  - name: "Daily Security Summary"
    query: "tag:security AND created:today"
    notify:
      - type: email
        recipients: [security@company.com]
    frequency: daily
    send_at: "09:00"
```

### Alert Frequencies

| Frequency | Description |
|-----------|-------------|
| `immediate` | Send as soon as new match appears |
| `hourly` | Summary every hour (if matches) |
| `daily` | Daily digest at specified time |
| `weekly` | Weekly digest on specified day |

---

## Search API

### Basic API Search

```bash
curl -X GET "https://api.incident-copilot.com/v1/incidents/search" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -G \
  --data-urlencode "q=severity:critical AND status:open" \
  --data-urlencode "limit=50" \
  --data-urlencode "sort=created_at:desc"
```

### Response Format

```json
{
  "data": [
    {
      "id": "INC-12345",
      "title": "Payment gateway timeout",
      "severity": "critical",
      "status": "open",
      "created_at": "2024-03-15T10:30:00Z",
      "_score": 15.7,
      "_highlight": {
        "title": ["<em>Payment</em> gateway <em>timeout</em>"]
      }
    }
  ],
  "meta": {
    "total": 42,
    "limit": 50,
    "offset": 0,
    "took_ms": 23
  },
  "facets": {
    "severity": {
      "critical": 5,
      "high": 12,
      "medium": 20,
      "low": 5
    }
  }
}
```

### Aggregations

```bash
# Get aggregations/facets
curl -X GET "https://api.incident-copilot.com/v1/incidents/search" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -G \
  --data-urlencode "q=*" \
  --data-urlencode "aggs=severity,team,service" \
  --data-urlencode "limit=0"  # Only get aggregations
```

---

## Search Tips by Use Case

### Finding Root Causes

```
# Incidents with specific error messages
description:"out of memory" OR description:"OOM"
description:"connection pool exhausted"
description:"disk full"

# Incidents affecting specific component
service:database AND (title:slow OR title:timeout)
```

### Pattern Detection

```
# Recurring issues in same service
service:checkout AND created:last_30_days | group_by:title

# Issues at specific times
created_hour:[2 TO 5]  # 2am-5am issues

# Weekend incidents
created_day_of_week:[6 TO 7]  # Saturday/Sunday
```

### Compliance & Reporting

```
# Incidents without resolution notes
status:resolved AND NOT _exists_:resolution_notes

# Long-running incidents
duration:>480  # Over 8 hours

# Incidents with customer communication
tag:customer-notified OR _exists_:external_ticket_id
```

### On-Call Analysis

```
# My on-call incidents last month
created:last_month AND created_by_oncall:me

# Incidents during specific shift
created:[2024-03-10T18:00:00 TO 2024-03-11T06:00:00]
```

---

## Performance Optimization

### Search Performance Tips

1. **Be specific** - Narrow queries are faster
   ```
   # Slow
   *payment*
   
   # Fast
   title:payment AND created:last_7_days
   ```

2. **Use filters over queries** - Filters are cached
   ```
   # Better for repeated searches
   status:open AND severity:critical
   ```

3. **Limit results** - Request only what you need
   ```
   limit=20  # Don't fetch 1000 when you need 20
   ```

4. **Use sorting carefully** - Some sorts are expensive
   ```
   # Fast (indexed fields)
   sort=created_at:desc
   
   # Slower (computed fields)
   sort=duration:desc
   ```

5. **Avoid leading wildcards**
   ```
   # Slow
   *payment*
   
   # Fast
   payment*
   ```

---

## Search Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `/` | Focus search bar |
| `Enter` | Execute search |
| `↑` / `↓` | Navigate results |
| `Ctrl+Enter` | Open in new tab |
| `Ctrl+S` | Save current search |
| `Esc` | Clear search / close |

---

## Best Practices

1. **Start broad, then narrow** - Begin with general terms, add filters
2. **Use saved searches** - Don't retype common queries
3. **Set up alerts** - For critical pattern monitoring
4. **Learn the syntax** - Structured queries are more precise
5. **Check aggregations** - Facets help understand result distribution
6. **Bookmark important searches** - Quick access to common views

---

## Common Pitfalls

| Issue | Cause | Solution |
|-------|-------|----------|
| No results | Too specific | Remove some filters, check spelling |
| Too many results | Too broad | Add severity, date, or team filters |
| Unexpected results | Operator precedence | Use parentheses for grouping |
| Slow search | Leading wildcards | Use prefix wildcards only |
| Missing matches | Case sensitivity | Search is case-insensitive by default |

---

## Examples by Role

### For Incident Commanders

```
# Active major incidents
severity:critical AND status:open AND tag:major-incident

# Incidents needing IC assignment
status:open AND NOT _exists_:incident_commander

# Recent escalations
escalated:true AND created:last_24_hours
```

### For SRE Teams

```
# Production alerts this week
environment:production AND created:this_week

# Service degradations
status:open AND (title:degraded OR title:slow OR title:latency)

# Repeat incidents (same title)
created:last_30_days | group_by:title | having:count>2
```

### For Engineering Managers

```
# Team incident load
team:my_team AND created:this_month | group_by:week

# Long resolution times
team:my_team AND duration:>240 AND status:resolved

# Missing postmortems
team:my_team AND severity:critical AND resolved:last_30_days AND NOT _exists_:postmortem
```

### For Security Teams

```
# Security-related incidents
tag:security OR title:breach OR title:vulnerability

# Data access incidents
tag:data-access OR title:"unauthorized access"

# Compliance gaps
tag:compliance AND NOT tag:resolved-compliant
```

---

## Next Steps

- [Custom Dashboards](./custom-dashboards.md) - Visualize search results
- [Webhook Integration](./webhook-integration.md) - Trigger actions on search matches
- [Cost Tracking](./cost-tracking.md) - Analyze incident costs with search