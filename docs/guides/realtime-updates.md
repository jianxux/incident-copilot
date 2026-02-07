# Real-Time Updates Guide

This guide explains how to implement real-time updates in your Incident Copilot integration using WebSockets, Server-Sent Events (SSE), and push notifications.

## Overview

Real-time updates enable:
- **Live incident feeds** - See new incidents instantly
- **Collaborative response** - Real-time comments and status changes
- **Dashboard updates** - Metrics refresh without polling
- **Instant notifications** - Push alerts to mobile and desktop

---

## Connection Methods

| Method | Use Case | Browser Support | Server Load |
|--------|----------|-----------------|-------------|
| **WebSocket** | Full duplex, high frequency | All modern | Medium |
| **SSE** | Server → Client only | All modern | Low |
| **Long Polling** | Legacy fallback | All | High |
| **Push Notifications** | Mobile/Desktop alerts | Native apps | Low |

---

## Step 1: WebSocket Connection

### Connecting to WebSocket

```javascript
// JavaScript client
const ws = new WebSocket('wss://realtime.incident-copilot.com/v1/stream');

// Authentication
ws.onopen = () => {
  ws.send(JSON.stringify({
    type: 'auth',
    token: 'your_api_token'
  }));
};

// Handle messages
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  handleRealtimeEvent(message);
};

// Reconnection logic
ws.onclose = (event) => {
  if (event.code !== 1000) {
    // Unexpected close, reconnect with backoff
    setTimeout(() => connect(), getBackoffDelay());
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};
```

### Subscribe to Channels

```javascript
// Subscribe to specific channels
ws.send(JSON.stringify({
  type: 'subscribe',
  channels: [
    'incidents:*',           // All incident events
    'incidents:INC-12345',   // Specific incident
    'team:platform',         // Team events
    'oncall:primary'         // On-call changes
  ]
}));

// Unsubscribe
ws.send(JSON.stringify({
  type: 'unsubscribe',
  channels: ['incidents:INC-12345']
}));
```

### Event Types

```javascript
function handleRealtimeEvent(message) {
  switch (message.type) {
    case 'incident.created':
      addIncidentToList(message.data);
      break;
      
    case 'incident.updated':
      updateIncidentInList(message.data);
      break;
      
    case 'incident.status_changed':
      updateIncidentStatus(message.data.incident_id, message.data.new_status);
      break;
      
    case 'incident.comment_added':
      appendComment(message.data.incident_id, message.data.comment);
      break;
      
    case 'incident.assigned':
      updateAssignee(message.data.incident_id, message.data.assignee);
      break;
      
    case 'sla.warning':
      showSLAWarning(message.data);
      break;
      
    case 'sla.breach':
      showSLABreach(message.data);
      break;
      
    case 'metrics.updated':
      refreshDashboardMetrics(message.data);
      break;
      
    default:
      console.log('Unknown event type:', message.type);
  }
}
```

<!-- Diagram: WebSocket Event Flow -->
<!-- Shows client connection, auth, subscription, and event handling -->

---

## Step 2: Server-Sent Events (SSE)

### SSE Connection

For simpler server-to-client streaming:

```javascript
// JavaScript client
const eventSource = new EventSource(
  'https://api.incident-copilot.com/v1/events/stream?token=your_api_token'
);

// Connection opened
eventSource.onopen = () => {
  console.log('SSE connection established');
};

// Handle events by type
eventSource.addEventListener('incident.created', (event) => {
  const data = JSON.parse(event.data);
  addIncidentToList(data);
});

eventSource.addEventListener('incident.updated', (event) => {
  const data = JSON.parse(event.data);
  updateIncidentInList(data);
});

// Generic message handler
eventSource.onmessage = (event) => {
  console.log('Received event:', event.data);
};

// Error handling
eventSource.onerror = (error) => {
  console.error('SSE error:', error);
  // EventSource automatically reconnects
};
```

### Filtering SSE Events

```javascript
// Subscribe to filtered stream
const params = new URLSearchParams({
  token: 'your_api_token',
  severity: 'critical,high',
  team: 'platform',
  events: 'incident.created,incident.status_changed'
});

const eventSource = new EventSource(
  `https://api.incident-copilot.com/v1/events/stream?${params}`
);
```

---

## Step 3: Push Notifications

### Web Push (Browser)

#### Register Service Worker

```javascript
// Register service worker
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').then((registration) => {
    console.log('Service Worker registered');
    subscribeToPush(registration);
  });
}

