/**
 * Automated Code Vulnerability Reviewer - Dashboard Application Client Logic
 */

// Application State
const state = {
  currentTab: 'new-review',
  sourceType: 'local',
  currentReview: null,
  allFindings: [],
  activeFilters: {
    search: '',
    severity: 'all',
    agent: 'all',
    category: 'all',
  },
  historyItems: [],
};

// Initialization
document.addEventListener('DOMContentLoaded', () => {
  checkBackendHealth();
  loadHistory();
});

// Check API Health Status
async function checkBackendHealth() {
  const statusEl = document.getElementById('backend-status');
  const statusText = document.getElementById('backend-status-text');
  try {
    const res = await fetch('/health');
    if (res.ok) {
      statusEl.style.color = '#10b981';
      statusEl.style.borderColor = 'rgba(16, 185, 129, 0.3)';
      statusEl.style.background = 'rgba(16, 185, 129, 0.1)';
      statusText.textContent = 'Backend Connected';
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch (err) {
    statusEl.style.color = '#ef4444';
    statusEl.style.borderColor = 'rgba(239, 68, 68, 0.3)';
    statusEl.style.background = 'rgba(239, 68, 68, 0.1)';
    statusText.textContent = 'Backend Disconnected';
  }
}

// Navigation Tab Switcher
function switchTab(tabId) {
  state.currentTab = tabId;
  const tabs = ['new-review', 'findings', 'history'];
  tabs.forEach((t) => {
    const view = document.getElementById(`view-${t}`);
    const navBtn = document.getElementById(`tab-nav-${t === 'new-review' ? 'new' : t}`);
    if (t === tabId) {
      view.classList.add('active');
      navBtn.classList.add('active');
    } else {
      view.classList.remove('active');
      navBtn.classList.remove('active');
    }
  });
  hideError();
  if (tabId === 'history') {
    loadHistory();
  }
}

// Source Type Switcher (Local vs GitHub)
function setSourceType(type) {
  state.sourceType = type;
  const btnLocal = document.getElementById('btn-src-local');
  const btnGithub = document.getElementById('btn-src-github');
  const formLocal = document.getElementById('form-group-local');
  const formGithub = document.getElementById('form-group-github');

  if (type === 'local') {
    btnLocal.classList.add('active');
    btnGithub.classList.remove('active');
    formLocal.style.display = 'block';
    formGithub.style.display = 'none';
  } else {
    btnLocal.classList.remove('active');
    btnGithub.classList.add('active');
    formLocal.style.display = 'none';
    formGithub.style.display = 'block';
  }
}

// Error Banner Utilities
function showError(msg) {
  const banner = document.getElementById('global-error');
  banner.textContent = msg;
  banner.style.display = 'block';
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function hideError() {
  const banner = document.getElementById('global-error');
  banner.style.display = 'none';
  banner.textContent = '';
}

// Helper: Pipeline Step Updater
function updatePipelineStep(stepId, state) {
  const step = document.getElementById(`step-${stepId}`);
  if (!step) return;
  step.classList.remove('active', 'completed');
  if (state === 'active') {
    step.classList.add('active');
  } else if (state === 'completed') {
    step.classList.add('completed');
  }
}

// Helper: Agent Telemetry Card Updater
function updateAgentCard(agentPrefix, status, findings, execTime) {
  const statusEl = document.getElementById(`agent-${agentPrefix}-status`);
  const findingsEl = document.getElementById(`agent-${agentPrefix}-findings`);
  const timeEl = document.getElementById(`agent-${agentPrefix}-time`);

  if (statusEl) {
    statusEl.className = 'agent-status-pill ' + (
      status === 'RUNNING' ? 'agent-status-running' :
      status === 'DONE' ? 'agent-status-done' : 'agent-status-idle'
    );
    statusEl.textContent = status;
  }
  if (findingsEl && findings !== undefined) findingsEl.textContent = findings;
  if (timeEl && execTime !== undefined) timeEl.textContent = `${Number(execTime).toFixed(2)}s`;
}

// Helper: Normalize finding structure whether flat or nested in ModeratedFinding
function normalizeFinding(f) {
  if (!f) return {};
  if (f.finding) {
    const inner = f.finding;
    const ev = inner.evidence || {};
    const rem = inner.remediation || {};
    return {
      id: inner.id,
      title: inner.title,
      description: inner.description,
      category: inner.category,
      severity: inner.severity ? String(inner.severity).toUpperCase() : 'INFO',
      confidence: inner.confidence,
      file_path: ev.file_path || '',
      line_start: ev.start_line || 1,
      line_end: ev.end_line || 1,
      code_snippet: ev.code_snippet || '',
      remediation_advice: rem.recommended_fix || rem.explanation || '',
      cwe_ids: inner.cwe_id ? [inner.cwe_id] : (f.cwe_ids || []),
      priority_rank: f.priority_rank,
      risk_score: f.risk_score !== undefined ? f.risk_score : (inner.raw_risk_score || 0),
      agent_roles: (f.sources && f.sources.length) ? f.sources.map(s => String(s).toLowerCase()) : (inner.agent_role ? [String(inner.agent_role).toLowerCase()] : []),
      agent_role: inner.agent_role ? String(inner.agent_role).toLowerCase() : 'security_auditor',
    };
  }
  return f;
}

// Trigger Review Pipeline Execution
async function startReview() {
  hideError();

  let targetPath = '';
  let ref = null;
  let token = null;

  if (state.sourceType === 'local') {
    targetPath = document.getElementById('local-path').value.trim();
    if (!targetPath) {
      showError('Please provide a valid local repository directory path.');
      return;
    }
  } else {
    targetPath = document.getElementById('github-url').value.trim();
    ref = document.getElementById('github-ref').value.trim() || null;
    token = document.getElementById('github-token').value.trim() || null;
    if (!targetPath) {
      showError('Please provide a valid GitHub repository URL.');
      return;
    }
  }

  // Set UI to loading state
  const btn = document.getElementById('btn-start-review');
  const spinner = document.getElementById('btn-start-review-spinner');
  const btnText = document.getElementById('btn-start-review-text');

  btn.disabled = true;
  spinner.style.display = 'inline-block';
  btnText.textContent = 'Analyzing Repository...';

  // Animate stages
  updatePipelineStep('ingestion', 'active');
  updatePipelineStep('context', '');
  updatePipelineStep('analysis', '');
  updatePipelineStep('moderation', '');

  updateAgentCard('sec', 'RUNNING', 0, 0);
  updateAgentCard('arch', 'RUNNING', 0, 0);
  const modStatus = document.getElementById('agent-mod-status');
  if (modStatus) {
    modStatus.className = 'agent-status-pill agent-status-running';
    modStatus.textContent = 'WAITING';
  }

  const startTime = Date.now();
  const stepTimer = setInterval(() => {
    const elapsed = (Date.now() - startTime) / 1000;
    if (elapsed > 1.0) updatePipelineStep('ingestion', 'completed');
    if (elapsed > 1.2 && elapsed < 2.5) updatePipelineStep('context', 'active');
    if (elapsed > 2.5) {
      updatePipelineStep('context', 'completed');
      updatePipelineStep('analysis', 'active');
    }
    const secTime = document.getElementById('agent-sec-time');
    const archTime = document.getElementById('agent-arch-time');
    if (secTime) secTime.textContent = `${elapsed.toFixed(1)}s`;
    if (archTime) archTime.textContent = `${elapsed.toFixed(1)}s`;
  }, 300);

  try {
    const payload = {
      source_type: state.sourceType,
      path_or_url: targetPath,
      ref: ref,
      token: token,
    };

    const res = await fetch('/api/v1/dashboard/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    clearInterval(stepTimer);

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: 'Scan request failed.' }));
      throw new Error(errData.detail || errData.error || `HTTP ${res.status}`);
    }

    const review = await res.json();
    const totalElapsed = (Date.now() - startTime) / 1000;

    // Complete all pipeline stages
    updatePipelineStep('ingestion', 'completed');
    updatePipelineStep('context', 'completed');
    updatePipelineStep('analysis', 'completed');
    updatePipelineStep('moderation', 'completed');

    // Update Telemetry Metrics from review report
    const secFindings = (review.findings || []).filter(f => f.agent_roles && f.agent_roles.includes('security_auditor')).length;
    const archFindings = (review.findings || []).filter(f => f.agent_roles && f.agent_roles.includes('software_architect')).length;
    const dedupCount = (review.moderation_metadata && review.moderation_metadata.deduplicated_count) || 0;

    updateAgentCard('sec', 'DONE', secFindings, totalElapsed * 0.45);
    updateAgentCard('arch', 'DONE', archFindings, totalElapsed * 0.45);

    if (modStatus) {
      modStatus.className = 'agent-status-pill agent-status-done';
      modStatus.textContent = 'COMPLETED';
    }
    const dedupEl = document.getElementById('agent-mod-dedup');
    if (dedupEl) dedupEl.textContent = dedupCount;
    const modStateEl = document.getElementById('agent-mod-state');
    if (modStateEl) modStateEl.textContent = 'Arbitrated';

    // Set state and render findings
    state.currentReview = review;
    state.allFindings = (review.findings || []).map(normalizeFinding);

    renderFindings(state.allFindings);
    updateSummaryStats(review);

    // Switch to Findings Explorer
    setTimeout(() => {
      switchTab('findings');
    }, 600);

  } catch (err) {
    clearInterval(stepTimer);
    showError(err.message || 'An unexpected error occurred during scan execution.');
    updateAgentCard('sec', 'IDLE', 0, 0);
    updateAgentCard('arch', 'IDLE', 0, 0);
  } finally {
    btn.disabled = false;
    spinner.style.display = 'none';
    btnText.textContent = 'Launch Vulnerability Review';
  }
}

