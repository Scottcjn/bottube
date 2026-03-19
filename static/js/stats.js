async function fetchHealthStats() {
    try {
        const response = await fetch('/api/health');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error fetching health stats:', error);
        return null;
    }
}

function updateStatsDisplay(stats) {
    if (!stats) {
        return;
    }

    // Update total videos
    const totalVideosElement = document.getElementById('total-videos');
    if (totalVideosElement && stats.total_videos !== undefined) {
        totalVideosElement.textContent = stats.total_videos.toLocaleString();
    }

    // Update total channels
    const totalChannelsElement = document.getElementById('total-channels');
    if (totalChannelsElement && stats.total_channels !== undefined) {
        totalChannelsElement.textContent = stats.total_channels.toLocaleString();
    }

    // Update total views
    const totalViewsElement = document.getElementById('total-views');
    if (totalViewsElement && stats.total_views !== undefined) {
        totalViewsElement.textContent = stats.total_views.toLocaleString();
    }

    // Update storage used
    const storageUsedElement = document.getElementById('storage-used');
    if (storageUsedElement && stats.storage_used !== undefined) {
        storageUsedElement.textContent = formatBytes(stats.storage_used);
    }

    // Update uptime
    const uptimeElement = document.getElementById('uptime');
    if (uptimeElement && stats.uptime !== undefined) {
        uptimeElement.textContent = formatUptime(stats.uptime);
    }
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatUptime(seconds) {
    const days = Math.floor(seconds / (24 * 3600));
    const hours = Math.floor((seconds % (24 * 3600)) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    
    if (days > 0) {
        return `${days}d ${hours}h ${minutes}m`;
    } else if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else {
        return `${minutes}m`;
    }
}

async function initializeStats() {
    const stats = await fetchHealthStats();
    updateStatsDisplay(stats);
}

function startStatsPolling(intervalMs = 30000) {
    initializeStats();
    setInterval(async () => {
        const stats = await fetchHealthStats();
        updateStatsDisplay(stats);
    }, intervalMs);
}

// Initialize stats when DOM is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeStats);
} else {
    initializeStats();
}

// Export functions for potential use in other modules
window.BoTTubeStats = {
    fetchHealthStats,
    updateStatsDisplay,
    initializeStats,
    startStatsPolling,
    formatBytes,
    formatUptime
};