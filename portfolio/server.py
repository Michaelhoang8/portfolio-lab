"""Local-only HTTP adapter; no third-party runtime dependencies."""
import argparse
import json
import os
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .db import connect, initialize
from . import services, data_apps, security_apps, ml_apps, devops_apps, rest_api, capabilities
from .validation import ValidationError, NotFoundError, ConflictError
from .json_input import decode, read_exact

STATIC = Path(__file__).parent / 'static'

def handler_for(database, api_key=None):
    api_key = os.environ.get('PORTFOLIO_API_KEY','') if api_key is None else api_key
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def parse_request(self):
            if not super().parse_request():
                return False
            hosts=self.headers.get_all('Host',[])
            match=re.fullmatch(r'(?:localhost|127\.0\.0\.1|\[::1\])(?::([0-9]{1,5}))?',hosts[0].strip(),re.I) if len(hosts)==1 else None
            if not match or match.group(1) is not None and not 1<=int(match.group(1))<=65535:
                self.close_connection=True
                self.reply(400, {'error':'Use one loopback Host header: localhost, 127.0.0.1, or [::1]'})
                return False
            return True

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
            try:
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
                self.end_headers()
                if self.command != 'HEAD':
                    self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if self.is_rest():
                rest_api.handle(self,database,api_key)
                return
            path = self.path.split('?', 1)[0]
            if path == '/api/movements.csv':
                db = connect(database)
                chunks = services.movement_csv(db)
                try:
                    first = next(chunks)
                    self.send_response(200)
                    self.send_header('Content-Type','text/csv; charset=utf-8')
                    self.send_header('Content-Disposition','attachment; filename="stock-movements.csv"')
                    self.send_header('Cache-Control','no-store')
                    self.send_header('X-Content-Type-Options','nosniff')
                    self.send_header('Connection','close')
                    self.close_connection = True
                    self.end_headers()
                    if self.command == 'HEAD':
                        return
                    self.wfile.write(first.encode('utf-8'))
                    for chunk in chunks:
                        self.wfile.write(chunk.encode('utf-8'))
                except (BrokenPipeError, ConnectionResetError):
                    pass  # The download was cancelled; close its read cursor below.
                finally:
                    chunks.close()
                    db.close()
                return
            if path == '/api/state':
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
                     '/rest_transport.js': ('rest_transport.js', 'text/javascript; charset=utf-8'),
                     '/csv_columns.js': ('csv_columns.js', 'text/javascript; charset=utf-8'),
                     '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                     '/observatory.js': ('observatory.js', 'text/javascript; charset=utf-8'),
                     '/observatory.css': ('observatory.css', 'text/css; charset=utf-8'),
                     '/capabilities.js': ('capabilities.js', 'text/javascript; charset=utf-8'),
                     '/identities.js': ('identities.js', 'text/javascript; charset=utf-8'),
                     '/identities.css': ('identities.css', 'text/css; charset=utf-8'),
                     '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if path not in files:
                self.reply(404, {'error': 'Not found'})
                return
            name, mime = files[path]
            raw=(STATIC / name).read_bytes()
            self.reply(200, json.loads(raw) if name=='openapi.json' else raw, mime)

        def do_POST(self):
            if self.is_rest():
                rest_api.handle(self,database,api_key)
                return
            # Custom header + JSON prevent browser cross-origin form submissions.
            if self.headers.get('X-Portfolio-Client') != 'browser' or self.headers.get_content_type() != 'application/json':
                self.reply(403, {'error': 'JSON requests require X-Portfolio-Client: browser'})
                return
            db = connect(database)
            try:
                if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
                    raise ValidationError('Provide one Content-Length; transfer encoding is not supported')
                raw_length = self.headers.get('Content-Length', '')
                if not re.fullmatch(r'[0-9]{1,8}', raw_length):
                    raise ValidationError('A valid Content-Length is required')
                length = int(raw_length)
                limit = 6_100_000 if self.path.startswith(('/api/data/','/api/security/','/api/ml/','/api/devops/','/api/extensions/')) else 16384
                if not 0 < length <= limit:
                    raise ValidationError(f'Request must contain 1–{limit} bytes')
                data = decode(read_exact(self.rfile,length))
                if not isinstance(data, dict):
                    raise ValidationError('Expected a JSON object')
                extensions={'/api/extensions/model':capabilities.load_model,'/api/extensions/predict':capabilities.predict,'/api/extensions/experiment-plan':capabilities.experiment_plan}
                if self.path in extensions:
                    self.reply(200,extensions[self.path](data));return
                if self.path == '/api/extensions/stock-plan':
                    self.reply(200,capabilities.stock_plan(db,data));return
                details=re.fullmatch(r'/api/tickets/(\d+)/details',self.path)
                if details:
                    self.reply(200,services.ticket_details(db,int(details[1]),data));return
                devops_routes={'/api/devops/manifest':devops_apps.manifest,'/api/devops/pipeline':devops_apps.pipeline,'/api/devops/reliability':devops_apps.reliability}
                if self.path in devops_routes:
                    self.reply(200,capabilities.enrich(self.path,data,devops_routes[self.path](data)))
                    return
                ml_routes = {'/api/ml/train':ml_apps.train,'/api/ml/search':ml_apps.search,'/api/ml/evaluate':ml_apps.evaluate}
                if self.path in ml_routes:
                    self.reply(200, capabilities.enrich(self.path,data,ml_routes[self.path](data)))
                    return
                security_routes = {'/api/security/logs':security_apps.auth_logs,
                    '/api/security/headers':security_apps.inspect_headers,'/api/security/secrets':security_apps.scan_secrets}
                if self.path in security_routes:
                    self.reply(200, capabilities.enrich(self.path,data,security_routes[self.path](data)))
                    return
                data_routes = {'/api/data/profile':data_apps.profile, '/api/data/clean':data_apps.clean,
                               '/api/data/sales':data_apps.sales}
                if self.path in data_routes:
                    self.reply(200, capabilities.enrich(self.path,data,data_routes[self.path](data)))
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
            except TimeoutError:
                self.reply(408, {'error': 'Request body timed out'})
            except NotFoundError as error:
                self.reply(404, {'error': str(error)})
            except ConflictError as error:
                self.reply(409, {'error': str(error)})
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
