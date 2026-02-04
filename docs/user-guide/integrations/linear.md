# 📋 Linear Integration

Create Linear issues for incidents and action items.

---

## 🔧 Setup

```bash
LINEAR_API_KEY=lin_api_xxx
LINEAR_TEAM_ID=TEAM-xxx
```

---

## ⚙️ Configuration

### Auto-create Issues

```bash
LINEAR_AUTO_CREATE_INCIDENT=true
LINEAR_INCIDENT_STATE=Triage
LINEAR_INCIDENT_PRIORITY_MAP='{
  "critical": 1,
  "high": 2,
  "medium": 3,
  "low": 4
}'
```

### Action Items

```bash
LINEAR_AUTO_CREATE_ACTION_ITEMS=true
LINEAR_ACTION_ITEM_STATE=Backlog
```

---

## 📚 Related Documentation

- [Jira Integration](./jira.md)
- [Postmortems](../features/postmortems.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
