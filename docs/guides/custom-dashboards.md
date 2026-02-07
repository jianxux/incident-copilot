# Custom Dashboards Guide

This guide explains how to build custom dashboards in Incident Copilot to visualize incident metrics, SLA compliance, and team performance.

## Overview

Custom dashboards allow you to:
- **Visualize** key incident metrics
- **Monitor** SLA compliance in real-time
- **Track** team performance and trends
- **Share** insights with stakeholders

---

## Dashboard Components

### Available Widget Types

| Widget | Description | Use Case |
|--------|-------------|----------|
| **Metric** | Single large number | Total incidents, MTTR |
| **Gauge** | Circular progress indicator | SLA compliance % |
| **Line Chart** | Time series trends | Incident trends over time |
| **Bar Chart** | Category comparisons | Incidents by severity |
| **Pie Chart** | Distribution breakdown | Incidents by service |
| **Table** | Detailed data rows | Active incidents list |
| **Heatmap** | Two-dimensional data | Incidents by hour/day |
| **Status Board** | Service health grid | System status overview |

---

## Step 1: Create a Dashboard

### Via CLI

```bash
# Create a new dashboard
incident-copilot dashboard create \
  --name "SRE Overview" \
  --description "Main dashboard for SRE team" \
  --visibility team \
  --team sre-team

# Output:
# Dashboard created: dash_abc123
# URL: https://app.incident-copilot.com/dashboards/dash_abc123
```

### Via Configuration

```yaml
# config/dashboards/sre-overview.yaml
dashboard:
  id: sre-overview
  name: "SRE Overview"
  description: "Main dashboard for SRE team"
  
  settings:
    refresh_interval_seconds: 30
    default_time_range: 7d
    theme: dark
    
  visibility:
    type: team
    team_ids: [sre-team, platform-team]
    
  layout:
    columns: 12
    row_height: 80
```

---

## Step 2: Add Widgets

### Metric Widget

Display a single key metric:

```yaml
widgets:
  - id: total_incidents
    type: metric
    title: "Total Incidents (MTD)"
    position: { x: 0, y: 0, w: 3, h: 2 }
    
    query:
      metric: incidents.count
      time_range: month_to_date
      
    display:
      format: number
      color_thresholds:
        - value: 10
          color: green
        - value: 25
          color: yellow
        - value: 50
          color: red
```

### Gauge Widget

Show progress toward a goal:

```yaml
  - id: sla_compliance
    type: gauge
    title: "SLA Compliance"
    position: { x: 3, y: 0, w: 3, h: 2 }
    
    query:
      metric: sla.compliance_rate
      time_range: 30d
      
    display:
      min: 0
      max: 100
      format: percentage
      thresholds:
        - value: 90
          color: red
        - value: 95
          color: yellow
        - value: 100
          color: green
      target: 99.5
```

### Line Chart Widget

Visualize trends over time:

```yaml
  - id: incident_trend
    type: line_chart
    title: "Incident Trend"
    position: { x: 6, y: 0, w: 6, h: 3 }
    
    query:
      metrics:
        - name: incidents
          query: "count(incidents)"
          color: "#1a73e8"
        - name: sev1_incidents
          query: "count(incidents{severity='critical'})"
          color: "#ea4335"
      time_range: 30d
      granularity: 1d
      
    display:
      x_axis:
        label: "Date"
        format: "MMM DD"
      y_axis:
        label: "Count"
        min: 0
      legend: true
      fill: true
```

<!-- Diagram: Line Chart Widget -->
<!-- Shows incident trend with multiple series and legend -->

### Bar Chart Widget

Compare categories:

```yaml
  - id: incidents_by_severity
    type: bar_chart
    title: "Incidents by Severity"
    position: { x: 0, y: 2, w: 4, h: 3 }
    
    query:
      sql: |
        SELECT severity, COUNT(*) as count
        FROM incidents
        WHERE created_at > now() - interval '30 days'
        GROUP BY severity
        ORDER BY 
          CASE severity 
            WHEN 'critical' THEN 1
            WHEN 'high' THEN 2
            WHEN 'medium' THEN 3
            WHEN 'low' THEN 4
          END
          
    display:
      orientation: horizontal
      colors:
        critical: "#ea4335"
        high: "#fa7b17"
        medium: "#fbbc04"
        low: "#34a853"
```

### Table Widget

Display detailed data:

