/* RigMind — asistente personal de reportes de pozo.
   Etapa 1: auditar el lapso y completar. Etapa 2: traducir a inglés. */

window.latestAuditData = null;
let isDiffMode = false;
let isAlignedMode = false;
let inMemoryApiKey = '';
let inMemoryProvider = 'auto';

const $ = (id) => document.getElementById(id);

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined && text !== null) n.textContent = String(text);
  return n;
}

/* ------------------------------------------------------------------ */
/* Clave de IA                                                         */
/* ------------------------------------------------------------------ */
function setClientApiKey(key, provider) {
  inMemoryApiKey = key;
  inMemoryProvider = provider;
  try {
    localStorage.setItem('rigmind_api_key', key);
    localStorage.setItem('rigmind_provider', provider);
  } catch (e) {}
}

function getClientApiKey() {
  try {
    const k = localStorage.getItem('rigmind_api_key');
    if (k) return k;
  } catch (e) {}
  return inMemoryApiKey || '';
}

function getClientProvider() {
  try {
    const p = localStorage.getItem('rigmind_provider');
    if (p) return p;
  } catch (e) {}
  return inMemoryProvider || 'auto';
}

function clearClientApiKey() {
  inMemoryApiKey = '';
  inMemoryProvider = 'auto';
  try {
    localStorage.removeItem('rigmind_api_key');
    localStorage.removeItem('rigmind_provider');
  } catch (e) {}
}

function detectProviderFromKey(key) {
  if (!key) return 'auto';
  const k = key.trim();
  if (k.startsWith('sk-ant-')) return 'anthropic';
  if (k.startsWith('gsk_')) return 'groq';
  if (k.startsWith('sk-') && k.length <= 36) return 'deepseek';
  if (k.startsWith('sk-')) return 'openai';
  if (k.startsWith('AIza')) return 'gemini';
  return 'deepseek';
}

const PROVIDER_LABEL = {
  deepseek: '🐳 DeepSeek',
  openai: '🟢 OpenAI',
  anthropic: '🟣 Claude',
  groq: '⚡ Groq',
  gemini: '🔵 Gemini',
  auto: '🤖 Auto',
};

function renderApiVault() {
  const container = $('apiVaultContainer');
  const rigBadge = $('rigStatusBadge');
  const key = getClientApiKey();
  if (!container) return;

  if (key) {
    const detected = getClientProvider() === 'auto' ? detectProviderFromKey(key) : getClientProvider();
    const label = PROVIDER_LABEL[detected] || 'IA';
    if (rigBadge) {
      rigBadge.className = 'badge badge-emerald';
      rigBadge.innerText = label + ' conectado';
    }
    container.innerHTML =
      '<div style="display:inline-flex; align-items:center; gap:8px; background:rgba(16,185,129,.12); border:1px solid rgba(16,185,129,.5); padding:4px 10px; border-radius:4px;" title="Clave guardada en este equipo y en el servidor local.">' +
      '<span style="font-size:.75rem;color:#34D399;font-weight:600;">🔒 ' + label + ' (******)</span>' +
      '<button type="button" class="btn-vault-action" onclick="testApiKeyClient()" title="Probar conexión">🧪 Probar</button>' +
      '<button type="button" class="btn-vault-action" onclick="changeApiKey()" title="Cambiar clave">⚙️ Cambiar</button>' +
      '</div>';
  } else {
    if (rigBadge) {
      rigBadge.className = 'badge badge-amber';
      rigBadge.innerText = 'Reglas locales (sin IA)';
    }
    container.innerHTML =
      '<div style="display:inline-flex;align-items:center;gap:6px;background:#0E131A;border:1px solid var(--border);padding:3px 8px;border-radius:4px;">' +
      '<select id="providerSelect" class="meta-input" style="padding:2px 4px;font-size:.75rem;background:#080B0F;border:1px solid #232E3E;color:var(--text-main);border-radius:3px;">' +
      '<option value="auto">🤖 Auto-Detectar</option>' +
      '<option value="deepseek">🐳 DeepSeek (V3 / R1)</option>' +
      '<option value="openai">🟢 OpenAI (GPT-4o)</option>' +
      '<option value="anthropic">🟣 Claude 3.5</option>' +
      '<option value="groq">⚡ Groq (Llama 3.3)</option>' +
      '<option value="gemini">🔵 Google Gemini</option>' +
      '</select>' +
      '<input type="password" id="secureApiKeyInput" class="api-input" placeholder="Pegar API Key..." autocomplete="off" spellcheck="false" style="width:140px;letter-spacing:1px;">' +
      '<button type="button" class="btn-vault-save" onclick="saveApiKeyClient()" title="Probar y guardar">💾</button>' +
      '</div>';
  }
}

