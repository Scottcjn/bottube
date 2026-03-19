// Footer stats updater
(function() {
    'use strict';

    const STATS_UPDATE_INTERVAL = 30000; // 30 seconds
    const HEALTH_ENDPOINT = '/health';

    // Stats elements
    const statsElements = {
        totalVideos: document.querySelector('[data-stat="total-videos"]'),
        totalViews: document.querySelector('[data-stat="total-views"]'),
        totalUsers: document.querySelector('[data-stat="total-users"]'),
        serverUptime: document.querySelector('[data-stat="server-uptime"]')
    };

    // Format numbers with commas
    function formatNumber(num) {
        if (num === null || num === undefined) return '--';
        return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }

    // Format uptime
    function formatUptime(seconds) {
        if (!seconds) return '--';
        
        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);

        if (days > 0) {
            return `${days}d ${hours}h`;
        } else if (hours > 0) {
            return `${hours}h ${minutes}m`;
        } else {
            return `${minutes}m`;
        }
    }

    // Update stats display
    function updateStatsDisplay(data) {
        try {
            if (statsElements.totalVideos && data.stats && data.stats.total_videos !== undefined) {
                statsElements.totalVideos.textContent = formatNumber(data.stats.total_videos);
            }

            if (statsElements.totalViews && data.stats && data.stats.total_views !== undefined) {
                statsElements.totalViews.textContent = formatNumber(data.stats.total_views);
            }

            if (statsElements.totalUsers && data.stats && data.stats.total_users !== undefined) {
                statsElements.totalUsers.textContent = formatNumber(data.stats.total_users);
            }

            if (statsElements.serverUptime && data.uptime !== undefined) {
                statsElements.serverUptime.textContent = formatUptime(data.uptime);
            }
        } catch (error) {
            console.warn('Error updating stats display:', error);
        }
    }

    // Fetch stats from health endpoint
    async function fetchStats() {
        try {
            const response = await fetch(HEALTH_ENDPOINT, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json'
                },
                cache: 'no-cache'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            updateStatsDisplay(data);

        } catch (error) {
            console.warn('Failed to fetch stats:', error);
            // Keep existing values on error, don't reset to "--"
        }
    }

    // Initialize stats updater
    function init() {
        // Check if any stats elements exist
        const hasStatsElements = Object.values(statsElements).some(el => el !== null);
        
        if (!hasStatsElements) {
            console.info('No footer stats elements found, skipping stats updater');
            return;
        }

        // Initial fetch
        fetchStats();

        // Set up periodic updates
        setInterval(fetchStats, STATS_UPDATE_INTERVAL);

        // Update on page visibility change (when user returns to tab)
        if (typeof document.addEventListener === 'function') {
            document.addEventListener('visibilitychange', function() {
                if (!document.hidden) {
                    fetchStats();
                }
            });
        }
    }

    // Start when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();