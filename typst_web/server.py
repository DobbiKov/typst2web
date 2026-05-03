"""
Local dev server for typst-to-web.

Serves the generated HTML and proxies AI API requests to avoid CORS issues
with providers that don't send Access-Control-Allow-Origin headers (e.g. ilaas.fr).

Usage:
    typst-web serve output.html [--port 7890]
    python -m typst_web.server output.html
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


_PROXY_PATH = "/ai-proxy"


def _make_handler(html_path: Path):
    html_bytes = html_path.read_bytes()
    html_len   = len(html_bytes)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quieter logging
            print(f"  {self.address_string()} {fmt % args}")

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            if self.path in ("/", "/index.html", f"/{html_path.name}"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(html_len))
                self._cors()
                self.end_headers()
                self.wfile.write(html_bytes)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path != _PROXY_PATH:
                self.send_response(404)
                self.end_headers()
                return

            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)

            try:
                req_data = json.loads(body)
            except json.JSONDecodeError:
                self._json_error(400, "Invalid JSON")
                return

            target_url = req_data.get("url")
            headers    = req_data.get("headers", {})
            payload    = req_data.get("body")

            if not target_url:
                self._json_error(400, "Missing 'url'")
                return

            try:
                upstream = urllib.request.Request(
                    target_url,
                    data=json.dumps(payload).encode() if payload is not None else None,
                    headers={**headers, "Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(upstream, timeout=120) as resp:
                    self.send_response(resp.status)
                    # Forward content-type; force CORS open
                    ct = resp.headers.get("Content-Type", "application/json")
                    self.send_header("Content-Type", ct)
                    self._cors()
                    self.end_headers()
                    # Stream chunks as they arrive
                    while True:
                        chunk = resp.read(4096)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()

            except urllib.error.HTTPError as e:
                err_body = e.read()
                self.send_response(e.code)
                self.send_header("Content-Type", "application/json")
                self._cors()
                self.end_headers()
                self.wfile.write(err_body)
            except Exception as exc:
                self._json_error(502, str(exc))

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin",  "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, x-api-key, anthropic-version, anthropic-dangerous-allow-browser")

        def _json_error(self, code: int, msg: str):
            body = json.dumps({"error": msg}).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(html_path: Path, port: int = 7890):
    html_path = html_path.resolve()
    if not html_path.exists():
        raise FileNotFoundError(html_path)

    handler = _make_handler(html_path)
    httpd   = HTTPServer(("127.0.0.1", port), handler)
    url     = f"http://localhost:{port}/"
    print(f"\nServing {html_path.name}")
    print(f"  Open:  {url}")
    print(f"  Proxy: http://localhost:{port}{_PROXY_PATH}")
    print("  Press Ctrl+C to stop.\n")

    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    import sys
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 7890
    if not path:
        print("Usage: python -m typst_web.server OUTPUT.html [PORT]")
        sys.exit(1)
    serve(path, port)