async function saveApiKeyClient() {
  const input = $('secureApiKeyInput');
  const provSelect = $('providerSelect');
  if (!input) return;
  const key = input.value.trim();
  if (!key) {
    alert('Pegue la clave de API antes de guardar.');
    return;
  }
  let provider = provSelect ? provSelect.value : 'auto';
  if (provider === 'auto') provider = detectProviderFromKey(key);

  try {
    const res = await fetch('/api/config/test-api-key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: key, provider: provider }),
    });
    const data = await res.json();
    if (!data.success) {
      alert('❌ No se pudo conectar con ' + provider.toUpperCase() + ':\n\n' + (data.error || 'Error desconocido'));
      return;
    }
  } catch (err) {
    alert('No se pudo probar la clave: ' + err.message);
    return;
  }

  setClientApiKey(key, provider);
  renderApiVault();
  try {
    await fetch('/api/config/api-key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: key, provider: provider }),
    });
  } catch (e) {}
  alert('✅ Clave verificada y guardada. Ya puede auditar y traducir con IA.');
}

async function testApiKeyClient() {
  const key = getClientApiKey();
  if (!key) {
    alert('No hay clave configurada.');
    return;
  }
  const badge = $('rigStatusBadge');
  if (badge) badge.innerText = '⏳ Probando...';
  try {
    const t0 = performance.now();
    const res = await fetch('/api/config/test-api-key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: key, provider: getClientProvider() }),
    });
    const data = await res.json();
    const ms = Math.round(performance.now() - t0);
    if (data.success) {
      if (badge) {
        badge.className = 'badge badge-emerald';
        badge.innerText = '🟢 ' + data.provider.toUpperCase() + ' (' + ms + ' ms)';
      }
      alert('✅ Conexión activa con ' + data.provider.toUpperCase() + '\nModelo: ' + data.model + '\nLatencia: ' + ms + ' ms');
    } else {
      if (badge) {
        badge.className = 'badge badge-crimson';
        badge.innerText = '🔴 Error de conexión';
      }
      alert('❌ ' + (data.error || 'No se pudo conectar.'));
    }
  } catch (err) {
    alert('Error de red: ' + err.message);
  }
}

function changeApiKey() {
  if (!confirm('¿Cambiar o borrar la clave de IA de este equipo?')) return;
  clearClientApiKey();
  fetch('/api/config/api-key', { method: 'DELETE' }).catch(() => {});
  renderApiVault();
}

async function syncApiStatusFromServer() {
  if (getClientApiKey()) return;
  try {
    const res = await fetch('/api/config/api-key-status');
    const d = await res.json();
    if (d.has_key) {
      const badge = $('rigStatusBadge');
      if (badge) {
        badge.className = 'badge badge-emerald';
        badge.innerText = 'IA configurada en el servidor';
      }
    }
  } catch (e) {}
}

/* ------------------------------------------------------------------ */
/* Carga del ejemplo                                                   */
/* ------------------------------------------------------------------ */
async function loadSampleData() {
  try {
    const res = await fetch('/api/sample');
    const data = await res.json();
    $('rawTextInput').value = data.sample_text;
    const start = $('periodStartInput');
    const end = $('periodEndInput');
    if (start) start.value = '07:00';
    if (end) end.value = '24:00';
    runStage1Audit();
  } catch (err) {
    alert('No se pudo cargar el ejemplo: ' + err.message);
  }
}

