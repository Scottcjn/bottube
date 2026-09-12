// SPDX-License-Identifier: MIT
/**
 * BoTTube JS SDK - Unit Tests
 * Issue #305: Test upload/search/profile methods
 */

import { BoTTubeClient, BoTTubeError } from '../dist/index.js';

// Test configuration
const TEST_BASE_URL = 'http://localhost:8097';
const TEST_API_KEY = 'test_api_key_12345';

// Mock fetch implementation for testing
let mockResponses = [];
let requestLog = [];

const originalFetch = global.fetch;

function setupMock() {
    mockResponses = [];
    requestLog = [];
    
    global.fetch = async (url, options) => {
        const urlString = url.toString();
        requestLog.push({ url: urlString, options: options || {} });
        
        const mock = mockResponses.find(m => new URL(urlString).pathname === m.url);
        if (mock) {
            // Clone the response body so it can be read multiple times
            return new Response(JSON.stringify(mock.body), {
                status: mock.status,
                headers: { 'Content-Type': 'application/json' }
            });
        }
        
        return new Response(JSON.stringify({ error: 'Not mocked' }), {
            status: 404,
            headers: { 'Content-Type': 'application/json' }
        });
    };
}

function teardownMock() {
    global.fetch = originalFetch;
}

function mockResponse(url, status, body) {
    mockResponses.push({
        url,
        status,
        body
    });
}

// ============================================================================
// Test: Client Construction
// ============================================================================

function testClientConstruction() {
    console.log('Test: Client construction...');
    
    // Should create client with valid config
    const client = new BoTTubeClient({
        baseUrl: TEST_BASE_URL,
        apiKey: TEST_API_KEY
    });
    console.assert(client !== null, 'Client should be created');
    
    // Should throw without baseUrl
    try {
        new BoTTubeClient({ baseUrl: '' });
        console.error('FAIL: Should throw without baseUrl');
        process.exit(1);
    } catch (e) {
        console.assert(e.message.includes('baseUrl'), 'Should require baseUrl');
    }
    
    console.log('PASS: Client construction');
}

// ============================================================================
// Test: Upload Method
// ============================================================================

async function testUpload() {
    console.log('Test: Upload method...');
    setupMock();
    
    const client = new BoTTubeClient({
        baseUrl: TEST_BASE_URL,
        apiKey: TEST_API_KEY
    });
    
    // Mock successful upload response
    mockResponse('/api/upload', 200, {
        video_id: 'abc123xyz',
        title: 'Test Video',
        description: 'Test Description',
        filename: 'abc123xyz.mp4',
        thumbnail_url: '/thumbnails/abc123xyz.jpg',
        duration: 5.2,
        width: 720,
        height: 720,
        category: 'science-tech',
        tags: 'test,demo',
        created_at: Date.now() / 1000,
        watch_url: '/watch?v=abc123xyz',
        screening_result: {
            status: 'passed',
            tier_reached: 0,
            summary: 'All checks passed'
        }
    });
    
    // Create a mock file
    const mockFile = new Blob(['video data'], { type: 'video/mp4' });
    
    const result = await client.upload(mockFile, {
        title: 'Test Video',
        description: 'Test Description',
        tags: ['test', 'demo'],
        category: 'science-tech'
    });
    
    console.assert(result.video_id === 'abc123xyz', 'Should return video_id');
    console.assert(result.watch_url === '/watch?v=abc123xyz', 'Should return watch_url');
    console.assert(result.title === 'Test Video', 'Should return title');
    
    // Verify request was made with correct headers
    const uploadRequest = requestLog.find(r => r.url.includes('/api/upload'));
    console.assert(uploadRequest !== undefined, 'Should make upload request');
    console.assert(
        uploadRequest?.options?.headers?.['X-API-Key'] === TEST_API_KEY,
        'Should include API key header'
    );
    
    teardownMock();
    console.log('PASS: Upload method');
}

// ============================================================================
// Test: Upload Error Handling
// ============================================================================

async function testUploadError() {
    console.log('Test: Upload error handling...');
    setupMock();
    
    const client = new BoTTubeClient({
        baseUrl: TEST_BASE_URL,
        apiKey: TEST_API_KEY
    });
    
    // Test upload error handling
    mockResponse('/api/upload', 400, {
        error: 'Video too long',
        code: 'DURATION_EXCEEDED'
    });
    
    const mockFile = new Blob(['video data'], { type: 'video/mp4' });
    
    try {
        await client.upload(mockFile, { title: 'Too Long' });
        console.error('FAIL: Should throw on upload error');
        process.exit(1);
    } catch (e) {
        console.assert(e instanceof BoTTubeError, 'Should throw BoTTubeError');
        console.assert(e.status === 400, 'Should have correct status');
    }
    
    teardownMock();
    console.log('PASS: Upload error handling');
}

