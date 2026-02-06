# API Examples

This document provides practical code examples for common API operations using curl, Python, and JavaScript.

---

## Authentication

### Login with Email/Password

**curl:**

```bash
curl -X POST https://api.example.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "your-password"
  }'
```

**Python:**

```python
import requests

response = requests.post(
    "https://api.example.com/api/auth/login",
    json={
        "email": "user@example.com",
        "password": "your-password"
    }
)

data = response.json()
access_token = data["access_token"]
refresh_token = data["refresh_token"]

# Use the token for subsequent requests
headers = {"Authorization": f"Bearer {access_token}"}
```

**JavaScript:**

```javascript
const response = await fetch('https://api.example.com/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    email: 'user@example.com',
    password: 'your-password'
  })
});

const { access_token, refresh_token } = await response.json();

// Use the token for subsequent requests
const headers = { 'Authorization': `Bearer ${access_token}` };
```

### Refresh Access Token

**Python:**

```python
def refresh_access_token(refresh_token):
    response = requests.post(
        "https://api.example.com/api/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise Exception("Token refresh failed")
```

**JavaScript:**

```javascript
async function refreshAccessToken(refreshToken) {
  const response = await fetch('https://api.example.com/api/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken })
  });
  
  if (!response.ok) throw new Error('Token refresh failed');
  const data = await response.json();
  return data.access_token;
}
```

---

## Incidents

### Get MTTR Statistics

**curl:**

```bash
curl -X GET "https://api.example.com/api/analytics/mttr?days=7&service=payments-api" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

**Python:**

```python
import requests

def get_mttr_stats(access_token, days=7, service=None):
    params = {"days": days}
    if service:
        params["service"] = service
    
    response = requests.get(
        "https://api.example.com/api/analytics/mttr",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params
    )
    
    return response.json()

# Example usage
stats = get_mttr_stats(access_token, days=30, service="payments-api")
print(f"Mean MTTR: {stats['mean_mttr_minutes']} minutes")
print(f"P90 MTTR: {stats['p90_mttr_minutes']} minutes")
```

**JavaScript:**

```javascript
async function getMttrStats(accessToken, days = 7, service = null) {
  const params = new URLSearchParams({ days: days.toString() });
  if (service) params.append('service', service);
  
  const response = await fetch(
    `https://api.example.com/api/analytics/mttr?${params}`,
    { headers: { 'Authorization': `Bearer ${accessToken}` } }
  );
  
  return response.json();
}

// Example usage
const stats = await getMttrStats(accessToken, 30, 'payments-api');
console.log(`Mean MTTR: ${stats.mean_mttr_minutes} minutes`);
```

### Compare Periods

**Python:**

```python
def compare_periods(access_token, days=7, service=None):
    params = {"days": days}
    if service:
        params["service"] = service
    
    response = requests.get(
        "https://api.example.com/api/analytics/comparison",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params
    )
    
    data = response.json()
    
    if data["mttr_change_percent"] < 0:
        print(f"MTTR improved by {abs(data['mttr_change_percent'])}%!")
    else:
        print(f"MTTR increased by {data['mttr_change_percent']}%")
    
    return data
```

---

## Postmortems

### Generate Postmortem

**curl:**

```bash
curl -X POST https://api.example.com/api/postmortems/generate \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INC-12345",
    "format": "markdown",
    "include_ai_analysis": true
  }'
```

**Python:**

```python
def generate_postmortem(access_token, incident_id, include_ai=True):
    response = requests.post(
        "https://api.example.com/api/postmortems/generate",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json={
            "incident_id": incident_id,
            "format": "markdown",
            "include_ai_analysis": include_ai
        }
    )
    
    return response.json()