/* ------------------------------------------------------------------ */
/* Render de hallazgos y completitud                                   */
/* ------------------------------------------------------------------ */
function findingCard(f) {
  const sev = (f.severity || 'info').toLowerCase();
  const card = el('div', 'finding-card sev-' + sev);
  const head = el('div', 'finding-head', f.badge || 'Hallazgo');
  const agent = el('span', 'finding-agent', ' · ' + (f.agent || ''));
  head.appendChild(agent);
  card.appendChild(head);
  if (f.message) card.appendChild(el('div', '', f.message));

  if (f.evidence && (f.evidence.quote || f.evidence.line)) {
    const evi = el('div', 'finding-evi');
    evi.textContent = (f.evidence.line ? 'L' + f.evidence.line + ' · ' : '') + (f.evidence.quote ? '«' + f.evidence.quote + '»' : '');
    card.appendChild(evi);
  }
  const meta = el('div', 'finding-meta');
  if (f.standard) {
    const std = el('span', 'finding-std', '📏 ' + f.standard);
    meta.appendChild(std);
  }
  if (f.suggestion) {
    const fix = el('div', 'finding-fix', '✏️ ' + f.suggestion);
    meta.appendChild(fix);
  }
  if (meta.childNodes.length) card.appendChild(meta);
  return card;
}

function renderFindings(list, prepend, clearFirst) {
  const container = $('findingsListContainer');
  if (!container) return;
  if (clearFirst) container.innerHTML = '';
  (list || []).forEach((f) => {
    const card = findingCard(f);
    if (prepend) container.prepend(card);
    else container.appendChild(card);
  });
}

function renderCompleteness(comp) {
  const container = $('findingsListContainer');
  if (!container || !comp) return;

  const block = el('div', 'chk-block');
  const title = el('div', 'chk-title',
    'Checklist por operación · ' + comp.score + '% (' + comp.level + ')');
  block.appendChild(title);

  (comp.by_operation || []).forEach((op) => {
    const head = el('div', 'chk-row');
    head.appendChild(el('span', 'chk-ok', '▸'));
    head.appendChild(el('span', '', op.label + '  [' + op.from + '–' + op.to + '] · ' + op.score + '%'));
    block.appendChild(head);
    (op.missing || []).forEach((m) => {
      const row = el('div', 'chk-row');
      row.appendChild(el('span', 'chk-miss', m.priority === 'requerido' ? '✗' : '·'));
      row.appendChild(el('span', 'chk-miss', m.label));
      row.appendChild(el('span', 'chk-hint', '— ' + m.hint));
      block.appendChild(row);
    });
  });

  const header = comp.header || {};
  if ((header.missing || []).length) {
    block.appendChild(el('div', 'chk-title', 'Encabezado del reporte'));
    header.missing.forEach((m) => {
      const row = el('div', 'chk-row');
      row.appendChild(el('span', 'chk-miss', m.priority === 'requerido' ? '✗' : '·'));
      row.appendChild(el('span', 'chk-miss', m.label));
      row.appendChild(el('span', 'chk-hint', '— ' + m.hint));
      block.appendChild(row);
    });
  }
  container.appendChild(block);
}

function setChip(id, cls, text) {
  const chip = $(id);
  if (!chip) return;
  chip.className = 'pf-chip ' + cls;
  chip.innerText = text;
}

