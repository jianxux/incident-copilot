# Webhook Integration Guide

This guide explains how to integrate Incident Copilot with external systems using webhooks, both for receiving events (inbound) and sending notifications (outbound).

## Overview

Webhooks enable:
- **Inbound**: Create incidents from monitoring tools (PagerDuty, Datadog, etc.)
- **Outbound**: Notify external systems when incidents change
- **Bidirectional**: Full synchronization with external incident management

---

## Inbound Webhooks

### Create a Webhook Endpoint

```bash
# Create an inbound webhook
incident-copilot webhook create \
  --name "Datadog Alerts" \
  --direction inbound \
  --source datadog

# Output:
# Webhook created successfully
# ID: wh_abc123
# URL: https://hooks.incident-copilot.com/inbound/wh_abc123
# Secret: whsec_xxxxxxxxxxxx
```

### Configure Webhook Settings

```yaml
# config/webhooks/datadog-inbound.yaml
webhook:
  id: wh_abc123
  name: "Datadog Alerts"
  direction: inbound
  
  authentication:
    type: signature
    header: X-Datadog-Signature
    algorithm: hmac_sha256
    secret: "${DATADOG_WEBHOOK_SECRET}"
    
  rate_limit:
    requests_per_minute: 100
    burst: 20
    
  payload_mapping:
    incident:
      title: "$.title"
      description: "$.body"
      severity: 
        field: "$.priority"
        mapping:
          P1: critical
          P2: high
          P3: medium
          P4: low
      source: datadog
      external_id: "$.alert_id"
      tags:
        - "source:datadog"
        - "monitor:{{$.monitor_name}}"
```

### Payload Transformation

Transform incoming payloads to match Incident Copilot schema:

```yaml
# config/webhooks/transforms/datadog.yaml
transform:
  # JSONPath expressions
  title: "$.alertTitle"
  description: |
    **Alert Details**
    
    Monitor: {{$.monitorName}}
    Query: {{$.query}}
    Threshold: {{$.threshold}}
    Value: {{$.value}}
    
    [View in Datadog]({{$.link}})
    
  severity:
    expr: |
      if $.priority == "P1" then "critical"
      elif $.priority == "P2" then "high"
      elif $.priority == "P3" then "medium"
      else "low"
      
  # Static values
  source: "datadog"
  auto_acknowledge: false
  
  # Conditional fields
  service:
    expr: "$.tags | map(select(startswith('service:'))) | .[0] | split(':')[1]"
    default: "unknown"
```

### Supported Inbound Sources

| Source | Auto-Detection | Configuration |
|--------|---------------|---------------|
| PagerDuty | ✅ | Signature validation |
| Datadog | ✅ | API key header |
| New Relic | ✅ | Custom header |
| Prometheus Alertmanager | ✅ | Basic auth |
| Grafana | ✅ | Bearer token |
| AWS CloudWatch | ✅ | SNS signature |
| Azure Monitor | ✅ | Shared key |
| Custom | Manual | Configurable |

### PagerDuty Integration Example

```yaml
# config/webhooks/pagerduty-inbound.yaml
webhook:
  name: "PagerDuty Incidents"
  source: pagerduty
  
  authentication:
    type: pagerduty_signature
    secret: "${PAGERDUTY_WEBHOOK_SECRET}"
    
  event_filters:
    - event_type: incident.triggered
      action: create_incident
    - event_type: incident.acknowledged
      action: acknowledge_incident
    - event_type: incident.resolved
      action: resolve_incident
      
  payload_mapping:
    incident:
      title: "$.incident.title"
      description: "$.incident.description"
      severity:
        field: "$.incident.urgency"
        mapping:
          high: critical
          low: medium
      external_id: "$.incident.id"
      external_url: "$.incident.html_url"
```

---

## Outbound Webhooks

### Create Outbound Webhook

```bash
# Create an outbound webhook
incident-copilot webhook create \
  --name "Slack Notifications" \
  --direction outbound \
  --url "https://hooks.slack.com/services/xxx/yyy/zzz"

# Output:
# Webhook created: wh_xyz789
```

### Configure Outbound Events

