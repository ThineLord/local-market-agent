/* Apply before styles load so the first paint matches the saved appearance. */
(() => {
  const key = 'lma-theme';
  const system = matchMedia('(prefers-color-scheme: dark)');
  const normalize = value => ['light', 'dark', 'system'].includes(value) ? value : 'system';
  let preference = 'system';
  try { preference = normalize(localStorage.getItem(key)); } catch {}

  function apply() {
    const theme = preference === 'system' ? (system.matches ? 'dark' : 'light') : preference;
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.themePreference = preference;
    document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#17221e' : '#f6f5f0';
    window.dispatchEvent(new CustomEvent('lma-theme-change', {detail: {preference, theme}}));
  }

  window.lmaTheme = Object.freeze({
    get preference() { return preference; },
    setPreference(value) {
      preference = normalize(value);
      try { localStorage.setItem(key, preference); } catch {}
      apply();
    }
  });
  system.addEventListener('change', () => { if (preference === 'system') apply(); });
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) {
      preference = normalize(event.newValue);
      apply();
    }
  });
  apply();
})();
