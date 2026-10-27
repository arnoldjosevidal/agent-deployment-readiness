"""Read-only, provenance-checked normalization for real exploratory pair evidence.
Never edits source ledgers/traces and never feeds pilot denominators.
"""
import csv, hashlib, json, sqlite3
from pathlib import Path
REAL='REAL_EXPLORATORY_B1_DEVIATION_NOT_PILOT'; REAL_OUT='REAL_EXPLORATORY_NOT_PILOT'; SYNTHETIC='SYNTHETIC_FIXTURE'
MODES={'A_NO_GATE':'A_NO_GATE','G_CALENDAR_READONLY_V1':'WITH_GATE'}
EXPECTED_CASES={'MVP1_G_03','MVP1_A_03'}
class EvidenceError(ValueError): pass
def sha(data): return hashlib.sha256(data).hexdigest()
def evidence_class(payload):
    meta=payload.get('metadata') or {}; acct=meta.get('real_accounting') or {}
    real_markers=(payload.get('classification')==REAL or meta.get('scope')==REAL or acct.get('classification')==REAL)
    if real_markers:
        valid=(payload.get('classification')==REAL and meta.get('scope')==REAL and acct.get('classification')==REAL
          and acct.get('synthetic_usage') is False and type(acct.get('real_external_requests')) is int
          and acct['real_external_requests']>0 and acct.get('mock_requests')==0)
        if valid: return REAL_OUT
        raise EvidenceError('UNCLASSIFIED_OR_CONFLICTING_PROVENANCE')
    if (payload.get('classification') in ('OFFLINE_SYNTHETIC_FIXTURE_NOT_REAL_EPISODE','OFFLINE_MOCK_TRANSPORT_NOT_REAL_EPISODE','SYNTHETIC_LOCAL_WALKTHROUGH_NOT_MODEL_EXPERIMENT')
        or meta.get('scope')=='OFFLINE_SYNTHETIC_FIXTURE_NOT_78_REAL_EPISODES'
        or (acct.get('synthetic_usage') is True and acct.get('real_external_requests')==0)): return SYNTHETIC
    raise EvidenceError('UNCLASSIFIED_OR_CONFLICTING_PROVENANCE')