```yaml
# config/webhooks/slack-outbound.yaml
webhook:
  id: wh_xyz789
  name: "Slack Notifications"
  direction: outbound
  
  endpoint:
    url: "${SLACK_WEBHOOK_URL}"
    method: POST
    headers:
      Content-Type: application/json
      
  retry:
    max_attempts: 3
    backoff:
      initial_seconds: 1
      multiplier: 2
      max_seconds: 60
      
  events:
    - incident.created
    - incident.acknowledged
    - incident.severity_changed
    - incident.resolved
    - incident.comment_added
    - sla.breach
```

### Outbound Payload Templates

```yaml
# config/webhooks/templates/slack.yaml
templates:
  incident.created:
    blocks:
      - type: header
        text:
          type: plain_text
          text: "🚨 New Incident: {{incident.title}}"
          
      - type: section
        fields:
          - type: mrkdwn
            text: "*Severity:* {{incident.severity}}"
          - type: mrkdwn
            text: "*Status:* {{incident.status}}"
          - type: mrkdwn
            text: "*Service:* {{incident.service}}"
          - type: mrkdwn
            text: "*Assigned:* {{incident.assignee.name}}"
            
      - type: actions
        elements:
          - type: button
            text:
              type: plain_text
              text: "View Incident"
            url: "{{incident.url}}"
            style: primary
            
  incident.resolved:
    blocks:
      - type: section
        text:
          type: mrkdwn
          text: "✅ *Resolved:* {{incident.title}}\n\nDuration: {{incident.duration_human}}"
```

<!-- Diagram: Slack Notification Example -->
<!-- Shows formatted Slack message with incident details and buttons -->

### Event Filtering

Only send webhooks for specific events:

```yaml
webhook:
  events:
    - event: incident.created
      filter:
        severity: [critical, high]
        
    - event: incident.severity_changed
      filter:
        new_severity: critical
        
    - event: sla.breach
      # No filter - send all SLA breaches
```

---

## Bidirectional Sync

### Two-Way Integration

Sync incidents between Incident Copilot and external systems:

```yaml
# config/webhooks/bidirectional/jira.yaml
integration:
  name: "Jira Sync"
  type: bidirectional
  
  inbound:
    url: "https://hooks.incident-copilot.com/inbound/wh_jira123"
    events:
      - jira.issue.created
      - jira.issue.updated
      - jira.issue.resolved
      
  outbound:
    url: "https://company.atlassian.net/rest/api/3/issue"
    auth:
      type: basic
      username: "${JIRA_USERNAME}"
      password: "${JIRA_API_TOKEN}"
    events:
      - incident.created
      - incident.updated
      - incident.resolved
      
  field_mapping:
    # Incident Copilot → Jira
    to_external:
      summary: "incident.title"
      description: "incident.description"
      priority:
        field: "incident.severity"
        mapping:
          critical: Highest
          high: High
          medium: Medium
          low: Low
          
    # Jira → Incident Copilot
    from_external:
      title: "fields.summary"
      description: "fields.description"
      external_id: "key"
      external_url: "self"
      
  sync_rules:
    create_external_on_incident: true
    create_incident_on_external: true
    sync_comments: true
    sync_status: true
```

### Conflict Resolution

```yaml
sync_rules:
  conflict_resolution:
    strategy: last_write_wins  # or: source_priority, manual
    source_priority:
      - incident_copilot
      - jira
      
  # Prevent sync loops
  deduplication:
    window_seconds: 5
    key_fields: [external_id, updated_at]
```

---

## Authentication

### Signature Verification (Inbound)

```yaml
authentication:
  type: signature
  algorithm: hmac_sha256
  header: X-Webhook-Signature
  secret: "${WEBHOOK_SECRET}"
  
  # Optional: Include timestamp to prevent replay
  timestamp_header: X-Webhook-Timestamp
  timestamp_tolerance_seconds: 300
```

### Bearer Token (Outbound)

```yaml
endpoint:
  url: "https://api.external.com/webhook"
  headers:
    Authorization: "Bearer ${EXTERNAL_API_TOKEN}"
```

### OAuth 2.0 (Outbound)

```yaml
authentication:
  type: oauth2
  client_id: "${OAUTH_CLIENT_ID}"
  client_secret: "${OAUTH_CLIENT_SECRET}"
  token_url: "https://auth.external.com/oauth/token"
  scopes:
    - webhooks:write
```

### IP Allowlisting

