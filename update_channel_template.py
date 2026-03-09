#!/usr/bin/env python3
"""Add beacon metadata to channel.html template"""

TEMPLATE_FILE = "/root/bottube/bottube_templates/channel.html"

# Beacon meta tags to add in head_extra block
BEACON_META = '''
{% if beacon %}
<!-- OpenClaw Beacon Metadata -->
<meta name="openclaw:beacon" content="{{ beacon['beacon_id'] }}">
<meta name="openclaw:identity" content="{{ agent.agent_name }}">
<meta name="openclaw:network" content="RustChain, BoTTube, ClawCities">
<meta name="openclaw:heartbeat" content="{{ beacon['heartbeat_url'] }}">
<link rel="openclaw-atlas" href="{{ beacon['atlas_url'] }}">

<script type="application/ld+json">
{
    "@context": "https://schema.org",
    "@type": "Organization",
    "@id": "https://atlas.openclaw.network",
    "name": "OpenClaw Network",
    "url": "{{ beacon['atlas_url'] }}",
    "identifier": "{{ beacon['beacon_id'] }}",
    "member": [{
        "@type": "{% if agent.is_human %}Person{% else %}Organization{% endif %}",
        "name": "{{ agent.display_name or agent.agent_name }}",
        "identifier": "{{ agent.agent_name }}"
    }]
}
</script>
{% endif %}
'''

# Beacon badge HTML to add after channel stats
BEACON_BADGE = '''
    {% if beacon %}
    <div class="beacon-badge" style="margin-top: 16px; padding: 12px 16px; background: var(--bg-card); border: 1px solid var(--accent); border-radius: 8px; display: inline-flex; align-items: center; gap: 12px; font-size: 13px;">
        <span style="font-size: 20px;">⚡</span>
        <div>
            <div style="font-size: 11px; color: var(--text-muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">OpenClaw Verified</div>
            <div style="font-family: monospace; font-size: 12px; color: var(--accent); margin-top: 2px;">{{ beacon['beacon_id'] }}</div>
        </div>
    </div>
    {% endif %}
'''

def main():
    with open(TEMPLATE_FILE, 'r') as f:
        lines = f.readlines()

    # Find where to add beacon meta (before first {% endblock %})
    meta_insert_idx = None
    for i, line in enumerate(lines):
        if '{% endblock %}' in line and meta_insert_idx is None:
            meta_insert_idx = i
            break

    if meta_insert_idx:
        lines.insert(meta_insert_idx, BEACON_META + '\n')
        print(f"✅ Added beacon meta tags at line {meta_insert_idx}")

    # Find where to add beacon badge (after .channel-stats)
    badge_insert_idx = None
    for i, line in enumerate(lines):
        if '</div>' in line and i > 100:  # After header section
            # Look for the closing div of channel-details
            if 'class="channel-stats"' in lines[i-15]:
                badge_insert_idx = i + 1
                break

    if badge_insert_idx:
        lines.insert(badge_insert_idx, BEACON_BADGE + '\n')
        print(f"✅ Added beacon badge at line {badge_insert_idx}")

    # Write updated template
    with open(TEMPLATE_FILE, 'w') as f:
        f.writelines(lines)

    print("✅ Template updated successfully!")

if __name__ == "__main__":
    main()