/* ------------------------------------------------------------------ */
/* Etapa 1: auditar y re-auditar                                       */
/* ------------------------------------------------------------------ */
function applyAuditResponse(data, start, end) {
  window.latestAuditData = data;
  const notice = $('gapNoticeText');
  const btnT = $('btnTranslateStage2');
  const period = data.period || {};
  const pf = data.preflight || {};
  const win = period.window || { from: start, to: end };

  $('calcDurText').innerText = (period.total_duration || 0) + ' h';
  const bal = $('timeBalanceBadge');
  if (bal) {
    bal.innerText = 'Lapso ' + win.from + '–' + win.to + ' · ' + (period.coverage_pct || 0) + '%';
    bal.className = 'badge ' + ((period.coverage_pct || 0) >= 99.5 ? 'badge-emerald' : 'badge-amber');
  }
  if (notice) {
    const bits = [];
    if ((pf.gaps_hours || 0) > 0) bits.push('⚠️ ' + pf.gaps_hours + ' h sin registro');
    if ((pf.overlaps_hours || 0) > 0) bits.push('⚠️ ' + pf.overlaps_hours + ' h solapadas');
    if (!bits.length) bits.push('✅ lapso cubierto sin huecos');
    bits.push('⏱️ ' + (period.events || []).length + ' eventos');
    if (data.ai_status && data.ai_status.connected) {
      bits.push('⚡ IA: ' + (data.ai_status.engine || ''));
    } else if (data.ai_status && data.ai_status.error) {
      bits.push('⚠️ IA no disponible: reglas locales');
    }
    notice.innerHTML = '<span style="color:var(--text-muted);font-weight:600;">' + bits.join(' · ') + '</span>';
  }

  $('polishedTextInput').value = data.corrected_spanish || '';
  $('diffViewBox').innerHTML = data.visual_diff_html || '';
  if (isDiffMode) toggleDiffMode();

  const tips = $('tipsListContainer');
  tips.innerHTML = '';
  (data.learning_tips || []).forEach((t) => tips.appendChild(el('li', 'tip-item', t)));

  const comp = data.completeness || { score: 0, level: 'Sin datos', missing_required: [] };
  $('tierLabel').innerText = comp.level + ' · ' + comp.score + '%';
  $('tierLabel').style.color = comp.score >= 85 ? 'var(--emerald)' : comp.score >= 65 ? '#38BDF8' : 'var(--amber)';
  const bar = $('maturityProgressBar');
  bar.style.width = comp.score + '%';
  bar.style.background = comp.score >= 85 ? 'var(--emerald)' : comp.score >= 65 ? '#38BDF8' : 'var(--amber)';

  const missing = comp.missing_required || [];
  $('missingTipsText').innerText = missing.length
    ? 'Falta: ' + missing.slice(0, 3).map((m) => m.label + ' (' + m.from + '–' + m.to + ')').join(' · ')
    : 'No falta ningún campo obligatorio en las operaciones detectadas.';

  setChip('pfHoursChip', (period.coverage_pct || 0) >= 99.5 ? 'pf-ok' : 'pf-warn',
    '⏱️ Lapso: ' + win.from + '–' + win.to + ' · ' + (period.coverage_pct || 0) + '%');
  setChip('pfMathChip', (pf.critical || 0) > 0 ? 'pf-err' : 'pf-ok',
    (pf.critical || 0) > 0 ? '📐 Aritmética: ' + pf.critical + ' error(es)' : '📐 Aritmética: sin errores');
  setChip('pfNormsChip', comp.score >= 85 ? 'pf-ok' : 'pf-warn',
    '📏 Completitud: ' + comp.score + '%');
  setChip('pfBlanksChip', missing.length ? 'pf-warn' : 'pf-ok',
    missing.length ? '✍️ Faltan: ' + missing.length + ' campos' : '✍️ Campos obligatorios completos');

  const findings = data.agent_findings || [];
  const badge = $('findingsCountBadge');
  if (badge) {
    badge.innerText = findings.length + ' hallazgos';
    badge.className = 'badge ' + ((pf.critical || 0) > 0 ? 'badge-crimson' : 'badge-cyan');
  }
  renderFindings(findings, false, true);
  renderCompleteness(comp);

  if (btnT) btnT.classList.add('btn-pulse');
}

