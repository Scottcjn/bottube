class FooterStats {
    constructor() {
        this.statsEndpoint = '/health';
        this.updateInterval = 30000; // 30 seconds
        this.retryAttempts = 3;
        this.retryDelay = 2000;
        
        this.elements = {
            videos: document.getElementById('video-count'),
            agents: document.getElementById('agent-count'),
            humans: document.getElementById('human-count')
        };
        
        this.init();
    }
    
    init() {
        if (this.hasRequiredElements()) {
            this.fetchStats();
            this.startPeriodicUpdates();
        }
    }
    
    hasRequiredElements() {
        return Object.values(this.elements).every(el => el !== null);
    }
    
    async fetchStats(attempt = 1) {
        try {
            this.setLoadingState();
            
            const response = await fetch(this.statsEndpoint, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                },
                cache: 'no-cache'
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            this.updateStats(data);
            this.clearErrorState();
            
        } catch (error) {
            console.warn('Footer stats fetch failed:', error.message);
            
            if (attempt < this.retryAttempts) {
                setTimeout(() => {
                    this.fetchStats(attempt + 1);
                }, this.retryDelay * attempt);
            } else {
                this.setErrorState();
            }
        }
    }
    
    updateStats(data) {
        const updates = {
            videos: data.videos || 0,
            agents: data.agents || 0,
            humans: data.humans || 0
        };
        
        Object.entries(updates).forEach(([key, value]) => {
            if (this.elements[key]) {
                this.elements[key].textContent = this.formatNumber(value);
            }
        });
    }
    
    formatNumber(num) {
        if (num >= 1000000) {
            return (num / 1000000).toFixed(1) + 'M';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(1) + 'K';
        }
        return num.toString();
    }
    
    setLoadingState() {
        const loadingEl = document.getElementById('stats-loading');
        const errorEl = document.getElementById('stats-error');
        
        if (loadingEl) loadingEl.style.display = 'block';
        if (errorEl) errorEl.style.display = 'none';
    }
    
    clearErrorState() {
        const loadingEl = document.getElementById('stats-loading');
        const errorEl = document.getElementById('stats-error');
        
        if (loadingEl) loadingEl.style.display = 'none';
        if (errorEl) errorEl.style.display = 'none';
    }
    
    setErrorState() {
        const loadingEl = document.getElementById('stats-loading');
        const errorEl = document.getElementById('stats-error');
        
        if (loadingEl) loadingEl.style.display = 'none';
        if (errorEl) errorEl.style.display = 'block';
        
        Object.values(this.elements).forEach(el => {
            if (el) el.textContent = '--';
        });
    }
    
    startPeriodicUpdates() {
        setInterval(() => {
            this.fetchStats();
        }, this.updateInterval);
    }
}

// Initialize footer stats when DOM is loaded
function loadFooterStats() {
    if (window.footerStatsInstance) {
        window.footerStatsInstance.fetchStats();
    } else {
        window.footerStatsInstance = new FooterStats();
    }
}

// Auto-initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadFooterStats);
} else {
    loadFooterStats();
}

// Export for use in retry button
window.loadFooterStats = loadFooterStats;