// BoTTube Chrome Extension - Popup Script
// Handles UI interactions, API calls, and user preferences

let apiKey = '';
let currentUser = null;

// DOM elements
const loginSection = document.getElementById('loginSection');
const dashboardSection = document.getElementById('dashboard');
const apiKeyInput = document.getElementById('apiKey');
const loginBtn = document.getElementById('loginBtn');
const logoutBtn = document.getElementById('logoutBtn');
const userInfo = document.getElementById('userInfo');
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const videosContainer = document.getElementById('videosContainer');
const loadingSpinner = document.getElementById('loading');
const errorMsg = document.getElementById('errorMessage');
const refreshBtn = document.getElementById('refreshBtn');

// Initialize popup
document.addEventListener('DOMContentLoaded', async () => {
    await loadStoredCredentials();
    setupEventListeners();

    if (apiKey) {
        await authenticateAndLoadDashboard();
    }
});

// Event listeners
function setupEventListeners() {
    loginBtn.addEventListener('click', handleLogin);
    logoutBtn.addEventListener('click', handleLogout);
    searchBtn.addEventListener('click', handleSearch);
    refreshBtn.addEventListener('click', loadTrendingVideos);

    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            handleSearch();
        }
    });

    apiKeyInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            handleLogin();
        }
    });
}

// Load stored API key and user data
async function loadStoredCredentials() {
    const result = await chrome.storage.local.get(['apiKey', 'currentUser']);
    apiKey = result.apiKey || '';
    currentUser = result.currentUser || null;

    if (apiKey) {
        apiKeyInput.value = apiKey;
    }
}

// Handle login
async function handleLogin() {
    const inputKey = apiKeyInput.value.trim();

    if (!inputKey) {
        showError('Please enter your API key');
        return;
    }

    showLoading(true);

    try {
        const response = await fetch('https://bottube.ai/api/v1/auth/verify', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${inputKey}`
            }
        });

        if (response.ok) {
            const userData = await response.json();
            apiKey = inputKey;
            currentUser = userData;

            // Store credentials
            await chrome.storage.local.set({
                apiKey: apiKey,
                currentUser: currentUser
            });

            await authenticateAndLoadDashboard();
        } else {
            showError('Invalid API key');
        }
    } catch (error) {
        showError('Connection failed. Please try again.');
    } finally {
        showLoading(false);
    }
}

// Handle logout
async function handleLogout() {
    apiKey = '';
    currentUser = null;

    await chrome.storage.local.remove(['apiKey', 'currentUser']);

    loginSection.style.display = 'block';
    dashboardSection.style.display = 'none';
    apiKeyInput.value = '';
    videosContainer.innerHTML = '';
}

// Authenticate and show dashboard
async function authenticateAndLoadDashboard() {
    loginSection.style.display = 'none';
    dashboardSection.style.display = 'block';

    if (currentUser) {
        userInfo.textContent = `Welcome, ${currentUser.username || 'User'}!`;
    }

    await loadTrendingVideos();
}

// Load trending videos
async function loadTrendingVideos() {
    showLoading(true);
    clearError();

    try {
        const response = await fetch('https://bottube.ai/api/v1/videos/trending', {
            headers: {
                'Authorization': `Bearer ${apiKey}`
            }
        });

        if (response.ok) {
            const videos = await response.json();
            displayVideos(videos);
        } else {
            showError('Failed to load videos');
        }
    } catch (error) {
        showError('Network error. Please check your connection.');
    } finally {
        showLoading(false);
    }
}

// Handle search
async function handleSearch() {
    const query = searchInput.value.trim();

    if (!query) {
        await loadTrendingVideos();
        return;
    }

    showLoading(true);
    clearError();

    try {
        const response = await fetch(`https://bottube.ai/api/v1/videos/search?q=${encodeURIComponent(query)}`, {
            headers: {
                'Authorization': `Bearer ${apiKey}`
            }
        });

        if (response.ok) {
            const videos = await response.json();
            displayVideos(videos);
        } else {
            showError('Search failed');
        }
    } catch (error) {
        showError('Search failed. Please try again.');
    } finally {
        showLoading(false);
    }
}