async function _executeAudit(text, useAi, triggerBtn, busyLabel, idleLabel) {
  const well = $('wellNameInput').value.trim();
  const start = ($('periodStartInput') || {}).value || '00:00';
  const end = ($('periodEndInput') || {}).value || '24:00';
  const notice = $('gapNoticeText');

  if (triggerBtn) { triggerBtn.disabled = true; triggerBtn.innerText = busyLabel; }
  if (notice) notice.innerHTML = '<span style="color:var(--cyan);font-weight:600;">⏳ Auditando el lapso...</span>';

  try {
    const res = await fetch('/api/audit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_text: text,
        well_name: well,
        period_start: start,
        period_end: end,
        api_key: getClientApiKey(),
        provider: getClientProvider(),
        use_ai: useAi,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Error del servidor');
    applyAuditResponse(data, start, end);
  } catch (err) {
    if (notice) notice.innerHTML = '<span style="color:var(--crimson);font-weight:700;">❌ ' + err.message + '</span>';
    alert('Error al auditar: ' + err.message);
  } finally {
    if (triggerBtn) { triggerBtn.disabled = false; triggerBtn.innerText = idleLabel; }
  }
}

async function runStage1Audit() {
  const raw = $('rawTextInput').value.trim();
  const notice = $('gapNoticeText');
  if (!raw) {
    $('rawTextInput').focus();
    if (notice) notice.innerHTML = '<span style="color:var(--crimson);font-weight:700;">⚠️ Pegue el reporte en la Caja 1.</span>';
    return;
  }
  await _executeAudit(raw, true, $('btnAuditStage1'), '⏳ Auditando...', '⚡ 1. Auditar Reporte');
}

async function reauditBox2() {
  const polished = $('polishedTextInput').value.trim();
  if (!polished) {
    alert('No hay texto en la Caja 2 para re-auditar.');
    return;
  }
  await _executeAudit(polished, false, $('btnReauditBox2'), '⏳ Validando...', '🔄 Re-auditar');
}

/* ------------------------------------------------------------------ */
/* Editor: diff y navegación de campos                                 */
/* ------------------------------------------------------------------ */
function toggleDiffMode() {
  const editor = $('polishedTextInput');
  const diffBox = $('diffViewBox');
  const btn = $('btnToggleDiff');
  if (!isDiffMode) {
    editor.style.display = 'none';
    diffBox.style.display = 'block';
    if (btn) btn.innerText = '✏️ Modo Editor';
    isDiffMode = true;
  } else {
    editor.style.display = 'block';
    diffBox.style.display = 'none';
    if (btn) btn.innerText = '🔍 Ver Diff';
    isDiffMode = false;
  }
}

function focusNextPlaceholder() {
  const editor = $('polishedTextInput');
  if (isDiffMode) toggleDiffMode();
  editor.focus();
  const text = editor.value;
  const regex = /\[[^\]\r\n]+\]/g;
  const pos = editor.selectionEnd || 0;
  regex.lastIndex = pos;
  let match = regex.exec(text);
  if (!match) {
    regex.lastIndex = 0;
    match = regex.exec(text);
  }
  if (match) {
    editor.setSelectionRange(match.index, match.index + match[0].length);
    const line = text.substring(0, match.index).split('\n').length;
    editor.scrollTop = Math.max(0, (line - 3) * 20);
  } else {
    alert('✅ No quedan campos pendientes.');
  }
}

/* ------------------------------------------------------------------ */
/* Etapa 2: traducir                                                   */
/* ------------------------------------------------------------------ */
async function runStage2Translate() {
  const text = $('polishedTextInput').value.trim();
  const well = $('wellNameInput').value.trim();
  const btn = $('btnTranslateStage2');
  const out = $('englishOutputBox');

  if (!text) {
    alert('Primero audite y complete el reporte en la Caja 2.');
    return;
  }
  const pendingMatches = text.match(/\[completar:[^\]]+\]/gi) || [];
  if (pendingMatches.length) {
    const proceed = confirm(
      'Todavía quedan ' + pendingMatches.length + ' campo(s) [completar: ...] sin llenar en la Caja 2.\n\n' +
      '• Aceptar: Traducir de todas formas.\n' +
      '• Cancelar: Volver para completarlos ahora.'
    );
    if (!proceed) {
      focusNextPlaceholder();
      return;
    }
  }
  if (btn) { btn.disabled = true; btn.classList.remove('btn-pulse'); btn.innerText = '⏳ Traduciendo...'; }
  out.innerText = '⏳ Traduciendo con el proveedor seleccionado...';

  try {
    const res = await fetch('/api/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        polished_spanish: text,
        well_name: well,
        api_key: getClientApiKey(),
        provider: getClientProvider(),
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Error del servidor');
    out.innerText = data.english_iadc || '';
    if (isAlignedMode) renderAlignedTable();

    const engine = $('translationEngineBadge');
    if (engine) {
      engine.innerText = data.engine_source || '';
      engine.style.color = (data.engine_source || '').toLowerCase().includes('offline') ? 'var(--amber)' : 'var(--emerald)';
    }

    const q = data.translation_qaqc || {};
    const statusBadge = $('translationAuditBadge');
    const parityBadge = $('dataParityBadge');
    if (statusBadge) {
      const map = {
        VERIFICADO: ['badge-emerald', '✓ Verificado'],
        REVISAR_ESPANOL: ['badge-crimson', '✗ Español residual'],
        REVISAR_DATOS: ['badge-amber', '⚠ Faltan datos'],
        REVISAR_SIGLAS: ['badge-amber', '⚠ Faltan siglas'],
        BORRADOR_OFFLINE: ['badge-crimson', 'Borrador offline'],
      };
      const cfg = map[q.status] || ['badge-cyan', q.status || 'Sin verificar'];
      statusBadge.style.display = 'inline-block';
      statusBadge.className = 'badge ' + cfg[0];
      statusBadge.innerText = cfg[1];
    }
    if (parityBadge) {
      parityBadge.style.display = 'inline-block';
      parityBadge.className = 'badge ' + ((q.data_parity_pct || 0) >= 95 ? 'badge-cyan' : 'badge-amber');
      parityBadge.innerText = 'Números ' + (q.data_parity_pct || 0) + '% · Siglas ' + (q.acronym_pct || 0) + '%';
    }

    if (q.findings && q.findings.length) {
      renderFindings(q.findings, true, false);
      const badge = $('findingsCountBadge');
      if (badge) badge.innerText = 'Traducción: ' + q.findings.length + ' avisos';
    }
  } catch (err) {
    out.innerText = '❌ ' + err.message;
    alert('Error al traducir: ' + err.message);
  } finally {
    if (btn) { btn.disabled = false; btn.innerText = '🚀 2. Traducir a Inglés IADC'; }
  }
}

