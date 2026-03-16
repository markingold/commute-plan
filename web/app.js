function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('tab-btn-active'));
  document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('tab-panel-active'));

  const btn = document.querySelector('.tab-btn[data-tab="' + tab + '"]');
  if (btn) {
    btn.classList.add('tab-btn-active');
  }

  const panel = document.getElementById('tab-panel-' + tab);
  if (panel) {
    panel.classList.add('tab-panel-active');
  }

  const ids = ['planner-tab-input', 'config-gui-tab-input', 'config-raw-tab-input', 'feedback-tab-input'];
  ids.forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.value = tab;
    }
  });

  try {
    const url = new URL(window.location.href);
    url.searchParams.set('tab', tab);
    window.history.replaceState({}, '', url.toString());
  } catch (_) {
    // Ignore URL mutation issues in older/non-browser contexts.
  }
}