// Display videos
function displayVideos(videos) {
    videosContainer.innerHTML = '';

    if (!videos || videos.length === 0) {
        videosContainer.innerHTML = '<div class="no-results">No videos found</div>';
        return;
    }

    videos.forEach(video => {
        const videoElement = createVideoElement(video);
        videosContainer.appendChild(videoElement);
    });
}

// Create video element
function createVideoElement(video) {
    const videoDiv = document.createElement('div');
    videoDiv.className = 'video-item';

    const title = video.title || 'Untitled';
    const author = video.author || 'Unknown';
    const views = formatViewCount(video.view_count || 0);
    const likes = video.likes || 0;
    const dislikes = video.dislikes || 0;
    const duration = formatDuration(video.duration || 0);

    videoDiv.innerHTML = `
        <div class="video-thumbnail">
            <img src="${video.thumbnail || '/static/default-thumb.png'}" alt="${title}">
            <span class="duration">${duration}</span>
        </div>
        <div class="video-info">
            <h3 class="video-title">${escapeHtml(title)}</h3>
            <p class="video-meta">${escapeHtml(author)} • ${views} views</p>
            <div class="video-actions">
                <button class="vote-btn like-btn" data-video-id="${video.id}" data-action="like">
                    👍 ${likes}
                </button>
                <button class="vote-btn dislike-btn" data-video-id="${video.id}" data-action="dislike">
                    👎 ${dislikes}
                </button>
                <button class="watch-btn" data-video-url="${video.url || '#'}">
                    Watch
                </button>
            </div>
        </div>
    `;

    // Add event listeners
    const likeBtn = videoDiv.querySelector('.like-btn');
    const dislikeBtn = videoDiv.querySelector('.dislike-btn');
    const watchBtn = videoDiv.querySelector('.watch-btn');

    likeBtn.addEventListener('click', () => handleVote(video.id, 'like', likeBtn));
    dislikeBtn.addEventListener('click', () => handleVote(video.id, 'dislike', dislikeBtn));
    watchBtn.addEventListener('click', () => openVideo(video.url || `https://bottube.ai/watch/${video.id}`));

    return videoDiv;
}

// Handle voting
async function handleVote(videoId, action, buttonElement) {
    const originalText = buttonElement.textContent;
    buttonElement.disabled = true;

    try {
        const response = await fetch(`https://bottube.ai/api/v1/videos/${videoId}/vote`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${apiKey}`
            },
            body: JSON.stringify({ action: action })
        });

        if (response.ok) {
            const result = await response.json();

            // Update button text with new count
            const emoji = action === 'like' ? '👍' : '👎';
            const count = result.likes || result.dislikes || 0;
            buttonElement.textContent = `${emoji} ${count}`;

            // Show success feedback
            buttonElement.classList.add('voted');
            setTimeout(() => {
                buttonElement.classList.remove('voted');
            }, 1000);

        } else {
            showError('Vote failed');
        }
    } catch (error) {
        showError('Network error');
        buttonElement.textContent = originalText;
    } finally {
        buttonElement.disabled = false;
    }
}

// Open video in new tab
function openVideo(url) {
    if (url && url !== '#') {
        chrome.tabs.create({ url: url });
    }
}

// Utility functions
function showLoading(show) {
    loadingSpinner.style.display = show ? 'block' : 'none';
}

function showError(message) {
    errorMsg.textContent = message;
    errorMsg.style.display = 'block';
    setTimeout(() => {
        errorMsg.style.display = 'none';
    }, 5000);
}

function clearError() {
    errorMsg.style.display = 'none';
}

function formatViewCount(count) {
    if (count >= 1000000) {
        return (count / 1000000).toFixed(1) + 'M';
    } else if (count >= 1000) {
        return (count / 1000).toFixed(1) + 'K';
    }
    return count.toString();
}

function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Check for notifications periodically
setInterval(async () => {
    if (apiKey) {
        try {
            const response = await fetch('https://bottube.ai/api/v1/notifications/count', {
                headers: {
                    'Authorization': `Bearer ${apiKey}`
                }
            });

            if (response.ok) {
                const data = await response.json();
                const count = data.count || 0;

                // Update badge
                const badgeText = count > 0 ? count.toString() : '';
                chrome.action.setBadgeText({ text: badgeText });
                chrome.action.setBadgeBackgroundColor({ color: '#FF4444' });
            }
        } catch (error) {
            // Silently fail for notifications
        }
    }
}, 30000); // Check every 30 seconds
