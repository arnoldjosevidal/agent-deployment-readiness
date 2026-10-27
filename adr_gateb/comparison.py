"""Reuse PREP denominators; explicit frozen G mapping, synthetic only here."""
import json
from decimal import Decimal, InvalidOperation
from adr_g64r.common import SafetyError
from adr_p1.comparison import summarize as inherited
from .design import A,G
def _money(value):
    try:value=Decimal(str(value))
    except (InvalidOperation,TypeError,ValueError):raise SafetyError('RESOURCE_MONEY_INVALID')from None
    if not value.is_finite()or value<0:raise SafetyError('RESOURCE_MONEY_INVALID')
    return value

def _resource_summary(payloads,classification):
    out={}
    for mode,arm in ((A,A),(G,G)):
        runs=[p for p in payloads if p['metadata']['mode']==mode]
        attempted=complete=unknown=input_tokens=output_tokens=token_runs=latency_ms=latency_runs=reserved_tokens=external=0
        reserved_usd=estimated_usd=synthetic_usd=Decimal(0);reserved_known=estimated_known=synthetic_known=True
        estimated_any=False;cost_bases=set()
        scopes=set()
        for p in runs:
            meta=p['metadata'];scope=meta.get('scope');scopes.add(scope)
            events=p['events'];requests={e.get('call_id') for e in events if e['type']=='model_request'}
            if None in requests or len(requests)!=sum(e['type']=='model_request' for e in events):raise SafetyError('RESOURCE_REQUEST_ID')
            attempted+=len(requests);results={}
            for e in events:
                if e['type']=='model_result':
                    rid=e.get('call_id')
                    if rid not in requests or rid in results:raise SafetyError('RESOURCE_RESULT_ID')
                    key='elapsed_ms_synthetic' if classification=='SYNTHETIC' else 'elapsed_ms'
                    value=e.get(key)
                    if type(value)is int and value>=0:latency_ms+=value;latency_runs+=1
                    results[rid]=e
            if classification=='SYNTHETIC':
                rows=meta.get('gateb_attempts')or[]
                if {r[1] for r in rows}!=requests:raise SafetyError('SYNTHETIC_LEDGER_REQUEST_MISMATCH')
                for row in rows:
                    _,rid,status,inp,reserved,charged,cost,_elapsed=row
                    if type(reserved)is int and reserved>=0:reserved_tokens+=reserved
                    if status=='OK'and type(inp)is int and type(charged)is int and charged>=inp:
                        input_tokens+=inp;output_tokens+=charged-inp;token_runs+=1;complete+=1
                    else:unknown+=1
                    if cost is None:synthetic_known=False
                    else:synthetic_usd+=_money(cost)
                close=next((e for e in events if e['type']=='accounting_close'),{})
                external+=close.get('real_external_requests',0)
            else:
                rows=meta.get('nebius_requests')or[];by_id={r[0]:r for r in rows}
                if len(by_id)!=len(rows)or set(by_id)!=requests:raise SafetyError('PROVIDER_LEDGER_REQUEST_MISMATCH')
                for rid,status,reserved,reserved_cost,inp,outp in rows:
                    if type(reserved)is not int or reserved<0:raise SafetyError('PROVIDER_RESERVED_TOKENS_INVALID')
                    reserved_tokens+=reserved;reserved_usd+=_money(reserved_cost)
                    if status=='COMPLETE'and type(inp)is int and type(outp)is int and inp>=0 and outp>=0:
                        input_tokens+=inp;output_tokens+=outp;token_runs+=1;complete+=1
                    else:unknown+=1
                accounting=meta.get('real_accounting')or{}
                if accounting.get('real_external_requests')!=len(rows):raise SafetyError('PROVIDER_REQUEST_COUNT_MISMATCH')
                external+=accounting['real_external_requests']
                if accounting.get('reserved_usd')is None or _money(accounting['reserved_usd'])!=sum((_money(r[3])for r in rows),Decimal(0)):reserved_known=False
                cost=accounting.get('known_cost_usd')
                if cost is None or not accounting.get('cost_basis'):estimated_known=False
                else:estimated_usd+=_money(cost);estimated_any=True
                if accounting.get('cost_basis'):cost_bases.add(accounting['cost_basis'])
                if accounting.get('unknown_requests',0):estimated_known=False
        if len(scopes)>1:raise SafetyError('MIXED_RESOURCE_SCOPES')
        scope=next(iter(scopes))if scopes else'NOT_RUN'
        if attempted!=complete+unknown:raise SafetyError('RESOURCE_REQUEST_ACCOUNTING')
        if classification=='SYNTHETIC'and external!=0:raise SafetyError('SYNTHETIC_EXTERNAL_REQUESTS')
        out[arm]={'classification':classification,'scope':scope,'episodes_in_ledger':len(runs),
          'model_requests_attempted':attempted,'model_requests_complete':complete,'model_requests_unknown':unknown,
          'input_tokens_observed':input_tokens if token_runs else None,'output_tokens_observed':output_tokens if token_runs else None,
          'token_usage_request_denominator':token_runs,'latency_elapsed_ms_observed':latency_ms if latency_runs else None,
          'token_usage_request_unknown':attempted-token_runs,'latency_request_denominator':latency_runs,
          'latency_request_unknown':attempted-latency_runs,'reserved_tokens':reserved_tokens if attempted else None,
          'reserved_usd':str(reserved_usd)if classification!='SYNTHETIC'and attempted and reserved_known else None,
          'estimated_cost_usd':str(estimated_usd)if classification!='SYNTHETIC'and attempted and estimated_known else None,
          'estimated_cost_usd_known_subtotal':str(estimated_usd)if classification!='SYNTHETIC'and estimated_any else None,
          'estimated_cost_basis':'|'.join(sorted(cost_bases))if cost_bases else('NOT_APPLICABLE_SYNTHETIC'if classification=='SYNTHETIC'else'UNKNOWN'),
          'estimated_cost_status':'ESTIMATE_NOT_INVOICE'if classification!='SYNTHETIC'and attempted and estimated_known else('PARTIAL_KNOWN_ESTIMATE'if classification!='SYNTHETIC'and estimated_any else('UNKNOWN'if classification!='SYNTHETIC'and attempted else'NOT_APPLICABLE_SYNTHETIC')),
          'simulated_cost_usd':str(synthetic_usd)if classification=='SYNTHETIC'and attempted and synthetic_known else None,
          'provider_invoice_cost_usd':'NOT_PROVIDED','external_requests':external}
    return out

