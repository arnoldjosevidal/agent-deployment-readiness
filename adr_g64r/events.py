"""Instrumentación de un runtime local. No importa AgentDojo ni carga tareas."""
from ast import literal_eval
import json
from .common import SafetyError,canonical,digest,identifier,scrub,utc

DECISIONS={'ALLOW','BLOCK','REQUIRE_APPROVAL'}

def validate_events(events,run_id):
    states={};seen=set()
    for seq,e in enumerate(events,1):
        if e.get('seq')!=seq or e.get('run_id')!=run_id or e.get('event_id')!=f'{run_id}-e{seq}' or e.get('event_id') in seen:raise SafetyError('INVALID_EVENT_IDENTITY')
        seen.add(e['event_id'])
        from datetime import datetime
        if datetime.fromisoformat(e['timestamp']).utcoffset() is None:raise SafetyError('NAIVE_TIMESTAMP')
        cid=e['call_id'];s=states.get(cid);kind=e['type']
        if kind=='request':
            if s is not None or e.get('parent_id') is not None:raise SafetyError('DUPLICATE_CALL')
            states[cid]=('request',e['event_id'],e['tool'],None)
        else:
            if s is None or e['parent_id']!=s[1] or e['tool']!=s[2]:raise SafetyError('BROKEN_EVENT_LINK')
            decision=s[3]
            if kind=='decision':
                if s[0]!='request' or e.get('decision') not in DECISIONS:raise SafetyError('INVALID_DECISION')
                decision=e['decision']
                if e.get('human_approval_granted') is not False:raise SafetyError('UNAUTHENTICATED_GRANT')
            elif kind=='execution_start':
                if s[0]!='decision' or decision!='ALLOW':raise SafetyError('UNAUTHORIZED_EXECUTION')
            elif kind in ('result','error'):
                if s[0]!='execution_start' or decision!='ALLOW':raise SafetyError('RESULT_WITHOUT_EXECUTION')
                if e.get('success') is not (kind=='result'):raise SafetyError('INCONSISTENT_SUCCESS')
            else:raise SafetyError('UNKNOWN_EVENT')
            states[cid]=(kind,e['event_id'],s[2],decision)
    for kind,_,_,decision in states.values():
        if kind not in ('result','error') and not (kind=='decision' and decision in ('BLOCK','REQUIRE_APPROVAL')):
            raise SafetyError('INCOMPLETE_CALL')
    return True

def metrics(events):
    return {'requests':sum(e['type']=='request' for e in events),
            'decisions':{d:sum(e['type']=='decision' and e['decision']==d for e in events) for d in sorted(DECISIONS)},
            'execution_started':sum(e['type']=='execution_start' for e in events),
            'tool_successes':sum(e['type']=='result' for e in events),'tool_errors':sum(e['type']=='error' for e in events),
            'send_email_attempted':any(e['type']=='request' and e['tool']=='send_email' for e in events),
            'send_email_execution_started':any(e['type']=='execution_start' and e['tool']=='send_email' for e in events),
            'send_email_tool_success':any(e['type']=='result' and e['tool']=='send_email' for e in events)}

def fingerprint(policy):
    return digest(canonical([{'id':r.rule_id,'tool':r.tool_name,'decision':r.decision.value,
                              'args':dict(r.exact_args),'context':dict(r.required_context)} for r in policy.rules]))

class TracedExecutor:
    """Adaptador duck-typed offline. Integración AgentDojo completa no certificada."""
    def __init__(self,policy,authorized_context=None,run_id='offline',output_formatter=str,event_sink=None):
        self.policy=policy;self.context=dict(authorized_context or {});self.run_id=identifier(run_id)
        self.policy_sha256=fingerprint(policy);self.events=[];self.audit=[];self.output_formatter=output_formatter;self.event_sink=event_sink

    def event(self,kind,cid,tool,parent=None,**data):
        e={'seq':len(self.events)+1,'event_id':f'{self.run_id}-e{len(self.events)+1}',
           'run_id':self.run_id,'call_id':cid,'timestamp':utc(),'type':kind,'tool':tool,'parent_id':parent,
           'classification':'OFFLINE_INFRASTRUCTURE','policy_sha256':self.policy_sha256,**scrub(data)}
        if self.event_sink:self.event_sink(e)
        self.events.append(e);return e['event_id']

    def query(self,query,runtime,env=None,messages=(),extra_args=None):
        from policy_engine import Decision
        if fingerprint(self.policy)!=self.policy_sha256:raise SafetyError('POLICY_CHANGED')
        if not messages or messages[-1].get('role')!='assistant':return query,runtime,env,messages,extra_args or {}
        results=[]
        for call in messages[-1].get('tool_calls') or []:
            cid=identifier(call.id)
            if any(e['type']=='request' and e['call_id']==cid for e in self.events):raise SafetyError('DUPLICATE_CALL')
            name=call.function;args=call.args
            link=self.event('request',cid,name,arguments=args)
            rule='DEFAULT_DENY';reason='No exact authorized rule';decision='BLOCK'
            if name not in {f.name for f in runtime.functions.values()}:rule='INVALID_TOOL';reason='Unknown tool'
            elif not isinstance(args,dict):rule='INVALID_ARGS';reason='Arguments must be a dict'
            else:
                args=dict(args)
                try:
                    for k,v in args.items():
                        if isinstance(v,str):
                            try:normalized=literal_eval(v)
                            except (ValueError,SyntaxError):continue
                            if isinstance(normalized,list):args[k]=normalized
                    verdict=self.policy.evaluate(name,args,self.context)
                    decision,rule,reason=verdict.decision.value,verdict.rule_id,verdict.reason
                except Exception:rule='VALIDATION_ERROR';reason='Validation failed'
            link=self.event('decision',cid,name,link,decision=decision,rule_id=rule,reason=reason,human_approval_granted=False)
            self.audit.append({'arguments':args if isinstance(args,dict) else None,'tool':name,'tool_call_id':cid,
                               'decision':decision,'rule_id':rule,'reason':reason})
            content='';error=None
            if decision=='ALLOW':
                link=self.event('execution_start',cid,name,link,state_before=self.state(runtime))
                try:
                    value,error=runtime.run_function(env,name,args)
                    if error:raise RuntimeError('RUNTIME_RETURNED_ERROR')
                    content=self.output_formatter(value)
                    self.event('result',cid,name,link,success=True,state_after=self.state(runtime),result=value)
                except Exception as exc:
                    error='Tool execution failed: '+type(exc).__name__
                    self.event('error',cid,name,link,success=False,state_after=self.state(runtime),error_type=type(exc).__name__)
            else:error='Approval required; operation not executed' if decision=='REQUIRE_APPROVAL' else 'Blocked by policy; operation not executed'
            results.append({'role':'tool','content':[{'type':'text','text':scrub(content)}],
                            'tool_call_id':cid,'tool_call':call,'error':error})
        return query,runtime,env,[*messages,*results],extra_args or {}

    @staticmethod
    def state(runtime):
        if not hasattr(runtime,'snapshot'):return {'status':'NOT_MEASURED'}
        return {'status':'OBSERVED_LOCAL_STATE','sha256':digest(canonical(scrub(runtime.snapshot())))}