function _parseTimedLines(txt) {
  const rx = /^\s*(\d{1,2}:\d{2}(?:\s*-\s*\d{1,2}:\d{2})?)\s*[:;\-]?\s*(.+)$/;
  const rows = [];
  (txt || '').split('\n').forEach((line) => {
    const m = line.match(rx);
    if (m) rows.push({ time: m[1].replace(/\s+/g, ' '), body: m[2].trim() });
    else if (line.trim() && rows.length) rows[rows.length - 1].body += ' ' + line.trim();
  });
  return rows;
}

function renderAlignedTable() {
  const box = $('alignedViewBox');
  if (!box) return;
  const esRows = _parseTimedLines(($('polishedTextInput') || {}).value || '');
  const enRows = _parseTimedLines(($('englishOutputBox') || {}).innerText || '');
  box.innerHTML = '';

  if (!enRows.length) {
    box.appendChild(el('div', '', 'Ejecute primero el Paso 2 para comparar línea por línea.'));
    return;
  }
  const enByTime = {};
  enRows.forEach((r) => { enByTime[r.time] = r.body; });

  const table = el('table', 'aligned-table');
  const thead = document.createElement('thead');
  const hr = document.createElement('tr');
  ['Hora', 'Español (Caja 2)', 'Inglés IADC (Caja 4)'].forEach((h) => hr.appendChild(el('th', '', h)));
  thead.appendChild(hr);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  const count = Math.max(esRows.length, enRows.length);
  for (let i = 0; i < count; i++) {
    const es = esRows[i];
    const en = (es && enByTime[es.time]) ? { time: es.time, body: enByTime[es.time] } : enRows[i];
    const tr = document.createElement('tr');
    tr.appendChild(el('td', 'aligned-time', (es && es.time) || (en && en.time) || '—'));
    tr.appendChild(el('td', '', (es && es.body) || '—'));
    tr.appendChild(el('td', '', (en && en.body) || '—'));
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  box.appendChild(table);
}

function toggleAlignedView() {
  const out = $('englishOutputBox');
  const aligned = $('alignedViewBox');
  const btn = $('btnToggleAligned');
  if (!out || !aligned) return;
  if (!isAlignedMode) {
    renderAlignedTable();
    out.style.display = 'none';
    aligned.style.display = 'block';
    if (btn) btn.innerText = '📄 Solo Inglés';
    isAlignedMode = true;
  } else {
    out.style.display = 'block';
    aligned.style.display = 'none';
    if (btn) btn.innerText = '🔀 Vista alineada';
    isAlignedMode = false;
  }
}

/* ------------------------------------------------------------------ */
/* Copiar / guardar                                                    */
/* ------------------------------------------------------------------ */
function copyText(txt) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(txt);
  }
  const ta = document.createElement('textarea');
  ta.value = txt;
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  document.body.removeChild(ta);
  return Promise.resolve();
}

