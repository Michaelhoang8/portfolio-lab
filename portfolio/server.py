"""Local-only HTTP adapter; no third-party runtime dependencies."""
import argparse
import json
import os
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .db import connect, initialize
from . import services, data_apps, security_apps, ml_apps, devops_apps, rest_api
from .validation import ValidationError, NotFoundError

STATIC = Path(__file__).parent / 'static'

def handler_for(database, api_key=None):
    api_key = os.environ.get('PORTFOLIO_API_KEY','') if api_key is None else api_key
    class Handler(BaseHTTPRequestHandler):
        def is_rest(self):
            return self.path.split('?',1)[0] == '/api/v1' or self.path.startswith('/api/v1/')

        def do_PATCH(self):
            if self.is_rest():
                rest_api.handle(self,database,api_key)
            else:
                self.reply(404, {'error':'Not found'})

        do_PUT = do_PATCH
        do_DELETE = do_PATCH
        do_OPTIONS = do_PATCH

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
            if self.is_rest():
                rest_api.handle(self,database,api_key)
                return
            if self.path == '/api/state':
                db = connect(database)
                try:
                    self.reply(200, services.snapshot(db))
                finally:
                    db.close()
                return
            files = {'/': ('index.html', 'text/html; charset=utf-8'),
                     '/rest': ('rest.html', 'text/html; charset=utf-8'),
                     '/rest.js': ('rest.js', 'text/javascript; charset=utf-8'),
                     '/rest.css': ('rest.css', 'text/css; charset=utf-8'),
                     '/openapi.json': ('openapi.json', 'application/json; charset=utf-8'),
                     '/devops': ('devops.html', 'text/html; charset=utf-8'),
                     '/devops.js': ('devops.js', 'text/javascript; charset=utf-8'),
                     '/devops.css': ('devops.css', 'text/css; charset=utf-8'),
                     '/ml': ('ml.html', 'text/html; charset=utf-8'),
                     '/ml.js': ('ml.js', 'text/javascript; charset=utf-8'),
                     '/ml.css': ('ml.css', 'text/css; charset=utf-8'),
                     '/security': ('security.html', 'text/html; charset=utf-8'),
                     '/security.js': ('security.js', 'text/javascript; charset=utf-8'),
                     '/security.css': ('security.css', 'text/css; charset=utf-8'),
                     '/data': ('data.html', 'text/html; charset=utf-8'),
                     '/data.js': ('data.js', 'text/javascript; charset=utf-8'),
                     '/data.css': ('data.css', 'text/css; charset=utf-8'),
                     '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                     '/identities.js': ('identities.js', 'text/javascript; charset=utf-8'),
                     '/identities.css': ('identities.css', 'text/css; charset=utf-8'),
                     '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if self.path not in files:
                self.reply(404, {'error': 'Not found'})
                return
            name, mime = files[self.path]
            raw=(STATIC / name).read_bytes()
            self.reply(200, json.loads(raw) if name=='openapi.json' else raw, mime)

        def do_POST(self):
            if self.is_rest():
                rest_api.handle(self,database,api_key)
                return
            # Custom header + JSON prevent browser cross-origin form submissions.
            if self.headers.get('X-Portfolio-Client') != 'browser' or self.headers.get('Content-Type') != 'application/json':
                self.reply(403, {'error': 'JSON requests require X-Portfolio-Client: browser'})
                return
            db = connect(database)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                limit = 6_100_000 if self.path.startswith(('/api/data/','/api/security/','/api/ml/','/api/devops/')) else 16384
                if not 0 < length <= limit:
                    raise ValidationError(f'Request must contain 1–{limit} bytes')
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValidationError('Expected a JSON object')
                devops_routes={'/api/devops/manifest':devops_apps.manifest,'/api/devops/pipeline':devops_apps.pipeline,'/api/devops/reliability':devops_apps.reliability}
                if self.path in devops_routes:
                    self.reply(200,devops_routes[self.path](data))
                    return
                ml_routes = {'/api/ml/train':ml_apps.train,'/api/ml/search':ml_apps.search,'/api/ml/evaluate':ml_apps.evaluate}
                if self.path in ml_routes:
                    self.reply(200, ml_routes[self.path](data))
                    return
                security_routes = {'/api/security/logs':security_apps.auth_logs,
                    '/api/security/headers':security_apps.inspect_headers,'/api/security/secrets':security_apps.scan_secrets}
                if self.path in security_routes:
                    self.reply(200, security_routes[self.path](data))
                    return
                data_routes = {'/api/data/profile':data_apps.profile, '/api/data/clean':data_apps.clean,
                               '/api/data/sales':data_apps.sales}
                if self.path in data_routes:
                    self.reply(200, data_routes[self.path](data))
                    return
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
