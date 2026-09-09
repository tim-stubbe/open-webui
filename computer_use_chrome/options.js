const input = document.querySelector('#token');
const status = document.querySelector('#status');

chrome.storage.local.get('token').then(({ token }) => { input.value = token || ''; });
document.querySelector('#save').addEventListener('click', async () => {
  await chrome.storage.local.set({ token: input.value.trim() });
  status.textContent = 'Gespeichert';
});
