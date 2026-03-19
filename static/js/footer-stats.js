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
                this.animateCountUpdate(this.elements[key], value);
            }
        });
    }
    
    animateCountUpdate(element, newValue) {
        const currentText = element.textContent.replace(/,/g, '');
        const currentValue = parseInt(currentText) || 0;
        
        if (currentValue === newValue) return;
        
        const duration = 800;
        const steps = 20;
        const increment = (newValue - currentValue) / steps;
        let step = 0;
        
        const timer = setInterval(() => {
            step++;
            const value = Math.round(currentValue + (increment * step));
            element.textContent = this.formatNumber(Math.min(value, newValue));
            
            if (step >= steps) {
                clearInterval(timer);
                element.textContent = this.formatNumber(newValue);
            }
        }, duration / steps);
    }
    
    formatNumber(num) {
        return num.toLocaleString();
    }
    
    setLoadingState() {
        Object.values(this.elements).forEach(el => {
            if (el) el.classList.add('loading');
        });
    }
    
    setErrorState() {
        Object.values(this.elements).forEach(el => {
            if (el) {
                el.textContent = '--';
                el.classList.remove('loading');
                el.classList.add('error');
            }
        });
    }
    
    clearErrorState() {
        Object.values(this.elements).forEach(el => {
            if (el) {
                el.classList.remove('loading', 'error');
            }
        });
    }
    
    startPeriodicUpdates() {
        setInterval(() => {
            this.fetchStats();
        }, this.updateInterval);
    }
    
    destroy() {
        if (this.updateTimer) {
            clearInterval(this.updateTimer);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.footerStats = new FooterStats();
});

window.addEventListener('beforeunload', () => {
    if (window.footerStats) {
        window.footerStats.destroy();
    }
});