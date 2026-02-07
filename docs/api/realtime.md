# WebSocket API

Real-time incident updates, live collaboration, and event streaming via WebSocket connections.

## Overview

The WebSocket API provides:
- Real-time incident status updates
- Live timeline events and comments
- Typing indicators and presence
- Dashboard metric streaming
- Alert notifications

## Connection

### WebSocket URL

```
wss://api.incident-copilot.io/ws/v1
```

### Authentication

Connect with JWT token as query parameter or in the first message.

#### Option 1: Query Parameter

```
wss://api.incident-copilot.io/ws/v1?token=<your_jwt_token>
```

#### Option 2: Initial Message

```json
{
  "type": "auth",
  "token": "<your_jwt_token>"
}
```

### Connection Example

```javascript
const ws = new WebSocket('wss://api.incident-copilot.io/ws/v1?token=' + token);

ws.onopen = () => {
  console.log('Connected to Incident Copilot');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Received:', message);
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = (event) => {
  console.log('Connection closed:', event.code, event.reason);
};
```

### Connection Response

```json
{
  "type": "connected",
  "connection_id": "conn_abc123",
  "user_id": "user_123",
  "server_time": "2024-01-26T10:00:00Z",
  "heartbeat_interval_ms": 30000
}
```

---

## Rate Limits

| Action | Limit |
|--------|-------|
| Connections per user | 5 concurrent |
| Messages per minute | 60 |
| Subscriptions per connection | 50 |

---

## Message Format

All messages follow this structure:

```json
{
  "type": "<message_type>",
  "payload": { ... },
  "timestamp": "2024-01-26T10:00:00Z",
  "id": "msg_unique_id"
}
```

---

## Subscriptions

### Subscribe to Incident

Subscribe to real-time updates for a specific incident.

#### Request

```json
{
  "type": "subscribe",
  "channel": "incident",
  "incident_id": "inc_12345"
}
```

#### Response

```json
{
  "type": "subscribed",
  "channel": "incident:inc_12345",
  "current_subscribers": 5
}
```

### Subscribe to All Incidents

Subscribe to updates for all incidents (new, status changes).

#### Request

```json
{
  "type": "subscribe",
  "channel": "incidents",
  "filters": {
    "priority": ["critical", "high"],
    "team": ["platform"]
  }
}
```

#### Response

```json
{
  "type": "subscribed",
  "channel": "incidents",
  "filters_applied": {
    "priority": ["critical", "high"],
    "team": ["platform"]
  }
}
```

### Subscribe to Dashboard Metrics

```json
{
  "type": "subscribe",
  "channel": "metrics",
  "dashboard_id": "dash_001"
}
```

### Subscribe to User Notifications

```json
{
  "type": "subscribe",
  "channel": "notifications"
}
```

### Unsubscribe

```json
{
  "type": "unsubscribe",
  "channel": "incident:inc_12345"
}
```

---

## Incoming Events

### Incident Created

```json
{
  "type": "incident.created",
  "payload": {
    "incident": {
      "id": "inc_12346",
      "title": "Database connection failures",
      "priority": "critical",
      "severity": 1,
      "status": "open",
      "team": "platform",
      "created_by": {
        "id": "user_456",
        "name": "John Doe"
      },
      "created_at": "2024-01-26T10:15:00Z"
    }
  },
  "timestamp": "2024-01-26T10:15:00Z"
}
```

### Incident Updated

```json
{
  "type": "incident.updated",
  "payload": {
    "incident_id": "inc_12345",
    "changes": {
      "status": {
        "from": "open",
        "to": "investigating"
      },
      "assigned_to": {
        "from": null,
        "to": {
          "id": "user_123",
          "name": "Jane Smith"
        }
      }
    },
    "updated_by": {
      "id": "user_789",
      "name": "Team Lead"
    }
  },
  "timestamp": "2024-01-26T10:20:00Z"
}
```

### Incident Resolved

```json
{
  "type": "incident.resolved",
  "payload": {
    "incident_id": "inc_12345",
    "resolution_summary": "Increased connection pool size and restarted affected services",
    "resolved_by": {
      "id": "user_123",
      "name": "Jane Smith"
    },
    "ttr_minutes": 45,
    "resolved_at": "2024-01-26T11:00:00Z"
  },
  "timestamp": "2024-01-26T11:00:00Z"
}
```

