# ☁️ AWS CloudWatch Integration

Fetch logs from AWS CloudWatch Logs.

---

## 🔧 Setup

### Configure AWS Credentials

```bash
LOG_PROVIDER=cloudwatch
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-key-id  # Or use IAM role
AWS_SECRET_ACCESS_KEY=your-secret
```

### Log Group Mapping

```bash
CLOUDWATCH_LOG_GROUP_MAP='{
  "payments-api": "/aws/lambda/payments-api",
  "auth-service": "/ecs/auth-service"
}'
```

---

## 🔐 IAM Permissions

```json
{
  "Effect": "Allow",
  "Action": [
    "logs:FilterLogEvents",
    "logs:GetLogEvents"
  ],
  "Resource": "arn:aws:logs:*:*:log-group:*"
}
```

---

## ✅ Testing

```bash
incident-copilot test-integration cloudwatch
```

---

## 📚 Related Documentation

- [Datadog Integration](./datadog.md)
- [Context Cards](../features/context-cards.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
