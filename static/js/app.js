/* ══════════════════════════════════════
   MARISI READER v3 — App JS
══════════════════════════════════════ */

let STATE = {
  user: null,
  books: [],
  currentBookId: null,
  currentView: 'home',
  currentBookTab: 'overview',
  chatBookId: null,
  selectedFile: null,
  srcType: 'pdf',
  obStep: 0,
  obAnswers: {},
  obStructuredAnswers: {},
  obOpenAnswers: {},
  obQuestions: [],
  obOpenQuestions: [],
  obPhase: 'structured' // 'structured' | 'open' | 'done'
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

/* ── ONBOARDING v2 ────────────────── */
async function startOnboarding() {
  showScreen('onboarding');
  STATE.obPhase = 'structured';
  STATE.obStep = 0;
  STATE.obAnswers = {};
  STATE.obStructuredAnswers = {};
  STATE.obOpenAnswers = {};

  const [structured, open] = await Promise.all([
    api('/api/onboarding/questions'),
    api('/api/onboarding/open-questions')
  ]);
  STATE.obQuestions = structured;
  STATE.obOpenQuestions = open;
  renderObStep();
}

function renderObStep() {
  const isOpen = STATE.obPhase === 'open';
  const questions = isOpen ? STATE.obOpenQuestions : STATE.obQuestions;
  const total = STATE.obQuestions.length + STATE.obOpenQuestions.length;
  const globalStep = isOpen ? STATE.obQuestions.length + STATE.obStep : STATE.obStep;

  document.getElementById('ob-progress-fill').style.width = `${((globalStep + 1) / total) * 100}%`;
  document.getElementById('ob-step-counter').textContent = `${globalStep + 1} / ${total}`;
  document.getElementById('ob-back').style.display = (globalStep > 0) ? 'block' : 'none';

  const isLastQuestion = isOpen
    ? STATE.obStep === STATE.obOpenQuestions.length - 1
    : STATE.obStep === STATE.obQuestions.length - 1 && STATE.obOpenQuestions.length === 0;
  const isLastOverall = isOpen && STATE.obStep === STATE.obOpenQuestions.length - 1;

  document.getElementById('ob-next').textContent = isLastOverall ? 'Finalizar y conocerme ✨' : 'Siguiente →';

  const q = questions[STATE.obStep];
  if (!q) return;

  // Update part label
  if (!isOpen) {
    document.getElementById('ob-phase-label').textContent = q.part || '¿Cómo piensas?';
  } else {
    document.getElementById('ob-phase-label').textContent = '🔍 Conocerte de verdad';
    document.getElementById('ob-main-title').innerHTML = 'Ahora las preguntas importantes <span>💭</span>';
    document.getElementById('ob-subtitle').textContent = 'Estas respuestas me ayudan a entender cómo piensas, no solo qué lees.';
  }

  if (isOpen) {
    const current = STATE.obOpenAnswers[q.id] || '';
    document.getElementById('onboarding-question').innerHTML = `
      <div class="ob-question">
        <h3>${esc(q.question)}</h3>
        <textarea class="ob-open-textarea" id="ob-open-${q.id}" placeholder="Escribe tu respuesta aquí…">${esc(current)}</textarea>
      </div>`;
    document.getElementById(`ob-open-${q.id}`).addEventListener('input', e => {
      STATE.obOpenAnswers[q.id] = e.target.value;
    });
  } else {
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
}

function selectOb(qid, value, isMulti) {
  if (isMulti) {
    let arr = STATE.obAnswers[qid] || [];
    arr = arr.includes(value) ? arr.filter(v=>v!==value) : [...arr, value];
    STATE.obAnswers[qid] = arr;
  } else {
    STATE.obAnswers[qid] = value;
  }
  STATE.obStructuredAnswers[qid] = STATE.obAnswers[qid];
  renderObStep();
}

function obBack() {
  if (STATE.obPhase === 'open' && STATE.obStep === 0) {
    STATE.obPhase = 'structured';
    STATE.obStep = STATE.obQuestions.length - 1;
  } else if (STATE.obStep > 0) {
    STATE.obStep--;
  }
  renderObStep();
}

async function obNext() {
  const isOpen = STATE.obPhase === 'open';
  const q = isOpen ? STATE.obOpenQuestions[STATE.obStep] : STATE.obQuestions[STATE.obStep];

  if (isOpen) {
    const ans = STATE.obOpenAnswers[q.id] || '';
    if (ans.trim().length < 5) return toast('Escribe una respuesta antes de continuar', 'error');

    if (STATE.obStep < STATE.obOpenQuestions.length - 1) {
      STATE.obStep++;
      renderObStep();
    } else {
      await finishOnboarding();
    }
  } else {
    const ans = STATE.obAnswers[q.id];
    if (!ans || (Array.isArray(ans) && !ans.length)) return toast('Selecciona al menos una opción', 'error');
    STATE.obStructuredAnswers[q.id] = ans;

    if (STATE.obStep < STATE.obQuestions.length - 1) {
      STATE.obStep++;
      renderObStep();
    } else {
      // Transición a preguntas abiertas
      STATE.obPhase = 'open';
      STATE.obStep = 0;
      renderObStep();
    }
  }
}

async function finishOnboarding() {
  document.getElementById('ob-next').textContent = 'Analizando tu perfil…';
  document.getElementById('ob-next').disabled = true;

  // Mostrar pantalla de procesamiento
  document.getElementById('onboarding-question').innerHTML = `
    <div class="ob-processing">
      <div class="ob-processing-icon">🧠</div>
      <h3>Construyendo tu perfil intelectual…</h3>
      <p class="muted-text">La IA está analizando tus respuestas para entender cómo piensas, qué valoras y cómo aprendes.</p>
      <div class="ob-processing-bar"><div class="ob-processing-fill"></div></div>
    </div>`;

  const res = await api('/api/onboarding/save-full', 'POST', {
    structured: STATE.obStructuredAnswers,
    open: STATE.obOpenAnswers
  });

  if (res.error) {
    toast(res.error, 'error');
    document.getElementById('ob-next').disabled = false;
    document.getElementById('ob-next').textContent = 'Finalizar y conocerme ✨';
    return;
  }

  if (res.intellectual_type) {
    document.getElementById('onboarding-question').innerHTML = `
      <div class="ob-result">
        <div class="ob-result-icon">✨</div>
        <div class="ob-result-type">${esc(res.intellectual_type)}</div>
        <p class="ob-result-summary">${esc(res.profile_summary || 'Tu perfil intelectual ha sido creado. Marisi ahora te conoce mejor.')}</p>
      </div>`;
    document.getElementById('ob-next').textContent = 'Ir a mi biblioteca →';
    document.getElementById('ob-next').disabled = false;
    document.getElementById('ob-next').onclick = () => enterApp();
    document.getElementById('ob-back').style.display = 'none';
  } else {
    enterApp();
  }
}

async function restartOnboarding() {
  STATE.user.onboarding_done = false;
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
  switchBookTab('overview');

  const book = await api(`/api/books/${id}`);
  document.getElementById('topbar-title').textContent = book.title;
  document.getElementById('topbar-actions').innerHTML = `
    <button onclick="switchView('chat');loadChat(${id})">💬 Chat</button>
    <button onclick="openGame(${id})">🎮 Jugar</button>
    <button onclick="switchView('home');STATE.currentBookId=null">← Inicio</button>`;

  renderBookOverview(book, id);
  renderBookList(STATE.books);
}

function switchBookTab(tab) {
  STATE.currentBookTab = tab;
  document.querySelectorAll('.book-tab').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.book-tab-panel').forEach(p => p.classList.remove('active'));
  document.getElementById(`btab-${tab}`)?.classList.add('active');
  document.getElementById(`book-tab-${tab}`)?.classList.add('active');

  const id = STATE.currentBookId;
  if (!id) return;

  if (tab === 'reflection') renderReflectionTab(id);
  if (tab === 'debate') renderDebateTab(id);
  if (tab === 'characters') renderCharactersTab(id);
  if (tab === 'memory') renderMemoryTab(id);
  if (tab === 'connections') renderConnectionsTab(id);
}

function renderBookOverview(book, id) {
  const ct = book.content_type || 'legal';
  const kc = book.key_concepts||[];
  const norms = book.norms||[];
  const juris = book.jurisprudence||[];
  const exam = book.exam_questions||[];
  const chaps = book.chapter_map||[];
  const tools = book.tools_frameworks||[];
  const actions = book.action_items||[];

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

    <div class="section-title">Mis notas</div>
    <textarea class="notes-area" id="notes-${id}" placeholder="Escribe tus apuntes personales…">${esc(book.personal_notes||'')}</textarea>
    <button class="save-btn" onclick="saveNotes(${id})">Guardar notas</button>

    <div class="danger-zone">
      <button class="delete-btn" onclick="deleteBook(${id})">🗑 Eliminar</button>
    </div>`;
}

/* ── PESTAÑA: REFLEXIÓN ───────────── */
async function renderReflectionTab(id) {
  const el = document.getElementById('reflection-content');
  el.innerHTML = `<div class="tab-loading"><span class="loading-spinner"></span>Cargando reflexiones…</div>`;

  const existing = await api(`/api/books/${id}/reflection`);

  if (existing.length) {
    const byPhase = {};
    existing.forEach(r => { if (!byPhase[r.phase]) byPhase[r.phase] = []; byPhase[r.phase].push(r); });
    const phaseLabels = { before: 'Antes de leer', after: 'Después de leer', revisit: 'Revisitando' };

    el.innerHTML = `
      <h2 class="section-h2">🪞 Mis reflexiones</h2>
      ${Object.entries(byPhase).map(([phase, items]) => `
        <div class="section-title">${phaseLabels[phase] || phase}</div>
        <div class="reflection-list">
          ${items.map(r => `<div class="reflection-item">
            <div class="reflection-q">${esc(r.question)}</div>
            <div class="reflection-a">${esc(r.answer)}</div>
          </div>`).join('')}
        </div>
      `).join('')}
      <div style="margin-top:2rem">
        <div class="section-title">Nueva reflexión</div>
        <div class="phase-selector">
          <button class="phase-btn active" onclick="selectPhase(this,'after')">Después de leer</button>
          <button class="phase-btn" onclick="selectPhase(this,'revisit')">Revisitar</button>
        </div>
        <button class="btn-primary" style="margin-top:1rem" onclick="startReflection(${id}, document.querySelector('.phase-btn.active')?.dataset?.phase || 'after')">
          Generar nuevas preguntas →
        </button>
      </div>`;
  } else {
    el.innerHTML = `
      <div class="reflection-intro">
        <div style="font-size:2.5rem;margin-bottom:1rem">🪞</div>
        <h2 class="section-h2">Reflexión sobre el libro</h2>
        <p class="muted-text" style="margin-bottom:1.5rem">La IA genera preguntas personalizadas para ti sobre este libro. Tus respuestas construyen tu perfil intelectual y me ayudan a entender cómo te afectó la lectura.</p>
        <div class="phase-selector">
          <button class="phase-btn active" data-phase="before" onclick="selectPhase(this,'before')">Antes de leer</button>
          <button class="phase-btn" data-phase="after" onclick="selectPhase(this,'after')">Después de leer</button>
          <button class="phase-btn" data-phase="revisit" onclick="selectPhase(this,'revisit')">Revisitar</button>
        </div>
        <button class="btn-primary" style="margin-top:1.5rem;max-width:300px" onclick="startReflection(${id}, document.querySelector('.phase-btn.active')?.dataset?.phase || 'after')">
          Comenzar reflexión →
        </button>
      </div>`;
  }
}

function selectPhase(btn, phase) {
  document.querySelectorAll('.phase-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  btn.dataset.phase = phase;
}

async function startReflection(bookId, phase) {
  const el = document.getElementById('reflection-content');
  el.innerHTML = `<div class="tab-loading"><span class="loading-spinner"></span>Generando preguntas personalizadas para ti…</div>`;

  const res = await api(`/api/books/${bookId}/reflection/questions`, 'POST', { phase });
  if (res.error) return el.innerHTML = `<p class="error-msg">${esc(res.error)}</p>`;

  const questions = res.questions;
  const answers = {};

  el.innerHTML = `
    <h2 class="section-h2">🪞 Reflexión — ${phase === 'before' ? 'Antes de leer' : phase === 'revisit' ? 'Revisitando' : 'Después de leer'}</h2>
    <p class="muted-text" style="margin-bottom:1.5rem">Estas preguntas fueron generadas especialmente para ti. No hay respuestas correctas.</p>
    <div id="reflection-questions">
      ${questions.map((q,i) => `
        <div class="reflection-q-card">
          <div class="reflection-q-num">Pregunta ${i+1}</div>
          <div class="reflection-q-text">${esc(q.question)}</div>
          <textarea class="reflection-answer-input" id="ra-${i}" placeholder="Escribe tu respuesta…" rows="3"></textarea>
        </div>`).join('')}
    </div>
    <button class="btn-primary" style="margin-top:1.5rem" onclick="submitReflection(${bookId},'${phase}',${JSON.stringify(questions).replace(/</g,'\\u003c')})">
      Guardar reflexiones y actualizar mi perfil →
    </button>`;
}

async function submitReflection(bookId, phase, questions) {
  const answers = questions.map((q, i) => ({
    question: q.question,
    answer: document.getElementById(`ra-${i}`)?.value || ''
  })).filter(a => a.answer.trim().length > 0);

  if (!answers.length) return toast('Responde al menos una pregunta', 'error');

  const el = document.getElementById('reflection-content');
  el.innerHTML = `<div class="tab-loading"><span class="loading-spinner"></span>Analizando tus respuestas y actualizando tu perfil…</div>`;

  const res = await api(`/api/books/${bookId}/reflection/save`, 'POST', { phase, answers });
  if (res.error) return el.innerHTML = `<p class="error-msg">${esc(res.error)}</p>`;

  let insightHtml = '';
  if (res.mind_change) insightHtml += `<div class="insight-card mind-change"><div class="insight-label">💡 Cambio en tu pensamiento</div><p>${esc(res.mind_change)}</p></div>`;
  if (res.emotional_impact) insightHtml += `<div class="insight-card emotional"><div class="insight-label">❤️ Impacto emocional detectado</div><p>${esc(res.emotional_impact)}</p></div>`;
  if (res.cross_book_insight) insightHtml += `<div class="insight-card cross"><div class="insight-label">🔗 Conexión con otros libros</div><p>${esc(res.cross_book_insight)}</p></div>`;

  el.innerHTML = `
    <div class="reflection-result">
      <div style="font-size:2rem;margin-bottom:1rem">✅</div>
      <h3>Reflexión guardada</h3>
      <p class="muted-text">Tu perfil intelectual ha sido actualizado con lo que aprendí de ti en esta reflexión.</p>
      ${insightHtml}
      <div style="display:flex;gap:.75rem;margin-top:1.5rem;flex-wrap:wrap">
        <button class="btn-primary" onclick="renderReflectionTab(${bookId})">Ver todas mis reflexiones</button>
        <button class="btn-ghost" onclick="openMindProfile()">Ver mi perfil →</button>
      </div>
    </div>`;
}

/* ── PESTAÑA: DEBATE ──────────────── */
async function renderDebateTab(id) {
  const el = document.getElementById('debate-content');
  el.innerHTML = `
    <h2 class="section-h2">⚔️ Debate filosófico</h2>
    <p class="muted-text" style="margin-bottom:1.5rem">La IA genera un debate entre el autor de este libro y otro pensador histórico o contemporáneo sobre las ideas centrales de la obra.</p>
    <div class="debate-controls">
      <input type="text" id="debate-opponent" class="debate-opponent-input" placeholder="Oponente (opcional, ej: Nietzsche, Frankl…)">
      <button class="btn-primary" onclick="loadDebate(${id})">Generar debate →</button>
    </div>
    <div id="debate-result" style="margin-top:1.5rem"></div>`;

  // Auto-cargar si ya hay debate guardado
  loadDebate(id, false);
}

async function loadDebate(bookId, force = true) {
  const opponent = document.getElementById('debate-opponent')?.value?.trim() || null;
  const el = document.getElementById('debate-result');
  el.innerHTML = `<div class="tab-loading"><span class="loading-spinner"></span>Generando debate…</div>`;

  const params = new URLSearchParams();
  if (force) params.set('force', 'true');
  if (opponent) params.set('opponent', opponent);

  const res = await api(`/api/books/${bookId}/debate?${params}`);
  if (res.error) { el.innerHTML = `<p class="muted-text">${esc(res.error)}</p>`; return; }

  const d = res.debate;
  if (!d || d.error) { el.innerHTML = `<p class="muted-text">Genera tu primer debate usando el botón de arriba.</p>`; return; }

  el.innerHTML = `
    <div class="debate-card">
      <div class="debate-vs">${esc(d.participant_a)} <span class="vs-badge">vs</span> ${esc(d.participant_b)}</div>
      ${d.why_this_opponent ? `<div class="debate-why muted-text">${esc(d.why_this_opponent)}</div>` : ''}
      ${d.central_tension ? `<div class="debate-tension">⚡ ${esc(d.central_tension)}</div>` : ''}
      <div class="debate-exchanges">
        ${(d.exchanges||[]).map(e => `
          <div class="debate-exchange ${e.speaker === d.participant_a ? 'left' : 'right'}">
            <div class="debate-speaker">${esc(e.speaker)}</div>
            <div class="debate-text">${esc(e.text)}</div>
            ${e.subtext ? `<div class="debate-subtext">${esc(e.subtext)}</div>` : ''}
          </div>`).join('')}
      </div>
      ${d.conclusion ? `<div class="debate-conclusion"><div class="section-title">Síntesis</div><p>${esc(d.conclusion)}</p></div>` : ''}
    </div>`;
}

/* ── PESTAÑA: PERSONAJES ──────────── */
function renderCharactersTab(id) {
  const book = STATE.books.find(b => b.id === id) || {};
  const el = document.getElementById('characters-content');
  el.innerHTML = `
    <h2 class="section-h2">🎭 Simulación de personajes</h2>
    <p class="muted-text" style="margin-bottom:1.5rem">Pregúntale a cualquier autor o personaje de este libro cómo respondería a una situación concreta.</p>
    <div class="character-sim-form">
      <div class="field">
        <label>Personaje o autor</label>
        <input type="text" id="char-name" class="settings-input" placeholder="Ej: Meursault, Albert Camus, el narrador…">
      </div>
      <div class="field" style="margin-top:.75rem">
        <label>Tu pregunta o situación</label>
        <textarea id="char-question" class="notes-area" rows="3" placeholder="Ej: ¿Qué harías si tuvieras que defender a alguien en un juicio? ¿Qué opinas de las redes sociales?"></textarea>
      </div>
      <button class="btn-primary" style="margin-top:1rem" onclick="runCharacterSim(${id})">Simular respuesta →</button>
    </div>
    <div id="char-result" style="margin-top:1.5rem"></div>`;
}

async function runCharacterSim(bookId) {
  const character = document.getElementById('char-name')?.value?.trim();
  const question = document.getElementById('char-question')?.value?.trim();
  if (!character || !question) return toast('Completa el personaje y la pregunta', 'error');

  const el = document.getElementById('char-result');
  el.innerHTML = `<div class="tab-loading"><span class="loading-spinner"></span>Invocando a ${esc(character)}…</div>`;

  const res = await api(`/api/books/${bookId}/character-sim`, 'POST', { character, question });
  if (res.error) { el.innerHTML = `<p class="error-msg">${esc(res.error)}</p>`; return; }

  el.innerHTML = `
    <div class="char-response-card">
      <div class="char-name-badge">${esc(res.character || character)}</div>
      <div class="char-response">${esc(res.in_character_response || '')}</div>
      ${res.narrator_note ? `<div class="char-narrator"><div class="insight-label">📝 Nota del narrador</div><p>${esc(res.narrator_note)}</p></div>` : ''}
      ${res.follow_up_question ? `<div class="char-followup"><div class="insight-label">💬 ${esc(res.character || character)} te pregunta:</div><p class="char-followup-q">${esc(res.follow_up_question)}</p></div>` : ''}
    </div>
    <button class="btn-ghost" style="margin-top:1rem;width:100%" onclick="renderCharactersTab(${bookId})">Nueva simulación</button>`;
}

/* ── PESTAÑA: MEMORIA ─────────────── */
function renderMemoryTab(id) {
  const el = document.getElementById('memory-content');
  el.innerHTML = `
    <h2 class="section-h2">🧠 Recuerdo inteligente</h2>
    <p class="muted-text" style="margin-bottom:1.5rem">¿Qué recuerdas realmente de este libro? Responde libremente y detectaré qué conceptos dominaste, cuáles olvidaste y cuáles tienes confusos.</p>
    <div class="memory-form">
      <div class="field">
        <label>¿De qué trata este libro?</label>
        <textarea id="mem-summary" class="notes-area" rows="3" placeholder="Escribe lo que recuerdas del resumen…"></textarea>
      </div>
      <div class="field" style="margin-top:.75rem">
        <label>¿Cuáles son los conceptos principales que recuerdas?</label>
        <textarea id="mem-concepts" class="notes-area" rows="3" placeholder="Lista los conceptos que vienen a tu mente…"></textarea>
      </div>
      <div class="field" style="margin-top:.75rem">
        <label>¿Qué fue lo más importante que aprendiste?</label>
        <textarea id="mem-lesson" class="notes-area" rows="2" placeholder="La lección principal fue…"></textarea>
      </div>
      <button class="btn-primary" style="margin-top:1rem" onclick="runMemoryCheck(${id})">Analizar mi memoria →</button>
    </div>
    <div id="memory-result" style="margin-top:1.5rem"></div>`;
}

async function runMemoryCheck(bookId) {
  const answers = {
    summary: document.getElementById('mem-summary')?.value || '',
    concepts: document.getElementById('mem-concepts')?.value || '',
    main_lesson: document.getElementById('mem-lesson')?.value || ''
  };

  if (!answers.summary && !answers.concepts) return toast('Escribe algo antes de analizar', 'error');

  const el = document.getElementById('memory-result');
  el.innerHTML = `<div class="tab-loading"><span class="loading-spinner"></span>Analizando tu memoria…</div>`;

  const res = await api(`/api/books/${bookId}/memory-check`, 'POST', { answers });
  if (res.error) { el.innerHTML = `<p class="error-msg">${esc(res.error)}</p>`; return; }

  const scoreColor = res.retention_score >= 7 ? 'var(--success)' : res.retention_score >= 4 ? 'var(--gold)' : 'var(--danger)';

  el.innerHTML = `
    <div class="memory-result-card">
      <div class="memory-score-row">
        <div class="memory-score" style="color:${scoreColor}">${res.retention_score}/10</div>
        <div class="memory-label">${esc(res.retention_label || '')}</div>
      </div>
      ${res.mastered_concepts?.length ? `
        <div class="memory-section">
          <div class="insight-label" style="color:var(--success)">✅ Conceptos dominados</div>
          <ul class="memory-list">${res.mastered_concepts.map(c=>`<li>${esc(c)}</li>`).join('')}</ul>
        </div>` : ''}
      ${res.forgotten_concepts?.length ? `
        <div class="memory-section">
          <div class="insight-label" style="color:var(--danger)">❌ Conceptos olvidados</div>
          <ul class="memory-list">${res.forgotten_concepts.map(c=>`<li>${esc(c)}</li>`).join('')}</ul>
        </div>` : ''}
      ${res.confused_concepts?.length ? `
        <div class="memory-section">
          <div class="insight-label" style="color:var(--gold)">⚠️ Conceptos confusos</div>
          <ul class="memory-list">${res.confused_concepts.map(c=>`<li>${esc(c)}</li>`).join('')}</ul>
        </div>` : ''}
      ${res.personalized_review?.length ? `
        <div class="section-title" style="margin-top:1.5rem">Repaso personalizado</div>
        ${res.personalized_review.map(r=>`
          <div class="review-item">
            <div class="review-concept">${esc(r.concept)}</div>
            <div class="review-reminder">${esc(r.quick_reminder)}</div>
            ${r.memory_hook ? `<div class="review-hook">🪝 ${esc(r.memory_hook)}</div>` : ''}
          </div>`).join('')}` : ''}
    </div>`;
}

/* ── PESTAÑA: CONEXIONES ──────────── */
async function renderConnectionsTab(id) {
  const el = document.getElementById('connections-content');
  el.innerHTML = `<div class="tab-loading"><span class="loading-spinner"></span>Cargando conexiones…</div>`;

  const connections = await api(`/api/books/${id}/connections`);

  if (!connections.length) {
    el.innerHTML = `
      <h2 class="section-h2">🕸 Conexiones con tu biblioteca</h2>
      <p class="muted-text">Aún no hay conexiones detectadas. Las conexiones se generan automáticamente cuando tienes más libros en tu biblioteca y se analizan en segundo plano.</p>`;
    return;
  }

  const typeColors = { coincide: 'var(--success)', contradice: 'var(--danger)', complementa: 'var(--accent2)' };
  const typeLabels = { coincide: '🤝 Coincide', contradice: '⚡ Contradice', complementa: '🔗 Complementa' };

  el.innerHTML = `
    <h2 class="section-h2">🕸 Conexiones con tu biblioteca</h2>
    <p class="muted-text" style="margin-bottom:1.5rem">Este libro está relacionado con ${connections.length} libro${connections.length!==1?'s':''} de tu biblioteca.</p>
    <div class="connections-list">
      ${connections.map(c => `
        <div class="connection-card" onclick="openBook(${c.other_id})">
          <div class="connection-type" style="color:${typeColors[c.relation_type]||'var(--muted)'}">
            ${typeLabels[c.relation_type]||c.relation_type}
            <span class="connection-strength">${'●'.repeat(c.strength||1)}</span>
          </div>
          <div class="connection-book">${esc(c.other_title||'')} <span class="muted-text">— ${esc(c.other_author||'')}</span></div>
          ${c.summary ? `<div class="connection-summary">${esc(c.summary)}</div>` : ''}
          ${c.shared_concepts?.length ? `<div class="connection-concepts">${c.shared_concepts.map(s=>`<span class="topic-tag">${esc(s)}</span>`).join('')}</div>` : ''}
        </div>`).join('')}
    </div>`;
}

/* ── PERFIL INTELECTUAL ───────────── */
async function openMindProfile() {
  switchView('mind');
  document.getElementById('topbar-title').textContent = 'Mi perfil intelectual';
  document.getElementById('topbar-actions').innerHTML = `<button onclick="switchView('home')">← Inicio</button>`;

  const el = document.getElementById('mind-content');
  el.innerHTML = `<div class="tab-loading"><span class="loading-spinner"></span>Cargando tu perfil…</div>`;

  const mind = await api('/api/reader/mind');
  const evolution = await api('/api/reader/evolution');

  if (!mind.exists) {
    el.innerHTML = `
      <div style="text-align:center;padding:3rem 1rem">
        <div style="font-size:2.5rem;margin-bottom:1rem">🧠</div>
        <h2 class="section-h2">Tu perfil intelectual está en construcción</h2>
        <p class="muted-text">Completa el onboarding y reflexiona sobre tus libros para que Marisi te conozca mejor.</p>
        <button class="btn-primary" style="margin-top:1.5rem;max-width:240px" onclick="restartOnboarding()">Iniciar perfil →</button>
      </div>`;
    return;
  }

  el.innerHTML = `
    <div class="mind-header">
      <div class="mind-type">${esc(mind.intellectual_type || 'Lector en construcción')}</div>
      ${mind.profile_summary ? `<p class="mind-summary">${esc(mind.profile_summary)}</p>` : ''}
      <div class="mind-stats-row">
        <div class="mind-stat"><span class="mind-stat-num">${mind.stats?.total_books||0}</span><span class="mind-stat-label">Libros</span></div>
        <div class="mind-stat"><span class="mind-stat-num">${mind.stats?.reflected_books||0}</span><span class="mind-stat-label">Reflexionados</span></div>
        <div class="mind-stat"><span class="mind-stat-num">${mind.stats?.evolution_entries||0}</span><span class="mind-stat-label">Entradas de evolución</span></div>
      </div>
    </div>

    ${mind.main_bias ? `
      <div class="section-title">Sesgo principal detectado</div>
      <div class="mind-bias-card">${esc(mind.main_bias)}</div>` : ''}

    <div class="mind-two-col">
      ${mind.thinker_affinities?.length ? `
        <div>
          <div class="section-title">Autores afines</div>
          <div class="thinker-list">
            ${mind.thinker_affinities.map(t=>`<div class="thinker-item affinity">✦ ${esc(t)}</div>`).join('')}
          </div>
        </div>` : ''}
      ${mind.thinker_conflicts?.length ? `
        <div>
          <div class="section-title">Autores que te desafían</div>
          <div class="thinker-list">
            ${mind.thinker_conflicts.map(t=>`<div class="thinker-item conflict">⚡ ${esc(t)}</div>`).join('')}
          </div>
        </div>` : ''}
    </div>

    ${mind.detected_values?.length ? `
      <div class="section-title">Valores detectados</div>
      <div class="values-chips">
        ${mind.detected_values.map(v=>`<span class="value-chip">${esc(v)}</span>`).join('')}
      </div>` : ''}

    ${mind.recurring_tensions?.length ? `
      <div class="section-title">Tensiones intelectuales recurrentes</div>
      <div class="tensions-list">
        ${mind.recurring_tensions.map(t=>`<div class="tension-item">⟳ ${esc(t)}</div>`).join('')}
      </div>` : ''}

    ${evolution.evolution_entries?.length ? `
      <div class="section-title">Evolución de tu pensamiento</div>
      <div class="evolution-timeline">
        ${evolution.evolution_entries.map((e,i)=>`
          <div class="evolution-entry">
            <div class="evolution-dot"></div>
            <div class="evolution-text">${esc(e)}</div>
          </div>`).join('')}
      </div>` : ''}

    <div style="margin-top:2rem;padding-top:1.5rem;border-top:1px solid var(--border)">
      <button class="btn-ghost-sm" onclick="restartOnboarding()">Actualizar perfil →</button>
    </div>`;
}

/* ── HELPERS DE LIBRO ─────────────── */
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
  const msgs = await api(`/api/books/${bookId}/chat`);
  const container = document.getElementById('chat-messages');
  const book = STATE.books.find(b=>b.id===bookId)||{};

  if (!msgs.length) {
    const suggestions = {
      legal: ['¿Cuál es el concepto más importante?','Explícame las normas citadas','Hazme una pregunta de examen','Repaso rápido para parcial'],
      tech: ['¿Qué tecnologías cubre este libro?','Dame un ejemplo práctico','¿Cuáles son los conceptos más difíciles?','Resúmeme los puntos clave'],
      data_science: ['¿Qué algoritmos se cubren?','Explícame el concepto más importante','Dame un ejercicio práctico','¿Cuáles herramientas se usan?'],
      personal: ['¿Cuál es la idea principal?','Dame las 3 acciones más importantes','¿Cómo aplico esto en mi vida?','Resúmeme por capítulos'],
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

/* ── GAMES ────────────────────────── */
let GAME_STATE = { sessionId:null, questions:[], current:0, score:0, maxScore:0, bookId:null, answered:false };

async function openGame(bookId) {
  GAME_STATE = { sessionId:null, questions:[], current:0, score:0, maxScore:0, bookId, answered:false };
  switchView('game');
  document.getElementById('topbar-title').textContent = 'Juego de comprensión';
  document.getElementById('topbar-actions').innerHTML = `<button onclick="openBook(${bookId})">← Volver</button>`;

  const content = document.getElementById('game-content');
  content.innerHTML = `<div class="game-intro">
    <div class="game-intro-icon">🎮</div>
    <h2>Juego de comprensión</h2>
    <p class="muted-text">Voy a generar un mini-juego basado en este libro.</p>
    <div id="game-loading" class="hidden"><span class="loading-spinner"></span>Generando juego…</div>
    <button id="btn-start-game" class="btn-primary" onclick="startGame(${bookId})">Generar juego →</button>
  </div>`;
}

async function startGame(bookId) {
  document.getElementById('btn-start-game').classList.add('hidden');
  document.getElementById('game-loading').classList.remove('hidden');

  const res = await api(`/api/books/${bookId}/game`, 'POST');
  if (res.error) {
    toast(res.error, 'error');
    document.getElementById('game-loading').classList.add('hidden');
    document.getElementById('btn-start-game').classList.remove('hidden');
    return;
  }

  GAME_STATE.sessionId = res.session_id;
  GAME_STATE.questions = res.questions;
  GAME_STATE.maxScore = res.questions.filter(q=>q.type==='comprehension').length;
  GAME_STATE.current = 0;
  GAME_STATE.score = 0;
  renderGameIntroFragment(res.category, res.fragment_text);
}

function renderGameIntroFragment(category, fragment) {
  const content = document.getElementById('game-content');
  content.innerHTML = `
    <div class="game-fragment-card">
      <div class="game-category">${esc(category)}</div>
      <div class="game-fragment-text">${esc(fragment)}</div>
    </div>
    <button class="btn-primary" onclick="renderGameQuestion()">Empezar preguntas →</button>`;
}

function renderGameQuestion() {
  const q = GAME_STATE.questions[GAME_STATE.current];
  const total = GAME_STATE.questions.length;
  const isInterp = q.type === 'interpretation';
  GAME_STATE.answered = false;

  document.getElementById('game-content').innerHTML = `
    <div class="game-progress">
      <span>Pregunta ${GAME_STATE.current+1} de ${total}</span>
      <span class="game-score">⭐ ${GAME_STATE.score}/${GAME_STATE.maxScore}</span>
    </div>
    ${isInterp ? '<div class="game-type-badge interp">🧠 Interpretación personal</div>' : '<div class="game-type-badge comp">✅ Comprensión</div>'}
    <div class="game-question">${esc(q.question)}</div>
    <div class="game-options">
      ${q.options.map((opt,i)=>`<button class="game-option" data-idx="${i}" onclick="answerGame(${i})">${esc(opt)}</button>`).join('')}
    </div>
    <div id="game-feedback" class="game-feedback hidden"></div>
    <button id="btn-next-game" class="btn-primary hidden" onclick="nextGameQuestion()">
      ${GAME_STATE.current < total-1 ? 'Siguiente →' : 'Finalizar juego →'}
    </button>`;
}

async function answerGame(idx) {
  if (GAME_STATE.answered) return;
  GAME_STATE.answered = true;
  const q = GAME_STATE.questions[GAME_STATE.current];
  document.querySelectorAll('.game-option').forEach(b=>b.style.pointerEvents='none');

  const res = await api(`/api/games/${GAME_STATE.sessionId}/answer`, 'POST', {
    question_index: GAME_STATE.current, answer_index: idx
  });

  const options = document.querySelectorAll('.game-option');
  const feedback = document.getElementById('game-feedback');

  if (q.type === 'comprehension') {
    options[idx].classList.add(res.correct ? 'correct' : 'incorrect');
    if (!res.correct && res.correct_index !== undefined) options[res.correct_index].classList.add('correct');
    if (res.correct) GAME_STATE.score++;
    feedback.innerHTML = `<strong>${res.correct?'¡Correcto! ✅':'No exactamente ❌'}</strong> ${esc(res.explanation||'')}`;
  } else {
    options[idx].classList.add('selected');
    feedback.innerHTML = `<strong>Gracias por compartir tu perspectiva 🧠</strong>`;
  }
  feedback.classList.remove('hidden');
  document.getElementById('btn-next-game').classList.remove('hidden');
  document.querySelector('.game-progress .game-score').textContent = `⭐ ${GAME_STATE.score}/${GAME_STATE.maxScore}`;
}

function nextGameQuestion() {
  GAME_STATE.current++;
  if (GAME_STATE.current < GAME_STATE.questions.length) {
    renderGameQuestion();
  } else {
    finishGame();
  }
}

async function finishGame() {
  const content = document.getElementById('game-content');
  content.innerHTML = `<div class="game-intro"><span class="loading-spinner"></span>Calculando resultados…</div>`;
  const res = await api(`/api/games/${GAME_STATE.sessionId}/finish`, 'POST');
  content.innerHTML = `
    <div class="game-result">
      <div class="game-result-icon">🏆</div>
      <h2>¡Juego completado!</h2>
      <div class="game-result-score">${res.score} / ${res.max_score}</div>
      <p class="muted-text">preguntas de comprensión correctas</p>
      ${res.insights ? `<div class="game-insights">
        <div class="section-title">Lo que aprendí de ti</div>
        <div class="game-insights-text">${esc(res.insights)}</div>
      </div>` : ''}
      <div class="game-result-actions">
        <button class="btn-primary" onclick="openGame(${GAME_STATE.bookId})">Jugar otra vez</button>
        <button class="btn-ghost" onclick="openBook(${GAME_STATE.bookId})">Volver al libro</button>
      </div>
    </div>`;
}

/* ── PWA ──────────────────────────── */
if('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js').catch(()=>{});