def normalize(ledger,out):
    ledger=Path(ledger).resolve(); out=Path(out).resolve(); base=ledger.parent; csv_path=base/'runs.csv'; traces=base/'traces'
    if not ledger.is_file() or not csv_path.is_file() or not traces.is_dir(): raise EvidenceError('SOURCE_SET_INCOMPLETE')
    with csv_path.open(encoding='utf-8-sig',newline='') as f: rows={r['run_id']:r for r in csv.DictReader(f)}
    trace_paths=[base/r['trace_path'] for r in rows.values()]
    original_paths=[ledger,csv_path,*trace_paths]
    original_hashes={str(p):sha(p.read_bytes()) for p in original_paths}
    db=sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True)
    normalized=[]
    try:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise EvidenceError('SQLITE_INTEGRITY')
        runs=db.execute('SELECT run_id,payload,sha256 FROM runs ORDER BY run_id').fetchall()
        if set(rows) != {r[0] for r in runs}: raise EvidenceError('CSV_RUN_SET_MISMATCH')
        reservations=dict(db.execute('SELECT run_id,status FROM gateb_reservations'))
        for run_id,raw,stored_sha in runs:
            if sha(raw)!=stored_sha: raise EvidenceError('RUN_PAYLOAD_HASH_MISMATCH')
            payload=json.loads(raw); meta=payload['metadata']
            if evidence_class(payload)!=REAL_OUT: raise EvidenceError('SYNTHETIC_EVIDENCE_NOT_IN_REAL_PAIR_EXPORT')
            if meta.get('planned_episode_id') not in EXPECTED_CASES or meta.get('mode') not in MODES: raise EvidenceError('UNEXPECTED_EXPLORATORY_CASE')
            if meta.get('error') is not None: raise EvidenceError('RUN_ERROR_NOT_COMPARABLE')
            evs=[ev for ev in payload['events'] if ev.get('type')=='evaluation_result']
            if len(evs)!=1 or any(ev.get('type')=='evaluation_error' for ev in payload['events']): raise EvidenceError('EVALUATION_NOT_FINAL')
            ev=evs[0]
            if type(ev.get('utility')) is not bool or type(ev.get('attacker_success')) is not bool: raise EvidenceError('OUTCOME_NOT_BOOLEAN')
            reqs=meta.get('nebius_requests') or []; acct=meta['real_accounting']
            if not reqs or any(r[1]!='COMPLETE' for r in reqs) or len(reqs)!=acct.get('real_external_requests') or acct.get('unknown_requests')!=0: raise EvidenceError('REQUEST_ACCOUNTING_INCOMPLETE')
            actual=db.execute('SELECT id,status,reserved_tokens,reserved_usd,input_tokens,output_tokens FROM p1_requests WHERE session=? AND substr(id,1,?)=? ORDER BY id',(meta['nebius_session'],len(run_id+'-m'),run_id+'-m')).fetchall()
            expected=sorted([tuple(r) for r in reqs],key=lambda r:r[0])
            if actual!=expected: raise EvidenceError('REQUEST_LEDGER_MISMATCH')
            for raw_event,event_sha in db.execute('SELECT event,sha FROM p1_events WHERE session=? AND substr(id,1,?)=?',(meta['nebius_session'],len(run_id+'-m'),run_id+'-m')):
                if sha(raw_event)!=event_sha: raise EvidenceError('REQUEST_EVENT_HASH_MISMATCH')
            for raw_event,event_sha in db.execute('SELECT event,sha256 FROM event_journal WHERE run_id=? ORDER BY seq',(run_id,)):
                if sha(raw_event)!=event_sha: raise EvidenceError('EVENT_JOURNAL_HASH_MISMATCH')
            csvrow=rows.get(run_id)
            if not csvrow or csvrow.get('classification')!=payload.get('classification'): raise EvidenceError('CSV_RUN_IDENTITY_MISMATCH')
            trace_path=base/csvrow['trace_path']; trace_raw=trace_path.read_bytes(); trace_sha=sha(trace_raw)
            if trace_sha!=csvrow['trace_sha256'] or json.loads(trace_raw)!=payload: raise EvidenceError('TRACE_PAYLOAD_HASH_MISMATCH')
            if csvrow.get('outcome_status')!=payload['metrics'].get('status') or csvrow.get('utility')!=str(ev['utility']) or csvrow.get('attacker_success')!=str(ev['attacker_success']): raise EvidenceError('CSV_METRICS_LINEAGE_MISMATCH')
            normalized.append({'run_id':run_id,'pair_id':'MVP1_PAIR_03','case_id':meta['planned_episode_id'],'arm':MODES[meta['mode']],
              'source_classification':payload['classification'],'normalized_classification':REAL_OUT,'source_reservation_status':reservations.get(run_id),
              'source_metrics_status':payload['metrics'].get('status'),'normalized_status':'COMPLETE',
              'normalization_basis':'verified non-synthetic accounting, real-exploratory provenance and one final evaluator event; legacy status field ignored',
              'utility':ev['utility'],'attacker_success':ev['attacker_success'],'requests':len(reqs),'request_errors':0,
              'trace_sha256':trace_sha,'run_payload_sha256':stored_sha,'evaluation_family_id':ev.get('evaluation_family_id'),
              'evaluation_family_sha256':ev.get('evaluation_family_sha256')})
        if {r['case_id'] for r in normalized}!=EXPECTED_CASES or {r['arm'] for r in normalized}!={'A_NO_GATE','WITH_GATE'} or len(normalized)!=2: raise EvidenceError('PAIR_INCOMPLETE_OR_DUPLICATE')
    finally: db.close()
    if any(sha(Path(p).read_bytes())!=h for p,h in original_hashes.items()): raise EvidenceError('SOURCE_MUTATION_DETECTED')
    result={'schema':'adr.exploratory-normalization.v1','scope':'PAIR_03_REFERENCE_RECONCILIATION_NOT_PILOT',
      'source_files_sha256':original_hashes,'source_integrity':'READ_ONLY_HASHES_AND_LEDGER_EXPORT_LINKS_VERIFIED',
      'records':sorted(normalized,key=lambda r:(r['arm']!='A_NO_GATE',r['case_id'])),
      'comparison':{'arms':['A_NO_GATE','WITH_GATE'],'valid_n_per_arm':1,
        'utility':{r['arm']:r['utility'] for r in normalized},'attacker_success':{r['arm']:r['attacker_success'] for r in normalized},
        'interpretation':'One exploratory matched pair only; no general efficacy claim.'}}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    if any(sha(Path(p).read_bytes())!=h for p,h in original_hashes.items()): raise EvidenceError('SOURCE_MUTATION_DETECTED')
    return result
