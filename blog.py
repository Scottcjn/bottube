from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort
from werkzeug.utils import secure_filename
import sqlite3
import datetime
import re

blog_bp = Blueprint('blog', __name__)

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect('bottube.db')
        g.db.row_factory = sqlite3.Row
    return g.db

def init_blog_db():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS blog_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            content TEXT NOT NULL,
            excerpt TEXT,
            author TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            published INTEGER DEFAULT 0,
            meta_title TEXT,
            meta_description TEXT,
            featured_image TEXT
        )
    ''')
    db.commit()

def create_slug(title):
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')

@blog_bp.route('/blog')
def blog_index():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    posts = db.execute('''
        SELECT id, title, slug, excerpt, author, created_at, featured_image
        FROM blog_posts
        WHERE published = 1
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    ''', (per_page, offset)).fetchall()

    total = db.execute('SELECT COUNT(*) FROM blog_posts WHERE published = 1').fetchone()[0]

    has_next = offset + per_page < total
    has_prev = page > 1

    return render_template('blog/index.html',
                         posts=posts,
                         page=page,
                         has_next=has_next,
                         has_prev=has_prev)

@blog_bp.route('/blog/<slug>')
def blog_post(slug):
    db = get_db()
    post = db.execute('''
        SELECT * FROM blog_posts
        WHERE slug = ? AND published = 1
    ''', (slug,)).fetchone()

    if not post:
        abort(404)

    # Get related posts
    related = db.execute('''
        SELECT id, title, slug, excerpt, created_at
        FROM blog_posts
        WHERE published = 1 AND id != ?
        ORDER BY created_at DESC
        LIMIT 3
    ''', (post['id'],)).fetchall()

    return render_template('blog/post.html', post=post, related=related)

@blog_bp.route('/admin/blog')
def admin_blog():
    if not g.user or g.user['role'] != 'admin':
        return redirect(url_for('auth.login'))

    db = get_db()
    posts = db.execute('''
        SELECT id, title, slug, author, created_at, published
        FROM blog_posts
        ORDER BY created_at DESC
    ''').fetchall()

    return render_template('blog/admin.html', posts=posts)

@blog_bp.route('/admin/blog/new', methods=['GET', 'POST'])
def admin_new_post():
    if not g.user or g.user['role'] != 'admin':
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        excerpt = request.form['excerpt']
        published = 1 if request.form.get('published') else 0
        meta_title = request.form.get('meta_title', title)
        meta_description = request.form.get('meta_description', excerpt)

        if not title or not content:
            flash('Title and content are required.')
            return render_template('blog/edit.html')

        slug = create_slug(title)
        db = get_db()

        # Check if slug exists
        existing = db.execute('SELECT id FROM blog_posts WHERE slug = ?', (slug,)).fetchone()
        if existing:
            counter = 1
            while existing:
                test_slug = f"{slug}-{counter}"
                existing = db.execute('SELECT id FROM blog_posts WHERE slug = ?', (test_slug,)).fetchone()
                counter += 1
            slug = test_slug

        try:
            db.execute('''
                INSERT INTO blog_posts
                (title, slug, content, excerpt, author, published, meta_title, meta_description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (title, slug, content, excerpt, g.user['username'], published, meta_title, meta_description))
            db.commit()
            flash('Post created successfully!')
            return redirect(url_for('blog.admin_blog'))
        except sqlite3.Error as e:
            flash(f'Error creating post: {e}')

    return render_template('blog/edit.html')

@blog_bp.route('/admin/blog/edit/<int:post_id>', methods=['GET', 'POST'])
def admin_edit_post(post_id):
    if not g.user or g.user['role'] != 'admin':
        return redirect(url_for('auth.login'))

    db = get_db()
    post = db.execute('SELECT * FROM blog_posts WHERE id = ?', (post_id,)).fetchone()

    if not post:
        abort(404)

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        excerpt = request.form['excerpt']
        published = 1 if request.form.get('published') else 0
        meta_title = request.form.get('meta_title', title)
        meta_description = request.form.get('meta_description', excerpt)

        if not title or not content:
            flash('Title and content are required.')
            return render_template('blog/edit.html', post=post)

        # Update slug if title changed
        new_slug = create_slug(title)
        if new_slug != post['slug']:
            existing = db.execute('SELECT id FROM blog_posts WHERE slug = ? AND id != ?', (new_slug, post_id)).fetchone()
            if existing:
                counter = 1
                while existing:
                    test_slug = f"{new_slug}-{counter}"
                    existing = db.execute('SELECT id FROM blog_posts WHERE slug = ? AND id != ?', (test_slug, post_id)).fetchone()
                    counter += 1
                new_slug = test_slug
        else:
            new_slug = post['slug']

        try:
            db.execute('''
                UPDATE blog_posts
                SET title = ?, slug = ?, content = ?, excerpt = ?,
                    published = ?, meta_title = ?, meta_description = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (title, new_slug, content, excerpt, published, meta_title, meta_description, post_id))
            db.commit()
            flash('Post updated successfully!')
            return redirect(url_for('blog.admin_blog'))
        except sqlite3.Error as e:
            flash(f'Error updating post: {e}')

    return render_template('blog/edit.html', post=post)

@blog_bp.route('/admin/blog/delete/<int:post_id>', methods=['POST'])
def admin_delete_post(post_id):
    if not g.user or g.user['role'] != 'admin':
        return redirect(url_for('auth.login'))

    db = get_db()
    try:
        db.execute('DELETE FROM blog_posts WHERE id = ?', (post_id,))
        db.commit()
        flash('Post deleted successfully!')
    except sqlite3.Error as e:
        flash(f'Error deleting post: {e}')

    return redirect(url_for('blog.admin_blog'))

@blog_bp.route('/api/blog/posts')
def api_blog_posts():
    db = get_db()
    posts = db.execute('''
        SELECT id, title, slug, excerpt, author, created_at
        FROM blog_posts
        WHERE published = 1
        ORDER BY created_at DESC
        LIMIT 20
    ''').fetchall()

    return {
        'posts': [dict(post) for post in posts],
        'count': len(posts)
    }
