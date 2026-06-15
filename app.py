import os, json, secrets, threading
from flask import Flask, request, jsonify, render_template, session, g
from werkzeug.utils import secure_filename
from database import get_db, init_db, close_connection
from auth import register_auth_routes, login_required, get_current_user
from onboarding import register_onboarding_routes, get_user_profile_instructions
from academic import register_academic_routes, get_academic_context
from ingestion import process_source
from connections import get_connections_for_book, semantic_search, build_connections
from flashcards import register_flashcard_routes
from readermind import register_reader_mind_routes

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True

app.teardown_appcontext(close_connection)
register_auth_routes(app)
register_onboarding_routes(app)
register_academic_routes(app)
register_flashcard_routes(app)
register_reader_mind_routes(app)

init_db(app)

ALLOWED_EXTENSIONS = {'pdf','png','jpg','jpeg','webp','heic','epub','docx'}

def get_api_key(db, user_id):
    env_key = os.environ.get('OPENAI_API_KEY', '').strip()
    if env_key:
        return env_key
    user = db.execute('SELECT api_key_enc FROM users WHERE id=?', (user_id,)).fetchone()
    return (user['api_key_enc'] if user else '') or ''

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

# ── BOOKS ──────────────────────────────────────────
@app.route('/api/books', methods=['GET'])
@login_required
def get_books():
    db = get_db()
    user_id = session['user_id']
    branch = request.args.get('branch','')
    search = request.args.get('search','')
    content_type = request.args.get('content_type','')
    query = 'SELECT id,title,author,year,branch,content_type,pages,rating,source_type,created_at,summary FROM books WHERE user_id=?'
    params = [user_id]
    if branch: query += ' AND branch=?'; params.append(branch)
    if content_type: query += ' AND content_type=?'; params.append(content_type)
    if search: query += ' AND (title LIKE ? OR author LIKE ?)'; params.extend([f'%{search}%',f'%{search}%'])
    query += ' ORDER BY created_at DESC'
    return jsonify([dict(b) for b in db.execute(query, params).fetchall()])

@app.route('/api/books/<int:book_id>', methods=['GET'])
@login_required
def get_book(book_id):
    db = get_db()
    user_id = session['user_id']
    book = db.execute('SELECT * FROM books WHERE id=? AND user_id=?', (book_id, user_id)).fetchone()
    if not book: return jsonify({'error':'Libro no encontrado'}), 404
    data = dict(book)
    for f in ['key_concepts','norms','jurisprudence','exam_questions','chapter_map','tools_frameworks','action_items','why_this_book_matters','concept_map']:
        if data.get(f):
            try: data[f] = json.loads(data[f])
            except: data[f] = []
        else: data[f] = []
    if data.get('debate_suggestion'):
        try: data['debate_suggestion'] = json.loads(data['debate_suggestion'])
        except: data['debate_suggestion'] = {}
    else:
        data['debate_suggestion'] = {}
    if data.get('what_community_says'):
        try: data['what_community_says'] = json.loads(data['what_community_says'])
        except: data['what_community_says'] = {}
    else:
        data['what_community_says'] = {}
    return jsonify(data)

@app.route('/api/books/<int:book_id>', methods=['PATCH'])
@login_required
def update_book(book_id):
    db = get_db()
    user_id = session['user_id']
    body = request.get_json()
    allowed = ['rating','personal_notes','title','author','branch','subject_link']
    updates = {k:v for k,v in body.items() if k in allowed}
    if not updates: return jsonify({'error':'Nada que actualizar'}), 400
    set_clause = ', '.join(f'{k}=?' for k in updates)
    db.execute(f'UPDATE books SET {set_clause} WHERE id=? AND user_id=?', list(updates.values())+[book_id, user_id])
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/books/<int:book_id>', methods=['DELETE'])
@login_required
def delete_book(book_id):
    db = get_db()
    user_id = session['user_id']
    db.execute('DELETE FROM chat_messages WHERE book_id=? AND user_id=?', (book_id, user_id))
    db.execute('DELETE FROM book_connections WHERE user_id=? AND (book_a_id=? OR book_b_id=?)', (user_id, book_id, book_id))
    db.execute('DELETE FROM flashcard_sets WHERE book_id=? AND user_id=?', (book_id, user_id))
    db.execute('DELETE FROM reader_reflections WHERE book_id=? AND user_id=?', (book_id, user_id))
    db.execute('DELETE FROM historical_debates WHERE book_id=? AND user_id=?', (book_id, user_id))
    db.execute('DELETE FROM books WHERE id=? AND user_id=?', (book_id, user_id))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/branches', methods=['GET'])
