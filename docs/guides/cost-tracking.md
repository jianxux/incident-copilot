# Cost Tracking Guide

This guide explains how to track incident costs and measure the ROI of your incident management process with Incident Copilot.

## Overview

Understanding the true cost of incidents helps you:
- **Prioritize** reliability investments
- **Justify** tooling and headcount
- **Identify** expensive failure patterns
- **Measure** improvement over time

---

## Cost Categories

### Direct Costs

| Category | Description | Example |
|----------|-------------|---------|
| **Engineering Time** | Hours spent by responders | 10 engineers × 2 hours = 20 person-hours |
| **Infrastructure** | Cloud costs during incident | Scaled up to handle load: $5,000 |
| **Third-Party** | External services, consultants | Called AWS support: $15,000 |
| **Customer Credits** | SLA violation credits | Issued refunds: $50,000 |

### Indirect Costs

| Category | Description | Example |
|----------|-------------|---------|
| **Lost Revenue** | Transaction failure, downtime | 2 hours × $100k/hour = $200,000 |
| **Reputation** | Customer churn, brand damage | Hard to quantify, estimated |
| **Opportunity Cost** | Delayed features, projects | Sprint disruption: 40 person-hours |
| **Compliance** | Regulatory fines, audits | GDPR fine: $500,000 |

---

## Step 1: Configure Cost Tracking

### Enable Cost Tracking

```yaml
# config/cost-tracking.yaml
cost_tracking:
  enabled: true
  currency: USD
  fiscal_year_start: "01-01"  # MM-DD
  
  # Default hourly rates by role
  hourly_rates:
    engineer: 150
    senior_engineer: 200
    staff_engineer: 250
    manager: 175
    director: 225
    executive: 300
    
  # Team-specific overrides
  team_rates:
    security_team:
      engineer: 175
      senior_engineer: 225
```

### Configure Cost Rules

```yaml
# config/cost-tracking/rules.yaml
cost_rules:
  # Automatic time tracking
  time_tracking:
    enabled: true
    track_from:
      - status_change: acknowledged
      - role_assignment
    track_until:
      - status_change: resolved
      - role_unassignment
      
  # Infrastructure cost integration
  infrastructure:
    enabled: true
    providers:
      - type: aws
        cost_explorer_integration: true
        tag_filter: "incident_id"
      - type: gcp
        billing_export_dataset: "billing_export"
      - type: datadog
        api_key: "${DATADOG_API_KEY}"
        
  # Revenue impact estimation
  revenue_impact:
    enabled: true
    metrics:
      - name: transactions_per_minute
        source: datadog
        query: "sum:checkout.transactions{env:prod}.as_rate()"
        revenue_per_unit: 50  # Average transaction value
```

---

## Step 2: Track Engineering Time

### Automatic Time Tracking

Time is tracked automatically based on incident activity:

```yaml
# config/cost-tracking/time-tracking.yaml
time_tracking:
  auto_track:
    # Track when user is assigned
    - event: user_assigned
      start_tracking: true
      
    # Track when user comments
    - event: comment_added
      add_time_minutes: 5
      
    # Track when user views incident (optional)
    - event: incident_viewed
      add_time_minutes: 2
      only_if:
        user_role: responder
        
  # Round to nearest increment
  rounding:
    increment_minutes: 15
    direction: up
```

### Manual Time Entry

```bash
# Log time spent
incident-copilot cost log-time INC-12345 \
  --user alice@company.com \
  --hours 2.5 \
  --category response \
  --notes "Investigating database locks"

# Log time for multiple users (war room)
incident-copilot cost log-time INC-12345 \
  --users alice@company.com,bob@company.com,carol@company.com \
  --hours 1.5 \
  --category war_room
```

### Time Entry via UI

<!-- Diagram: Time Entry Form -->
<!-- Shows time entry modal with user, hours, category, notes fields -->

The incident detail page includes a "Log Time" button that opens a quick entry form.

---

## Step 3: Track Revenue Impact

### Configure Revenue Metrics

```yaml
# config/cost-tracking/revenue.yaml
revenue_metrics:
  - id: checkout_revenue
    name: "Checkout Revenue"
    source: datadog
    query: "sum:checkout.revenue{env:prod}.as_rate()"
    unit: usd_per_minute
    
  - id: api_revenue
    name: "API Revenue"
    source: prometheus
    query: "sum(rate(api_revenue_total[1m]))"
    unit: usd_per_minute
    
  - id: subscription_value
    name: "Subscription MRR"
    source: static
    value: 500000  # $500k MRR
    unit: usd_per_month
```

