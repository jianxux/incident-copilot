/**
 * Real-time WebSocket Client for Incident Copilot Dashboard
 * Provides WebSocket connection management with automatic reconnection,
 * event handling, and integration with dashboard components.
 */

class RealtimeClient {
    constructor(options = {}) {
        this.options = {
            // WebSocket URL - auto-detect protocol
            wsUrl: options.wsUrl || this.getWebSocketUrl(),
            // SSE fallback URL
            sseUrl: options.sseUrl || '/dashboard/events',
            // Reconnection settings
            maxReconnectAttempts: options.maxReconnectAttempts || 10,
            reconnectBaseDelay: options.reconnectBaseDelay || 1000,
            reconnectMaxDelay: options.reconnectMaxDelay || 30000,
            // Heartbeat settings
            heartbeatInterval: options.heartbeatInterval || 30000,
            heartbeatTimeout: options.heartbeatTimeout || 10000,
            // Use SSE instead of WebSocket
            useSSE: options.useSSE || false,
            // Debug mode
            debug: options.debug || false
        };
        
        this.ws = null;
        this.sse = null;
        this.reconnectAttempts = 0;
        this.reconnectTimer = null;
        this.heartbeatTimer = null;
        this.heartbeatTimeoutTimer = null;
        this.isConnected = false;
        this.isConnecting = false;
        this.manualClose = false;
        
        // Event handlers map
        this.handlers = new Map();
        
        // Connection status element IDs
        this.statusDotId = 'status-dot';
        this.statusTextId = 'status-text';
        
        // Pending messages queue (for when disconnected)
        this.pendingMessages = [];
        
        // Subscribe to default events
        this.setupDefaultHandlers();
    }
    
