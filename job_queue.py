"""
job_queue.py — Sistema de procesamiento en background para Marisi Reader

Usa SQLite como queue de jobs + threading para procesamiento asíncrono.
Sin dependencias externas (no Celery, no Redis) — funciona en Railway Free tier.

Estados de un job:
  pending   → en cola, esperando worker
  running   → siendo procesado actualmente
  done      → completado con éxito
  error     → falló con mensaje de error
"""

import sqlite3, json, threading, os, time, traceback
from datetime import datetime
import sys
sys.path.append(r"C:\Users\CARVATO\Documents\VScode  archivos\mery")



DATABASE = os.environ.get("DB_PATH", "marisi_reader.db")

# ── SCHEMA ────────────────────────────────────────────────────────────────────

JOBS_SCHEMA = """
CREATE TABLE IF NOT EXISTS processing_jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    book_id     INTEGER,                -- se llena cuando el libro es creado
    status      TEXT NOT NULL DEFAULT 'pending',
    step        TEXT DEFAULT '',        -- etapa actual (extract/analyze/synthesize)
    progress    INTEGER DEFAULT 0,      -- 0-100
    progress_msg TEXT DEFAULT '',       -- mensaje legible para el usuario
    source_type TEXT NOT NULL,
    filepath    TEXT,
    source_url  TEXT,
    filename    TEXT,
    error_msg   TEXT,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

def init_jobs_table(db):
    """Agrega la tabla de jobs si no existe — llamar desde init_db."""
    db.executescript(JOBS_SCHEMA)
    db.commit()


# ── DB HELPERS ────────────────────────────────────────────────────────────────

def _get_conn():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def create_job(user_id: int, source_type: str,
               filepath: str = None, source_url: str = None,
               filename: str = None) -> int:
    """Crea un job y retorna su ID."""
    conn = _get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO processing_jobs
               (user_id, status, source_type, filepath, source_url, filename, progress, progress_msg)
               VALUES (?, 'pending', ?, ?, ?, ?, 0, 'En cola de procesamiento...')""",
            (user_id, source_type, filepath, source_url, filename)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_job(job_id: int) -> dict | None:
    """Retorna el estado actual de un job."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM processing_jobs WHERE id=?", (job_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_jobs(user_id: int, limit: int = 10) -> list[dict]:
    """Lista los jobs recientes de un usuario."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT id, status, step, progress, progress_msg, book_id,
                      filename, source_type, error_msg, created_at, updated_at
               FROM processing_jobs
               WHERE user_id=?
               ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _update_job(job_id: int, **kwargs):
    """Actualiza campos de un job."""
    kwargs["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [job_id]
    conn = _get_conn()
    try:
        conn.execute(f"UPDATE processing_jobs SET {set_clause} WHERE id=?", values)
        conn.commit()
    finally:
        conn.close()


def _set_progress(job_id: int, step: str, current: int, total: int, message: str):
    """Callback de progreso — calcula porcentaje y actualiza DB."""
    pct = int((current / max(total, 1)) * 100)

    # Mapear etapas a rangos de progreso para UI más suave
    step_ranges = {
        "extract":    (0, 10),
        "metadata":   (10, 15),
        "analyze":    (15, 75),
        "accumulate": (75, 80),
        "synthesize": (80, 99),
    }
    lo, hi = step_ranges.get(step, (0, 99))
    global_pct = lo + int((pct / 100) * (hi - lo))

    _update_job(
        job_id,
        step=step,
        progress=global_pct,
        progress_msg=message,
        status="running"
    )


# ── WORKER ────────────────────────────────────────────────────────────────────

def _run_job(job_id: int, api_key: str, profile_instructions: str,
             academic_context: str):
    """
    Función que corre en un thread separado.
    Procesa el job y guarda el resultado en la DB.
    """
    job = get_job(job_id)
    if not job:
        return

    user_id = job["user_id"]
    source_type = job["source_type"]
    filepath = job["filepath"]
    source_url = job["source_url"]

    _update_job(job_id, status="running", progress=0,
                progress_msg="Iniciando análisis...")

    try:
        # ── Seleccionar motor de procesamiento ────────────────────────────
        if source_type == "pdf":
            # PDFs: usar motor de chunks para libros grandes
            from ingestion_chunked import process_pdf_chunked

            def progress_cb(step, current, total, message):
                _set_progress(job_id, step, current, total, message)

            result = process_pdf_chunked(
                filepath=filepath,
                api_key=api_key,
                profile_instructions=profile_instructions,
                progress_callback=progress_cb
            )

        else:
            # URL / imagen / epub / docx → motor original (no chunked)
            from ingestion import process_source
            _update_job(job_id, progress=10,
                        progress_msg="Extrayendo contenido...")
            result = process_source(
                source_type, filepath or source_url,
                api_key, profile_instructions
            )
            _update_job(job_id, progress=90,
                        progress_msg="Guardando análisis...")

        # ── Guardar libro en DB ───────────────────────────────────────────
        conn = _get_conn()
        try:
            cur = conn.execute(
                """INSERT INTO books
                   (user_id, title, author, year, branch, content_type, pages,
                    source_type, source_url, filename, summary,
                    key_concepts, norms, jurisprudence, exam_questions,
                    chapter_map, tools_frameworks, action_items,
                    debate_suggestion, why_this_book_matters,
                    concept_map, what_community_says,
                    author_thesis, transformative_ideas, importance_hierarchy,
                    character_profiles, debatable_ideas, impact_by_profile, real_questions)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    user_id,
                    result.get("title", "Sin título"),
                    result.get("author", ""),
                    result.get("year", "---"),
                    result.get("branch", "General"),
                    result.get("content_type", "legal"),
                    result.get("pages", 0),
                    source_type,
                    source_url,
                    job.get("filename"),
                    result.get("summary", ""),
                    json.dumps(result.get("key_concepts", [])),
                    json.dumps(result.get("norms", [])),
                    json.dumps(result.get("jurisprudence", [])),
                    json.dumps(result.get("exam_questions", [])),
                    json.dumps(result.get("chapter_map", [])),
                    json.dumps(result.get("tools_frameworks", [])),
                    json.dumps(result.get("action_items", [])),
                    json.dumps(result.get("debate_suggestion", {})),
                    json.dumps(result.get("why_this_book_matters", [])),
                    json.dumps(result.get("concept_map", [])),
                    json.dumps(result.get("what_community_says", {})),
                    result.get("author_thesis", ""),
                    json.dumps(result.get("transformative_ideas", [])),
                    json.dumps(result.get("importance_hierarchy", {})),
                    json.dumps(result.get("character_profiles", [])),
                    json.dumps(result.get("debatable_ideas", [])),
                    json.dumps(result.get("impact_by_profile", [])),
                    json.dumps(result.get("real_questions", [])),
                )
            )
            conn.commit()
            book_id = cur.lastrowid

            # ── Guardar chunks y su análisis para modo lectura ────────────
            chunks_data = result.get("_chunks", [])
            if chunks_data:
                for ch in chunks_data:
                    chunk_cur = conn.execute(
                        """INSERT OR IGNORE INTO book_chunks
                           (book_id, user_id, chunk_index, page_start, page_end, pages_label, raw_text)
                           VALUES (?,?,?,?,?,?,?)""",
                        (book_id, user_id,
                         ch.get("chunk_index", 0),
                         ch.get("page_start", 0),
                         ch.get("page_end", 0),
                         ch.get("pages", ""),
                         ch.get("raw_text", "")[:20000])
                    )
                    chunk_id = chunk_cur.lastrowid
                    if chunk_id:
                        conn.execute(
                            """INSERT OR IGNORE INTO chunk_analysis
                               (chunk_id, book_id, key_concepts, norms, cases,
                                chapter_topics, exam_signals, doctrinal_notes, supporting_elements)
                               VALUES (?,?,?,?,?,?,?,?,?)""",
                            (chunk_id, book_id,
                             json.dumps(ch.get("key_concepts", [])),
                             json.dumps(ch.get("norms", [])),
                             json.dumps(ch.get("cases", [])),
                             json.dumps(ch.get("chapter_topics", [])),
                             json.dumps(ch.get("exam_signals", [])),
                             json.dumps(ch.get("doctrinal_notes", [])),
                             json.dumps(ch.get("supporting_elements", [])))
                        )
                conn.commit()
                print(f"✅ {len(chunks_data)} chunks guardados para modo lectura")
        finally:
            conn.close()

        # ── Conexiones entre libros en background ─────────────────────────
        def _bg_connections(uid, bid, ak):
            import sqlite3 as _sq
            db2 = _sq.connect(DATABASE)
            db2.row_factory = _sq.Row
            try:
                from connections import build_connections
                build_connections(db2, uid, bid, ak)
            except Exception as e:
                print(f"⚠ Conexiones background: {e}")
            finally:
                db2.close()

        threading.Thread(
            target=_bg_connections,
            args=(user_id, book_id, api_key),
            daemon=True
        ).start()

        # ── Job completado ────────────────────────────────────────────────
                # ── Notificación por email ────────────────────────────────────────
        try:
            conn2 = _get_conn()
            user = conn2.execute('SELECT email FROM users WHERE id=?', (user_id,)).fetchone()
            conn2.close()
            if user and user['email']:
                from mery.comms import gmail_enviar
                gmail_enviar(
                    destinatario=user['email'],
                    asunto=f"📚 Tu libro está listo: {result.get('title', '---')}",
                    cuerpo=f"""Tu análisis ha terminado.

                    📖 {result.get('title', '---')}

                    Resumen:
                    {result.get('summary', '')[:800]}

                    Ya puedes entrar a Marisi Reader y estudiar el contenido completo."""
                )
        except Exception as e:

            print(f"⚠ Email no enviado: {e}")
        _update_job(
            job_id,
            status="done",
            book_id=book_id,
            progress=100,
            progress_msg=f"✅ {result.get('title', 'Libro')} — análisis completo"
        )

        print(f"✅ Job {job_id} completado → book_id={book_id}")

    except Exception as e:
        tb = traceback.format_exc()
        print(f"❌ Job {job_id} falló:\n{tb}")
        _update_job(
            job_id,
            status="error",
            progress=0,
            progress_msg="Error en el análisis",
            error_msg=str(e)[:500]
        )


# ── API PÚBLICA ───────────────────────────────────────────────────────────────

def enqueue_job(
    user_id: int,
    api_key: str,
    source_type: str,
    profile_instructions: str = "",
    academic_context: str = "",
    filepath: str = None,
    source_url: str = None,
    filename: str = None
) -> int:
    """
    Crea un job y lo lanza en un thread daemon.
    Retorna el job_id inmediatamente.
    """
    job_id = create_job(
        user_id=user_id,
        source_type=source_type,
        filepath=filepath,
        source_url=source_url,
        filename=filename
    )

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, api_key, profile_instructions, academic_context),
        daemon=True
    )
    thread.start()

    print(f"🚀 Job {job_id} encolado para user={user_id}")
    return job_id