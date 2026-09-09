const BRIDGE = 'http://127.0.0.1:8765';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function token() {
  return (await chrome.storage.local.get('token')).token || '';
}

async function request(path, options = {}) {
  const value = await token();
  if (!value) throw new Error('Bridge token is not configured');
  const response = await fetch(`${BRIDGE}${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${value}`, 'Content-Type': 'application/json' }
  });
  if (!response.ok) throw new Error(`Bridge returned ${response.status}`);
  return response.json();
}

function uniqueSelector(element) {
  if (element.id) return `#${CSS.escape(element.id)}`;
  for (const attribute of ['data-testid', 'name', 'aria-label']) {
    const value = element.getAttribute(attribute);
    if (value) {
      const candidate = `${element.tagName.toLowerCase()}[${attribute}="${CSS.escape(value)}"]`;
      if (document.querySelectorAll(candidate).length === 1) return candidate;
    }
  }
  const parts = [];
  let current = element;
  while (current && current !== document.body && parts.length < 5) {
    let part = current.tagName.toLowerCase();
    const siblings = current.parentElement
      ? [...current.parentElement.children].filter((item) => item.tagName === current.tagName)
      : [];
    if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(current) + 1})`;
    parts.unshift(part);
    current = current.parentElement;
  }
  return parts.join(' > ');
}

function pageState() {
  const interactive = [...document.querySelectorAll('a,button,input,textarea,select,[role="button"]')]
    .filter((element) => element.getClientRects().length > 0)
    .slice(0, 150)
    .map((element) => ({
      tag: element.tagName.toLowerCase(),
      selector: uniqueSelector(element),
      text: (element.innerText || element.getAttribute('aria-label') || element.placeholder || '').trim().slice(0, 160)
    }));
  return {
    url: location.href,
    title: document.title,
    text: (document.body?.innerText || '').slice(0, 12000),
    interactive
  };
}

async function execute(command) {
  if (command.action === 'browser_navigate') {
    location.assign(command.url);
    return;
  }
  if (command.action === 'browser_scroll') {
    window.scrollBy({ top: command.delta_y, behavior: 'smooth' });
    return;
  }
  const element = document.querySelector(command.selector);
  if (!element) throw new Error('Element not found');
  element.scrollIntoView({ block: 'center' });
  if (command.action === 'browser_click') {
    element.click();
  } else if (command.action === 'browser_type') {
    element.focus();
    element.value = command.text;
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
  }
}

async function loop() {
  while (true) {
    try {
      if (document.visibilityState !== 'visible') {
        await sleep(750);
        continue;
      }
      await request('/v1/browser/state', { method: 'POST', body: JSON.stringify(pageState()) });
      const { command } = await request('/v1/browser/next');
      if (command) {
        try {
          await execute(command);
          await request('/v1/browser/result', {
            method: 'POST',
            body: JSON.stringify({ command_id: command.id, status: 'ok' })
          });
        } catch (error) {
          await request('/v1/browser/result', {
            method: 'POST',
            body: JSON.stringify({ command_id: command.id, status: 'error', error: String(error.message || error) })
          });
        }
      }
    } catch (_) {
      // The bridge may be stopped. Retry quietly without leaking page data elsewhere.
    }
    await sleep(750);
  }
}

loop();
