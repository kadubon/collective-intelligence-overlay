"""Loopback HTTP fixture without HTTPServer's unrelated reverse-DNS lookup."""

import sys
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingTCPServer


class LoopbackHTTPServer(ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"owned process")

        def log_message(self, *args):
            pass

    with LoopbackHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler) as server:
        server.serve_forever()
