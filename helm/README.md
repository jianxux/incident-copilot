# Incident Copilot Helm Chart

This Helm chart deploys the Incident Copilot application on a Kubernetes cluster.

## Prerequisites

- Kubernetes 1.21+
- Helm 3.0+
- PV provisioner (optional, for Redis persistence)

## Installation

### Add the repository (if hosted)

```bash
helm repo add incident-copilot https://your-org.github.io/incident-copilot
helm repo update
```

### Install from local chart

```bash
# Clone the repository
git clone https://github.com/your-org/incident-copilot.git
cd incident-copilot

# Install with default values
helm install incident-copilot ./helm/incident-copilot

# Install with custom values
helm install incident-copilot ./helm/incident-copilot -f my-values.yaml

# Install in a specific namespace
helm install incident-copilot ./helm/incident-copilot -n incident-copilot --create-namespace
```

### Install with inline values

```bash
helm install incident-copilot ./helm/incident-copilot \
  --set anthropic.apiKey=sk-ant-xxx \
  --set slack.botToken=xoxb-xxx \
  --set pagerduty.apiKey=xxx \
  --set pagerduty.webhookSecret=xxx
```

## Upgrading

```bash
# Upgrade to latest version
helm upgrade incident-copilot ./helm/incident-copilot

# Upgrade with new values
helm upgrade incident-copilot ./helm/incident-copilot -f my-values.yaml

# Rollback to previous release
helm rollback incident-copilot 1
```

## Uninstalling

```bash
helm uninstall incident-copilot
```

## Configuration

### General

| Parameter | Description | Default |
|-----------|-------------|---------|
| `replicaCount` | Number of replicas | `1` |
| `image.repository` | Image repository | `incident-copilot` |
| `image.tag` | Image tag | Chart appVersion |
| `image.pullPolicy` | Image pull policy | `IfNotPresent` |
| `imagePullSecrets` | Image pull secrets | `[]` |
| `nameOverride` | Override chart name | `""` |
| `fullnameOverride` | Override full name | `""` |

### Service Account

| Parameter | Description | Default |
|-----------|-------------|---------|
| `serviceAccount.create` | Create service account | `true` |
| `serviceAccount.annotations` | Service account annotations | `{}` |
| `serviceAccount.name` | Service account name | `""` |

### Service

| Parameter | Description | Default |
|-----------|-------------|---------|
| `service.type` | Service type | `ClusterIP` |
| `service.port` | Service port | `8000` |

### Ingress

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ingress.enabled` | Enable ingress | `false` |
| `ingress.className` | Ingress class name | `""` |
| `ingress.annotations` | Ingress annotations | `{}` |
| `ingress.hosts` | Ingress hosts configuration | See values.yaml |
| `ingress.tls` | Ingress TLS configuration | `[]` |

### Resources

| Parameter | Description | Default |
|-----------|-------------|---------|
| `resources.limits.cpu` | CPU limit | `500m` |
| `resources.limits.memory` | Memory limit | `512Mi` |
| `resources.requests.cpu` | CPU request | `100m` |
| `resources.requests.memory` | Memory request | `256Mi` |

### Autoscaling

| Parameter | Description | Default |
|-----------|-------------|---------|
| `autoscaling.enabled` | Enable HPA | `false` |
| `autoscaling.minReplicas` | Minimum replicas | `1` |
| `autoscaling.maxReplicas` | Maximum replicas | `10` |
| `autoscaling.targetCPUUtilizationPercentage` | Target CPU % | `80` |
| `autoscaling.targetMemoryUtilizationPercentage` | Target memory % | `80` |

### Application Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `config.logProvider` | Log provider (datadog/cloudwatch) | `datadog` |
| `config.aiModel` | AI model for summarization | `claude-sonnet-4-20250514` |
| `config.opsgenieRegion` | Opsgenie region (us/eu) | `us` |
| `config.awsRegion` | AWS region for CloudWatch | `us-east-1` |
| `config.cloudwatchLogGroupMap` | CloudWatch log group mapping (JSON) | `""` |

### Integration Secrets

#### PagerDuty

| Parameter | Description | Default |
|-----------|-------------|---------|
| `pagerduty.apiKey` | PagerDuty API key | `""` |
| `pagerduty.webhookSecret` | Webhook signing secret | `""` |

#### Opsgenie

| Parameter | Description | Default |
|-----------|-------------|---------|
| `opsgenie.apiKey` | Opsgenie API key (GenieKey) | `""` |
| `opsgenie.webhookSecret` | Webhook signing secret | `""` |

#### GitHub

| Parameter | Description | Default |
|-----------|-------------|---------|
| `github.token` | Personal access token | `""` |
| `github.org` | Organization name | `""` |

#### Datadog

| Parameter | Description | Default |
|-----------|-------------|---------|
| `datadog.apiKey` | Datadog API key | `""` |
| `datadog.appKey` | Datadog application key | `""` |

#### AWS CloudWatch

| Parameter | Description | Default |
|-----------|-------------|---------|
| `cloudwatch.accessKeyId` | AWS access key ID | `""` |
| `cloudwatch.secretAccessKey` | AWS secret access key | `""` |

#### Slack

| Parameter | Description | Default |
|-----------|-------------|---------|
| `slack.botToken` | Slack bot OAuth token | `""` |
| `slack.defaultChannel` | Default notification channel | `#incidents` |

