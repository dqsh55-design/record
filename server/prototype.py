"""Local-only hybrid prototype; never deploys or registers an external service."""
import argparse
import json
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.simple_server import make_server, WSGIServer
from .app import create_app
from .search import OfficialSearch

ROOT=Path(__file__).resolve().parents[1]

def prototype_app(service=None):
    # Explicitly ephemeral by default: no production persistence or secrets implied.
    service=service or OfficialSearch(json.loads((ROOT/'data/official-realtime.json').read_text()),':memory:')
    base=create_app(service,allowed_origins=['https://dqsh55-design.github.io'])
    html=(ROOT/'index.html').read_text().replace('name="record-search-mode" content="catalog"','name="record-search-mode" content="hybrid"')
    html=html.replace('日本語・英語で検索できます。公式確認済みの公開目次から探します。','日本語・英語で検索できます。未登録のアーティストは公式発売情報を確認します。')
    def app(environ,start_response):
        if environ.get('REQUEST_METHOD')=='GET' and environ.get('PATH_INFO')=='/':
            payload=html.encode();start_response('200 OK',[('Content-Type','text/html; charset=utf-8'),('Cache-Control','no-store'),('Content-Length',str(len(payload)))]);return [payload]
        if environ.get('REQUEST_METHOD')=='GET' and environ.get('PATH_INFO')=='/data/official-catalog.json':
            payload=(ROOT/'data/official-catalog.json').read_bytes();start_response('200 OK',[('Content-Type','application/json'),('Content-Length',str(len(payload)))]);return [payload]
        return base(environ,start_response)
    app.service=service
    return app

class LocalServer(ThreadingMixIn,WSGIServer):
    daemon_threads=True

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8001);args=parser.parse_args()
    app=prototype_app()
    try:
        with make_server('127.0.0.1',args.port,app,server_class=LocalServer) as server:
            print(f'Local prototype: http://127.0.0.1:{server.server_port}/ (not a public deployment)',flush=True);server.serve_forever()
    finally:app.service.cache.close()
