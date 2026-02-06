# 📋 Jira Integration

Automatically create Jira issues for incidents and postmortem action items.

---

## 🔧 Setup

```bash
JIRA_URL=https://your-org.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_API_TOKEN=your-api-token
JIRA_PROJECT_KEY=INC
```

---

## ⚙️ Configuration

### Auto-create Issues

```bash
JIRA_AUTO_CREATE_INCIDENT=true
JIRA_INCIDENT_TYPE=Bug
JIRA_INCIDENT_PRIORITY_MAP='{
  "critical": "Highest",
  "high": "High",
  "medium": "Medium",
  "low": "Low"
}'
```

### Action Items from Postmortems

```bash
JIRA_AUTO_CREATE_ACTION_ITEMS=true
JIRA_ACTION_ITEM_TYPE=Task
```

---

## 📚 Related Documentation

- [Linear Integration](./linear.md)
- [Postmortems](../features/postmortems.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
