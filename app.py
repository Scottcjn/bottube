from flask import Flask, render_template

app = Flask(__name__)

# Existing routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/signup')
def signup():
    return render_template('signup.html')

@app.route('/upload')
def upload():
    return render_template('upload.html')

@app.route('/bridge/wrtc')
def wrtc():
    return render_template('wrtc.html')

@app.route('/agents')
def agents():
    return render_template('agents.html')

@app.route('/anchors')
def anchors():
    return render_template('anchors.html')

@app.route('/blog')
def blog():
    return render_template('blog.html')

# New routes to fix the issue
@app.route('/channel/1')
def channel_1():
    return render_template('channel_1.html')

@app.route('/subscriptions')
def subscriptions():
    return render_template('subscriptions.html')

@app.route('/playlists')
def playlists():
    return render_template('playlists.html')

@app.route('/history')
def history():
    return render_template('history.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

if __name__ == '__main__':
    app.run(debug=True)