async function subscribeToPush(registration) {
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY)
  });
  
  // Send subscription to backend
  await fetch('/api/push/subscribe', {
    method: 'POST',
    body: JSON.stringify(subscription),
    headers: { 'Content-Type': 'application/json' }
  });
}
```

#### Service Worker Handler

```javascript
// sw.js
self.addEventListener('push', (event) => {
  const data = event.data.json();
  
  const options = {
    body: data.body,
    icon: '/icons/incident-copilot-192.png',
    badge: '/icons/badge-72.png',
    tag: data.incident_id,  // Replace existing notification
    data: {
      url: data.url,
      incident_id: data.incident_id
    },
    actions: [
      { action: 'acknowledge', title: 'Acknowledge' },
      { action: 'view', title: 'View' }
    ],
    requireInteraction: data.severity === 'critical'
  };
  
  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// Handle notification actions
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  
  if (event.action === 'acknowledge') {
    // Acknowledge in background
    fetch(`/api/incidents/${event.notification.data.incident_id}/acknowledge`, {
      method: 'POST'
    });
  }
  
  // Open incident page
  event.waitUntil(
    clients.openWindow(event.notification.data.url)
  );
});
```

### Mobile Push

Configure push for mobile apps (see [Mobile App Guide](./mobile-app.md)):

```yaml
# config/push/mobile.yaml
push:
  ios:
    enabled: true
    apns_key_id: "${APNS_KEY_ID}"
    apns_team_id: "${APNS_TEAM_ID}"
    apns_bundle_id: "com.company.incidentcopilot"
    
  android:
    enabled: true
    fcm_server_key: "${FCM_SERVER_KEY}"
    
  priorities:
    critical: high
    high: high
    medium: normal
    low: low
```

---

## Step 4: React Integration

### useRealtime Hook

```jsx
// hooks/useRealtime.js
import { useEffect, useState, useCallback, useRef } from 'react';

export function useRealtime(channels, onMessage) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  
  const connect = useCallback(() => {
    const ws = new WebSocket('wss://realtime.incident-copilot.com/v1/stream');
    wsRef.current = ws;
    
    ws.onopen = () => {
      setConnected(true);
      ws.send(JSON.stringify({
        type: 'auth',
        token: getAuthToken()
      }));
      ws.send(JSON.stringify({
        type: 'subscribe',
        channels
      }));
    };
    
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      onMessage(message);
    };
    
    ws.onclose = () => {
      setConnected(false);
      // Reconnect after 3 seconds
      setTimeout(connect, 3000);
    };
    
    return ws;
  }, [channels, onMessage]);
  
  useEffect(() => {
    const ws = connect();
    return () => ws.close();
  }, [connect]);
  
  return { connected };
}
```

### Incident List Component

```jsx
// components/IncidentList.jsx
import { useState, useCallback } from 'react';
import { useRealtime } from '../hooks/useRealtime';

export function IncidentList() {
  const [incidents, setIncidents] = useState([]);
  
  const handleRealtimeMessage = useCallback((message) => {
    switch (message.type) {
      case 'incident.created':
        setIncidents(prev => [message.data, ...prev]);
        break;
        
      case 'incident.updated':
        setIncidents(prev => prev.map(inc => 
          inc.id === message.data.id ? message.data : inc
        ));
        break;
        
      case 'incident.deleted':
        setIncidents(prev => prev.filter(inc => 
          inc.id !== message.data.id
        ));
        break;
    }
  }, []);
  
  const { connected } = useRealtime(['incidents:*'], handleRealtimeMessage);
  
  return (
    <div>
      <ConnectionStatus connected={connected} />
      <ul>
        {incidents.map(incident => (
          <IncidentRow key={incident.id} incident={incident} />
        ))}
      </ul>
    </div>
  );
}
```

---

## Step 5: Connection Management

### Heartbeat / Keep-Alive

```javascript
class RealtimeConnection {
  constructor(url, token) {
    this.url = url;
    this.token = token;
    this.heartbeatInterval = null;
    this.reconnectAttempts = 0;
  }
  
  connect() {
    this.ws = new WebSocket(this.url);
    
    this.ws.onopen = () => {
      this.authenticate();
      this.startHeartbeat();
      this.reconnectAttempts = 0;
    };
    
    this.ws.onclose = () => {
      this.stopHeartbeat();
      this.scheduleReconnect();
    };
  }
  
  startHeartbeat() {
    this.heartbeatInterval = setInterval(() => {
      if (this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30000); // Every 30 seconds
  }
  
  stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }
  
  scheduleReconnect() {
    const delay = Math.min(
      1000 * Math.pow(2, this.reconnectAttempts),
      30000 // Max 30 seconds
    );
    this.reconnectAttempts++;
    
    setTimeout(() => this.connect(), delay);
  }
}
```

### Connection State Management

```javascript
// Connection states
const ConnectionState = {
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  AUTHENTICATED: 'authenticated',
  RECONNECTING: 'reconnecting',
  DISCONNECTED: 'disconnected',
  ERROR: 'error'
};

class RealtimeClient {
  constructor() {
    this.state = ConnectionState.DISCONNECTED;
    this.listeners = new Set();
  }
  