### Timeline Event

```json
{
  "type": "timeline.event",
  "payload": {
    "incident_id": "inc_12345",
    "event": {
      "id": "evt_001",
      "type": "status_change",
      "description": "Status changed to investigating",
      "user": {
        "id": "user_123",
        "name": "Jane Smith"
      },
      "metadata": {
        "from_status": "open",
        "to_status": "investigating"
      },
      "created_at": "2024-01-26T10:20:00Z"
    }
  },
  "timestamp": "2024-01-26T10:20:00Z"
}
```

### Comment Added

```json
{
  "type": "comment.added",
  "payload": {
    "incident_id": "inc_12345",
    "comment": {
      "id": "cmt_001",
      "content": "Identified the root cause - connection pool exhaustion",
      "author": {
        "id": "user_123",
        "name": "Jane Smith",
        "avatar": "https://..."
      },
      "created_at": "2024-01-26T10:25:00Z"
    }
  },
  "timestamp": "2024-01-26T10:25:00Z"
}
```

### SLA Warning

```json
{
  "type": "sla.warning",
  "payload": {
    "incident_id": "inc_12345",
    "sla_type": "resolution",
    "target_minutes": 240,
    "elapsed_minutes": 180,
    "remaining_minutes": 60,
    "threshold_percent": 75
  },
  "timestamp": "2024-01-26T13:00:00Z"
}
```

### SLA Breach

```json
{
  "type": "sla.breach",
  "payload": {
    "incident_id": "inc_12345",
    "sla_type": "resolution",
    "target_minutes": 240,
    "actual_minutes": 245,
    "exceeded_by_minutes": 5,
    "breached_at": "2024-01-26T14:05:00Z"
  },
  "timestamp": "2024-01-26T14:05:00Z"
}
```

### Escalation

```json
{
  "type": "escalation",
  "payload": {
    "incident_id": "inc_12345",
    "level": 2,
    "escalated_to": [
      {
        "id": "user_999",
        "name": "On-Call Manager",
        "role": "incident_commander"
      }
    ],
    "reason": "SLA breach - resolution target exceeded",
    "escalated_at": "2024-01-26T14:05:00Z"
  },
  "timestamp": "2024-01-26T14:05:00Z"
}
```

### Presence Update

```json
{
  "type": "presence.update",
  "payload": {
    "incident_id": "inc_12345",
    "users": [
      {
        "id": "user_123",
        "name": "Jane Smith",
        "status": "active",
        "last_seen": "2024-01-26T10:30:00Z"
      },
      {
        "id": "user_456",
        "name": "John Doe",
        "status": "viewing",
        "last_seen": "2024-01-26T10:29:45Z"
      }
    ]
  },
  "timestamp": "2024-01-26T10:30:00Z"
}
```

### Typing Indicator

```json
{
  "type": "typing",
  "payload": {
    "incident_id": "inc_12345",
    "user": {
      "id": "user_123",
      "name": "Jane Smith"
    },
    "is_typing": true
  },
  "timestamp": "2024-01-26T10:30:05Z"
}
```

### Metrics Update

```json
{
  "type": "metrics.update",
  "payload": {
    "dashboard_id": "dash_001",
    "metrics": {
      "active_incidents": 12,
      "critical_count": 2,
      "mttr_minutes": 45.3,
      "sla_compliance_percent": 94.5
    }
  },
  "timestamp": "2024-01-26T10:30:00Z"
}
```

### Notification

```json
{
  "type": "notification",
  "payload": {
    "id": "notif_001",
    "title": "You've been assigned to an incident",
    "message": "Database connection failures (INC-12345)",
    "incident_id": "inc_12345",
    "priority": "high",
    "action_url": "/incidents/inc_12345"
  },
  "timestamp": "2024-01-26T10:15:00Z"
}
```

---

## Outgoing Messages

### Send Typing Indicator

```json
{
  "type": "typing",
  "incident_id": "inc_12345",
  "is_typing": true
}
```

### Update Presence

```json
{
  "type": "presence",
  "incident_id": "inc_12345",
  "status": "active"
}
```

#### Presence Status Values

| Status | Description |
|--------|-------------|
| `active` | Actively working on incident |
| `viewing` | Viewing incident details |
| `idle` | Tab open but inactive |
| `away` | User away |

