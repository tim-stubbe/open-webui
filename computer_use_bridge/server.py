#!/usr/bin/env python3
"""Small macOS computer-use bridge with fixed, auditable actions.

It binds to localhost by default. Set COMPUTER_USE_ALLOW_INPUT=true only after
granting Accessibility permission and when input actions are wanted.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import subprocess
import socketserver
import tempfile
import threading
import time
import urllib.parse
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = os.getenv('COMPUTER_USE_HOST', '127.0.0.1')
PORT = int(os.getenv('COMPUTER_USE_PORT', '8765'))
TOKEN = os.getenv('COMPUTER_USE_TOKEN', '')
ALLOW_INPUT = os.getenv('COMPUTER_USE_ALLOW_INPUT', 'false').lower() == 'true'
MAX_BODY_BYTES = 16_384
COMMAND_TTL_SECONDS = 30
_browser_lock = threading.Lock()
_browser_commands: list[dict] = []
_browser_results: dict[str, dict] = {}
_browser_state: dict = {'connected': False}


class RequestError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status


def validate_action(payload: dict) -> dict:
    action = payload.get('action')
    if action == 'click':
        x, y = payload.get('x'), payload.get('y')
        if not isinstance(x, int) or not isinstance(y, int) or not (0 <= x <= 16384 and 0 <= y <= 16384):
            raise RequestError(HTTPStatus.BAD_REQUEST, 'click requires valid x and y coordinates')
        return {'action': action, 'x': x, 'y': y}
    if action == 'type':
        text = payload.get('text')
        if not isinstance(text, str) or not text or len(text) > 4000:
            raise RequestError(HTTPStatus.BAD_REQUEST, 'type requires 1 to 4000 characters')
        return {'action': action, 'text': text}
    if action == 'scroll':
        delta_y = payload.get('delta_y')
        if not isinstance(delta_y, int) or not -4000 <= delta_y <= 4000:
            raise RequestError(HTTPStatus.BAD_REQUEST, 'scroll requires delta_y between -4000 and 4000')
        return {'action': action, 'delta_y': delta_y}
    if action in {'browser_click', 'browser_type'}:
        selector = payload.get('selector')
        if not isinstance(selector, str) or not selector or len(selector) > 500:
            raise RequestError(HTTPStatus.BAD_REQUEST, f'{action} requires a valid selector')
        result = {'action': action, 'selector': selector}
        if action == 'browser_type':
            text = payload.get('text')
            if not isinstance(text, str) or not text or len(text) > 4000:
                raise RequestError(HTTPStatus.BAD_REQUEST, 'browser_type requires 1 to 4000 characters')
            result['text'] = text
        return result
    if action == 'browser_scroll':
        delta_y = payload.get('delta_y')
        if not isinstance(delta_y, int) or not -4000 <= delta_y <= 4000:
            raise RequestError(HTTPStatus.BAD_REQUEST, 'browser_scroll requires a valid delta_y')
        return {'action': action, 'delta_y': delta_y}
    if action == 'browser_navigate':
        url = payload.get('url')
        if not isinstance(url, str) or len(url) > 2048:
            raise RequestError(HTTPStatus.BAD_REQUEST, 'browser_navigate requires a valid URL')
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc or parsed.username or parsed.password:
            raise RequestError(HTTPStatus.BAD_REQUEST, 'only HTTP(S) URLs without embedded credentials are allowed')
        return {'action': action, 'url': url}
    raise RequestError(HTTPStatus.BAD_REQUEST, 'unsupported action')


def run_action(action: dict) -> None:
    if not ALLOW_INPUT:
        raise RequestError(HTTPStatus.FORBIDDEN, 'input actions are disabled')
    if action['action'] == 'click':
        script = f'tell application "System Events" to click at {{{action["x"]}, {action["y"]}}}'
    elif action['action'] == 'type':
        script = 'on run argv\n tell application "System Events" to keystroke (item 1 of argv)\nend run'
        subprocess.run(['osascript', '-e', script, action['text']], check=True, timeout=5)
        return
    else:
        key_code = 126 if action['delta_y'] > 0 else 125
        repeats = max(1, min(20, abs(action['delta_y']) // 100))
        script = f'tell application "System Events" to repeat {repeats} times\nkey code {key_code}\nend repeat'
    subprocess.run(['osascript', '-e', script], check=True, timeout=5)


def queue_browser_action(action: dict) -> dict:
    if not ALLOW_INPUT:
        raise RequestError(HTTPStatus.FORBIDDEN, 'input actions are disabled')
    command = {**action, 'id': str(uuid.uuid4()), 'created_at': time.time()}
    with _browser_lock:
        _browser_commands.append(command)
    return {'status': 'queued', 'command_id': command['id'], 'action': action['action']}


def next_browser_command() -> dict:
    cutoff = time.time() - COMMAND_TTL_SECONDS
    with _browser_lock:
        _browser_commands[:] = [item for item in _browser_commands if item['created_at'] >= cutoff]
        if not _browser_commands:
            return {'command': None}
        return {'command': _browser_commands.pop(0)}


def capture_screen() -> dict:
    with tempfile.TemporaryDirectory(prefix='open-webui-computer-use-') as tmp:
        output = Path(tmp) / 'screen.png'
        subprocess.run(['/usr/sbin/screencapture', '-x', '-t', 'png', str(output)], check=True, timeout=8)
        return {
            'mime_type': 'image/png',
            'image_base64': base64.b64encode(output.read_bytes()).decode('ascii'),
        }


class Handler(BaseHTTPRequestHandler):
    server_version = 'OpenWebUIComputerUse/0.1'

    def _send(self, status: HTTPStatus, payload: dict) -> None:
        encoded = json.dumps(payload, separators=(',', ':')).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()
        self.wfile.write(encoded)

    def _authorize(self) -> None:
        supplied = self.headers.get('Authorization', '').removeprefix('Bearer ')
        if not TOKEN or not hmac.compare_digest(supplied, TOKEN):
            raise RequestError(HTTPStatus.UNAUTHORIZED, 'unauthorized')

    def _payload(self) -> dict:
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError as exc:
            raise RequestError(HTTPStatus.BAD_REQUEST, 'invalid content length') from exc
        if size <= 0 or size > MAX_BODY_BYTES:
            raise RequestError(HTTPStatus.BAD_REQUEST, 'invalid request size')
        try:
            payload = json.loads(self.rfile.read(size))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RequestError(HTTPStatus.BAD_REQUEST, 'invalid JSON') from exc
        if not isinstance(payload, dict):
            raise RequestError(HTTPStatus.BAD_REQUEST, 'JSON object required')
        return payload

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._authorize()
            if self.path == '/v1/status':
                self._send(HTTPStatus.OK, {'status': 'ok', 'platform': 'macos', 'input_enabled': ALLOW_INPUT})
            elif self.path == '/v1/observe':
                self._send(HTTPStatus.OK, capture_screen())
            elif self.path == '/v1/browser/state':
                with _browser_lock:
                    self._send(HTTPStatus.OK, dict(_browser_state))
            elif self.path == '/v1/browser/next':
                self._send(HTTPStatus.OK, next_browser_command())
            else:
                self._send(HTTPStatus.NOT_FOUND, {'error': 'not found'})
        except RequestError as exc:
            self._send(exc.status, {'error': str(exc)})
        except (OSError, subprocess.SubprocessError):
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': 'screen capture failed'})

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._authorize()
            payload = self._payload()
            if self.path == '/v1/browser/state':
                with _browser_lock:
                    _browser_state.clear()
                    _browser_state.update(payload, connected=True, updated_at=time.time())
                self._send(HTTPStatus.OK, {'status': 'ok'})
                return
            if self.path == '/v1/browser/result':
                command_id = payload.get('command_id')
                if not isinstance(command_id, str):
                    raise RequestError(HTTPStatus.BAD_REQUEST, 'command_id is required')
                with _browser_lock:
                    _browser_results[command_id] = {**payload, 'updated_at': time.time()}
                self._send(HTTPStatus.OK, {'status': 'ok'})
                return
            if self.path != '/v1/actions':
                self._send(HTTPStatus.NOT_FOUND, {'error': 'not found'})
                return
            action = validate_action(payload)
            if action['action'].startswith('browser_'):
                self._send(HTTPStatus.ACCEPTED, queue_browser_action(action))
            else:
                run_action(action)
                self._send(HTTPStatus.OK, {'status': 'ok', 'action': action['action']})
        except RequestError as exc:
            self._send(exc.status, {'error': str(exc)})
        except (OSError, subprocess.SubprocessError):
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': 'input action failed'})

    def log_message(self, format: str, *args) -> None:
        # Do not log request bodies because typed text may be private.
        print(f'{self.client_address[0]} - {format % args}')

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(HTTPStatus.NO_CONTENT, {})


class BridgeHTTPServer(ThreadingHTTPServer):
    """HTTP server that avoids a potentially blocking reverse-DNS lookup."""

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port


def main() -> None:
    if not TOKEN:
        raise SystemExit('COMPUTER_USE_TOKEN must be set')
    server = BridgeHTTPServer((HOST, PORT), Handler)
    print(f'Computer-use bridge listening on http://{HOST}:{PORT}; input_enabled={ALLOW_INPUT}')
    server.serve_forever()


if __name__ == '__main__':
    main()
