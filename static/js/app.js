/* ══════════════════════════════════════
   MARISI READER v2 — App JS
══════════════════════════════════════ */

let STATE = {
  user: null,
  books: [],
  currentBookId: null,
  currentView: 'home',
  chatBookId: null,
  selectedFile: null,
  srcType: 'pdf',
  obStep: 0,
  obAnswers: {},
  obQuestions: []
};

const TYPE_LABELS = {
  legal: '⚖️ Jurídico', tech: '💻 Tecnología',
  data_science: '📊 Data Science', personal: '🌱 Personal', article: '📄 Artículo'
};

/* ── INIT ─────────────────────────── */
window.addEventListener('DOMContentLoaded', async () => {
  const res = await api('/api/auth/me');
  if (res.user_id) {
    STATE.user = res;
    if (!res.onboarding_done) await startOnboarding();
    else enterApp();
  }
});

/* ── AUTH ─────────────────────────── */
function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach((b,i) => b.classList.toggle('active', (i===0&&tab==='login')||(i===1&&tab==='register')));
  document.getElementById('tab-login').classList.toggle('active', tab==='login');
  document.getElementById('tab-register').classList.toggle('active', tab==='register');
}

async function doLogin() {
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  if (!username || !password) return toast('Completa todos los campos', 'error');
  const res = await api('/api/auth/login', 'POST', { username, password });
  if (res.error) return toast(res.error, 'error');
  STATE.user = res;
  if (!res.onboarding_done) await startOnboarding();
  else enterApp();
}

async function doRegister() {
  const display_name = document.getElementById('reg-name').value.trim();
  const username = document.getElementById('reg-username').value.trim();
  const password = document.getElementById('reg-password').value;
  const api_key = document.getElementById('reg-apikey').value.trim();
  if (!display_name || !username || !password) return toast('Completa los campos requeridos', 'error');
  const res = await api('/api/auth/register', 'POST', { display_name, username, password, api_key });
  if (res.error) return toast(res.error, 'error');
  STATE.user = res;
  await startOnboarding();
}

async function doLogout() {
  await api('/api/auth/logout', 'POST');
  STATE.user = null;
  showScreen('auth');
}

/* ── ONBOARDING ───────────────────── */
async function startOnboarding() {
  showScreen('onboarding');
  const res = await api('/api/onboarding/questions');
  STATE.obQuestions = res;
  STATE.obStep = 0;
  STATE.obAnswers = {};
  renderObStep();
}

function renderObStep() {
  const q = STATE.obQuestions[STATE.obStep];
  if (!q) return;
  const total = STATE.obQuestions.length;
  document.getElementById('ob-progress-fill').style.width = `${((STATE.obStep+1)/total)*100}%`;
  document.getElementById('ob-back').style.display = STATE.obStep > 0 ? 'block' : 'none';
  document.getElementById('ob-next').textContent = STATE.obStep === total-1 ? 'Finalizar ✓' : 'Siguiente →';

  const isMulti = q.multi;
  const current = STATE.obAnswers[q.id] || (isMulti ? [] : null);

  document.getElementById('onboarding-question').innerHTML = `
    <div class="ob-question">
      <h3>${esc(q.question)}</h3>
      <div class="ob-options">
        ${q.options.map(o => `
          <button class="ob-option ${isMulti ? (current.includes(o.value)?'selected':'') : (current===o.value?'selected':'')}"
            onclick="selectOb('${q.id}','${o.value}',${isMulti})">
            ${esc(o.label)}
          </button>`).join('')}
      </div>
    </div>`;
}

function selectOb(qid, value, isMulti) {
  if (isMulti) {
    let arr = STATE.obAnswers[qid] || [];
    arr = arr.includes(value) ? arr.filter(v=>v!==value) : [...arr, value];
    STATE.obAnswers[qid] = arr;
  } else {
    STATE.obAnswers[qid] = value;
  }
  renderObStep();
}

function obBack() {
  if (STATE.obStep > 0) { STATE.obStep--; renderObStep(); }
}

