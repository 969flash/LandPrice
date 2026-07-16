"""브라우저 → 로컬 파일 수신 서버 (V-World 벌크 우회 수신용).

크롬 페이지 컨텍스트의 fetch()가 받은 ZIP을 POST로 넘겨받아
data/raw/vworld_bulk/ 에 저장한다. localhost 전용, 일회성.
크롬 PNA(사설망 접근) preflight에 응답하도록 OPTIONS 처리 포함.
"""

import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

DEST = Path(__file__).resolve().parents[1] / "data" / "raw" / "vworld_bulk"
DEST.mkdir(parents=True, exist_ok=True)
PORT = 8877

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "content-type,x-filename",
    "Access-Control-Allow-Private-Network": "true",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s\n" % (fmt % args))

    def _headers(self, code=200):
        self.send_response(code)
        for k, v in CORS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_OPTIONS(self):
        self._headers(204)

    def do_POST(self):
        name = self.headers.get("x-filename", "unknown.bin")
        name = re.sub(r"[^\w.\-]", "_", name)[:100]  # 경로 조작 방지
        length = int(self.headers.get("content-length", 0))
        if length <= 0 or length > 2_000_000_000:
            self._headers(400)
            return
        data = self.rfile.read(length)
        ok = data[:2] == b"PK"  # ZIP 매직 확인
        out = DEST / (name if ok else name + ".notzip")
        out.write_bytes(data)
        self._headers(200)
        self.wfile.write(b"ok" if ok else b"notzip")
        sys.stderr.write(f"수신: {out.name} ({length:,} bytes, zip={ok})\n")


if __name__ == "__main__":
    print(f"수신 서버 시작: http://localhost:{PORT} → {DEST}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
