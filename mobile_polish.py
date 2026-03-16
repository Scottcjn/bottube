import re

# 1. Update base.html to add bottom tab bar and fix grid layout
with open("bottube_templates/base.html", "r") as f:
    base_html = f.read()

# Add bottom tab bar HTML before closing body
if '<nav class="mobile-bottom-nav">' not in base_html:
    mobile_nav = """
    <!-- Mobile Bottom Navigation -->
    <nav class="mobile-bottom-nav">
        <a href="{{ P }}/" class="mobile-nav-item">
            <span class="icon">&#127968;</span>
            <span class="label">Home</span>
        </a>
        <a href="{{ P }}/trending" class="mobile-nav-item">
            <span class="icon">&#128293;</span>
            <span class="label">Trending</span>
        </a>
        <a href="{{ P }}/agents" class="mobile-nav-item">
            <span class="icon">&#129302;</span>
            <span class="label">Agents</span>
        </a>
        <a href="{{ P }}/dashboard" class="mobile-nav-item">
            <span class="icon">&#128100;</span>
            <span class="label">Profile</span>
        </a>
    </nav>
</body>
"""
    base_html = base_html.replace('</body>', mobile_nav)

# Add CSS for bottom nav and touch targets
css_additions = """
        /* Mobile Bottom Nav */
        .mobile-bottom-nav {
            display: none;
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: var(--bg-secondary);
            border-top: 1px solid var(--border);
            padding-bottom: env(safe-area-inset-bottom, 0);
            z-index: 1000;
        }
        
        .mobile-nav-item {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 8px 0;
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 10px;
            min-height: 48px; /* Touch target */
        }
        
        .mobile-nav-item .icon { font-size: 20px; margin-bottom: 2px; }
        .mobile-nav-item:hover, .mobile-nav-item.active { color: var(--accent); }

        @media (max-width: 640px) {
            .mobile-bottom-nav { display: flex; }
            .footer { padding-bottom: 70px; } /* Add space for nav */
            .header-right { display: none !important; } /* Hide top nav links entirely */
            .main { padding-bottom: 80px; }
            
            /* Responsive Grid */
            .video-grid { grid-template-columns: 1fr !important; gap: 16px; }
            
            /* Touch targets */
            button, .btn-primary, .btn-secondary, select, input {
                min-height: 44px;
            }
        }
        
        @media (min-width: 641px) and (max-width: 1024px) {
            .video-grid { grid-template-columns: repeat(2, 1fr) !important; }
        }
        
        @media (min-width: 1025px) {
            .video-grid { grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
        }
"""
base_html = base_html.replace('</style>', f'{css_additions}\n    </style>')

with open("bottube_templates/base.html", "w") as f:
    f.write(base_html)

# 2. Update watch.html for sticky comment and video player full width
with open("bottube_templates/watch.html", "r") as f:
    watch_html = f.read()

watch_css = """
    /* Mobile Polish */
    @media (max-width: 640px) {
        .watch-layout { padding: 0; }
        .video-player { 
            width: 100vw; 
            margin-left: -12px; 
            margin-right: -12px;
            border-radius: 0; 
            aspect-ratio: 16 / 9;
        }
        
        .video-details { padding: 12px; }
        
        /* Sticky Comment Input */
        .comment-form {
            position: sticky;
            bottom: 60px; /* Above bottom nav */
            background: var(--bg-primary);
            z-index: 100;
            padding: 12px;
            border-top: 1px solid var(--border);
            box-shadow: 0 -4px 10px rgba(0,0,0,0.5);
            margin: 0 -12px;
        }
        
        .comment-form textarea {
            min-height: 44px; /* Touch target */
        }
        
        .action-buttons { flex-wrap: wrap; gap: 8px; }
        .action-btn { flex: 1; justify-content: center; }
        
        .channel-info-row { flex-direction: column; align-items: flex-start; gap: 12px; }
        .channel-row-right { width: 100%; }
        .watch-sub-btn { width: 100%; text-align: center; }
    }
"""
watch_html = watch_html.replace('</style>', f'{watch_css}\n    </style>')

with open("bottube_templates/watch.html", "w") as f:
    f.write(watch_html)

print("Applied mobile responsive polish.")
