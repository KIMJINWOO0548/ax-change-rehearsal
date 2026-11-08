"""Loopback-only workbench server. Not a production or multi-user service."""
from __future__ import annotations

import json
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .app import build_context, execute_run
from .engine import ROOT
from .validation import _reject_constant, _unique_pairs


ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/index.html': ('index.html', 'text/html; charset=utf-8'),
          '/app.css': ('app.css', 'text/css; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/review.js': ('review.js', 'text/javascript; charset=utf-8')}
MAX_BODY = 2048
CSP = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port):
        self.csrf_token = secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1', port), WorkbenchHandler)

    def handle_error(self, request, client_address):
        # Do not disclose local paths or request contents through traceback output.
        pass


class WorkbenchHandler(BaseHTTPRequestHandler):
    server_version = 'AXRehearsal'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format, *args):
        pass

    def _send(self, status, content, content_type='application/json; charset=utf-8'):
        body = content if isinstance(content, bytes) else json.dumps(content, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', CSP)
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, code, message):
        self._send(status, {'error': {'code': code, 'message': message}})

    def _trusted_request(self):
        hosts = self.headers.get_all('Host', [])
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if len(hosts) != 1 or hosts[0].lower() not in allowed:
            self._error(403, 'UNTRUSTED_HOST', '이 작업대의 로컬 주소로 접속해야 합니다.')
            return False
        origins = self.headers.get_all('Origin', [])
        if origins and (len(origins) != 1 or origins[0] != 'http://' + hosts[0].lower()):
            self._error(403, 'UNTRUSTED_ORIGIN', '다른 사이트에서 보낸 요청을 차단했습니다.')
            return False
        sites = self.headers.get_all('Sec-Fetch-Site', [])
        if sites and (len(sites) != 1 or sites[0] not in {'same-origin', 'none'}):
            self._error(403, 'CROSS_SITE_REQUEST', '다른 사이트에서 보낸 요청을 차단했습니다.')
            return False
        return True

    def do_GET(self):
        if not self._trusted_request():
            return
        if self.path == '/api/context':
            try:
                context = build_context()
                self._send(200, {**context, 'csrf_token': self.server.csrf_token})
            except Exception:
                self._error(500, 'CONTEXT_UNAVAILABLE', '규정 근거를 읽지 못했습니다. 로컬 프로젝트 파일을 확인하세요.')
        elif self.path in ASSETS:
            name, content_type = ASSETS[self.path]
            try:
                self._send(200, (ROOT / 'web' / name).read_bytes(), content_type)
            except OSError:
                self._error(503, 'ASSET_UNAVAILABLE', '화면 파일을 읽지 못했습니다.')
        else:
            self._error(404, 'NOT_FOUND', '요청한 경로가 없습니다.')

    def do_POST(self):
        if not self._trusted_request():
            return
        if self.path != '/api/run':
            self._error(404, 'NOT_FOUND', '요청한 경로가 없습니다.')
            return
        tokens = self.headers.get_all('X-CSRF-Token', [])
        if len(tokens) != 1 or not tokens[0].isascii() or not secrets.compare_digest(tokens[0], self.server.csrf_token):
            self._error(403, 'SESSION_REQUIRED', '화면을 새로고침한 뒤 다시 실행하세요.')
            return
        if self.headers.get_all('Transfer-Encoding'):
            self._error(400, 'INVALID_ENCODING', '고정 길이 JSON 요청만 지원합니다.')
            return
        content_types = self.headers.get_all('Content-Type', [])
        if len(content_types) != 1 or content_types[0].split(';')[0].strip().lower() != 'application/json':
            self._error(415, 'JSON_REQUIRED', 'JSON 요청만 지원합니다.')
            return
        lengths = self.headers.get_all('Content-Length', [])
        if len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,8}', lengths[0]):
            self._error(400, 'INVALID_LENGTH', '요청 길이가 유효하지 않습니다.')
            return
        length = int(lengths[0])
        if length > MAX_BODY:
            self._error(413, 'BODY_TOO_LARGE', '요청 크기 제한을 넘었습니다.')
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('Incomplete request')
            config = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_pairs,
                                parse_constant=_reject_constant)
            result = execute_run(config)
        except (ValueError, UnicodeError):
            self._error(400, 'INVALID_CONFIGURATION', '설정을 확인하세요. 지원하지 않는 버전·입력 또는 변경된 정책 근거입니다.')
        except (TimeoutError, OSError):
            self._error(408, 'REQUEST_TIMEOUT', '요청을 읽지 못했습니다. 다시 시도하세요.')
        except Exception:
            self._error(500, 'RUN_FAILED', '실행을 완료하지 못했습니다. 결과를 통과로 간주하지 마세요.')
        else:
            self._send(200, result)

    def do_OPTIONS(self):
        self._error(405, 'METHOD_NOT_ALLOWED', '지원하지 않는 요청 방식입니다.')


def make_server(port=8765):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('Invalid port')
    return WorkbenchServer(port)
