class SEOEnhancements {
    constructor() {
        this.imageObserver = null;
        this.performanceMetrics = {
            startTime: performance.now(),
            loadedImages: 0,
            failedImages: 0
        };

        this.init();
    }

    init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.setup());
        } else {
            this.setup();
        }
    }

    setup() {
        this.setupLazyLoading();
        this.setupProgressiveImageLoading();
        this.cleanupDebugArtifacts();
        this.initPerformanceMonitoring();
    }

    setupLazyLoading() {
        if (!('IntersectionObserver' in window)) {
            this.fallbackImageLoading();
            return;
        }

        const imageObserverOptions = {
            root: null,
            rootMargin: '50px',
            threshold: 0.1
        };

        this.imageObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    this.loadImage(entry.target);
                    this.imageObserver.unobserve(entry.target);
                }
            });
        }, imageObserverOptions);

        const lazyImages = document.querySelectorAll('img[data-src], img[loading="lazy"]');
        lazyImages.forEach(img => {
            this.imageObserver.observe(img);
        });
    }

    loadImage(imageElement) {
        const dataSrc = imageElement.dataset.src;
        const dataSrcset = imageElement.dataset.srcset;

        if (dataSrc) {
            imageElement.src = dataSrc;
            imageElement.removeAttribute('data-src');
        }

        if (dataSrcset) {
            imageElement.srcset = dataSrcset;
            imageElement.removeAttribute('data-srcset');
        }

        imageElement.addEventListener('load', () => {
            this.performanceMetrics.loadedImages++;
            imageElement.classList.add('loaded');
        }, { once: true });

        imageElement.addEventListener('error', () => {
            this.performanceMetrics.failedImages++;
            this.handleImageLoadError(imageElement);
        }, { once: true });
    }

    handleImageLoadError(imageElement) {
        const fallbackSrc = imageElement.dataset.fallback || '/static/images/placeholder.svg';
        if (imageElement.src !== fallbackSrc) {
            imageElement.src = fallbackSrc;
        }
        imageElement.classList.add('error');
    }

    fallbackImageLoading() {
        const lazyImages = document.querySelectorAll('img[data-src]');
        lazyImages.forEach(img => {
            setTimeout(() => this.loadImage(img), 100);
        });
    }

    setupProgressiveImageLoading() {
        const images = document.querySelectorAll('img');

        images.forEach(img => {
            if (!img.srcset && img.dataset.sizes) {
                this.generateResponsiveSizes(img);
            }

            if (!img.alt && img.dataset.altText) {
                img.alt = img.dataset.altText;
            }

            if (!img.loading) {
                img.loading = 'lazy';
            }
        });
    }

    generateResponsiveSizes(imageElement) {
        const baseSrc = imageElement.src || imageElement.dataset.src;
        if (!baseSrc) return;

        const sizes = ['320w', '640w', '1024w', '1280w'];
        const srcsetParts = sizes.map(size => {
            const width = parseInt(size);
            return `${this.getResponsiveImageUrl(baseSrc, width)} ${size}`;
        });

        imageElement.srcset = srcsetParts.join(', ');
        imageElement.sizes = '(max-width: 320px) 320px, (max-width: 640px) 640px, (max-width: 1024px) 1024px, 1280px';
    }

    getResponsiveImageUrl(originalUrl, width) {
        if (originalUrl.includes('/uploads/')) {
            const parts = originalUrl.split('/uploads/');
            return `${parts[0]}/uploads/resized/${width}/${parts[1]}`;
        }
        return originalUrl;
    }

    cleanupDebugArtifacts() {
        if (window.location.hostname !== 'localhost' && !window.location.hostname.includes('127.0.0.1')) {
            this.removeConsoleStatements();
            this.removeDebugElements();
        }
    }

    removeConsoleStatements() {
        const originalConsole = window.console;
        const noop = () => {};

        if (typeof originalConsole === 'object') {
            window.console = {
                ...originalConsole,
                log: noop,
                debug: noop,
                info: originalConsole.info,
                warn: originalConsole.warn,
                error: originalConsole.error
            };
        }
    }

    removeDebugElements() {
        const debugElements = document.querySelectorAll('[data-debug], .debug, #debug-panel');
        debugElements.forEach(el => el.remove());
    }

    initPerformanceMonitoring() {
        if ('PerformanceObserver' in window) {
            this.setupPerformanceObserver();
        }

        window.addEventListener('load', () => {
            this.calculatePerformanceMetrics();
        });
    }

    setupPerformanceObserver() {
        try {
            const observer = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                entries.forEach(entry => {
                    if (entry.entryType === 'largest-contentful-paint') {
                        this.trackLCP(entry.startTime);
                    }
                    if (entry.entryType === 'layout-shift') {
                        this.trackCLS(entry.value);
                    }
                });
            });

            observer.observe({ entryTypes: ['largest-contentful-paint', 'layout-shift'] });
        } catch (error) {
            // Silently handle unsupported performance observers
        }
    }

    trackLCP(value) {
        if (window.gtag) {
            window.gtag('event', 'web_vitals', {
                name: 'LCP',
                value: Math.round(value),
                event_category: 'Performance'
            });
        }
    }

    trackCLS(value) {
        if (window.gtag && value > 0.1) {
            window.gtag('event', 'web_vitals', {
                name: 'CLS',
                value: value,
                event_category: 'Performance'
            });
        }
    }

    calculatePerformanceMetrics() {
        const endTime = performance.now();
        const totalTime = endTime - this.performanceMetrics.startTime;

        const metrics = {
            totalLoadTime: totalTime,
            imagesLoaded: this.performanceMetrics.loadedImages,
            imagesFailed: this.performanceMetrics.failedImages,
            timestamp: new Date().toISOString()
        };

        this.sendPerformanceData(metrics);
    }

    sendPerformanceData(metrics) {
        if (navigator.sendBeacon && window.location.hostname !== 'localhost') {
            const data = JSON.stringify(metrics);
            navigator.sendBeacon('/api/performance-metrics', data);
        }
    }
}

const seoEnhancements = new SEOEnhancements();