```yaml
  - id: active_incidents
    type: table
    title: "Active Incidents"
    position: { x: 4, y: 2, w: 8, h: 4 }
    
    query:
      sql: |
        SELECT 
          id,
          title,
          severity,
          status,
          assigned_to,
          created_at,
          sla_status
        FROM incidents
        WHERE status NOT IN ('resolved', 'closed')
        ORDER BY 
          CASE severity 
            WHEN 'critical' THEN 1
            WHEN 'high' THEN 2
            WHEN 'medium' THEN 3
            WHEN 'low' THEN 4
          END,
          created_at DESC
        LIMIT 20
        
    display:
      columns:
        - field: id
          label: "ID"
          link: "/incidents/{{id}}"
        - field: title
          label: "Title"
          truncate: 50
        - field: severity
          label: "Severity"
          badge: true
        - field: status
          label: "Status"
        - field: assigned_to
          label: "Assignee"
          avatar: true
        - field: sla_status
          label: "SLA"
          badge: true
      pagination: true
      page_size: 10
```

### Heatmap Widget

Show patterns by time:

```yaml
  - id: incident_heatmap
    type: heatmap
    title: "Incidents by Hour/Day"
    position: { x: 0, y: 6, w: 6, h: 3 }
    
    query:
      sql: |
        SELECT 
          EXTRACT(DOW FROM created_at) as day,
          EXTRACT(HOUR FROM created_at) as hour,
          COUNT(*) as count
        FROM incidents
        WHERE created_at > now() - interval '90 days'
        GROUP BY day, hour
        
    display:
      x_axis:
        label: "Hour"
        values: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 
                 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
      y_axis:
        label: "Day"
        values: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
      color_scale:
        min_color: "#e8f0fe"
        max_color: "#1a73e8"
```

<!-- Diagram: Heatmap Widget -->
<!-- Shows 7x24 grid with incident density by hour and day -->

### Status Board Widget

Monitor service health:

```yaml
  - id: service_status
    type: status_board
    title: "Service Health"
    position: { x: 6, y: 6, w: 6, h: 3 }
    
    data_source:
      type: services
      filter:
        environment: production
        
    display:
      layout: grid
      columns: 4
      show_last_incident: true
      statuses:
        - value: operational
          color: "#34a853"
          icon: check_circle
        - value: degraded
          color: "#fbbc04"
          icon: warning
        - value: outage
          color: "#ea4335"
          icon: error
```

---

## Step 3: Configure Data Sources

### SQL Queries

Direct SQL for complex queries:

```yaml
query:
  type: sql
  sql: |
    WITH monthly_stats AS (
      SELECT 
        date_trunc('month', created_at) as month,
        COUNT(*) as incident_count,
        AVG(EXTRACT(EPOCH FROM (resolved_at - created_at))/60) as avg_mttr
      FROM incidents
      WHERE created_at > now() - interval '12 months'
      GROUP BY date_trunc('month', created_at)
    )
    SELECT 
      month,
      incident_count,
      ROUND(avg_mttr, 2) as avg_mttr_minutes
    FROM monthly_stats
    ORDER BY month
```

### Metric Queries

Simplified metric syntax:

```yaml
query:
  type: metric
  metric: incidents.mttr.p95
  filters:
    severity: [critical, high]
    team: platform
  time_range: 30d
  granularity: 1d
```

### External Data Sources

Pull from monitoring tools:

```yaml
query:
  type: external
  source: datadog
  query: "sum:incidents.count{env:prod}.as_count()"
  
# Or Prometheus
query:
  type: external
  source: prometheus
  query: "sum(increase(incident_count_total[1d]))"
```

---

## Step 4: Layout and Styling

### Grid Layout

Dashboards use a 12-column grid:

```yaml
layout:
  columns: 12
  row_height: 80  # pixels
  margin: 10      # pixels between widgets
  
widgets:
  - id: widget1
    position:
      x: 0      # Column start (0-11)
      y: 0      # Row start
      w: 4      # Width in columns
      h: 2      # Height in rows
```

### Responsive Layouts

Define breakpoints for different screens:

```yaml
widgets:
  - id: mttr_metric
    position:
      default: { x: 0, y: 0, w: 3, h: 2 }
      tablet: { x: 0, y: 0, w: 6, h: 2 }
      mobile: { x: 0, y: 0, w: 12, h: 2 }
```

### Custom Styling

```yaml
dashboard:
  theme:
    background: "#1a1a2e"
    card_background: "#16213e"
    text_color: "#ffffff"
    accent_color: "#1a73e8"
    
widgets:
  - id: custom_styled
    style:
      background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
      border_radius: "12px"
      box_shadow: "0 4px 6px rgba(0, 0, 0, 0.1)"
```

---

## Step 5: Interactivity

### Drill-Down Links

```yaml
widgets:
  - id: severity_chart
    type: bar_chart
    
    interactions:
      on_click:
        action: navigate
        url: "/incidents?severity={{clicked.severity}}&status=open"
```

### Filters

Add dashboard-level filters:

```yaml
dashboard:
  filters:
    - id: time_range
      type: time_range
      default: 7d
      options: [24h, 7d, 30d, 90d, custom]
      
    - id: severity_filter
      type: multi_select
      label: "Severity"
      options:
        - value: critical
          label: "Critical"
        - value: high
          label: "High"
        - value: medium
          label: "Medium"
        - value: low
          label: "Low"
      default: [critical, high]
      
    - id: team_filter
      type: select
      label: "Team"
      data_source:
        type: teams
        
# Reference filters in widget queries
widgets:
  - id: filtered_incidents
    query:
      sql: |
        SELECT * FROM incidents
        WHERE severity = ANY($severity_filter)
          AND team_id = $team_filter
          AND created_at > $time_range.start
```

### Auto-Refresh

```yaml
dashboard:
  settings:
    refresh_interval_seconds: 30
    
widgets:
  - id: live_incidents
    settings:
      refresh_interval_seconds: 10  # Override for this widget
```

---

## Step 6: Share and Embed

### Share Dashboard

```bash
# Generate share link
incident-copilot dashboard share dash_abc123 \
  --visibility public \
  --expires 7d

# Output:
# Share URL: https://app.incident-copilot.com/shared/abc123xyz
# Expires: 2024-03-22
```

### Embed in Other Tools

```yaml
dashboard:
  embedding:
    enabled: true
    allowed_domains:
      - "internal.company.com"
      - "wiki.company.com"
      
# Get embed code
# <iframe src="https://app.incident-copilot.com/embed/dash_abc123" 
#         width="100%" height="600" frameborder="0"></iframe>
```

### Export to PDF

```bash
# Export dashboard as PDF
incident-copilot dashboard export dash_abc123 \
  --format pdf \
  --time-range 30d \
  --output sre-dashboard-march.pdf
```

---

## Dashboard Templates

### Template 1: Executive Summary

```yaml
# config/dashboards/executive-summary.yaml
dashboard:
  name: "Executive Summary"
  description: "High-level incident metrics for leadership"
  
widgets:
  - id: mttr_gauge
    type: gauge
    title: "MTTR (minutes)"
    position: { x: 0, y: 0, w: 3, h: 2 }
    query:
      metric: incidents.mttr.avg
      time_range: 30d
    display:
      target: 60
      
  - id: sla_compliance
    type: gauge
    title: "SLA Compliance"
    position: { x: 3, y: 0, w: 3, h: 2 }
    query:
      metric: sla.compliance_rate
    display:
      target: 99.5
      
  - id: monthly_trend
    type: line_chart
    title: "Monthly Trend"
    position: { x: 6, y: 0, w: 6, h: 3 }
    query:
      sql: |
        SELECT month, incident_count, mttr_minutes
        FROM monthly_metrics
        ORDER BY month
```

### Template 2: On-Call Dashboard

```yaml
# config/dashboards/oncall.yaml
dashboard:
  name: "On-Call Dashboard"
  description: "Real-time view for on-call engineers"
  
widgets:
  - id: active_critical
    type: metric
    title: "Active Critical"
    position: { x: 0, y: 0, w: 2, h: 2 }
    query:
      sql: |
        SELECT COUNT(*) 
        FROM incidents 
        WHERE severity = 'critical' 
          AND status NOT IN ('resolved', 'closed')
          
  - id: current_oncall
    type: status_board
    title: "Who's On-Call"
    position: { x: 2, y: 0, w: 4, h: 2 }
    data_source:
      type: oncall
      schedules: [primary, secondary]
      
  - id: active_incidents_table
    type: table
    title: "Active Incidents"
    position: { x: 0, y: 2, w: 12, h: 5 }
    # ... table config
```

---

## Best Practices

1. **Start simple** - Begin with 4-6 key metrics, expand as needed
2. **Use consistent colors** - Severity colors should match across widgets
3. **Set appropriate refresh** - Don't refresh too often (battery/bandwidth)
4. **Group related metrics** - Place related widgets together
5. **Include context** - Add descriptions to help viewers understand metrics
6. **Test on mobile** - Ensure responsive layouts work on all devices

---

## Common Pitfalls

| Issue | Cause | Solution |
|-------|-------|----------|
| Slow dashboard | Too many complex queries | Optimize queries, increase granularity |
| Confusing layout | Too many widgets | Reduce to essential metrics |
| Stale data | Low refresh rate | Increase refresh for critical metrics |
| Broken filters | Query not using filter params | Check filter references in SQL |
| Mobile issues | Fixed-width widgets | Use responsive position configs |

---

## Next Steps

- [Cost Tracking](./cost-tracking.md) - Add cost metrics to dashboards
- [SLA Configuration](./sla-configuration.md) - Create SLA monitoring dashboards
- [Real-Time Updates](./realtime-updates.md) - Add live update features
