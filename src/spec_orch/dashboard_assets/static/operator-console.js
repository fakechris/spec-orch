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
          <div class="context-meta"><a class="artifact-link" href="/artifacts/${safeEsc(escHtml, value)}" target="_blank" rel="noreferrer">${safeEsc(escHtml, value)}</a></div>
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

  function renderActionButtons(actions, missionId, escHtml) {
    return (actions || []).map(action => {
      if (action === 'approve') {
        return `<button class="btn btn-green btn-sm" onclick="approveGo('${missionId}')">Approve</button>`
      }
      if (action === 'retry' || action === 'rerun') {
        return `<button class="btn btn-red btn-sm" onclick="retryMission('${missionId}')">${action}</button>`
      }
      if (action === 'resume') {
        return `<button class="btn btn-sm" onclick="openDiscuss('${missionId}')">Resume</button>`
      }
      if (action === 'inject_guidance') {
        return `<button class="btn btn-primary btn-sm" onclick="openDiscuss('${missionId}')">Inject guidance</button>`
      }
      return `<button class="btn btn-sm" type="button">${safeEsc(escHtml, action)}</button>`
    }).join('')
  }

  function renderPacketRow(packet, selectedPacketId, escHtml) {
    const inScope = (packet?.files_in_scope || []).slice(0, 2).join(', ')
    const isSelected = packet?.packet_id === selectedPacketId
    return `
      <button class="packet-row ${isSelected ? 'active' : ''}" type="button" onclick="selectPacket('${packet?.packet_id}')">
        <div class="packet-row-header">
          <div class="packet-row-title">${safeEsc(escHtml, packet?.title)}</div>
          <span class="run-class">${safeEsc(escHtml, packet?.run_class || 'packet')}</span>
        </div>
        <div class="packet-row-meta">
          <span>${safeEsc(escHtml, packet?.packet_id)}</span>
          <span>Wave ${safeEsc(escHtml, String(packet?.wave_id ?? '—'))}</span>
          ${packet?.linear_issue_id ? `<span>${safeEsc(escHtml, packet.linear_issue_id)}</span>` : ''}
        </div>
        <div class="packet-row-meta">
          <span>${safeEsc(escHtml, inScope || 'No scoped files')}</span>
        </div>
      </button>
    `
  }

  function renderLatestRound(round, escHtml) {
    const decision = round?.decision || {}
    const succeeded = (round?.worker_results || []).filter(result => result.succeeded).length
    const total = (round?.worker_results || []).length
    return `
      <div class="context-card">
        <div class="context-title">${safeEsc(escHtml, decision.summary || 'No supervisor decision summary')}</div>
        <div class="context-meta">
          <span>Action ${safeEsc(escHtml, decision.action || '—')}</span>
          <span>Confidence ${decision.confidence != null ? safeEsc(escHtml, String(decision.confidence)) : '—'}</span>
          <span>Workers ${succeeded}/${total}</span>
        </div>
      </div>
      <div class="context-list">
        ${(round?.worker_results || []).map(result => `
          <div class="context-card">
            <div class="context-title">${safeEsc(escHtml, result.title || result.packet_id || 'worker')}</div>
            <div class="context-meta">
              <span>${safeEsc(escHtml, result.packet_id || '—')}</span>
              <span>${result.succeeded ? 'succeeded' : 'failed'}</span>
              ${result.report_path ? `<span>${safeEsc(escHtml, result.report_path)}</span>` : ''}
            </div>
          </div>
        `).join('')}
      </div>
    `
  }

  function renderSimpleList(items, emptyText, escHtml) {
    if (!items || !items.length) {
      return `<div class="empty-panel">${safeEsc(escHtml, emptyText)}</div>`
    }
    return `<div class="context-list">${items.map(item => `
      <div class="context-card">
        <div class="context-title">${safeEsc(escHtml, item)}</div>
      </div>
    `).join('')}</div>`
  }

  function renderApprovalWorkspace(
    approvalRequest,
    approvalHistory,
    approvalState,
    missionId,
    escHtml,
  ) {
    const latestAction = approvalHistory && approvalHistory.length ? approvalHistory[0] : null
    const latestActionSummary = formatApprovalActionState(latestAction)
    const stateStatus = approvalState?.status || ''
    const stateSummary = approvalState?.summary || ''
    const pending = stateStatus === 'pending'

    return `
      <div class="context-card">
        <div class="context-title">${safeEsc(escHtml, approvalRequest?.summary || 'Approval required')}</div>
        <div class="context-meta">
          <span>Round ${safeEsc(escHtml, String(approvalRequest?.round_id || '—'))}</span>
          <span>${safeEsc(escHtml, approvalRequest?.decision_action || 'ask_human')}</span>
          <span>${safeEsc(escHtml, approvalRequest?.timestamp || '—')}</span>
        </div>
        ${stateStatus ? `
          <div class="context-meta">
            <span class="detail-chip">${safeEsc(escHtml, stateStatus)}</span>
            ${stateSummary ? `<span>${safeEsc(escHtml, stateSummary)}</span>` : ''}
          </div>
        ` : ''}
      </div>
      ${latestAction ? `
        <div class="context-card">
          <div class="context-title">Latest operator decision</div>
          <div class="context-meta">
            <span class="detail-chip">${safeEsc(escHtml, latestAction?.label || latestAction?.action_key || 'Action')}</span>
            <span class="detail-chip">${safeEsc(escHtml, latestAction?.effect || 'guidance_sent')}</span>
            <span>${safeEsc(escHtml, latestAction?.timestamp || '—')}</span>
          </div>
          ${latestActionSummary ? `<div class="context-meta"><span>${safeEsc(escHtml, latestActionSummary)}</span></div>` : ''}
          <div class="transcript-entry-body">${safeEsc(escHtml, latestAction?.message || '')}</div>
        </div>
      ` : ''}
      <div class="context-card">
        <div class="context-title">Blocking question</div>
        <div class="transcript-entry-body">${safeEsc(escHtml, approvalRequest?.blocking_question || 'No blocking question recorded.')}</div>
      </div>
      <div class="context-card">
        <div class="context-title">Operator actions</div>
        <div class="context-meta">
          ${(approvalRequest?.actions || []).map(action => `
            <button
              class="btn ${action.key === 'approve' ? 'btn-primary' : ''} btn-sm"
              type="button"
              ${pending ? 'disabled' : ''}
              onclick="triggerApprovalAction('${missionId}', '${safeEsc(escHtml, action?.key || '')}')"
            >${safeEsc(escHtml, action?.label || action?.key || 'Action')}</button>
          `).join('')}
          <button
            class="btn btn-sm"
            type="button"
            ${pending ? 'disabled' : ''}
            onclick="openDiscussPreset('${missionId}', '${safeEsc(escHtml, (approvalRequest?.actions || [])[0]?.message || '')}')"
          >Open discuss</button>
          <button class="btn btn-sm" type="button" onclick="load()">Refresh state</button>
        </div>
      </div>
      <div class="context-card">
        <div class="context-title">Recent operator actions</div>
        ${
          approvalHistory && approvalHistory.length
            ? `<div class="context-list">
                ${approvalHistory.slice(0, 3).map(item => `
                  <div class="context-card">
                    <div class="context-title">${safeEsc(escHtml, item?.label || item?.action_key || 'Action')}</div>
                    <div class="context-meta">
                      <span>${safeEsc(escHtml, item?.timestamp || '—')}</span>
                      <span>${safeEsc(escHtml, item?.channel || 'web-dashboard')}</span>
                      <span class="detail-chip">${safeEsc(escHtml, item?.status || 'sent')}</span>
                      <span class="detail-chip">${safeEsc(escHtml, item?.effect || 'guidance_sent')}</span>
                    </div>
                    <div class="transcript-entry-body">${safeEsc(escHtml, item?.message || '')}</div>
                  </div>
                `).join('')}
              </div>`
            : '<div class="empty-panel">No operator actions recorded yet.</div>'
        }
      </div>
    `
  }

  function renderApprovalQueue(items, escHtml) {
    if (!items || !items.length) {
      return '<div class="empty-panel">No approval-required missions right now.</div>'
    }
    return `
      <div class="context-list">
        ${items.map(item => `
          <div class="context-card queue-card">
            <div class="context-title">${safeEsc(escHtml, item?.mission?.title || item?.title || 'Approval')}</div>
            <div class="context-meta">
              <span class="detail-chip">${safeEsc(escHtml, item?.approval_state?.status || 'approval')}</span>
              <span>${safeEsc(escHtml, item?.summary || item?.approval_request?.summary || '')}</span>
            </div>
            <div class="context-meta">
              <span>Round ${safeEsc(escHtml, String(item?.current_round || item?.approval_request?.round_id || '—'))}</span>
              ${item?.latest_operator_action ? `<span>${safeEsc(escHtml, item.latest_operator_action.label || item.latest_operator_action.action_key || 'Action')}</span>` : ''}
              ${item?.recommended_action ? `<span>${safeEsc(escHtml, item.recommended_action)}</span>` : ''}
            </div>
            ${item?.blocking_question ? `<div class="transcript-entry-body">${safeEsc(escHtml, item.blocking_question)}</div>` : ''}
          </div>
        `).join('')}
      </div>
    `
  }

  function renderApprovalQueuePanel(queue, selectedMissionIds, batchState, escHtml) {
    const items = queue?.items || []
    const counts = queue?.counts || {}
    const selected = new Set(selectedMissionIds || [])
    const disabled = !items.length || !selected.size || batchState?.pending
    return `
      <section class="mission-section">
        <div class="section-heading">
          <h3>Approval Queue</h3>
          <div class="context-meta">
            <span>${safeEsc(escHtml, `${counts.pending || 0} pending`)}</span>
            <span>${safeEsc(escHtml, `${counts.missions || 0} missions`)}</span>
            <span>${safeEsc(escHtml, `${counts.requires_followup || 0} follow-up`)}</span>
          </div>
        </div>
        <div class="queue-toolbar">
          <label class="queue-toggle">
            <input type="checkbox" ${items.length && selected.size === items.length ? 'checked' : ''} onchange="toggleAllApprovalSelections(this.checked)"/>
            <span>Select all</span>
          </label>
          <div class="queue-actions">
            <button class="btn btn-primary btn-sm" type="button" ${disabled ? 'disabled' : ''} onclick="triggerApprovalBatchAction('approve')">Approve selected</button>
            <button class="btn btn-sm" type="button" ${disabled ? 'disabled' : ''} onclick="triggerApprovalBatchAction('request_revision')">Request revision</button>
            <button class="btn btn-sm" type="button" ${disabled ? 'disabled' : ''} onclick="triggerApprovalBatchAction('ask_followup')">Ask follow-up</button>
          </div>
        </div>
        ${batchState?.summary ? `
          <div class="context-card queue-summary">
            <div class="context-title">Batch status</div>
            <div class="context-meta">${safeEsc(escHtml, batchState.summary)}</div>
            ${batchState?.focusMissionId ? `
              <div class="context-meta">
                <button class="btn btn-sm" type="button" onclick="focusMissionFromBatch('${safeEsc(escHtml, batchState.focusMissionId)}')">Open affected mission</button>
              </div>
            ` : ''}
            ${Array.isArray(batchState?.results) && batchState.results.length ? `
              <div class="context-list detail-section">
                ${batchState.results.map(item => `
                  <div class="context-card">
                    <div class="context-title">${safeEsc(escHtml, item?.action?.label || item?.mission_id || 'Mission')}</div>
                    <div class="context-meta">
                      <span class="detail-chip">${safeEsc(escHtml, item?.action?.status || 'unknown')}</span>
                      <span>${safeEsc(escHtml, item?.mission_id || '')}</span>
                    </div>
                    <div class="context-meta">
                      <button class="btn btn-sm" type="button" onclick="focusMissionFromBatch('${safeEsc(escHtml, item?.mission_id || '')}')">Open mission</button>
                    </div>
                  </div>
                `).join('')}
              </div>
            ` : ''}
          </div>
        ` : ''}
        <div class="context-list">
          ${items.map(item => `
            <div class="context-card queue-card ${selected.has(item?.mission_id) ? 'active' : ''}">
              <div class="queue-card-header">
                <label class="queue-toggle">
                  <input type="checkbox" ${selected.has(item?.mission_id) ? 'checked' : ''} onchange="toggleApprovalSelection('${safeEsc(escHtml, item?.mission_id || '')}', this.checked)"/>
                  <span class="context-title">${safeEsc(escHtml, item?.mission?.title || item?.title || 'Approval')}</span>
                </label>
                <span class="detail-chip">${safeEsc(escHtml, item?.urgency || item?.approval_state?.status || 'approval')}</span>
              </div>
              <div class="context-meta">
                <span class="detail-chip">${safeEsc(escHtml, item?.approval_state?.status || 'approval')}</span>
                <span>${safeEsc(escHtml, item?.summary || item?.approval_request?.summary || '')}</span>
              </div>
              <div class="context-meta">
                <span>Round ${safeEsc(escHtml, String(item?.current_round || item?.approval_request?.round_id || '—'))}</span>
                <span>${safeEsc(escHtml, `${item?.wait_minutes || 0} min waiting`)}</span>
                ${item?.latest_operator_action ? `<span>${safeEsc(escHtml, item.latest_operator_action.label || item.latest_operator_action.action_key || 'Action')}</span>` : ''}
              </div>
              ${item?.blocking_question ? `<div class="transcript-entry-body">${safeEsc(escHtml, item.blocking_question)}</div>` : ''}
            </div>
          `).join('')}
        </div>
      </section>
    `
  }

  function renderVisualQaPanel(visualQa, escHtml) {
    const summary = visualQa?.summary || {}
    const rounds = visualQa?.rounds || []
    return `
      <div class="mission-metrics surface-metrics">
        <div class="mission-metric">
          <div class="mission-metric-label">Visual rounds</div>
          <div class="mission-metric-value">${safeEsc(escHtml, String(summary.total_rounds || 0))}</div>
        </div>
        <div class="mission-metric">
          <div class="mission-metric-label">Blocking findings</div>
          <div class="mission-metric-value">${safeEsc(escHtml, String(summary.blocking_findings || 0))}</div>
        </div>
        <div class="mission-metric">
          <div class="mission-metric-label">Warnings</div>
          <div class="mission-metric-value">${safeEsc(escHtml, String(summary.warning_findings || 0))}</div>
        </div>
        <div class="mission-metric">
          <div class="mission-metric-label">Confidence</div>
          <div class="mission-metric-value">${safeEsc(escHtml, String(summary.latest_confidence ?? 0))}</div>
        </div>
      </div>
      ${summary.blocking_rounds?.length ? `
        <div class="context-card budget-incident critical">
          <div class="context-title">Blocking visual regressions</div>
          <div class="context-meta">
            <span>${safeEsc(escHtml, `Rounds ${summary.blocking_rounds.join(', ')}`)}</span>
            <span>${safeEsc(escHtml, `${summary.gallery_items || 0} gallery items`)}</span>
          </div>
        </div>
      ` : ''}
      ${rounds.length ? `<div class="context-list">
        ${rounds.map(round => `
          <div class="context-card">
            <div class="context-title">Round ${safeEsc(escHtml, round.round_id)}</div>
            <div class="context-meta">
              <span class="detail-chip">${safeEsc(escHtml, round.status || 'pass')}</span>
              <span>${safeEsc(escHtml, round.summary || '')}</span>
            </div>
            ${round.gallery?.length ? `
              <div class="visual-gallery">
                ${round.gallery.map(item => `
                  <a class="visual-shot" href="/artifacts/${safeEsc(escHtml, item.path)}" target="_blank" rel="noreferrer">
                    <div class="visual-shot-frame">
                      <img src="/artifacts/${safeEsc(escHtml, item.path)}" alt="${safeEsc(escHtml, item.label || 'artifact')}" loading="lazy"/>
                    </div>
                    <div class="visual-shot-meta">
                      <span class="detail-chip">${safeEsc(escHtml, item.kind || 'image')}</span>
                      <span>${safeEsc(escHtml, item.label || item.path)}</span>
                    </div>
                  </a>
                `).join('')}
              </div>
            ` : ''}
            ${round.findings?.length ? `<div class="context-list detail-section">
              ${round.findings.map(finding => `
                <div class="context-card detail-finding">
                  <div class="context-title">${safeEsc(escHtml, finding?.severity || 'finding')}</div>
                  <div class="transcript-entry-body">${safeEsc(escHtml, finding?.message || '')}</div>
                </div>
              `).join('')}
            </div>` : '<div class="empty-panel">No visual findings recorded.</div>'}
            ${round.artifact_path ? `<div class="context-meta"><a class="artifact-link" href="/artifacts/${safeEsc(escHtml, round.artifact_path)}" target="_blank" rel="noreferrer">${safeEsc(escHtml, round.artifact_path)}</a></div>` : ''}
          </div>
        `).join('')}
      </div>` : '<div class="empty-panel">No visual evaluation rounds recorded yet.</div>'}
    `
  }

  function renderCostsPanel(costs, escHtml) {
    const summary = costs?.summary || {}
    const workers = costs?.workers || []
    const incidents = costs?.incidents || []
    const thresholds = summary?.thresholds || {}
    return `
      <div class="mission-metrics surface-metrics">
        <div class="mission-metric">
          <div class="mission-metric-label">Workers</div>
          <div class="mission-metric-value">${safeEsc(escHtml, String(summary.workers || 0))}</div>
        </div>
        <div class="mission-metric">
          <div class="mission-metric-label">Input tokens</div>
          <div class="mission-metric-value">${safeEsc(escHtml, String(summary.input_tokens || 0))}</div>
        </div>
        <div class="mission-metric">
          <div class="mission-metric-label">Output tokens</div>
          <div class="mission-metric-value">${safeEsc(escHtml, String(summary.output_tokens || 0))}</div>
        </div>
        <div class="mission-metric">
          <div class="mission-metric-label">Cost USD</div>
          <div class="mission-metric-value">${safeEsc(escHtml, String(summary.cost_usd || 0))}</div>
        </div>
      </div>
      <div class="context-card">
        <div class="context-title">Budget status</div>
        <div class="context-meta">
          <span class="detail-chip">${safeEsc(escHtml, summary.budget_status || 'unconfigured')}</span>
          ${thresholds.warning_usd != null ? `<span>Warn ${safeEsc(escHtml, String(thresholds.warning_usd))}</span>` : ''}
          ${thresholds.critical_usd != null ? `<span>Critical ${safeEsc(escHtml, String(thresholds.critical_usd))}</span>` : ''}
        </div>
      </div>
      ${incidents.length ? `<div class="context-list detail-section">
        ${incidents.map(incident => `
          <div class="context-card budget-incident ${safeEsc(escHtml, incident?.severity || 'warning')}">
            <div class="context-title">${safeEsc(escHtml, incident?.message || 'Budget incident')}</div>
            <div class="context-meta">
              <span>${safeEsc(escHtml, `Actual ${incident?.actual_cost_usd ?? 0}`)}</span>
              <span>${safeEsc(escHtml, `Threshold ${incident?.threshold_usd ?? 0}`)}</span>
            </div>
          </div>
        `).join('')}
      </div>` : ''}
      ${workers.length ? `<div class="context-list">
        ${workers.map(worker => `
          <div class="context-card">
            <div class="context-title">${safeEsc(escHtml, worker.packet_id || 'worker')}</div>
            <div class="context-meta">
              <span>${safeEsc(escHtml, worker.adapter || 'adapter')}</span>
              <span>${safeEsc(escHtml, worker.turn_status || 'unknown')}</span>
            </div>
            <div class="detail-grid detail-section">
              <div class="detail-row"><div class="detail-key">Input</div><div class="detail-value">${safeEsc(escHtml, worker.input_tokens || 0)}</div></div>
              <div class="detail-row"><div class="detail-key">Output</div><div class="detail-value">${safeEsc(escHtml, worker.output_tokens || 0)}</div></div>
              <div class="detail-row"><div class="detail-key">Cost</div><div class="detail-value">${safeEsc(escHtml, worker.cost_usd || 0)}</div></div>
            </div>
            ${worker.report_path ? `<div class="context-meta"><a class="artifact-link" href="/artifacts/${safeEsc(escHtml, worker.report_path)}" target="_blank" rel="noreferrer">${safeEsc(escHtml, worker.report_path)}</a></div>` : ''}
          </div>
        `).join('')}
      </div>` : '<div class="empty-panel">No worker cost data recorded yet.</div>'}
    `
  }

  function renderTranscriptFilters(selectedPacketTranscript, selectedTranscriptFilter, escHtml) {
    const counts = selectedPacketTranscript?.summary?.block_counts || {}
    const filters = [{key: 'all', label: 'All'}].concat(
      Object.entries(counts)
        .sort((a, b) => a[0].localeCompare(b[0]))
        .map(([key, value]) => ({key, label: `${key} (${value})`}))
    )
    return filters.map(filter => `
      <button
        class="mission-tab ${selectedTranscriptFilter === filter.key ? 'active' : ''}"
        type="button"
        onclick="selectTranscriptFilter('${safeEsc(escHtml, filter.key)}')"
      >${safeEsc(escHtml, filter.label)}</button>
    `).join('')
  }

  function renderTranscriptPreview(
    selectedPacketId,
    selectedPacketTranscript,
    selectedTranscriptFilter,
    selectedTranscriptBlockIndex,
    escHtml,
    renderTranscriptBody,
  ) {
    if (!selectedPacketId) {
      return '<div class="empty-panel">Select a packet to inspect its transcript.</div>'
    }
    if (!selectedPacketTranscript || selectedPacketTranscript.loading) {
      return '<div class="empty-panel">Loading transcript…</div>'
    }
    if (selectedPacketTranscript.error) {
      return `<div class="empty-panel">${safeEsc(escHtml, selectedPacketTranscript.error)}</div>`
    }
    const entries = selectedPacketTranscript.entries || []
    const blocks = selectedPacketTranscript.blocks || []
    if (!entries.length && !blocks.length) {
      return '<div class="empty-panel">No transcript events have been recorded yet.</div>'
    }
    const summary = selectedPacketTranscript.summary || {}
    const milestones = selectedPacketTranscript.milestones || []
    const visibleBlocks =
      selectedTranscriptFilter === 'all'
        ? blocks
        : blocks.filter(block => (block.block_type || 'event') === selectedTranscriptFilter)
    const summaryMeta = [
      `${summary.entry_count || 0} events`,
      ...(summary.latest_timestamp ? [summary.latest_timestamp] : []),
      ...Object.entries(summary.kind_counts || {}).map(([kind, count]) => `${kind} ${count}`),
    ]
    return `
      <div class="context-card">
        <div class="context-title">Packet timeline</div>
        <div class="context-meta">${summaryMeta.map(item => `<span>${safeEsc(escHtml, String(item))}</span>`).join('')}</div>
        ${milestones.length ? `<div class="context-meta">${milestones.map(item => `<span class="run-class">${safeEsc(escHtml, item.event_type || 'milestone')}</span>`).join('')}</div>` : ''}
      </div>
      ${
        visibleBlocks.length
          ? visibleBlocks.slice(-8).map(block => {
              const blockIndex = blocks.indexOf(block)
              const active = blockIndex === selectedTranscriptBlockIndex
              return `
                <button type="button" class="transcript-entry ${safeEsc(escHtml, block.block_type || 'event')} ${active ? 'active' : ''}" onclick="selectTranscriptBlock(${blockIndex})">
                  <div class="transcript-entry-header">
                    <div class="context-title">${safeEsc(escHtml, block.title || 'event')}</div>
                    <span class="run-class">${safeEsc(escHtml, block.block_type || 'event')}</span>
                    ${block.emphasis ? `<span class="detail-chip detail-chip-${safeEsc(escHtml, block.emphasis)}">${safeEsc(escHtml, block.emphasis)}</span>` : ''}
                  </div>
                  <div class="transcript-entry-meta">
                    <span>${safeEsc(escHtml, block.timestamp || '—')}</span>
                    ${block.body ? `<span>${safeEsc(escHtml, block.body)}</span>` : ''}
                    ${block.artifact_path ? `<span class="detail-chip">artifact</span>` : ''}
                    ${block.source_path ? `<span class="detail-chip">source</span>` : ''}
                  </div>
                  ${block.body ? `<div class="transcript-entry-body">${safeEsc(escHtml, block.body)}</div>` : ''}
                </button>
              `
            }).join('')
          : blocks.length
            ? '<div class="empty-panel">No transcript blocks match the current filter.</div>'
            : entries.slice(-8).map(entry => `
                <div class="transcript-entry ${safeEsc(escHtml, entry.kind || '')}">
                  <div class="transcript-entry-header">
                    <div class="context-title">${safeEsc(escHtml, entry.message || entry.event_type || entry.kind || 'event')}</div>
                    <span class="run-class">${safeEsc(escHtml, entry.kind || 'event')}</span>
                  </div>
                  <div class="transcript-entry-meta">
                    <span>${safeEsc(escHtml, entry.timestamp || '—')}</span>
                    ${entry.event_type ? `<span>${safeEsc(escHtml, entry.event_type)}</span>` : ''}
                  </div>
                  ${renderTranscriptBody(entry)}
                </div>
              `).join('')
      }
    `
  }

  function renderTranscriptInspector(
    selectedPacketId,
    selectedPacketTranscript,
    selectedTranscriptBlockIndex,
    escHtml,
    renderTranscriptDetails,
  ) {
    if (!selectedPacketId) {
      return '<div class="empty-panel">Select a packet to inspect transcript evidence.</div>'
    }
    if (!selectedPacketTranscript || selectedPacketTranscript.loading) {
      return '<div class="empty-panel">Loading transcript evidence…</div>'
    }
    if (selectedPacketTranscript.error) {
      return `<div class="empty-panel">${safeEsc(escHtml, selectedPacketTranscript.error)}</div>`
    }
    const blocks = selectedPacketTranscript.blocks || []
    if (!blocks.length || selectedTranscriptBlockIndex == null || !blocks[selectedTranscriptBlockIndex]) {
      return '<div class="empty-panel">Select a transcript block to inspect its evidence.</div>'
    }
    const block = blocks[selectedTranscriptBlockIndex]
    const links = [block.artifact_path, block.source_path].filter(Boolean)
    const burstItems = Array.isArray(block.items) ? block.items : []
    return `
        <div class="context-card">
          <div class="context-title">${safeEsc(escHtml, block.title || 'Transcript evidence')}</div>
          <div class="context-meta">
            <span>${safeEsc(escHtml, block.block_type || 'event')}</span>
            ${block.emphasis ? `<span class="detail-chip detail-chip-${safeEsc(escHtml, block.emphasis)}">${safeEsc(escHtml, block.emphasis)}</span>` : ''}
            <span>${safeEsc(escHtml, block.timestamp || '—')}</span>
          </div>
        ${block.body ? `<div class="transcript-entry-body">${safeEsc(escHtml, block.body)}</div>` : ''}
      </div>
      ${renderTranscriptDetails(block.details, escHtml)}
      ${burstItems.length ? `
        <div class="context-card">
          <div class="context-title">Burst items</div>
          <div class="context-list">
            ${burstItems.map(item => `
              <div class="context-card">
                <div class="context-title">${safeEsc(escHtml, item.title || item.block_type || 'tool')}</div>
                <div class="context-meta">
                  <span>${safeEsc(escHtml, item.block_type || 'tool')}</span>
                  <span>${safeEsc(escHtml, item.timestamp || '—')}</span>
                </div>
                ${item.body ? `<div class="transcript-entry-body">${safeEsc(escHtml, item.body)}</div>` : ''}
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}
      ${links.length ? links.map(path => `
        <div class="context-card">
          <div class="context-title">Linked evidence</div>
          <div class="context-meta"><span class="artifact-link">${safeEsc(escHtml, String(path))}</span></div>
        </div>
      `).join('') : '<div class="empty-panel">No linked evidence path for this block.</div>'}
    `
  }

  window.SpecOrchOperatorConsole = {
    buildMissionSubtitle,
    renderActionButtons,
    renderApprovalQueue,
    renderApprovalQueuePanel,
    renderApprovalWorkspace,
    renderArtifactLinks,
    renderCostsPanel,
    renderDetailValue,
    renderLatestRound,
    renderPacketRow,
    renderRoundContext,
    renderSimpleList,
    renderTranscriptFilters,
    renderTranscriptInspector,
    renderTranscriptPreview,
    renderTranscriptDetails,
    renderVisualQaPanel,
    formatApprovalActionState,
  }
  globalThis.__SPEC_ORCH_OPERATOR_CONSOLE__ = true;
})(window)
