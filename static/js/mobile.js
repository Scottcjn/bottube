document.addEventListener('DOMContentLoaded', function() {
    // Mobile viewport detection
    const isMobile = window.innerWidth <= 768;
    const isTouch = 'ontouchstart' in window;

    // Hamburger menu toggle
    const hamburger = document.querySelector('.hamburger-menu');
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.querySelector('.mobile-overlay');

    if (hamburger && sidebar) {
        hamburger.addEventListener('click', function() {
            sidebar.classList.toggle('active');
            document.body.classList.toggle('menu-open');

            if (overlay) {
                overlay.classList.toggle('active');
            }
        });

        if (overlay) {
            overlay.addEventListener('click', function() {
                sidebar.classList.remove('active');
                document.body.classList.remove('menu-open');
                overlay.classList.remove('active');
            });
        }
    }

    // Touch-friendly video controls
    const videos = document.querySelectorAll('video');
    videos.forEach(video => {
        let touchStartTime = 0;
        let touchEndTime = 0;

        video.addEventListener('touchstart', function(e) {
            touchStartTime = Date.now();
        });

        video.addEventListener('touchend', function(e) {
            touchEndTime = Date.now();
            const touchDuration = touchEndTime - touchStartTime;

            // Single tap to play/pause (touch duration < 200ms)
            if (touchDuration < 200) {
                e.preventDefault();
                if (video.paused) {
                    video.play();
                } else {
                    video.pause();
                }
            }
        });

        // Double tap for fullscreen
        let lastTouchEnd = 0;
        video.addEventListener('touchend', function(e) {
            const now = Date.now();
            if (now - lastTouchEnd <= 300) {
                e.preventDefault();
                if (video.requestFullscreen) {
                    video.requestFullscreen();
                } else if (video.webkitRequestFullscreen) {
                    video.webkitRequestFullscreen();
                }
            }
            lastTouchEnd = now;
        });
    });

    // Responsive video container adjustments
    function adjustVideoContainers() {
        const videoContainers = document.querySelectorAll('.video-container');
        const windowWidth = window.innerWidth;

        videoContainers.forEach(container => {
            if (windowWidth <= 480) {
                container.style.height = '200px';
            } else if (windowWidth <= 768) {
                container.style.height = '250px';
            } else {
                container.style.height = 'auto';
            }
        });
    }

    // Swipe gestures for navigation
    let touchStartX = 0;
    let touchStartY = 0;

    document.addEventListener('touchstart', function(e) {
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
    });

    document.addEventListener('touchmove', function(e) {
        if (!touchStartX || !touchStartY) return;

        const touchCurrentX = e.touches[0].clientX;
        const touchCurrentY = e.touches[0].clientY;

        const diffX = touchStartX - touchCurrentX;
        const diffY = touchStartY - touchCurrentY;

        // Prevent scrolling during horizontal swipes
        if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > 50) {
            e.preventDefault();
        }
    });

    document.addEventListener('touchend', function(e) {
        if (!touchStartX || !touchStartY) return;

        const touchEndX = e.changedTouches[0].clientX;
        const touchEndY = e.changedTouches[0].clientY;

        const diffX = touchStartX - touchEndX;
        const diffY = touchStartY - touchEndY;

        // Swipe left/right threshold
        if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > 100) {
            if (diffX > 0 && sidebar && !sidebar.classList.contains('active')) {
                // Swipe left - open sidebar
                sidebar.classList.add('active');
                document.body.classList.add('menu-open');
                if (overlay) overlay.classList.add('active');
            } else if (diffX < 0 && sidebar && sidebar.classList.contains('active')) {
                // Swipe right - close sidebar
                sidebar.classList.remove('active');
                document.body.classList.remove('menu-open');
                if (overlay) overlay.classList.remove('active');
            }
        }

        touchStartX = 0;
        touchStartY = 0;
    });

    // Optimize scroll performance on mobile
    let ticking = false;

    function updateScrollPosition() {
        const scrollTop = window.pageYOffset;
        const header = document.querySelector('.header');

        if (header && isMobile) {
            if (scrollTop > 100) {
                header.classList.add('scrolled');
            } else {
                header.classList.remove('scrolled');
            }
        }

        ticking = false;
    }

    document.addEventListener('scroll', function() {
        if (!ticking) {
            requestAnimationFrame(updateScrollPosition);
            ticking = true;
        }
    });

    // Handle orientation changes
    window.addEventListener('orientationchange', function() {
        setTimeout(function() {
            adjustVideoContainers();

            // Close mobile menu on orientation change
            if (sidebar && sidebar.classList.contains('active')) {
                sidebar.classList.remove('active');
                document.body.classList.remove('menu-open');
                if (overlay) overlay.classList.remove('active');
            }
        }, 100);
    });

    // Resize handler
    let resizeTimer;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function() {
            adjustVideoContainers();
        }, 100);
    });

    // Initial setup
    adjustVideoContainers();

    // Prevent iOS bounce scroll
    document.body.addEventListener('touchmove', function(e) {
        if (e.target === document.body) {
            e.preventDefault();
        }
    });

    // Mobile-specific form handling
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        const inputs = form.querySelectorAll('input, textarea');

        inputs.forEach(input => {
            // Prevent zoom on input focus
            input.addEventListener('focus', function() {
                const viewport = document.querySelector('meta[name=viewport]');
                if (viewport) {
                    viewport.setAttribute('content', 'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=0');
                }
            });

            input.addEventListener('blur', function() {
                const viewport = document.querySelector('meta[name=viewport]');
                if (viewport) {
                    viewport.setAttribute('content', 'width=device-width, initial-scale=1');
                }
            });
        });
    });
});
