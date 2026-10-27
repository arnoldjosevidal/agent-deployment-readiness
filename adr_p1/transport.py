"""Bounded Nebius boundary. SQLite authority; unknown usage retains reservation.

The operator supplies a separately reviewed authorization artifact. This is an
application gate, not a cryptographic identity/OS sandbox or provider billing cap.
"""
from dataclasses import dataclass,asdict
from decimal import Decimal,InvalidOperation
import hashlib,json,os,sqlite3,subprocess,sys,time
from pathlib import Path
from datetime import datetime,timezone
from adr_g64r.common import SafetyError,canonical,identifier,utc

HOST='api.tokenfactory.nebius.com'
MODEL='nvidia/Nemotron-3_5-Lightning'
def hashed(obj):return hashlib.sha256(canonical(obj)).hexdigest()
@dataclass(frozen=True)
class Limits:
    model:str=MODEL
    max_requests:int=0
    max_total_tokens:int=0
    max_input_tokens:int=0
    max_output_tokens:int=0
    max_call_ms:int=0
    max_total_ms:int=0
    max_retries:int=0
    budget_usd:str='0'
    reservation_usd_per_token:str='0'
    def validate(self):
        for k,v in asdict(self).items():
            if k.startswith('max_') and (type(v)is not int or v<0):raise SafetyError('INVALID_LIMIT')
        if self.model!=MODEL or self.max_retries!=0:raise SafetyError('MODEL_OR_RETRY_NOT_APPROVED')
        for v in (self.budget_usd,self.reservation_usd_per_token):
            try:d=Decimal(v)
            except (InvalidOperation,TypeError):raise SafetyError('INVALID_MONEY')
            if not d.is_finite() or d<0:raise SafetyError('INVALID_MONEY')
        if self.max_output_tokens>16384 or self.max_call_ms>300000 or self.max_total_ms>86400000:raise SafetyError('UNSAFE_LIMIT')
        return self

