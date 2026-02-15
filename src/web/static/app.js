/**
 * Incident Copilot Dashboard - Real-time UI
 */

// ── Auth gate: redirect to login if no valid token ──
(function authGate() {
    const token = localStorage.getItem('access_token');
    if (!token) {
        window.location.href = '/login';
        return;
    }
    // Check token expiry (JWT payload is base64url in part 1)
    try {
        const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/')));
        if (payload.exp && payload.exp * 1000 < Date.now()) {
            // Token expired — clear and redirect
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            localStorage.removeItem('user');
            window.location.href = '/login?error=session_expired';
            return;
        }
    } catch(e) {
        // Malformed token — clear and redirect
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        window.location.href = '/login';
        return;
    }
})();

// Connection status management
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');

function setConnectionStatus(connected) {
    if (connected) {
        statusDot.className = 'w-2 h-2 rounded-full bg-green-500 animate-pulse-dot';
        statusText.textContent = 'Connected';
        statusText.className = 'text-green-400';
    } else {
        statusDot.className = 'w-2 h-2 rounded-full bg-red-500';
        statusText.textContent = 'Disconnected';
        statusText.className = 'text-red-400';
    }
}

// Toast notifications
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    
    const colors = {
        info: 'bg-blue-500',
        success: 'bg-green-500',
        error: 'bg-red-500',
        warning: 'bg-yellow-500',
    };
    
    toast.className = `${colors[type]} text-white px-4 py-3 rounded-lg shadow-lg animate-slide-in flex items-center space-x-2`;
    toast.innerHTML = `
        <i class="fas ${type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle'}"></i>
        <span>${message}</span>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        toast.style.transition = 'all 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// SSE Connection
let eventSource = null;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;

function connectSSE() {
    if (eventSource) {
        eventSource.close();
    }
    
    eventSource = new EventSource('/dashboard/events');
    
    eventSource.onopen = () => {
        setConnectionStatus(true);
        reconnectAttempts = 0;
        console.log('SSE connected');
    };
    
    eventSource.onerror = (error) => {
        console.error('SSE error:', error);
        setConnectionStatus(false);
        eventSource.close();
        
        // Attempt reconnection with backoff
        if (reconnectAttempts < maxReconnectAttempts) {
            const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
            reconnectAttempts++;
            console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttempts})`);
            setTimeout(connectSSE, delay);
        }
    };
    
    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleSSEEvent(data);
        } catch (e) {
            console.error('Failed to parse SSE event:', e);
        }
    };
}

function handleSSEEvent(data) {
    console.log('SSE event:', data);
    
    switch (data.type) {
        case 'connected':
            // silently connected — no toast needed
            break;
            
        case 'new_incident':
            showToast(`New incident: ${data.title}`, 'warning');
            updateStats();
            addIncidentToList(data);
            break;
            
        case 'incident_completed':
            showToast(`Incident ${data.incident_id.slice(0, 8)}... processed (${data.assembly_time_ms}ms)`, 'success');
            updateStats();
            updateIncidentStatus(data.incident_id, 'completed');
            break;
            
        case 'incident_error':
            showToast(`Incident ${data.incident_id.slice(0, 8)}... failed`, 'error');
            updateStats();
            updateIncidentStatus(data.incident_id, 'error');
            break;
    }
}

// Update dashboard stats
async function updateStats() {
    try {
        const response = await fetch('/dashboard/api/stats');
        const stats = await response.json();
        
        document.getElementById('stat-total').textContent = stats.total;
        document.getElementById('stat-processing').textContent = stats.by_status.processing;
        document.getElementById('stat-completed').textContent = stats.by_status.completed;
        document.getElementById('stat-errors').textContent = stats.by_status.error;
    } catch (e) {
        console.error('Failed to update stats:', e);
    }
}

// Add new incident to list
function addIncidentToList(data) {
    const list = document.getElementById('incidents-list');
    if (!list) return;
    
    // Remove empty state if present
    const emptyState = list.querySelector('.text-center');
    if (emptyState) {
        emptyState.remove();
    }
    
    // Create new incident element
    const incident = document.createElement('a');
    incident.href = `/dashboard/incident/${data.incident_id}`;
    incident.className = 'block px-6 py-4 hover:bg-slate-700/50 transition-colors group animate-slide-in';
    incident.dataset.incidentId = data.incident_id;
    
    const severityColors = {
        critical: 'bg-red-600',
        high: 'bg-orange-500',
        medium: 'bg-yellow-500',
        low: 'bg-blue-500',
        info: 'bg-gray-500',
    };
    
    incident.innerHTML = `
        <div class="flex items-center justify-between">
            <div class="flex items-center space-x-4">
                <div class="flex-shrink-0">
                    <span class="w-3 h-3 rounded-full block ${severityColors[data.severity] || 'bg-gray-500'}"></span>
                </div>
                <div>
                    <div class="flex items-center space-x-3">
                        <h3 class="text-white font-medium group-hover:text-blue-400 transition-colors">
                            ${escapeHtml(data.title.slice(0, 60))}${data.title.length > 60 ? '...' : ''}
                        </h3>
                        <span class="px-2 py-0.5 text-xs rounded-full bg-yellow-500 text-white font-medium status-badge">
                            processing
                        </span>
                    </div>
                    <div class="flex items-center space-x-4 mt-1 text-sm text-gray-400">
                        <span class="flex items-center">
                            <i class="fas fa-server mr-1.5"></i>
                            ${escapeHtml(data.service)}
                        </span>
                        <span class="flex items-center">
                            <i class="fas fa-clock mr-1.5"></i>
                            Just now
                        </span>
                        <span class="flex items-center capitalize">
                            <i class="fas fa-flag mr-1.5"></i>
                            ${data.severity}
                        </span>
                    </div>
                </div>
            </div>
            <div class="text-gray-500 group-hover:text-blue-400 transition-colors">
                <i class="fas fa-chevron-right"></i>
            </div>
        </div>
    `;
    
    // Insert at the top
    list.insertBefore(incident, list.firstChild);
}

// Update incident status in list
function updateIncidentStatus(incidentId, status) {
    const incident = document.querySelector(`[data-incident-id="${incidentId}"]`);
    if (!incident) return;
    
    const badge = incident.querySelector('.status-badge');
    if (badge) {
        badge.textContent = status;
        badge.className = `px-2 py-0.5 text-xs rounded-full text-white font-medium status-badge ${
            status === 'completed' ? 'bg-green-500' : 'bg-red-500'
        }`;
    }
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Demo incident creation
async function createDemoIncident() {
    try {
        const response = await fetch('/dashboard/api/demo', { method: 'POST' });
        const data = await response.json();
        showToast('Demo incident created!', 'success');
    } catch (e) {
        showToast('Failed to create demo incident', 'error');
        console.error('Demo creation failed:', e);
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    connectSSE();
    
    // Periodic stats refresh as backup
    setInterval(updateStats, 30000);
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (eventSource) {
        eventSource.close();
    }
});
