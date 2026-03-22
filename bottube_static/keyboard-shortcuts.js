/**
 * BoTTube Video Player Keyboard Shortcuts
 * Issue: rustchain-bounties#2140
 * Bounty: 5 RTC
 * 
 * YouTube-style keyboard shortcuts for video playback
 */

(function() {
    'use strict';
    
    // Configuration
    const SHORTCUTS = {
        ' ': 'togglePlay',      // Space - Play/Pause
        'k': 'togglePlay',      // K - Play/Pause
        'j': 'rewind10',        // J - Seek back 10s
        'l': 'forward10',       // L - Seek forward 10s
        'm': 'toggleMute',      // M - Mute toggle
        'f': 'toggleFullscreen',// F - Fullscreen
        'arrowleft': 'rewind5', // Left Arrow - Seek back 5s
        'arrowright': 'forward5',// Right Arrow - Seek forward 5s
        'arrowup': 'volumeUp',  // Up Arrow - Volume up
        'arrowdown': 'volumeDown'// Down Arrow - Volume down
    };
    
    const SEEK_TIME = {
        short: 5,   // seconds
        long: 10    // seconds
    };
    
    const VOLUME_STEP = 0.1; // 10%
    
    let videoPlayer = null;
    let overlayTimeout = null;
    
    /**
     * Initialize keyboard shortcuts
     */
    function init() {
        // Find video player
        videoPlayer = document.querySelector('video') || document.querySelector('iframe');
        
        if (!videoPlayer) {
            console.log('[BoTTube Shortcuts] No video player found');
            return;
        }
        
        // Add keyboard listener
        document.addEventListener('keydown', handleKeyDown);
        
        console.log('[BoTTube Shortcuts] Keyboard shortcuts enabled');
        showOverlay('Keyboard shortcuts enabled - Press ? for help');
    }
    
    /**
     * Handle keyboard events
     */
    function handleKeyDown(event) {
        // Ignore if typing in input/textarea
        if (isInputFocused()) {
            return;
        }
        
        const key = event.key.toLowerCase();
        const action = SHORTCUTS[key];
        
        if (action) {
            event.preventDefault();
            executeAction(action);
            showFeedback(key);
        }
        
        // Help overlay
        if (key === '?' || (event.shiftKey && key === '/')) {
            event.preventDefault();
            showHelpOverlay();
        }
    }
    
    /**
     * Check if input element is focused
     */
    function isInputFocused() {
        const active = document.activeElement;
        return active && (
            active.tagName === 'INPUT' ||
            active.tagName === 'TEXTAREA' ||
            active.isContentEditable
        );
    }
    
    /**
     * Execute shortcut action
     */
    function executeAction(action) {
        switch (action) {
            case 'togglePlay':
                if (videoPlayer.paused) {
                    videoPlayer.play();
                } else {
                    videoPlayer.pause();
                }
                break;
                
            case 'rewind10':
                videoPlayer.currentTime = Math.max(0, videoPlayer.currentTime - SEEK_TIME.long);
                break;
                
            case 'forward10':
                videoPlayer.currentTime = Math.min(
                    videoPlayer.duration,
                    videoPlayer.currentTime + SEEK_TIME.long
                );
                break;
                
            case 'rewind5':
                videoPlayer.currentTime = Math.max(0, videoPlayer.currentTime - SEEK_TIME.short);
                break;
                
            case 'forward5':
                videoPlayer.currentTime = Math.min(
                    videoPlayer.duration,
                    videoPlayer.currentTime + SEEK_TIME.short
                );
                break;
                
            case 'toggleMute':
                videoPlayer.muted = !videoPlayer.muted;
                break;
                
            case 'toggleFullscreen':
                toggleFullscreen();
                break;
                
            case 'volumeUp':
                videoPlayer.volume = Math.min(1, videoPlayer.volume + VOLUME_STEP);
                break;
                
            case 'volumeDown':
                videoPlayer.volume = Math.max(0, videoPlayer.volume - VOLUME_STEP);
                break;
        }
    }
    
    /**
     * Toggle fullscreen
     */
    function toggleFullscreen() {
        const container = document.querySelector('.video-player-container') || document.documentElement;
        
        if (!document.fullscreenElement) {
            container.requestFullscreen().catch(err => {
                console.log('[BoTTube Shortcuts] Fullscreen error:', err);
            });
        } else {
            document.exitFullscreen();
        }
    }
    
    /**
     * Show feedback overlay
     */
    function showFeedback(key) {
        let overlay = document.getElementById('shortcut-feedback-overlay');
        
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'shortcut-feedback-overlay';
            overlay.style.cssText = `
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: rgba(0, 0, 0, 0.8);
                color: white;
                padding: 20px 40px;
                border-radius: 8px;
                font-size: 48px;
                font-weight: bold;
                z-index: 9999;
                pointer-events: none;
                opacity: 0;
                transition: opacity 0.2s;
            `;
            document.body.appendChild(overlay);
        }
        
        // Set icon based on key
        const icons = {
            ' ': '▶',
            'k': '▶',
            'j': '⏪',
            'l': '⏩',
            'm': '🔇',
            'f': '⛶',
            'arrowleft': '⏪',
            'arrowright': '⏩',
            'arrowup': '🔊',
            'arrowdown': '🔉'
        };
        
        overlay.textContent = icons[key] || key.toUpperCase();
        overlay.style.opacity = '1';
        
        // Clear existing timeout
        if (overlayTimeout) {
            clearTimeout(overlayTimeout);
        }
        
        // Hide after 500ms
        overlayTimeout = setTimeout(() => {
            overlay.style.opacity = '0';
        }, 500);
    }
    
    /**
     * Show help overlay
     */
    function showHelpOverlay() {
        let overlay = document.getElementById('shortcuts-help-overlay');
        
        if (overlay) {
            overlay.remove();
            return;
        }
        
        overlay = document.createElement('div');
        overlay.id = 'shortcuts-help-overlay';
        overlay.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0, 0, 0, 0.95);
            color: white;
            padding: 30px;
            border-radius: 12px;
            font-family: Arial, sans-serif;
            z-index: 10000;
            max-width: 500px;
            width: 90%;
        `;
        
        overlay.innerHTML = `
            <h2 style="margin: 0 0 20px 0; font-size: 24px;">⌨️ Keyboard Shortcuts</h2>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                <div><strong>Space / K</strong></div><div>Play/Pause</div>
                <div><strong>J</strong></div><div>Rewind 10s</div>
                <div><strong>L</strong></div><div>Forward 10s</div>
                <div><strong>← / →</strong></div><div>Seek 5s</div>
                <div><strong>M</strong></div><div>Mute</div>
                <div><strong>F</strong></div><div>Fullscreen</div>
                <div><strong>↑ / ↓</strong></div><div>Volume</div>
                <div><strong>?</strong></div><div>Show this help</div>
            </div>
            <p style="margin-top: 20px; font-size: 12px; color: #aaa; text-align: center;">
                Press ? to close
            </p>
        `;
        
        overlay.addEventListener('click', () => overlay.remove());
        document.body.appendChild(overlay);
    }
    
    /**
     * Show generic overlay message
     */
    function showOverlay(message) {
        const overlay = document.createElement('div');
        overlay.style.cssText = `
            position: fixed;
            bottom: 80px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 10px 20px;
            border-radius: 6px;
            font-size: 14px;
            z-index: 9999;
            opacity: 0;
            transition: opacity 0.3s;
        `;
        overlay.textContent = message;
        document.body.appendChild(overlay);
        
        setTimeout(() => overlay.style.opacity = '1', 100);
        setTimeout(() => {
            overlay.style.opacity = '0';
            setTimeout(() => overlay.remove(), 300);
        }, 2000);
    }
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
