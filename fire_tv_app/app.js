// Fire TV App for BoTTube
// Main application logic for video browsing and playback

class BoTTubeFireTVApp {
    constructor() {
        this.apiBaseUrl = 'https://api.bottube.com';
        this.currentFocus = null;
        this.navigationStack = [];
        this.videos = [];
        this.categories = [];
        this.currentCategory = 'trending';
        this.currentVideoIndex = 0;
        this.player = null;
        this.isPlaying = false;
        this.volume = 50;
        this.lastActivity = Date.now();

        this.init();
    }

    async init() {
        console.log('Initializing BoTTube Fire TV App...');

        // Set up UI event listeners
        this.setupEventListeners();

        // Load initial content
        await this.loadCategories();
        await this.loadTrendingVideos();

        // Initialize UI
        this.renderCategories();
        this.renderVideoGrid();
        this.setInitialFocus();

        // Start activity monitoring
        this.startActivityMonitor();

        console.log('BoTTube Fire TV App initialized');
    }

    setupEventListeners() {
        document.addEventListener('keydown', this.handleKeyPress.bind(this));
        document.addEventListener('webkitfullscreenchange', this.handleFullscreenChange.bind(this));

        // Handle video events
        document.addEventListener('videoended', this.handleVideoEnd.bind(this));
        document.addEventListener('videounavailable', this.handleVideoError.bind(this));
    }

    handleKeyPress(event) {
        this.lastActivity = Date.now();

        const key = event.keyCode || event.which;

        switch(key) {
            case 37: // Left arrow
                this.navigateLeft();
                break;
            case 38: // Up arrow
                this.navigateUp();
                break;
            case 39: // Right arrow
                this.navigateRight();
                break;
            case 40: // Down arrow
                this.navigateDown();
                break;
            case 13: // Enter/Select
                this.handleSelect();
                break;
            case 8: // Back button
            case 27: // Escape
                this.handleBack();
                break;
            case 179: // Play/Pause
                this.togglePlayback();
                break;
            case 227: // Fast forward
                this.fastForward();
                break;
            case 228: // Rewind
                this.rewind();
                break;
            default:
                console.log('Unhandled key:', key);
        }

        event.preventDefault();
    }