// Update Summary Statistics Counters
function updateSummaryStats(review) {
  const findings = (review.findings || []).map(normalizeFinding);
  const total = findings.length;
  let crit = 0, high = 0, med = 0, low = 0;
  let maxRisk = 0.0;

  findings.forEach((f) => {
    const sev = (f.severity || '').toLowerCase();
    if (sev === 'critical') crit++;
    else if (sev === 'high') high++;
    else if (sev === 'medium') med++;
    else if (sev === 'low') low++;

    const risk = Number(f.risk_score || 0);
    if (risk > maxRisk) maxRisk = risk;
  });

  document.getElementById('stat-total').textContent = total;
  document.getElementById('stat-critical').textContent = crit;
  document.getElementById('stat-high').textContent = high;
  document.getElementById('stat-medium').textContent = med;
  document.getElementById('stat-low').textContent = low;
  document.getElementById('stat-max-risk').textContent = maxRisk.toFixed(2);

  const badge = document.getElementById('tab-findings-count');
  if (badge) badge.textContent = total;
}

// Filter Finding Handlers
function setSeverityFilter(sev) {
  state.activeFilters.severity = sev;
  document.querySelectorAll('.sev-btn').forEach((b) => {
    if (b.getAttribute('data-sev') === sev) {
      b.classList.add('active');
    } else {
      b.classList.remove('active');
    }
  });
  applyFilters();
}

