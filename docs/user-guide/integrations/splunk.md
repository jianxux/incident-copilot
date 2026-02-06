# 🔍 Splunk Integration

Fetch logs from Splunk Enterprise or Splunk Cloud.

---

## 🔧 Setup

```bash
LOG_PROVIDER=splunk
SPLUNK_HOST=your-instance.splunkcloud.com
SPLUNK_PORT=8089
SPLUNK_TOKEN=your-hec-token
SPLUNK_INDEX=main
```

---

## 🔍 Search Configuration

```bash
SPLUNK_SEARCH_QUERY="index={index} sourcetype=* error"
SPLUNK_SEARCH_EARLIEST=-15m
```

---

## ✅ Testing

```bash
incident-copilot test-integration splunk
```

---

## 📚 Related Documentation

- [Datadog Integration](./datadog.md)
- [CloudWatch Integration](./cloudwatch.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