async function obNext() {
  const q = STATE.obQuestions[STATE.obStep];
  const ans = STATE.obAnswers[q.id];
  if (!ans || (Array.isArray(ans) && !ans.length)) return toast('Selecciona al menos una opción', 'error');
  if (STATE.obStep < STATE.obQuestions.length - 1) {
    STATE.obStep++; renderObStep();
  } else {
    const payload = {
      level: STATE.obAnswers['level'] || 'intermediate',
      style: STATE.obAnswers['style'] || 'mixed',
      depth: STATE.obAnswers['depth'] || 'standard',
      interests: STATE.obAnswers['interests'] || [],
      goal: STATE.obAnswers['goal'] || 'understand'
    };
    const res = await api('/api/onboarding/save', 'POST', payload);
    if (res.error) return toast(res.error, 'error');
    enterApp();
  }
}

async function restartOnboarding() {
  await startOnboarding();
}

/* ── ENTER APP ────────────────────── */
function enterApp() {
  showScreen('app');
  const name = STATE.user?.display_name || 'Estudiante';
  document.getElementById('hero-name').textContent = name;
  document.getElementById('sidebar-user').innerHTML = `<strong>${esc(name)}</strong>${esc(STATE.user?.username||'')}`;
  loadBooks();
}

/* ── BOOKS ────────────────────────── */
async function loadBooks() {
  const type = document.getElementById('type-filter')?.value || '';
  const search = document.getElementById('search-input')?.value || '';
  const params = new URLSearchParams();
  if (type) params.set('content_type', type);
  if (search) params.set('search', search);
  const books = await api('/api/books?' + params);
  STATE.books = Array.isArray(books) ? books : [];
  renderBookList(STATE.books);
  renderHome(STATE.books);
}

function filterBooks() { loadBooks(); }

function renderBookList(books) {
  const list = document.getElementById('book-list');
  if (!books.length) {
    list.innerHTML = '<div class="empty-state"><p>Sin contenido aún.<br>Agrega tu primer libro ↓</p></div>';
    return;
  }
  list.innerHTML = books.map(b => `
    <div class="book-item ${b.id===STATE.currentBookId?'active':''}" onclick="openBook(${b.id})">
      <div class="book-item-title">${esc(b.title)}</div>
      <div class="book-item-meta">
        <div class="type-dot ${b.content_type||'legal'}"></div>
        <span class="branch-badge">${esc(b.branch||'General')}</span>
        ${b.rating ? '⭐'.repeat(b.rating) : ''}
      </div>
    </div>`).join('');
}

function renderHome(books) {
  const byType = {};
  books.forEach(b => { const t = b.content_type||'other'; byType[t]=(byType[t]||0)+1; });
  const pages = books.reduce((s,b)=>s+(b.pages||0),0);
  document.getElementById('home-stats').innerHTML = `
    <div class="stat-card"><div class="stat-num">${books.length}</div><div class="stat-label">Libros</div></div>
    <div class="stat-card"><div class="stat-num">${pages}</div><div class="stat-label">Páginas</div></div>
    <div class="stat-card"><div class="stat-num">${byType['legal']||0}</div><div class="stat-label">Jurídicos</div></div>
    <div class="stat-card"><div class="stat-num">${(byType['tech']||0)+(byType['data_science']||0)}</div><div class="stat-label">Tech</div></div>`;

  const recent = document.getElementById('recent-books');
  if (!books.length) {
    recent.innerHTML = '<div class="empty-state" style="padding:2rem 0">Agrega tu primer libro o artículo para comenzar.</div>';
    return;
  }
  recent.innerHTML = `
    <div class="recent-label">Recientes</div>
    <div class="recent-cards">
      ${books.slice(0,8).map(b=>`
        <div class="recent-card" onclick="openBook(${b.id})">
          <div class="rc-type ${b.content_type||'legal'}">${TYPE_LABELS[b.content_type]||'📚 General'}</div>
          <div class="rc-title">${esc(b.title)}</div>
          <div class="rc-author">${esc(b.author||'')}</div>
        </div>`).join('')}
    </div>`;
}