### Heartbeat

Send periodically to keep connection alive.

```json
{
  "type": "ping"
}
```

#### Response

```json
{
  "type": "pong",
  "timestamp": "2024-01-26T10:30:30Z"
}
```

### Acknowledge Notification

```json
{
  "type": "notification.ack",
  "notification_id": "notif_001"
}
```

---

## Error Messages

```json
{
  "type": "error",
  "error": {
    "code": "SUBSCRIPTION_FAILED",
    "message": "Failed to subscribe to incident",
    "details": {
      "incident_id": "inc_99999",
      "reason": "Incident not found"
    }
  },
  "timestamp": "2024-01-26T10:30:00Z"
}
```

### Error Codes

| Code | Description |
|------|-------------|
| `AUTH_FAILED` | Authentication failed or token expired |
| `AUTH_REQUIRED` | No authentication provided |
| `SUBSCRIPTION_FAILED` | Failed to subscribe to channel |
| `PERMISSION_DENIED` | No access to requested resource |
| `RATE_LIMITED` | Too many messages |
| `INVALID_MESSAGE` | Malformed message format |
| `CONNECTION_LIMIT` | Too many concurrent connections |

---

## Connection Management

### Reconnection

On disconnect, implement exponential backoff:

```javascript
let reconnectAttempts = 0;
const maxReconnectDelay = 30000;

function reconnect() {
  const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), maxReconnectDelay);
  reconnectAttempts++;
  
  setTimeout(() => {
    const ws = new WebSocket(wsUrl);
    ws.onopen = () => {
      reconnectAttempts = 0;
      // Resubscribe to channels
    };
  }, delay);
}

ws.onclose = (event) => {
  if (event.code !== 1000) { // Not a normal closure
    reconnect();
  }
};
```

### Close Codes

| Code | Meaning |
|------|---------|
| 1000 | Normal closure |
| 1001 | Going away (server shutdown) |
| 1008 | Policy violation (auth failed) |
| 1011 | Server error |
| 4000 | Token expired |
| 4001 | Rate limited |
| 4002 | Invalid subscription |

---

## Complete Example

```javascript
class IncidentWebSocket {
  constructor(token) {
    this.token = token;
    this.ws = null;
    this.subscriptions = new Set();
    this.connect();
  }

  connect() {
    this.ws = new WebSocket(
      `wss://api.incident-copilot.io/ws/v1?token=${this.token}`
    );

    this.ws.onopen = () => {
      console.log('Connected');
      this.startHeartbeat();
      this.resubscribe();
    };

    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      this.handleMessage(message);
    };

    this.ws.onclose = (event) => {
      console.log('Disconnected:', event.code);
      this.stopHeartbeat();
      if (event.code !== 1000) {
        this.reconnect();
      }
    };
  }

  handleMessage(message) {
    switch (message.type) {
      case 'incident.created':
        this.onIncidentCreated(message.payload);
        break;
      case 'incident.updated':
        this.onIncidentUpdated(message.payload);
        break;
      case 'comment.added':
        this.onCommentAdded(message.payload);
        break;
      case 'notification':
        this.onNotification(message.payload);
        break;
      case 'pong':
        // Heartbeat acknowledged
        break;
    }
  }

  subscribe(channel, options = {}) {
    const sub = { channel, ...options };
    this.subscriptions.add(JSON.stringify(sub));
    this.send({ type: 'subscribe', ...sub });
  }

  unsubscribe(channel) {
    this.send({ type: 'unsubscribe', channel });
  }

  send(message) {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  startHeartbeat() {
    this.heartbeatInterval = setInterval(() => {
      this.send({ type: 'ping' });
    }, 30000);
  }

  stopHeartbeat() {
    clearInterval(this.heartbeatInterval);
  }

  resubscribe() {
    this.subscriptions.forEach(sub => {
      this.send({ type: 'subscribe', ...JSON.parse(sub) });
    });
  }

  reconnect() {
    setTimeout(() => this.connect(), 5000);
  }
}

// Usage
const ws = new IncidentWebSocket(token);
ws.subscribe('incidents', { priority: ['critical', 'high'] });
ws.subscribe('incident', { incident_id: 'inc_12345' });
```