    async loadCategories() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/categories`);
            if (response.ok) {
                this.categories = await response.json();
            } else {
                // Fallback categories
                this.categories = [
                    { id: 'trending', name: 'Trending', icon: '🔥' },
                    { id: 'recent', name: 'Recent', icon: '🆕' },
                    { id: 'technology', name: 'Technology', icon: '💻' },
                    { id: 'entertainment', name: 'Entertainment', icon: '🎬' },
                    { id: 'music', name: 'Music', icon: '🎵' }
                ];
            }
        } catch (error) {
            console.error('Failed to load categories:', error);
            this.categories = [
                { id: 'trending', name: 'Trending', icon: '🔥' },
                { id: 'recent', name: 'Recent', icon: '🆕' }
            ];
        }
    }

    async loadTrendingVideos() {
        await this.loadVideosForCategory('trending');
    }

    async loadVideosForCategory(categoryId) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/videos?category=${categoryId}&limit=50`);
            if (response.ok) {
                this.videos = await response.json();
            } else {
                // Fallback mock data
                this.videos = this.generateMockVideos();
            }
            this.currentCategory = categoryId;
            this.currentVideoIndex = 0;
        } catch (error) {
            console.error('Failed to load videos:', error);
            this.videos = this.generateMockVideos();
        }
    }

    generateMockVideos() {
        return [
            {
                id: 'demo1',
                title: 'Welcome to BoTTube',
                description: 'Getting started with BoTTube on Fire TV',
                thumbnail: 'assets/thumb1.jpg',
                duration: '2:30',
                views: '1.2K',
                author: 'BoTTube Team'
            },
            {
                id: 'demo2',
                title: 'Fire TV Navigation Demo',
                description: 'How to navigate the BoTTube Fire TV interface',
                thumbnail: 'assets/thumb2.jpg',
                duration: '1:45',
                views: '890',
                author: 'BoTTube Team'
            }
        ];
    }

    renderCategories() {
        const categoriesContainer = document.getElementById('categories-row');
        if (!categoriesContainer) return;

        categoriesContainer.innerHTML = '';

        this.categories.forEach((category, index) => {
            const categoryElement = document.createElement('div');
            categoryElement.className = 'category-item focusable';
            categoryElement.dataset.categoryId = category.id;
            categoryElement.dataset.index = index;

            categoryElement.innerHTML = `
                <div class="category-icon">${category.icon}</div>
                <div class="category-name">${category.name}</div>
            `;

            categoriesContainer.appendChild(categoryElement);
        });
    }

    renderVideoGrid() {
        const videoGrid = document.getElementById('video-grid');
        if (!videoGrid) return;

        videoGrid.innerHTML = '';

        this.videos.forEach((video, index) => {
            const videoElement = document.createElement('div');
            videoElement.className = 'video-item focusable';
            videoElement.dataset.videoId = video.id;
            videoElement.dataset.index = index;

            videoElement.innerHTML = `
                <div class="video-thumbnail">
                    <img src="${video.thumbnail || 'assets/default-thumb.jpg'}" alt="${video.title}">
                    <div class="video-duration">${video.duration}</div>
                </div>
                <div class="video-info">
                    <h3 class="video-title">${video.title}</h3>
                    <p class="video-author">${video.author}</p>
                    <p class="video-views">${video.views} views</p>
                </div>
            `;

            videoGrid.appendChild(videoElement);
        });
    }

    setInitialFocus() {
        const firstFocusable = document.querySelector('.focusable');
        if (firstFocusable) {
            this.setFocus(firstFocusable);
        }
    }

    setFocus(element) {
        if (this.currentFocus) {
            this.currentFocus.classList.remove('focused');
        }

        this.currentFocus = element;
        element.classList.add('focused');
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    navigateLeft() {
        if (!this.currentFocus) return;

        const currentIndex = parseInt(this.currentFocus.dataset.index);
        const parent = this.currentFocus.parentElement;

        if (parent.id === 'categories-row') {
            const prevCategory = parent.children[currentIndex - 1];
            if (prevCategory) {
                this.setFocus(prevCategory);
            }
        } else if (parent.id === 'video-grid') {
            const cols = this.getGridColumns();
            if (currentIndex % cols > 0) {
                const leftVideo = parent.children[currentIndex - 1];
                if (leftVideo) {
                    this.setFocus(leftVideo);
                }
            }
        }
    }

    navigateRight() {
        if (!this.currentFocus) return;

        const currentIndex = parseInt(this.currentFocus.dataset.index);
        const parent = this.currentFocus.parentElement;

        if (parent.id === 'categories-row') {
            const nextCategory = parent.children[currentIndex + 1];
            if (nextCategory) {
                this.setFocus(nextCategory);
            }
        } else if (parent.id === 'video-grid') {
            const cols = this.getGridColumns();
            if (currentIndex % cols < cols - 1) {
                const rightVideo = parent.children[currentIndex + 1];
                if (rightVideo) {
                    this.setFocus(rightVideo);
                }
            }
        }
    }

    navigateUp() {
        if (!this.currentFocus) return;

        const parent = this.currentFocus.parentElement;

        if (parent.id === 'video-grid') {
            const currentIndex = parseInt(this.currentFocus.dataset.index);
            const cols = this.getGridColumns();

            if (currentIndex >= cols) {
                const upVideo = parent.children[currentIndex - cols];
                if (upVideo) {
                    this.setFocus(upVideo);
                }
            } else {
                // Move to categories
                const categories = document.getElementById('categories-row');
                const categoryToFocus = categories.querySelector(`[data-category-id="${this.currentCategory}"]`) || categories.firstElementChild;
                if (categoryToFocus) {
                    this.setFocus(categoryToFocus);
                }
            }
        }
    }

    navigateDown() {
        if (!this.currentFocus) return;

        const parent = this.currentFocus.parentElement;

        if (parent.id === 'categories-row') {
            // Move to video grid
            const videoGrid = document.getElementById('video-grid');
            const firstVideo = videoGrid.firstElementChild;
            if (firstVideo) {
                this.setFocus(firstVideo);
            }
        } else if (parent.id === 'video-grid') {
            const currentIndex = parseInt(this.currentFocus.dataset.index);
            const cols = this.getGridColumns();
            const downVideo = parent.children[currentIndex + cols];
            if (downVideo) {
                this.setFocus(downVideo);
            }
        }
    }

    getGridColumns() {
        const videoGrid = document.getElementById('video-grid');
        if (!videoGrid || !videoGrid.firstElementChild) return 4;

        const itemWidth = videoGrid.firstElementChild.offsetWidth;
        const gridWidth = videoGrid.offsetWidth;
        return Math.floor(gridWidth / itemWidth) || 4;
    }

    async handleSelect() {
        if (!this.currentFocus) return;

        const parent = this.currentFocus.parentElement;

        if (parent.id === 'categories-row') {
            const categoryId = this.currentFocus.dataset.categoryId;
            await this.selectCategory(categoryId);
        } else if (parent.id === 'video-grid') {
            const videoId = this.currentFocus.dataset.videoId;
            this.playVideo(videoId);
        }
    }

    async selectCategory(categoryId) {
        this.showLoadingIndicator();
        await this.loadVideosForCategory(categoryId);
        this.renderVideoGrid();
        this.hideLoadingIndicator();

        // Focus first video
        const videoGrid = document.getElementById('video-grid');
        const firstVideo = videoGrid.firstElementChild;
        if (firstVideo) {
            this.setFocus(firstVideo);
        }
    }

    async playVideo(videoId) {
        const video = this.videos.find(v => v.id === videoId);
        if (!video) return;

        this.navigationStack.push('video-grid');
        this.showVideoPlayer(video);
    }

    showVideoPlayer(video) {
        const playerContainer = document.getElementById('video-player');
        const videoElement = document.getElementById('main-video');
        const titleElement = document.getElementById('player-title');
        const descElement = document.getElementById('player-description');

        titleElement.textContent = video.title;
        descElement.textContent = video.description;

        // In a real implementation, this would load the actual video URL
        videoElement.src = `${this.apiBaseUrl}/videos/${video.id}/stream`;

        playerContainer.style.display = 'flex';
        document.body.classList.add('player-active');

        this.player = videoElement;
        this.isPlaying = true;

        videoElement.play().catch(error => {
            console.error('Video playback failed:', error);
            this.handleVideoError();
        });
    }

    hideVideoPlayer() {
        const playerContainer = document.getElementById('video-player');
        const videoElement = document.getElementById('main-video');

        if (this.player) {
            this.player.pause();
            this.player.src = '';
            this.player = null;
        }

        playerContainer.style.display = 'none';
        document.body.classList.remove('player-active');
        this.isPlaying = false;

        // Return focus to video grid
        const videoGrid = document.getElementById('video-grid');
        const focusTarget = videoGrid.children[this.currentVideoIndex] || videoGrid.firstElementChild;
        if (focusTarget) {
            this.setFocus(focusTarget);
        }
    }

    handleBack() {
        if (this.isPlaying) {
            this.hideVideoPlayer();
        } else if (this.navigationStack.length > 0) {
            this.navigationStack.pop();
            // Handle navigation history if needed
        }
    }

    togglePlayback() {
        if (!this.player) return;

        if (this.isPlaying) {
            this.player.pause();
            this.isPlaying = false;
        } else {
            this.player.play();
            this.isPlaying = true;
        }
    }

    fastForward() {
        if (!this.player) return;
        this.player.currentTime = Math.min(this.player.duration, this.player.currentTime + 30);
    }

    rewind() {
        if (!this.player) return;
        this.player.currentTime = Math.max(0, this.player.currentTime - 30);
    }

    handleVideoEnd() {
        // Auto-play next video or return to grid
        this.hideVideoPlayer();
    }

    handleVideoError() {
        console.error('Video playback error');
        this.showMessage('Unable to play video');
        setTimeout(() => {
            this.hideVideoPlayer();
        }, 2000);
    }

    handleFullscreenChange() {
        // Handle fullscreen state changes
        console.log('Fullscreen changed');
    }

    showLoadingIndicator() {
        const loader = document.getElementById('loading-indicator');
        if (loader) {
            loader.style.display = 'flex';
        }
    }

    hideLoadingIndicator() {
        const loader = document.getElementById('loading-indicator');
        if (loader) {
            loader.style.display = 'none';
        }
    }

    showMessage(text) {
        const messageElement = document.getElementById('message-overlay');
        if (messageElement) {
            messageElement.textContent = text;
            messageElement.style.display = 'flex';
            setTimeout(() => {
                messageElement.style.display = 'none';
            }, 3000);
        }
    }

    startActivityMonitor() {
        setInterval(() => {
            const now = Date.now();
            if (now - this.lastActivity > 30000) { // 30 seconds
                // Hide UI elements for lean-back experience
                document.body.classList.add('inactive');
            } else {
                document.body.classList.remove('inactive');
            }
        }, 5000);
    }
}

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.bottube = new BoTTubeFireTVApp();
});
