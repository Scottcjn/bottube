// Enhanced mobile menu functionality with accessibility support
function initMobileMenu() {
  const btn = document.getElementById('mobile-menu-btn');
  const menu = document.getElementById('mobile-menu');
  
  if (!btn || !menu) return;
  
  function toggleMenu() {
    const isExpanded = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', !isExpanded);
    menu.classList.toggle('active');
  }
  
  // Click handler
  btn.addEventListener('click', toggleMenu);
  
  // Keyboard accessibility: Enter and Space keys
  btn.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggleMenu();
    }
  });
}

// Enhanced notification functionality with accessibility support
function initNotifications() {
  const bellBtn = document.getElementById('bell-btn');
  const notificationPanel = document.getElementById('notification-panel');
  
  if (!bellBtn || !notificationPanel) return;
  
  function toggleNotifications() {
    const isExpanded = bellBtn.getAttribute('aria-expanded') === 'true';
    bellBtn.setAttribute('aria-expanded', !isExpanded);
    notificationPanel.classList.toggle('active');
  }
  
  // Click handler
  bellBtn.addEventListener('click', function(e) {
    e.preventDefault();
    toggleNotifications();
  });
  
  // Keyboard accessibility: Enter and Space keys
  bellBtn.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggleNotifications();
    }
  });
}

// Initialize accessibility features when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
  initMobileMenu();
  initNotifications();
});

// Existing base.js functionality (if any)
// Add other existing functions here...