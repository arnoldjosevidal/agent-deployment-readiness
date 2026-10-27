"""SQLite es autoridad: payload/ledger atómicos; trazas y CSV son vistas recuperables.

Una transacción confirmada sobrevive a fallos de exportación. Nunca se reejecuta
una operación para recuperarla. Fuentes/DB dañados causan parada, no reparación muda.
"""
from contextlib import contextmanager,nullcontext
import csv
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from .common import DuplicateRun,IntegrityError,SafetyError,canonical,digest,identifier,scrub,utc
from .events import metrics,validate_events

class EvidenceStore:
    def __init__(self,root,validator=None,metric_deriver=None):
        self.validate=validator or validate_events;self.derive=metric_deriver or metrics
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.db=self.root/'ledger.sqlite3'
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, payload BLOB NOT NULL, sha256 TEXT NOT NULL, created TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS event_journal (run_id TEXT NOT NULL, seq INTEGER NOT NULL, event BLOB NOT NULL, sha256 TEXT NOT NULL, PRIMARY KEY(run_id,seq))')

    def record_event(self,event):
        """Journal durable antes de ejecutar; rechaza cambios a un run sellado."""
        run_id=identifier(event['run_id']);raw=canonical(event)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if db.execute('SELECT 1 FROM runs WHERE run_id=?',(run_id,)).fetchone():raise DuplicateRun(run_id)
                count=db.execute('SELECT count(*) FROM event_journal WHERE run_id=?',(run_id,)).fetchone()[0]
                if event['seq']!=count+1:raise IntegrityError('JOURNAL_SEQUENCE')
                db.execute('INSERT INTO event_journal VALUES (?,?,?,?)',(run_id,event['seq'],raw,digest(raw)));db.commit()
            except BaseException:db.rollback();raise

    def interrupted(self):
        """Reporte de journal sin commit final; jamás reejecutar herramientas."""
        with self.connection() as db:
            rows=db.execute('SELECT run_id,seq,event,sha256 FROM event_journal WHERE run_id NOT IN (SELECT run_id FROM runs) ORDER BY run_id,seq').fetchall()
        report={}
        for rid,seq,raw,sha in rows:
            if digest(raw)!=sha:raise IntegrityError('JOURNAL_CORRUPTION')
            report.setdefault(rid,{'status':'INTERRUPTED_OR_INCOMPLETE','events':[]})['events'].append(json.loads(raw))
        return report

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.db,timeout=20,isolation_level=None)
        db.execute('PRAGMA synchronous=FULL');db.execute('PRAGMA foreign_keys=ON')
        try:yield db
        finally:db.close()

    @staticmethod
    def fault(hook,stage):
        if hook:hook(stage)

    def commit(self,run_id,events,metadata=None,fault=None):
        identifier(run_id)
        # Comprobación previa sin tocar trazas/vistas; se repite bajo lock para carreras.
        with self.connection() as db:
            if db.execute('SELECT 1 FROM runs WHERE run_id=?',(run_id,)).fetchone():raise DuplicateRun(run_id)
        self.validate(events,run_id)
        payload={'schema':'adr.g64r.evidence.v1','classification':metadata['real_accounting']['classification']if metadata and 'real_accounting'in metadata else 'OFFLINE_INFRASTRUCTURE',
                 'run_id':run_id,'events':scrub(events),'metrics':self.derive(events),'metadata':scrub(metadata or {}),
                 'real_external_requests':(metadata or {}).get('real_accounting',{}).get('real_external_requests',0),'real_cost_usd':(metadata or {}).get('real_accounting',{}).get('real_cost_usd','0')}
        self.fault(fault,'before_transaction')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if db.execute('SELECT 1 FROM runs WHERE run_id=?',(run_id,)).fetchone():raise DuplicateRun(run_id)
                journal=db.execute('SELECT event,sha256 FROM event_journal WHERE run_id=? ORDER BY seq',(run_id,)).fetchall()
                if journal and ([json.loads(raw) for raw,_ in journal]!=payload['events'] or any(digest(raw)!=sha for raw,sha in journal)):
                    raise IntegrityError('JOURNAL_PAYLOAD_MISMATCH')
                if metadata and metadata.get('transport_session_id'):
                    sid=metadata['transport_session_id']
                    if db.execute("SELECT 1 FROM attempts WHERE session=? AND status='RESERVED'",(sid,)).fetchone():raise IntegrityError('PENDING_TRANSPORT')
                    budget=db.execute('SELECT config,requests,tokens,cost,elapsed,stopped FROM budgets WHERE session=?',(sid,)).fetchone()
                    if budget is None:raise IntegrityError('UNKNOWN_BUDGET')
                    attempts=db.execute('SELECT attempt_id,status,charged_tokens,cost,elapsed FROM attempts WHERE session=? ORDER BY attempt_id',(sid,)).fetchall()
                    db.execute("UPDATE budgets SET stopped=COALESCE(stopped,'SEALED_BY_EVIDENCE') WHERE session=?",(sid,))
                    budget=db.execute('SELECT config,requests,tokens,cost,elapsed,stopped FROM budgets WHERE session=?',(sid,)).fetchone()
                    payload['transport_ledger_snapshot']={'session':sid,'budget':budget,'attempts':attempts}
                raw=canonical(payload);sha=digest(raw)
                db.execute('INSERT INTO runs VALUES (?,?,?,?)',(run_id,raw,sha,utc()))
                self.fault(fault,'after_insert_before_commit')
                db.commit()
            except BaseException:db.rollback();raise
        self.fault(fault,'after_commit')
        self.recover(fault=fault)
        return sha

    def _publish_trace(self,path,raw,fault):
        if path.exists():
            if path.read_bytes()!=raw:raise IntegrityError('TRACE_MISMATCH: '+path.name)
            return
        stage=self.root/'.staging';stage.mkdir(exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix=path.stem+'-',suffix='.partial',dir=stage)
        try:
            with os.fdopen(fd,'wb') as out:
                out.write(raw[:max(1,len(raw)//2)]);out.flush();os.fsync(out.fileno())
                self.fault(fault,'partial_trace')
                out.write(raw[max(1,len(raw)//2):]);out.flush();os.fsync(out.fileno())
            # NTFS in this Windows environment denies hard-link creation even
            # within one volume. Rename is atomic on the same volume and, on
            # Windows, fails if the destination already exists; this preserves
            # exclusive publication without replacing a prior trace.
            try:
                if os.name=='nt':os.rename(temp,path)
                else:os.link(temp,path)
            except FileExistsError:
                if path.read_bytes()!=raw:raise IntegrityError('TRACE_COLLISION')
        finally:
            # Tras muerte real del proceso queda .partial; no se considera evidencia.
            if Path(temp).exists():Path(temp).unlink()

    def recover(self,fault=None):
        """Reexportación bajo lock DB; restos staging se conservan para análisis."""
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                rows=db.execute('SELECT run_id,payload,sha256 FROM runs ORDER BY run_id').fetchall()
                traces=self.root/'traces';traces.mkdir(exist_ok=True)
                expected=set();csvrows=[]
                for run_id,raw,sha in rows:
                    if digest(raw)!=sha:raise IntegrityError('LEDGER_PAYLOAD_MISMATCH')
                    p=json.loads(raw);self.validate(p['events'],run_id)
                    if self.derive(p['events'])!=p['metrics']:raise IntegrityError('METRIC_MISMATCH')
                    trace=traces/(run_id+'.json');expected.add(trace.name)
                    self._publish_trace(trace,raw,fault)
                    m=p['metrics']
                    csvrows.append({'run_id':run_id,'classification':p['classification'],'requests':m['requests'],
                      'allow':m['decisions']['ALLOW'],'block':m['decisions']['BLOCK'],'require_approval':m['decisions']['REQUIRE_APPROVAL'],
                      'execution_started':m['execution_started'],'tool_successes':m['tool_successes'],'tool_errors':m['tool_errors'],
                      'trace_path':'traces/'+trace.name,'trace_sha256':sha})
                    if 'NOT_APPLICABLE'in m['decisions']:
                        csvrows[-1].update({'not_applicable':m['decisions']['NOT_APPLICABLE'],'model_requests':m['model_requests'],'schema_errors':m['schema_errors'],'outcome_status':m['status'],'utility':m['utility'],'attacker_success':m['attacker_success']})
                        csvrows[-1].update({k:m[k]for k in('evaluation_family_id','evaluation_family_sha256','native_evaluator_id','native_evaluator_sha256','native_utility','native_attacker_success')})
                        csvrows[-1]['collateral_effects_json']=json.dumps(m['collateral_effects'],sort_keys=True,ensure_ascii=False)
                if {p.name for p in traces.glob('*.json')}-expected:raise IntegrityError('ORPHAN_TRACE')
                self.fault(fault,'after_traces_before_csv')
                fields=['run_id','classification','requests','allow','block','require_approval','execution_started','tool_successes','tool_errors','trace_path','trace_sha256']
                if csvrows and 'not_applicable'in csvrows[0]:fields+=['not_applicable','model_requests','schema_errors','outcome_status','utility','attacker_success']
                if csvrows and 'evaluation_family_id'in csvrows[0]:fields+=['evaluation_family_id','evaluation_family_sha256','native_evaluator_id','native_evaluator_sha256','native_utility','native_attacker_success','collateral_effects_json']
                output=io.StringIO(newline='');writer=csv.DictWriter(output,fieldnames=fields);writer.writeheader();writer.writerows(csvrows)
                target=self.root/'runs.csv';rawcsv=output.getvalue().encode('utf-8')
                if not target.exists() or target.read_bytes()!=rawcsv:
                    fd,tmp=tempfile.mkstemp(prefix='view-',suffix='.partial',dir=self.root)
                    try:
                        with os.fdopen(fd,'wb') as out:out.write(rawcsv);out.flush();os.fsync(out.fileno())
                        self.fault(fault,'before_csv_replace')
                        os.replace(tmp,target)
                    finally:
                        if Path(tmp).exists():Path(tmp).unlink()
                result=self.verify(db=db)
                db.commit()
            except BaseException:db.rollback();raise
        return result

    def verify(self,db=None):
        own_connection=db is None
        with self.connection() if own_connection else nullcontext(db) as db:
            if own_connection:db.execute('BEGIN IMMEDIATE')
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise IntegrityError('DATABASE_CORRUPTION')
            rows=db.execute('SELECT run_id,payload,sha256 FROM runs ORDER BY run_id').fetchall()
            for run_id,raw,sha in rows:
                p=json.loads(raw);self.validate(p['events'],run_id)
                if digest(raw)!=sha or self.derive(p['events'])!=p['metrics']:raise IntegrityError('LEDGER_MISMATCH')
                journal=db.execute('SELECT event,sha256 FROM event_journal WHERE run_id=? ORDER BY seq',(run_id,)).fetchall()
                if journal and ([json.loads(e) for e,_ in journal]!=p['events'] or any(digest(e)!=h for e,h in journal)):raise IntegrityError('JOURNAL_PAYLOAD_MISMATCH')
                if 'transport_ledger_snapshot' in p:
                    snap=p['transport_ledger_snapshot'];sid=snap['session']
                    budget=db.execute('SELECT config,requests,tokens,cost,elapsed,stopped FROM budgets WHERE session=?',(sid,)).fetchone()
                    attempts=db.execute('SELECT attempt_id,status,charged_tokens,cost,elapsed FROM attempts WHERE session=? ORDER BY attempt_id',(sid,)).fetchall()
                    if canonical(budget)!=canonical(snap['budget']) or canonical(attempts)!=canonical(snap['attempts']):raise IntegrityError('TRANSPORT_LEDGER_MISMATCH')
                path=self.root/'traces'/(run_id+'.json')
                if not path.exists() or path.read_bytes()!=raw:raise IntegrityError('VIEW_TRACE_MISMATCH')
            csvpath=self.root/'runs.csv'
            if not csvpath.exists():raise IntegrityError('CSV_MISSING')
            with csvpath.open(newline='',encoding='utf-8') as f:view=list(csv.DictReader(f))
            if len(view)!=len(rows):raise IntegrityError('CSV_COUNT_MISMATCH')
            for row,(run_id,raw,sha) in zip(view,rows):
                m=json.loads(raw)['metrics']
                expected={'run_id':run_id,'classification':json.loads(raw)['classification'],'requests':str(m['requests']),
                          'allow':str(m['decisions']['ALLOW']),'block':str(m['decisions']['BLOCK']),
                          'require_approval':str(m['decisions']['REQUIRE_APPROVAL']),
                          'execution_started':str(m['execution_started']),'tool_successes':str(m['tool_successes']),
                          'tool_errors':str(m['tool_errors']),'trace_path':'traces/'+run_id+'.json','trace_sha256':sha}
                if 'NOT_APPLICABLE'in m['decisions']:
                    expected.update({'not_applicable':str(m['decisions']['NOT_APPLICABLE']),'model_requests':str(m['model_requests']),'schema_errors':str(m['schema_errors']),'outcome_status':m['status'],'utility':''if m['utility']is None else str(m['utility']),'attacker_success':''if m['attacker_success']is None else str(m['attacker_success'])})
                    expected.update({k:''if m[k]is None else str(m[k])for k in('evaluation_family_id','evaluation_family_sha256','native_evaluator_id','native_evaluator_sha256','native_utility','native_attacker_success')})
                    expected['collateral_effects_json']=json.dumps(m['collateral_effects'],sort_keys=True,ensure_ascii=False)
                if row!=expected:raise IntegrityError('CSV_CONTENT_MISMATCH')
            if {p.name for p in (self.root/'traces').glob('*.json')}!={r[0]+'.json' for r in rows}:raise IntegrityError('ORPHAN_TRACE')
        return {'runs':len(rows),'database':'ok','traces':'ok','csv':'ok'}
