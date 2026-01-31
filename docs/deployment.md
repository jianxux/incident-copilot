# Deployment Guide

This guide covers deploying Incident Copilot in various environments.

## Quick Start (Docker)

The fastest way to get started:

```bash
# Clone and configure
git clone https://github.com/jianxux/incident-copilot.git
cd incident-copilot
cp .env.example .env
# Edit .env with your API keys

# Run with Docker Compose
docker-compose up -d
```

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `PAGERDUTY_API_KEY` | PagerDuty API key for incident enrichment |
| `PAGERDUTY_WEBHOOK_SECRET` | Webhook signing secret for verification |
| `GITHUB_TOKEN` | Personal access token for deployment data |
| `GITHUB_ORG` | GitHub organization name |
| `SLACK_BOT_TOKEN` | Slack bot OAuth token |
| `ANTHROPIC_API_KEY` | Claude API key for log summarization |

### Optional - Log Providers

Choose one:

**Datadog (default):**
```
DATADOG_API_KEY=your-api-key
DATADOG_APP_KEY=your-app-key
DATADOG_SITE=datadoghq.com
```

**CloudWatch:**
```
LOG_PROVIDER=cloudwatch
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-west-2
```

### Optional - Additional Integrations

**Opsgenie:**
```
OPSGENIE_API_KEY=your-api-key
OPSGENIE_WEBHOOK_SECRET=your-webhook-secret
```

### Optional - Server Configuration

```
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=info
ENVIRONMENT=production
```

## Deployment Options

### 1. Single VM / VPS

Good for: Small teams, pilots, development

```bash
# On your VM
git clone https://github.com/jianxux/incident-copilot.git
cd incident-copilot

# Configure
cp .env.example .env
nano .env  # Add your keys

# Build and run
docker-compose up -d

# Check logs
docker-compose logs -f
```

Set up a reverse proxy (nginx) for HTTPS:

```nginx
server {
    listen 443 ssl;
    server_name copilot.yourcompany.com;
    
    ssl_certificate /etc/letsencrypt/live/copilot.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/copilot.yourcompany.com/privkey.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 2. Kubernetes

Good for: Production deployments, high availability

Create a namespace:
```bash
kubectl create namespace incident-copilot
```

Create secrets:
```bash
kubectl create secret generic incident-copilot-secrets \
  --namespace incident-copilot \
  --from-literal=PAGERDUTY_API_KEY=xxx \
  --from-literal=GITHUB_TOKEN=xxx \
  # ... add all secrets
```

Deploy:
```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: incident-copilot
  namespace: incident-copilot
spec:
  replicas: 2
  selector:
    matchLabels:
      app: incident-copilot
  template:
    metadata:
      labels:
        app: incident-copilot
    spec:
      containers:
        - name: api
          image: ghcr.io/jianxux/incident-copilot:latest
          ports:
            - containerPort: 8000
          envFrom:
            - secretRef:
                name: incident-copilot-secrets
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: incident-copilot
  namespace: incident-copilot
spec:
  selector:
    app: incident-copilot
  ports:
    - port: 80
      targetPort: 8000
  type: ClusterIP
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: incident-copilot
  namespace: incident-copilot
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
    - hosts:
        - copilot.yourcompany.com
      secretName: incident-copilot-tls
  rules:
    - host: copilot.yourcompany.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: incident-copilot
                port:
                  number: 80
```

Apply:
```bash
kubectl apply -f deployment.yaml
```

### 3. AWS ECS

Good for: AWS-native deployments

Task definition:
```json
{
  "family": "incident-copilot",
  "containerDefinitions": [
    {
      "name": "api",
      "image": "ghcr.io/jianxux/incident-copilot:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "secrets": [
        {
          "name": "PAGERDUTY_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:us-west-2:123456789:secret:incident-copilot/PAGERDUTY_API_KEY"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/incident-copilot",
          "awslogs-region": "us-west-2",
          "awslogs-stream-prefix": "api"
        }
      }
    }
  ],
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "256",
  "memory": "512"
}
```

## Webhook Configuration

### PagerDuty

1. Go to **Services** → Select your service → **Integrations**
2. Click **Add Integration** → **Generic Webhook (v3)**
3. Set the webhook URL: `https://copilot.yourcompany.com/webhooks/pagerduty`
4. Copy the **Signing Secret** to your `PAGERDUTY_WEBHOOK_SECRET`

Events to subscribe:
- `incident.triggered`
- `incident.acknowledged`
- `incident.resolved`

### Opsgenie

1. Go to **Settings** → **Integrations** → **Add Integration**
2. Select **Webhook**
3. Set the URL: `https://copilot.yourcompany.com/webhooks/opsgenie`
4. Enable signing and copy the secret

### Slack App

1. Create a new app at https://api.slack.com/apps
2. Add these Bot Token Scopes:
   - `chat:write`
   - `chat:write.public`
3. Install to workspace
4. Copy the **Bot User OAuth Token** to `SLACK_BOT_TOKEN`
5. Invite the bot to your incident channels

## Monitoring

### Health Checks

- `GET /` - Basic health check
- `GET /webhooks/health` - Webhook subsystem health

### Metrics (Future)

Prometheus metrics will be exposed at `/metrics`:
- `incident_copilot_alerts_received_total`
- `incident_copilot_context_assembly_duration_seconds`
- `incident_copilot_cards_delivered_total`

### Logging

Structured JSON logs by default. Set `LOG_LEVEL` to control verbosity:
- `debug` - All logs including detailed traces
- `info` - Normal operation (default)
- `warning` - Warnings and errors only
- `error` - Errors only

## Troubleshooting

### Webhooks not arriving

1. Check webhook URL is publicly accessible
2. Verify SSL certificate is valid
3. Check PagerDuty/Opsgenie webhook logs for delivery attempts
4. Ensure firewall allows inbound HTTPS

### Context cards not posting to Slack

1. Verify `SLACK_BOT_TOKEN` is correct
2. Ensure bot is invited to the target channel
3. Check for rate limiting in logs

### Slow context assembly

1. Check network latency to external APIs
2. Verify API rate limits aren't being hit
3. Consider increasing timeout values

---

*Last updated: January 2026*
