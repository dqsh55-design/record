"""Real HTTP readiness check; unclear official sources must never be contacted."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from wsgiref.simple_server import make_server
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server.public import create_public_app,PAGES_ORIGIN
from server.app import ThreadedServer


def validate():
    report={'version':'v0.90','checkedAt':datetime.now(timezone.utc).isoformat(),'publicDeployment':False,'liveOfficialRetrieval':False,'reason':'All source permissions pending or prohibited; no official network requests permitted.','catalogSha256':hashlib.sha256((ROOT/'data/official-catalog.json').read_bytes()).hexdigest(),'searches':[]}
    with tempfile.TemporaryDirectory() as directory:
        app=create_public_app(cache_path=str(Path(directory)/'cache.sqlite3'))
        server=make_server('127.0.0.1',0,app,server_class=ThreadedServer);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch('server.search.build_opener') as network:
                for name in ['Willie Nelson','ウィリー・ネルソン','Jimi Hendrix','Miles Davis']:
                    req=Request('http://127.0.0.1:'+str(server.server_port)+'/api/search?'+urlencode({'q':name}),headers={'Origin':PAGES_ORIGIN})
                    with urlopen(req,timeout=10) as response:body=json.load(response)
                    assert body['status']=='policy_restricted' and body['artist']['albums']==[]
                    report['searches'].append({'query':name,'status':body['status'],'works':0})
                network.assert_not_called()
            catalog=json.loads((ROOT/'data/official-catalog.json').read_text());report['registeredWorks']=sum(len(a['albums']) for a in catalog['artists'])
            report['registeredMilesWorks']=len(next(a for a in catalog['artists'] if a['name']=='Miles Davis')['albums'])
            assert report['registeredWorks']==292 and report['registeredMilesWorks']==72
        finally:server.shutdown();server.server_close();thread.join(timeout=2);app.service.cache.close()
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    report=validate();args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
