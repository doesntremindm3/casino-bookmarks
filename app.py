#!/usr/bin/env python3
import os
import sqlite3
import csv
import io
import re
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import requests
try:
    from openpyxl import Workbook, load_workbook
    XLSX_AVAILABLE = True
except ImportError:
    XLSX_AVAILABLE = False

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production-please')
CASINODATA_URL = os.environ.get('CASINODATA_URL', 'https://casinodata.dougshipe.com')

DB_PATH = '/data/bookmarks.db'
CASINODATA_DB = '/casinodata/casinodata.db'
ADMIN_SUBDOMAIN = os.environ.get('ADMIN_SUBDOMAIN', 'casinobookmarks')


def get_db():
    """Get database connection"""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def generate_pretty_name(url):
    """Generate a pretty, readable name from a URL"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        
        # Remove common prefixes
        domain = re.sub(r'^www\.', '', domain)
        
        # Get the main part (before TLD)
        parts = domain.split('.')
        if len(parts) > 1:
            main_part = parts[0]
        else:
            main_part = domain
        
        # Split on common separators and capitalize
        words = re.split(r'[-_]', main_part)
        
        # Capitalize each word
        pretty_words = []
        for word in words:
            if word:
                # Handle camelCase
                camel_split = re.sub(r'([a-z])([A-Z])', r'\1 \2', word)
                pretty_words.extend([w.capitalize() for w in camel_split.split()])
        
        pretty_name = ' '.join(pretty_words) if pretty_words else domain
        
        return pretty_name
    except:
        return url


def ensure_unique_name(db, base_name, exclude_id=None):
    """Ensure a name is unique in global_urls table"""
    name = base_name
    counter = 1
    
    while True:
        if exclude_id:
            existing = db.execute(
                'SELECT id FROM global_urls WHERE name = ? AND id != ?',
                (name, exclude_id)
            ).fetchone()
        else:
            existing = db.execute(
                'SELECT id FROM global_urls WHERE name = ?',
                (name,)
            ).fetchone()
        
        if not existing:
            return name
        
        counter += 1
        name = f"{base_name} ({counter})"


def init_db():
    """Initialize database with v8 schema"""
    db = get_db()
    
    # Create subdomains table (unchanged from v7)
    db.execute('''
        CREATE TABLE IF NOT EXISTS subdomains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create global URLs table (new in v8)
    db.execute('''
        CREATE TABLE IF NOT EXISTS global_urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create junction table linking subdomains to global URLs (new in v8)
    db.execute('''
        CREATE TABLE IF NOT EXISTS subdomain_urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subdomain_id INTEGER NOT NULL,
            global_url_id INTEGER NOT NULL,
            enabled INTEGER DEFAULT 0,
            display_order INTEGER NOT NULL,
            FOREIGN KEY (subdomain_id) REFERENCES subdomains (id) ON DELETE CASCADE,
            FOREIGN KEY (global_url_id) REFERENCES global_urls (id) ON DELETE CASCADE,
            UNIQUE(subdomain_id, global_url_id)
        )
    ''')
    
    # Create settings table (new in v8.1)
    db.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    # Set default batch size if not exists
    db.execute('''
        INSERT OR IGNORE INTO settings (key, value) VALUES ('batch_size', '10')
    ''')
    
    db.commit()
    
    # Check if we need to migrate from v7
    try:
        # Check if old urls table exists
        result = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='urls'").fetchone()
        if result:
            print("DEBUG: Found v7 'urls' table - checking if migration needed", flush=True)
            
            # Check if global_urls has any data
            global_count = db.execute('SELECT COUNT(*) as count FROM global_urls').fetchone()['count']
            
            if global_count == 0:
                print("DEBUG: Starting v7 to v8 migration...", flush=True)
                migrate_v7_to_v8(db)
    except Exception as e:
        print(f"DEBUG: Migration check/execution failed: {e}", flush=True)
    
    db.close()


def migrate_v7_to_v8(db):
    """Migrate v7 database structure to v8"""
    print("DEBUG: Migrating v7 to v8 schema...", flush=True)
    
    # Get all unique URLs from v7 urls table
    v7_urls = db.execute('SELECT DISTINCT url FROM urls ORDER BY url').fetchall()
    
    url_id_map = {}  # Maps v7 URL string to new global_url_id
    
    # Create global URLs with pretty names
    for row in v7_urls:
        url = row['url']
        pretty_name = generate_pretty_name(url)
        unique_name = ensure_unique_name(db, pretty_name)
        
        db.execute(
            'INSERT INTO global_urls (url, name) VALUES (?, ?)',
            (url, unique_name)
        )
        db.commit()
        
        # Get the new ID
        new_id = db.execute('SELECT id FROM global_urls WHERE url = ?', (url,)).fetchone()['id']
        url_id_map[url] = new_id
        
        print(f"DEBUG: Created global URL: {unique_name} -> {url}", flush=True)
    
    # Now create junction table entries from v7 urls
    v7_url_records = db.execute(
        'SELECT id, subdomain_id, url, display_order, enabled FROM urls ORDER BY subdomain_id, display_order'
    ).fetchall()
    
    for record in v7_url_records:
        global_url_id = url_id_map[record['url']]
        
        db.execute(
            '''INSERT INTO subdomain_urls (subdomain_id, global_url_id, enabled, display_order) 
               VALUES (?, ?, ?, ?)''',
            (record['subdomain_id'], global_url_id, record['enabled'], record['display_order'])
        )
    
    db.commit()
    
    # Rename old urls table to urls_v7_backup
    db.execute('ALTER TABLE urls RENAME TO urls_v7_backup')
    db.commit()
    
    print("DEBUG: v7 to v8 migration completed! Old 'urls' table renamed to 'urls_v7_backup'", flush=True)


def login_required(f):
    """Decorator to require login for admin routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def get_setting(key, default=None):
    """Get a setting value from database"""
    db = get_db()
    result = db.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    db.close()
    return result['value'] if result else default


