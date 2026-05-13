const elements = {
  statusDot: document.getElementById('status-dot'),
  statusText: document.getElementById('status-text'),
  updatedAt: document.getElementById('updated-at'),
  sessionPercent: document.getElementById('session-percent'),
  sessionBar: document.getElementById('session-bar'),
  sessionReset: document.getElementById('session-reset'),
  weeklyPercent: document.getElementById('weekly-percent'),
  weeklyBar: document.getElementById('weekly-bar'),
  weeklyReset: document.getElementById('weekly-reset'),
  refreshButton: document.getElementById('refresh-button'),
  error: document.getElementById('error'),
  mascotWrap: document.getElementById('mascot-wrap'),
  mascotMode: document.getElementById('mascot-mode'),
  mascotCaption: document.getElementById('mascot-caption'),
};

function clampPercent(value) {
  const number = Number(value || 0);
  return Math.max(0, Math.min(100, Math.round(number)));
}

function formatMinutes(value) {
  if (value === null || value === undefined) return '--';
  const minutes = Math.max(0, Math.round(Number(value)));
  if (minutes < 60) return `${minutes}分`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (rest === 0) return `${hours}時間`;
  return `${hours}時間${rest}分`;
}

function formatTime(value) {
  const date = value ? new Date(value) : new Date();
  return new Intl.DateTimeFormat('ja-JP', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date);
}

function setStatus(kind, text) {
  elements.statusDot.classList.remove('ok', 'error', 'waiting');
  elements.statusDot.classList.add(kind);
  elements.statusText.textContent = text;
}

function updateMascot(session, weekly) {
  const score = Math.max(session, weekly);
  const wrap = elements.mascotWrap;
  if (!wrap) return;

  wrap.classList.remove('mood-calm', 'mood-active', 'mood-busy', 'mood-hot', 'mood-max');

  if (score < 25) {
    wrap.classList.add('mood-calm');
    elements.mascotMode.textContent = 'IDLE';
    elements.mascotCaption.textContent = 'LOW USAGE';
  } else if (score < 50) {
    wrap.classList.add('mood-active');
    elements.mascotMode.textContent = 'ACTIVE';
    elements.mascotCaption.textContent = 'WARMING UP';
  } else if (score < 75) {
    wrap.classList.add('mood-busy');
    elements.mascotMode.textContent = 'BUSY';
    elements.mascotCaption.textContent = 'STEADY WORK';
  } else if (score < 90) {
    wrap.classList.add('mood-hot');
    elements.mascotMode.textContent = 'HOT';
    elements.mascotCaption.textContent = 'USAGE RISING';
  } else {
    wrap.classList.add('mood-max');
    elements.mascotMode.textContent = 'MAX';
    elements.mascotCaption.textContent = 'TAKE A BREAK';
  }
}

function render(data) {
  const session = clampPercent(data.sessionPercent);
  const weekly = clampPercent(data.weeklyPercent);

  elements.sessionPercent.textContent = `${session}%`;
  elements.sessionBar.style.width = `${session}%`;
  elements.sessionReset.textContent = formatMinutes(data.sessionResetMinutes);

  elements.weeklyPercent.textContent = `${weekly}%`;
  elements.weeklyBar.style.width = `${weekly}%`;
  elements.weeklyReset.textContent = formatMinutes(data.weeklyResetMinutes);

  elements.updatedAt.textContent = formatTime(data.updatedAt);
  setStatus('ok', data.status || 'LOCAL');
  elements.error.hidden = true;
  updateMascot(session, weekly);
}

async function refresh() {
  elements.refreshButton.disabled = true;
  elements.refreshButton.textContent = 'UPDATING';
  setStatus('waiting', 'UPDATING');

  try {
    const response = await fetch('/api/usage', { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    render(data);
  } catch (error) {
    setStatus('error', 'ERROR');
    elements.error.textContent = error.message;
    elements.error.hidden = false;
  } finally {
    elements.refreshButton.disabled = false;
    elements.refreshButton.textContent = 'UPDATE';
  }
}

elements.refreshButton.addEventListener('click', refresh);
refresh();
setInterval(refresh, 60_000);