### Impact Calculation

Revenue impact is calculated automatically:

```
Revenue Impact = (Normal Revenue Rate - Incident Revenue Rate) × Duration
```

Example:
```
Normal: $10,000/minute
During incident: $2,000/minute
Duration: 45 minutes
Impact: ($10,000 - $2,000) × 45 = $360,000
```

### Partial Impact

For partial outages:

```yaml
# On incident, set impact percentage
incident_update:
  incident_id: INC-12345
  impact_percentage: 30  # 30% of transactions affected
  
# Revenue impact will be:
# $360,000 × 0.30 = $108,000
```

---

## Step 4: Track Infrastructure Costs

### AWS Cost Integration

```yaml
# config/cost-tracking/aws.yaml
aws_integration:
  enabled: true
  region: us-east-1
  
  cost_allocation:
    # Tag resources with incident ID for tracking
    auto_tag: true
    tag_key: incident_id
    
  cost_categories:
    - name: compute
      services: [EC2, ECS, Lambda]
    - name: data
      services: [RDS, DynamoDB, S3]
    - name: network
      services: [CloudFront, ELB, VPC]
      
  # Fetch costs for resources tagged during incident
  query:
    lookback_days: 7
    granularity: DAILY
```

### Manual Infrastructure Cost Entry

```bash
# Log infrastructure cost
incident-copilot cost log-infrastructure INC-12345 \
  --amount 5000 \
  --category compute \
  --description "Emergency EC2 scale-up" \
  --provider aws
```

---

## Step 5: Track Customer Impact

### SLA Credits

```yaml
# config/cost-tracking/sla-credits.yaml
sla_credits:
  enabled: true
  
  policies:
    - name: enterprise_sla
      customer_tier: enterprise
      thresholds:
        - downtime_minutes: 60
          credit_percentage: 10
        - downtime_minutes: 240
          credit_percentage: 25
        - downtime_minutes: 1440
          credit_percentage: 50
          
  # Calculate based on customer MRR
  credit_basis: customer_mrr
```

### Customer Churn Risk

```yaml
# config/cost-tracking/churn-risk.yaml
churn_risk:
  enabled: true
  
  risk_factors:
    - condition:
        customer_tier: enterprise
        impact: high
      risk_score: 0.15  # 15% churn risk
      estimated_ltv: 100000
      
    - condition:
        incidents_this_month: { gte: 3 }
      risk_score: 0.25
```

---

## Step 6: Generate Cost Reports

### Incident Cost Summary

```bash
# Get cost summary for an incident
incident-copilot cost summary INC-12345

# Output:
# ══════════════════════════════════════════════
# Cost Summary: INC-12345
# ══════════════════════════════════════════════
# 
# ENGINEERING TIME
#   Response:        8.5 hours    $1,275.00
#   Investigation:   4.0 hours    $  600.00
#   Remediation:     3.0 hours    $  450.00
#   ─────────────────────────────────────────
#   Subtotal:       15.5 hours    $2,325.00
# 
# INFRASTRUCTURE
#   AWS (compute):                $  850.00
#   AWS (data):                   $  125.00
#   ─────────────────────────────────────────
#   Subtotal:                     $  975.00
# 
# REVENUE IMPACT
#   Lost transactions (45 min):  $108,000.00
# 
# CUSTOMER IMPACT
#   SLA credits issued:           $5,000.00
#   Churn risk (estimated):      $15,000.00
#   ─────────────────────────────────────────
#   Subtotal:                    $20,000.00
# 
# ══════════════════════════════════════════════
# TOTAL INCIDENT COST:          $131,300.00
# ══════════════════════════════════════════════
```

### Monthly Cost Report

```bash
# Generate monthly report
incident-copilot cost report monthly \
  --month 2024-03 \
  --format pdf \
  --output march-2024-incident-costs.pdf
```

<!-- Diagram: Monthly Cost Report -->
<!-- Shows bar chart of costs by category, pie chart by team, trend line -->

### Cost by Category Dashboard

```yaml
# config/dashboards/cost-dashboard.yaml
widgets:
  - type: metric
    title: "Total Cost (MTD)"
    query: "sum(incident_cost_total{month='current'})"
    format: currency
    
  - type: bar_chart
    title: "Cost by Category"
    query: |
      SELECT category, SUM(amount) as total
      FROM incident_costs
      WHERE month = current_month()
      GROUP BY category
    
  - type: line_chart
    title: "Cost Trend (12 months)"
    query: |
      SELECT month, SUM(amount) as total
      FROM incident_costs
      WHERE created_at > now() - interval '12 months'
      GROUP BY month
      ORDER BY month
      
  - type: table
    title: "Top 10 Most Expensive Incidents"
    query: |
      SELECT incident_id, title, total_cost
      FROM incidents
      WHERE month = current_month()
      ORDER BY total_cost DESC
      LIMIT 10
```

