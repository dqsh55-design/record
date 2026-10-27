"""Prepare a Pages index using an approved API URL; never include a DB secret."""
import argparse
from pathlib import Path
import re
from urllib.parse import urlsplit


def configure(html, base):
    url=urlsplit(base)
    if (url.scheme!='https' or not url.hostname or url.username or url.password or url.port or
        url.query or url.fragment or url.path not in {'','/'} or not re.fullmatch(r'[a-z0-9.-]+',url.hostname)):
        raise ValueError('Use a public HTTPS API origin, without credentials, port, path or query')
    tag='<meta name="record-api-base" content="'+base.rstrip('/')+'/">'
    result,count=re.subn(r'<meta name="record-api-base" content="[^"]*">',lambda _:tag,html)
    if count!=1: raise ValueError('Expected exactly one API meta tag')
    mode='<meta name="record-search-mode" content="api">'
    result,count=re.subn(r'<meta name="record-search-mode" content="[^"]*">',lambda _:mode,result)
    if count!=1: raise ValueError('Expected exactly one explicit search mode tag')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('api_origin')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    args.output.write_text(configure((root/'index.html').read_text(),args.api_origin))
