import os, json, secrets, threading
from flask import Flask, request, jsonify, render_template, session, g
from werkzeug.utils import secure_filename
from database import get_db, init_db, close_connection
from auth import register_auth_routes, login_required, get_current_user
from onboarding import register_onboarding_routes, get_user_profile_instructions
from academic import register_academic_routes, get_academic_context
from ingestion import process_source
from job_queue import enqueue_job, get_job, get_user_jobs, init_jobs_table
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
init_jobs_table(get_db(app))

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
    for f in ['key_concepts','norms','jurisprudence','exam_questions','chapter_map','tools_frameworks',
              'action_items','why_this_book_matters','concept_map','transformative_ideas',
              'character_profiles','debatable_ideas','impact_by_profile','real_questions']:
        if data.get(f):
            try: data[f] = json.loads(data[f])
            except: data[f] = []
        else: data[f] = []
    for f in ['debate_suggestion','what_community_says','importance_hierarchy']:
        if data.get(f):
            try: data[f] = json.loads(data[f])
            except: data[f] = {}
        else: data[f] = {}
    if not data.get('author_thesis'):
        data['author_thesis'] = ''
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
    filename = None

    if source_type == 'url':
        source_url = request.form.get('url','').strip()
        if not source_url: return jsonify({'error':'Ingresa una URL válida'}), 400
    else:
        if 'file' not in request.files: return jsonify({'error':'No se envió archivo'}), 400
        file = request.files['file']
        if not file or not allowed_file(file.filename): return jsonify({'error':'Formato no soportado'}), 400
        filename = secure_filename(file.filename)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        ext = filename.rsplit('.',1)[-1].lower()
        if ext == 'pdf': source_type = 'pdf'
        elif ext in ('epub','docx'): source_type = ext
        else: source_type = 'image'

    job_id = enqueue_job(
        user_id=user_id,
        api_key=api_key,
        source_type=source_type,
        profile_instructions=profile_instructions,
        academic_context=academic_context,
        filepath=filepath,
        source_url=source_url,
        filename=filename
    )
    return jsonify({'ok': True, 'job_id': job_id, 'status': 'pending'})

# ── JOBS / POLLING ───────────────────────────────────
@app.route('/api/jobs/<int:job_id>', methods=['GET'])
@login_required
def get_job_status(job_id):
    user_id = session['user_id']
    job = get_job(job_id)
    if not job: return jsonify({'error':'Job no encontrado'}), 404
    if job['user_id'] != user_id: return jsonify({'error':'No autorizado'}), 403
    return jsonify({
        'job_id': job_id,
        'status': job['status'],
        'step': job.get('step',''),
        'progress': job.get('progress', 0),
        'progress_msg': job.get('progress_msg',''),
        'book_id': job.get('book_id'),
        'error_msg': job.get('error_msg') if job['status'] == 'error' else None,
        'filename': job.get('filename',''),
        'updated_at': job.get('updated_at','')
    })

@app.route('/api/jobs', methods=['GET'])
@login_required
def list_jobs():
    user_id = session['user_id']
    return jsonify(get_user_jobs(user_id, limit=20))

@app.route('/api/jobs/<int:job_id>/cancel', methods=['DELETE'])
@login_required
def cancel_job(job_id):
    user_id = session['user_id']
    job = get_job(job_id)
    if not job: return jsonify({'error':'Job no encontrado'}), 404
    if job['user_id'] != user_id: return jsonify({'error':'No autorizado'}), 403
    if job['status'] not in ('pending','error'): return jsonify({'error':'Solo se pueden cancelar jobs en pending o error'}), 400
    from job_queue import _update_job
    _update_job(job_id, status='cancelled', progress_msg='Cancelado por el usuario')
    return jsonify({'ok': True})

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

# ── MODO LECTURA ─────────────────────────────────────────────────────────────

