# ADR-003: Pluggable Integration Architecture

## Status
Accepted

## Context

Customers use different observability stacks:
- Monitoring: Datadog, CloudWatch, New Relic, Prometheus
- Alerting: PagerDuty, Opsgenie, VictorOps
- SCM: GitHub, GitLab, Bitbucket
- Communication: Slack, Teams, Discord

We need to support multiple integrations without tight coupling.

## Decision

Define abstract interfaces that each integration implements:

```python
class AlertAdapter(ABC):
    @abstractmethod
    async def parse_webhook(self, payload: dict) -> Incident
    
    @abstractmethod
    async def acknowledge(self, incident_id: str) -> bool

class LogAdapter(ABC):
    @abstractmethod
    async def get_logs(self, service: str, minutes: int) -> list[LogEntry]
    
    @abstractmethod
    async def search(self, query: str) -> list[LogEntry]

class DeployAdapter(ABC):
    @abstractmethod
    async def get_recent_deploys(self, repo: str, hours: int) -> list[Deploy]
```

Registry pattern for loading:
```python
# config.yaml
integrations:
  alert: pagerduty
  logs: datadog
  deploys: github

# runtime
alert_adapter = IntegrationRegistry.get("alert", config.alert)
```

## Consequences

### Positive
- Easy to add new integrations (implement interface)
- Customers only configure what they use
- Testing with mock adapters is simple
- Multi-cloud/multi-tool by design

### Negative
- Interface must be general enough for all implementations
- Some integrations have unique features we can't expose generically
- Configuration complexity for customers with many tools

### Mitigation
- `extra_features` dict for integration-specific capabilities
- Clear documentation on which features work with which integrations
- Wizard-based setup for common stack combinations
