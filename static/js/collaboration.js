class CollaborationDashboard {
    constructor() {
        this.currentUser = null;
        this.collaborations = [];
        this.statusUpdateInterval = null;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadCollaborations();
        this.setupRealTimeUpdates();
        this.initializeFormValidation();
    }

    setupEventListeners() {
        // Invitation response buttons
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('accept-invite-btn')) {
                this.handleInvitationResponse(e.target.dataset.inviteId, 'accept');
            } else if (e.target.classList.contains('decline-invite-btn')) {
                this.handleInvitationResponse(e.target.dataset.inviteId, 'decline');
            }
        });

        // Project update forms
        const updateForms = document.querySelectorAll('.project-update-form');
        updateForms.forEach(form => {
            form.addEventListener('submit', (e) => this.handleProjectUpdate(e));
        });

        // Revenue sharing calculator
        const revenueInputs = document.querySelectorAll('.revenue-share-input');
        revenueInputs.forEach(input => {
            input.addEventListener('input', () => this.calculateRevenueSharing());
        });

        // Create collaboration button
        const createBtn = document.getElementById('create-collab-btn');
        if (createBtn) {
            createBtn.addEventListener('click', () => this.showCreateCollaborationModal());
        }

        // Filter and sort controls
        const filterSelect = document.getElementById('collab-filter');
        if (filterSelect) {
            filterSelect.addEventListener('change', () => this.filterCollaborations());
        }

        const sortSelect = document.getElementById('collab-sort');
        if (sortSelect) {
            sortSelect.addEventListener('change', () => this.sortCollaborations());
        }
    }

    async loadCollaborations() {
        try {
            const response = await fetch('/api/collaborations', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            this.collaborations = data.collaborations || [];
            this.renderCollaborations();
            this.updateDashboardStats();
        } catch (error) {
            console.error('Failed to load collaborations:', error);
            this.showError('Failed to load collaboration data');
        }
    }

    async handleInvitationResponse(inviteId, action) {
        try {
            const button = document.querySelector(`[data-invite-id="${inviteId}"]`);
            const originalText = button.textContent;
            button.disabled = true;
            button.textContent = action === 'accept' ? 'Accepting...' : 'Declining...';

            const response = await fetch(`/api/collaborations/invites/${inviteId}/${action}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`Failed to ${action} invitation`);
            }

            const result = await response.json();

            if (result.success) {
                this.showSuccess(`Invitation ${action}ed successfully`);
                this.loadCollaborations(); // Refresh the list

                // Remove the invite card or update status
                const inviteCard = button.closest('.invite-card');
                if (inviteCard) {
                    inviteCard.style.opacity = '0.5';
                    setTimeout(() => inviteCard.remove(), 1000);
                }
            } else {
                throw new Error(result.error || 'Unknown error');
            }
        } catch (error) {
            console.error(`Error ${action}ing invitation:`, error);
            this.showError(`Failed to ${action} invitation: ${error.message}`);

            // Reset button
            const button = document.querySelector(`[data-invite-id="${inviteId}"]`);
            button.disabled = false;
            button.textContent = originalText;
        }
    }

    async handleProjectUpdate(event) {
        event.preventDefault();
        const form = event.target;
        const formData = new FormData(form);
        const collaborationId = form.dataset.collaborationId;

        try {
            const submitBtn = form.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.textContent = 'Updating...';

            const response = await fetch(`/api/collaborations/${collaborationId}/update`, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error('Failed to update project');
            }

            const result = await response.json();

            if (result.success) {
                this.showSuccess('Project updated successfully');
                this.loadCollaborations();
                form.reset();
            } else {
                throw new Error(result.error || 'Update failed');
            }
        } catch (error) {
            console.error('Project update error:', error);
            this.showError(`Update failed: ${error.message}`);
        } finally {
            const submitBtn = form.querySelector('button[type="submit"]');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Update Project';
        }
    }

    calculateRevenueSharing() {
        const totalRevenue = parseFloat(document.getElementById('total-revenue')?.value || 0);
        const shareInputs = document.querySelectorAll('.revenue-share-input');
        let totalShares = 0;

        // Calculate total shares
        shareInputs.forEach(input => {
            totalShares += parseFloat(input.value || 0);
        });

        if (totalShares > 100) {
            this.showError('Total revenue shares cannot exceed 100%');
            return;
        }

        // Update individual amounts
        shareInputs.forEach(input => {
            const sharePercent = parseFloat(input.value || 0);
            const amount = (totalRevenue * sharePercent) / 100;
            const amountDisplay = input.parentElement.querySelector('.share-amount');
            if (amountDisplay) {
                amountDisplay.textContent = `$${amount.toFixed(2)}`;
            }
        });

        // Update remaining percentage
        const remainingPercent = 100 - totalShares;
        const remainingDisplay = document.getElementById('remaining-percent');
        if (remainingDisplay) {
            remainingDisplay.textContent = `${remainingPercent.toFixed(1)}% remaining`;
            remainingDisplay.className = remainingPercent < 0 ? 'text-danger' : 'text-muted';
        }
    }

    setupRealTimeUpdates() {
        // Poll for status updates every 30 seconds
        this.statusUpdateInterval = setInterval(() => {
            this.updateCollaborationStatuses();
        }, 30000);
    }

    async updateCollaborationStatuses() {
        try {
            const response = await fetch('/api/collaborations/status', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (response.ok) {
                const data = await response.json();
                this.updateStatusIndicators(data.statuses || {});
            }
        } catch (error) {
            console.error('Status update failed:', error);
        }
    }

    updateStatusIndicators(statuses) {
        Object.entries(statuses).forEach(([collabId, status]) => {
            const statusElement = document.querySelector(`[data-collab-id="${collabId}"] .status-indicator`);
            if (statusElement) {
                statusElement.className = `status-indicator status-${status.toLowerCase()}`;
                statusElement.textContent = status;

                const lastUpdate = statusElement.parentElement.querySelector('.last-update');
                if (lastUpdate) {
                    lastUpdate.textContent = `Updated ${this.formatTimeAgo(status.updated_at)}`;
                }
            }
        });
    }

    initializeFormValidation() {
        const forms = document.querySelectorAll('.collaboration-form');
        forms.forEach(form => {
            this.addFormValidation(form);
        });
    }

    addFormValidation(form) {
        const inputs = form.querySelectorAll('input, textarea, select');

        inputs.forEach(input => {
            input.addEventListener('blur', () => this.validateField(input));
            input.addEventListener('input', () => this.clearFieldError(input));
        });

        form.addEventListener('submit', (e) => {
            if (!this.validateForm(form)) {
                e.preventDefault();
                this.showError('Please fix validation errors before submitting');
            }
        });
    }

    validateField(field) {
        const value = field.value.trim();
        let isValid = true;
        let errorMessage = '';

        // Required field validation
        if (field.hasAttribute('required') && !value) {
            isValid = false;
            errorMessage = 'This field is required';
        }

        // Email validation
        if (field.type === 'email' && value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
            isValid = false;
            errorMessage = 'Please enter a valid email address';
        }

        // Number validation
        if (field.type === 'number' && value) {
            const num = parseFloat(value);
            if (isNaN(num) || num < 0 || num > 100) {
                isValid = false;
                errorMessage = 'Please enter a valid percentage (0-100)';
            }
        }

        this.displayFieldValidation(field, isValid, errorMessage);
        return isValid;
    }

    validateForm(form) {
        const fields = form.querySelectorAll('input, textarea, select');
        let isFormValid = true;

        fields.forEach(field => {
            if (!this.validateField(field)) {
                isFormValid = false;
            }
        });

        return isFormValid;
    }

    displayFieldValidation(field, isValid, message) {
        const errorElement = field.parentElement.querySelector('.field-error');

        if (isValid) {
            field.classList.remove('is-invalid');
            field.classList.add('is-valid');
            if (errorElement) errorElement.remove();
        } else {
            field.classList.remove('is-valid');
            field.classList.add('is-invalid');

            if (!errorElement) {
                const error = document.createElement('div');
                error.className = 'field-error text-danger small mt-1';
                error.textContent = message;
                field.parentElement.appendChild(error);
            } else {
                errorElement.textContent = message;
            }
        }
    }

    clearFieldError(field) {
        field.classList.remove('is-invalid', 'is-valid');
        const errorElement = field.parentElement.querySelector('.field-error');
        if (errorElement) errorElement.remove();
    }

    renderCollaborations() {
        const container = document.getElementById('collaborations-container');
        if (!container) return;

        if (this.collaborations.length === 0) {
            container.innerHTML = `
                <div class="text-center py-5">
                    <i class="fas fa-users fa-3x text-muted mb-3"></i>
                    <h5>No collaborations yet</h5>
                    <p class="text-muted">Start collaborating with other creators!</p>
                    <button class="btn btn-primary" onclick="collaborationDashboard.showCreateCollaborationModal()">
                        Create Collaboration
                    </button>
                </div>
            `;
            return;
        }

        container.innerHTML = this.collaborations.map(collab => this.renderCollaborationCard(collab)).join('');
    }

    renderCollaborationCard(collab) {
        return `
            <div class="collaboration-card card mb-3" data-collab-id="${collab.id}">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h6 class="mb-0">${this.escapeHtml(collab.title)}</h6>
                    <span class="status-indicator status-${collab.status.toLowerCase()}">${collab.status}</span>
                </div>
                <div class="card-body">
                    <p class="card-text">${this.escapeHtml(collab.description)}</p>
                    <div class="row">
                        <div class="col-sm-6">
                            <small class="text-muted">Contributors:</small>
                            <div class="contributors">
                                ${collab.contributors.map(c => `
                                    <span class="badge bg-secondary me-1">${this.escapeHtml(c.name)}</span>
                                `).join('')}
                            </div>
                        </div>
                        <div class="col-sm-6 text-sm-end">
                            <small class="text-muted">Revenue Share:</small>
                            <div class="fw-bold">${collab.revenue_share}%</div>
                        </div>
                    </div>
                    <div class="mt-2">
                        <small class="text-muted last-update">Updated ${this.formatTimeAgo(collab.updated_at)}</small>
                    </div>
                </div>
                <div class="card-footer">
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-primary" onclick="collaborationDashboard.viewCollaboration('${collab.id}')">
                            View Details
                        </button>
                        <button class="btn btn-outline-secondary" onclick="collaborationDashboard.editCollaboration('${collab.id}')">
                            Edit
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    updateDashboardStats() {
        const stats = {
            total: this.collaborations.length,
            active: this.collaborations.filter(c => c.status === 'Active').length,
            pending: this.collaborations.filter(c => c.status === 'Pending').length,
            completed: this.collaborations.filter(c => c.status === 'Completed').length
        };

        Object.entries(stats).forEach(([key, value]) => {
            const element = document.getElementById(`stat-${key}`);
            if (element) element.textContent = value;
        });
    }

    filterCollaborations() {
        const filter = document.getElementById('collab-filter')?.value || 'all';
        let filtered = this.collaborations;

        if (filter !== 'all') {
            filtered = this.collaborations.filter(c => c.status.toLowerCase() === filter.toLowerCase());
        }

        this.renderFilteredCollaborations(filtered);
    }

    sortCollaborations() {
        const sortBy = document.getElementById('collab-sort')?.value || 'recent';
        let sorted = [...this.collaborations];

        switch (sortBy) {
            case 'title':
                sorted.sort((a, b) => a.title.localeCompare(b.title));
                break;
            case 'status':
                sorted.sort((a, b) => a.status.localeCompare(b.status));
                break;
            case 'recent':
            default:
                sorted.sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
                break;
        }

        this.collaborations = sorted;
        this.renderCollaborations();
    }

    showCreateCollaborationModal() {
        const modal = document.getElementById('createCollaborationModal');
        if (modal) {
            const bootstrapModal = new bootstrap.Modal(modal);
            bootstrapModal.show();
        }
    }

    formatTimeAgo(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;
        return date.toLocaleDateString();
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    showSuccess(message) {
        this.showAlert(message, 'success');
    }

    showError(message) {
        this.showAlert(message, 'danger');
    }

    showAlert(message, type) {
        const alertContainer = document.getElementById('alert-container') || document.body;
        const alert = document.createElement('div');
        alert.className = `alert alert-${type} alert-dismissible fade show`;
        alert.innerHTML = `
            ${this.escapeHtml(message)}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        alertContainer.appendChild(alert);

        setTimeout(() => {
            if (alert.parentNode) {
                alert.remove();
            }
        }, 5000);
    }

    destroy() {
        if (this.statusUpdateInterval) {
            clearInterval(this.statusUpdateInterval);
        }
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.collaborationDashboard = new CollaborationDashboard();
});