def summary(design,store=None,channel='candidate'):
    if channel not in('candidate','native'):raise SafetyError('UNKNOWN_METRIC_CHANNEL')
    records=[];bindings=set();payloads=[]
    if store is not None:
        store.verify()
        with store.connection()as db:
            payloads=[json.loads(raw)for(raw,)in db.execute('SELECT payload FROM runs ORDER BY run_id')]
        for p in payloads:
            meta=p['metadata'];m=p['metrics'];row=design.row(meta['planned_episode_id'])
            if meta['scope']!='OFFLINE_SYNTHETIC_FIXTURE_NOT_78_REAL_EPISODES':raise SafetyError('EVIDENCE_CLASS')
            idkey,hashkey=('evaluation_family_id','evaluation_family_sha256')if channel=='candidate'else('native_evaluator_id','native_evaluator_sha256')
            binding=(m[idkey],m[hashkey],m['native_evaluator_id'],m['native_evaluator_sha256'])
            if 'UNBOUND_HISTORICAL'in binding:raise SafetyError('UNBOUND_EVALUATOR')
            bindings.add(binding)
            if len(bindings)>1:raise SafetyError('MIXED_EVALUATOR_VERSIONS')
            utility=m['utility']if channel=='candidate'else m['native_utility'];attacker=m['attacker_success']if channel=='candidate'else m['native_attacker_success']
            if m['status']=='ERROR'and(utility is not None or attacker is not None):raise SafetyError('ERROR_OUTCOMES_NOT_NULL')
            records.append({'arm':A if row['mode']==A else 'WITH_GATE','case_id':row['case_id'],'status':'COMPLETE'if m['status']=='VALID_SYNTHETIC_FIXTURE'else'ERROR','classification':'SYNTHETIC','evidence_sha256':__import__('hashlib').sha256((store.root/'traces'/(p['run_id']+'.json')).read_bytes()).hexdigest(),'utility':utility,'attacker_success':attacker,'email_attempted':m['send_email_attempted'],'email_execution_started':m['send_email_execution_started'],'email_tool_success':m['send_email_tool_success']})
    result=inherited(records,'SYNTHETIC'if store else'REAL_MODEL')
    resources=_resource_summary(payloads,'SYNTHETIC') if payloads else None
    for r in result:
        if r['arm']=='WITH_GATE':r['arm']=G
        r['SR']=1-r['ASR']if r['ASR']is not None else None
        r['false_block']='NOT_MEASURED'
        r['metric_channel']=channel;r['metric_role']='PRIMARY_CANDIDATE_NOT_APPROVED_FOR_REAL'if channel=='candidate'else'NATIVE_DIAGNOSTIC'
        r['evaluator_id'],r['evaluator_sha256']=next(iter(bindings))[:2]if bindings else('NOT_BOUND_NO_EXECUTION','NOT_BOUND_NO_EXECUTION')
        r['resources']=resources.get(r['arm']) if resources else None
    return result
