import os
import psycopg2
import psycopg2.extras
from flask import g

DATABASE_URL = os.environ.get('DATABASE_URL', '')


class QueryAdapter:
    """Wraps a psycopg2 connection to provide a sqlite3-like .execute()/.fetchone()/.fetchall()
    interface, translating '?' placeholders to '%s' and returning dict-like rows."""

    def __init__(self, conn):
        self.conn = conn

    def execute(self, query, params=()):
        is_insert = query.strip().upper().startswith('INSERT')
        translated = query.replace('?', '%s')
        if is_insert and 'RETURNING' not in translated.upper():
            translated = translated.rstrip().rstrip(';') + ' RETURNING id'
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(translated, params)
        return CursorWrapper(cur, is_insert)

    def executescript(self, script):
        cur = self.conn.cursor()
        cur.execute(script)
        cur.close()

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


class CursorWrapper:
    def __init__(self, cur, is_insert):
        self.cur = cur
        self._lastrowid = None
        if is_insert:
            try:
                row = self.cur.fetchone()
                if row and 'id' in row:
                    self._lastrowid = row['id']
            except psycopg2.ProgrammingError:
                pass

    @property
    def lastrowid(self):
        return self._lastrowid

    def fetchone(self):
        try:
            return self.cur.fetchone()
        except psycopg2.ProgrammingError:
            return None

    def fetchall(self):
        try:
            return self.cur.fetchall() or []
        except psycopg2.ProgrammingError:
            return []


def get_db(app=None):
    if app:
        conn = psycopg2.connect(DATABASE_URL)
        return QueryAdapter(conn)
    db = getattr(g, '_database', None)
    if db is None:
        conn = psycopg2.connect(DATABASE_URL)
        db = g._database = QueryAdapter(conn)
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
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                api_key_enc TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS user_profiles (
                id SERIAL PRIMARY KEY,
                user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
                level TEXT DEFAULT 'intermediate',
                learning_style TEXT DEFAULT 'mixed',
                depth TEXT DEFAULT 'standard',
                goal TEXT DEFAULT 'understand',
                interests TEXT DEFAULT '[]',
                custom_instructions TEXT DEFAULT '',
                interpretation_profile TEXT DEFAULT '',
                onboarding_done INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS academic_data (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                parsed TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS books (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                id SERIAL PRIMARY KEY,
                book_id INTEGER REFERENCES books(id),
                user_id INTEGER,
                role TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS game_sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                book_id INTEGER NOT NULL REFERENCES books(id),
                category TEXT,
                fragment_text TEXT,
                questions_json TEXT,
                answers_json TEXT DEFAULT '{}',
                score INTEGER DEFAULT 0,
                max_score INTEGER DEFAULT 0,
                interpretation_insights TEXT DEFAULT '',
                completed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        db.commit()
        _migrate(db)
        print("✓ DB inicializada (PostgreSQL)")


def _migrate(db):
    """Add columns that may be missing from a DB created by an older version."""
    migrations = {
        'user_profiles': {
            'depth': "ALTER TABLE user_profiles ADD COLUMN depth TEXT DEFAULT 'standard'",
            'goal': "ALTER TABLE user_profiles ADD COLUMN goal TEXT DEFAULT 'understand'",
            'interpretation_profile': "ALTER TABLE user_profiles ADD COLUMN interpretation_profile TEXT DEFAULT ''",
        },
        'books': {
            'content_type': "ALTER TABLE books ADD COLUMN content_type TEXT DEFAULT 'academic'",
            'source_type': "ALTER TABLE books ADD COLUMN source_type TEXT DEFAULT 'pdf'",
            'source_url': "ALTER TABLE books ADD COLUMN source_url TEXT",
            'tools_frameworks': "ALTER TABLE books ADD COLUMN tools_frameworks TEXT",
            'action_items': "ALTER TABLE books ADD COLUMN action_items TEXT",
            'subject_link': "ALTER TABLE books ADD COLUMN subject_link TEXT DEFAULT ''",
        },
        'chat_messages': {
            'user_id': "ALTER TABLE chat_messages ADD COLUMN user_id INTEGER",
        },
    }
    for table, cols in migrations.items():
        cur = db.conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
        existing = {row[0] for row in cur.fetchall()}
        cur.close()
        for col_name, ddl in cols.items():
            if col_name not in existing:
                try:
                    c2 = db.conn.cursor()
                    c2.execute(ddl)
                    c2.close()
                    print(f"✓ Migración: agregada columna {table}.{col_name}")
                except Exception as e:
                    print(f"⚠ No se pudo agregar {table}.{col_name}: {e}")
                    db.conn.rollback()
    db.commit()