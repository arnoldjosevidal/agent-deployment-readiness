"""Two-case integration entrypoint; no real calls without all explicit gates."""
from pathlib import Path
import argparse,json,sys,os
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))

def runtime_manifest():
    from adr_g64r.common import digest
    return {p.relative_to(ROOT).as_posix():digest(p.read_bytes())for p in sorted(ROOT.rglob('*'))if p.is_file()and not any(x in p.parts for x in ('__pycache__','revision_backups','.git','preparacion'))and p.suffix in ('.py','.json','.jinja','.txt')and p.name!='AUTHORIZATION_REQUEST.json'}

def main():
    from adr_g64r.common import SafetyError,canonical,digest
    p=argparse.ArgumentParser();p.add_argument('--authorization',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    grant=json.loads(Path(a.authorization).read_text(encoding='utf-8'))
    if os.environ.get('ADR_TEST_OUTPUT'):raise SafetyError('OFFLINE_ENVIRONMENT_NO_REAL_DRIVER')
    if grant.get('human_approved')is not True:raise SafetyError('EXPLICIT_TWO_CASE_APPROVAL_REQUIRED')
    expected=json.loads((ROOT/'config/TWO_CASE_PROFILE.json').read_text(encoding='utf-8'))
    if grant.get('runtime_sha256')!=digest(canonical(runtime_manifest()))or grant.get('profile_sha256')!=digest(canonical(expected)):raise SafetyError('GRANT_SOURCE_OR_PROFILE_MISMATCH')
    from adr_gateb.import_boundary import install
    install()
    from adr_live.model import TokenCounter,NebiusModel,CASE_IDS
    from adr_gateb.design import Design
    from adr_gateb.candidate_s1 import CandidateS1
    from adr_gateb.evidence import Store
    from adr_gateb.runner import Runner
    from adr_p1.transport import Transport,Limits
    design=Design(ROOT/'freeze_reference');s1=CandidateS1(design);counter=TokenCounter()
    row=design.row(CASE_IDS[0]);payload={'model':expected['limits']['model'],'messages':[{'role':'system','content':design.profile['system_message']},{'role':'user','content':s1.suite.get_user_task_by_id(row['task_id']).PROMPT}],'tools':s1.tools,'temperature':0.0,'max_tokens':2048,'stream':False,'store':False,'tool_choice':'auto'}
    if not counter.certificate(payload)['verified']:raise SafetyError('PROVIDER_TOKEN_BINDING_UNVERIFIED_NO_CALLS')
    if grant.get('case_ids')!=list(CASE_IDS)or grant.get('max_spend_usd')!='0.10':raise SafetyError('TWO_CASE_SCOPE_REQUIRED')
    if not os.environ.get('NEBIUS_API_KEY'):raise SafetyError('CREDENTIAL_UNAVAILABLE')
    # No credential values ever printed, persisted or passed as argv.
    out=Path(a.output).resolve()
    allowed=ROOT.parent/'evidence/mvp_stage1_real'
    if not out.is_relative_to(allowed.resolve())or str(out)!=grant.get('output_dir')or out.exists():raise SafetyError('FRESH_AUTHORIZED_ADR_EVIDENCE_DIRECTORY_REQUIRED')
    out.mkdir(parents=True,exist_ok=False);store=Store(out);transport=Transport(store,grant['session_id'],Limits(**expected['limits']))
    if grant.get('config_hash')!=transport.config_hash:raise SafetyError('TRANSPORT_GRANT_MISMATCH')
    runner=Runner(design,s1,store)
    for i,pid in enumerate(CASE_IDS):
        result=runner.run(pid,'real-integration-'+str(i),NebiusModel(transport,{**grant,'planned_case_id':pid}))
        store.verify()
        if result['error']:raise SafetyError('INTEGRATION_STOPPED_REVIEW_REQUIRED')
    print(json.dumps({'status':'TWO_REAL_INTEGRATION_CASES_COMPLETE_NOT_PILOT','evidence':str(out),'verification':store.verify()}))
if __name__=='__main__':main()