  setState(newState) {
    const oldState = this.state;
    this.state = newState;
    this.listeners.forEach(listener => 
      listener(newState, oldState)
    );
  }
  
  onStateChange(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}
```

---

## Step 6: Optimistic Updates

### Implement Optimistic UI

```javascript
async function acknowledgeIncident(incidentId) {
  // Optimistic update - immediately show acknowledged
  updateLocalIncident(incidentId, {
    status: 'acknowledged',
    acknowledged_at: new Date().toISOString(),
    acknowledged_by: currentUser
  });
  
  try {
    // Send to server
    await api.post(`/incidents/${incidentId}/acknowledge`);
    // Server will broadcast update via WebSocket
    
  } catch (error) {
    // Revert optimistic update on failure
    revertLocalIncident(incidentId);
    showError('Failed to acknowledge incident');
  }
}
```

### Conflict Resolution

```javascript
function handleServerUpdate(serverData) {
  const localData = getLocalIncident(serverData.id);
  
  if (!localData) {
    // New incident, just add it
    addLocalIncident(serverData);
    return;
  }
  
  // Check for conflicts
  if (serverData.updated_at > localData.updated_at) {
    // Server is newer, accept server version
    updateLocalIncident(serverData.id, serverData);
  } else if (localData.pending_changes) {
    // We have pending changes, merge
    const merged = mergeChanges(localData, serverData);
    updateLocalIncident(serverData.id, merged);
  }
}
```

---

## Step 7: Dashboard Real-Time Updates

### Metric Streaming

```javascript
// Subscribe to metric updates
ws.send(JSON.stringify({
  type: 'subscribe',
  channels: ['metrics:dashboard']
}));

// Handle metric updates
function handleMetricUpdate(data) {
  switch (data.metric) {
    case 'active_incidents':
      updateGauge('activeIncidents', data.value);
      break;
      
    case 'mttr':
      updateChart('mttrTrend', data.timestamp, data.value);
      break;
      
    case 'sla_compliance':
      updateGauge('slaCompliance', data.value);
      animateIfChanged(data.previous_value, data.value);
      break;
  }
}
```

### Throttling Updates

```javascript
// Throttle frequent updates
class ThrottledUpdater {
  constructor(callback, delay = 1000) {
    this.callback = callback;
    this.delay = delay;
    this.pending = null;
    this.timeout = null;
  }
  
  update(data) {
    this.pending = data;
    
    if (!this.timeout) {
      this.timeout = setTimeout(() => {
        this.callback(this.pending);
        this.pending = null;
        this.timeout = null;
      }, this.delay);
    }
  }
}

const chartUpdater = new ThrottledUpdater((data) => {
  chart.update(data);
}, 500);
```

---

## Best Practices

1. **Implement reconnection** - Always handle disconnects gracefully
2. **Use exponential backoff** - Don't hammer the server on reconnect
3. **Subscribe selectively** - Only subscribe to needed channels
4. **Handle duplicates** - Use message IDs to prevent duplicate processing
5. **Optimize payload size** - Request only needed fields
6. **Use compression** - Enable WebSocket compression for large payloads

---

## Common Pitfalls

| Issue | Cause | Solution |
|-------|-------|----------|
| Connection drops | No heartbeat | Implement ping/pong |
| Missed events | Reconnecting | Use sequence IDs, request missed events |
| High memory usage | Unbounded event queue | Implement queue limits |
| Stale data | No reconciliation | Fetch full state on reconnect |
| Battery drain | Constant connection | Use push for mobile |

---

## Debugging

### Enable Debug Logging

```javascript
const debug = localStorage.getItem('realtime_debug') === 'true';

ws.onmessage = (event) => {
  if (debug) {
    console.log('[WS Received]', event.data);
  }
  // ... handle message
};
```

### Monitor Connection Health

```javascript
class ConnectionMonitor {
  constructor(ws) {
    this.ws = ws;
    this.messageCount = 0;
    this.lastMessageAt = null;
    
    ws.onmessage = () => {
      this.messageCount++;
      this.lastMessageAt = Date.now();
    };
  }
  
  getStats() {
    return {
      state: this.ws.readyState,
      messageCount: this.messageCount,
      lastMessageAt: this.lastMessageAt,
      connectionAge: Date.now() - this.connectedAt
    };
  }
}
```

---

## Next Steps

- [Webhook Integration](./webhook-integration.md) - Server-side event handling
- [Custom Dashboards](./custom-dashboards.md) - Build real-time dashboards
- [Mobile App](./mobile-app.md) - Mobile push notification setup
