"""Transporte exclusivamente fixture: ni URL, cliente SDK, callable ni red.

Contabilidad durable por reserva, incluida la pérdida del proceso. Importes
sintéticos Decimal; los contadores reales de llamadas/gasto externo son cero.
"""
from dataclasses import asdict,dataclass
from decimal import Decimal,InvalidOperation
import json
import math
import time
from .common import SafetyError,canonical,digest,identifier,utc

def amount(value):
    try:x=Decimal(str(value))
    except InvalidOperation:raise SafetyError('INVALID_DECIMAL')
    if not x.is_finite() or x<0:raise SafetyError('INVALID_DECIMAL')
    return x

@dataclass(frozen=True)
class Limits:
    max_requests:int=0
    max_tokens:int=0
    max_input_tokens:int=0
    max_output_tokens:int=0
    max_call_ms:int=0
    max_total_ms:int=0
    max_retries:int=0
    max_simulated_usd:str='0'
    simulated_usd_per_token:str='0'

    def checked(self):
        for k,v in asdict(self).items():
            if k not in ('max_simulated_usd','simulated_usd_per_token') and (type(v)is not int or v<0):raise SafetyError('INVALID_LIMIT')
        amount(self.max_simulated_usd);amount(self.simulated_usd_per_token)
        return self

@dataclass(frozen=True)
class FixtureReply:
    output_tokens:int=0
    elapsed_ms:int=0
    outcome:str='OK'

