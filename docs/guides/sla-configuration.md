# SLA Configuration Guide

This guide explains how to configure Service Level Agreements (SLAs) in Incident Copilot to ensure timely incident response and resolution.

## Overview

SLA policies define:
- **Response time** - Time to first acknowledgment
- **Resolution time** - Time to incident closure
- **Escalation triggers** - When to escalate breaching SLAs
- **Business hours** - When SLA clocks are active

---

## Understanding SLA Metrics

### Key Terms

| Metric | Definition |
|--------|------------|
| **MTTA** | Mean Time to Acknowledge - Average time to first response |
| **MTTR** | Mean Time to Resolve - Average time to resolution |
| **SLA Breach** | When response/resolution exceeds defined threshold |
| **SLA At Risk** | Approaching breach threshold (configurable %) |

### SLA Clock States

```
┌─────────────┐    Incident Created    ┌─────────────┐
│   Stopped   │ ─────────────────────► │   Running   │
└─────────────┘                        └─────────────┘
                                              │
                   Acknowledged               │
              ◄───────────────────────────────┤
                                              │
                                              ▼
┌─────────────┐     Resolved           ┌─────────────┐
│   Stopped   │ ◄───────────────────── │   Paused    │
└─────────────┘                        └─────────────┘
                                       (Waiting on external)
```

---

## Step 1: Define SLA Policies

### Basic Configuration

```yaml
# config/sla/policies.yaml
sla_policies:
  - name: critical_production
    description: "Critical production incidents"
    priority: 1
    
    conditions:
      severity: [critical, sev1]
      environment: production
      
    targets:
      acknowledge:
        warning_minutes: 5
        breach_minutes: 15
      resolve:
        warning_minutes: 60
        breach_minutes: 240  # 4 hours
        
  - name: high_priority
    description: "High priority incidents"
    priority: 2
    
    conditions:
      severity: [high, sev2]
      
    targets:
      acknowledge:
        warning_minutes: 15
        breach_minutes: 30
      resolve:
        warning_minutes: 240
        breach_minutes: 480  # 8 hours
        
  - name: standard
    description: "Default SLA policy"
    priority: 100  # Lowest priority, fallback
    default: true
    
    conditions: {}  # Matches all incidents
    
    targets:
      acknowledge:
        warning_minutes: 60
        breach_minutes: 120
      resolve:
        warning_minutes: 1440  # 24 hours
        breach_minutes: 4320  # 72 hours
```

### Condition Matching

SLA policies support rich condition matching:

```yaml
conditions:
  # Match by severity
  severity: [critical, high]
  
  # Match by service
  service:
    - payment-gateway
    - user-auth
    
  # Match by tags
  tags:
    include: [customer-facing, revenue-impacting]
    exclude: [test, synthetic]
    
  # Match by team
  team: platform-team
  
  # Custom field matching
  custom_fields:
    region: [us-east, us-west]
    customer_tier: enterprise
    
  # Time-based conditions
  created_during:
    business_hours: true  # Only during business hours
```

---

## Step 2: Configure Business Hours

### Define Business Hours Calendars

```yaml
# config/sla/business-hours.yaml
business_hours:
  calendars:
    - name: us_business
      timezone: "America/New_York"
      hours:
        monday: { start: "09:00", end: "17:00" }
        tuesday: { start: "09:00", end: "17:00" }
        wednesday: { start: "09:00", end: "17:00" }
        thursday: { start: "09:00", end: "17:00" }
        friday: { start: "09:00", end: "17:00" }
        saturday: null  # Closed
        sunday: null    # Closed
        
    - name: follow_the_sun
      description: "24x5 coverage across regions"
      timezone: "UTC"
      hours:
        monday: { start: "00:00", end: "23:59" }
        tuesday: { start: "00:00", end: "23:59" }
        wednesday: { start: "00:00", end: "23:59" }
        thursday: { start: "00:00", end: "23:59" }
        friday: { start: "00:00", end: "23:59" }
        saturday: null
        sunday: null
        
    - name: "24x7"
      description: "Always on"
      always_on: true
```

### Configure Holidays

```yaml
# config/sla/holidays.yaml
holidays:
  calendar: us_business
  dates:
    - date: "2024-01-01"
      name: "New Year's Day"
    - date: "2024-07-04"
      name: "Independence Day"
    - date: "2024-12-25"
      name: "Christmas Day"
      
  # Recurring holidays
  recurring:
    - name: "Thanksgiving"
      rule: "fourth Thursday of November"
    - name: "Memorial Day"
      rule: "last Monday of May"
```

### Apply Business Hours to SLA Policies

```yaml
sla_policies:
  - name: standard_business
    business_hours:
      calendar: us_business
      pause_outside_hours: true  # SLA clock pauses after hours
      
  - name: critical_24x7
    business_hours:
      calendar: "24x7"
      pause_outside_hours: false  # Clock always runs
```

---

## Step 3: Set Up SLA Notifications

### Configure Alert Channels

```yaml
# config/sla/notifications.yaml
sla_notifications:
  channels:
    - name: slack_sre
      type: slack
      webhook_url: "${SLACK_SRE_WEBHOOK}"
      
    - name: pagerduty
      type: pagerduty
      integration_key: "${PAGERDUTY_KEY}"
      
    - name: email_managers
      type: email
      recipients:
        - sre-leads@company.com
        - oncall-managers@company.com

  rules:
    # Warning: SLA at risk
    - trigger: sla_warning
      delay_minutes: 0
      channels: [slack_sre]
      template: sla_warning
      
    # Breach: SLA violated
    - trigger: sla_breach
      delay_minutes: 0
      channels: [slack_sre, pagerduty]
      template: sla_breach
      
    # Repeated breach: escalate to managers
    - trigger: sla_breach
      conditions:
        breach_count: { gte: 2 }
      channels: [email_managers]
      template: sla_escalation
```

