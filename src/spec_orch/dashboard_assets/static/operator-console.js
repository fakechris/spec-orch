/*
 * Operator console helper library.
 *
 * This keeps the heaviest evidence-reading helpers out of the transitional
 * inline dashboard script while the workbench refactor is still in progress.
 */

(function initOperatorConsoleHelpers(globalThis) {
  function safeEsc(escHtml, value) {
    return typeof escHtml === 'function' ? escHtml(String(value ?? '')) : String(value ?? '');
  }

  function renderDetailValue(value, escHtml) {
    if (Array.isArray(value)) {
      if (!value.length) return '<span class="detail-empty">—</span>';
      return value
        .map(item => `<span class="detail-chip">${safeEsc(escHtml, item)}</span>`)
        .join('');
    }
    if (value && typeof value === 'object') {
      return `<span class="detail-json">${safeEsc(escHtml, JSON.stringify(value))}</span>`;
    }
    if (value === null || value === undefined || value === '') {
      return '<span class="detail-empty">—</span>';
    }
    return safeEsc(escHtml, value);
  }

  function renderTranscriptDetails(details, escHtml) {
    if (!details || typeof details !== 'object') {
      return '';
    }

    const entries = Object.entries(details);
    const artifactRows = [];
    const findingRows = [];
    const genericRows = [];

    for (const [key, value] of entries) {
      if (key === 'artifacts' && value && typeof value === 'object' && !Array.isArray(value)) {
        for (const [artifactKey, artifactValue] of Object.entries(value)) {
          artifactRows.push(`
            <div class="detail-row">
              <div class="detail-key">${safeEsc(escHtml, artifactKey)}</div>
              <div class="detail-value artifact-link">${safeEsc(escHtml, artifactValue)}</div>
            </div>
          `);
        }
        continue;
      }

      if (key === 'findings' && Array.isArray(value)) {
        for (const finding of value) {
          findingRows.push(`
            <div class="context-card detail-finding">
              <div class="context-title">${safeEsc(escHtml, finding?.severity || 'finding')}</div>
              <div class="transcript-entry-body">${safeEsc(escHtml, finding?.message || '')}</div>
            </div>
          `);
        }
        continue;
      }

      genericRows.push(`
        <div class="detail-row">
          <div class="detail-key">${safeEsc(escHtml, key)}</div>
          <div class="detail-value">${renderDetailValue(value, escHtml)}</div>
        </div>
      `);
    }

    return `
      <div class="context-card">
        <div class="context-title">Structured details</div>
        ${genericRows.length ? `<div class="detail-grid">${genericRows.join('')}</div>` : '<div class="empty-panel">No structured fields.</div>'}
        ${findingRows.length ? `<div class="context-list detail-section"><div class="context-title">Findings</div>${findingRows.join('')}</div>` : ''}
        ${artifactRows.length ? `<div class="detail-grid detail-section">${artifactRows.join('')}</div>` : ''}
      </div>
    `;
  }

  function formatApprovalActionState(action) {
    if (!action || typeof action !== 'object') {
      return '';
    }
    const status = String(action.status || '');
    const effect = String(action.effect || '');
    if (status === 'applied') {
      return effect ? `Applied • ${effect}` : 'Applied';
    }
    if (status === 'not_applied') {
      return effect ? `Recorded only • ${effect}` : 'Recorded only';
    }
    if (status) {
      return effect ? `${status} • ${effect}` : status;
    }
    return effect;
  }

  window.SpecOrchOperatorConsole = {
    renderDetailValue,
    renderTranscriptDetails,
    formatApprovalActionState,
  }
  globalThis.__SPEC_ORCH_OPERATOR_CONSOLE__ = true;
})(window)
