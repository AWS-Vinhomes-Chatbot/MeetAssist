// ==================== THÊM DEMO MODE ====================
const DEMO_MODE = true;  // ✅ BẬT DEMO MODE (set = false khi deploy production)

// Mock demo data
const DEMO_DATA = {
    user: {
        email: 'demo@admin.com',
        sub: 'demo-user-123'
    },
    tokens: {
        id_token: 'demo-id-token',
        access_token: 'demo-access-token',
        refresh_token: 'demo-refresh-token'
    }
};

// ==================== COGNITO AUTHENTICATION ====================

class CognitoAuth {
    constructor() {
        this.config = window.APP_CONFIG;
        this.tokens = null;
        this.user = null;
    }

    isAuthenticated() {
        // ✅ DEMO MODE: Always return true
        if (DEMO_MODE) return true;
        
        const tokens = this.getTokensFromStorage();
        if (!tokens || !tokens.id_token) return false;
        
        const payload = this.parseJWT(tokens.id_token);
        const now = Math.floor(Date.now() / 1000);
        return payload.exp > now;
    }

    parseJWT(token) {
        // ✅ DEMO MODE: Return mock data
        if (DEMO_MODE) return DEMO_DATA.user;
        
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(
            atob(base64).split('').map(c => 
                '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)
            ).join('')
        );
        return JSON.parse(jsonPayload);
    }

    getTokensFromStorage() {
        // ✅ DEMO MODE: Return mock tokens
        if (DEMO_MODE) return DEMO_DATA.tokens;
        
        const tokens = localStorage.getItem('cognito_tokens');
        return tokens ? JSON.parse(tokens) : null;
    }

    saveTokensToStorage(tokens) {
        if (DEMO_MODE) return;
        
        localStorage.setItem('cognito_tokens', JSON.stringify(tokens));
        this.tokens = tokens;
        
        const payload = this.parseJWT(tokens.id_token);
        this.user = {
            email: payload.email,
            sub: payload.sub
        };
    }

    login() {
        // ✅ DEMO MODE: Show alert instead of redirect
        if (DEMO_MODE) {
            alert('DEMO MODE: Login is disabled. Set DEMO_MODE = false to enable Cognito authentication.');
            return;
        }
        
        const redirectUri = window.location.origin + '/callback';
        const cognitoLoginUrl = `https://${this.config.cognitoDomain}/login?` +
            `client_id=${this.config.userPoolClientId}&` +
            `response_type=code&` +
            `scope=openid+email+profile&` +
            `redirect_uri=${encodeURIComponent(redirectUri)}`;
        
        window.location.href = cognitoLoginUrl;
    }

    async handleCallback() {
        // ✅ DEMO MODE: Skip callback
        if (DEMO_MODE) return true;
        
        const urlParams = new URLSearchParams(window.location.search);
        const code = urlParams.get('code');
        
        if (!code) return false;

        try {
            const redirectUri = window.location.origin + '/callback';
            const tokenEndpoint = `https://${this.config.cognitoDomain}/oauth2/token`;
            
            const response = await fetch(tokenEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                body: new URLSearchParams({
                    grant_type: 'authorization_code',
                    client_id: this.config.userPoolClientId,
                    code: code,
                    redirect_uri: redirectUri
                })
            });

            if (!response.ok) {
                const error = await response.text();
                throw new Error(`Token exchange failed: ${error}`);
            }

            const tokens = await response.json();
            this.saveTokensToStorage(tokens);
            
            window.history.replaceState({}, document.title, '/');
            return true;
        } catch (error) {
            console.error('Callback error:', error);
            showError('Authentication failed: ' + error.message);
            return false;
        }
    }

    logout() {
        // ✅ DEMO MODE: Just reload page
        if (DEMO_MODE) {
            if (confirm('DEMO MODE: Reload page?')) {
                window.location.reload();
            }
            return;
        }
        
        localStorage.removeItem('cognito_tokens');
        const logoutUrl = `https://${this.config.cognitoDomain}/logout?` +
            `client_id=${this.config.userPoolClientId}&` +
            `logout_uri=${encodeURIComponent(window.location.origin)}`;
        window.location.href = logoutUrl;
    }

    getAccessToken() {
        // ✅ DEMO MODE: Return mock token
        if (DEMO_MODE) return DEMO_DATA.tokens.access_token;
        
        const tokens = this.getTokensFromStorage();
        return tokens ? tokens.access_token : null;
    }

    getUserInfo() {
        // ✅ DEMO MODE: Return mock user
        if (DEMO_MODE) return DEMO_DATA.user;
        
        const tokens = this.getTokensFromStorage();
        if (!tokens) return null;
        return this.parseJWT(tokens.id_token);
    }
}

