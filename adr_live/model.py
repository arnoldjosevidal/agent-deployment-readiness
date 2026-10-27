"""Explicit two-case boundary. No authorization is supplied by this module."""
from copy import deepcopy
from pathlib import Path
from decimal import Decimal
import json,sys,time,os
from adr_g64r.common import SafetyError,canonical,digest
from adr_p1.transport import Transport,MODEL
from adr_p1.exploratory_transport import ExploratoryTransport
from adr_p1.campaign_transport import CampaignTransport
from adr_p1.approval_exploratory_transport import ApprovalExploratoryTransport

ROOT=Path(__file__).resolve().parents[1]
REVISION='a9904d24bcc1d289a1950fa9d2b978c47cf903b9'
_PLAN=json.loads((ROOT/'freeze_reference/PLAN_78_EPISODIOS_V1.json').read_text(encoding='utf-8'))
CASE_IDS=tuple(e['planned_episode_id'] for e in sorted(_PLAN['episodes'],key=lambda x:x['sequence']) if e.get('pair_id') not in {'MVP1_PAIR_03','MVP1_PAIR_04'})
def classification():return 'OFFLINE_MOCK_TRANSPORT_NOT_REAL_EPISODE'if os.environ.get('ADR_TEST_OUTPUT')else 'REAL_EXPLORATORY_B1_DEVIATION_NOT_PILOT'

class TokenCounter:
    def __init__(self):
        sys.path.insert(0,str(ROOT/'vendor'))
        from jinja2.sandbox import ImmutableSandboxedEnvironment
        from tokenizers import Tokenizer
        env=ImmutableSandboxedEnvironment(trim_blocks=True,lstrip_blocks=True,extensions=['jinja2.ext.loopcontrols'])
        env.filters['tojson']=lambda x,**kw:json.dumps(x,ensure_ascii=False,sort_keys=True,**kw)
        def fail(message):raise SafetyError('TOKEN_TEMPLATE_REJECTED')
        env.globals['raise_exception']=fail
        self.template=env.from_string((ROOT/'assets/nemotron_tokenizer/chat_template.jinja').read_text(encoding='utf-8'))
        self.tokenizer=Tokenizer.from_file(str(ROOT/'assets/nemotron_tokenizer/tokenizer.json'))
    def certificate(self,payload):
        messages=deepcopy(payload['messages'])
        for m in messages:
            for call in m.get('tool_calls',[]):
                f=call['function']
                if isinstance(f['arguments'],str):
                    # Same raw arguments are sent; this conversion is rendering only.
                    try:f['arguments']=json.loads(f['arguments'])
                    except ValueError:raise SafetyError('UNRENDERABLE_TOOL_HISTORY')from None
                    if type(f['arguments'])is not dict:raise SafetyError('UNRENDERABLE_TOOL_HISTORY')
        rendered=self.template.render(messages=messages,tools=payload.get('tools',[]),add_generation_prompt=True,bos_token='<s>',eos_token='</s>')
        count=len(self.tokenizer.encode(rendered,add_special_tokens=False).ids)
        if count>7168:raise SafetyError('LOCAL_INPUT_HEADROOM_EXHAUSTED')
        # Local count is exact for the pinned public template, NOT a certified
        # upper bound for an undisclosed provider serving template/revision.
        # Enabling requires a separately evidenced provider binding, never a
        # numerical margin or the first billed response as a certificate.
        binding=json.loads((ROOT/'config/PROVIDER_TOKEN_BINDING.json').read_text(encoding='utf-8'))
        verified=False
        if binding.get('verified')is True:
            proof=(ROOT/binding['proof_path']).resolve()
            verified=(proof.is_relative_to(ROOT)and proof.is_file()and digest(proof.read_bytes())==binding.get('proof_sha256')and bool(binding.get('review_reference'))and binding.get('model')==MODEL and binding.get('revision')==REVISION and binding.get('template_sha256')==digest((ROOT/'assets/nemotron_tokenizer/chat_template.jinja').read_bytes())and binding.get('tokenizer_sha256')==digest((ROOT/'assets/nemotron_tokenizer/tokenizer.json').read_bytes()))
            if not verified:raise SafetyError('INVALID_PROVIDER_TOKEN_BINDING')
        return {'payload_sha256':digest(canonical(payload)),'model':MODEL,'tokenizer_revision':REVISION,'local_template_tokens':count,'upper_bound':8192,'headroom_tokens':8192-count,'verified':bool(verified),'provider_binding':'EVIDENCED_SERVING_TEMPLATE'if verified else 'UNVERIFIED_SERVING_TEMPLATE','rendered_sha256':digest(rendered.encode())}

