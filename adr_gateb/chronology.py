"""Journal-backed, immutable evaluator input; never supplied by the model."""
from dataclasses import dataclass
import json,re
from adr_g64r.common import SafetyError,canonical,digest
_ISSUER=object()
@dataclass(frozen=True)
class VerifiedPrefix:
    raw:bytes
    sha256:str
    issuer:object
    def events(self):
        if self.issuer is not _ISSUER or digest(self.raw)!=self.sha256:raise SafetyError('EV_PREFIX_CORRUPT_OR_UNTRUSTED')
        return json.loads(self.raw)

def from_journal(store,events):
    if not events:raise SafetyError('EV_PREFIX_MISSING')
    rid=events[0]['run_id']
    with store.connection()as db:
        rows=db.execute('SELECT seq,event,sha256 FROM event_journal WHERE run_id=? ORDER BY seq',(rid,)).fetchall()
    if not rows or any(seq!=i or digest(raw)!=sha for i,(seq,raw,sha)in enumerate(rows,1)):raise SafetyError('EV_JOURNAL_CORRUPT')
    actual=[json.loads(raw)for _,raw,_ in rows]
    raw=canonical(events)
    if canonical(actual)!=raw:raise SafetyError('EV_PREFIX_JOURNAL_MISMATCH')
    return VerifiedPrefix(raw,digest(raw),_ISSUER)

def receipt(email_id,email_sha256,result_sha256,redacted_result):
    data={'schema':'adr.email.receipt.v2','email_id':email_id,'email_sha256':email_sha256,'result_sha256':result_sha256,'redacted_result_sha256':digest(canonical(redacted_result))}
    return {**data,'binding_sha256':digest(canonical(data))}

def validate_receipt(event):
    r=event.get('result_reference')
    fields={'schema','email_id','email_sha256','result_sha256','redacted_result_sha256','binding_sha256'}
    if type(r)is not dict or set(r)!=fields or r.get('schema')!='adr.email.receipt.v2' or type(r.get('email_id'))is not str or not r['email_id']:raise SafetyError('EV_EMAIL_REFERENCE_MISSING_OR_INVALID')
    if any(type(r[k])is not str or not re.fullmatch('[0-9a-f]{64}',r[k])for k in fields-{'schema','email_id'}):raise SafetyError('EV_EMAIL_REFERENCE_HASH_INVALID')
    data={k:v for k,v in r.items()if k!='binding_sha256'}
    if digest(canonical(data))!=r['binding_sha256']or r['result_sha256']!=event.get('result_sha256')or r['redacted_result_sha256']!=digest(canonical(event.get('result_redacted'))):raise SafetyError('EV_EMAIL_REFERENCE_BINDING_CORRUPT')
    return r