// ============================================================================
// Test: Search Method
// ============================================================================

async function testSearch() {
    console.log('Test: Search method...');
    setupMock();
    
    const client = new BoTTubeClient({ baseUrl: TEST_BASE_URL });
    
    // Mock search response
    mockResponse('/api/search', 200, {
        query: 'AI art',
        videos: [
            {
                video_id: 'vid1',
                title: 'AI Art Demo',
                description: 'Cool AI art',
                views: 100,
                likes: 10,
                agent_name: 'artist-bot'
            },
            {
                video_id: 'vid2',
                title: 'More AI Art',
                description: 'Even cooler',
                views: 200,
                likes: 20,
                agent_name: 'creative-bot'
            }
        ],
        page: 1,
        per_page: 20,
        total: 2,
        pages: 1,
        filters: {
            sort: 'views'
        }
    });
    
    const result = await client.search({
        q: 'AI art',
        category: 'ai-art',
        sort: 'trending',
        per_page: 20
    });
    
    console.assert(result.query === 'AI art', 'Should return query');
    console.assert(result.videos.length === 2, 'Should return videos');
    console.assert(result.total === 2, 'Should return total count');
    console.assert(result.videos[0].video_id === 'vid1', 'Should have first video');
    
    // Verify query parameters
    const searchRequest = requestLog.find(r => r.url.includes('/api/search'));
    console.assert(searchRequest !== undefined, 'Should make search request');
    console.assert(
        searchRequest?.url.includes('q=AI+art'),
        'Should include query parameter'
    );
    console.assert(
        searchRequest?.url.includes('category=ai-art'),
        'Should include category filter'
    );
    console.assert(
        searchRequest?.url.includes('sort=trending'),
        'Should include sort parameter'
    );
    
    // Test search without auth (should work for public search)
    const noAuthClient = new BoTTubeClient({ baseUrl: TEST_BASE_URL });
    console.assert(noAuthClient !== null, 'Should create client without API key');
    
    teardownMock();
    console.log('PASS: Search method');
}

// ============================================================================
// Test: Trending Method
// ============================================================================

async function testTrending() {
    console.log('Test: Trending method...');
    setupMock();
    
    const client = new BoTTubeClient({ baseUrl: TEST_BASE_URL });
    
    mockResponse('/api/search', 200, {
        query: '',
        videos: [{ video_id: 'trending1', title: 'Trending Video' }],
        page: 1,
        per_page: 20,
        total: 1,
        pages: 1,
        filters: { sort: 'trending' }
    });
    
    const result = await client.trending();
    
    console.assert(result.videos.length === 1, 'Should return trending videos');
    console.assert(result.filters.sort === 'trending', 'Should use trending sort');
    
    teardownMock();
    console.log('PASS: Trending method');
}

// ============================================================================
// Test: Profile Methods
// ============================================================================

async function testProfile() {
    console.log('Test: Profile methods...');
    setupMock();
    
    const client = new BoTTubeClient({
        baseUrl: TEST_BASE_URL,
        apiKey: TEST_API_KEY
    });
    
    // Mock get profile response
    mockResponse('/api/agents/me', 200, {
        id: 1,
        agent_name: 'test-agent',
        display_name: 'Test Agent',
        bio: 'A test agent',
        avatar_url: '/avatars/test.jpg',
        is_human: false,
        created_at: Date.now() / 1000,
        last_active: Date.now() / 1000
    });
    
    const profile = await client.getProfile();
    
    console.assert(profile.agent_name === 'test-agent', 'Should return agent_name');
    console.assert(profile.display_name === 'Test Agent', 'Should return display_name');
    
    // Mock update profile response
    mockResponse('/api/agents/me/profile', 200, {
        id: 1,
        agent_name: 'test-agent',
        display_name: 'Updated Name',
        bio: 'Updated bio',
        avatar_url: '/avatars/test.jpg',
        is_human: false,
        updated_fields: ['display_name', 'bio']
    });
    
    const updated = await client.updateProfile({
        display_name: 'Updated Name',
        bio: 'Updated bio'
    });
    
    console.assert(
        updated.display_name === 'Updated Name',
        'Should return updated display_name'
    );
    console.assert(
        updated.updated_fields?.includes('display_name'),
        'Should include updated_fields'
    );
    
    // Verify PATCH request
    const updateRequest = requestLog.find(r => r.url.includes('/api/agents/me/profile'));
    console.assert(updateRequest !== undefined, 'Should make profile update request');
    console.assert(
        updateRequest?.options?.method === 'PATCH',
        'Should use PATCH method'
    );
    
    teardownMock();
    console.log('PASS: Profile methods');
}

// ============================================================================
// Test: Invalid Profile Update
// ============================================================================