function copyEnglishTranslation() {
  const txt = $('englishOutputBox').innerText.trim();
  if (!txt || txt.startsWith('Aquí aparecerá') || txt.startsWith('⏳')) return;
  copyText(txt).then(() => {
    const notice = $('copyConfirmNotice');
    if (notice) {
      notice.innerText = '✅ Traducción copiada';
      setTimeout(() => { notice.innerText = ''; }, 3000);
    }
  });
}

function copyBilingualDOR() {
  const well = $('wellNameInput').value.trim() || 'Well';
  const spanish = $('polishedTextInput').value.trim();
  const english = $('englishOutputBox').innerText.trim();
  if (!spanish) {
    alert('Debe procesar al menos el reporte en español.');
    return;
  }
  const body =
    '================================================================================\n' +
    'DAILY OPERATIONS REPORT (DOR) / REPORTE DIARIO DE OPERACIONES\n' +
    'POZO / WELL: ' + well + '\n' +
    '================================================================================\n\n' +
    '--- REPORTE EN ESPAÑOL (REVISADO) ---\n' + spanish + '\n\n' +
    '--- ENGLISH OPERATIONS REPORT ---\n' + (english || '[Traducción pendiente]') + '\n\n' +
    '================================================================================\n' +
    'Generado con RigMind — revisión humana requerida antes de entregar al operador.\n';
  copyText(body).then(() => {
    const notice = $('copyConfirmNotice');
    if (notice) {
      notice.innerText = '✅ DOR bilingüe copiado';
      setTimeout(() => { notice.innerText = ''; }, 3500);
    }
  });
}

async function saveToGoldenMemory() {
  const spanish = $('polishedTextInput').value.trim();
  const english = $('englishOutputBox').innerText.trim();
  if (!spanish) {
    alert('Primero procese y audite un reporte.');
    return;
  }
  const name = prompt('Nombre de la operación (ej. Asentamiento HMBP 7"):', 'Operación estándar');
  if (!name) return;
  try {
    const res = await fetch('/api/memory/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        category: 'well_intervention',
        operation: name,
        spanish_exemplar: spanish,
        english_iadc: english,
        learning_tip: (window.latestAuditData && window.latestAuditData.learning_tips || []).join(' | '),
      }),
    });
    const d = await res.json();
    alert(d.success ? '⭐ Ejemplo guardado.' : 'No se pudo guardar el ejemplo.');
  } catch (e) {
    alert('Error al guardar: ' + e.message);
  }
}


/* ------------------------------------------------------------------ */
/* Historial y exportación                                             */
/* ------------------------------------------------------------------ */
function currentPayload() {
  const d = window.latestAuditData || {};
  const comp = d.completeness || {};
  const meta = (d.period && d.period.meta) || {};
  return {
    well: ($('wellNameInput') || {}).value || 'Well',
    report_date: meta.fecha || null,
    period_start: ($('periodStartInput') || {}).value || '00:00',
    period_end: ($('periodEndInput') || {}).value || '24:00',
    spanish: ($('polishedTextInput') || {}).value || '',
    english: ($('englishOutputBox') || {}).innerText.trim(),
    findings: d.agent_findings || [],
    completeness: comp.score || 0,
    operations: comp.by_operation || [],
  };
}

