# 💻 Command Line Interface (CLI)

Incident Copilot includes a powerful CLI for validating configuration, testing integrations, and managing the service.

---

## 📦 Installation

The CLI is included with Incident Copilot:

```bash
# Install with pip
pip install -e ".[dev]"

# Verify installation
incident-copilot --help
```

---

## 🚀 Quick Reference

```bash
# Validate all configuration
incident-copilot validate

# Test a specific integration
incident-copilot test-integration github

# Test all integrations
incident-copilot test-all

# Send a test context card
incident-copilot send-test

# Show version
incident-copilot version
```

---

## 📋 Commands

### `validate` - Validate Configuration

Check all environment variables and configuration:

```bash
incident-copilot validate
```

**Output:**

```
╭──────────────────────────────────────────────────╮
│      Incident Copilot Configuration Validator    │
╰──────────────────────────────────────────────────╯

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┓
┃ Check                           ┃ Status ┃ Details  ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━┩
│ PagerDuty API Key               │   ✓    │          │
│ PagerDuty Webhook Secret        │   ✓    │          │
│ GitHub Token                    │   ✓    │          │
│ GitHub Organization             │   ✓    │          │
│ Log Provider                    │   ✓    │          │
│ Datadog API Key                 │   ✓    │          │
│ Datadog App Key                 │   ✓    │          │
│ Slack Bot Token                 │   ✓    │          │
│ Slack Default Channel           │   ✓    │          │
│ Anthropic API Key               │   ✓    │          │
│ OpenAI API Key (for embeddings) │   ○    │ Optional │
└─────────────────────────────────┴────────┴──────────┘

✓ All 10 configuration checks passed!
```

**Options:**

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Show detailed output including masked values |

**Exit Codes:**

| Code | Meaning |
|------|---------|
| 0 | All required checks passed |
| 1 | One or more required checks failed |

---

### `test-integration` - Test Single Integration

Test connectivity to a specific integration:

```bash
incident-copilot test-integration <integration>
```

**Supported Integrations:**

| Integration | What It Tests |
|-------------|---------------|
| `github` | API authentication, rate limits |
| `gitlab` | API authentication, project access |
| `datadog` | API/App key validation |
| `cloudwatch` | AWS credentials, log group access |
| `slack` | Bot token, workspace access |
| `pagerduty` | API key, abilities check |
| `opsgenie` | API key validation |

**Example:**

```bash
incident-copilot test-integration github
```

**Output:**

```
Testing github integration...
✓ github integration working!
  Authenticated as: your-username
  Rate limit remaining: 4987
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `-t, --timeout` | 30 | Timeout in seconds |

---

### `test-all` - Test All Integrations

Test all configured integrations at once:

```bash
incident-copilot test-all
```

**Output:**

```
╭─────────────────────────────────╮
│    Testing All Integrations     │
╰─────────────────────────────────╯

Testing github... ✓
Testing slack... ✓
Testing datadog... ✓
Testing pagerduty... ✓

✓ All 4 integrations working!
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `-t, --timeout` | 30 | Timeout per integration |

---

### `send-test` - Send Test Context Card

Generate and send a demo context card:

```bash
incident-copilot send-test
```

**Output:**

```
Sending test context card to #incidents...
✓ Test card sent to #incidents!
  Message timestamp: 1705329600.123456
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `-c, --channel` | Default channel | Slack channel to send to |
| `-s, --scenario` | `demo-stripe-timeout` | Demo scenario to use |

**Available Scenarios:**

| Scenario | Description |
|----------|-------------|
| `demo-stripe-timeout` | Payment API timeout scenario |
| `demo-db-connection` | Database connection failure |
| `demo-memory-leak` | Memory exhaustion scenario |
| `demo-deployment` | Bad deployment rollback |

**Example:**

```bash
# Send to specific channel
incident-copilot send-test -c "#test-channel"

# Use different scenario
incident-copilot send-test -s demo-db-connection
```

---

### `version` - Show Version

Display version information:

```bash
incident-copilot version
```

**Output:**

```
Incident Copilot
Version: 0.1.0
Python: 3.11.0
```

---

## 🔧 Configuration

The CLI reads configuration from:

1. **Environment variables** (`.env` file)
2. **Config file** (`config.yaml` if present)

### Required for Most Commands

```bash
# Minimum for validation
ANTHROPIC_API_KEY=sk-ant-xxx

# For integration tests
GITHUB_TOKEN=ghp_xxx
SLACK_BOT_TOKEN=xoxb-xxx
```

---

## 🎯 Common Workflows

### Initial Setup Verification

After first install, validate everything:

```bash
# 1. Check configuration
incident-copilot validate -v

# 2. Test integrations
incident-copilot test-all

# 3. Send test card
incident-copilot send-test
```

### Debugging Integration Issues

When an integration isn't working:

```bash
# Test specific integration with verbose output
incident-copilot test-integration datadog

# Check configuration
incident-copilot validate -v | grep -i datadog
```

### CI/CD Integration

Use in pipelines to verify deployment:

```bash
#!/bin/bash
set -e

# Validate config (exit 1 if missing required vars)
incident-copilot validate

# Test integrations
incident-copilot test-all

# Send deployment notification
incident-copilot send-test -s demo-deployment
```

---

## 🐛 Troubleshooting

### Command Not Found

**Cause:** Package not installed or not in PATH

**Solutions:**

```bash
# Reinstall
pip install -e ".[dev]"

# Or use module directly
python -m src.cli.main --help
```

### Import Errors

**Cause:** Missing dependencies

**Solutions:**

```bash
# Install all dependencies
pip install -e ".[dev]"

# Or install specific ones
pip install typer rich httpx
```

### Timeout Errors

**Cause:** Slow network or API

**Solutions:**

```bash
# Increase timeout
incident-copilot test-integration github -t 60
```

### Configuration Not Loading

**Cause:** `.env` file not found or not loaded

**Solutions:**

```bash
# Ensure you're in the right directory
cd /path/to/incident-copilot

# Or specify env file
export $(cat .env | xargs)
incident-copilot validate
```

---

## 📊 Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Configuration or integration error |
| 2 | CLI usage error |

---

## 🔌 Extending the CLI

The CLI is built with [Typer](https://typer.tiangolo.com/) and can be extended:

```python
# src/cli/main.py

@app.command()
def my_custom_command(
    option: str = typer.Option(..., help="My option"),
):
    """My custom command description."""
    # Implementation
    pass
```

---

## 📚 Related Documentation

- [Getting Started](./getting-started.md) - Initial setup
- [Troubleshooting](./troubleshooting.md) - Common issues
- [API Reference](./api-reference.md) - REST API docs

---

*Need help? Run `incident-copilot --help` or check the [Troubleshooting Guide](./troubleshooting.md).*
