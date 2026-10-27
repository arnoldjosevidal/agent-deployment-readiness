"""Only known S1 IDs; never load shared split manifests, suites or S2."""
import hashlib
TASKS=['user_task_0','user_task_1','user_task_3']
INJECTIONS=['injection_task_'+str(i) for i in (0,4,5,6,11,12)]
METHODS=['direct','important_instructions']
def membership(identifier):
    forced={'user_task_0','user_task_1','user_task_3','injection_task_0'}
    return identifier in forced or hashlib.sha256(('ADR-SPLIT-V1|'+identifier).encode('ascii')).digest()[0]%2==0
def manifest():
    cases=[{'case_id':'benign-'+t,'task':t,'injection':None,'method':None,'kind':'benign'} for t in TASKS]
    cases += [{'case_id':t+'-'+a+'-'+m,'task':t,'injection':a,'method':m,'kind':'attacked'} for t in TASKS for a in INJECTIONS for m in METHODS]
    return {'classification':'PROPOSED_EXECUTION_MANIFEST_NOT_RESULTS','execution_enabled':False,'approved_external_requests':0,'approved_budget_usd':'0','pilot_P1_A_episodes':39,'paired_comparison_total_episodes':78,'episodes_per_arm':39,'paired_extension_status':'PREPARED_NOT_AUTHORIZED','arms':['A_NO_GATE','WITH_GATE_POLICY_PENDING_FREEZE'],'rounds':1,'cases':cases,'s1_derivation':{i:membership(i) for i in TASKS+INJECTIONS},'membership_basis':'Pinned build_split.py algorithm only, not a shared S1/S2 manifest read','model':'nvidia/Nemotron-3_5-Lightning','provider_host':'api.tokenfactory.nebius.com','benchmark':'v1.2/workspace','agentdojo':'0.1.35','policy_provenance':'Guard policy pending independent user-intent-derived freeze; G6.3 oracle policies diagnostic only','optional_not_mvp_blockers':['B/C/E','non-inferiority','S2'],'order':'fixed: benign task order, then task × injection × method; matched initial fixture per arm','retry_automatic':0,'stop_on_infrastructure_error':True,'model_revision':'PROVIDER_REVISION_UNVERIFIED_NO_CALL','metrics':{'BU_denominator':3,'UUA_ASR_denominator':36,'native_attacked_second_boolean':'attacker_goal_success','benign_second_boolean':'not_attack_measurement','unknown_results':None}}
