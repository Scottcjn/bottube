class BoTTubeSDK {
    constructor(baseUrl = 'http://localhost:5000', apiKey = null) {
        this.baseUrl = baseUrl.replace(/\/$/, '');
        this.apiKey = apiKey;
        this.authToken = null;
    }

    async _makeRequest(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };

        if (this.authToken) {
            headers['Authorization'] = `Bearer ${this.authToken}`;
        } else if (this.apiKey) {
            headers['X-API-Key'] = this.apiKey;
        }

        const config = {
            method: 'GET',
            headers,
            ...options
        };

        try {
            const response = await fetch(url, config);

            if (!response.ok) {
                let errorMessage = `HTTP ${response.status}`;
                try {
                    const errorData = await response.json();
                    errorMessage = errorData.error || errorData.message || errorMessage;
                } catch (e) {
                    errorMessage = await response.text() || errorMessage;
                }
                throw new Error(errorMessage);
            }

            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            }

            return await response.text();
        } catch (error) {
            if (error instanceof TypeError && error.message.includes('fetch')) {
                throw new Error('Network error: Unable to connect to BoTTube API');
            }
            throw error;
        }
    }

    async authenticate(username, password) {
        try {
            const response = await this._makeRequest('/auth/login', {
                method: 'POST',
                body: JSON.stringify({ username, password })
            });

            if (response.token) {
                this.authToken = response.token;
                return { success: true, user: response.user };
            }

            throw new Error('Authentication failed');
        } catch (error) {
            throw new Error(`Authentication error: ${error.message}`);
        }
    }

    async uploadVideo(videoFile, metadata = {}) {
        if (!videoFile) {
            throw new Error('Video file is required');
        }

        const formData = new FormData();
        formData.append('video', videoFile);

        Object.keys(metadata).forEach(key => {
            if (metadata[key] !== undefined) {
                formData.append(key, metadata[key]);
            }
        });

        try {
            const response = await this._makeRequest('/api/videos/upload', {
                method: 'POST',
                headers: {
                    ...(this.authToken && { 'Authorization': `Bearer ${this.authToken}` }),
                    ...(this.apiKey && { 'X-API-Key': this.apiKey })
                },
                body: formData
            });

            return {
                success: true,
                videoId: response.video_id,
                message: response.message,
                video: response.video
            };
        } catch (error) {
            throw new Error(`Upload failed: ${error.message}`);
        }
    }

    async searchVideos(query, filters = {}) {
        const params = new URLSearchParams();

        if (query) {
            params.append('q', query);
        }

        Object.keys(filters).forEach(key => {
            if (filters[key] !== undefined && filters[key] !== null) {
                params.append(key, filters[key]);
            }
        });

        const queryString = params.toString();
        const endpoint = `/api/videos/search${queryString ? `?${queryString}` : ''}`;

        try {
            const response = await this._makeRequest(endpoint);
            return {
                success: true,
                videos: response.videos || [],
                total: response.total || 0,
                page: response.page || 1,
                totalPages: response.total_pages || 1
            };
        } catch (error) {
            throw new Error(`Search failed: ${error.message}`);
        }
    }

    async getVideo(videoId) {
        if (!videoId) {
            throw new Error('Video ID is required');
        }

        try {
            const response = await this._makeRequest(`/api/videos/${videoId}`);
            return {
                success: true,
                video: response.video || response
            };
        } catch (error) {
            throw new Error(`Failed to get video: ${error.message}`);
        }
    }

    async addComment(videoId, content, parentId = null) {
        if (!videoId || !content) {
            throw new Error('Video ID and comment content are required');
        }

        const payload = {
            content: content.trim(),
            ...(parentId && { parent_id: parentId })
        };

        try {
            const response = await this._makeRequest(`/api/videos/${videoId}/comments`, {
                method: 'POST',
                body: JSON.stringify(payload)
            });

            return {
                success: true,
                comment: response.comment,
                message: response.message
            };
        } catch (error) {
            throw new Error(`Comment failed: ${error.message}`);
        }
    }

    async getComments(videoId, page = 1, limit = 20) {
        if (!videoId) {
            throw new Error('Video ID is required');
        }

        const params = new URLSearchParams({
            page: page.toString(),
            limit: limit.toString()
        });

        try {
            const response = await this._makeRequest(`/api/videos/${videoId}/comments?${params}`);
            return {
                success: true,
                comments: response.comments || [],
                total: response.total || 0,
                page: response.page || 1,
                totalPages: response.total_pages || 1
            };
        } catch (error) {
            throw new Error(`Failed to get comments: ${error.message}`);
        }
    }

    async voteVideo(videoId, voteType) {
        if (!videoId || !['up', 'down'].includes(voteType)) {
            throw new Error('Video ID and valid vote type (up/down) are required');
        }

        try {
            const response = await this._makeRequest(`/api/videos/${videoId}/vote`, {
                method: 'POST',
                body: JSON.stringify({ vote: voteType })
            });

            return {
                success: true,
                message: response.message,
                upvotes: response.upvotes,
                downvotes: response.downvotes,
                userVote: response.user_vote
            };
        } catch (error) {
            throw new Error(`Vote failed: ${error.message}`);
        }
    }

    async getUserProfile(userId = null) {
        const endpoint = userId ? `/api/users/${userId}` : '/api/users/me';

        try {
            const response = await this._makeRequest(endpoint);
            return {
                success: true,
                user: response.user || response
            };
        } catch (error) {
            throw new Error(`Failed to get user profile: ${error.message}`);
        }
    }

    async getUserVideos(userId = null, page = 1, limit = 20) {
        const baseEndpoint = userId ? `/api/users/${userId}` : '/api/users/me';
        const params = new URLSearchParams({
            page: page.toString(),
            limit: limit.toString()
        });

        try {
            const response = await this._makeRequest(`${baseEndpoint}/videos?${params}`);
            return {
                success: true,
                videos: response.videos || [],
                total: response.total || 0,
                page: response.page || 1,
                totalPages: response.total_pages || 1
            };
        } catch (error) {
            throw new Error(`Failed to get user videos: ${error.message}`);
        }
    }

    async deleteVideo(videoId) {
        if (!videoId) {
            throw new Error('Video ID is required');
        }

        try {
            const response = await this._makeRequest(`/api/videos/${videoId}`, {
                method: 'DELETE'
            });

            return {
                success: true,
                message: response.message || 'Video deleted successfully'
            };
        } catch (error) {
            throw new Error(`Delete failed: ${error.message}`);
        }
    }

    logout() {
        this.authToken = null;
    }

    isAuthenticated() {
        return !!this.authToken;
    }
}

module.exports = BoTTubeSDK;
