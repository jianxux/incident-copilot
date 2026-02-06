/**
 * Chart utilities for Incident Copilot Dashboard
 * Uses Chart.js for visualizations with real-time update support
 */

// Default chart colors for dark theme
const ChartColors = {
    // Severity colors
    critical: '#dc2626',
    high: '#f97316',
    medium: '#eab308',
    low: '#3b82f6',
    info: '#6b7280',
    
    // Status colors
    triggered: '#ef4444',
    acknowledged: '#f59e0b',
    investigating: '#3b82f6',
    resolved: '#22c55e',
    closed: '#64748b',
    
    // General colors
    primary: '#3b82f6',
    success: '#22c55e',
    warning: '#f59e0b',
    danger: '#ef4444',
    
    // Chart palette
    palette: [
        '#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6',
        '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1'
    ],
    
    // Grid and text colors for dark theme
    gridColor: 'rgba(148, 163, 184, 0.1)',
    textColor: '#94a3b8',
    tooltipBg: '#1e293b',
    tooltipBorder: '#334155'
};

// Default chart options for dark theme
const defaultChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: {
        duration: 750,
        easing: 'easeOutQuart'
    },
    plugins: {
        legend: {
            labels: {
                color: ChartColors.textColor,
                font: { family: 'Inter, system-ui, sans-serif' }
            }
        },
        tooltip: {
            backgroundColor: ChartColors.tooltipBg,
            borderColor: ChartColors.tooltipBorder,
            borderWidth: 1,
            titleColor: '#fff',
            bodyColor: ChartColors.textColor,
            padding: 12,
            cornerRadius: 8,
            displayColors: true,
            boxPadding: 4
        }
    },
    scales: {
        x: {
            grid: { color: ChartColors.gridColor },
            ticks: { color: ChartColors.textColor }
        },
        y: {
            grid: { color: ChartColors.gridColor },
            ticks: { color: ChartColors.textColor }
        }
    }
};

/**
 * Chart Manager - handles creation and updates of all dashboard charts
 */
class ChartManager {
    constructor() {
        this.charts = new Map();
        this.updateQueue = [];
        this.isProcessing = false;
    }
    
    /**
     * Create or get a chart instance
     */
    getOrCreate(canvasId, config) {
        if (this.charts.has(canvasId)) {
            return this.charts.get(canvasId);
        }
        
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.warn(`Canvas element not found: ${canvasId}`);
            return null;
        }
        
        const ctx = canvas.getContext('2d');
        const chart = new Chart(ctx, config);
        this.charts.set(canvasId, chart);
        return chart;
    }
    
    /**
     * Update a chart with new data
     */
    update(canvasId, data, options = {}) {
        const chart = this.charts.get(canvasId);
        if (!chart) return;
        
        // Queue update for batch processing
        this.updateQueue.push({ chart, data, options });
        this.processQueue();
    }
    
    /**
     * Process update queue (debounced)
     */
    processQueue() {
        if (this.isProcessing) return;
        
        this.isProcessing = true;
        requestAnimationFrame(() => {
            while (this.updateQueue.length > 0) {
                const { chart, data, options } = this.updateQueue.shift();
                
                if (data.labels) {
                    chart.data.labels = data.labels;
                }
                
                if (data.datasets) {
                    data.datasets.forEach((dataset, i) => {
                        if (chart.data.datasets[i]) {
                            Object.assign(chart.data.datasets[i], dataset);
                        } else {
                            chart.data.datasets.push(dataset);
                        }
                    });
                }
                
                chart.update(options.animation === false ? 'none' : undefined);
            }
            this.isProcessing = false;
        });
    }
    
    /**
     * Add a data point to a chart (for real-time updates)
     */
    addDataPoint(canvasId, label, values, maxPoints = 20) {
        const chart = this.charts.get(canvasId);
        if (!chart) return;
        
        // Add label
        chart.data.labels.push(label);
        
        // Add values to each dataset
        values.forEach((value, i) => {
            if (chart.data.datasets[i]) {
                chart.data.datasets[i].data.push(value);
            }
        });
        
        // Remove old points if exceeding max
        while (chart.data.labels.length > maxPoints) {
            chart.data.labels.shift();
            chart.data.datasets.forEach(dataset => dataset.data.shift());
        }
        
        chart.update('none');
    }
    
    /**
     * Destroy a chart
     */
    destroy(canvasId) {
        const chart = this.charts.get(canvasId);
        if (chart) {
            chart.destroy();
            this.charts.delete(canvasId);
        }
    }
    
    /**
     * Destroy all charts
     */
    destroyAll() {
        this.charts.forEach(chart => chart.destroy());
        this.charts.clear();
    }
}

// Create global chart manager instance
const chartManager = new ChartManager();