```yaml
security:
  allowed_ips:
    - 10.0.0.0/8
    - 192.168.1.0/24
    - 52.1.2.3  # Specific IP
```

---

## Monitoring and Debugging

### View Webhook Logs

```bash
# View recent webhook deliveries
incident-copilot webhook logs wh_abc123 --limit 50

# Filter by status
incident-copilot webhook logs wh_abc123 --status failed

# View specific delivery
incident-copilot webhook logs wh_abc123 --delivery del_xyz789 --verbose
```

### Webhook Metrics Dashboard

```yaml
# config/dashboards/webhooks.yaml
widgets:
  - type: metric
    title: "Success Rate"
    query: "webhooks.delivery_success_rate"
    
  - type: line_chart
    title: "Deliveries Over Time"
    query: |
      SELECT 
        time_bucket('1h', delivered_at) as hour,
        COUNT(*) FILTER (WHERE status = 'success') as success,
        COUNT(*) FILTER (WHERE status = 'failed') as failed
      FROM webhook_deliveries
      GROUP BY hour
      
  - type: table
    title: "Recent Failures"
    query: |
      SELECT webhook_name, event_type, error_message, delivered_at
      FROM webhook_deliveries
      WHERE status = 'failed'
      ORDER BY delivered_at DESC
      LIMIT 20
```

### Test Webhooks

```bash
# Send a test event
incident-copilot webhook test wh_abc123 \
  --event incident.created \
  --payload '{"title": "Test Incident", "severity": "low"}'

# Validate inbound webhook
incident-copilot webhook validate wh_abc123 \
  --payload-file sample-payload.json
```

---

## Best Practices

1. **Always verify signatures** - Validate inbound webhook authenticity
2. **Implement idempotency** - Handle duplicate deliveries gracefully
3. **Use retry with backoff** - Don't overwhelm failing endpoints
4. **Log everything** - Keep delivery logs for debugging
5. **Set timeouts** - Don't wait forever for slow endpoints
6. **Filter events** - Only send relevant events to reduce noise
7. **Test thoroughly** - Use test mode before going live

---

## Common Pitfalls

| Issue | Cause | Solution |
|-------|-------|----------|
| Missing webhooks | Endpoint timeout | Increase timeout, optimize endpoint |
| Duplicate incidents | Retry without idempotency | Use external_id for deduplication |
| Invalid signature | Wrong secret or algorithm | Verify secret, check signature format |
| Payload errors | Schema mismatch | Validate payload mapping |
| Rate limiting | Too many events | Implement batching or filtering |

---

## Examples

### Example 1: Prometheus Alertmanager

```yaml
# config/webhooks/alertmanager.yaml
webhook:
  name: "Alertmanager"
  source: prometheus_alertmanager
  
  payload_mapping:
    incident:
      title: "$.alerts[0].labels.alertname"
      description: "$.alerts[0].annotations.description"
      severity:
        field: "$.alerts[0].labels.severity"
        mapping:
          critical: critical
          warning: high
          info: low
      service: "$.alerts[0].labels.service"
      tags:
        - "source:alertmanager"
        - "job:{{$.alerts[0].labels.job}}"
```

### Example 2: Custom Webhook to Microsoft Teams

```yaml
# config/webhooks/teams.yaml
webhook:
  name: "Teams Notifications"
  direction: outbound
  
  endpoint:
    url: "${TEAMS_WEBHOOK_URL}"
    
  templates:
    incident.created:
      "@type": "MessageCard"
      "@context": "http://schema.org/extensions"
      themeColor: "{{if incident.severity == 'critical'}}FF0000{{else}}FFA500{{end}}"
      summary: "New Incident: {{incident.title}}"
      sections:
        - activityTitle: "🚨 {{incident.title}}"
          facts:
            - name: "Severity"
              value: "{{incident.severity}}"
            - name: "Service"
              value: "{{incident.service}}"
            - name: "Status"
              value: "{{incident.status}}"
          markdown: true
      potentialAction:
        - "@type": "OpenUri"
          name: "View Incident"
          targets:
            - os: default
              uri: "{{incident.url}}"
```

---

## Next Steps

- [Real-Time Updates](./realtime-updates.md) - WebSocket integration
- [Enterprise Setup](./enterprise-setup.md) - Secure webhook configuration
- [Escalation Policies](./escalation-policies.md) - Trigger escalations via webhooks
