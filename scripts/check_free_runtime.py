"""Start the exact Gunicorn factory on loopback, never on a public host."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request,urlopen
from urllib.error import URLError,HTTPError
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    base='http://127.0.0.1:'+str(port)
    env=dict(os.environ,RECORD_CACHE_PATH=str(Path(directory)/'cache.sqlite3'))
    process=subprocess.Popen([sys.executable,'-m','gunicorn','server.public:create_public_app()','--bind','127.0.0.1:'+str(port),'--workers','1','--threads','4','--timeout','75','--max-requests','0'],cwd=ROOT,env=env)
    try:
        for attempt in range(100):
            try:
                with urlopen(base+'/health',timeout=1) as r:assert json.load(r)['status']=='ok'
                break
            except URLError:
                if process.poll() is not None:raise RuntimeError('Gunicorn exited before health check')
                time.sleep(.1)
        else:raise RuntimeError('Gunicorn startup timed out')
        request=Request(base+'/api/search?q=Willie+Nelson',headers={'Origin':'https://dqsh55-design.github.io'})
        with urlopen(request,timeout=5) as r:
            assert r.headers['Access-Control-Allow-Origin']=='https://dqsh55-design.github.io'
            body=json.load(r);assert body['status']=='policy_restricted' and not body['artist']['albums']
        try:urlopen(base+'/api/search?q=Willie+Nelson',timeout=5)
        except HTTPError as error:assert error.code==403
        else:raise AssertionError('Originless request should fail')
        print('Gunicorn loopback smoke passed: health, exact CORS, permission stop, no-origin refusal. No deployment.')
    finally:process.terminate();process.wait(timeout=10)