#### Anthropic

| Parameter | Description | Default |
|-----------|-------------|---------|
| `anthropic.apiKey` | Anthropic API key | `""` |

### Redis

| Parameter | Description | Default |
|-----------|-------------|---------|
| `redis.enabled` | Enable bundled Redis | `true` |
| `redis.externalUrl` | External Redis URL (when disabled) | `""` |
| `redis.image.repository` | Redis image repository | `redis` |
| `redis.image.tag` | Redis image tag | `7-alpine` |
| `redis.service.port` | Redis service port | `6379` |
| `redis.persistence.enabled` | Enable Redis persistence | `false` |
| `redis.persistence.size` | PVC size | `1Gi` |
| `redis.persistence.storageClass` | Storage class | `""` |

### Health Probes

| Parameter | Description | Default |
|-----------|-------------|---------|
| `probes.liveness.enabled` | Enable liveness probe | `true` |
| `probes.liveness.path` | Liveness probe path | `/` |
| `probes.readiness.enabled` | Enable readiness probe | `true` |
| `probes.readiness.path` | Readiness probe path | `/` |

## Example Values

### Minimal Production Setup (PagerDuty + Datadog)

```yaml
# values-production-pd.yaml
replicaCount: 2

image:
  repository: your-registry/incident-copilot
  tag: "0.2.0"

ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: incident-copilot.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: incident-copilot-tls
      hosts:
        - incident-copilot.example.com

resources:
  limits:
    cpu: 1000m
    memory: 1Gi
  requests:
    cpu: 200m
    memory: 512Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 5

config:
  logProvider: datadog

pagerduty:
  apiKey: "your-pagerduty-api-key"
  webhookSecret: "your-webhook-secret"

github:
  token: "ghp_xxxx"
  org: "your-org"

datadog:
  apiKey: "your-datadog-api-key"
  appKey: "your-datadog-app-key"

slack:
  botToken: "xoxb-xxxx"
  defaultChannel: "#incidents"

anthropic:
  apiKey: "sk-ant-xxxx"

redis:
  enabled: true
  persistence:
    enabled: true
    size: 5Gi
```

### Opsgenie + CloudWatch Setup

```yaml
# values-opsgenie-cloudwatch.yaml
config:
  logProvider: cloudwatch
  opsgenieRegion: us
  awsRegion: us-west-2
  cloudwatchLogGroupMap: '{"payments-api": "/aws/lambda/payments,/ecs/payments"}'

opsgenie:
  apiKey: "your-opsgenie-geniekey"
  webhookSecret: "your-webhook-secret"

github:
  token: "ghp_xxxx"
  org: "your-org"

cloudwatch:
  accessKeyId: "AKIA..."
  secretAccessKey: "..."

slack:
  botToken: "xoxb-xxxx"
  defaultChannel: "#incidents"

anthropic:
  apiKey: "sk-ant-xxxx"
```

### External Redis (Using AWS ElastiCache)

```yaml
# values-external-redis.yaml
redis:
  enabled: false
  externalUrl: "redis://my-elasticache-cluster.xxxxx.cache.amazonaws.com:6379"
```

### Using External Secrets

For production, consider using External Secrets Operator or Sealed Secrets:

```yaml
# values-external-secrets.yaml
# Don't set secrets here - manage them externally

# Disable built-in secret creation
pagerduty: {}
opsgenie: {}
github: {}
datadog: {}
cloudwatch: {}
slack: {}
anthropic: {}

# Add annotation to reference external secret
podAnnotations:
  external-secrets.io/refresh-interval: "1h"
```

Then create an ExternalSecret that populates the same secret name:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: incident-copilot-secrets
spec:
  secretStoreRef:
    name: aws-secrets-manager
    kind: ClusterSecretStore
  target:
    name: incident-copilot-secrets
  data:
    - secretKey: ANTHROPIC_API_KEY
      remoteRef:
        key: incident-copilot/anthropic
        property: api_key
    # ... more mappings
```

## Troubleshooting

### Check pod logs

```bash
kubectl logs -l app.kubernetes.io/name=incident-copilot -f
```

### Verify secrets are mounted

```bash
kubectl exec -it deploy/incident-copilot -- env | grep -E "(API_KEY|TOKEN)"
```

### Check Redis connectivity

```bash
kubectl exec -it deploy/incident-copilot -- redis-cli -h incident-copilot-redis ping
```

### Validate webhook endpoints

```bash
kubectl port-forward svc/incident-copilot 8000:8000
curl http://localhost:8000/webhooks/health
```
