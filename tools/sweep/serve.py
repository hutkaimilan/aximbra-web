import http.server, functools, os, sys, socketserver

ROOT = sys.argv[1]

class H(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        p = super().translate_path(path)
        if not os.path.exists(p) and "." not in os.path.basename(p):
            return os.path.join(ROOT, "index.html")
        return p

class TS(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

with TS(("127.0.0.1", int(sys.argv[2])),
                            functools.partial(H, directory=ROOT)) as s:
    s.serve_forever()
