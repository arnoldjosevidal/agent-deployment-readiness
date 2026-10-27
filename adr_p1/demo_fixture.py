"""Offline evidence walkthrough; NOT agent/model behavior."""
from types import SimpleNamespace
from adr_g64r.storage import EvidenceStore
from adr_g64r.events import TracedExecutor,metrics
from policy_engine import PolicyRule,PolicyEngine,Decision

def build(root):
    store=EvidenceStore(root)
    class Runtime:
        functions={'read':SimpleNamespace(name='read'),'send_email':SimpleNamespace(name='send_email')}
        def __init__(self):self.executed=[]
        def snapshot(self):return {'executed':self.executed}
        def run_function(self,env,name,args):self.executed.append(name);return 'synthetic-only',None
    policy=PolicyEngine([PolicyRule('safe-read','read',Decision.ALLOW,{'id':'public-fixture'}),PolicyRule('human-review','send_email',Decision.REQUIRE_APPROVAL,{'to':'reviewer@example.invalid'})])
    runtime=Runtime();ex=TracedExecutor(policy,run_id='demo-synthetic-v1',event_sink=store.record_event)
    calls=[SimpleNamespace(function=name,args=args,id='demo-'+str(i)) for i,(name,args) in enumerate([('read',{'id':'public-fixture'}),('send_email',{'to':'unapproved@example.invalid'}),('send_email',{'to':'reviewer@example.invalid'})])]
    ex.query('synthetic',runtime,messages=[{'role':'assistant','tool_calls':calls}])
    store.commit(ex.run_id,ex.events,metadata={'classification':'SYNTHETIC_LOCAL_WALKTHROUGH_NOT_MODEL_EXPERIMENT'})
    store.verify()
    return {'classification':'SYNTHETIC_LOCAL_WALKTHROUGH','decisions':[e['decision'] for e in ex.events if e['type']=='decision'],'metrics':metrics(ex.events),'runtime_executed':runtime.executed,'human_approval_granted':False,'events':ex.events}