async function saveReport() {
  const payload = currentPayload();
  if (!payload.spanish.trim()) {
    alert('No hay reporte en español para guardar.');
    return;
  }
  try {
    const res = await fetch('/api/report/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || 'No se pudo guardar');
    const notice = $('copyConfirmNotice');
    if (notice) {
      notice.innerText = '💾 Guardado #' + d.id;
      setTimeout(() => { notice.innerText = ''; }, 3000);
    }
    await loadHistory(d.id);
  } catch (e) {
    alert('Error al guardar: ' + e.message);
  }
}

async function loadHistory(selectId) {
  const sel = $('historySelect');
  if (!sel) return;
  try {
    const res = await fetch('/api/reports');
    const d = await res.json();
    const keep = selectId || sel.value;
    sel.innerHTML = '<option value="">— reportes guardados —</option>';
    (d.reports || []).forEach((r) => {
      const o = document.createElement('option');
      o.value = r.id;
      o.textContent = '#' + r.id + ' · ' + r.well + ' · ' + (r.report_date || '') +
        ' · ' + r.period_start + '–' + r.period_end + ' · ' + r.completeness + '%';
      sel.appendChild(o);
    });
    if (keep) sel.value = String(keep);
  } catch (e) {}
}

async function loadSelectedReport() {
  const id = ($('historySelect') || {}).value;
  if (!id) return;
  try {
    const res = await fetch('/api/report/' + id);
    const r = await res.json();
    if (!res.ok) throw new Error(r.error || 'Reporte no encontrado');
    $('wellNameInput').value = r.well || 'Yopo-1';
    $('periodStartInput').value = r.period_start || '00:00';
    $('periodEndInput').value = r.period_end || '24:00';
    $('polishedTextInput').value = r.spanish || '';
    $('englishOutputBox').innerText = r.english || '';
    window.latestAuditData = {
      agent_findings: r.findings || [],
      completeness: { score: r.completeness || 0 },
    };
    renderFindings(r.findings || [], false, true);
    const notice = $('gapNoticeText');
    if (notice) {
      notice.innerHTML = '<span style="color:var(--cyan);font-weight:600;">📂 Reporte #' + r.id +
        ' cargado (' + (r.report_date || '') + ')</span>';
    }
    const badge = $('findingsCountBadge');
    if (badge) badge.innerText = (r.findings || []).length + ' hallazgos';
  } catch (e) {
    alert('Error al abrir el reporte: ' + e.message);
  }
}

async function exportReport(fmt) {
  const payload = currentPayload();
  if (!payload.spanish.trim()) {
    alert('Procese un reporte antes de exportar.');
    return;
  }
  try {
    const res = await fetch('/api/report/export/' + fmt, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'No se pudo generar el archivo');
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'DOR_' + (payload.well || 'Well') + '.' + fmt;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert('Error al exportar: ' + e.message);
  }
}

/* ------------------------------------------------------------------ */
/* Arranque                                                            */
/* ------------------------------------------------------------------ */
renderApiVault();
syncApiStatusFromServer();
loadHistory();

document.addEventListener('DOMContentLoaded', () => {
  renderApiVault();
  syncApiStatusFromServer();
  loadHistory();

  const editor = $('polishedTextInput');
  if (editor) {
    editor.addEventListener('keydown', (e) => {
      if (e.key !== 'Tab') return;
      const regex = /\[[^\]\r\n]+\]/g;
      regex.lastIndex = editor.selectionEnd || 0;
      let m = regex.exec(editor.value);
      if (!m) {
        regex.lastIndex = 0;
        m = regex.exec(editor.value);
      }
      if (m) {
        e.preventDefault();
        editor.setSelectionRange(m.index, m.index + m[0].length);
      }
    });
  }

  const diffBox = $('diffViewBox');
  if (diffBox) {
    diffBox.addEventListener('click', (e) => {
      const blank = e.target.closest('.diff-blank');
      if (!blank) return;
      if (isDiffMode) toggleDiffMode();
      const ed = $('polishedTextInput');
      ed.focus();
      const idx = ed.value.indexOf(blank.innerText.trim());
      if (idx !== -1) ed.setSelectionRange(idx, idx + blank.innerText.trim().length);
    });
  }
});

window.runStage1Audit = runStage1Audit;
window.reauditBox2 = reauditBox2;
window.runStage2Translate = runStage2Translate;
window.toggleDiffMode = toggleDiffMode;
window.toggleAlignedView = toggleAlignedView;
window.focusNextPlaceholder = focusNextPlaceholder;
window.saveApiKeyClient = saveApiKeyClient;
window.testApiKeyClient = testApiKeyClient;
window.changeApiKey = changeApiKey;
window.loadSampleData = loadSampleData;
window.copyEnglishTranslation = copyEnglishTranslation;
window.copyBilingualDOR = copyBilingualDOR;
window.saveToGoldenMemory = saveToGoldenMemory;
window.saveReport = saveReport;
window.exportReport = exportReport;
window.loadHistory = loadHistory;
window.loadSelectedReport = loadSelectedReport;