/* ── BOOK DETAIL ──────────────────── */
async function openBook(id) {
  STATE.currentBookId = id;
  STATE.chatBookId = id;
  closeSidebarMobile();
  switchView('book');

  const book = await api(`/api/books/${id}`);
  document.getElementById('topbar-title').textContent = book.title;
  document.getElementById('topbar-actions').innerHTML = `
    <button onclick="switchView('chat');loadChat(${id})" id="btn-chat-tab">💬 Chat</button>
    <button onclick="switchView('home');STATE.currentBookId=null">← Inicio</button>`;

  const ct = book.content_type || 'legal';
  const kc = book.key_concepts||[];
  const norms = book.norms||[];
  const juris = book.jurisprudence||[];
  const exam = book.exam_questions||[];
  const chaps = book.chapter_map||[];
  const tools = book.tools_frameworks||[];
  const actions = book.action_items||[];

  const subjects = await api('/api/academic/subjects');
  const subjectOpts = subjects.map(s=>`<option value="${esc(s.name)}" ${s.name===book.subject_link?'selected':''}>${esc(s.name)}</option>`).join('');

  document.getElementById('book-content').innerHTML = `
    <div class="book-header">
      <div class="content-type-badge ${ct}">${TYPE_LABELS[ct]||ct}</div>
      <h1 class="book-title">${esc(book.title)}</h1>
      <p class="book-author">${esc(book.author||'Autor desconocido')}</p>
      <div class="book-meta-row">
        ${book.year&&book.year!=='---'?`<div class="book-meta-item"><span class="meta-label">Año</span><span class="meta-val">${esc(book.year)}</span></div>`:''}
        ${book.pages?`<div class="book-meta-item"><span class="meta-label">Páginas</span><span class="meta-val">${book.pages}</span></div>`:''}
        <div class="book-meta-item"><span class="meta-label">Calificación</span>
          <div class="book-rating" id="rating-${id}">
            ${[1,2,3,4,5].map(i=>`<span class="star ${book.rating>=i?'on':''}" onclick="setRating(${id},${i})">⭐</span>`).join('')}
          </div>
        </div>
      </div>
    </div>

    <div class="section-title">Resumen</div>
    <div class="summary-box">${esc(book.summary||'')}</div>

    ${kc.length?`<div class="section-title">Conceptos clave (${kc.length})</div>
    <div class="cards-grid">${kc.map(c=>`<div class="detail-card">
      <div class="card-term">${esc(c.term||'')}</div>
      <div class="card-def">${esc(c.definition||'')}</div>
      ${c.context?`<div class="card-ctx">${esc(c.context)}</div>`:''}
    </div>`).join('')}</div>`:''}

    ${tools.length?`<div class="section-title">Herramientas y frameworks (${tools.length})</div>
    <div class="cards-grid">${tools.map(t=>`<div class="detail-card">
      <div class="card-term tech">${esc(t.name||'')}</div>
      <div class="card-def">${esc(t.purpose||'')}</div>
      ${t.when_to_use?`<div class="card-ctx">Cuándo usarlo: ${esc(t.when_to_use)}</div>`:''}
    </div>`).join('')}</div>`:''}

    ${actions.length?`<div class="section-title">Acciones prácticas (${actions.length})</div>
    <div class="cards-grid">${actions.map(a=>`<div class="detail-card">
      <div class="card-term green">✅ ${esc(a.action||'')}</div>
      <div class="card-def">${esc(a.context||'')}</div>
      ${a.benefit?`<div class="card-ctx">Beneficio: ${esc(a.benefit)}</div>`:''}
    </div>`).join('')}</div>`:''}

    ${norms.length?`<div class="section-title">${ct==='legal'?'Normas y artículos':'Fuentes citadas'} (${norms.length})</div>
    <div class="cards-grid">${norms.map(n=>`<div class="detail-card">
      <div class="card-term orange">⚖️ ${esc(n.norm||'')}</div>
      <div class="card-def">${esc(n.content||'')}</div>
      ${n.relevance?`<div class="card-ctx">${esc(n.relevance)}</div>`:''}
    </div>`).join('')}</div>`:''}

    ${juris.length?`<div class="section-title">Jurisprudencia (${juris.length})</div>
    <div class="cards-grid">${juris.map(j=>`<div class="detail-card">
      <div class="card-term" style="color:var(--success)">📋 ${esc(j.case||'')}</div>
      <div class="card-ctx">${esc(j.court||'')}</div>
      <div class="card-def">${esc(j.contribution||'')}</div>
    </div>`).join('')}</div>`:''}

    ${exam.length?`<div class="section-title">Preguntas de estudio (${exam.length})</div>
    <div class="cards-grid">${exam.map((q,i)=>`<div class="detail-card">
      <div class="exam-q">${i+1}. ${esc(q.question||'')}</div>
      ${q.hint?`<div class="exam-hint">${esc(q.hint)}</div>`:''}
    </div>`).join('')}</div>`:''}

    ${chaps.length?`<div class="section-title">Estructura</div>
    <div class="cards-grid">${chaps.map(c=>`<div class="detail-card">
      <div class="card-term">📖 ${esc(c.chapter||'')}</div>
      <div class="chapter-topics">${(c.topics||[]).map(t=>`<span class="topic-tag">${esc(t)}</span>`).join('')}</div>
    </div>`).join('')}</div>`:''}

    ${subjects.length?`<div class="section-title">Vincular a materia</div>
    <div class="subject-link-row">
      <select id="subject-select-${id}" onchange="saveSubjectLink(${id})">
        <option value="">Sin vincular</option>${subjectOpts}
      </select>
    </div>`:''}

    <div class="section-title">Mis notas</div>
    <textarea class="notes-area" id="notes-${id}" placeholder="Escribe tus apuntes personales…">${esc(book.personal_notes||'')}</textarea>
    <button class="save-btn" onclick="saveNotes(${id})">Guardar notas</button>

    <div class="danger-zone">
      <button class="delete-btn" onclick="deleteBook(${id})">🗑 Eliminar</button>
    </div>`;

  document.querySelectorAll('.book-item').forEach(el => {
    el.classList.toggle('active', el.onclick?.toString().includes(`openBook(${id})`));
  });
}

