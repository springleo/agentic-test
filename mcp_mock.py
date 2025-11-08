#!/usr/bin/env python3
"""
Simple mock MCP server for local testing.

Usage:
  python mcp_mock.py --port 8080

It accepts POST requests to /predict, /analyze, /v1/predict, /mcp/predict and returns a dummy JSON analysis.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import argparse
import json
from urllib.parse import urlparse


class Handler(BaseHTTPRequestHandler):
    def _respond(self, code: int, data: dict):
        txt = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(txt)))
        self.end_headers()
        self.wfile.write(txt)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path not in ("/predict", "/analyze", "/v1/predict", "/mcp/predict", "/"):
            self._respond(404, {"error": "unknown endpoint"})
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            payload = {"raw": raw.decode("utf-8", errors="replace")}

        # produce a trivial deterministic "analysis"
        metrics = payload.get("metrics") if isinstance(payload, dict) else None
        total = metrics.get("total_runs") if metrics else None

        resp = {
            "status": "ok",
            "analysis": {
                "received_total_runs": total,
                "prediction": "no-issues" if (total and total > 0) else "no-data",
            },
        }

        self._respond(200, resp)

    def do_GET(self):
        self._respond(200, {"info": "mcp-mock running"})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()

    server = HTTPServer((args.host, args.port), Handler)
    print(f"mcp_mock listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down")
        server.server_close()


if __name__ == "__main__":
    main()