@app.route('/api/books/<int:book_id>/chunks', methods=['GET'])
@login_required
def get_book_chunks(book_id):
    """Lista todos los chunks de un libro con su rango de páginas."""
    db = get_db()
    user_id = session['user_id']
    book = db.execute('SELECT id FROM books WHERE id=? AND user_id=?', (book_id, user_id)).fetchone()
    if not book: return jsonify({'error': 'Libro no encontrado'}), 404
    rows = db.execute(
        'SELECT id, chunk_index, page_start, page_end, pages_label FROM book_chunks WHERE book_id=? ORDER BY chunk_index',
        (book_id,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/books/<int:book_id>/chunks/page/<int:page_num>', methods=['GET'])
@login_required
def get_chunk_by_page(book_id, page_num):
    """
    Retorna el chunk y su análisis para una página específica.
    El frontend llama esto cuando el usuario navega a una página del PDF.
    """
    db = get_db()
    user_id = session['user_id']
    book = db.execute('SELECT id FROM books WHERE id=? AND user_id=?', (book_id, user_id)).fetchone()
    if not book: return jsonify({'error': 'Libro no encontrado'}), 404

    chunk = db.execute(
        'SELECT * FROM book_chunks WHERE book_id=? AND page_start<=? AND page_end>=? ORDER BY chunk_index LIMIT 1',
        (book_id, page_num, page_num)
    ).fetchone()
    if not chunk: return jsonify({'error': 'No hay análisis para esta página'}), 404

    analysis = db.execute(
        'SELECT * FROM chunk_analysis WHERE chunk_id=?', (chunk['id'],)
    ).fetchone()

    result = {
        'chunk_id': chunk['id'],
        'chunk_index': chunk['chunk_index'],
        'pages': chunk['pages_label'],
        'page_start': chunk['page_start'],
        'page_end': chunk['page_end'],
        'raw_text': chunk['raw_text'] or '',
    }
    if analysis:
        for f in ['key_concepts', 'norms', 'cases', 'chapter_topics', 'exam_signals', 'doctrinal_notes']:
            try: result[f] = json.loads(analysis[f] or '[]')
            except: result[f] = []
    return jsonify(result)

@app.route('/api/books/<int:book_id>/chunks/<int:chunk_id>/chat', methods=['POST'])
@login_required
def chat_with_chunk(book_id, chunk_id):
    """
    Chat contextual con un chunk específico.
    Usa el texto del chunk como contexto primario + análisis del libro completo.
    """
    user_id = session['user_id']
    db = get_db()
    body = request.get_json()
    message = body.get('message', '').strip()
    if not message: return jsonify({'error': 'Mensaje vacío'}), 400

    api_key = get_api_key(db, user_id)
    if not api_key: return jsonify({'error': 'No hay API key'}), 400

    book = db.execute('SELECT * FROM books WHERE id=? AND user_id=?', (book_id, user_id)).fetchone()
    chunk = db.execute('SELECT * FROM book_chunks WHERE id=? AND book_id=?', (chunk_id, book_id)).fetchone()
    if not book or not chunk: return jsonify({'error': 'No encontrado'}), 404

    analysis = db.execute('SELECT * FROM chunk_analysis WHERE chunk_id=?', (chunk_id,)).fetchone()

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    chunk_context = chunk['raw_text'][:8000]
    analysis_context = ""
    if analysis:
        try:
            norms = json.loads(analysis['norms'] or '[]')
            cases = json.loads(analysis['cases'] or '[]')
            concepts = json.loads(analysis['key_concepts'] or '[]')
            analysis_context = f"\nNormas en esta sección: {json.dumps(norms[:5], ensure_ascii=False)}\nCasos: {json.dumps(cases[:3], ensure_ascii=False)}\nConceptos: {json.dumps(concepts[:5], ensure_ascii=False)}"
        except: pass

    system = f"""Eres Marisi, tutora experta en {book['branch'] or 'derecho'}.
El usuario está leyendo las páginas {chunk['pages_label']} de "{book['title']}".

TEXTO DE ESTAS PÁGINAS:
{chunk_context}
{analysis_context}

Responde basándote PRIMERO en el texto de estas páginas.
Si la pregunta va más allá, usa tu conocimiento del libro completo.
Sé directa, específica y útil para examen."""

    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": message}
        ],
        max_tokens=800,
        temperature=0.3
    )
    return jsonify({'reply': r.choices[0].message.content})
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