class OfflineTransport:
    def __init__(self,store,session_id,limits):
        self.store=store;self.session=identifier(session_id);self.limits=limits.checked();self.real_start=time.monotonic()
        encoded=canonical(asdict(limits)).decode()
        with store.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS budgets (session TEXT PRIMARY KEY,config TEXT NOT NULL,requests INTEGER NOT NULL,tokens INTEGER NOT NULL,cost TEXT NOT NULL,elapsed INTEGER NOT NULL,stopped TEXT,started_ns INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS attempts (session TEXT NOT NULL,attempt_id TEXT NOT NULL,status TEXT NOT NULL,input_tokens INTEGER NOT NULL,reserved_tokens INTEGER NOT NULL,charged_tokens INTEGER NOT NULL,cost TEXT NOT NULL,elapsed INTEGER NOT NULL,created TEXT NOT NULL,finished TEXT,started_ns INTEGER NOT NULL, PRIMARY KEY(session,attempt_id))')
            db.execute('CREATE TABLE IF NOT EXISTS transport_events (seq INTEGER PRIMARY KEY AUTOINCREMENT,session TEXT NOT NULL,attempt_id TEXT NOT NULL,event TEXT NOT NULL,timestamp TEXT NOT NULL)')
            db.execute('BEGIN IMMEDIATE')
            try:
                old=db.execute('SELECT config FROM budgets WHERE session=?',(self.session,)).fetchone()
                if old and old[0]!=encoded:raise SafetyError('CONFIG_RESET_DENIED')
                if not old:db.execute('INSERT INTO budgets VALUES (?,?,0,0,?,0,NULL,?)',(self.session,encoded,'0',time.monotonic_ns()))
                # Reservas inciertas se cobran completas y detienen la sesión al reabrir.
                pending=db.execute("SELECT attempt_id FROM attempts WHERE session=? AND status='RESERVED'",(self.session,)).fetchall()
                for (aid,) in pending:
                    db.execute("UPDATE attempts SET status='INTERRUPTED',finished=? WHERE session=? AND attempt_id=?",(utc(),self.session,aid))
                    db.execute('INSERT INTO transport_events(session,attempt_id,event,timestamp) VALUES (?,?,?,?)',(self.session,aid,'INTERRUPTED',utc()))
                if pending:db.execute('UPDATE budgets SET stopped=? WHERE session=?',('INTERRUPTED_RESERVATION',self.session))
                db.commit()
            except BaseException:db.rollback();raise

    def snapshot(self):
        with self.store.connection() as db:
            row=db.execute('SELECT requests,tokens,cost,elapsed,stopped FROM budgets WHERE session=?',(self.session,)).fetchone()
            attempts=db.execute('SELECT attempt_id,status,input_tokens,reserved_tokens,charged_tokens,cost,elapsed FROM attempts WHERE session=? ORDER BY created,attempt_id',(self.session,)).fetchall()
            events=db.execute('SELECT seq,attempt_id,event,timestamp FROM transport_events WHERE session=? ORDER BY seq',(self.session,)).fetchall()
        if row[0]!=len(attempts) or row[1]!=sum(x[4] for x in attempts) or amount(row[2])!=sum((amount(x[5]) for x in attempts),Decimal(0)) or row[3]!=sum(x[6] for x in attempts):raise SafetyError('BUDGET_LEDGER_MISMATCH')
        return {'requests':row[0],'charged_tokens':row[1],'simulated_cost_usd':row[2],'elapsed_ms':row[3],'stopped':row[4],
                'attempts':attempts,'events':events,'real_external_requests':0,'real_cost_usd':'0','mode':'OFFLINE_FIXTURE_ONLY'}

    def reserve(self,attempt_id,input_tokens):
        identifier(attempt_id)
        l=self.limits
        if type(input_tokens)is not int or not 0<=input_tokens<=l.max_input_tokens:raise SafetyError('INPUT_LIMIT')
        reserved=input_tokens+l.max_output_tokens;cost=Decimal(reserved)*amount(l.simulated_usd_per_token)
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if db.execute('SELECT 1 FROM attempts WHERE session=? AND attempt_id=?',(self.session,attempt_id)).fetchone():raise SafetyError('DUPLICATE_ATTEMPT')
                requests,tokens,used,elapsed,stopped,started_ns=db.execute('SELECT requests,tokens,cost,elapsed,stopped,started_ns FROM budgets WHERE session=?',(self.session,)).fetchone()
                wall=(time.monotonic_ns()-started_ns)//1_000_000
                reason=stopped
                if not reason and db.execute("SELECT 1 FROM attempts WHERE session=? AND status='RESERVED'",(self.session,)).fetchone():reason='IN_FLIGHT_REQUEST'
                if not reason and (wall<0 or requests+1>l.max_requests or tokens+reserved>l.max_tokens or amount(used)+cost>amount(l.max_simulated_usd) or max(elapsed,wall)>=l.max_total_ms or l.max_call_ms==0):reason='HARD_CAP_STOP'
                if reason:
                    db.execute('UPDATE budgets SET stopped=? WHERE session=?',(reason,self.session));db.commit();raise SafetyError(reason)
                db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,NULL,?)',(self.session,attempt_id,'RESERVED',input_tokens,reserved,reserved,str(cost),0,utc(),time.monotonic_ns()))
                db.execute('UPDATE budgets SET requests=requests+1,tokens=tokens+?,cost=? WHERE session=?',(reserved,str(amount(used)+cost),self.session))
                db.execute('INSERT INTO transport_events(session,attempt_id,event,timestamp) VALUES (?,?,?,?)',(self.session,attempt_id,'RESERVED',utc()))
                db.commit()
            except BaseException:
                if db.in_transaction:db.rollback()
                raise

    def settle(self,attempt_id,reply):
        if not isinstance(reply,FixtureReply) or type(reply.output_tokens)is not int or type(reply.elapsed_ms)is not int or reply.output_tokens<0 or reply.elapsed_ms<0 or reply.outcome not in ('OK','RETRYABLE_ERROR','FATAL_ERROR'):
            raise SafetyError('INVALID_FIXTURE')
        l=self.limits
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row=db.execute('SELECT status,input_tokens,reserved_tokens,cost,started_ns FROM attempts WHERE session=? AND attempt_id=?',(self.session,attempt_id)).fetchone()
                if row is None or row[0]!='RESERVED':raise SafetyError('INVALID_ATTEMPT_STATE')
                _,inp,reserved,reserved_cost,started_ns=row
                b=db.execute('SELECT requests,tokens,cost,elapsed,stopped,started_ns FROM budgets WHERE session=?',(self.session,)).fetchone()
                elapsed_ms=max(reply.elapsed_ms,(time.monotonic_ns()-started_ns)//1_000_000)
                status=reply.outcome;stop=b[4]
                if reply.output_tokens>l.max_output_tokens:status='OUTPUT_OVERRUN';stop=status
                elif elapsed_ms<0 or elapsed_ms>l.max_call_ms or max(b[3]+elapsed_ms,(time.monotonic_ns()-b[5])//1_000_000)>l.max_total_ms:status='TIMEOUT';stop=status
                elif reply.outcome=='FATAL_ERROR':stop='FATAL_ERROR'
                # Sin usage fiable en error/timeout se conserva reserva completa.
                charged=inp+reply.output_tokens if status in ('OK','OUTPUT_OVERRUN') else reserved
                cost=Decimal(charged)*amount(l.simulated_usd_per_token)
                total=amount(b[2])-amount(reserved_cost)+cost
                if b[1]-reserved+charged>l.max_tokens or total>amount(l.max_simulated_usd):stop='USAGE_OVERRUN'
                db.execute('UPDATE attempts SET status=?,charged_tokens=?,cost=?,elapsed=?,finished=? WHERE session=? AND attempt_id=?',
                           (status,charged,str(cost),elapsed_ms,utc(),self.session,attempt_id))
                db.execute('UPDATE budgets SET tokens=tokens-?+?,cost=?,elapsed=elapsed+?,stopped=? WHERE session=?',
                           (reserved,charged,str(total),elapsed_ms,stop,self.session))
                db.execute('INSERT INTO transport_events(session,attempt_id,event,timestamp) VALUES (?,?,?,?)',(self.session,attempt_id,status,utc()))
                db.commit()
            except BaseException:db.rollback();raise
        if stop:raise SafetyError(stop)
        return status

    def request(self,request_id,input_tokens,replies,fault=None):
        identifier(request_id)
        if type(replies) not in (list,tuple) or not replies:raise SafetyError('FIXTURE_ONLY')
        # No se acepta un callable/URL/cliente; ningún código de proveedor se invoca.
        for reply in replies:
            if not isinstance(reply,FixtureReply):raise SafetyError('FIXTURE_ONLY')
            if type(reply.output_tokens)is not int or type(reply.elapsed_ms)is not int or reply.output_tokens<0 or reply.elapsed_ms<0 or reply.outcome not in ('OK','RETRYABLE_ERROR','FATAL_ERROR'):raise SafetyError('INVALID_FIXTURE')
        for retry in range(self.limits.max_retries+1):
            if retry>=len(replies):break
            aid=f'{request_id}-a{retry+1}'
            self.reserve(aid,input_tokens)
            if fault:fault('after_reservation')
            status=self.settle(aid,replies[retry])
            if status=='OK':return self.snapshot()
            if status!='RETRYABLE_ERROR':raise SafetyError(status)
        with self.store.connection() as db:db.execute('UPDATE budgets SET stopped=? WHERE session=?',('RETRY_LIMIT',self.session))
        raise SafetyError('RETRY_LIMIT')

    def external_request(self,*args,**kwargs):raise SafetyError('EXTERNAL_CALLS_DISABLED_ZERO_BUDGET')
