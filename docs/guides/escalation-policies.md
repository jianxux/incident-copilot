# Escalation Policies Guide

This guide covers setting up escalation workflows in Incident Copilot to ensure incidents reach the right people at the right time.

## Overview

Escalation policies define:
- **Who** gets notified at each stage
- **When** to escalate (time-based or condition-based)
- **How** to contact responders (multi-channel)
- **Fallback** behavior when no one responds

---

## Core Concepts

### Escalation Hierarchy

```
Level 0: Primary On-Call
    │
    ▼ (15 min no response)
Level 1: Secondary On-Call
    │
    ▼ (15 min no response)
Level 2: Team Lead
    │
    ▼ (30 min no response)
Level 3: Engineering Manager
    │
    ▼ (30 min no response)
Level 4: VP of Engineering
```

### Escalation Triggers

| Trigger Type | Description |
|--------------|-------------|
| **Time-based** | No acknowledgment within X minutes |
| **Condition-based** | Severity upgrade, SLA breach, manual |
| **Hybrid** | Combination of time and conditions |

---

## Step 1: Define Escalation Policies

### Basic Policy Structure

```yaml
# config/escalation/policies.yaml
escalation_policies:
  - name: platform_team
    description: "Platform infrastructure team escalation"
    
    rules:
      - level: 0
        targets:
          - type: schedule
            schedule_id: platform_primary_oncall
        timeout_minutes: 15
        
      - level: 1
        targets:
          - type: schedule
            schedule_id: platform_secondary_oncall
        timeout_minutes: 15
        
      - level: 2
        targets:
          - type: user
            user_id: platform_lead
        timeout_minutes: 30
        
      - level: 3
        targets:
          - type: user
            user_id: eng_manager
        repeat:
          times: 3
          delay_minutes: 10
```

### Multi-Target Escalation

Notify multiple people simultaneously:

```yaml
escalation_policies:
  - name: critical_all_hands
    rules:
      - level: 0
        targets:
          # Notify on-call AND all senior engineers
          - type: schedule
            schedule_id: primary_oncall
          - type: team
            team_id: senior_engineers
            notify: all  # all, random, round_robin
        timeout_minutes: 5
```

### Conditional Escalation

Different paths based on incident properties:

```yaml
escalation_policies:
  - name: smart_escalation
    rules:
      - level: 0
        conditions:
          severity: [low, medium]
        targets:
          - type: schedule
            schedule_id: general_oncall
        timeout_minutes: 30
        
      - level: 0
        conditions:
          severity: [high, critical]
        targets:
          - type: schedule
            schedule_id: senior_oncall
        timeout_minutes: 10
        
      # Security incidents go directly to security team
      - level: 0
        conditions:
          tags: [security, breach]
        targets:
          - type: team
            team_id: security_team
            notify: all
        timeout_minutes: 5
```

---

## Step 2: Configure On-Call Schedules

### Create Schedules

```yaml
# config/oncall/schedules.yaml
schedules:
  - id: platform_primary_oncall
    name: "Platform Primary On-Call"
    timezone: "America/Los_Angeles"
    
    layers:
      - name: weekday
        rotation_type: weekly
        start_time: "2024-01-01T09:00:00"
        users:
          - alice@company.com
          - bob@company.com
          - carol@company.com
        restrictions:
          - type: day_of_week
            days: [monday, tuesday, wednesday, thursday, friday]
            start_time: "09:00"
            end_time: "18:00"
            
      - name: after_hours
        rotation_type: weekly
        users:
          - dave@company.com
          - eve@company.com
        restrictions:
          - type: day_of_week
            days: [monday, tuesday, wednesday, thursday, friday]
            start_time: "18:00"
            end_time: "09:00"  # Next day
            
      - name: weekend
        rotation_type: weekly
        users:
          - frank@company.com
          - grace@company.com
        restrictions:
          - type: day_of_week
            days: [saturday, sunday]
```

### Override Schedules

