"""WSGI app: same-origin live API and the existing RECORD interface."""
import argparse
from concurrent.futures import TimeoutError as FutureTimeout
import json
import os
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server, WSGIServer
from .search import OfficialSearch, SourceError

ROOT=Path(__file__).resolve().parents[1]


def create_app(service=None, root=ROOT):
    service=service or OfficialSearch(json.loads((root/'data/official-realtime.json').read_text()),os.environ.get('RECORD_CACHE_PATH','/tmp/record-official-cache.sqlite3'))
    def application(environ,start_response):
        path=environ.get('PATH_INFO','/')
        status='200 OK'
        content_type='application/json; charset=utf-8'
        if environ.get('REQUEST_METHOD')!='GET':
            status='405 Method Not Allowed';body={'status':'method_not_allowed'}
        elif path in {'/api/search','/record/api/search'}:
            params=parse_qs(environ.get('QUERY_STRING',''),keep_blank_values=True)
            try:
                if set(params)-{'q','refresh'} or len(params.get('q',[]))!=1 or params.get('refresh',['0']) not in [['0'],['1']]:
                    raise ValueError('invalid search parameters')
                body=service.search(params['q'][0],refresh=params.get('refresh',['0'])==['1'])
            except ValueError:
                status='400 Bad Request';body={'status':'invalid_query','message':'アーティスト名を入力してください。'}
            except (SourceError,FutureTimeout):
                status='503 Service Unavailable';body={'status':'service_unavailable','message':'検索サービスが混み合っています。再度お試しください。'}
            except Exception:
                status='503 Service Unavailable';body={'status':'service_unavailable','message':'検索サービスを利用できません。再度お試しください。'}
        elif path in {'/','/record/','/index.html'}:
            content_type='text/html; charset=utf-8';body=(root/'index.html').read_text()
        elif path=='/health':
            body={'status':'ok','mode':'official-on-demand','version':1}
        else:
            status='404 Not Found';body={'status':'not_found'}
        payload=(body if isinstance(body,str) else json.dumps(body,ensure_ascii=False)).encode()
        headers=[('Content-Type',content_type),('Content-Length',str(len(payload))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff')]
        # No blanket CORS proxy: use the same origin or a controlled reverse proxy.
        start_response(status,headers)
        return [payload]
    application.service=service
    return application


class ThreadedServer(ThreadingMixIn,WSGIServer):
    daemon_threads=True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    with make_server(args.host,args.port,create_app(),server_class=ThreadedServer) as server:
        server.serve_forever()


if __name__=='__main__':main()
