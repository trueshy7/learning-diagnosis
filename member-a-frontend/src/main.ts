if (import.meta.env.VITE_BACKEND_CONTRACT === 'group-v0') {
  import('./group/main').catch(showError);
} else {
  import('./full-main').catch(showError);
}
function showError() {
  const root = document.getElementById('app');
  if (root) root.textContent = '应用暂时无法启动，请刷新重试。';
}
