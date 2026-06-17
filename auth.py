import bcrypt, secrets, json
from functools import wraps
from flask import request, jsonify, session
from database import get_db

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Sesión requerida'}), 401
        return f(*args, **kwargs)
    return decorated

def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    db = get_db()
    return db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()

def register_auth_routes(app):

    @app.route('/api/auth/register', methods=['POST'])
    def register():
        db = get_db()
        body = request.get_json()
        username = body.get('username','').strip().lower()
        display_name = body.get('display_name','').strip()
        password = body.get('password','')
        api_key = body.get('api_key','').strip()
        email = body.get('email','').strip().lower()

        if not username or not password or not display_name:
            return jsonify({'error': 'Faltan datos'}), 400
        if len(password) < 6:
            return jsonify({'error': 'La contraseña debe tener al menos 6 caracteres'}), 400

        count = db.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']
        if count >= 5:
            return jsonify({'error': 'Límite de 5 usuarios alcanzado'}), 403

        if db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
            return jsonify({'error': 'Ese nombre de usuario ya existe'}), 409

        is_admin = 1 if count == 0 else 0
        pw_hash = hash_password(password)
        cur = db.execute(
            'INSERT INTO users (username, display_name, password_hash, is_admin, api_key_enc, email) VALUES (?,?,?,?,?,?)',
            (username, display_name, pw_hash, is_admin, api_key, email)
        )
        db.execute('INSERT INTO user_profiles (user_id) VALUES (?)', (cur.lastrowid,))
        db.commit()

        session['user_id'] = cur.lastrowid
        session['username'] = username
        return jsonify({'ok': True, 'user_id': cur.lastrowid, 'is_admin': bool(is_admin), 'display_name': display_name})

    @app.route('/api/auth/login', methods=['POST'])
    def login():
        db = get_db()
        body = request.get_json()
        username = body.get('username','').strip().lower()
        password = body.get('password','')

        user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if not user or not check_password(password, user['password_hash']):
            return jsonify({'error': 'Usuario o contraseña incorrectos'}), 401

        session['user_id'] = user['id']
        session['username'] = user['username']

        profile = db.execute('SELECT * FROM user_profiles WHERE user_id=?', (user['id'],)).fetchone()
        onboarding_done = profile['onboarding_done'] if profile else 0

        return jsonify({
            'ok': True,
            'user_id': user['id'],
            'username': user['username'],
            'display_name': user['display_name'],
            'is_admin': bool(user['is_admin']),
            'api_key': user['api_key_enc'] or '',
            'onboarding_done': bool(onboarding_done)
        })

    @app.route('/api/auth/logout', methods=['POST'])
    def logout():
        session.clear()
        return jsonify({'ok': True})

    @app.route('/api/auth/me', methods=['GET'])
    def me():
        user = get_current_user()
        if not user:
            return jsonify({'error': 'No autenticado'}), 401
        db = get_db()
        profile = db.execute('SELECT * FROM user_profiles WHERE user_id=?', (user['id'],)).fetchone()
        return jsonify({
            'user_id': user['id'],
            'username': user['username'],
            'display_name': user['display_name'],
            'is_admin': bool(user['is_admin']),
            'api_key': user['api_key_enc'] or '',
            'onboarding_done': bool(profile['onboarding_done']) if profile else False
        })

    @app.route('/api/auth/update_key', methods=['POST'])
    @login_required
    def update_key():
        db = get_db()
        body = request.get_json()
        api_key = body.get('api_key','').strip()
        user_id = session['user_id']
        db.execute('UPDATE users SET api_key_enc=? WHERE id=?', (api_key, user_id))
        db.commit()
        return jsonify({'ok': True})

    @app.route('/api/users', methods=['GET'])
    @login_required
    def list_users():
        user = get_current_user()
        if not user['is_admin']:
            return jsonify({'error': 'Solo el admin puede ver usuarios'}), 403
        db = get_db()
        users = db.execute('SELECT id, username, display_name, is_admin, created_at FROM users').fetchall()
        return jsonify([dict(u) for u in users])