# Example usage
result = generate_postmortem(access_token, "INC-12345")
postmortem = result["postmortem"]
print(f"Postmortem ID: {postmortem['id']}")
print(f"AI Generated: {postmortem['ai_generated']}")
```

**JavaScript:**

```javascript
async function generatePostmortem(accessToken, incidentId, includeAi = true) {
  const response = await fetch('https://api.example.com/api/postmortems/generate', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      incident_id: incidentId,
      format: 'markdown',
      include_ai_analysis: includeAi
    })
  });
  
  return response.json();
}
```

### Export Postmortem to Confluence

**Python:**

```python
def export_postmortem(access_token, postmortem_id, format="confluence"):
    response = requests.post(
        f"https://api.example.com/api/postmortems/{postmortem_id}/export",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json={"format": format}
    )
    
    data = response.json()
    
    # Save to file
    with open(f"postmortem_{postmortem_id}.txt", "w") as f:
        f.write(data["content"])
    
    return data["content"]
```

---

## Webhooks

### Configure PagerDuty Webhook

```bash
# In PagerDuty, configure webhook with:
# URL: https://api.example.com/webhooks/pagerduty
# Events: incident.triggered
```

### Test PagerDuty Webhook Locally

**curl:**

```bash
curl -X POST http://localhost:8000/webhooks/pagerduty \
  -H "Content-Type: application/json" \
  -d '{
    "event": {
      "event_type": "incident.triggered",
      "data": {
        "id": "TEST-001",
        "incident_number": 1,
        "title": "Test Incident",
        "urgency": "high",
        "created_at": "2024-01-15T10:30:00Z",
        "html_url": "https://example.pagerduty.com/incidents/TEST-001",
        "service": {
          "id": "PSVC001",
          "summary": "test-service"
        },
        "assignments": []
      }
    }
  }'
```

### Verify Webhook Signature

**Python:**

```python
import hmac
import hashlib