### Notification Templates

```yaml
# config/sla/templates.yaml
templates:
  sla_warning:
    title: "⚠️ SLA Warning: {{incident.title}}"
    body: |
      Incident #{{incident.id}} is at risk of breaching SLA.
      
      **Current Status:** {{incident.status}}
      **Severity:** {{incident.severity}}
      **Time Remaining:** {{sla.time_remaining}}
      
      [View Incident]({{incident.url}})
      
  sla_breach:
    title: "🚨 SLA Breach: {{incident.title}}"
    body: |
      Incident #{{incident.id}} has breached its SLA.
      
      **Breach Type:** {{sla.breach_type}}
      **Exceeded By:** {{sla.exceeded_by}}
      **Policy:** {{sla.policy_name}}
      
      Immediate attention required.
      
      [View Incident]({{incident.url}})
```

---

## Step 4: SLA Reporting

### Generate SLA Reports

```bash
# Weekly SLA compliance report
incident-copilot report sla \
  --period weekly \
  --format pdf \
  --output weekly-sla-report.pdf

# Monthly breakdown by team
incident-copilot report sla \
  --period monthly \
  --group-by team \
  --format csv \
  --output monthly-sla-by-team.csv
```

### Dashboard Metrics

```yaml
# config/dashboards/sla-metrics.yaml
widgets:
  - type: gauge
    title: "SLA Compliance Rate"
    metric: sla.compliance_percentage
    thresholds:
      red: 90
      yellow: 95
      green: 99
      
  - type: line_chart
    title: "MTTA Trend"
    metric: incidents.mtta_minutes
    period: 30d
    group_by: severity
    
  - type: table
    title: "Active SLA Breaches"
    query: |
      SELECT incident_id, title, severity, 
             sla_policy, breach_type, exceeded_by
      FROM incidents 
      WHERE sla_breached = true 
        AND status != 'resolved'
      ORDER BY severity, exceeded_by DESC
```

<!-- Diagram: SLA Dashboard Layout -->
<!-- Shows compliance gauge, trend charts, and breach table -->

---

## Step 5: SLA Pause Rules

Configure when SLA clocks should pause:

```yaml
# config/sla/pause-rules.yaml
pause_rules:
  # Pause when waiting for customer
  - name: waiting_on_customer
    trigger:
      status: waiting_customer
    resume:
      status: [open, in_progress]
      
  # Pause when blocked by external dependency
  - name: external_blocker
    trigger:
      labels: [blocked-external]
    resume:
      labels_removed: [blocked-external]
      
  # Pause during change freeze
  - name: change_freeze
    trigger:
      labels: [change-freeze]
    resume:
      labels_removed: [change-freeze]
    notification:
      message: "SLA paused due to change freeze"
```

---

## Best Practices

1. **Start conservative** - Begin with longer SLA windows, tighten as you mature
2. **Align with customer contracts** - Internal SLAs should be tighter than external
3. **Use severity-based tiers** - Critical issues need faster response than low priority
4. **Account for business hours** - Don't set unrealistic 24/7 SLAs if team isn't staffed
5. **Review regularly** - Analyze breaches monthly and adjust policies
6. **Automate escalation** - Don't rely on humans to notice SLA warnings

---

## Common Pitfalls

| Issue | Cause | Solution |
|-------|-------|----------|
| Too many breaches | Unrealistic SLA targets | Analyze historical data, adjust thresholds |
| Clock not pausing | Missing pause rule | Add pause rule for blocked/waiting states |
| Wrong policy applied | Overlapping conditions | Check policy priorities, use explicit conditions |
| Timezone issues | Misconfigured business hours | Verify timezone in calendar config |
| Missed warnings | Notification delay | Check alert channel configuration |

---

## Examples

### Example 1: E-commerce Platform

```yaml
sla_policies:
  - name: checkout_critical
    conditions:
      service: [checkout, payments]
      severity: critical
    targets:
      acknowledge: { breach_minutes: 5 }
      resolve: { breach_minutes: 30 }
    business_hours:
      calendar: "24x7"
      
  - name: catalog_high
    conditions:
      service: [catalog, search]
      severity: high
    targets:
      acknowledge: { breach_minutes: 15 }
      resolve: { breach_minutes: 120 }
```

### Example 2: B2B SaaS with Tiered Support

```yaml
sla_policies:
  - name: enterprise_tier
    conditions:
      custom_fields:
        customer_tier: enterprise
    targets:
      acknowledge: { breach_minutes: 15 }
      resolve: { breach_minutes: 240 }
      
  - name: professional_tier
    conditions:
      custom_fields:
        customer_tier: professional
    targets:
      acknowledge: { breach_minutes: 60 }
      resolve: { breach_minutes: 480 }
      
  - name: starter_tier
    conditions:
      custom_fields:
        customer_tier: starter
    targets:
      acknowledge: { breach_minutes: 240 }
      resolve: { breach_minutes: 1440 }
```

---

## Next Steps

- [Escalation Policies](./escalation-policies.md) - Set up escalation when SLAs breach
- [Custom Dashboards](./custom-dashboards.md) - Build SLA monitoring dashboards
- [Cost Tracking](./cost-tracking.md) - Measure the cost of SLA breaches
