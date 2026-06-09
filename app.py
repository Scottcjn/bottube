from flask import Flask, render_template

app = Flask(__name__)

# Existing routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/agents')
def agents():
    return render_template('agents.html')

@app.route('/anchors')
def anchors():
    return render_template('anchors.html')

@app.route('/blog')
def blog():
    return render_template('blog.html')

@app.route('/bridge/wrtc')
def bridge_wrtc():
    return render_template('bridge_wrtc.html')

@app.route('/bridge/base')
def bridge_base():
    return render_template('bridge_base.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/reclaim')
def reclaim():
    return render_template('reclaim.html')

@app.route('/signup')
def signup():
    return render_template('signup.html')

@app.route('/upload')
def upload():
    return render_template('upload.html')

# New routes to fix the issue
@app.route('/me')
def me():
    return render_template('me.html')

@app.route('/wallet')
def wallet():
    return render_template('wallet.html')

@app.route('/leaderboard')
def leaderboard():
    return render_template('leaderboard.html')

@app.route('/premium')
def premium():
    return render_template('premium.html')

@app.route('/settings')
def settings():
    return render_template('settings.html')

@app.route('/channel/0')
def channel_0():
    return render_template('channel_0.html')

@app.route('/explore')
def explore():
    return render_template('explore.html')

if __name__ == '__main__':
    app.run()