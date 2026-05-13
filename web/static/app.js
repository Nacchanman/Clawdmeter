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
  setStatus('ok', data.status || 'allowed');
  elements.error.hidden = true;
}

async function refresh() {
  elements.refreshButton.disabled = true;
  elements.refreshButton.textContent = '更新中...';
  setStatus('waiting', '更新中');

  try {
    const response = await fetch('/api/usage', { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    render(data);
  } catch (error) {
    setStatus('error', 'エラー');
    elements.error.textContent = error.message;
    elements.error.hidden = false;
  } finally {
    elements.refreshButton.disabled = false;
    elements.refreshButton.textContent = '今すぐ更新';
  }
}

elements.refreshButton.addEventListener('click', refresh);
refresh();
setInterval(refresh, 60_000);