    /**
     * Get WebSocket URL based on current location
     */
    getWebSocketUrl() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}/ws`;
    }
    
    /**
     * Connect to the real-time server
     */
    connect() {
        if (this.isConnected || this.isConnecting) {
            this.log('Already connected or connecting');
            return;
        }
        
        this.manualClose = false;
        
        if (this.options.useSSE) {
            this.connectSSE();
        } else {
            this.connectWebSocket();
        }
    }
    
    /**
     * Connect via WebSocket
     */
    connectWebSocket() {
        this.isConnecting = true;
        this.updateStatus('connecting', 'Connecting...');
        
        try {
            this.ws = new WebSocket(this.options.wsUrl);
            
            this.ws.onopen = () => this.handleOpen();
            this.ws.onclose = (event) => this.handleClose(event);
            this.ws.onerror = (error) => this.handleError(error);
            this.ws.onmessage = (event) => this.handleMessage(event);
            
        } catch (error) {
            this.log('WebSocket creation failed, falling back to SSE', error);
            this.options.useSSE = true;
            this.connectSSE();
        }
    }
    
    /**
     * Connect via Server-Sent Events (fallback)
     */
    connectSSE() {
        this.isConnecting = true;
        this.updateStatus('connecting', 'Connecting...');
        
        try {
            this.sse = new EventSource(this.options.sseUrl);
            
            this.sse.onopen = () => this.handleOpen();
            this.sse.onerror = (error) => this.handleSSEError(error);
            this.sse.onmessage = (event) => this.handleMessage(event);
            
            // Handle named events
            ['incident_new', 'incident_update', 'incident_resolved', 'metrics_update', 
             'responder_update', 'timeline_event', 'service_status'].forEach(eventType => {
                this.sse.addEventListener(eventType, (event) => {
                    this.handleMessage({ data: event.data, type: eventType });
                });
            });
            
        } catch (error) {
            this.handleError(error);
        }
    }
    
    /**
     * Handle successful connection
     */
    handleOpen() {
        this.isConnected = true;
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        this.updateStatus('connected', 'Connected');
        
        this.log('Connected to real-time server');
        this.emit('connected', { timestamp: Date.now() });
        
        // Start heartbeat
        this.startHeartbeat();
        
        // Send any pending messages
        this.flushPendingMessages();
        
        // Show toast notification
        if (window.showToast) {
            window.showToast('Real-time updates active', 'success');
        }
    }
    
    /**
     * Handle WebSocket close
     */
    handleClose(event) {
        this.isConnected = false;
        this.isConnecting = false;
        this.stopHeartbeat();
        
        this.log('Connection closed', event.code, event.reason);
        this.updateStatus('disconnected', 'Disconnected');
        this.emit('disconnected', { code: event.code, reason: event.reason });
        
        // Attempt reconnection if not manually closed
        if (!this.manualClose) {
            this.scheduleReconnect();
        }
    }
    
    /**
     * Handle SSE error (always fires on connection close)
     */
    handleSSEError(error) {
        if (this.sse.readyState === EventSource.CLOSED) {
            this.handleClose({ code: 0, reason: 'SSE connection closed' });
        } else if (this.sse.readyState === EventSource.CONNECTING) {
            this.updateStatus('reconnecting', 'Reconnecting...');
        }
    }
    
    /**
     * Handle connection error
     */
    handleError(error) {
        this.log('Connection error', error);
        this.emit('error', { error });
        this.updateStatus('error', 'Connection error');
    }
    
    /**
     * Handle incoming message
     */
    handleMessage(event) {
        try {
            const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
            const eventType = data.type || event.type || 'message';
            
            this.log('Received message', eventType, data);
            
            // Reset heartbeat on any message
            this.resetHeartbeat();
            
            // Emit to registered handlers
            this.emit(eventType, data);
            this.emit('message', { type: eventType, data });
            
        } catch (error) {
            this.log('Failed to parse message', error);
        }
    }
    
    /**
     * Schedule a reconnection attempt
     */
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.options.maxReconnectAttempts) {
            this.log('Max reconnection attempts reached');
            this.updateStatus('failed', 'Connection failed');
            this.emit('reconnect_failed', { attempts: this.reconnectAttempts });
            return;
        }
        
        // Exponential backoff with jitter
        const delay = Math.min(
            this.options.reconnectBaseDelay * Math.pow(2, this.reconnectAttempts) + 
            Math.random() * 1000,
            this.options.reconnectMaxDelay
        );
        
        this.reconnectAttempts++;
        this.updateStatus('reconnecting', `Reconnecting in ${Math.round(delay / 1000)}s...`);
        this.log(`Scheduling reconnect attempt ${this.reconnectAttempts} in ${delay}ms`);
        
        this.reconnectTimer = setTimeout(() => {
            this.connect();
        }, delay);
    }
    
    /**
     * Start heartbeat ping
     */
    startHeartbeat() {
        if (!this.ws) return; // SSE doesn't need heartbeat
        
        this.heartbeatTimer = setInterval(() => {
            if (this.isConnected && this.ws.readyState === WebSocket.OPEN) {
                this.send({ type: 'ping', timestamp: Date.now() });
                
                // Set timeout for pong response
                this.heartbeatTimeoutTimer = setTimeout(() => {
                    this.log('Heartbeat timeout, reconnecting...');
                    this.ws.close();
                }, this.options.heartbeatTimeout);
            }
        }, this.options.heartbeatInterval);
    }
    
    /**
     * Stop heartbeat
     */
    stopHeartbeat() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
        if (this.heartbeatTimeoutTimer) {
            clearTimeout(this.heartbeatTimeoutTimer);
            this.heartbeatTimeoutTimer = null;
        }
    }
    
    /**
     * Reset heartbeat timeout (called on message receive)
     */
    resetHeartbeat() {
        if (this.heartbeatTimeoutTimer) {
            clearTimeout(this.heartbeatTimeoutTimer);
            this.heartbeatTimeoutTimer = null;
        }
    }
    
    /**
     * Send a message to the server
     */
    send(data) {
        const message = typeof data === 'string' ? data : JSON.stringify(data);
        
        if (this.isConnected && this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(message);
            this.log('Sent message', data);
        } else {
            // Queue message for later
            this.pendingMessages.push(message);
            this.log('Message queued (not connected)', data);
        }
    }
    
    /**
     * Flush pending messages after reconnection
     */
    flushPendingMessages() {
        while (this.pendingMessages.length > 0) {
            const message = this.pendingMessages.shift();
            this.ws.send(message);
        }
    }
    
    /**
     * Subscribe to an event
     */
    on(eventType, handler) {
        if (!this.handlers.has(eventType)) {
            this.handlers.set(eventType, []);
        }
        this.handlers.get(eventType).push(handler);
        return this; // Allow chaining
    }
    
    /**
     * Unsubscribe from an event
     */
    off(eventType, handler) {
        if (!this.handlers.has(eventType)) return;
        
        const handlers = this.handlers.get(eventType);
        const index = handlers.indexOf(handler);
        if (index > -1) {
            handlers.splice(index, 1);
        }
        return this;
    }
    
    /**
     * Emit an event to handlers
     */
    emit(eventType, data) {
        if (this.handlers.has(eventType)) {
            this.handlers.get(eventType).forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    this.log('Handler error', eventType, error);
                }
            });
        }
    }
    
    /**
     * Update connection status UI
     */
    updateStatus(status, text) {
        const statusDot = document.getElementById(this.statusDotId);
        const statusText = document.getElementById(this.statusTextId);
        
        if (statusDot) {
            const colors = {
                connected: 'bg-green-500 animate-pulse-dot',
                connecting: 'bg-yellow-500 animate-pulse',
                reconnecting: 'bg-yellow-500 animate-pulse',
                disconnected: 'bg-red-500',
                error: 'bg-red-500',
                failed: 'bg-gray-500'
            };
            statusDot.className = `w-2 h-2 rounded-full ${colors[status] || 'bg-gray-500'}`;
        }
        
        if (statusText) {
            statusText.textContent = text;
            statusText.className = `text-${status === 'connected' ? 'green' : status === 'error' || status === 'failed' ? 'red' : 'gray'}-400`;
        }
    }
    
    /**
     * Setup default event handlers for dashboard components
     */
    setupDefaultHandlers() {
        // Handle incoming incidents
        this.on('new_incident', (data) => {
            if (window.showToast) {
                window.showToast(`New incident: ${data.title}`, 'warning');
            }
            // Update incident list if available
            if (typeof addIncidentToList === 'function') {
                addIncidentToList(data);
            }
        });
        
        // Handle incident completion
        this.on('incident_completed', (data) => {
            if (window.showToast) {
                window.showToast(`Incident resolved (${data.assembly_time_ms}ms)`, 'success');
            }
            if (typeof updateIncidentStatus === 'function') {
                updateIncidentStatus(data.incident_id, 'completed');
            }
        });
        
        // Handle incident errors
        this.on('incident_error', (data) => {
            if (window.showToast) {
                window.showToast(`Incident processing failed`, 'error');
            }
            if (typeof updateIncidentStatus === 'function') {
                updateIncidentStatus(data.incident_id, 'error');
            }
        });
        
        // Handle metrics updates
        this.on('metrics_update', (data) => {
            if (window.metricsCards) {
                window.metricsCards.updateAll(data.metrics);
            }
        });
        
        // Handle timeline events
        this.on('timeline_event', (data) => {
            if (window.timelineVisual) {
                window.timelineVisual.addEvent(data.event);
            }
        });
        
        // Handle responder updates
        this.on('responder_update', (data) => {
            if (window.responderCards) {
                if (data.action === 'add') {
                    window.responderCards.addResponder(data.responder);
                } else if (data.action === 'remove') {
                    window.responderCards.removeResponder(data.responder_id);
                } else if (data.action === 'update') {
                    window.responderCards.updateResponder(data.responder_id, data.updates);
                }
            }
        });
        
        // Handle service status updates
        this.on('service_status', (data) => {
            if (window.serviceMap) {
                window.serviceMap.updateServiceStatus(data.service_id, data.status);
            }
        });
        
        // Handle pong response
        this.on('pong', () => {
            this.resetHeartbeat();
        });
    }
    
    /**
     * Disconnect from the server
     */
    disconnect() {
        this.manualClose = true;
        this.stopHeartbeat();
        
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        
        if (this.sse) {
            this.sse.close();
            this.sse = null;
        }
        
        this.isConnected = false;
        this.updateStatus('disconnected', 'Disconnected');
    }
    
    /**
     * Subscribe to a specific incident's updates
     */
    subscribeToIncident(incidentId) {
        this.send({
            type: 'subscribe',
            channel: 'incident',
            incident_id: incidentId
        });
    }
    
    /**
     * Unsubscribe from a specific incident's updates
     */
    unsubscribeFromIncident(incidentId) {
        this.send({
            type: 'unsubscribe',
            channel: 'incident',
            incident_id: incidentId
        });
    }
    
    /**
     * Log debug messages
     */
    log(...args) {
        if (this.options.debug) {
            console.log('[RealtimeClient]', ...args);
        }
    }
}

// Create global instance
const realtimeClient = new RealtimeClient({
    useSSE: true,  // Default to SSE for broader compatibility
    debug: false
});

// Auto-connect on page load
document.addEventListener('DOMContentLoaded', () => {
    realtimeClient.connect();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    realtimeClient.disconnect();
});

// Expose globally
window.realtimeClient = realtimeClient;
window.RealtimeClient = RealtimeClient;
