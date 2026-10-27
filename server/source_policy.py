"""Deny by default. robots permission alone never authorizes public collection."""
from datetime import datetime
import json
from pathlib import Path
import time
from urllib.parse import urlsplit

POLICY_PATH=Path(__file__).resolve().parents[1]/'data/official-access-policy.json'

class SourcePolicy:
    def __init__(self, document, clock=time.time):
        if document.get('version')!=1 or not isinstance(document.get('hosts'),dict):
            raise ValueError('Invalid source access policy')
        self.document,self.clock=document,clock

    @classmethod
    def load(cls,clock=time.time):
        return cls(json.loads(POLICY_PATH.read_text()),clock)

    def permits(self,host):
        entry=self.document['hosts'].get(host,{})
        try:
            evidence=urlsplit(entry['permissionEvidenceUrl'])
            reviewed_date=datetime.fromisoformat(entry['reviewedAt'].replace('Z','+00:00'))
            expiry_date=datetime.fromisoformat(entry['validUntil'].replace('Z','+00:00'))
            if reviewed_date.tzinfo is None or expiry_date.tzinfo is None:return False
            reviewed,expires=reviewed_date.timestamp(),expiry_date.timestamp()
            return (entry.get('status')=='approved' and entry.get('scope')=='public-automated-release-metadata'
                    and evidence.scheme=='https' and bool(evidence.hostname) and not evidence.username and not evidence.password
                    and reviewed<=self.clock()<expires and expires-reviewed<=90*86400)
        except (KeyError,TypeError,ValueError,AttributeError):
            return False
