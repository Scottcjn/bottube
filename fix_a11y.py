import re

with open("bottube_templates/watch.html", "r") as f:
    html = f.read()

# Fix 1: Share Links & Buttons (Lines ~1854)
html = html.replace('title="Copy for Discord"', 'title="Copy for Discord" aria-label="Copy for Discord"')
html = html.replace('title="Copy link"', 'title="Copy link" aria-label="Copy link"')
html = html.replace('title="Get embed code"', 'title="Get embed code" aria-label="Get embed code"')

# Fix 2: Embed Code Panel Inputs (Lines ~1861)
html = html.replace('<input type="text" id="share-url"', '<label for="share-url" class="sr-only">Share link</label>\n                        <input type="text" id="share-url" aria-label="Share link"')
html = html.replace('<select id="embed-size"', '<label for="embed-size" class="sr-only">Embed size</label>\n                            <select id="embed-size" aria-label="Embed size"')
html = html.replace('<textarea id="embed-code"', '<label for="embed-code" class="sr-only">Embed code</label>\n                        <textarea id="embed-code" aria-label="Embed code"')
html = html.replace('onclick="copyEmbedCode()" style=', 'onclick="copyEmbedCode()" aria-label="Copy Embed Code" style=')

# Fix 3: Subscribe Button (Lines ~1928)
html = html.replace('id="watch-sub-btn" class="watch-sub-btn', 'id="watch-sub-btn" aria-label="Subscribe to {{ video.channel_name }}" class="watch-sub-btn')
html = html.replace('href="{{ P }}/login" class="watch-sub-btn', 'href="{{ P }}/login" aria-label="Subscribe to {{ video.channel_name }}" class="watch-sub-btn')

# Fix 4: Tip Buttons & Inputs (Lines ~1945)
html = html.replace('id="tip-toggle-btn"', 'id="tip-toggle-btn" aria-label="Toggle Tip Panel"')
html = html.replace('class="tip-btn" style="text-decoration:none;display:inline-flex;"', 'class="tip-btn" aria-label="Toggle Tip Panel" style="text-decoration:none;display:inline-flex;"')
html = html.replace('onclick="selectTipAmount(0.01)"', 'aria-label="Send 0.01 RTC tip" onclick="selectTipAmount(0.01)"')
html = html.replace('onclick="selectTipAmount(0.05)"', 'aria-label="Send 0.05 RTC tip" onclick="selectTipAmount(0.05)"')
html = html.replace('onclick="selectTipAmount(0.1)"', 'aria-label="Send 0.10 RTC tip" onclick="selectTipAmount(0.1)"')
html = html.replace('onclick="selectTipAmount(0.5)"', 'aria-label="Send 0.50 RTC tip" onclick="selectTipAmount(0.5)"')
html = html.replace('onclick="selectTipAmount(1.0)"', 'aria-label="Send 1.00 RTC tip" onclick="selectTipAmount(1.0)"')
html = html.replace('<input type="number" id="tip-amount"', '<label for="tip-amount" class="sr-only">Custom Tip Amount</label>\n                        <input type="number" id="tip-amount" aria-label="Custom Tip Amount"')
html = html.replace('<input type="text" class="tip-msg-input" id="tip-message"', '<label for="tip-message" class="sr-only">Tip Message</label>\n                    <input type="text" class="tip-msg-input" id="tip-message" aria-label="Tip Message"')
html = html.replace('id="send-tip-btn"', 'id="send-tip-btn" aria-label="Confirm Send Tip"')

# Fix 5: Comment Inputs & Buttons (Lines ~2084)
html = html.replace('<select id="comment-type"', '<label for="comment-type" class="sr-only">Comment type</label>\n                <select id="comment-type" aria-label="Comment type"')
html = html.replace('id="comment-btn" onclick="postComment()"', 'id="comment-btn" aria-label="Post comment" onclick="postComment()"')
html = html.replace('title="Like">&#9650;</button>', 'title="Like" aria-label="Upvote this comment">&#9650;</button>')
html = html.replace('title="Dislike">&#9660;</button>', 'title="Dislike" aria-label="Downvote this comment">&#9660;</button>')
html = html.replace('class="reply-btn" onclick="showReplyForm', 'class="reply-btn" aria-label="Reply to comment" onclick="showReplyForm')

with open("bottube_templates/watch.html", "w") as f:
    f.write(html)
