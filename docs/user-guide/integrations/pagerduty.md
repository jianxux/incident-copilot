# 🔔 PagerDuty Integration

PagerDuty is the primary alert source for Incident Copilot. When incidents trigger in PagerDuty, context cards are automatically generated and delivered.

---

## Overview

| Feature | Status |
|---------|--------|
| Alert webhooks | ✅ Supported |
| On-call roster | ✅ Supported |
| Incident sync | ✅ Supported |
| Service mapping | ✅ Supported |

---

## Prerequisites

- PagerDuty account with admin access
- At least one PagerDuty service configured
- Network access from PagerDuty to your Incident Copilot instance (HTTPS)

---

## 🔧 Setup

### Step 1: Create API Key

1. Log in to PagerDuty
2. Navigate to **Integrations** → **API Access Keys**
3. Click **Create New API Key**
4. Configure:
   - **Description**: `Incident Copilot`
   - **Type**: Read-only API Key
5. Click **Create Key** and copy the key

![PagerDuty API Key](../images/pagerduty-api-key-placeholder.png)
*Screenshot: Creating a PagerDuty API key*

Add to your `.env`:
```bash
PAGERDUTY_API_KEY=your-api-key-here
```

### Step 2: Configure Webhook

1. Go to **Services** → Select your service → **Integrations**
2. Click **Add Integration**
3. Search for and select **Generic Webhook (v3)**
4. Configure:
   - **Name**: `Incident Copilot`
   - **Endpoint URL**: `https://your-domain.com/webhooks/pagerduty`
   - **Events**: Select at minimum `incident.triggered`
   
   Recommended events:
   - `incident.triggered` (required)
   - `incident.acknowledged` (optional, for timeline)
   - `incident.resolved` (optional, for metrics)

![PagerDuty Webhook](../images/pagerduty-webhook-placeholder.png)
*Screenshot: Configuring PagerDuty webhook*

5. After saving, copy the **Signing Secret**

Add to your `.env`:
```bash
PAGERDUTY_WEBHOOK_SECRET=your-signing-secret
```

### Step 3: Configure Multiple Services (Optional)

To add Incident Copilot to multiple services:

**Option A: Repeat webhook setup** for each service

**Option B: Use Global Event Rules**
1. Go to **Automation** → **Event Rules**
2. Create a rule that triggers the webhook for all matching services

---

## 🔗 On-Call Roster Integration

Display the current on-call engineer in context cards.

### Configuration

```bash
# Enable on-call roster
ONCALL_PROVIDER=pagerduty
ONCALL_ENABLED=true

# Default schedule (used if no service mapping)
ONCALL_SCHEDULE_ID=PABCDEF

# Map services to specific schedules (optional)
ONCALL_SCHEDULE_MAP='{"payments-api": "PABC123", "auth-service": "PDEF456"}'
```

### Finding Schedule IDs

1. Go to **People** → **Schedules**
2. Click on a schedule
3. The ID is in the URL: `https://yourcompany.pagerduty.com/schedules/PABCDEF`

---

## 🗺️ Service Mapping

Map PagerDuty services to GitHub repositories:

```bash
SERVICE_REPO_MAP='{"payments-api": "my-org/payment-service"}'
```

If not configured, Incident Copilot assumes:
- PagerDuty service name = GitHub repo name

---

## ✅ Testing

### Validate Configuration

```bash
incident-copilot validate
```

### Test Integration

```bash
incident-copilot test-integration pagerduty
```

### Trigger Test Incident

1. In PagerDuty, go to your service
2. Click **+ New Incident**
3. Fill in a test title
4. Verify:
   - Webhook delivered (check PagerDuty → Integration → Recent Deliveries)
   - Context card appears in Slack

---

## 🔒 Security

### Webhook Signature Verification

All webhook payloads are verified using HMAC-SHA256:
- Incident Copilot validates the `X-PagerDuty-Signature` header
- Invalid signatures are rejected with 401 Unauthorized

### IP Allowlisting

If you use IP allowlisting, add PagerDuty's webhook IPs:
- See: [PagerDuty IP Safelist](https://support.pagerduty.com/docs/safelist-ips)

---

## 🐛 Troubleshooting

### Webhook Not Received

1. **Check webhook URL** - Ensure it's publicly accessible via HTTPS
2. **Check Recent Deliveries** in PagerDuty
3. **Verify signing secret** - No extra whitespace or quotes
4. **Check firewall rules** - Allow PagerDuty IPs

### Invalid Signature Error

```bash
# Common cause: whitespace in secret
# Wrong:
PAGERDUTY_WEBHOOK_SECRET="abc123"  # quotes included
PAGERDUTY_WEBHOOK_SECRET= abc123   # leading space

# Correct:
PAGERDUTY_WEBHOOK_SECRET=abc123
```

### On-Call Not Showing

1. Verify `ONCALL_ENABLED=true`
2. Check schedule ID is correct
3. Ensure API key has read access to schedules
4. Test with: `incident-copilot test-integration pagerduty-oncall`

---

## 📚 Related Documentation

- [Opsgenie Integration](./opsgenie.md) - Alternative alert source
- [Getting Started](../getting-started.md) - Initial setup guide
- [Troubleshooting](../troubleshooting.md) - General troubleshooting

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or [FAQ](../faq.md).*