def set_setting(key, value):
    """Set a setting value in database"""
    db = get_db()
    db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))

def get_casinodata_sites():
    """Fetch all sites from casinodata database"""
    try:
        conn = sqlite3.connect(CASINODATA_DB)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute('SELECT id, name, url FROM sites WHERE is_active = 1 ORDER BY name COLLATE NOCASE')
        sites = cur.fetchall()
        conn.close()
        return [dict(row) for row in sites]
    except Exception as e:
        print(f"Error reading casinodata: {e}")
        return []

    db.commit()
    db.close()


@app.route('/login', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page - authenticates via CasinoData"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please enter both username and password', 'error')
            return render_template('login.html')
        
        try:
            # Call casinodata API to authenticate
            response = requests.post(
                f"{CASINODATA_URL}/api/auth/login?app=casinobookmarks",
                json={
                    "username": username,
                    "password": password,
                    "remember_me": True
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                # Authentication successful
                data = response.json()
                session['logged_in'] = True
                session['username'] = username
                session['is_admin'] = (data.get('app_role') == 'admin')
                flash(f'Welcome back, {username}!', 'success')
                return redirect(url_for('admin'))
            
            elif response.status_code == 403:
                flash('You do not have access to Casino Bookmarks. Please contact an administrator.', 'error')
            
            elif response.status_code == 401:
                flash('Invalid username or password', 'error')
            
            else:
                flash('Authentication failed. Please try again.', 'error')
        
        except requests.RequestException as e:
            print(f"Error connecting to authentication service: {e}")
            flash('Could not connect to authentication service. Please try again later.', 'error')
        
        return render_template('login.html')
    
    # GET request - show login form
    if session.get('logged_in'):
        return redirect(url_for('admin'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout route"""
    session.pop('logged_in', None)
    flash('Successfully logged out', 'success')
    return redirect(url_for('login'))


@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Settings page"""
    if request.method == 'POST':
        batch_size = request.form.get('batch_size', '10')
        
        # Validate batch_size is a number
        try:
            batch_size_int = int(batch_size)
            if batch_size_int < 1:
                flash('Batch size must be at least 1', 'error')
            elif batch_size_int > 500:
                flash('Batch size cannot exceed 500', 'error')
            else:
                set_setting('batch_size', str(batch_size_int))
                flash(f'Settings saved! URLs will now open {batch_size_int} at a time.', 'success')
        except ValueError:
            flash('Batch size must be a number', 'error')
        
        return redirect(url_for('settings'))
    
    # GET request - show settings form
    batch_size = get_setting('batch_size', '10')
    return render_template('settings.html', batch_size=batch_size)


@app.route('/admin')
@login_required
def admin():
    """Admin dashboard - list all subdomains"""
    db = get_db()
    subdomains = db.execute('SELECT * FROM subdomains ORDER BY name').fetchall()
    
    # Get total URLs in global repository
    global_url_count = len(get_casinodata_sites())
    
    # Get URL count for each subdomain
    subdomain_list = []
    for sub in subdomains:
        # Total URLs associated with this subdomain
        url_count = db.execute(
            'SELECT COUNT(*) as count FROM subdomain_urls WHERE subdomain_id = ?',
            (sub['id'],)
        ).fetchone()['count']
        
        # Enabled URLs for this subdomain
        enabled_count = db.execute(
            'SELECT COUNT(*) as count FROM subdomain_urls WHERE subdomain_id = ? AND enabled = 1',
            (sub['id'],)
        ).fetchone()['count']
        
        subdomain_list.append({
            'id': sub['id'],
            'name': sub['name'],
            'created_at': sub['created_at'],
            'url_count': url_count,
            'enabled_count': enabled_count
        })
    
    db.close()
    return render_template('admin.html', subdomains=subdomain_list, global_url_count=global_url_count)


@app.route('/admin/subdomain/create', methods=['POST'])
@login_required
def create_subdomain():
    """Create a new subdomain"""
    name = request.form.get('name', '').strip().lower()
    
    # Validate subdomain name
    if not re.match(r'^[a-z0-9-]+$', name):
        flash('Subdomain name must contain only lowercase letters, numbers, and hyphens', 'error')
        return redirect(url_for('admin'))
    
    if name == ADMIN_SUBDOMAIN:
        flash('Cannot use reserved subdomain name', 'error')
        return redirect(url_for('admin'))
    
    db = get_db()
    try:
        db.execute('INSERT INTO subdomains (name) VALUES (?)', (name,))
        db.commit()
        flash(f'Subdomain "{name}" created successfully!', 'success')
    except sqlite3.IntegrityError:
        flash('Subdomain already exists', 'error')
    finally:
        db.close()
    
    return redirect(url_for('admin'))


@app.route('/admin/subdomain/<int:subdomain_id>/delete', methods=['POST'])
@login_required
def delete_subdomain(subdomain_id):
    """Delete a subdomain and all its URL associations"""
    db = get_db()
    subdomain = db.execute('SELECT name FROM subdomains WHERE id = ?', (subdomain_id,)).fetchone()
    if subdomain:
        db.execute('DELETE FROM subdomains WHERE id = ?', (subdomain_id,))
        db.commit()
        flash(f'Subdomain "{subdomain["name"]}" deleted successfully', 'success')
    db.close()
    return redirect(url_for('admin'))


@app.route('/admin/subdomain/<int:subdomain_id>')
@login_required
def edit_subdomain(subdomain_id):
    """Edit subdomain - manage URL associations using casinodata"""
    db = get_db()
    subdomain = db.execute('SELECT * FROM subdomains WHERE id = ?', (subdomain_id,)).fetchone()
    if not subdomain:
        flash('Subdomain not found', 'error')
        db.close()
        return redirect(url_for('admin'))
    
    # Get all sites from casinodata
    casinodata_sites = get_casinodata_sites()
    
    # Get enabled status for each site from subdomain_urls
    enabled_sites = {}
    rows = db.execute(
        'SELECT casinodata_site_id, enabled, display_order FROM subdomain_urls WHERE subdomain_id = ?',
        (subdomain_id,)
    ).fetchall()
    for row in rows:
        if row['casinodata_site_id']:
            enabled_sites[row['casinodata_site_id']] = {
                'enabled': row['enabled'],
                'display_order': row['display_order']
            }
    
    # Build URL list with enabled status
    urls = []
    for site in casinodata_sites:
        site_info = enabled_sites.get(site['id'], {'enabled': 0, 'display_order': 999999})
        urls.append({
            'casinodata_site_id': site['id'],
            'url': site['url'],
            'name': site['name'],
            'enabled': site_info['enabled'],
            'display_order': site_info['display_order']
        })
    
    # Count enabled URLs
    enabled_count = db.execute(
        'SELECT COUNT(*) as count FROM subdomain_urls WHERE subdomain_id = ? AND enabled = 1',
        (subdomain_id,)
    ).fetchone()['count']
    
    total_sites = len(casinodata_sites)
    db.close()
    
    return render_template('edit_subdomain.html',
                         subdomain=subdomain,
                         urls=urls,
                         enabled_count=enabled_count,
                         total_global_urls=total_sites)
@app.route('/admin/subdomain/<int:subdomain_id>/url/<int:site_id>/toggle', methods=['POST'])
@login_required
def toggle_url(subdomain_id, site_id):
    """Toggle URL enabled/disabled for a subdomain (uses casinodata_site_id)"""
    db = get_db()
    # Check if association exists
    existing = db.execute(
        'SELECT id, enabled FROM subdomain_urls WHERE subdomain_id = ? AND casinodata_site_id = ?',
        (subdomain_id, site_id)
    ).fetchone()
    
    if existing:
        # Toggle enabled state
        new_enabled = 0 if existing['enabled'] else 1
        db.execute(
            'UPDATE subdomain_urls SET enabled = ? WHERE id = ?',
            (new_enabled, existing['id'])
        )
    else:
        # Create new association (enabled by default, at end of list)
        max_order = db.execute(
            'SELECT COALESCE(MAX(display_order), -1) as max_order FROM subdomain_urls WHERE subdomain_id = ?',
            (subdomain_id,)
        ).fetchone()['max_order']
        db.execute(
            'INSERT INTO subdomain_urls (subdomain_id, casinodata_site_id, enabled, display_order) VALUES (?, ?, 1, ?)',
            (subdomain_id, site_id, max_order + 1)
        )
    
    db.commit()
    db.close()
    return redirect(url_for('edit_subdomain', subdomain_id=subdomain_id))

def move_url(subdomain_id, global_url_id, direction):
    """Move URL up or down in order"""
    db = get_db()
    
    current = db.execute(
        'SELECT id, display_order FROM subdomain_urls WHERE subdomain_id = ? AND global_url_id = ?',
        (subdomain_id, global_url_id)
    ).fetchone()
    
    if not current:
        db.close()
        return redirect(url_for('edit_subdomain', subdomain_id=subdomain_id))
    
    if direction == 'up':
        # Find the URL above this one
        swap_with = db.execute(
            'SELECT id, display_order FROM subdomain_urls WHERE subdomain_id = ? AND display_order < ? ORDER BY display_order DESC LIMIT 1',
            (subdomain_id, current['display_order'])
        ).fetchone()
    else:  # down
        # Find the URL below this one
        swap_with = db.execute(
            'SELECT id, display_order FROM subdomain_urls WHERE subdomain_id = ? AND display_order > ? ORDER BY display_order ASC LIMIT 1',
            (subdomain_id, current['display_order'])
        ).fetchone()
    
    if swap_with:
        # Swap display orders
        db.execute('UPDATE subdomain_urls SET display_order = ? WHERE id = ?', (swap_with['display_order'], current['id']))
        db.execute('UPDATE subdomain_urls SET display_order = ? WHERE id = ?', (current['display_order'], swap_with['id']))
        db.commit()
    
    db.close()
    return redirect(url_for('edit_subdomain', subdomain_id=subdomain_id))


@app.route('/admin/subdomain/<int:subdomain_id>/edit-name', methods=['GET', 'POST'])
@login_required
def edit_subdomain_name(subdomain_id):
    """Edit subdomain name"""
    db = get_db()
    subdomain = db.execute('SELECT * FROM subdomains WHERE id = ?', (subdomain_id,)).fetchone()
    
    if not subdomain:
        flash('Subdomain not found', 'error')
        db.close()
        return redirect(url_for('admin'))
    
    if request.method == 'POST':
        new_name = request.form.get('name', '').strip().lower()
        
        if not re.match(r'^[a-z0-9-]+$', new_name):
            flash('Subdomain name must contain only lowercase letters, numbers, and hyphens', 'error')
        elif new_name == ADMIN_SUBDOMAIN:
            flash('Cannot use reserved subdomain name', 'error')
        else:
            try:
                db.execute('UPDATE subdomains SET name = ? WHERE id = ?', (new_name, subdomain_id))
                db.commit()
                flash(f'Subdomain renamed to "{new_name}" successfully!', 'success')
                db.close()
                return redirect(url_for('admin'))
            except sqlite3.IntegrityError:
                flash('Subdomain name already exists', 'error')
    
    db.close()
    return render_template('edit_subdomain_name.html', subdomain=subdomain)


@app.route('/')
def index():
    """Main route - determine if admin or opener page"""
    host = request.headers.get('Host', '').lower()
    
    # Check if it's the admin subdomain
    if host == f'{ADMIN_SUBDOMAIN}.dougshipe.com':
        if session.get('logged_in'):
            return redirect(url_for('admin'))
        return redirect(url_for('login'))
    
    # Extract subdomain from format: subdomain.bookmarks.dougshipe.com
    if '.bookmarks.dougshipe.com' in host:
        subdomain = host.split('.bookmarks.dougshipe.com')[0].split('.')[-1]
        
        db = get_db()
        subdomain_record = db.execute(
            'SELECT id FROM subdomains WHERE name = ?',
            (subdomain,)
        ).fetchone()
        
        if subdomain_record:
            # Get enabled site IDs for this subdomain
            enabled_sites = db.execute('''
                SELECT casinodata_site_id, display_order
                FROM subdomain_urls
                WHERE subdomain_id = ? AND enabled = 1 AND casinodata_site_id IS NOT NULL
                ORDER BY display_order
            ''', (subdomain_record['id'],)).fetchall()
            db.close()
            
            # Get URLs from casinodata
            casinodata_sites = get_casinodata_sites()
            site_url_map = {site['id']: site['url'] for site in casinodata_sites}
            
            url_list = []
            for row in enabled_sites:
                site_id = row['casinodata_site_id']
                if site_id in site_url_map:
                    url_list.append(site_url_map[site_id])
            url_list = []
            for row in enabled_sites:
                site_id = row['casinodata_site_id']
                if site_id in site_url_map:
                    url_list.append(site_url_map[site_id])
                batch_size = int(get_setting('batch_size', '10'))
                return render_template('opener.html', subdomain=subdomain, urls=url_list, batch_size=batch_size)
            else:
                return render_template('no_urls.html', subdomain=subdomain)
        
        db.close()
        return render_template('subdomain_not_found.html', subdomain=subdomain)
    
    # Fallback
    return 'Bookmark Manager v8 - Access via subdomain.bookmarks.dougshipe.com or admin at casinobookmarkstest.dougshipe.com'


if __name__ == '__main__':
    # Initialize database
    init_db()
    # Run the app
    app.run(host='0.0.0.0', port=5000, debug=False)