```bash
# Create an override (vacation coverage)
incident-copilot oncall override create \
  --schedule platform_primary_oncall \
  --user bob@company.com \
  --start "2024-03-15T09:00:00-07:00" \
  --end "2024-03-22T09:00:00-07:00" \
  --reason "Alice on vacation"

# List active overrides
incident-copilot oncall override list --schedule platform_primary_oncall
```

<!-- Diagram: On-Call Schedule Calendar View -->
<!-- Shows weekly rotation with overrides highlighted -->

---

## Step 3: Configure Notification Channels

### User Contact Methods

```yaml
# config/users/notification-preferences.yaml
users:
  - id: alice
    email: alice@company.com
    contact_methods:
      - type: email
        address: alice@company.com
        priority: 3  # Lowest priority
        
      - type: sms
        number: "+1-555-123-4567"
        priority: 2
        
      - type: push
        device_token: "xxx"
        priority: 1  # Highest priority
        
      - type: slack
        user_id: "U12345"
        priority: 2
        
    notification_rules:
      - urgency: high
        channels: [push, sms, slack]
        delay_minutes: 0
        
      - urgency: low
        channels: [email, slack]
        delay_minutes: 5
```

### Notification Sequences

```yaml
# config/escalation/notification-sequence.yaml
notification_sequences:
  aggressive:
    description: "For critical incidents"
    steps:
      - delay: 0
        channels: [push, sms]
      - delay: 2
        channels: [phone_call]
      - delay: 5
        channels: [push, sms, phone_call]  # Repeat
        
  standard:
    description: "For normal priority"
    steps:
      - delay: 0
        channels: [push, slack]
      - delay: 5
        channels: [sms]
      - delay: 10
        channels: [phone_call]
```

---

## Step 4: Automatic Escalation Triggers

### SLA-Based Escalation

```yaml
# config/escalation/sla-triggers.yaml
sla_triggers:
  - name: sla_warning_escalate
    condition:
      sla_status: at_risk
      current_level: 0
    action:
      escalate_to_level: 1
      notification:
        message: "SLA at risk, escalating to backup"
        
  - name: sla_breach_escalate
    condition:
      sla_status: breached
    action:
      escalate_to_level: 2
      add_labels: [sla-breached]
      notification:
        message: "SLA breached, escalating to management"
```

### Severity-Based Escalation

```yaml
# config/escalation/severity-triggers.yaml
severity_triggers:
  - name: severity_upgrade
    condition:
      severity_changed_to: [critical, sev1]
    action:
      reset_escalation: true  # Start from level 0
      use_policy: critical_escalation
      notification:
        message: "Severity upgraded to {{incident.severity}}"
```

### Manual Escalation

```bash
# Manually escalate an incident
incident-copilot incident escalate INC-12345 \
  --reason "Need senior engineer assistance" \
  --level 2

# Escalate and reassign
incident-copilot incident escalate INC-12345 \
  --to-user senior_engineer@company.com \
  --reason "Complex database issue"
```

---

## Step 5: Configure Fallback Behavior

### When No One Responds

```yaml
# config/escalation/fallback.yaml
fallback:
  # After all levels exhausted
  after_all_levels:
    action: loop_from_level
    level: 0
    max_loops: 3
    
  # If still no response
  after_max_loops:
    action: notify_fallback
    targets:
      - type: team
        team_id: all_engineers
        notify: all
      - type: external
        webhook_url: "${EMERGENCY_WEBHOOK}"
        
  # Business hours fallback
  outside_business_hours:
    use_policy: after_hours_escalation
```

### Dead Man's Switch

```yaml
# config/escalation/dead-mans-switch.yaml
dead_mans_switch:
  enabled: true
  check_interval_minutes: 5
  
  conditions:
    - incident_status: [open, acknowledged]
      no_activity_minutes: 60
      severity: [critical, high]
      
  action:
    notification:
      channels: [slack_sre, pagerduty]
      message: "No activity on {{incident.id}} for 60 minutes"
    escalate: true
```

---

## Step 6: Escalation Automation

### Auto-Acknowledge Rules