function applyFilters() {
  state.activeFilters.search = (document.getElementById('filter-search').value || '').toLowerCase().trim();
  state.activeFilters.agent = document.getElementById('filter-agent').value;
  state.activeFilters.category = document.getElementById('filter-category').value;

  const filtered = state.allFindings.filter((item) => {
    // Severity
    if (state.activeFilters.severity !== 'all') {
      if ((item.severity || '').toLowerCase() !== state.activeFilters.severity) {
        return false;
      }
    }

    // Agent
    if (state.activeFilters.agent !== 'all') {
      const roles = item.agent_roles || [item.agent_role];
      if (!roles.includes(state.activeFilters.agent)) {
        return false;
      }
    }

    // Category
    if (state.activeFilters.category !== 'all') {
      const cat = (item.category || '').toLowerCase();
      if (!cat.includes(state.activeFilters.category)) {
        return false;
      }
    }

    // Search query
    if (state.activeFilters.search) {
      const q = state.activeFilters.search;
      const titleMatch = (item.title || '').toLowerCase().includes(q);
      const descMatch = (item.description || '').toLowerCase().includes(q);
      const fileMatch = (item.file_path || '').toLowerCase().includes(q);
      const cweMatch = (item.cwe_ids || []).some((c) => c.toLowerCase().includes(q));
      if (!titleMatch && !descMatch && !fileMatch && !cweMatch) {
        return false;
      }
    }

    return true;
  });

  renderFindings(filtered);
}