/**
 * Create an incidents over time line chart
 */
function createIncidentsOverTimeChart(canvasId, data) {
    const config = {
        type: 'line',
        data: {
            labels: data.labels || [],
            datasets: [{
                label: 'Incidents',
                data: data.values || [],
                borderColor: ChartColors.primary,
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 4,
                pointHoverRadius: 6
            }]
        },
        options: {
            ...defaultChartOptions,
            plugins: {
                ...defaultChartOptions.plugins,
                legend: { display: false }
            },
            scales: {
                ...defaultChartOptions.scales,
                y: {
                    ...defaultChartOptions.scales.y,
                    beginAtZero: true,
                    ticks: {
                        ...defaultChartOptions.scales.y.ticks,
                        stepSize: 1
                    }
                }
            }
        }
    };
    
    return chartManager.getOrCreate(canvasId, config);
}

/**
 * Create a severity distribution doughnut chart
 */
function createSeverityChart(canvasId, data) {
    const config = {
        type: 'doughnut',
        data: {
            labels: ['Critical', 'High', 'Medium', 'Low', 'Info'],
            datasets: [{
                data: [
                    data.critical || 0,
                    data.high || 0,
                    data.medium || 0,
                    data.low || 0,
                    data.info || 0
                ],
                backgroundColor: [
                    ChartColors.critical,
                    ChartColors.high,
                    ChartColors.medium,
                    ChartColors.low,
                    ChartColors.info
                ],
                borderColor: '#1e293b',
                borderWidth: 2,
                hoverOffset: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: ChartColors.textColor,
                        padding: 16,
                        usePointStyle: true,
                        pointStyle: 'circle'
                    }
                },
                tooltip: defaultChartOptions.plugins.tooltip
            }
        }
    };
    
    return chartManager.getOrCreate(canvasId, config);
}

/**
 * Create an MTTR trend chart
 */
function createMTTRChart(canvasId, data) {
    const config = {
        type: 'line',
        data: {
            labels: data.labels || [],
            datasets: [
                {
                    label: 'MTTR (minutes)',
                    data: data.mttr || [],
                    borderColor: ChartColors.primary,
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    fill: true,
                    tension: 0.3
                },
                {
                    label: 'Target',
                    data: data.labels?.map(() => data.target || 30) || [],
                    borderColor: ChartColors.warning,
                    borderDash: [5, 5],
                    pointRadius: 0,
                    fill: false
                }
            ]
        },
        options: {
            ...defaultChartOptions,
            scales: {
                ...defaultChartOptions.scales,
                y: {
                    ...defaultChartOptions.scales.y,
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Minutes',
                        color: ChartColors.textColor
                    }
                }
            }
        }
    };
    
    return chartManager.getOrCreate(canvasId, config);
}

/**
 * Create a service health heatmap
 */
function createServiceHealthChart(canvasId, data) {
    const config = {
        type: 'bar',
        data: {
            labels: data.services || [],
            datasets: [{
                label: 'Health Score',
                data: data.scores || [],
                backgroundColor: (data.scores || []).map(score => {
                    if (score >= 90) return ChartColors.success;
                    if (score >= 70) return ChartColors.warning;
                    return ChartColors.danger;
                }),
                borderRadius: 4,
                borderSkipped: false
            }]
        },
        options: {
            ...defaultChartOptions,
            indexAxis: 'y',
            plugins: {
                legend: { display: false },
                tooltip: defaultChartOptions.plugins.tooltip
            },
            scales: {
                x: {
                    ...defaultChartOptions.scales.x,
                    max: 100,
                    title: {
                        display: true,
                        text: 'Health Score',
                        color: ChartColors.textColor
                    }
                },
                y: {
                    ...defaultChartOptions.scales.y,
                    grid: { display: false }
                }
            }
        }
    };
    
    return chartManager.getOrCreate(canvasId, config);
}

/**
 * Create an incidents by status stacked bar chart
 */
function createStatusChart(canvasId, data) {
    const config = {
        type: 'bar',
        data: {
            labels: data.labels || [],
            datasets: [
                {
                    label: 'Triggered',
                    data: data.triggered || [],
                    backgroundColor: ChartColors.triggered,
                    borderRadius: 4
                },
                {
                    label: 'Acknowledged',
                    data: data.acknowledged || [],
                    backgroundColor: ChartColors.acknowledged,
                    borderRadius: 4
                },
                {
                    label: 'Investigating',
                    data: data.investigating || [],
                    backgroundColor: ChartColors.investigating,
                    borderRadius: 4
                },
                {
                    label: 'Resolved',
                    data: data.resolved || [],
                    backgroundColor: ChartColors.resolved,
                    borderRadius: 4
                }
            ]
        },
        options: {
            ...defaultChartOptions,
            plugins: {
                ...defaultChartOptions.plugins,
                legend: {
                    position: 'top',
                    labels: {
                        color: ChartColors.textColor,
                        usePointStyle: true,
                        pointStyle: 'rect'
                    }
                }
            },
            scales: {
                ...defaultChartOptions.scales,
                x: {
                    ...defaultChartOptions.scales.x,
                    stacked: true
                },
                y: {
                    ...defaultChartOptions.scales.y,
                    stacked: true,
                    beginAtZero: true
                }
            }
        }
    };
    
    return chartManager.getOrCreate(canvasId, config);
}