```yaml
# config/escalation/auto-ack.yaml
auto_acknowledge:
  # Acknowledge when someone views the incident
  - trigger: incident_viewed
    by: assigned_user
    
  # Acknowledge when comment is added
  - trigger: comment_added
    by: [assigned_user, escalation_target]
    
  # Don't auto-ack for these
  exceptions:
    - severity: critical  # Always require explicit ack
```

### Auto-Assign Rules

```yaml
# config/escalation/auto-assign.yaml
auto_assign:
  - conditions:
      service: payment-gateway
    assign_to:
      type: schedule
      schedule_id: payments_oncall
      
  - conditions:
      labels: [security]
    assign_to:
      type: team
      team_id: security_team
      strategy: round_robin
      
  - conditions:
      severity: critical
    assign_to:
      type: schedule
      schedule_id: senior_oncall
```

---

## Best Practices

1. **Start with 2-3 levels** - Don't over-engineer; add levels as needed
2. **15-minute timeouts** - Good balance between urgency and false positives
3. **Always have a fallback** - Never let incidents go unnoticed
4. **Test your escalations** - Run drills quarterly
5. **Respect quiet hours** - Use appropriate notification channels at night
6. **Document escalation paths** - Make sure everyone knows the chain

---

## Common Pitfalls

| Issue | Cause | Solution |
|-------|-------|----------|
| Escalation storms | Too aggressive timeouts | Increase timeout, add ack delay |
| Skipped levels | Conditions too specific | Simplify conditions, test matching |
| No notifications | Contact methods invalid | Verify user contact preferences |
| Infinite loops | No max loop limit | Set max_loops in fallback config |
| Wrong person paged | Stale schedule | Update schedules, use overrides |

---

## Testing Escalation Policies

### Dry Run Mode

```bash
# Test escalation without actually notifying
incident-copilot escalation test \
  --policy platform_team \
  --incident-template critical_outage \
  --dry-run

# Output:
# Level 0: Would notify alice@company.com via [push, sms]
# Level 0: Timeout at T+15min
# Level 1: Would notify bob@company.com via [push, sms]
# ...
```

### Fire Drill

```bash
# Create a drill incident
incident-copilot incident create \
  --title "DRILL: Testing escalation" \
  --severity high \
  --labels drill,test \
  --auto-resolve-minutes 30

# Review drill metrics
incident-copilot report drill --incident INC-DRILL-123
```

---

## Examples

### Example 1: Small Team (5 Engineers)

```yaml
escalation_policies:
  - name: small_team
    rules:
      - level: 0
        targets:
          - type: team
            team_id: engineering
            notify: round_robin
        timeout_minutes: 20
        
      - level: 1
        targets:
          - type: team
            team_id: engineering
            notify: all  # Everyone at once
        timeout_minutes: 20
```

### Example 2: Follow-the-Sun Global Team

```yaml
escalation_policies:
  - name: follow_the_sun
    rules:
      - level: 0
        targets:
          - type: schedule
            schedule_id: global_oncall  # Automatically selects by timezone
        timeout_minutes: 15
        
      - level: 1
        targets:
          - type: schedule
            schedule_id: global_backup
        timeout_minutes: 15
        
      - level: 2
        targets:
          - type: team
            team_id: regional_leads
            notify: all
```

### Example 3: Executive Escalation for Critical

```yaml
escalation_policies:
  - name: executive_escalation
    conditions:
      severity: critical
      customer_impact: high
      
    rules:
      - level: 0
        targets:
          - type: schedule
            schedule_id: senior_oncall
        timeout_minutes: 10
        
      - level: 1
        targets:
          - type: user
            user_id: vp_engineering
          - type: user
            user_id: cto
        notification_sequence: aggressive
```

---

## Next Steps

- [SLA Configuration](./sla-configuration.md) - Set SLAs that trigger escalations
- [Webhook Integration](./webhook-integration.md) - Integrate external alerting
- [Mobile App](./mobile-app.md) - Receive escalations on mobile
