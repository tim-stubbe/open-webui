"""
title: Local Computer Use
author: Tim Stubbe
version: 0.1.0
description: Read and control the connected Mac or Chrome tab through the local bridge.
required_open_webui_version: 0.11.0
"""

import json
import os
import urllib.parse
from pathlib import Path

import aiohttp
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        bridge_url: str = Field(default=os.getenv('COMPUTER_USE_BRIDGE_URL', ''), description='Mac bridge URL')
        bridge_token: str = Field(default=os.getenv('COMPUTER_USE_BRIDGE_TOKEN', ''), description='Mac bridge token')
        timeout_seconds: int = Field(default=20, ge=2, le=60)

    def __init__(self):
        self.valves = self.Valves()

    def _bridge_config(self) -> tuple[str, str]:
        url = self.valves.bridge_url.rstrip('/')
        token = self.valves.bridge_token
        if url and token:
            return url, token

        config_path = Path(os.getenv('DATA_DIR', '/app/backend/data')) / 'computer-use.json'
        try:
            config = json.loads(config_path.read_text(encoding='utf-8'))
            return str(config.get('url', '')).rstrip('/'), str(config.get('token', ''))
        except (OSError, ValueError, TypeError):
            return '', ''


    def _server_browser_config(self) -> tuple[str, str]:
        config_path = Path(os.getenv('DATA_DIR', '/app/backend/data')) / 'browser-use.json'
        try:
            config = json.loads(config_path.read_text(encoding='utf-8'))
            return str(config.get('url', '')).rstrip('/'), str(config.get('token', ''))
        except (OSError, ValueError, TypeError):
            return '', ''

    @staticmethod
    def _validate_url(url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError('Only HTTP(S) URLs without embedded credentials are allowed')
        return url

    async def _browserless_function(self, code: str, context: dict) -> str:
        base_url, token = self._server_browser_config()
        if not base_url or not token:
            return json.dumps({'error': 'TrueNAS browser is not configured'})
        timeout = aiohttp.ClientTimeout(total=max(30, self.valves.timeout_seconds))
        try:
            async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
                async with session.post(
                    f'{base_url}/chromium/function',
                    params={'token': token},
                    json={'code': code, 'context': context},
                    allow_redirects=False,
                ) as response:
                    data = await response.text()
                    if response.status >= 400:
                        return json.dumps({'error': f'TrueNAS browser returned HTTP {response.status}'})
                    return data[:30000]
        except (aiohttp.ClientError, TimeoutError):
            return json.dumps({'error': 'TrueNAS browser is unavailable'})

    async def browse_website(self, url: str) -> str:
        """Open a public website in Chromium on TrueNAS and return its rendered text and links.

        :param url: Full HTTP(S) URL without embedded credentials.
        """
        try:
            url = self._validate_url(url)
        except ValueError as exc:
            return json.dumps({'error': str(exc)})
        code = """export default async ({ page, context }) => {
          await page.goto(context.url, { waitUntil: 'domcontentloaded', timeout: 20000 });
          await new Promise(r => setTimeout(r, 800));
          const data = await page.evaluate(() => ({
            title: document.title, url: location.href,
            text: (document.body?.innerText || '').slice(0, 20000),
            links: [...document.querySelectorAll('a[href]')].slice(0, 80).map(a => ({text: (a.innerText || '').trim().slice(0, 160), href: a.href}))
          }));
          return { data, type: 'application/json' };
        };"""
        return await self._browserless_function(code, {'url': url})

    async def click_website(self, url: str, selector: str) -> str:
        """Open a website on TrueNAS, click an exact CSS selector, and return the resulting page text.

        :param url: Full HTTP(S) page URL.
        :param selector: Exact CSS selector found on the page.
        """
        try:
            url = self._validate_url(url)
        except ValueError as exc:
            return json.dumps({'error': str(exc)})
        if not selector or len(selector) > 500:
            return json.dumps({'error': 'Invalid selector'})
        code = """export default async ({ page, context }) => {
          await page.goto(context.url, { waitUntil: 'domcontentloaded', timeout: 20000 });
          await page.waitForSelector(context.selector, { timeout: 8000 });
          await page.click(context.selector);
          await new Promise(r => setTimeout(r, 1000));
          return { data: { title: await page.title(), url: page.url(), text: (await page.$eval('body', e => e.innerText)).slice(0, 20000) }, type: 'application/json' };
        };"""
        return await self._browserless_function(code, {'url': url, 'selector': selector})

    async def _request(self, method: str, path: str, payload: dict | None = None) -> str:
        """Call the fixed local bridge endpoint without exposing its token."""
        base_url, bridge_token = self._bridge_config()
        if not base_url or not bridge_token:
            return json.dumps({'error': 'Computer-use bridge is not configured'})
        timeout = aiohttp.ClientTimeout(total=self.valves.timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
                async with session.request(
                    method,
                    f'{base_url}{path}',
                    headers={'Authorization': f'Bearer {bridge_token}'},
                    json=payload,
                    allow_redirects=False,
                ) as response:
                    result = await response.json(content_type=None)
                    if response.status >= 400:
                        return json.dumps({'error': result.get('error', 'Bridge request failed')})
                    return json.dumps(result, ensure_ascii=False)
        except (aiohttp.ClientError, TimeoutError):
            return json.dumps({'error': 'Computer-use bridge is unavailable'})

    async def computer_status(self) -> str:
        """Check whether the private Mac computer-use bridge and input controls are available."""
        return await self._request('GET', '/v1/status')

    async def read_browser(self) -> str:
        """Read the active Chrome page URL, title, visible text and interactive elements before acting."""
        return await self._request('GET', '/v1/browser/state')

    async def click_browser(self, selector: str) -> str:
        """Click one element in Chrome using an exact CSS selector from read_browser.

        :param selector: Exact CSS selector returned by read_browser; do not invent selectors.
        """
        return await self._request('POST', '/v1/actions', {'action': 'browser_click', 'selector': selector})

    async def type_in_browser(self, selector: str, text: str) -> str:
        """Replace the value of one Chrome input with text.

        :param selector: Exact CSS selector returned by read_browser.
        :param text: Text the user explicitly asked to enter; never enter secrets without confirmation.
        """
        return await self._request(
            'POST', '/v1/actions', {'action': 'browser_type', 'selector': selector, 'text': text}
        )

    async def scroll_browser(self, delta_y: int) -> str:
        """Scroll the active Chrome page vertically.

        :param delta_y: Pixels to scroll, between -4000 and 4000. Positive values scroll down.
        """
        return await self._request('POST', '/v1/actions', {'action': 'browser_scroll', 'delta_y': delta_y})

    async def navigate_browser(self, url: str) -> str:
        """Navigate the active Chrome tab to an HTTP or HTTPS URL.

        :param url: Full HTTP(S) URL without embedded credentials.
        """
        return await self._request('POST', '/v1/actions', {'action': 'browser_navigate', 'url': url})