/**
 * Create a response time distribution histogram
 */
function createResponseTimeChart(canvasId, data) {
    const config = {
        type: 'bar',
        data: {
            labels: data.buckets || ['0-5m', '5-15m', '15-30m', '30-60m', '60m+'],
            datasets: [{
                label: 'Incidents',
                data: data.counts || [],
                backgroundColor: ChartColors.palette.slice(0, 5),
                borderRadius: 4
            }]
        },
        options: {
            ...defaultChartOptions,
            plugins: {
                legend: { display: false },
                tooltip: defaultChartOptions.plugins.tooltip
            },
            scales: {
                ...defaultChartOptions.scales,
                y: {
                    ...defaultChartOptions.scales.y,
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Number of Incidents',
                        color: ChartColors.textColor
                    }
                },
                x: {
                    ...defaultChartOptions.scales.x,
                    title: {
                        display: true,
                        text: 'Response Time',
                        color: ChartColors.textColor
                    }
                }
            }
        }
    };
    
    return chartManager.getOrCreate(canvasId, config);
}

/**
 * Create a real-time metrics sparkline
 */
function createSparkline(canvasId, data, color = ChartColors.primary) {
    const config = {
        type: 'line',
        data: {
            labels: data.labels || [],
            datasets: [{
                data: data.values || [],
                borderColor: color,
                backgroundColor: `${color}20`,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false }
            },
            scales: {
                x: { display: false },
                y: { display: false }
            },
            animation: false
        }
    };
    
    return chartManager.getOrCreate(canvasId, config);
}

/**
 * Create an incidents by service pie chart
 */
function createServiceIncidentsChart(canvasId, data) {
    const config = {
        type: 'pie',
        data: {
            labels: data.services || [],
            datasets: [{
                data: data.counts || [],
                backgroundColor: ChartColors.palette,
                borderColor: '#1e293b',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: ChartColors.textColor,
                        padding: 12,
                        usePointStyle: true
                    }
                },
                tooltip: defaultChartOptions.plugins.tooltip
            }
        }
    };
    
    return chartManager.getOrCreate(canvasId, config);
}

/**
 * Create a team performance radar chart
 */
function createTeamPerformanceChart(canvasId, data) {
    const config = {
        type: 'radar',
        data: {
            labels: ['MTTR', 'Response Time', 'Resolution Rate', 'Communication', 'Documentation'],
            datasets: data.teams?.map((team, i) => ({
                label: team.name,
                data: team.scores,
                borderColor: ChartColors.palette[i % ChartColors.palette.length],
                backgroundColor: `${ChartColors.palette[i % ChartColors.palette.length]}30`,
                pointBackgroundColor: ChartColors.palette[i % ChartColors.palette.length]
            })) || []
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: ChartColors.textColor }
                },
                tooltip: defaultChartOptions.plugins.tooltip
            },
            scales: {
                r: {
                    angleLines: { color: ChartColors.gridColor },
                    grid: { color: ChartColors.gridColor },
                    pointLabels: { color: ChartColors.textColor },
                    ticks: {
                        color: ChartColors.textColor,
                        backdropColor: 'transparent'
                    },
                    min: 0,
                    max: 100
                }
            }
        }
    };
    
    return chartManager.getOrCreate(canvasId, config);
}

/**
 * Update chart with real-time data
 */
function updateChartRealtime(canvasId, newValue, label) {
    const now = label || new Date().toLocaleTimeString();
    chartManager.addDataPoint(canvasId, now, [newValue]);
}

// Expose globally
window.ChartColors = ChartColors;
window.chartManager = chartManager;
window.createIncidentsOverTimeChart = createIncidentsOverTimeChart;
window.createSeverityChart = createSeverityChart;
window.createMTTRChart = createMTTRChart;
window.createServiceHealthChart = createServiceHealthChart;
window.createStatusChart = createStatusChart;
window.createResponseTimeChart = createResponseTimeChart;
window.createSparkline = createSparkline;
window.createServiceIncidentsChart = createServiceIncidentsChart;
window.createTeamPerformanceChart = createTeamPerformanceChart;
window.updateChartRealtime = updateChartRealtime;
