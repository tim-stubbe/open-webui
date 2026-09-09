"""
title: Local Computer Use
author: Tim Stubbe
version: 0.1.0
description: Read and control the connected Mac or Chrome tab through the local bridge.
required_open_webui_version: 0.11.0
"""

import json
import os

import aiohttp
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        bridge_url: str = Field(default=os.getenv('COMPUTER_USE_BRIDGE_URL', ''), description='Mac bridge URL')
        bridge_token: str = Field(default=os.getenv('COMPUTER_USE_BRIDGE_TOKEN', ''), description='Mac bridge token')
        timeout_seconds: int = Field(default=10, ge=2, le=30)

    def __init__(self):
        self.valves = self.Valves()

    async def _request(self, method: str, path: str, payload: dict | None = None) -> str:
        """Call the fixed local bridge endpoint without exposing its token."""
        base_url = self.valves.bridge_url.rstrip('/')
        if not base_url or not self.valves.bridge_token:
            return json.dumps({'error': 'Computer-use bridge is not configured'})
        timeout = aiohttp.ClientTimeout(total=self.valves.timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
                async with session.request(
                    method,
                    f'{base_url}{path}',
                    headers={'Authorization': f'Bearer {self.valves.bridge_token}'},
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
