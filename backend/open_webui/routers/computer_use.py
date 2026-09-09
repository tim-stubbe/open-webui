"""Admin-only proxy for a separately hosted computer-use bridge.

The bridge URL and its token are server-side environment variables. Clients never
receive the bridge credential and cannot choose an arbitrary upstream URL.
"""

import logging
import os
from typing import Literal

import aiohttp
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from open_webui.utils.auth import get_admin_user

log = logging.getLogger(__name__)
router = APIRouter()

COMPUTER_USE_BRIDGE_URL = os.getenv('COMPUTER_USE_BRIDGE_URL', '').rstrip('/')
COMPUTER_USE_BRIDGE_TOKEN = os.getenv('COMPUTER_USE_BRIDGE_TOKEN', '')
COMPUTER_USE_TIMEOUT_SECONDS = float(os.getenv('COMPUTER_USE_TIMEOUT_SECONDS', '10'))


class ComputerAction(BaseModel):
    action: Literal[
        'click',
        'type',
        'scroll',
        'browser_click',
        'browser_type',
        'browser_scroll',
        'browser_navigate',
    ]
    x: int | None = Field(default=None, ge=0, le=16384)
    y: int | None = Field(default=None, ge=0, le=16384)
    text: str | None = Field(default=None, max_length=4000)
    delta_y: int | None = Field(default=None, ge=-4000, le=4000)
    selector: str | None = Field(default=None, min_length=1, max_length=500)
    url: str | None = Field(default=None, min_length=1, max_length=2048)

    @model_validator(mode='after')
    def validate_action_arguments(self):
        if self.action == 'click' and (self.x is None or self.y is None):
            raise ValueError('click requires x and y')
        if self.action == 'type' and not self.text:
            raise ValueError('type requires non-empty text')
        if self.action == 'scroll' and self.delta_y is None:
            raise ValueError('scroll requires delta_y')
        if self.action in {'browser_click', 'browser_type'} and not self.selector:
            raise ValueError(f'{self.action} requires selector')
        if self.action == 'browser_type' and not self.text:
            raise ValueError('browser_type requires non-empty text')
        if self.action == 'browser_scroll' and self.delta_y is None:
            raise ValueError('browser_scroll requires delta_y')
        if self.action == 'browser_navigate' and not self.url:
            raise ValueError('browser_navigate requires url')
        return self


def _bridge_headers() -> dict[str, str]:
    return {'Authorization': f'Bearer {COMPUTER_USE_BRIDGE_TOKEN}'}


def _ensure_configured() -> None:
    if not COMPUTER_USE_BRIDGE_URL or not COMPUTER_USE_BRIDGE_TOKEN:
        raise HTTPException(status_code=503, detail='Computer use bridge is not configured')


async def _bridge_request(method: str, path: str, payload: dict | None = None) -> dict:
    _ensure_configured()
    timeout = aiohttp.ClientTimeout(total=COMPUTER_USE_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
            async with session.request(
                method,
                f'{COMPUTER_USE_BRIDGE_URL}{path}',
                headers=_bridge_headers(),
                json=payload,
                allow_redirects=False,
            ) as response:
                data = await response.json(content_type=None)
                if response.status >= 400:
                    raise HTTPException(
                        status_code=502,
                        detail=data.get('error', 'Computer use bridge rejected the request'),
                    )
                return data
    except HTTPException:
        raise
    except (aiohttp.ClientError, TimeoutError) as exc:
        log.warning('Computer use bridge request failed: %s', type(exc).__name__)
        raise HTTPException(status_code=502, detail='Computer use bridge is unavailable') from exc


@router.get('/status')
async def computer_use_status(user=Depends(get_admin_user)):
    return await _bridge_request('GET', '/v1/status')


@router.get('/observe')
async def computer_use_observe(user=Depends(get_admin_user)):
    return await _bridge_request('GET', '/v1/observe')


@router.get('/browser')
async def computer_use_browser_state(user=Depends(get_admin_user)):
    return await _bridge_request('GET', '/v1/browser/state')


@router.post('/actions')
async def computer_use_action(form_data: ComputerAction, user=Depends(get_admin_user)):
    return await _bridge_request('POST', '/v1/actions', form_data.model_dump(exclude_none=True))
