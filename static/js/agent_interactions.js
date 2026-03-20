class AgentInteractionManager {
    constructor() {
        this.socket = null;
        this.charts = {};
        this.currentFilters = {
            agent: 'all',
            timeRange: '24h',
            status: 'all'
        };
        this.interactions = [];
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;

        this.initializeWebSocket();
        this.initializeCharts();
        this.bindEvents();
        this.loadInitialData();
    }

    initializeWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/agent-interactions`;

        try {
            this.socket = new WebSocket(wsUrl);
            this.setupWebSocketHandlers();
        } catch (error) {
            console.error('WebSocket connection failed:', error);
            this.scheduleReconnect();
        }
    }

    setupWebSocketHandlers() {
        this.socket.onopen = () => {
            console.log('Agent interactions WebSocket connected');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.updateConnectionStatus(true);
        };

        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };

        this.socket.onclose = (event) => {
            console.log('WebSocket connection closed:', event.code, event.reason);
            this.isConnected = false;
            this.updateConnectionStatus(false);

            if (event.code !== 1000) {
                this.scheduleReconnect();
            }
        };

        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.updateConnectionStatus(false);
        };
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'interaction_update':
                this.updateInteraction(data.interaction);
                break;
            case 'new_interaction':
                this.addNewInteraction(data.interaction);
                break;
            case 'agent_status':
                this.updateAgentStatus(data.agent_id, data.status);
                break;
            case 'metrics_update':
                this.updateMetrics(data.metrics);
                break;
            default:
                console.warn('Unknown message type:', data.type);
        }
    }

    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max reconnection attempts reached');
            return;
        }

        const delay = Math.pow(2, this.reconnectAttempts) * 1000;
        this.reconnectAttempts++;

        setTimeout(() => {
            console.log(`Reconnection attempt ${this.reconnectAttempts}`);
            this.initializeWebSocket();
        }, delay);
    }

    updateConnectionStatus(connected) {
        const statusElement = document.getElementById('connection-status');
        if (statusElement) {
            statusElement.className = connected ? 'status-connected' : 'status-disconnected';
            statusElement.textContent = connected ? 'Connected' : 'Disconnected';
        }
    }

    initializeCharts() {
        this.initializeEngagementChart();
        this.initializeActivityChart();
        this.initializeResponseTimeChart();
    }

    initializeEngagementChart() {
        const ctx = document.getElementById('engagement-chart');
        if (!ctx) return;

        this.charts.engagement = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Interactions',
                    data: [],
                    borderColor: '#4f46e5',
                    backgroundColor: '#4f46e5',
                    tension: 0.3,
                    fill: false
                }, {
                    label: 'Responses',
                    data: [],
                    borderColor: '#10b981',
                    backgroundColor: '#10b981',
                    tension: 0.3,
                    fill: false
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top'
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false
                    }
                },
                interaction: {
                    mode: 'nearest',
                    axis: 'x',
                    intersect: false
                }
            }
        });
    }

    initializeActivityChart() {
        const ctx = document.getElementById('activity-chart');
        if (!ctx) return;

        this.charts.activity = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Active', 'Idle', 'Processing', 'Error'],
                datasets: [{
                    data: [0, 0, 0, 0],
                    backgroundColor: [
                        '#10b981',
                        '#6b7280',
                        '#f59e0b',
                        '#ef4444'
                    ],
                    borderWidth: 2,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }

    initializeResponseTimeChart() {
        const ctx = document.getElementById('response-time-chart');
        if (!ctx) return;

        this.charts.responseTime = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Average Response Time (ms)',
                    data: [],
                    backgroundColor: '#8b5cf6',
                    borderColor: '#7c3aed',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return value + 'ms';
                            }
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }

    bindEvents() {
        document.addEventListener('DOMContentLoaded', () => {
            this.bindFilterEvents();
            this.bindRefreshButton();
            this.bindExportButton();
        });
    }

    bindFilterEvents() {
        const agentFilter = document.getElementById('agent-filter');
        const timeRangeFilter = document.getElementById('time-range-filter');
        const statusFilter = document.getElementById('status-filter');

        if (agentFilter) {
            agentFilter.addEventListener('change', (e) => {
                this.currentFilters.agent = e.target.value;
                this.applyFilters();
            });
        }

        if (timeRangeFilter) {
            timeRangeFilter.addEventListener('change', (e) => {
                this.currentFilters.timeRange = e.target.value;
                this.applyFilters();
            });
        }

        if (statusFilter) {
            statusFilter.addEventListener('change', (e) => {
                this.currentFilters.status = e.target.value;
                this.applyFilters();
            });
        }
    }

    bindRefreshButton() {
        const refreshBtn = document.getElementById('refresh-interactions');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.loadInitialData();
                this.showNotification('Data refreshed successfully', 'success');
            });
        }
    }

    bindExportButton() {
        const exportBtn = document.getElementById('export-interactions');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => {
                this.exportData();
            });
        }
    }

    async loadInitialData() {
        try {
            const response = await fetch('/api/agent-interactions?' + new URLSearchParams(this.currentFilters));
            if (!response.ok) throw new Error('Failed to load interactions');

            const data = await response.json();
            this.interactions = data.interactions || [];

            this.updateInteractionsList();
            this.updateCharts(data);
            this.updateStats(data.stats || {});

        } catch (error) {
            console.error('Error loading initial data:', error);
            this.showNotification('Failed to load interaction data', 'error');
        }
    }

    applyFilters() {
        this.loadInitialData();
    }

    updateInteraction(interaction) {
        const index = this.interactions.findIndex(i => i.id === interaction.id);
        if (index !== -1) {
            this.interactions[index] = interaction;
        } else {
            this.interactions.unshift(interaction);
        }

        this.updateInteractionsList();
        this.updateChartsRealTime(interaction);
    }

    addNewInteraction(interaction) {
        this.interactions.unshift(interaction);

        if (this.interactions.length > 100) {
            this.interactions = this.interactions.slice(0, 100);
        }

        this.updateInteractionsList();
        this.updateChartsRealTime(interaction);
        this.showInteractionNotification(interaction);
    }

    updateInteractionsList() {
        const container = document.getElementById('interactions-list');
        if (!container) return;

        const filteredInteractions = this.filterInteractions();

        container.innerHTML = '';

        filteredInteractions.forEach(interaction => {
            const element = this.createInteractionElement(interaction);
            container.appendChild(element);
        });
    }

    filterInteractions() {
        return this.interactions.filter(interaction => {
            if (this.currentFilters.agent !== 'all' && interaction.agent_id !== this.currentFilters.agent) {
                return false;
            }

            if (this.currentFilters.status !== 'all' && interaction.status !== this.currentFilters.status) {
                return false;
            }

            const now = new Date();
            const interactionTime = new Date(interaction.timestamp);
            const timeDiff = now - interactionTime;

            switch (this.currentFilters.timeRange) {
                case '1h':
                    return timeDiff <= 3600000;
                case '6h':
                    return timeDiff <= 21600000;
                case '24h':
                    return timeDiff <= 86400000;
                case '7d':
                    return timeDiff <= 604800000;
                default:
                    return true;
            }
        });
    }

    createInteractionElement(interaction) {
        const div = document.createElement('div');
        div.className = `interaction-item status-${interaction.status}`;
        div.dataset.interactionId = interaction.id;

        const statusClass = this.getStatusClass(interaction.status);
        const timeAgo = this.formatTimeAgo(interaction.timestamp);

        div.innerHTML = `
            <div class="interaction-header">
                <div class="agent-info">
                    <span class="agent-name">${interaction.agent_name}</span>
                    <span class="interaction-type">${interaction.type}</span>
                </div>
                <div class="interaction-meta">
                    <span class="status-badge ${statusClass}">${interaction.status}</span>
                    <span class="timestamp">${timeAgo}</span>
                </div>
            </div>
            <div class="interaction-content">
                <div class="message-preview">${this.truncateText(interaction.message || '', 100)}</div>
                ${interaction.response ? `<div class="response-preview">${this.truncateText(interaction.response, 100)}</div>` : ''}
            </div>
            <div class="interaction-stats">
                ${interaction.response_time ? `<span class="response-time">${interaction.response_time}ms</span>` : ''}
                ${interaction.confidence ? `<span class="confidence">${Math.round(interaction.confidence * 100)}% confidence</span>` : ''}
            </div>
        `;

        div.addEventListener('click', () => this.showInteractionDetails(interaction));

        return div;
    }

    getStatusClass(status) {
        const statusClasses = {
            'completed': 'status-success',
            'processing': 'status-warning',
            'failed': 'status-error',
            'pending': 'status-info'
        };
        return statusClasses[status] || 'status-default';
    }

    formatTimeAgo(timestamp) {
        const now = new Date();
        const time = new Date(timestamp);
        const diff = now - time;

        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (days > 0) return `${days}d ago`;
        if (hours > 0) return `${hours}h ago`;
        if (minutes > 0) return `${minutes}m ago`;
        return `${seconds}s ago`;
    }

    truncateText(text, maxLength) {
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    }

    updateCharts(data) {
        if (data.engagement_data && this.charts.engagement) {
            this.charts.engagement.data.labels = data.engagement_data.labels;
            this.charts.engagement.data.datasets[0].data = data.engagement_data.interactions;
            this.charts.engagement.data.datasets[1].data = data.engagement_data.responses;
            this.charts.engagement.update('none');
        }

        if (data.activity_data && this.charts.activity) {
            this.charts.activity.data.datasets[0].data = [
                data.activity_data.active,
                data.activity_data.idle,
                data.activity_data.processing,
                data.activity_data.error
            ];
            this.charts.activity.update('none');
        }

        if (data.response_time_data && this.charts.responseTime) {
            this.charts.responseTime.data.labels = data.response_time_data.agents;
            this.charts.responseTime.data.datasets[0].data = data.response_time_data.times;
            this.charts.responseTime.update('none');
        }
    }

    updateChartsRealTime(interaction) {
        if (!this.charts.engagement) return;

        const now = new Date();
        const timeLabel = now.toLocaleTimeString();

        const chart = this.charts.engagement;
        chart.data.labels.push(timeLabel);
        chart.data.datasets[0].data.push(1);
        chart.data.datasets[1].data.push(interaction.status === 'completed' ? 1 : 0);

        if (chart.data.labels.length > 20) {
            chart.data.labels.shift();
            chart.data.datasets[0].data.shift();
            chart.data.datasets[1].data.shift();
        }

        chart.update('none');
    }

    updateStats(stats) {
        this.updateStatElement('total-interactions', stats.total_interactions || 0);
        this.updateStatElement('active-agents', stats.active_agents || 0);
        this.updateStatElement('avg-response-time', `${stats.avg_response_time || 0}ms`);
        this.updateStatElement('success-rate', `${Math.round((stats.success_rate || 0) * 100)}%`);
    }

    updateStatElement(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }

    updateAgentStatus(agentId, status) {
        const agentElements = document.querySelectorAll(`[data-agent-id="${agentId}"]`);
        agentElements.forEach(element => {
            element.className = element.className.replace(/status-\w+/, `status-${status}`);
        });
    }

    updateMetrics(metrics) {
        this.updateStats(metrics);
        if (this.charts.activity && metrics.activity_breakdown) {
            this.charts.activity.data.datasets[0].data = [
                metrics.activity_breakdown.active,
                metrics.activity_breakdown.idle,
                metrics.activity_breakdown.processing,
                metrics.activity_breakdown.error
            ];
            this.charts.activity.update('none');
        }
    }

    showInteractionDetails(interaction) {
        const modal = document.getElementById('interaction-modal');
        if (!modal) return;

        const content = modal.querySelector('.modal-content');
        if (!content) return;

        content.innerHTML = `
            <div class="modal-header">
                <h3>Interaction Details</h3>
                <button class="modal-close">&times;</button>
            </div>
            <div class="modal-body">
                <div class="detail-group">
                    <label>Agent:</label>
                    <span>${interaction.agent_name}</span>
                </div>
                <div class="detail-group">
                    <label>Type:</label>
                    <span>${interaction.type}</span>
                </div>
                <div class="detail-group">
                    <label>Status:</label>
                    <span class="status-badge ${this.getStatusClass(interaction.status)}">${interaction.status}</span>
                </div>
                <div class="detail-group">
                    <label>Timestamp:</label>
                    <span>${new Date(interaction.timestamp).toLocaleString()}</span>
                </div>
                ${interaction.message ? `
                <div class="detail-group">
                    <label>Message:</label>
                    <div class="message-content">${interaction.message}</div>
                </div>
                ` : ''}
                ${interaction.response ? `
                <div class="detail-group">
                    <label>Response:</label>
                    <div class="response-content">${interaction.response}</div>
                </div>
                ` : ''}
                ${interaction.response_time ? `
                <div class="detail-group">
                    <label>Response Time:</label>
                    <span>${interaction.response_time}ms</span>
                </div>
                ` : ''}
                ${interaction.confidence ? `
                <div class="detail-group">
                    <label>Confidence:</label>
                    <span>${Math.round(interaction.confidence * 100)}%</span>
                </div>
                ` : ''}
            </div>
        `;

        modal.style.display = 'block';

        const closeBtn = content.querySelector('.modal-close');
        closeBtn.addEventListener('click', () => {
            modal.style.display = 'none';
        });
    }

    showInteractionNotification(interaction) {
        const notification = document.createElement('div');
        notification.className = 'interaction-notification';
        notification.innerHTML = `
            <div class="notification-content">
                <strong>${interaction.agent_name}</strong> - ${interaction.type}
                <div class="notification-message">${this.truncateText(interaction.message || '', 50)}</div>
            </div>
        `;

        document.body.appendChild(notification);

        setTimeout(() => {
            notification.classList.add('show');
        }, 100);

        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                notification.remove();
            }, 300);
        }, 3000);
    }

    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;

        document.body.appendChild(notification);

        setTimeout(() => {
            notification.classList.add('show');
        }, 100);

        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                notification.remove();
            }, 300);
        }, 3000);
    }

    async exportData() {
        try {
            const response = await fetch('/api/agent-interactions/export?' + new URLSearchParams(this.currentFilters));
            if (!response.ok) throw new Error('Export failed');

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `agent_interactions_${new Date().toISOString().split('T')[0]}.csv`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            this.showNotification('Data exported successfully', 'success');
        } catch (error) {
            console.error('Export error:', error);
            this.showNotification('Export failed', 'error');
        }
    }

    destroy() {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.close();
        }

        Object.values(this.charts).forEach(chart => {
            if (chart) chart.destroy();
        });

        this.charts = {};
        this.interactions = [];
    }
}

let agentInteractionManager;

document.addEventListener('DOMContentLoaded', () => {
    agentInteractionManager = new AgentInteractionManager();
});

window.addEventListener('beforeunload', () => {
    if (agentInteractionManager) {
        agentInteractionManager.destroy();
    }
});
