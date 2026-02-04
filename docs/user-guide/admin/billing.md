# 💳 Billing & Plans

Incident Copilot offers flexible pricing plans to match your team's needs, with billing managed through Stripe.

---

## 📦 Available Plans

### Plan Comparison

| Feature | Free | Starter | Pro | Enterprise |
|---------|------|---------|-----|------------|
| **Incidents/month** | 50 | 200 | 500 | Unlimited |
| **Users** | 3 | 10 | 25 | Unlimited |
| **Integrations** | 2 | 5 | 10 | Unlimited |
| **Context cards** | ✅ | ✅ | ✅ | ✅ |
| **AI summaries** | ✅ | ✅ | ✅ | ✅ |
| **Similar incidents** | ❌ | ✅ | ✅ | ✅ |
| **Postmortems** | ❌ | ✅ | ✅ | ✅ |
| **Analytics** | Basic | Full | Full | Full + Custom |
| **SSO** | ❌ | ❌ | ✅ | ✅ |
| **API access** | ❌ | ✅ | ✅ | ✅ |
| **Support** | Community | Email | Priority | Dedicated |
| **SLA** | ❌ | ❌ | 99.9% | 99.99% |

### Pricing

| Plan | Monthly | Annual (20% off) |
|------|---------|------------------|
| Free | $0 | $0 |
| Starter | $49 | $470/year |
| Pro | $149 | $1,430/year |
| Enterprise | Custom | Contact sales |

---

## 🔧 Managing Your Subscription

### View Current Plan

```bash
GET /api/billing/subscription

Response:
{
  "plan": "pro",
  "status": "active",
  "current_period_start": "2025-01-01",
  "current_period_end": "2025-02-01",
  "cancel_at_period_end": false
}
```

### Upgrade Plan

1. Go to Settings → Billing
2. Click **Upgrade Plan**
3. Select new plan
4. Complete payment via Stripe Checkout

**Via API:**
```bash
POST /api/billing/checkout
{
  "plan": "pro",
  "success_url": "https://app.example.com/billing/success",
  "cancel_url": "https://app.example.com/billing/cancel"
}

Response:
{
  "checkout_url": "https://checkout.stripe.com/..."
}
```

### Downgrade Plan

Downgrades take effect at the end of the current billing period.

```bash
POST /api/billing/downgrade
{
  "plan": "starter"
}
```

### Cancel Subscription

```bash
POST /api/billing/cancel
{
  "reason": "Not using enough",
  "feedback": "Optional feedback"
}
```

Cancellation takes effect at period end. You retain access until then.

---

## 📊 Usage Tracking

### View Current Usage

```bash
GET /api/billing/usage

Response:
{
  "period": "2025-01",
  "incidents": {
    "used": 127,
    "limit": 500,
    "percent": 25.4
  },
  "users": {
    "used": 12,
    "limit": 25,
    "percent": 48.0
  },
  "integrations": {
    "used": 6,
    "limit": 10,
    "percent": 60.0
  }
}
```

### Usage Alerts

Automatic alerts when approaching limits:

| Threshold | Action |
|-----------|--------|
| 80% | Email warning |
| 90% | In-app notification |
| 100% | Upgrade prompt, soft limit |

---

## 🧾 Invoices & Receipts

### View Invoices

```bash
GET /api/billing/invoices

Response:
{
  "invoices": [
    {
      "id": "inv_abc123",
      "amount": 14900,
      "currency": "usd",
      "status": "paid",
      "created": "2025-01-01T00:00:00Z",
      "pdf_url": "https://..."
    }
  ]
}
```

### Download Invoice

```bash
GET /api/billing/invoices/{invoice_id}/pdf
```

---

## 💰 Payment Methods

### Update Payment Method

Access the Stripe Customer Portal:

```bash
POST /api/billing/portal
{
  "return_url": "https://app.example.com/settings/billing"
}

Response:
{
  "portal_url": "https://billing.stripe.com/session/..."
}
```

In the portal, you can:
- Update credit card
- View billing history
- Download invoices
- Update billing address

### Supported Payment Methods

- Credit/Debit cards (Visa, Mastercard, Amex)
- ACH bank transfer (US only, Enterprise)
- Wire transfer (Enterprise)

---

## 🔄 Billing Cycle

### Monthly Billing

- Charged on the same day each month
- Prorated charges for mid-cycle changes
- Immediate access to new plan features

### Annual Billing

- 20% discount vs monthly
- Paid upfront for the year
- Prorated refund if downgrading mid-year

### Proration Example

Upgrading from Starter ($49/mo) to Pro ($149/mo) mid-cycle:

```
Days remaining: 15 of 30
Starter credit: $49 × (15/30) = $24.50
Pro charge: $149 × (15/30) = $74.50
Net charge: $74.50 - $24.50 = $50.00
```

---

## ⚙️ Stripe Configuration

### Environment Variables

```bash
# Stripe API Keys
STRIPE_API_KEY=sk_live_your-secret-key
STRIPE_PUBLISHABLE_KEY=pk_live_your-publishable-key
STRIPE_WEBHOOK_SECRET=whsec_your-webhook-secret

# Price IDs (from Stripe Dashboard)
STRIPE_PRICE_STARTER=price_starter_monthly_id
STRIPE_PRICE_PRO=price_pro_monthly_id
STRIPE_PRICE_ENTERPRISE=price_enterprise_monthly_id
```

### Webhook Configuration

Configure Stripe webhooks to receive payment events:

**Endpoint URL:** `https://your-domain.com/webhooks/stripe`

**Events to subscribe:**
- `checkout.session.completed`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.paid`
- `invoice.payment_failed`

---

## 🚫 Handling Limits

### Soft Limits

When you hit your plan limit:

1. **Warning** - Notification about approaching limit
2. **Soft block** - Encouraged to upgrade
3. **Grace period** - 5% overage allowed
4. **Hard block** - New incidents queue, not processed

### Upgrade Prompts

Users see upgrade prompts when:
- Creating incident past limit
- Adding user past limit
- Configuring integration past limit

---

## 💼 Enterprise Plans

### Custom Pricing

Enterprise plans include:
- Unlimited usage
- Custom contract terms
- Dedicated support
- On-premise deployment option
- Custom integrations
- SLA guarantees

### Contact Sales

```bash
POST /api/billing/enterprise-inquiry
{
  "company": "Acme Corp",
  "employees": "500+",
  "email": "contact@acme.com",
  "needs": "On-premise deployment, custom integrations"
}
```

---

## 🐛 Troubleshooting

### Payment Failed

**Causes:**
- Card declined
- Insufficient funds
- Expired card

**Solutions:**
1. Update payment method in billing portal
2. Contact your bank
3. Try different payment method

### "Plan limit exceeded"

**Cause:** Usage exceeds plan limits

**Solutions:**
1. Upgrade plan
2. Wait for next billing period (limits reset)
3. Contact support for temporary increase

### Invoice Not Received

**Cause:** Email delivery issue

**Solutions:**
1. Check spam folder
2. Update billing email
3. Download from billing portal

### Refund Request

Contact support with:
- Account email
- Reason for refund
- Invoice number

Refunds processed within 5-10 business days.

---

## 📚 Related Documentation

- [Tenant Setup](./tenant-setup.md) - Plan limits per tenant
- [User Management](./user-management.md) - User seat limits
- [API Keys](./api-keys.md) - API rate limits

---

*Need help? Contact billing@example.com or check the [Troubleshooting Guide](../troubleshooting.md).*
