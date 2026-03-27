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

  function renderArtifactLinks(artifacts, escHtml) {
    const entries = Object.entries(artifacts || {}).filter(([, value]) => Boolean(value));
    if (!entries.length) {
      return '<div class="empty-panel">No artifact paths available.</div>';
    }
    return entries
      .map(([key, value]) => `
        <div class="context-card">
          <div class="context-title">${safeEsc(escHtml, key)}</div>
          <div class="context-meta"><span class="artifact-link">${safeEsc(escHtml, value)}</span></div>
        </div>
      `)
      .join('');
  }

  function renderRoundContext(round, escHtml) {
    const paths = round?.paths || {};
    const decision = round?.decision || {};
    return `
      <div class="context-card">
        <div class="context-title">${safeEsc(escHtml, decision.reason_code || 'round decision')}</div>
        <div class="context-meta">
          <span>Round ${safeEsc(escHtml, String(round?.round_id || '—'))}</span>
          <span>${safeEsc(escHtml, round?.status || 'unknown')}</span>
        </div>
      </div>
      ${Object.entries(paths)
        .filter(([, value]) => Boolean(value))
        .map(([key, value]) => `
          <div class="context-card">
            <div class="context-title">${safeEsc(escHtml, key)}</div>
            <div class="context-meta">${safeEsc(escHtml, value)}</div>
          </div>
        `)
        .join('')}
    `;
  }

  function buildMissionSubtitle(detail) {
    const mission = detail?.mission || {};
    const rounds = detail?.rounds || [];
    const lifecycle = detail?.lifecycle || {};
    const paused = lifecycle.round_orchestrator_state?.paused;
    const stateText = paused ? 'Paused for human input.' : 'Supervisor loop active.';
    const criterionCount = (mission.acceptance_criteria || []).length;
    return `${stateText} ${criterionCount} acceptance criteria, ${rounds.length} recorded rounds, and ${(detail?.packets || []).length} scoped packets.`;
  }

  window.SpecOrchOperatorConsole = {
    buildMissionSubtitle,
    renderArtifactLinks,
    renderDetailValue,
    renderRoundContext,
    renderTranscriptDetails,
    formatApprovalActionState,
  }
  globalThis.__SPEC_ORCH_OPERATOR_CONSOLE__ = true;
})(window)
