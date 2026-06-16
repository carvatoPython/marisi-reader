"""
PATCH PARA app.py — reemplaza las rutas de upload y agrega polling de jobs

Instrucciones de integración:
1. En app.py, agrega al inicio (junto a los otros imports):
       from job_queue import enqueue_job, get_job, get_user_jobs, init_jobs_table

2. En init_db(app), agrega al final del bloque with app.app_context():
       init_jobs_table(get_db())

3. Reemplaza la ruta /api/upload existente con la versión async de abajo.

4. Agrega las 3 rutas nuevas de jobs al final del archivo (antes del if __name__).
"""

# ══════════════════════════════════════════════════════════════════════════════
# REEMPLAZAR — ruta /api/upload  (borra la que tienes, pon esta)
# ══════════════════════════════════════════════════════════════════════════════

"""
@app.route('/api/upload', methods=['POST'])
@login_required
def upload_content():
    user_id = session['user_id']
    db = get_db()
    api_key = get_api_key(db, user_id)
    if not api_key:
        return jsonify({'error': 'No hay una API key de OpenAI configurada.'}), 400

    source_type = request.form.get('source_type', 'pdf')
    profile_instructions = get_user_profile_instructions(user_id)
    academic_context = get_academic_context(user_id)

    filepath = None
    source_url = None
    filename = None

    if source_type == 'url':
        source_url = request.form.get('url', '').strip()
        if not source_url:
            return jsonify({'error': 'Ingresa una URL válida'}), 400
    else:
        if 'file' not in request.files:
            return jsonify({'error': 'No se envió archivo'}), 400
        file = request.files['file']
        if not file or not allowed_file(file.filename):
            return jsonify({'error': 'Formato no soportado'}), 400

        filename = secure_filename(file.filename)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        ext = filename.rsplit('.', 1)[-1].lower()
        if ext == 'pdf':
            source_type = 'pdf'
        elif ext in ('epub', 'docx'):
            source_type = ext
        else:
            source_type = 'image'

    # ── Lanzar job en background — respuesta inmediata ──────────────────────
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

    return jsonify({
        'ok': True,
        'job_id': job_id,
        'status': 'pending',
        'message': 'Análisis iniciado. Puedes cerrar esta pantalla — te avisamos cuando termine.'
    })
"""


# ══════════════════════════════════════════════════════════════════════════════
# AGREGAR — 3 rutas nuevas de jobs (pega esto antes del if __name__)
# ══════════════════════════════════════════════════════════════════════════════

"""
# ── JOBS / POLLING ────────────────────────────────────────────────────────────

@app.route('/api/jobs/<int:job_id>', methods=['GET'])
@login_required
def get_job_status(job_id):
    \"\"\"
    Polling endpoint — el frontend llama esto cada 3 segundos.
    Retorna estado, progreso y book_id cuando termina.
    \"\"\"
    user_id = session['user_id']
    job = get_job(job_id)

    if not job:
        return jsonify({'error': 'Job no encontrado'}), 404
    if job['user_id'] != user_id:
        return jsonify({'error': 'No autorizado'}), 403

    return jsonify({
        'job_id': job_id,
        'status': job['status'],          # pending | running | done | error
        'step': job.get('step', ''),
        'progress': job.get('progress', 0),
        'progress_msg': job.get('progress_msg', ''),
        'book_id': job.get('book_id'),    # disponible cuando status=done
        'error_msg': job.get('error_msg') if job['status'] == 'error' else None,
        'filename': job.get('filename', ''),
        'updated_at': job.get('updated_at', '')
    })


@app.route('/api/jobs', methods=['GET'])
@login_required
def list_jobs():
    \"\"\"Lista los jobs recientes del usuario (para mostrar historial de uploads).\"\"\"
    user_id = session['user_id']
    jobs = get_user_jobs(user_id, limit=20)
    return jsonify(jobs)


@app.route('/api/jobs/<int:job_id>/cancel', methods=['DELETE'])
@login_required
def cancel_job(job_id):
    \"\"\"
    Marca un job como cancelado si está en pending.
    (Los jobs running no se pueden cancelar — el thread ya arrancó.)
    \"\"\"
    user_id = session['user_id']
    job = get_job(job_id)

    if not job:
        return jsonify({'error': 'Job no encontrado'}), 404
    if job['user_id'] != user_id:
        return jsonify({'error': 'No autorizado'}), 403
    if job['status'] not in ('pending', 'error'):
        return jsonify({'error': 'Solo se pueden cancelar jobs en pending o error'}), 400

    from job_queue import _update_job
    _update_job(job_id, status='cancelled', progress_msg='Cancelado por el usuario')
    return jsonify({'ok': True})
"""