class NebiusModel:
    def __init__(self,transport,authorization,counter=None):
        exploratory_pair=(type(transport)is ExploratoryTransport and authorization.get('exploratory_b1_deviation')is True)
        exploratory_campaign=(type(transport)is CampaignTransport and authorization.get('exploratory_b1_deviation')is True)
        exploratory_approval=(type(transport)is ApprovalExploratoryTransport and authorization.get('scope')=='EXPLORATORY_LIVE_NON_B1' and authorization.get('b1_status')=='BLOCKED')
        if type(transport)is not Transport and not exploratory_pair and not exploratory_campaign and not exploratory_approval:raise SafetyError('DURABLE_TRANSPORT_REQUIRED')
        if counter is not None and not os.environ.get('ADR_TEST_OUTPUT'):raise SafetyError('PRODUCTION_COUNTER_SUBSTITUTION_FORBIDDEN')
        if counter is None and type(transport)is ApprovalExploratoryTransport:
            # Experimental local counter for the explicitly non-B1 workflow.
            # The B1 Transport continues to use the frozen provider-binding path.
            from .counter_v031 import NebiusInputCounterV031
            counter=NebiusInputCounterV031()
        self.transport=transport;self.authorization=deepcopy(authorization);self.counter=counter or TokenCounter();self.index=0;self.certificate=None;self.current_episode=None;self.current_run_id=None
        if exploratory_approval and type(self.counter).__name__ == "NebiusInputCounterV031":
            # Load local pinned assets before accepting workflow requests.
            # This prewarm is offline and does not contact a provider.
            self.counter.prepare()
    def bind(self,planned_id,run_id,store):
        if planned_id not in CASE_IDS or store is not self.transport.store:raise SafetyError('CAMPAIGN_CASE_SCOPE_REQUIRED')
        if self.authorization.get('planned_case_id')!=planned_id:raise SafetyError('CASE_AUTHORIZATION_REQUIRED')
        self.current_episode,self.current_run_id=planned_id,run_id
        if type(self.transport)is CampaignTransport:self.transport.bind_episode(planned_id,run_id)
        self.index=0
    @staticmethod
    def wire_payload(payload):
        return {**payload,'store':False,'tool_choice':'auto'}
    def payload_hash(self,payload):return digest(canonical(self.wire_payload(payload)))
    def complete(self,payload,rid,remaining_ms,before_wire):
        from adr_gateb.runner import Frame
        p=self.wire_payload(payload);self.certificate=self.counter.certificate(p)
        start=time.monotonic()
        r=self.transport.request(rid,p['messages'],tools=p['tools'],authorization=self.authorization,token_certificate=self.certificate,deadline_ms=remaining_ms,before_wire=before_wire)
        self.index+=1
        c=r['choices'][0];m=c['message'];content=m.get('content')or ''
        if type(content)is not str or c.get('finish_reason')not in ('stop','tool_calls'):raise SafetyError('INCOMPLETE_OR_UNKNOWN_COMPLETION')
        calls=[]
        for tc in m.get('tool_calls')or []:
            if tc.get('type')!='function' or type(tc.get('function'))is not dict:raise SafetyError('MODEL_TOOL_SCHEMA')
            f=tc['function']
            if type(f.get('arguments'))is not str or type(f.get('name'))is not str:raise SafetyError('RAW_TOOL_ARGUMENTS_REQUIRED')
            calls.append({'id':tc['id'],'name':f['name'],'arguments':f['arguments']})
        return Frame(tuple(calls),content,r['usage']['prompt_tokens'],r['usage']['completion_tokens'],int((time.monotonic()-start)*1000))
    def request_snapshot(self,rid):
        if type(self.transport)is CampaignTransport:return self.transport.campaign.request_snapshot(self.current_episode)
        with self.transport.store.connection()as db:return db.execute('SELECT id,status,reserved_tokens,reserved_usd,input_tokens,output_tokens FROM p1_requests WHERE session=? AND substr(id,1,?)=? ORDER BY id',(self.transport.session,len(rid+'-m'),rid+'-m')).fetchall()
    def accounting(self,rid):
        if type(self.transport)is CampaignTransport:
            rows=self.request_snapshot(rid);complete=all(r[1]=='COMPLETE'for r in rows)
            cost=sum((Decimal(r[6])for r in rows if r[6]is not None),Decimal(0))
            mocked=bool(os.environ.get('ADR_TEST_OUTPUT'))
            return {'classification':classification(),'synthetic_usage':mocked,'real_external_requests':0 if mocked else len(rows),'mock_requests':len(rows)if mocked else 0,'real_cost_usd':'0'if mocked else str(cost)if complete else'UNKNOWN','known_cost_usd':str(cost),'reserved_usd':str(sum((Decimal(r[3])for r in rows if r[1]!='COMPLETE'),Decimal(0))),'cost_basis':'MOCK_ONLY'if mocked else'PUBLIC_NET_TARIFF_ESTIMATE_INCLUDING_21PCT_LOCAL_TAX_NOT_INVOICE','unknown_requests':sum(r[1]!='COMPLETE'for r in rows),'b1':'BLOCKED','local_input_bound_certified_by_provider':False,'campaign_control':{'campaign_id':self.transport.campaign and __import__('adr_campaign.campaign_runner',fromlist=['CAMPAIGN_ID']).CAMPAIGN_ID,'planned_episode_id':self.current_episode,'campaign_plan_sha256':self.transport.campaign.plan_sha256,'campaign_config_sha256':self.transport.campaign.config_sha256,'requests':rows,'verification':self.transport.campaign.verify()}}
        self.transport.snapshot()
        rows=self.request_snapshot(rid);complete=all(r[1]=='COMPLETE'for r in rows)
        cost=sum((Decimal(r[4])*Decimal('0.00000006')+Decimal(r[5])*Decimal('0.00000024')for r in rows if r[1]=='COMPLETE'),Decimal(0))
        mocked=bool(os.environ.get('ADR_TEST_OUTPUT'))
        return {'classification':'EXPLORATORY_LIVE_NON_B1' if type(self.transport)is ApprovalExploratoryTransport and not mocked else classification(),'synthetic_usage':mocked,'real_external_requests':0 if mocked else len(rows),'mock_requests':len(rows)if mocked else 0,'real_cost_usd':'0'if mocked else str(cost)if complete else 'UNKNOWN','known_cost_usd':str(cost),'reserved_usd':str(sum((Decimal(r[3])for r in rows),Decimal(0))),'cost_basis':'MOCK_ONLY'if mocked else 'PUBLIC_NET_TARIFF_ESTIMATE_NOT_INVOICE','unknown_requests':sum(r[1]!='COMPLETE'for r in rows),'b1':'BLOCKED' if type(self.transport)is ApprovalExploratoryTransport else 'UNCHANGED','provider_input_bound_certified':False if type(self.transport)is ApprovalExploratoryTransport else None}
