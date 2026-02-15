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

// ── Keyboard shortcuts ──
function initKeyboardShortcuts() {
    // Inject modal markup + styles
    const style = document.createElement('style');
    style.textContent = `
        .ic-kbd-overlay {
            position: fixed;
            inset: 0;
            background: rgba(28, 25, 23, 0.55);
            backdrop-filter: blur(6px);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            padding: 1.5rem;
        }
        .ic-kbd-overlay.show { display: flex; }
        .ic-kbd-modal {
            width: min(560px, 100%);
            background: #fffdf9;
            border: 1px solid rgba(28, 25, 23, 0.12);
            border-radius: 18px;
            box-shadow: 0 30px 80px rgba(28, 25, 23, 0.25);
            overflow: hidden;
            font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
        }
        .ic-kbd-header {
            padding: 1rem 1.25rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: linear-gradient(180deg, rgba(224, 90, 58, 0.10), rgba(224, 90, 58, 0));
        }
        .ic-kbd-title { font-weight: 700; color: #1c1917; }
        .ic-kbd-close {
            border: 0;
            background: transparent;
            color: rgba(28, 25, 23, 0.65);
            font-size: 0.95rem;
            cursor: pointer;
            padding: 0.35rem 0.5rem;
            border-radius: 10px;
        }
        .ic-kbd-close:hover { background: rgba(224, 90, 58, 0.10); color: #9a3412; }
        .ic-kbd-body { padding: 1rem 1.25rem 1.25rem; }
        .ic-kbd-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.75rem 0;
            border-top: 1px solid rgba(28, 25, 23, 0.06);
        }
        .ic-kbd-row:first-child { border-top: 0; }
        .ic-kbd-label { color: rgba(28, 25, 23, 0.75); font-weight: 600; }
        .ic-kbd-keys { display: flex; gap: 0.4rem; }
        .ic-kbd-key {
            background: rgba(224, 90, 58, 0.10);
            color: #9a3412;
            border: 1px solid rgba(224, 90, 58, 0.25);
            border-bottom-width: 2px;
            padding: 0.15rem 0.45rem;
            border-radius: 8px;
            font-weight: 700;
            font-size: 0.8rem;
        }
        .ic-kbd-footer {
            padding: 0.75rem 1.25rem;
            border-top: 1px solid rgba(28, 25, 23, 0.06);
            color: rgba(28, 25, 23, 0.55);
            font-size: 0.85rem;
        }
    `;
    document.head.appendChild(style);

    const overlay = document.createElement('div');
    overlay.className = 'ic-kbd-overlay';
    overlay.id = 'ic-kbd-overlay';
    overlay.innerHTML = `
        <div class="ic-kbd-modal" role="dialog" aria-modal="true" aria-labelledby="ic-kbd-title">
            <div class="ic-kbd-header">
                <div class="ic-kbd-title" id="ic-kbd-title">Keyboard shortcuts</div>
                <button class="ic-kbd-close" type="button" aria-label="Close shortcuts" title="Close (Esc)">Esc</button>
            </div>
            <div class="ic-kbd-body">
                <div class="ic-kbd-row">
                    <div class="ic-kbd-label">Go to dashboard</div>
                    <div class="ic-kbd-keys"><span class="ic-kbd-key">g</span><span class="ic-kbd-key">d</span></div>
                </div>
                <div class="ic-kbd-row">
                    <div class="ic-kbd-label">Go to analytics</div>
                    <div class="ic-kbd-keys"><span class="ic-kbd-key">g</span><span class="ic-kbd-key">a</span></div>
                </div>
                <div class="ic-kbd-row">
                    <div class="ic-kbd-label">Go to insights</div>
                    <div class="ic-kbd-keys"><span class="ic-kbd-key">g</span><span class="ic-kbd-key">i</span></div>
                </div>
                <div class="ic-kbd-row">
                    <div class="ic-kbd-label">Go to setup</div>
                    <div class="ic-kbd-keys"><span class="ic-kbd-key">g</span><span class="ic-kbd-key">s</span></div>
                </div>
                <div class="ic-kbd-row">
                    <div class="ic-kbd-label">Show this dialog</div>
                    <div class="ic-kbd-keys"><span class="ic-kbd-key">?</span></div>
                </div>
            </div>
            <div class="ic-kbd-footer">Tip: shortcuts are disabled while typing in inputs.</div>
        </div>
    `;
    document.body.appendChild(overlay);

    const closeBtn = overlay.querySelector('.ic-kbd-close');
    const modal = overlay.querySelector('.ic-kbd-modal');

    function isTypingTarget(el) {
        if (!el) return false;
        const tag = (el.tagName || '').toLowerCase();
        return tag === 'input' || tag === 'textarea' || el.isContentEditable;
    }

    function showShortcuts() {
        overlay.classList.add('show');
        closeBtn.focus();
    }

    function hideShortcuts() {
        overlay.classList.remove('show');
    }

    closeBtn.addEventListener('click', hideShortcuts);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) hideShortcuts();
    });
    modal.addEventListener('click', (e) => e.stopPropagation());

    // Key chord handler (g then d/a/i/s within a short window)
    let awaitingSecondKey = false;
    let chordTimer = null;

    function startChordWindow() {
        awaitingSecondKey = true;
        if (chordTimer) clearTimeout(chordTimer);
        chordTimer = setTimeout(() => { awaitingSecondKey = false; }, 900);
    }

    function go(path) {
        window.location.href = path;
    }

    document.addEventListener('keydown', (e) => {
        // Always allow Escape to close modal
        if (e.key === 'Escape' && overlay.classList.contains('show')) {
            e.preventDefault();
            hideShortcuts();
            return;
        }

        if (isTypingTarget(e.target)) return;
        if (e.ctrlKey || e.metaKey || e.altKey) return;

        // '?' toggles shortcuts modal
        if (e.key === '?') {
            e.preventDefault();
            if (overlay.classList.contains('show')) hideShortcuts();
            else showShortcuts();
            return;
        }

        // 'g' starts navigation chord
        if (!awaitingSecondKey && (e.key === 'g' || e.key === 'G')) {
            startChordWindow();
            return;
        }

        if (awaitingSecondKey) {
            const k = e.key.toLowerCase();
            awaitingSecondKey = false;
            if (chordTimer) clearTimeout(chordTimer);

            if (k === 'd') return go('/dashboard');
            if (k === 'a') return go('/dashboard/analytics');
            if (k === 'i') return go('/dashboard/insights');
            if (k === 's') return go('/dashboard/onboarding-wizard');
        }
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    connectSSE();
    initKeyboardShortcuts();

    // Periodic stats refresh as backup
    setInterval(updateStats, 30000);
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (eventSource) {
        eventSource.close();
    }
});