def _wire(payload,key,timeout_ms):
    """Dedicated child bounds DNS, TLS and response duration as one deadline.

    A local HTTP endpoint is accepted only in test mode; the worker separately
    enforces literal loopback and never allows this option for live grants.
    """
    worker=Path(__file__).resolve().parent.parent/'wire_worker.py'
    test_endpoint=os.environ.get('ADR_TEST_HTTP_ENDPOINT') if os.environ.get('ADR_TEST_OUTPUT') else None
    packet={'mode':'LOCAL_TEST_HTTP' if test_endpoint else 'LIVE_AUTHORIZED','payload':payload,'key':key,'timeout_ms':timeout_ms}
    if test_endpoint:packet['endpoint']=test_endpoint
    proc=subprocess.Popen([sys.executable,'-I','-B',str(worker)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        out,err=proc.communicate(json.dumps(packet).encode(),timeout=timeout_ms/1000)
    except subprocess.TimeoutExpired:
        proc.kill();proc.communicate();raise SafetyError('HARD_DEADLINE')
    if proc.returncode:
        audit=None
        try:
            failure=json.loads(err.decode('utf-8','replace')).get('wire_error',{})
            stage=failure.get('stage','unknown');kind=failure.get('type','unknown');audit=failure.get('audit')
            if not all(isinstance(v,str) and v.replace('_','').isalnum() and len(v)<=48 for v in (stage,kind)):
                stage,kind='unknown','unknown'
            if audit is not None and (not isinstance(audit,str) or len(audit)>120 or not all(c.isalnum() or c in "_:.-" for c in audit)):
                audit=None
        except (AttributeError,ValueError,UnicodeError):stage,kind,audit='unknown','unknown',None
        raise SafetyError(f'PROVIDER_WORKER_FAILURE:{stage}:{kind}'+(f':{audit}' if audit else ''))from None
    if len(out)>2_000_000:raise SafetyError('PROVIDER_RESPONSE_TOO_LARGE')
    try:return json.loads(out)
    except (ValueError,UnicodeError):raise SafetyError('MALFORMED_PROVIDER_RESPONSE')

class Transport:
    def __init__(self,store,session,limits=None):
        from adr_g64r.storage import EvidenceStore
        if not isinstance(store,EvidenceStore):raise SafetyError('DURABLE_SINK_REQUIRED')
        self.store=store;self.session=identifier(session);self.limits=(limits or Limits()).validate()
        self.config_hash=hashed(asdict(self.limits))
        with store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS p1_sessions (id TEXT PRIMARY KEY, config_hash TEXT NOT NULL, start_ns INTEGER NOT NULL, stopped TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS p1_requests (session TEXT, id TEXT, payload_hash TEXT, status TEXT, reserved_tokens INTEGER, reserved_usd TEXT, input_tokens INTEGER, output_tokens INTEGER, response_hash TEXT, created TEXT, PRIMARY KEY(session,id))')
            db.execute('CREATE TABLE IF NOT EXISTS p1_events (session TEXT,id TEXT,seq INTEGER,event BLOB,sha TEXT,PRIMARY KEY(session,id,seq))')
            row=db.execute('SELECT config_hash FROM p1_sessions WHERE id=?',(self.session,)).fetchone()
            if row and row[0]!=self.config_hash:raise SafetyError('CONFIG_DRIFT')
            db.execute('INSERT OR IGNORE INTO p1_sessions VALUES (?,?,?,NULL)',(self.session,self.config_hash,time.monotonic_ns()))
            if db.execute("SELECT 1 FROM p1_requests WHERE session=? AND status='STARTED'",(self.session,)).fetchone():
                db.execute("UPDATE p1_requests SET status='INTERRUPTED_UNKNOWN' WHERE session=? AND status='STARTED'",(self.session,))
                db.execute("UPDATE p1_sessions SET stopped='INTERRUPTED_UNKNOWN' WHERE id=?",(self.session,))
            db.commit()
    def _event(self,db,rid,kind,**values):
        seq=db.execute('SELECT count(*) FROM p1_events WHERE session=? AND id=?',(self.session,rid)).fetchone()[0]+1
        raw=canonical({'session_id':self.session,'request_id':rid,'seq':seq,'event':kind,'timestamp_utc':utc(),**values})
        db.execute('INSERT INTO p1_events VALUES (?,?,?,?,?)',(self.session,rid,seq,raw,hashlib.sha256(raw).hexdigest()))
    def snapshot(self):
        with self.store.connection() as db:
            rows=db.execute('SELECT id,status,reserved_tokens,reserved_usd,input_tokens,output_tokens FROM p1_requests WHERE session=? ORDER BY created,id',(self.session,)).fetchall()
            stopped=db.execute('SELECT stopped FROM p1_sessions WHERE id=?',(self.session,)).fetchone()[0]
            for raw,sha in db.execute('SELECT event,sha FROM p1_events WHERE session=?',(self.session,)):
                if hashlib.sha256(raw).hexdigest()!=sha:raise SafetyError('REQUEST_EVENT_INTEGRITY')
        return {'session_id':self.session,'config_hash':self.config_hash,'stopped':stopped,'requests':[dict(zip(('id','status','reserved_tokens','reserved_usd','input_tokens','output_tokens'),r)) for r in rows],
                'classification':'REAL_TRANSPORT_ACCOUNTING_NOT_SYNTHETIC_PRICE_MEASUREMENT','reserved_usd':str(sum((Decimal(r[3]) for r in rows),Decimal(0)))}
    def request(self,rid,messages,*,tools=None,authorization=None,token_certificate=None,deadline_ms=None,before_wire=None):
        identifier(rid);lim=self.limits
        # No credentials, network or reservation before explicit approved gates.
        if not authorization or authorization.get('human_approved')is not True:raise SafetyError('EXPLICIT_AUTHORIZATION_REQUIRED')
        if authorization.get('scope')!='ADR_S1_MVP' or authorization.get('config_hash')!=self.config_hash or authorization.get('session_id')!=self.session:raise SafetyError('AUTHORIZATION_SCOPE')
        try:expires=datetime.fromisoformat(authorization['expires_utc']);valid=expires.tzinfo is not None and expires>datetime.now(timezone.utc)
        except (KeyError,TypeError,ValueError):valid=False
        if not valid or not authorization.get('approval_reference'):raise SafetyError('AUTHORIZATION_EXPIRED_OR_UNREFERENCED')
        if min(lim.max_requests,lim.max_total_tokens,lim.max_input_tokens,lim.max_output_tokens,lim.max_call_ms,lim.max_total_ms)<=0 or Decimal(lim.budget_usd)<=0 or Decimal(lim.reservation_usd_per_token)<=0:raise SafetyError('ZERO_AUTHORIZED_BUDGET')
        payload={'model':lim.model,'messages':messages,'max_tokens':lim.max_output_tokens,'temperature':0.0,'stream':False,'store':False}
        if tools:payload.update(tools=tools,tool_choice='auto')
        raw=canonical(payload)
        if len(raw)>1_000_000 or not isinstance(messages,list) or not messages:raise SafetyError('INVALID_REQUEST')
        cert=token_certificate or {}
        if cert.get('payload_sha256')!=hashed(payload) or cert.get('model')!=lim.model or not cert.get('tokenizer_revision') or cert.get('verified')is not True or type(cert.get('upper_bound'))is not int or not 0<cert['upper_bound']<=lim.max_input_tokens:raise SafetyError('VERIFIED_INPUT_TOKEN_BOUND_REQUIRED')
        reserve=cert['upper_bound']+lim.max_output_tokens;cost=Decimal(reserve)*Decimal(lim.reservation_usd_per_token)
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM p1_requests WHERE session=? AND id=?',(self.session,rid)).fetchone():raise SafetyError('DUPLICATE_REQUEST')
            start,stop=db.execute('SELECT start_ns,stopped FROM p1_sessions WHERE id=?',(self.session,)).fetchone()
            elapsed=(time.monotonic_ns()-start)/1_000_000
            rows=db.execute('SELECT reserved_tokens,reserved_usd FROM p1_requests WHERE session=?',(self.session,)).fetchall()
            reason=stop or ('TOTAL_TIME_LIMIT' if elapsed<0 or elapsed>=lim.max_total_ms else None)
            if len(rows)>=lim.max_requests:reason=reason or 'REQUEST_LIMIT'
            if sum(r[0] for r in rows)+reserve>lim.max_total_tokens:reason=reason or 'TOKEN_LIMIT'
            if sum((Decimal(r[1]) for r in rows),Decimal(0))+cost>Decimal(lim.budget_usd):reason=reason or 'BUDGET_LIMIT'
            if reason:
                db.execute('UPDATE p1_sessions SET stopped=? WHERE id=?',(reason,self.session));db.commit();raise SafetyError(reason)
            timeout_ms=min(lim.max_call_ms,int(lim.max_total_ms-elapsed),deadline_ms if type(deadline_ms)is int else lim.max_call_ms)
            if timeout_ms<=0:raise SafetyError('TOTAL_TIME_LIMIT')
            db.execute('INSERT INTO p1_requests VALUES (?,?,?,?,?,?,NULL,NULL,NULL,?)',(self.session,rid,hashed(payload),'STARTED',reserve,str(cost),utc()))
            self._event(db,rid,'request',payload_sha256=hashed(payload))
            self._event(db,rid,'authorization',approval_reference=authorization['approval_reference'],config_hash=self.config_hash)
            self._event(db,rid,'execution_start',timeout_ms=timeout_ms,reserved_tokens=reserve,reserved_usd=str(cost));db.commit()
        try:
            if before_wire:before_wire()
            key=os.environ.get('NEBIUS_API_KEY')
            if not key:raise SafetyError('CREDENTIAL_UNAVAILABLE')
            response=_wire(payload,key,timeout_ms)
            u=response.get('usage',{});it=u.get('prompt_tokens');ot=u.get('completion_tokens')
            if response.get('model')!=lim.model or type(u.get('total_tokens'))is not int or u['total_tokens']!=it+ot:raise SafetyError('MODEL_OR_USAGE_DRIFT')
            if type(it)is not int or type(ot)is not int or it<0 or ot<0 or it>cert['upper_bound'] or ot>lim.max_output_tokens:raise SafetyError('USAGE_MISSING_OR_BOUND_EXCEEDED')
            choices=response.get('choices')
            if not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0].get('message'),dict) or choices[0]['message'].get('role')!='assistant':raise SafetyError('INVALID_COMPLETION')
            with self.store.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute("UPDATE p1_requests SET status='COMPLETE',input_tokens=?,output_tokens=?,response_hash=? WHERE session=? AND id=?",(it,ot,hashed(response),self.session,rid))
                self._event(db,rid,'result',response_sha256=hashed(response),input_tokens=it,output_tokens=ot);db.commit()
            return response
        except BaseException as exc:
            # Never log provider exceptions/messages, credentials or raw prompts.
            with self.store.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute("UPDATE p1_requests SET status='ERROR_UNKNOWN_USAGE' WHERE session=? AND id=?",(self.session,rid))
                db.execute("UPDATE p1_sessions SET stopped='REQUEST_ERROR' WHERE id=?",(self.session,))
                self._event(db,rid,'error',error_type=type(exc).__name__,usage='UNKNOWN_RESERVATION_RETAINED');db.commit()
            raise SafetyError('REQUEST_FAILED_STOPPED') from None