@login_required
def get_branches():
    db = get_db()
    user_id = session['user_id']
    rows = db.execute('SELECT DISTINCT branch FROM books WHERE user_id=? AND branch IS NOT NULL ORDER BY branch', (user_id,)).fetchall()
    return jsonify([r['branch'] for r in rows])

@app.route('/api/content_types', methods=['GET'])
@login_required
def get_content_types():
    db = get_db()
    user_id = session['user_id']
    rows = db.execute('SELECT DISTINCT content_type FROM books WHERE user_id=? AND content_type IS NOT NULL', (user_id,)).fetchall()
    return jsonify([r['content_type'] for r in rows])

# ── UPLOAD / INGEST ─────────────────────────────────
@app.route('/api/upload', methods=['POST'])
@login_required
def upload_content():
    user_id = session['user_id']
    db = get_db()
    api_key = get_api_key(db, user_id)
    if not api_key: return jsonify({'error':'No hay una API key de OpenAI configurada.'}), 400

    source_type = request.form.get('source_type','pdf')
    profile_instructions = get_user_profile_instructions(user_id)
    academic_context = get_academic_context(user_id)

    filepath = None
    source_url = None

    if source_type == 'url':
        source_url = request.form.get('url','').strip()
        if not source_url: return jsonify({'error':'Ingresa una URL válida'}), 400
        try:
            result = process_source('url', source_url, api_key, profile_instructions)
        except Exception as e:
            app.logger.exception('Error processing URL')
            return jsonify({'error': f'Error al procesar la URL: {str(e)}'}), 500
    else:
        if 'file' not in request.files: return jsonify({'error':'No se envió archivo'}), 400
        file = request.files['file']
        if not file or not allowed_file(file.filename): return jsonify({'error':'Formato no soportado'}), 400
        filename = secure_filename(file.filename)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        ext = filename.rsplit('.',1)[-1].lower()
        if ext == 'pdf':
            detected_type = 'pdf'
        elif ext in ('epub', 'docx'):
            detected_type = ext
        else:
            detected_type = 'image'
        try:
            result = process_source(detected_type, filepath, api_key, profile_instructions)
        except Exception as e:
            app.logger.exception('Error processing file')
            return jsonify({'error': f'Error al analizar: {str(e)}'}), 500

    cur = db.execute('''
        INSERT INTO books (user_id,title,author,year,branch,content_type,pages,source_type,source_url,
            filename,summary,key_concepts,norms,jurisprudence,exam_questions,chapter_map,
            tools_frameworks,action_items,debate_suggestion,why_this_book_matters,concept_map,what_community_says)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (user_id, result['title'], result.get('author',''), result.get('year','---'),
         result.get('branch','General'), result.get('content_type','personal'),
         result.get('pages',0), source_type, source_url,
         os.path.basename(filepath) if filepath else None,
         result.get('summary',''),
         json.dumps(result.get('key_concepts',[])),
         json.dumps(result.get('norms',[])),
         json.dumps(result.get('jurisprudence',[])),
         json.dumps(result.get('exam_questions',[])),
         json.dumps(result.get('chapter_map',[])),
         json.dumps(result.get('tools_frameworks',[])),
         json.dumps(result.get('action_items',[])),
         json.dumps(result.get('debate_suggestion',{})),
         json.dumps(result.get('why_this_book_matters',[])),
         json.dumps(result.get('concept_map',[])),
         json.dumps(result.get('what_community_says',{}))))
    db.commit()

    new_book_id = cur.lastrowid

    def _bg_connections(user_id, book_id, api_key):
        import sqlite3, os as _os
        db2 = sqlite3.connect(_os.environ.get('DB_PATH', 'marisi_reader.db'))
        db2.row_factory = sqlite3.Row
        try:
            build_connections(db2, user_id, book_id, api_key)
        except Exception as e:
            print(f"⚠ Error en background connections: {e}")
        finally:
            db2.close()

    threading.Thread(target=_bg_connections, args=(user_id, new_book_id, api_key), daemon=True).start()

    return jsonify({'ok':True,'book_id':new_book_id,'title':result['title'],'content_type':result.get('content_type')})

# ── CHAT ────────────────────────────────────────────
@app.route('/api/books/<int:book_id>/chat', methods=['GET'])
@login_required
def get_chat(book_id):
    db = get_db()
    user_id = session['user_id']
    msgs = db.execute('SELECT role,content,created_at FROM chat_messages WHERE book_id=? AND user_id=? ORDER BY id',
                      (book_id, user_id)).fetchall()
    return jsonify([dict(m) for m in msgs])

@app.route('/api/books/<int:book_id>/chat', methods=['POST'])
@login_required
def chat_with_book(book_id):
    user_id = session['user_id']
    db = get_db()
    body = request.get_json()
    user_message = body.get('message','').strip()
    if not user_message: return jsonify({'error':'Mensaje vacío'}), 400

    api_key = get_api_key(db, user_id)
    if not api_key: return jsonify({'error':'No hay una API key de OpenAI configurada'}), 400

    book = db.execute('SELECT * FROM books WHERE id=? AND user_id=?', (book_id, user_id)).fetchone()
    if not book: return jsonify({'error':'Libro no encontrado'}), 404

    history = list(reversed([dict(h) for h in db.execute(
        'SELECT role,content FROM chat_messages WHERE book_id=? AND user_id=? ORDER BY id DESC LIMIT 10',
        (book_id, user_id)).fetchall()]))

    profile_instructions = get_user_profile_instructions(user_id)
    academic_context = get_academic_context(user_id)

    from chat import chat_with_context
    reply = chat_with_context(dict(book), user_message, history, api_key, profile_instructions, academic_context)

    db.execute('INSERT INTO chat_messages (book_id,user_id,role,content) VALUES (?,?,?,?)', (book_id, user_id, 'user', user_message))
    db.execute('INSERT INTO chat_messages (book_id,user_id,role,content) VALUES (?,?,?,?)', (book_id, user_id, 'assistant', reply))
    db.commit()
    return jsonify({'reply': reply})

@app.route('/api/books/<int:book_id>/chat', methods=['DELETE'])
@login_required
def clear_chat(book_id):
    user_id = session['user_id']
    db = get_db()
    db.execute('DELETE FROM chat_messages WHERE book_id=? AND user_id=?', (book_id, user_id))
    db.commit()
    return jsonify({'ok': True})

# ── STATS ────────────────────────────────────────────
@app.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    user_id = session['user_id']
    db = get_db()
    books = db.execute('SELECT content_type, pages FROM books WHERE user_id=?', (user_id,)).fetchall()
    total = len(books)
    pages = sum(b['pages'] or 0 for b in books)
    by_type = {}
    for b in books:
        t = b['content_type'] or 'other'
        by_type[t] = by_type.get(t, 0) + 1
    return jsonify({'total_books': total, 'total_pages': pages, 'by_type': by_type})

# ── CONNECTIONS ──────────────────────────────────────
@app.route('/api/books/<int:book_id>/connections', methods=['GET'])
@login_required
def get_book_connections(book_id):
    db = get_db()
    user_id = session['user_id']
    return jsonify(get_connections_for_book(db, user_id, book_id))

# ── BÚSQUEDA SEMÁNTICA ───────────────────────────────
@app.route('/api/search/semantic', methods=['GET'])
@login_required
def semantic_search_route():
    user_id = session['user_id']
    db = get_db()
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'Parámetro q requerido'}), 400
    api_key = get_api_key(db, user_id)
    if not api_key:
        return jsonify({'error': 'No hay API key configurada'}), 400
    return jsonify(semantic_search(db, user_id, query, api_key))

# ── LIBROS POR MATERIA ───────────────────────────────
@app.route('/api/books/by-subject', methods=['GET'])
@login_required
def get_books_by_subject():
    db = get_db()
    user_id = session['user_id']
    subject = request.args.get('subject', '').strip()
    if not subject:
        return jsonify({'error': 'Parámetro subject requerido'}), 400
    rows = db.execute(
        'SELECT id,title,author,branch,content_type,rating,subject_link FROM books '
        'WHERE user_id=? AND subject_link LIKE ?',
        (user_id, f'%{subject}%')
    ).fetchall()
    return jsonify([dict(r) for r in rows])

if __name__ == '__main__':
    init_db(app)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)