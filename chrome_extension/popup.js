const API_BASE_URL = 'https://bottube.ai/api';

let userApiKey = null;
let currentPage = 1;
let isLoading = false;
let searchQuery = '';

document.addEventListener('DOMContentLoaded', function() {
    loadUserSettings();
    initializePopup();
    setupEventListeners();
});

function initializePopup() {
    showLoadingState();
    loadTrendingVideos();
}

function setupEventListeners() {
    const searchInput = document.getElementById('searchInput');
    const searchBtn = document.getElementById('searchBtn');
    const loadMoreBtn = document.getElementById('loadMoreBtn');
    const settingsBtn = document.getElementById('settingsBtn');
    const apiKeyInput = document.getElementById('apiKeyInput');
    const saveKeyBtn = document.getElementById('saveKeyBtn');

    searchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            performSearch();
        }
    });

    searchBtn.addEventListener('click', performSearch);
    loadMoreBtn.addEventListener('click', loadMoreVideos);
    settingsBtn.addEventListener('click', toggleSettings);
    saveKeyBtn.addEventListener('click', saveApiKey);

    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('vote-btn')) {
            handleVote(e);
        } else if (e.target.classList.contains('video-link')) {
            openVideo(e.target.dataset.videoId);
        }
    });
}

function loadUserSettings() {
    chrome.storage.sync.get(['bottubeApiKey'], function(result) {
        if (result.bottubeApiKey) {
            userApiKey = result.bottubeApiKey;
            document.getElementById('apiKeyInput').value = userApiKey;
        }
    });
}

async function loadTrendingVideos() {
    try {
        const response = await fetch(`${API_BASE_URL}/videos/trending?page=1&limit=10`);
        const data = await response.json();

        if (data.success) {
            displayVideos(data.videos, true);
            currentPage = 1;
            searchQuery = '';
        } else {
            showErrorMessage('Failed to load trending videos');
        }
    } catch (error) {
        showErrorMessage('Network error loading videos');
    } finally {
        hideLoadingState();
    }
}

async function performSearch() {
    const query = document.getElementById('searchInput').value.trim();
    if (!query) return;

    searchQuery = query;
    currentPage = 1;
    showLoadingState();

    try {
        const response = await fetch(`${API_BASE_URL}/videos/search?q=${encodeURIComponent(query)}&page=1&limit=10`);
        const data = await response.json();

        if (data.success) {
            displayVideos(data.videos, true);
        } else {
            showErrorMessage('Search failed');
        }
    } catch (error) {
        showErrorMessage('Search error occurred');
    } finally {
        hideLoadingState();
    }
}

async function loadMoreVideos() {
    if (isLoading) return;

    isLoading = true;
    const loadMoreBtn = document.getElementById('loadMoreBtn');
    loadMoreBtn.textContent = 'Loading...';
    loadMoreBtn.disabled = true;

    try {
        const endpoint = searchQuery ?
            `${API_BASE_URL}/videos/search?q=${encodeURIComponent(searchQuery)}&page=${currentPage + 1}&limit=10` :
            `${API_BASE_URL}/videos/trending?page=${currentPage + 1}&limit=10`;

        const response = await fetch(endpoint);
        const data = await response.json();

        if (data.success && data.videos.length > 0) {
            displayVideos(data.videos, false);
            currentPage++;
        } else {
            loadMoreBtn.style.display = 'none';
        }
    } catch (error) {
        showErrorMessage('Error loading more videos');
    } finally {
        isLoading = false;
        loadMoreBtn.textContent = 'Load More';
        loadMoreBtn.disabled = false;
    }
}

function displayVideos(videos, clearExisting = false) {
    const container = document.getElementById('videoContainer');

    if (clearExisting) {
        container.innerHTML = '';
    }

    if (!videos || videos.length === 0) {
        if (clearExisting) {
            container.innerHTML = '<div class="no-results">No videos found</div>';
        }
        return;
    }

    videos.forEach(video => {
        const videoElement = createVideoElement(video);
        container.appendChild(videoElement);
    });

    const loadMoreBtn = document.getElementById('loadMoreBtn');
    if (videos.length === 10) {
        loadMoreBtn.style.display = 'block';
    } else {
        loadMoreBtn.style.display = 'none';
    }
}