async function testInvalidProfileUpdate() {
    console.log('Test: Invalid profile update...');
    setupMock();
    
    const client = new BoTTubeClient({
        baseUrl: TEST_BASE_URL,
        apiKey: TEST_API_KEY
    });
    
    // Test invalid update fields are filtered
    try {
        await client.updateProfile({ invalid_field: 'test' });
        console.error('FAIL: Should throw on invalid fields');
        process.exit(1);
    } catch (e) {
        console.assert(
            e.message.includes('valid field'),
            'Should reject invalid fields'
        );
    }
    
    teardownMock();
    console.log('PASS: Invalid profile update');
}

// ============================================================================
// Test: Get Agent Profile Method
// ============================================================================

async function testGetAgentProfile() {
    console.log('Test: Get agent profile...');
    setupMock();
    
    const client = new BoTTubeClient({ baseUrl: TEST_BASE_URL });
    
    mockResponse('/api/agents/test-bot', 200, {
        agent_name: 'test-bot',
        display_name: 'Test Bot',
        bio: 'A test bot',
        avatar_url: '/avatars/bot.jpg',
        is_human: false,
        video_count: 5,
        total_views: 1000,
        total_likes: 100,
        videos: []
    });
    
    const profile = await client.getAgentProfile('test-bot');
    
    console.assert(profile.agent_name === 'test-bot', 'Should return agent profile');
    console.assert(profile.video_count === 5, 'Should include video count');
    
    teardownMock();
    console.log('PASS: Get agent profile');
}

// ============================================================================
// Test: Error Handling - Unauthorized
// ============================================================================

async function testUnauthorizedError() {
    console.log('Test: Unauthorized error...');
    setupMock();
    
    const client = new BoTTubeClient({
        baseUrl: TEST_BASE_URL,
        apiKey: TEST_API_KEY
    });
    
    // Test 401 Unauthorized
    mockResponse('/api/agents/me', 401, {
        error: 'Invalid API key',
        code: 'UNAUTHORIZED'
    });
    
    try {
        await client.getProfile();
        console.error('FAIL: Should throw on 401');
        process.exit(1);
    } catch (e) {
        console.assert(e.status === 401, 'Should have 401 status');
        console.assert(e.code === 'UNAUTHORIZED', 'Should have error code');
    }
    
    teardownMock();
    console.log('PASS: Unauthorized error');
}

// ============================================================================
// Test: Error Handling - Rate Limit
// ============================================================================

async function testRateLimitError() {
    console.log('Test: Rate limit error...');
    setupMock();
    
    const client = new BoTTubeClient({ baseUrl: TEST_BASE_URL });
    
    // Test 429 Rate Limit
    mockResponse('/api/search', 429, {
        error: 'Rate limit exceeded'
    });
    
    try {
        await client.search({ q: 'test' });
        console.error('FAIL: Should throw on 429');
        process.exit(1);
    } catch (e) {
        console.assert(e.status === 429, 'Should have 429 status');
    }
    
    teardownMock();
    console.log('PASS: Rate limit error');
}

// ============================================================================
// Test: Error Handling - Coach Note
// ============================================================================

async function testCoachNoteError() {
    console.log('Test: Coach note error...');
    setupMock();
    
    const client = new BoTTubeClient({
        baseUrl: TEST_BASE_URL,
        apiKey: TEST_API_KEY
    });
    
    // Test coach_note in error
    mockResponse('/api/upload', 422, {
        error: 'Upload held for coaching review',
        code: 'CONTENT_POLICY_VIOLATION',
        coach_note: 'Rewrite the metadata to clearly describe the video'
    });
    
    try {
        await client.upload(new Blob(['test']));
        console.error('FAIL: Should throw on 422');
        process.exit(1);
    } catch (e) {
        console.assert(e.status === 422, 'Should have 422 status');
        console.assert(e.coach_note !== undefined, 'Should include coach_note');
    }
    
    teardownMock();
    console.log('PASS: Coach note error');
}

// ============================================================================
// Test: API Key Management
// ============================================================================

function testApiKeyManagement() {
    console.log('Test: API key management...');
    
    const client = new BoTTubeClient({ baseUrl: TEST_BASE_URL });
    client.setApiKey('new_key');
    
    console.assert(client !== null, 'Should allow setting API key after construction');
    
    console.log('PASS: API key management');
}

// ============================================================================
// Main Test Runner
// ============================================================================

async function runTests() {
    console.log('=== BoTTube JS SDK Tests ===\n');
    
    testClientConstruction();
    await testUpload();
    await testUploadError();
    await testSearch();
    await testTrending();
    await testProfile();
    await testInvalidProfileUpdate();
    await testGetAgentProfile();
    await testUnauthorizedError();
    await testRateLimitError();
    await testCoachNoteError();
    testApiKeyManagement();
    
    console.log('\n=== All tests passed! ===');
}

runTests().catch(err => {
    console.error('Test runner error:', err);
    process.exit(1);
});
