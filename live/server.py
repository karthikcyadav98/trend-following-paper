"""Zero-dependency dashboard server (stdlib http.server)."""
import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB, STATE = os.path.join(ROOT, "web"), os.path.join(ROOT, "state")
MIME = {".html": "text/html; charset=utf-8", ".json": "application/json",
        ".css": "text/css", ".js": "text/javascript", ".png": "image/png"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json", code=200):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/api/portfolio":
            f = os.path.join(STATE, "portfolio.json")
            if not os.path.exists(f):
                return self._send(json.dumps({"error": "not generated yet"}), code=404)
            return self._send(open(f, "rb").read())
        rel = "index.html" if p == "/" else p.lstrip("/")
        fp = os.path.normpath(os.path.join(WEB, rel))
        if not fp.startswith(WEB) or not os.path.isfile(fp):
            return self._send("not found", "text/plain", 404)
        self._send(open(fp, "rb").read(), MIME.get(os.path.splitext(fp)[1], "application/octet-stream"))


def serve(port=8788):
    print(f"  dashboard -> http://127.0.0.1:{port}\n  ctrl-c to stop")
    try:
        ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
