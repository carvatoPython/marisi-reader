"""
ADDITIONS TO database.py
=========================

1. Inside init_db(), add these two CREATE TABLE statements to the executescript:
   (paste after the chat_messages table, before the closing triple-quote)
"""

NEW_TABLES = """
            CREATE TABLE IF NOT EXISTS book_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_a_id INTEGER NOT NULL,
                book_b_id INTEGER NOT NULL,
                relation_type TEXT NOT NULL,   -- coincide | contradice | complementa
                strength INTEGER DEFAULT 1,    -- 1=débil, 2=moderada, 3=fuerte
                summary TEXT,
                shared_concepts TEXT DEFAULT '[]',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, book_a_id, book_b_id),
                FOREIGN KEY (book_a_id) REFERENCES books(id),
                FOREIGN KEY (book_b_id) REFERENCES books(id)
            );
            CREATE TABLE IF NOT EXISTS flashcard_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                cards TEXT DEFAULT '[]',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(book_id, user_id),
                FOREIGN KEY (book_id) REFERENCES books(id)
            );
"""

"""
2. Inside _migrate(), add these entries to the `migrations` dict:

    'books': {
        ...existing entries...,
        'epub_support': None,  # handled via ALLOWED_EXTENSIONS in app.py, no column needed
    }

   No new columns are needed in existing tables — the new tables above handle everything.


3. (Optional) Add a migration guard for the new tables in _migrate():
   The CREATE TABLE IF NOT EXISTS above already handles this safely on first run.
"""


"""
ADDITIONS TO app.py
====================

1. Update ALLOWED_EXTENSIONS to include epub and docx:

    ALLOWED_EXTENSIONS = {'pdf','png','jpg','jpeg','webp','heic','epub','docx'}

2. In upload_content(), update the file-type detection block:

    OLD:
        detected_type = 'pdf' if ext == 'pdf' else 'image'

    NEW:
        if ext == 'pdf':
            detected_type = 'pdf'
        elif ext in ('epub', 'docx'):
            detected_type = ext          # ingestion.py must handle these
        else:
            detected_type = 'image'

3. After db.commit() in upload_content(), trigger async connection-building:

    from connections import build_connections
    import threading
    new_book_id = cur.lastrowid
    # Run in background so the upload response is instant
    threading.Thread(
        target=build_connections,
        args=(get_db(app._get_current_object()), user_id, new_book_id, api_key),
        daemon=True
    ).start()

    (Note: since SQLite connections aren't thread-safe to share, open a fresh
     connection inside build_connections using get_db(app) directly — already
     handled in connections.py which calls get_db without arguments for the
     request context. For background threads, pass the app and open a new conn:)

    # Safer pattern for background thread:
    def _bg_connections(app, user_id, book_id, api_key):
        import sqlite3, os
        db = sqlite3.connect(os.environ.get('DB_PATH', 'marisi_reader.db'))
        db.row_factory = sqlite3.Row
        from connections import build_connections
        build_connections(db, user_id, book_id, api_key)
        db.close()

    threading.Thread(
        target=_bg_connections,
        args=(app, user_id, cur.lastrowid, api_key),
        daemon=True
    ).start()

4. Register the new routes (add after register_academic_routes(app)):

    from flashcards import register_flashcard_routes
    register_flashcard_routes(app)

5. Add the connections and semantic search endpoints:

    from connections import get_connections_for_book, semantic_search

    @app.route('/api/books/<int:book_id>/connections', methods=['GET'])
    @login_required
    def get_book_connections(book_id):
        db = get_db()
        user_id = session['user_id']
        connections = get_connections_for_book(db, user_id, book_id)
        return jsonify(connections)

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
        results = semantic_search(db, user_id, query, api_key)
        return jsonify(results)

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


ADDITIONS TO ingestion.py
==========================

You'll need to add two new branches in your process_source() function:

    elif source_type == 'epub':
        # Extract text from EPUB then pass to the AI analysis pipeline
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup

        book_epub = epub.read_epub(source_path)
        texts = []
        for item in book_epub.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            texts.append(soup.get_text())
        full_text = '\\n'.join(texts)[:15000]  # trim to fit context
        # then pass full_text to your existing AI analysis prompt

    elif source_type == 'docx':
        from docx import Document
        doc = Document(source_path)
        full_text = '\\n'.join(p.text for p in doc.paragraphs if p.text.strip())[:15000]
        # then pass full_text to your existing AI analysis prompt

Dependencies to add to requirements.txt:
    EbookLib
    beautifulsoup4
    python-docx
"""