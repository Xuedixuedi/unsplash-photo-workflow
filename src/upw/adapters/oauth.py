"""Local loopback that catches the Unsplash OAuth redirect."""

from __future__ import annotations

import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from upw.errors import UpwError


def wait_for_code(redirect_uri: str, expected_state: str, timeout: float = 180) -> str:
    parsed = urllib.parse.urlparse(redirect_uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    path = parsed.path or "/"
    box: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib name
            request = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(request.query)
            if request.path != path:
                _reply(self, 404, "Not found.")
                return
            code = (params.get("code") or [""])[0]
            state = (params.get("state") or [""])[0]
            if not code or state != expected_state:
                _reply(self, 400, "Authorization failed. You can close this tab.")
                return
            box["code"] = code
            _reply(self, 200, "Unsplash authorized. You can close this tab and return to the terminal.")

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    server.timeout = 1
    deadline = time.time() + timeout
    try:
        while "code" not in box and time.time() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    if "code" not in box:
        raise UpwError("Timed out waiting for the Unsplash redirect.")
    return box["code"]


def _reply(handler: BaseHTTPRequestHandler, status: int, message: str) -> None:
    body = message.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
