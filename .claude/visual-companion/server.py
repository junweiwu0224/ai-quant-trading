#!/usr/bin/env python3
"""Visual companion server for design choices."""
import json
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

class CompanionHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
            self.wfile.write(html.encode('utf-8'))
        else:
            super().do_GET()

if __name__ == '__main__':
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = HTTPServer(('127.0.0.1', port), CompanionHandler)
    print(f'Visual companion serving at http://127.0.0.1:{port}')
    server.serve_forever()
