import sqlite3, os
from flask import g

DATABASE = os.environ.get('DB_PATH', 'marisi_reader.db')

def get_db(app=None):
    if app:
        db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        return db
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db(app):
    with app.app_context():
        db = get_db()
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                api_key_enc TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS user_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                level TEXT DEFAULT 'intermediate',
                learning_style TEXT DEFAULT 'mixed',
                depth TEXT DEFAULT 'standard',
                goal TEXT DEFAULT 'understand',
                interests TEXT DEFAULT '[]',
                custom_instructions TEXT DEFAULT '',
                onboarding_done INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS academic_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                parsed TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                author TEXT,
                year TEXT,
                branch TEXT,
                content_type TEXT DEFAULT 'academic',
                pages INTEGER,
                source_type TEXT DEFAULT 'pdf',
                source_url TEXT,
                filename TEXT,
                summary TEXT,
                key_concepts TEXT,
                norms TEXT,
                jurisprudence TEXT,
                exam_questions TEXT,
                chapter_map TEXT,
                tools_frameworks TEXT,
                action_items TEXT,
                rating INTEGER DEFAULT 0,
                personal_notes TEXT DEFAULT '',
                subject_link TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER,
                user_id INTEGER,
                role TEXT,
                content TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books(id)
            );
            CREATE TABLE IF NOT EXISTS book_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_a_id INTEGER NOT NULL,
                book_b_id INTEGER NOT NULL,
                relation_type TEXT NOT NULL,
                strength INTEGER DEFAULT 1,
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
        ''')
        db.commit()
        _migrate(db)
        print("✓ DB inicializada")

def _migrate(db):
    """Add columns that may be missing from a DB created by an older version."""
    migrations = {
        'user_profiles': {
            'depth': "ALTER TABLE user_profiles ADD COLUMN depth TEXT DEFAULT 'standard'",
            'goal': "ALTER TABLE user_profiles ADD COLUMN goal TEXT DEFAULT 'understand'",
        },
        'books': {
            'content_type': "ALTER TABLE books ADD COLUMN content_type TEXT DEFAULT 'academic'",
            'source_type': "ALTER TABLE books ADD COLUMN source_type TEXT DEFAULT 'pdf'",
            'source_url': "ALTER TABLE books ADD COLUMN source_url TEXT",
            'tools_frameworks': "ALTER TABLE books ADD COLUMN tools_frameworks TEXT",
            'action_items': "ALTER TABLE books ADD COLUMN action_items TEXT",
            'subject_link': "ALTER TABLE books ADD COLUMN subject_link TEXT DEFAULT ''",
            'user_id': "ALTER TABLE books ADD COLUMN user_id INTEGER",
        },
        'chat_messages': {
            'user_id': "ALTER TABLE chat_messages ADD COLUMN user_id INTEGER",
        },
    }
    for table, cols in migrations.items():
        existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
        for col_name, ddl in cols.items():
            if col_name not in existing:
                try:
                    db.execute(ddl)
                    print(f"✓ Migración: agregada columna {table}.{col_name}")
                except Exception as e:
                    print(f"⚠ No se pudo agregar {table}.{col_name}: {e}")
    db.commit()