def verify_pagerduty_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify PagerDuty webhook signature."""
    expected = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    # PagerDuty format: "v1=<hex>"
    provided = signature.split("=")[1] if "=" in signature else signature
    
    return hmac.compare_digest(expected, provided)

# In your webhook handler:
from fastapi import Request, HTTPException

async def handle_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-PagerDuty-Signature")
    
    if not verify_pagerduty_signature(body, signature, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Process webhook...
```

---

## WebSocket Real-time Updates

### Connect to WebSocket

**JavaScript:**

```javascript
class IncidentWebSocket {
  constructor(accessToken) {
    this.ws = null;
    this.accessToken = accessToken;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
  }
  
  connect() {
    this.ws = new WebSocket(
      `wss://api.example.com/api/realtime/ws?token=${this.accessToken}`
    );
    
    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
    };
    
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleEvent(data);
    };
    
    this.ws.onclose = () => {
      console.log('WebSocket closed');
      this.tryReconnect();
    };
    
    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }
  
  handleEvent(event) {
    switch (event.event_type) {
      case 'incident.created':
        console.log('New incident:', event.payload);
        break;
      case 'incident.updated':
        console.log('Incident updated:', event.payload);
        break;
      case 'comment.added':
        console.log('New comment:', event.payload);
        break;
      default:
        console.log('Event:', event);
    }
  }
  
  subscribe(incidentId) {
    this.ws.send(JSON.stringify({
      type: 'subscribe',
      incident_id: incidentId
    }));
  }
  
  unsubscribe(incidentId) {
    this.ws.send(JSON.stringify({
      type: 'unsubscribe',
      incident_id: incidentId
    }));
  }
  
  sendTyping(incidentId, isTyping = true) {
    this.ws.send(JSON.stringify({
      type: 'typing',
      incident_id: incidentId,
      is_typing: isTyping
    }));
  }
  
  tryReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
      console.log(`Reconnecting in ${delay}ms...`);
      setTimeout(() => this.connect(), delay);
    }
  }
  
  disconnect() {
    if (this.ws) {
      this.ws.close();
    }
  }
}

// Usage
const ws = new IncidentWebSocket(accessToken);
ws.connect();
ws.subscribe('INC-12345');
```

**Python (websockets library):**

```python
import asyncio
import json
import websockets

async def listen_to_incidents(access_token, incident_ids):
    uri = f"wss://api.example.com/api/realtime/ws?token={access_token}"
    
    async with websockets.connect(uri) as websocket:
        # Subscribe to incidents
        for incident_id in incident_ids:
            await websocket.send(json.dumps({
                "type": "subscribe",
                "incident_id": incident_id
            }))
        
        # Listen for events
        async for message in websocket:
            event = json.loads(message)
            print(f"Event: {event['event_type']}")
            
            if event['event_type'] == 'incident.updated':
                print(f"Incident updated: {event['payload']}")

# Run
asyncio.run(listen_to_incidents(
    access_token,
    ["INC-12345", "INC-12346"]
))
```

---

## Alert Correlation

### Create Correlation Rule

**curl:**

```bash
curl -X POST https://api.example.com/correlation/rules \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Database Alerts",
    "description": "Correlate all database-related alerts",
    "strategy": "service",
    "enabled": true,
    "priority": 10,
    "time_window_seconds": 300,
    "services": ["postgres", "mysql", "redis"],
    "match_tags": ["database", "storage"],
    "suppress_duplicates": true,
    "max_alerts_before_notify": 1
  }'
```

**Python:**

```python
def create_correlation_rule(access_token, rule_config):
    response = requests.post(
        "https://api.example.com/correlation/rules",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json=rule_config
    )
    
    return response.json()

# Example
rule = create_correlation_rule(access_token, {
    "name": "Payment Service Alerts",
    "strategy": "service",
    "services": ["payments-api", "payment-processor"],
    "time_window_seconds": 300,
    "suppress_duplicates": True
})
print(f"Created rule: {rule['rule_id']}")
```

### Test Alert Correlation

**Python:**

```python
def test_alert_correlation(access_token, alert_data):
    response = requests.post(
        "https://api.example.com/correlation/test",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json=alert_data
    )
    
    result = response.json()
    
    if result["correlated"]:
        print(f"Alert would be correlated to group: {result['group_id']}")
        print(f"Rule matched: {result['rule_matched']}")
        print(f"Would notify: {result['should_notify']}")
    else:
        print("Alert would create a new group")
    
    return result

# Test
test_alert_correlation(access_token, {
    "alert_id": "test-001",
    "title": "Payment API High Error Rate",
    "service": "payments-api",
    "severity": "high",
    "tags": ["payment", "production"]
})
```

---

## Cost Tracking

### Calculate Incident Cost

**Python:**

```python
from datetime import datetime, timedelta

def calculate_incident_cost(access_token, incident_data):
    response = requests.post(
        "https://api.example.com/api/costs/calculate",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json=incident_data
    )
    
    return response.json()

# Example
incident_start = datetime.utcnow() - timedelta(hours=2)
incident_end = datetime.utcnow()

result = calculate_incident_cost(access_token, {
    "incident_id": "INC-12345",
    "service_name": "payments-api",
    "severity": "high",
    "incident_started_at": incident_start.isoformat() + "Z",
    "incident_resolved_at": incident_end.isoformat() + "Z",
    "responders": [
        {
            "id": "U001",
            "name": "Jane Doe",
            "team": "platform",
            "role": "sre",
            "time_minutes": 120
        },
        {
            "id": "U002",
            "name": "John Smith",
            "team": "engineering",
            "role": "engineer",
            "time_minutes": 60
        }
    ],
    "affected_users": 5000,
    "affected_transactions": 250
})

print(f"Total Cost: ${result['cost']['total_cost']}")
```

### Generate Cost Report

**Python:**

```python
def generate_cost_report(access_token, period="monthly", services=None):
    request_body = {
        "period": period,
        "include_roi": True,
        "compare_previous": True,
        "top_incidents_limit": 10
    }
    
    if services:
        request_body["services"] = services
    
    response = requests.post(
        "https://api.example.com/api/costs/reports/generate",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json=request_body
    )
    
    report = response.json()["report"]
    
    print(f"Period: {report['period_start']} to {report['period_end']}")
    print(f"Total Incidents: {report['total_incidents']}")
    print(f"Total Cost: ${report['total_cost']}")
    print(f"Average Cost: ${report['average_cost_per_incident']}")
    
    if report.get('cost_change_percent'):
        change = report['cost_change_percent']
        direction = "decreased" if change < 0 else "increased"
        print(f"Cost {direction} by {abs(change)}% vs previous period")
    
    return report
```

---

## Status Page Integration

### Create Status Incident

**Python:**

```python
def create_status_incident(access_token, incident_data):
    response = requests.post(
        "https://api.example.com/statuspage/incidents",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json=incident_data
    )
    
    return response.json()

# Example
incident = create_status_incident(access_token, {
    "name": "API Performance Degradation",
    "status": "investigating",
    "impact": "minor",
    "body": "We are investigating reports of slow API responses.",
    "component_ids": ["comp_api_gateway"],
    "deliver_notifications": True
})

print(f"Created status incident: {incident['id']}")
print(f"Public URL: {incident['shortlink']}")
```

### Update Status Incident

**Python:**

```python
def update_status_incident(access_token, incident_id, update_data):
    response = requests.patch(
        f"https://api.example.com/statuspage/incidents/{incident_id}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json=update_data
    )
    
    return response.json()

# Progress through status updates
update_status_incident(access_token, incident_id, {
    "status": "identified",
    "body": "We have identified the root cause as a database connection issue.",
    "component_statuses": {
        "comp_api_gateway": "degraded_performance"
    }
})

# Later, resolve the incident
update_status_incident(access_token, incident_id, {
    "status": "resolved",
    "body": "The issue has been resolved. All systems are operational."
})
```

---

## Error Handling

### Python Error Handler

```python
import requests
from requests.exceptions import RequestException

class IncidentCopilotError(Exception):
    def __init__(self, status_code, detail, code=None):
        self.status_code = status_code
        self.detail = detail
        self.code = code
        super().__init__(f"{status_code}: {detail}")

def api_request(method, url, access_token, **kwargs):
    """Make an API request with proper error handling."""
    try:
        response = requests.request(
            method,
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            **kwargs
        )
        
        # Handle rate limiting
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 30))
            raise IncidentCopilotError(
                429,
                f"Rate limited. Retry after {retry_after} seconds",
                "rate_limited"
            )
        
        # Handle errors
        if not response.ok:
            error_data = response.json()
            detail = error_data.get("detail", "Unknown error")
            code = error_data.get("code")
            raise IncidentCopilotError(response.status_code, detail, code)
        
        return response.json()
    
    except RequestException as e:
        raise IncidentCopilotError(0, f"Network error: {e}", "network_error")

# Usage with retry
import time

def api_request_with_retry(method, url, access_token, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            return api_request(method, url, access_token, **kwargs)
        except IncidentCopilotError as e:
            if e.code == "rate_limited" and attempt < max_retries - 1:
                retry_after = int(e.detail.split()[-2])
                time.sleep(retry_after)
            else:
                raise
```

### JavaScript Error Handler

```javascript
class IncidentCopilotError extends Error {
  constructor(statusCode, detail, code = null) {
    super(`${statusCode}: ${detail}`);
    this.statusCode = statusCode;
    this.detail = detail;
    this.code = code;
  }
}

async function apiRequest(method, url, accessToken, options = {}) {
  try {
    const response = await fetch(url, {
      method,
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
        ...options.headers
      },
      ...options
    });
    
    if (response.status === 429) {
      const retryAfter = parseInt(response.headers.get('Retry-After') || '30');
      throw new IncidentCopilotError(
        429,
        `Rate limited. Retry after ${retryAfter} seconds`,
        'rate_limited'
      );
    }
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new IncidentCopilotError(
        response.status,
        errorData.detail || 'Unknown error',
        errorData.code
      );
    }
    
    return response.json();
  } catch (error) {
    if (error instanceof IncidentCopilotError) throw error;
    throw new IncidentCopilotError(0, `Network error: ${error.message}`, 'network_error');
  }
}

// Usage with retry
async function apiRequestWithRetry(method, url, accessToken, options = {}, maxRetries = 3) {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await apiRequest(method, url, accessToken, options);
    } catch (error) {
      if (error.code === 'rate_limited' && attempt < maxRetries - 1) {
        const retryAfter = parseInt(error.detail.match(/\d+/)[0]);
        await new Promise(resolve => setTimeout(resolve, retryAfter * 1000));
      } else {
        throw error;
      }
    }
  }
}
```

---

*See also: [API Overview](README.md) | [Error Codes](errors.md)*