---

## Step 7: Measure ROI

### Track Improvement Metrics

```yaml
# config/cost-tracking/roi.yaml
roi_metrics:
  baseline:
    period: "2023-Q4"  # Baseline quarter
    metrics:
      mttd_minutes: 45
      mttr_minutes: 120
      incidents_per_month: 25
      avg_cost_per_incident: 50000
      
  investments:
    - name: "Incident Copilot Implementation"
      cost: 50000
      date: "2024-01-01"
      
    - name: "On-call Training Program"
      cost: 25000
      date: "2024-02-01"
```

### ROI Dashboard

```yaml
# config/dashboards/roi-dashboard.yaml
widgets:
  - type: comparison
    title: "MTTR Improvement"
    baseline: 120
    current: "avg(incidents.mttr_minutes)"
    format: percentage_reduction
    
  - type: comparison
    title: "Incidents Prevented"
    baseline: 25
    current: "count(incidents{month='current'})"
    format: reduction
    
  - type: roi_calculator
    title: "ROI Summary"
    investments: 75000
    savings_query: |
      SELECT 
        baseline_cost - current_cost as savings
      FROM (
        SELECT 
          25 * 50000 as baseline_cost,
          COUNT(*) * AVG(total_cost) as current_cost
        FROM incidents
        WHERE month = current_month()
      )
```

### ROI Report

```bash
# Generate ROI report
incident-copilot cost roi-report \
  --baseline-period 2023-Q4 \
  --current-period 2024-Q1 \
  --format pdf

# Output includes:
# - Metric improvements (MTTD, MTTR, incident count)
# - Cost savings calculation
# - Investment payback period
# - Annualized ROI percentage
```

---

## Best Practices

1. **Track consistently** - Ensure all incidents have time logged
2. **Use automation** - Auto-track where possible to reduce manual effort
3. **Review monthly** - Analyze cost trends and outliers
4. **Include indirect costs** - Revenue impact often exceeds direct costs
5. **Communicate ROI** - Share improvements with leadership
6. **Calibrate estimates** - Validate revenue impact calculations periodically

---

## Common Pitfalls

| Issue | Cause | Solution |
|-------|-------|----------|
| Underestimated costs | Missing categories | Include indirect costs, opportunity cost |
| Inaccurate time | Manual entry forgotten | Use auto-tracking, require time logging |
| Wrong revenue impact | Bad metric configuration | Validate queries, check during incidents |
| ROI not visible | No baseline | Establish baseline before implementing changes |
| Gaming metrics | Incentive misalignment | Focus on trends, not absolute numbers |

---

## Examples

### Example 1: Calculate War Room Cost

```bash
# 10 engineers in a 2-hour war room
# Average rate: $175/hour

incident-copilot cost log-time INC-12345 \
  --users eng1,eng2,eng3,eng4,eng5,eng6,eng7,eng8,eng9,eng10 \
  --hours 2 \
  --category war_room \
  --notes "Critical outage war room"

# Cost: 10 × 2 × $175 = $3,500
```

### Example 2: Full Incident Cost Breakdown

```yaml
incident: INC-12345
title: "Payment Gateway Outage"
duration_minutes: 90

costs:
  engineering_time:
    - user: alice
      hours: 3.5
      role: senior_engineer
      cost: 700
    - user: bob
      hours: 2.0
      role: engineer
      cost: 300
    - user: carol
      hours: 1.5
      role: manager
      cost: 263
      
  infrastructure:
    - provider: aws
      category: compute
      amount: 450
      description: "Auto-scaling triggered"
      
  revenue_impact:
    normal_rate: 15000  # $/minute
    incident_rate: 3000
    duration_minutes: 90
    impact: 1080000
    
  customer_impact:
    credits_issued: 25000
    customers_affected: 150
    
total_cost: 1106713
```

---

## Next Steps

- [Custom Dashboards](./custom-dashboards.md) - Build cost tracking dashboards
- [SLA Configuration](./sla-configuration.md) - Link SLA breaches to costs
- [Enterprise Setup](./enterprise-setup.md) - Multi-tenant cost allocation
