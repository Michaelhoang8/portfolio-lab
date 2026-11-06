"""Local-only HTTP adapter; no third-party runtime dependencies."""
import argparse
import json
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .db import connect, initialize
from . import services
from .validation import ValidationError, NotFoundError

STATIC = Path(__file__).parent / 'static'

def handler_for(database):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, content_type='application/json; charset=utf-8'):
            raw = json.dumps(body).encode() if content_type.startswith('application/json') else body
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == '/api/state':
                db = connect(database)
                try:
                    self.reply(200, services.snapshot(db))
                finally:
                    db.close()
                return
            files = {'/': ('index.html', 'text/html; charset=utf-8'),
                     '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                     '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if self.path not in files:
                self.reply(404, {'error': 'Not found'})
                return
            name, mime = files[self.path]
            self.reply(200, (STATIC / name).read_bytes(), mime)

        def do_POST(self):
            # Custom header + JSON prevent browser cross-origin form submissions.
            if self.headers.get('X-Portfolio-Client') != 'browser' or self.headers.get('Content-Type') != 'application/json':
                self.reply(403, {'error': 'JSON requests require X-Portfolio-Client: browser'})
                return
            db = connect(database)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValidationError('Request must contain 1–16384 bytes')
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValidationError('Expected a JSON object')
                routes = {'/api/tickets': services.ticket_create, '/api/products': services.product_create,
                          '/api/movements': services.movement_create, '/api/experiments': services.experiment_create}
                move = re.fullmatch(r'/api/tickets/(\d+)/status', self.path)
                if move:
                    result = services.ticket_move(db, int(move[1]), data)
                elif self.path in routes:
                    result = routes[self.path](db, data)
                else:
                    raise NotFoundError('Route not found')
                self.reply(200 if move else 201, result)
            except NotFoundError as error:
                self.reply(404, {'error': str(error)})
            except sqlite3.IntegrityError:
                self.reply(409, {'error': 'Record conflicts with existing data; SKUs must be unique'})
            except (ValueError, UnicodeError) as error:
                self.reply(400, {'error': str(error)})
            except Exception:
                self.log_error('Unexpected server error')
                self.reply(500, {'error': 'Unexpected server error'})
            finally:
                db.close()
    return Handler

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--database', default='data/portfolio.db')
    args = parser.parse_args()
    initialize(args.database)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(args.database))
    print(f'Portfolio Lab: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