// ==================== API CLIENT ====================

class AdminAPI {
    constructor(auth) {
        this.auth = auth;
        this.baseUrl = window.APP_CONFIG.apiEndpoint;
    }

    async request(endpoint, body) {
        // ✅ DEMO MODE: Return mock data
        if (DEMO_MODE) {
            return this.getMockData(endpoint, body);
        }
        
        const token = this.auth.getAccessToken();
        if (!token) throw new Error('Not authenticated');

        try {
            const response = await fetch(`${this.baseUrl}${endpoint}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify(body)
            });

            if (!response.ok) {
                const error = await response.text();
                throw new Error(`API error (${response.status}): ${error}`);
            }

            return await response.json();
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }

    // ✅ MOCK DATA FOR DEMO
    getMockData(endpoint, body) {
        console.log('DEMO MODE: Returning mock data for', endpoint, body);
        
        // Simulate API delay
        return new Promise((resolve) => {
            setTimeout(() => {
                if (body.action === 'get_conversations' || endpoint === '/admin') {
                    resolve({
                        columns: ['conversation_id', 'user_id', 'timestamp', 'query', 'status', 'execution_time_ms'],
                        data: [
                            {
                                conversation_id: 'conv_001',
                                user_id: 'user_123',
                                timestamp: '2025-11-19T10:30:00Z',
                                query: 'Đặt phòng ngày mai lúc 10h',
                                status: 'success',
                                execution_time_ms: 245
                            },
                            {
                                conversation_id: 'conv_002',
                                user_id: 'user_456',
                                timestamp: '2025-11-19T11:15:00Z',
                                query: 'Hủy booking ID 789',
                                status: 'success',
                                execution_time_ms: 189
                            },
                            {
                                conversation_id: 'conv_003',
                                user_id: 'user_789',
                                timestamp: '2025-11-19T12:00:00Z',
                                query: 'Xem danh sách phòng trống',
                                status: 'error',
                                execution_time_ms: 567
                            },
                            {
                                conversation_id: 'conv_004',
                                user_id: 'user_123',
                                timestamp: '2025-11-19T13:45:00Z',
                                query: 'Thay đổi thời gian booking',
                                status: 'success',
                                execution_time_ms: 312
                            },
                            {
                                conversation_id: 'conv_005',
                                user_id: 'user_456',
                                timestamp: '2025-11-19T14:20:00Z',
                                query: 'Kiểm tra lịch hẹn của tôi',
                                status: 'timeout',
                                execution_time_ms: 3000
                            }
                        ]
                    });
                } else if (body.action === 'get_analytics') {
                    resolve({
                        data: [
                            { date: '2025-11-13', total_queries: 45, unique_users: 12, success_rate: 0.89, avg_execution_time: 234 },
                            { date: '2025-11-14', total_queries: 52, unique_users: 15, success_rate: 0.92, avg_execution_time: 198 },
                            { date: '2025-11-15', total_queries: 38, unique_users: 10, success_rate: 0.87, avg_execution_time: 276 },
                            { date: '2025-11-16', total_queries: 61, unique_users: 18, success_rate: 0.94, avg_execution_time: 189 },
                            { date: '2025-11-17', total_queries: 48, unique_users: 13, success_rate: 0.90, avg_execution_time: 245 },
                            { date: '2025-11-18', total_queries: 55, unique_users: 16, success_rate: 0.91, avg_execution_time: 212 },
                            { date: '2025-11-19', total_queries: 67, unique_users: 20, success_rate: 0.93, avg_execution_time: 198 }
                        ]
                    });
                } else if (endpoint === '/crawler') {
                    resolve({
                        message: 'Crawler started successfully (DEMO)',
                        state: 'RUNNING'
                    });
                }
                
                resolve({ data: [] });
            }, 500); // Simulate 500ms API delay
        });
    }

    async getConversations(filters) {
        return await this.request('/admin', {
            action: 'get_conversations',
            filters: filters
        });
    }

    async getAnalytics(dateRange) {
        return await this.request('/admin', {
            action: 'get_analytics',
            date_range: dateRange
        });
    }

    async triggerCrawler() {
        return await this.request('/crawler', {});
    }
}

// ==================== GLOBAL INSTANCES ====================

const auth = new CognitoAuth();
const api = new AdminAPI(auth);
let charts = {};

// ==================== INITIALIZATION ====================

document.addEventListener('DOMContentLoaded', async () => {
    const loading = document.getElementById('loading');
    const loginScreen = document.getElementById('login-screen');
    const dashboard = document.getElementById('dashboard');

    // Handle OAuth callback
    if (window.location.search.includes('code=')) {
        const success = await auth.handleCallback();
        if (!success) {
            loading.style.display = 'none';
            loginScreen.style.display = 'flex';
            return;
        }
    }

    // Check authentication
    if (auth.isAuthenticated()) {
        loading.style.display = 'none';
        dashboard.style.display = 'block';
        initDashboard();
    } else {
        loading.style.display = 'none';
        loginScreen.style.display = 'flex';
    }
});

// ==================== EVENT LISTENERS ====================

document.getElementById('login-btn')?.addEventListener('click', () => {
    auth.login();
});

document.getElementById('logout-btn')?.addEventListener('click', () => {
    if (confirm('Are you sure you want to logout?')) {
        auth.logout();
    }
});

document.querySelectorAll('.close').forEach(btn => {
    btn.addEventListener('click', () => {
        document.getElementById('error-modal').style.display = 'none';
        document.getElementById('success-modal').style.display = 'none';
    });
});

// ==================== DASHBOARD INITIALIZATION ====================

function initDashboard() {
    const userInfo = auth.getUserInfo();
    if (userInfo) {
        document.getElementById('user-email').textContent = userInfo.email;
        document.getElementById('user-avatar').textContent = userInfo.email.charAt(0).toUpperCase();
    }

    // Tab switching
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tabName = item.dataset.tab;
            switchTab(tabName);
        });
    });

    // Conversations tab
    document.getElementById('apply-filters')?.addEventListener('click', loadConversations);
    document.getElementById('reset-filters')?.addEventListener('click', resetFilters);
    document.getElementById('export-csv')?.addEventListener('click', exportConversationsCSV);

    // Analytics tab
    document.getElementById('load-analytics')?.addEventListener('click', loadAnalytics);

    // Crawler tab
    document.getElementById('trigger-crawler')?.addEventListener('click', triggerCrawler);
    document.getElementById('check-crawler-status')?.addEventListener('click', checkCrawlerStatus);

    // Quick actions
    document.querySelectorAll('.action-card').forEach(card => {
        card.addEventListener('click', () => {
            const action = card.dataset.action;
            handleQuickAction(action);
        });
    });

    // Refresh button
    document.getElementById('refresh-btn')?.addEventListener('click', () => {
        loadOverviewData();
    });

    // Set default dates (last 7 days)
    const today = new Date().toISOString().split('T')[0];
    const lastWeek = new Date(Date.now() - 7*24*60*60*1000).toISOString().split('T')[0];
    
    if (document.getElementById('filter-start-date')) {
        document.getElementById('filter-start-date').value = lastWeek;
        document.getElementById('filter-end-date').value = today;
    }
    if (document.getElementById('analytics-start-date')) {
        document.getElementById('analytics-start-date').value = lastWeek;
        document.getElementById('analytics-end-date').value = today;
    }

    // Initialize charts
    initializeCharts();
    
    // Load overview data
    loadOverviewData();
}

// ==================== TAB SWITCHING ====================

function switchTab(tabName) {
    // Update nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.dataset.tab === tabName) {
            item.classList.add('active');
        }
    });

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`${tabName}-tab`).classList.add('active');

    // Update page title
    const titles = {
        overview: { title: 'Overview', subtitle: "Welcome back! Here's what's happening today." },
        conversations: { title: 'Conversations', subtitle: 'View and filter conversation history' },
        analytics: { title: 'Analytics', subtitle: 'Detailed insights and metrics' },
        crawler: { title: 'Data Sync', subtitle: 'Manage AWS Glue Crawler' }
    };
    
    if (titles[tabName]) {
        document.getElementById('page-title').textContent = titles[tabName].title;
        document.getElementById('page-subtitle').textContent = titles[tabName].subtitle;
    }
}

// ==================== OVERVIEW FUNCTIONS ====================

async function loadOverviewData() {
    showLoading('Loading overview data...');
    
    try {
        // Get last 7 days analytics
        const endDate = new Date().toISOString().split('T')[0];
        const startDate = new Date(Date.now() - 7*24*60*60*1000).toISOString().split('T')[0];
        
        const analytics = await api.getAnalytics({
            start_date: startDate,
            end_date: endDate
        });

        updateOverviewStats(analytics);
        updateTrendChart(analytics);
        hideLoading();
    } catch (error) {
        console.error('Failed to load overview:', error);
        showError('Failed to load overview data: ' + error.message);
        hideLoading();
    }
}

function updateOverviewStats(analytics) {
    if (!analytics.data || analytics.data.length === 0) return;

    const totalConvs = analytics.data.reduce((sum, row) => sum + parseInt(row.total_queries || 0), 0);
    const uniqueUsers = new Set(analytics.data.map(row => row.user_id)).size;
    const successRates = analytics.data.map(row => parseFloat(row.success_rate || 0));
    const avgSuccessRate = (successRates.reduce((a, b) => a + b, 0) / successRates.length * 100).toFixed(1);
    const avgTimes = analytics.data.map(row => parseFloat(row.avg_execution_time || 0));
    const avgTime = (avgTimes.reduce((a, b) => a + b, 0) / avgTimes.length).toFixed(0);

    document.getElementById('stat-total-convs').textContent = totalConvs.toLocaleString();
    document.getElementById('stat-success-rate').textContent = avgSuccessRate + '%';
    document.getElementById('stat-active-users').textContent = uniqueUsers;
    document.getElementById('stat-avg-time').textContent = avgTime + 'ms';
}

// ==================== CONVERSATIONS FUNCTIONS ====================

async function loadConversations() {
    const startDate = document.getElementById('filter-start-date').value;
    const endDate = document.getElementById('filter-end-date').value;
    const userId = document.getElementById('filter-user-id').value.trim();
    const status = document.getElementById('filter-status').value;

    if (!startDate || !endDate) {
        showError('Please select both start and end dates');
        return;
    }

    showLoading('Loading conversations...');

    try {
        const filters = { start_date: startDate, end_date: endDate };
        if (userId) filters.user_id = userId;
        if (status) filters.status = status;

        const result = await api.getConversations(filters);
        displayConversations(result);
        hideLoading();
    } catch (error) {
        console.error('Failed to load conversations:', error);
        showError('Failed to load conversations: ' + error.message);
        hideLoading();
    }
}

function displayConversations(result) {
    const container = document.getElementById('conversations-list');
    
    if (!result.data || result.data.length === 0) {
        container.innerHTML = '<p class="placeholder">No conversations found for the selected filters</p>';
        return;
    }

    let html = '<table><thead><tr>';
    result.columns.forEach(col => {
        html += `<th>${formatColumnName(col)}</th>`;
    });
    html += '<th>Actions</th></tr></thead><tbody>';

    result.data.forEach((row, idx) => {
        html += '<tr>';
        result.columns.forEach(col => {
            const value = row[col];
            if (col === 'status') {
                html += `<td><span class="status-badge status-${value}">${value}</span></td>`;
            } else if (col === 'timestamp') {
                html += `<td>${formatDate(value)}</td>`;
            } else if (col === 'execution_time_ms') {
                html += `<td>${value}ms</td>`;
            } else {
                html += `<td>${truncateText(value, 50)}</td>`;
            }
        });
        html += `<td>
            <button class="btn-icon btn-view" data-index="${idx}" title="View details">👁️</button>
        </td>`;
        html += '</tr>';
    });

    html += '</tbody></table>';
    container.innerHTML = html;

    // Add event listeners
    container.querySelectorAll('.btn-view').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = btn.dataset.index;
            showConversationDetails(result.data[idx]);
        });
    });
}

function resetFilters() {
    const today = new Date().toISOString().split('T')[0];
    const lastWeek = new Date(Date.now() - 7*24*60*60*1000).toISOString().split('T')[0];
    
    document.getElementById('filter-start-date').value = lastWeek;
    document.getElementById('filter-end-date').value = today;
    document.getElementById('filter-user-id').value = '';
    document.getElementById('filter-status').value = '';
    
    document.getElementById('conversations-list').innerHTML = '<p class="placeholder">Click "Apply Filters" to load conversations</p>';
}

function exportConversationsCSV() {
    showError('Export feature coming soon!');
}

// ==================== ANALYTICS FUNCTIONS ====================

async function loadAnalytics() {
    const startDate = document.getElementById('analytics-start-date').value;
    const endDate = document.getElementById('analytics-end-date').value;

    if (!startDate || !endDate) {
        showError('Please select both start and end dates');
        return;
    }

    showLoading('Loading analytics...');

    try {
        const result = await api.getAnalytics({
            start_date: startDate,
            end_date: endDate
        });
        displayAnalytics(result);
        hideLoading();
    } catch (error) {
        console.error('Failed to load analytics:', error);
        showError('Failed to load analytics: ' + error.message);
        hideLoading();
    }
}

function displayAnalytics(result) {
    if (!result.data || result.data.length === 0) {
        showError('No analytics data found for the selected date range');
        return;
    }

    // Update metrics
    const totalQueries = result.data.reduce((sum, row) => sum + parseInt(row.total_queries || 0), 0);
    const uniqueUsers = result.data.reduce((sum, row) => sum + parseInt(row.unique_users || 0), 0);
    const avgSuccessRate = (result.data.reduce((sum, row) => sum + parseFloat(row.success_rate || 0), 0) / result.data.length * 100).toFixed(1);
    const avgTime = (result.data.reduce((sum, row) => sum + parseFloat(row.avg_execution_time || 0), 0) / result.data.length).toFixed(0);

    document.getElementById('metric-total').textContent = totalQueries.toLocaleString();
    document.getElementById('metric-users').textContent = uniqueUsers.toLocaleString();
    document.getElementById('metric-success').textContent = avgSuccessRate + '%';
    document.getElementById('metric-time').textContent = avgTime + 'ms';

    // Update analytics chart
    updateAnalyticsChart(result.data);
}

// ==================== CRAWLER FUNCTIONS ====================

async function triggerCrawler() {
    const logBox = document.getElementById('crawler-log');
    addLogEntry('⏳ Starting AWS Glue Crawler...');
    
    document.getElementById('trigger-crawler').disabled = true;

    try {
        const result = await api.triggerCrawler();
        addLogEntry(`✅ ${result.message || 'Crawler started successfully'}`);
        
        if (result.state) {
            updateCrawlerState(result.state);
        }
        
        showSuccess('Crawler started successfully!');
    } catch (error) {
        console.error('Failed to trigger crawler:', error);
        addLogEntry(`❌ Error: ${error.message}`);
        showError('Failed to start crawler: ' + error.message);
    } finally {
        document.getElementById('trigger-crawler').disabled = false;
    }
}

async function checkCrawlerStatus() {
    addLogEntry('🔍 Checking crawler status...');
    
    try {
        // This would require a separate API endpoint
        showError('Status check feature coming soon!');
    } catch (error) {
        addLogEntry(`❌ Error: ${error.message}`);
    }
}

function updateCrawlerState(state) {
    const badge = document.getElementById('crawler-state');
    badge.textContent = state;
    badge.className = 'status-badge status-' + state.toLowerCase();
}

function addLogEntry(message) {
    const logBox = document.getElementById('crawler-log');
    const timestamp = new Date().toLocaleTimeString();
    const entry = document.createElement('p');
    entry.className = 'log-entry';
    entry.textContent = `[${timestamp}] ${message}`;
    logBox.appendChild(entry);
    logBox.scrollTop = logBox.scrollHeight;
}

// ==================== CHART FUNCTIONS ====================

function initializeCharts() {
    // Trend Chart
    const trendCtx = document.getElementById('trendChart')?.getContext('2d');
    if (trendCtx) {
        charts.trend = new Chart(trendCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Conversations',
                    data: [],
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99, 102, 241, 0.1)',
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, grid: { color: 'rgba(0, 0, 0, 0.05)' } },
                    x: { grid: { display: false } }
                }
            }
        });
    }

    // Status Chart
    const statusCtx = document.getElementById('statusChart')?.getContext('2d');
    if (statusCtx) {
        charts.status = new Chart(statusCtx, {
            type: 'doughnut',
            data: {
                labels: ['Success', 'Error', 'Timeout'],
                datasets: [{
                    data: [0, 0, 0],
                    backgroundColor: ['#10b981', '#ef4444', '#f59e0b'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { position: 'bottom', labels: { padding: 20, usePointStyle: true } }
                }
            }
        });
    }

    // Analytics Chart
    const analyticsCtx = document.getElementById('analyticsChart')?.getContext('2d');
    if (analyticsCtx) {
        charts.analytics = new Chart(analyticsCtx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Queries per Day',
                    data: [],
                    backgroundColor: '#6366f1'
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true }
                }
            }
        });
    }
}

function updateTrendChart(analytics) {
    if (!charts.trend || !analytics.data) return;
    
    const labels = analytics.data.map(row => formatDate(row.date));
    const data = analytics.data.map(row => parseInt(row.total_queries || 0));
    
    charts.trend.data.labels = labels;
    charts.trend.data.datasets[0].data = data;
    charts.trend.update();
}

function updateAnalyticsChart(data) {
    if (!charts.analytics) return;
    
    const labels = data.map(row => formatDate(row.date));
    const values = data.map(row => parseInt(row.total_queries || 0));
    
    charts.analytics.data.labels = labels;
    charts.analytics.data.datasets[0].data = values;
    charts.analytics.update();
}

// ==================== UTILITY FUNCTIONS ====================

function showLoading(message = 'Loading...') {
    // You could implement a loading overlay here
    console.log(message);
}

function hideLoading() {
    // Hide loading overlay
}

function showError(message) {
    const modal = document.getElementById('error-modal');
    document.getElementById('error-message').textContent = message;
    modal.style.display = 'block';
}

function showSuccess(message) {
    const modal = document.getElementById('success-modal');
    document.getElementById('success-message').textContent = message;
    modal.style.display = 'block';
}

function formatColumnName(col) {
    return col.split('_').map(word => 
        word.charAt(0).toUpperCase() + word.slice(1)
    ).join(' ');
}

function formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function truncateText(text, maxLength) {
    if (!text) return '-';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

function showConversationDetails(conversation) {
    // TODO: Implement details modal
    console.log('Conversation details:', conversation);
    showError('Details view coming soon!');
}

function handleQuickAction(action) {
    switch(action) {
        case 'view-latest':
            switchTab('conversations');
            document.getElementById('apply-filters')?.click();
            break;
        case 'sync-data':
            switchTab('crawler');
            break;
        case 'export-report':
            showError('Export feature coming soon!');
            break;
    }
}