async function setRating(bookId, stars) {
  await api(`/api/books/${bookId}`, 'PATCH', { rating: stars });
  document.querySelectorAll(`#rating-${bookId} .star`).forEach((s,i)=>s.classList.toggle('on',i<stars));
  toast('Calificación guardada ⭐', 'success');
}

async function saveNotes(bookId) {
  const notes = document.getElementById(`notes-${bookId}`).value;
  await api(`/api/books/${bookId}`, 'PATCH', { personal_notes: notes });
  toast('Notas guardadas ✓', 'success');
}

async function saveSubjectLink(bookId) {
  const val = document.getElementById(`subject-select-${bookId}`)?.value || '';
  await api(`/api/books/${bookId}`, 'PATCH', { subject_link: val });
  toast('Materia vinculada ✓', 'success');
}

async function deleteBook(bookId) {
  if (!confirm('¿Eliminar este libro del catálogo?')) return;
  await api(`/api/books/${bookId}`, 'DELETE');
  STATE.currentBookId = null;
  toast('Eliminado ✓', 'success');
  loadBooks();
  switchView('home');
}

/* ── CHAT ─────────────────────────── */
async function loadChat(bookId) {
  STATE.chatBookId = bookId;
  document.getElementById('topbar-actions').querySelector('button')?.classList.add('active-tab');
  const msgs = await api(`/api/books/${bookId}/chat`);
  const container = document.getElementById('chat-messages');
  const book = STATE.books.find(b=>b.id===bookId)||{};

  if (!msgs.length) {
    const suggestions = {
      legal: ['¿Cuál es el concepto más importante?','Explícame las normas citadas','Hazme una pregunta de examen','Repaso rápido para parcial'],
      tech: ['¿Qué tecnologías cubre este libro?','Dame un ejemplo práctico del tema central','¿Cuáles son los conceptos más difíciles?','Resúmeme los puntos clave'],
      data_science: ['¿Qué algoritmos se cubren?','Explícame el concepto más importante','Dame un ejercicio práctico','¿Cuáles herramientas se usan?'],
      personal: ['¿Cuál es la idea principal del libro?','Dame las 3 acciones más importantes','¿Cómo aplico esto en mi vida?','Resúmeme por capítulos'],
      article: ['¿Cuál es el argumento central?','¿Qué evidencias usa el autor?','Dame un análisis crítico','¿Con qué puedo estar en desacuerdo?']
    };
    const ct = book.content_type || 'legal';
    const sugs = suggestions[ct] || suggestions.legal;
    container.innerHTML = `<div class="chat-empty">
      <div style="font-size:2rem">💬</div>
      <p>Chatea con <strong>${esc(book.title||'este libro')}</strong></p>
      <div class="chat-suggestions">
        ${sugs.map(s=>`<button class="suggestion-btn" onclick="sendSuggestion('${s.replace(/'/g,"\\'")}')">${s}</button>`).join('')}
      </div>
    </div>`;
    return;
  }
  container.innerHTML = msgs.map(m=>renderMsg(m.role, m.content, m.created_at)).join('');
  container.scrollTop = container.scrollHeight;
}

function renderMsg(role, content, time) {
  const t = time ? new Date(time).toLocaleTimeString('es-CO',{hour:'2-digit',minute:'2-digit'}) : '';
  return `<div class="msg ${role}">
    <div class="msg-bubble">${esc(content)}</div>
    ${t?`<div class="msg-time">${t}</div>`:''}
  </div>`;
}

function sendSuggestion(text) {
  document.getElementById('chat-input').value = text;
  sendChat();
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const msg = input.value.trim();
  if (!msg || !STATE.chatBookId) return;
  input.value = '';
  const container = document.getElementById('chat-messages');
  container.querySelector('.chat-empty')?.remove();
  container.insertAdjacentHTML('beforeend', renderMsg('user', msg, new Date().toISOString()));
  container.insertAdjacentHTML('beforeend', `<div class="msg assistant" id="typing"><div class="msg-bubble"><span class="loading-spinner"></span>Pensando…</div></div>`);
  container.scrollTop = container.scrollHeight;

  const res = await api(`/api/books/${STATE.chatBookId}/chat`, 'POST', { message: msg });
  document.getElementById('typing')?.remove();
  container.insertAdjacentHTML('beforeend', renderMsg('assistant', res.error ? '❌ '+res.error : res.reply, new Date().toISOString()));
  container.scrollTop = container.scrollHeight;
}

/* ── ADD CONTENT MODAL ────────────── */
function openAdd() {
  STATE.selectedFile = null;
  STATE.srcType = 'pdf';
  document.getElementById('file-selected-info').classList.add('hidden');
  document.getElementById('add-progress').classList.add('hidden');
  document.getElementById('url-input').value = '';
  openModal('modal-add');
}

function setSrcTab(type, btn) {
  STATE.srcType = type;
  document.querySelectorAll('.src-tab').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.src-panel').forEach(p=>p.classList.remove('active'));
  document.getElementById('src-'+type).classList.add('active');
}

function handleFileSelect(input, type) {
  const file = input.files[0];
  if (!file) return;
  STATE.selectedFile = file;
  STATE.srcType = type;
  const info = document.getElementById('file-selected-info');
  info.classList.remove('hidden');
  info.textContent = `📄 ${file.name} (${(file.size/1024/1024).toFixed(1)} MB)`;
}

async function doAdd() {
  const prog = document.getElementById('add-progress');
  const fill = document.getElementById('add-progress-fill');
  const text = document.getElementById('add-progress-text');
  prog.classList.remove('hidden');

  const steps = ['Extrayendo contenido…','Detectando tipo de libro…','Analizando con IA…','Generando preguntas…','Guardando en catálogo…'];
  let step = 0;
  const iv = setInterval(()=>{fill.style.width=Math.min(90,(step+1)/steps.length*100)+'%';text.textContent=steps[Math.min(step,steps.length-1)];step++;},2200);

  const formData = new FormData();

  if (STATE.srcType === 'url') {
    const url = document.getElementById('url-input').value.trim();
    if (!url) { clearInterval(iv); prog.classList.add('hidden'); return toast('Ingresa una URL válida','error'); }
    formData.append('source_type','url');
    formData.append('url', url);
  } else {
    if (!STATE.selectedFile) { clearInterval(iv); prog.classList.add('hidden'); return toast('Selecciona un archivo','error'); }
    formData.append('source_type', STATE.srcType);
    formData.append('file', STATE.selectedFile);
  }

  try {
    const res = await fetch('/api/upload', { method:'POST', body:formData });
    const data = await res.json();
    clearInterval(iv);
    if (data.error) { prog.classList.add('hidden'); return toast(data.error,'error'); }
    fill.style.width='100%';
    text.textContent='✓ ¡Guardado exitosamente!';
    setTimeout(()=>{
      closeModal('modal-add');
      loadBooks();
      toast(`"${data.title}" agregado ✓`,'success');
      setTimeout(()=>openBook(data.book_id),400);
    },900);
  } catch(e) {
    clearInterval(iv);
    prog.classList.add('hidden');
    toast('Error de conexión','error');
  }
}

/* ── ACADEMIC ─────────────────────── */
function openAcademic() {
  switchView('academic');
  document.getElementById('topbar-title').textContent = 'Malla y horarios';
  document.getElementById('topbar-actions').innerHTML = `<button onclick="switchView('home')">← Inicio</button>`;
  loadAcademicData();
}

async function uploadAcademic(file) {
  if (!file) return;
  toast('Procesando con IA…');
  const formData = new FormData();
  formData.append('file', file);
  formData.append('doc_type', 'malla');
  const res = await fetch('/api/academic/upload', { method:'POST', body:formData });
  const data = await res.json();
  if (data.error) return toast(data.error,'error');
  toast('Malla procesada ✓','success');
  loadAcademicData();
}

async function loadAcademicData() {
  const data = await api('/api/academic/data');
  const list = document.getElementById('academic-list');
  if (!data.length) { list.innerHTML = '<p class="muted-text">Aún no has subido ninguna malla ni horario.</p>'; return; }
  list.innerHTML = data.map(d => {
    const parsed = d.parsed || {};
    const subjects = parsed.subjects || [];
    return `<div class="academic-item">
      <div class="academic-item-title">${esc(parsed.career || d.type)} ${parsed.university?'— '+esc(parsed.university):''}</div>
      <div class="subject-chips">
        ${subjects.slice(0,20).map(s=>`<span class="subject-chip">${esc(s.name)}</span>`).join('')}
        ${subjects.length>20?`<span class="subject-chip">+${subjects.length-20} más</span>`:''}
      </div>
    </div>`;
  }).join('');
}

/* ── SETTINGS ─────────────────────── */
function openSettings() {
  switchView('settings');
  document.getElementById('topbar-title').textContent = 'Configuración';
  document.getElementById('topbar-actions').innerHTML = `<button onclick="switchView('home')">← Inicio</button>`;
  if (STATE.user?.api_key) document.getElementById('settings-apikey').value = STATE.user.api_key;
}

async function saveApiKey() {
  const key = document.getElementById('settings-apikey').value.trim();
  if (!key.startsWith('sk-')) return toast('La API key debe empezar con sk-','error');
  const res = await api('/api/auth/update_key','POST',{api_key:key});
  if (res.ok) { STATE.user.api_key = key; toast('API key guardada ✓','success'); }
}

/* ── VIEWS & NAVIGATION ───────────── */
function switchView(name) {
  STATE.currentView = name;
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
  document.getElementById('view-'+name)?.classList.add('active');
  if (name==='chat' && STATE.chatBookId) loadChat(STATE.chatBookId);
}

function showScreen(name) {
  document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));
  document.getElementById('screen-'+name)?.classList.add('active');
}

function toggleSidebar() { document.getElementById('sidebar').classList.toggle('open'); }
function closeSidebarMobile() { if(window.innerWidth<=640) document.getElementById('sidebar').classList.remove('open'); }
function openModal(id) { document.getElementById(id).classList.remove('hidden'); }
function closeModal(id) { document.getElementById(id).classList.add('hidden'); }

/* ── API HELPER ───────────────────── */
async function api(url, method='GET', body=null) {
  const opts = { method, headers:{'Content-Type':'application/json'} };
  if (body) opts.body = JSON.stringify(body);
  try {
    const res = await fetch(url, opts);
    return await res.json();
  } catch(e) { return {error:'Error de red'}; }
}

/* ── TOAST ────────────────────────── */
let toastTimer;
function toast(msg, type='') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast' + (type?' '+type:'');
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=>t.classList.add('hidden'),3000);
}

/* ── HELPERS ──────────────────────── */
function esc(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

/* ── PWA ──────────────────────────── */
if('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js').catch(()=>{});