// Helper: Escape HTML
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Render Findings List
function renderFindings(findings) {
  const container = document.getElementById('findings-list');
  if (!findings || findings.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <p>No findings match the current filter criteria.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = findings.map((f, idx) => {
    const sev = (f.severity || 'info').toLowerCase();
    const rank = f.priority_rank ? `#${f.priority_rank}` : `#${idx + 1}`;
    const riskScore = f.risk_score !== undefined ? Number(f.risk_score).toFixed(2) : 'N/A';
    const filePath = escapeHtml(f.file_path || 'Unknown file');
    const startLine = f.line_start || 1;
    const endLine = f.line_end || startLine;
    const lineLabel = startLine === endLine ? `Line ${startLine}` : `Lines ${startLine}-${endLine}`;
    const agentRoles = (f.agent_roles && f.agent_roles.length > 0)
      ? f.agent_roles.map(r => r === 'security_auditor' ? 'Security Auditor' : 'Software Architect').join(', ')
      : (f.agent_role || 'Automated Reviewer');

    const cwePills = (f.cwe_ids || []).map(cwe => `<span class="cwe-pill">${escapeHtml(cwe)}</span>`).join('');

    // Code preview formatting
    let codePreviewHtml = '';
    if (f.code_snippet) {
      const lines = f.code_snippet.split('\n');
      const linesHtml = lines.map((line, lIdx) => {
        const currLineNum = startLine + lIdx;
        const isHighlight = currLineNum >= startLine && currLineNum <= endLine;
        return `
          <div class="code-line ${isHighlight ? 'highlight' : ''}">
            <span class="line-num">${currLineNum}</span>
            <span class="line-text">${escapeHtml(line)}</span>
          </div>
        `;
      }).join('');

      codePreviewHtml = `
        <div class="code-evidence-block">
          <div class="code-evidence-header">
            <span>Evidence: ${filePath}:${lineLabel}</span>
            <span>Snippet (${lines.length} lines)</span>
          </div>
          <div class="code-container">
            ${linesHtml}
          </div>
        </div>
      `;
    }

    // Remediation Advice formatting
    let remediationHtml = '';
    if (f.remediation_advice || f.suggested_fix) {
      const advice = escapeHtml(f.remediation_advice || f.suggested_fix);
      remediationHtml = `
        <div class="remediation-box">
          <div class="remediation-header">
            <span>💡</span> Recommended Remediation Guidance
          </div>
          <div class="remediation-text">${advice}</div>
        </div>
      `;
    }

    return `
      <div class="finding-card">
        <div class="finding-card-header">
          <div class="finding-badges">
            <span class="priority-rank-badge">${rank}</span>
            <span class="sev-badge ${sev}">${sev}</span>
            <span class="risk-score-badge">Risk: ${riskScore}</span>
            <span class="agent-source-badge">${escapeHtml(agentRoles)}</span>
          </div>
          <div style="font-size: 0.78rem; color: var(--text-muted); font-family: var(--font-mono);">
            ${escapeHtml(f.category || 'General')}
          </div>
        </div>

        <h3 class="finding-title">${escapeHtml(f.title || 'Untitled Issue')}</h3>
        <div class="finding-loc">
          <span>📍</span> ${filePath}:${startLine}
        </div>

        ${cwePills ? `<div class="finding-cwe-list">${cwePills}</div>` : ''}

        <p class="finding-desc">${escapeHtml(f.description || '')}</p>

        ${codePreviewHtml}
        ${remediationHtml}
      </div>
    `;
  }).join('');
}

// Load Review History Scans
async function loadHistory() {
  const tbody = document.getElementById('history-table-body');
  try {
    const res = await fetch('/api/v1/history?limit=50');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const items = await res.json();
    state.historyItems = items;

    populateCompareDropdowns(items);

    if (!items || items.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" style="text-align: center; color: var(--text-dim); padding: 2rem;">
            No historical reviews found. Run a review to generate your first audit record!
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = items.map((item) => {
      const createdDate = item.created_at ? new Date(item.created_at).toLocaleString() : 'N/A';
      const critCount = (item.severity_distribution && item.severity_distribution.critical) || 0;
      return `
        <tr>
          <td><code style="color: var(--accent-cyan);">${escapeHtml(item.review_id.substring(0, 8))}</code></td>
          <td><strong>${escapeHtml(item.repo_id)}</strong></td>
          <td style="color: var(--text-muted); font-size: 0.8rem;">${createdDate}</td>
          <td><span style="font-weight: 700;">${item.total_findings}</span></td>
          <td><span style="color: ${critCount > 0 ? 'var(--sev-critical-text)' : 'var(--text-muted)'}; font-weight: 700;">${critCount}</span></td>
          <td><code>${item.max_risk_score.toFixed(2)}</code></td>
          <td>
            <div style="display: flex; gap: 0.4rem;">
              <button class="btn-secondary" style="padding: 0.3rem 0.6rem; font-size: 0.75rem;" onclick="inspectReview('${item.review_id}')">
                Inspect
              </button>
              <button class="btn-secondary" style="padding: 0.3rem 0.6rem; font-size: 0.75rem;" onclick="selectForCompare('${item.review_id}')">
                Compare
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; color: var(--sev-critical-text); padding: 1.5rem;">
          Failed to load review history: ${escapeHtml(err.message)}
        </td>
      </tr>
    `;
  }
}

// Populate Compare Dropdowns
function populateCompareDropdowns(items) {
  const baseSelect = document.getElementById('compare-base-select');
  const targetSelect = document.getElementById('compare-target-select');
  if (!baseSelect || !targetSelect) return;

  const optionsHtml = (items || []).map((it) => {
    const label = `${it.review_id.substring(0, 8)} - ${it.repo_id} (${it.total_findings} findings)`;
    return `<option value="${it.review_id}">${escapeHtml(label)}</option>`;
  }).join('');

  baseSelect.innerHTML = optionsHtml;
  targetSelect.innerHTML = optionsHtml;

  // Set default selection: target = 0 (newest), base = 1 (second newest) if available
  if (items.length > 1) {
    targetSelect.selectedIndex = 0;
    baseSelect.selectedIndex = 1;
  }
}

// Select a review for comparison shortcut
function selectForCompare(reviewId) {
  const targetSelect = document.getElementById('compare-target-select');
  const baseSelect = document.getElementById('compare-base-select');
  if (targetSelect.value !== reviewId) {
    targetSelect.value = reviewId;
  } else if (baseSelect) {
    baseSelect.value = reviewId;
  }
  window.scrollTo({ top: document.querySelector('.comparison-card').offsetTop - 60, behavior: 'smooth' });
}

// Inspect a historical review
async function inspectReview(reviewId) {
  try {
    const res = await fetch(`/api/v1/history/${reviewId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const review = await res.json();

    state.currentReview = review;
    state.allFindings = (review.findings || []).map(normalizeFinding);

    renderFindings(state.allFindings);
    updateSummaryStats(review);

    switchTab('findings');
  } catch (err) {
    showError(`Failed to load review details: ${err.message}`);
  }
}

// Compare two scans
async function compareScans() {
  hideError();
  const baseId = document.getElementById('compare-base-select').value;
  const targetId = document.getElementById('compare-target-select').value;

  if (!baseId || !targetId) {
    showError('Please select both a Base Scan (V1) and a Target Scan (V2) to compare.');
    return;
  }

  const btn = document.getElementById('btn-compare');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Comparing...';

  try {
    const res = await fetch('/api/v1/history/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        base_review_id: baseId,
        target_review_id: targetId,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Comparison request failed.' }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const diff = await res.json();
    renderCompareResults(diff);
  } catch (err) {
    showError(`Comparison error: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span>📊</span> Compare Scans';
  }
}

// Render Comparison Results
function renderCompareResults(diff) {
  const resultsDiv = document.getElementById('compare-results');
  resultsDiv.style.display = 'block';

  document.getElementById('diff-new-count').textContent = diff.summary.new_count;
  document.getElementById('diff-resolved-count').textContent = diff.summary.resolved_count;
  document.getElementById('diff-persistent-count').textContent = diff.summary.persistent_count;

  const deltaEl = document.getElementById('diff-risk-delta');
  const delta = diff.summary.risk_score_delta;
  deltaEl.textContent = (delta > 0 ? `+${delta.toFixed(2)}` : delta.toFixed(2));
  deltaEl.style.color = delta > 0 ? 'var(--sev-critical-text)' : 'var(--accent-green)';

  const listDiv = document.getElementById('diff-findings-list');
  let listHtml = '';

  // New findings
  (diff.new_findings || []).map(normalizeFinding).forEach((f) => {
    const sev = (f.severity || 'info').toLowerCase();
    listHtml += `
      <div class="finding-card" style="border-left: 4px solid var(--sev-critical-border);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
          <span style="font-size: 0.75rem; font-weight: 700; color: var(--sev-critical-text); background: var(--sev-critical-bg); padding: 0.15rem 0.5rem; border-radius: 4px;">
            + NEW VULNERABILITY INTRODUCED
          </span>
          <span class="sev-badge ${sev}">${sev}</span>
        </div>
        <strong>${escapeHtml(f.title)}</strong>
        <div style="font-size: 0.8rem; color: var(--text-dim); margin-top: 0.25rem;">
          ${escapeHtml(f.file_path)}:${f.line_start || 1}
        </div>
      </div>
    `;
  });

  // Resolved findings
  (diff.resolved_findings || []).map(normalizeFinding).forEach((f) => {
    const sev = (f.severity || 'info').toLowerCase();
    listHtml += `
      <div class="finding-card" style="border-left: 4px solid var(--accent-green); opacity: 0.9;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
          <span style="font-size: 0.75rem; font-weight: 700; color: var(--accent-green); background: rgba(16, 185, 129, 0.1); padding: 0.15rem 0.5rem; border-radius: 4px;">
            - VULNERABILITY RESOLVED
          </span>
          <span class="sev-badge ${sev}">${sev}</span>
        </div>
        <strong>${escapeHtml(f.title)}</strong>
        <div style="font-size: 0.8rem; color: var(--text-dim); margin-top: 0.25rem;">
          ${escapeHtml(f.file_path)}:${f.line_start || 1}
        </div>
      </div>
    `;
  });

  // Persistent findings (first 5)
  const persistent = diff.persistent_findings || [];
  if (persistent.length > 0) {
    listHtml += `
      <div style="font-size: 0.82rem; color: var(--text-dim); margin-top: 0.5rem;">
        Persistent unchanged findings: ${persistent.length} (retained across both scan revisions).
      </div>
    `;
  }

  if (!listHtml) {
    listHtml = '<div style="color: var(--text-muted); font-size: 0.85rem;">No finding differences found between the two selected scans.</div>';
  }

  listDiv.innerHTML = listHtml;
}