function createVideoElement(video) {
    const div = document.createElement('div');
    div.className = 'video-item';

    const thumbnail = video.thumbnail_url || 'https://via.placeholder.com/120x68?text=Video';
    const title = video.title || 'Untitled Video';
    const author = video.author || 'Unknown';
    const views = formatViewCount(video.view_count || 0);
    const likes = video.like_count || 0;
    const dislikes = video.dislike_count || 0;

    div.innerHTML = `
        <div class="video-thumbnail">
            <img src="${thumbnail}" alt="${title}" onerror="this.src='https://via.placeholder.com/120x68?text=Video'">
        </div>
        <div class="video-info">
            <h3 class="video-title">
                <a href="#" class="video-link" data-video-id="${video.id}">${title}</a>
            </h3>
            <div class="video-meta">
                <span class="video-author">${author}</span>
                <span class="video-views">${views} views</span>
            </div>
            <div class="video-actions">
                <button class="vote-btn like-btn" data-video-id="${video.id}" data-vote="like">
                    👍 ${likes}
                </button>
                <button class="vote-btn dislike-btn" data-video-id="${video.id}" data-vote="dislike">
                    👎 ${dislikes}
                </button>
            </div>
        </div>
    `;

    return div;
}

async function handleVote(event) {
    const videoId = event.target.dataset.videoId;
    const voteType = event.target.dataset.vote;

    if (!userApiKey) {
        showNotification('Please set your API key in settings', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/videos/${videoId}/vote`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${userApiKey}`
            },
            body: JSON.stringify({ vote: voteType })
        });

        const data = await response.json();

        if (data.success) {
            updateVoteDisplay(videoId, voteType, data.counts);
            showNotification(`Vote ${voteType} recorded!`, 'success');
        } else {
            showNotification('Vote failed: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        showNotification('Network error while voting', 'error');
    }
}

function updateVoteDisplay(videoId, voteType, counts) {
    const videoItem = document.querySelector(`[data-video-id="${videoId}"]`).closest('.video-item');
    const likeBtn = videoItem.querySelector('.like-btn');
    const dislikeBtn = videoItem.querySelector('.dislike-btn');

    if (counts) {
        likeBtn.textContent = `👍 ${counts.likes || 0}`;
        dislikeBtn.textContent = `👎 ${counts.dislikes || 0}`;
    }

    // Visual feedback for the vote
    const clickedBtn = voteType === 'like' ? likeBtn : dislikeBtn;
    clickedBtn.classList.add('voted');
    setTimeout(() => clickedBtn.classList.remove('voted'), 1000);
}

function openVideo(videoId) {
    chrome.tabs.create({ url: `https://bottube.ai/watch/${videoId}` });
    window.close();
}

function toggleSettings() {
    const settingsPanel = document.getElementById('settingsPanel');
    const mainContent = document.getElementById('mainContent');

    if (settingsPanel.style.display === 'none' || !settingsPanel.style.display) {
        settingsPanel.style.display = 'block';
        mainContent.style.display = 'none';
    } else {
        settingsPanel.style.display = 'none';
        mainContent.style.display = 'block';
    }
}

function saveApiKey() {
    const apiKey = document.getElementById('apiKeyInput').value.trim();

    if (!apiKey) {
        showNotification('Please enter a valid API key', 'error');
        return;
    }

    userApiKey = apiKey;
    chrome.storage.sync.set({ bottubeApiKey: apiKey }, function() {
        showNotification('API key saved successfully!', 'success');
        toggleSettings();
    });
}

function showLoadingState() {
    const container = document.getElementById('videoContainer');
    container.innerHTML = '<div class="loading">Loading videos...</div>';
}

function hideLoadingState() {
    const loadingEl = document.querySelector('.loading');
    if (loadingEl) {
        loadingEl.remove();
    }
}

function showErrorMessage(message) {
    const container = document.getElementById('videoContainer');
    container.innerHTML = `<div class="error-message">${message}</div>`;
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.classList.add('show');
    }, 100);

    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

function formatViewCount(count) {
    if (count >= 1000000) {
        return Math.floor(count / 1000000) + 'M';
    } else if (count >= 1000) {
        return Math.floor(count / 1000) + 'K';
    }
    return count.toString();
}

// Badge update functionality
function updateBadge() {
    chrome.action.getBadgeText({}, function(result) {
        if (!result) {
            checkForNewVideos();
        }
    });
}

async function checkForNewVideos() {
    try {
        const response = await fetch(`${API_BASE_URL}/videos/recent?limit=5`);
        const data = await response.json();

        if (data.success && data.videos.length > 0) {
            chrome.storage.local.get(['lastCheckTime'], function(result) {
                const lastCheck = result.lastCheckTime || 0;
                const newVideos = data.videos.filter(v =>
                    new Date(v.created_at).getTime() > lastCheck
                );

                if (newVideos.length > 0) {
                    chrome.action.setBadgeText({ text: newVideos.length.toString() });
                    chrome.action.setBadgeBackgroundColor({ color: '#ff6b6b' });
                }

                chrome.storage.local.set({ lastCheckTime: Date.now() });
            });
        }
    } catch (error) {
        console.log('Error checking for new videos:', error);
    }
}

// Clear badge when popup opens
chrome.action.setBadgeText({ text: '' });
