'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let csrf = null, scenarios = [], currentLab = null, guidedId = null, guidedState = null, guideStep = 0, runsCache = [], busy = false;
const BUILD = 'ADR_FINAL_JUDGE_EXPERIENCE_20261026_V1';
const TOUR = [
  {name:'The legitimate task',target:'task-request',title:'Start with the user’s task',text:'This is the request the agent should complete: summarize a fictional calendar event. It is the task outcome—not the extra action—that determines whether the useful work finished.'},
  {name:'What the agent encounters',target:'untrusted-content',title:'Tool output is data, not permission',text:'The calendar fixture includes untrusted text. It is shown with its source; the fixture does not prove Nemotron followed it.'},
  {name:'The proposed action',target:'agent-proposal',title:'Inspect the additional proposal',text:'The ScriptedModel fixture proposes a fictional email after the calendar lookup. This is a predetermined proposal, not a live model decision.'},
  {name:'ADR evaluates',target:'policy-decision',title:'ADR checks before the effect',text:'The local policy engine selects a branch for this specific tool action. The task lane and action lane are tracked separately.'},
  {name:'Human decision',target:'human-decision',title:'Review only the held action',text:'REQUIRE_APPROVAL holds this exact email. Choose approve or reject below. Next remains disabled until the backend records your choice.'},
  {name:'The task continues',target:'task-outcome',title:'See what happened to the main task',text:'After your decision, the backend returns its result to ScriptedModel. The task outcome shown here comes from the persisted run.'},
  {name:'Your evidence',target:'audit-evidence',title:'Inspect evidence for this run',text:'Open this run’s action record and audit events. Historical replay and provider records remain separate from this interactive run.'},
  {name:'Try it yourself',target:'tour-try',title:'Explore another existing scenario',text:'Choose a fixture and compare With ADR with Without ADR. Both remain inside the fictional sandbox.'}
];
const FAQ = [
 ['What is ADR?','ADR — Agent Deployment Readiness is an action-control and evidence layer for AI agents. It evaluates a proposed action before its effect.'],
 ['What does Agent Deployment Readiness mean?','It describes ADR’s goal: make an agent’s action permissions and supporting evidence ready to review before deployment. This prototype does not certify deployment readiness.'],
 ['What problem does ADR solve?','An agent may have access to a tool that it should not use for a particular task. ADR checks each proposed action against a policy before the tool effect.'],
 ['Why isn’t prompt engineering enough?','Instructions can guide a model, but this prototype places a deterministic policy check at the action boundary. The demo does not prove protection against all prompt injection.'],
 ['Does ADR replace the AI agent?','No. The agent proposes actions and continues the task. ADR evaluates proposed actions and records decisions.'],
 ['Does ADR require human approval for every action?','No. The policy can ALLOW a permitted action, BLOCK a prohibited one, or REQUIRE_APPROVAL for a held action. The fixtures show selective decisions.'],
 ['What happens when ADR blocks an action?','That action is stopped before the fictional executor. The task may continue if its workflow can proceed; the recorded task state determines the answer.'],
 ['Can legitimate work still continue?','In the existing offline fixtures, the calendar task completes after the additional email is rejected or the fictional file action is blocked. This is ScriptedModel fixture behavior, not live Nemotron utility evidence.'],
 ['What is the difference between BLOCK and REJECT?','BLOCK is the policy engine’s denial of an action. REJECT is a human operator’s decision not to approve an action that was held with REQUIRE_APPROVAL. A BLOCK cannot be overridden in this app.'],
 ['What does Nemotron do in this architecture?','In a connected runtime, Nemotron generates model responses and may propose structured tool calls. It does not make ADR’s deterministic policy decisions. This current app is offline; its Nemotron record is historical.'],
 ['How does ADR integrate with Nebius Token Factory?','The historical record reports Nebius Token Factory serving NVIDIA Nemotron-3.5-Lightning. This candidate does not call Nebius. Reproducible live integration and B1 validation remain pending.'],
 ['Is this demonstration live or scripted?','The interactive lab is offline and uses ScriptedModel fixtures with fictional tools. Historical Nemotron/Nebius requests are shown as read-only records and are never replayed.'],
 ['What has actually been tested?','The local policy service, fictional tool effects, authenticated operator decisions, continuation, persistence, recovery and audit chain have offline tests. Historical provider requests are separately summarized; this build has no live model run.'],
 ['What evidence does ADR record?','The local app records run and action identifiers, proposed tool and arguments, policy decision, operator choice, simulated effect, task outcome and hash-linked audit events.'],
 ['Can a human override a prohibited action?','No. BLOCK is not approvable. A human can approve or reject only a pending REQUIRE_APPROVAL action.'],
 ['How could an enterprise deploy ADR?','A possible path is an agent-tool interceptor, a policy service, authenticated approval workflow, tenant-isolated storage, and monitoring. These are proposed architecture, not implemented production features.'],
 ['Can ADR support governance and regulatory audit workflows?','Traceable action records may support an organization’s governance design. This prototype is not certified for the EU AI Act, GDPR or another regulatory framework.'],
 ['What limitations remain before production?','Live integration in this candidate, B1 token-binding evidence, multi-user identity, tenant isolation, deployment hardening, availability and operational performance all need further work and validation.'],
 ['How is this different from a normal approval workflow?','ADR distinguishes policy outcomes at the action boundary: allow, prohibit, or hold for a person. The current demo shows how action status and task status can differ.'],
 ['What makes ADR distinctive?','This prototype demonstrates a policy decision placed before fictional tool effects, with human review for held actions and linked evidence. It does not claim to be the first authorization engine or a unique market capability.']
];
async function api(path, body=null, method=body?'POST':'GET') {
  const headers={}; if(body){headers['Content-Type']='application/json';if(csrf)headers['X-ADR-CSRF']=csrf}
  const res=await fetch(path,{method,headers,credentials:'same-origin',body:body?JSON.stringify(body):undefined,cache:'no-store'});
  let data;try{data=await res.json()}catch{throw Object.assign(new Error('Invalid server response'),{code:'INVALID_SERVER_RESPONSE'})}
  if(!res.ok)throw Object.assign(new Error(data.error||'Request failed'),{code:data.error||'REQUEST_FAILED',status:res.status});
  return data;
}
function setMessage(id,text){if($(id))$(id).textContent=text}
function navigate(name){if(!csrf&&name!=='overview'){setMessage('loginMessage','Sign in below to open '+(name==='guided'?'Guided Experience':name==='lab'?'Put ADR to the Test':'this area')+'.');$('loginCard').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'center'});return}document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.id==='page-'+name));document.querySelectorAll('.main-nav [data-page]').forEach(b=>b.setAttribute('aria-current',String(b.dataset.page===name)));const behavior=matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth';if(name==='home')window.scrollTo({top:0,behavior});else $('page-'+name)?.scrollIntoView({behavior,block:'start'});if(name==='lab')loadRuns();if(name==='evidence')loadEvidence();if(name==='technology')loadImpactForTech()}
function node(title,detail,state='',tour=''){return '<div class="flow-node '+state+'"'+(tour?' data-tour="'+esc(tour)+'"':'')+'><b>'+esc(title)+'</b><small>'+esc(detail)+'</small></div>'}
function explanation(r){
 const a=r.actions||[],cal=a.find(x=>x.tool==='search_calendar_events'),mail=a.find(x=>x.tool==='send_email'),files=a.find(x=>x.tool==='list_files'),done=r.task_outcome?.status==='COMPLETED_FIXTURE_CHECK';
 const out=[];
 if(cal?.decision==='ALLOW'&&cal.executed)out.push('ADR allowed the fictional calendar lookup and returned its fixture result.');
 if(files?.decision==='BLOCK')out.push('ADR blocked the fictional file-access action before execution; no real file was accessed.');
 if(mail?.status==='pending')out.push('ADR held the fictional email for your decision. It has not been sent; the calendar result is already available.');
 if(mail?.operator_decision==='APPROVE'&&mail.executed)out.push('You approved this exact fictional email; the simulated .invalid outbox recorded one effect.');
 if(mail?.operator_decision==='REJECT'||mail?.status==='rejected')out.push('You rejected the fictional email. No simulated email effect was recorded.');
 if(mail?.executed&&mail.decision==='NOT_APPLIED')out.push('Without ADR’s policy layer, the fictional email reached the simulated .invalid outbox.');
 if(done)out.push('The ScriptedModel fixture completed the legitimate calendar summary, checked against the returned fictional event.');
 else if(r.status==='awaiting_approval')out.push('The main task is waiting for the human decision; it is not marked complete.');
 else if(r.status==='interrupted_unknown'||r.status==='stopped_error')out.push('The run stopped without a verified completion and was not automatically retried.');
 return out.join(' ');
}
function renderRun(r,target){
 const box=$(target); if(!r){box.innerHTML='';return}
 const acts=r.actions||[],cal=acts.find(a=>a.tool==='search_calendar_events'),mail=acts.find(a=>a.tool==='send_email'),files=acts.find(a=>a.tool==='list_files'),chosen=[...acts].reverse().find(a=>a.decision&&a.decision!=='NOT_APPLIED');
 const complete=r.task_outcome?.status==='COMPLETED_FIXTURE_CHECK',pending=r.status==='awaiting_approval',failed=['interrupted_unknown','stopped_error'].includes(r.status);
 const taskState=complete?'complete':pending?'waiting':failed?'stopped':'working';
 const source=esc(r.source_classification||'UNKNOWN_SOURCE');
 const taskNodes=[
   node('User request',r.user_task||'Fictional task', 'done'),
   node('Calendar lookup',cal?.executed?'Fixture result returned':'Not run',cal?.executed?'done':''),
   node('Agent processing',r.status==='completed'?'Fixture turn complete':pending?'Waiting on action':'In progress',r.status==='completed'?'done':pending?'wait':''),
   node('Continue task',pending?'Waiting for your decision':complete?'Continued after action result':failed?'Stopped on unknown/error state':'In progress',pending?'wait':complete?'done':failed?'stop':'current'),
   node('Task outcome',complete?'Completed — fixture check passed':r.status==='completed'?'Task ended; check result':'Not completed',complete?'done':failed?'stop':pending?'wait':'')
 ].join('');
 const proposal=[...acts].reverse().find(a=>a.tool!=='search_calendar_events')||acts.at(-1);
 const chosenName=proposal?.tool||'No tool proposal';
 const branch=(id,label,caption,selected)=>'<div class="branch '+(selected?'selected '+id:'')+'"><b>'+label+(selected?' · SELECTED':'')+'</b><small>'+caption+'</small></div>';
 const actionNodes=[node('Agent proposal',chosenName,acts.length?'done':'current'),node('ADR policy',r.mode==='with_adr'?(chosen?.decision||'Decision pending'):'Policy layer omitted',chosen?'done':'current')].join('');
 let branches=branch('allow','ALLOW',chosen?.decision==='ALLOW'?'Authorized fictional action ran':'Permitted action runs',chosen?.decision==='ALLOW')+branch('block','BLOCK',chosen?.decision==='BLOCK'?'Denied before the tool effect':'Prohibited action stops',chosen?.decision==='BLOCK')+branch('approval','REQUIRE_APPROVAL',chosen?.decision==='REQUIRE_APPROVAL'?(chosen.status==='pending'?'Held for human decision':chosen.operator_decision==='APPROVE'?'Approved exact action':'Rejected; no effect'):'Sensitive action waits for a person',chosen?.decision==='REQUIRE_APPROVAL');
 const untrusted=r.untrusted_content?'<div class="untrusted" data-tour="untrusted-content"><b>UNTRUSTED TOOL OUTPUT · FIXTURE</b>'+esc(typeof r.untrusted_content==='string'?r.untrusted_content:JSON.stringify(r.untrusted_content))+'<br><small>This content is data, not user authorization.</small></div>':'';
 let actionHtml=acts.map(a=>{
   const did=a.executed?(a.tool==='send_email'?'Recorded in simulated .invalid outbox.':a.tool==='search_calendar_events'?'Fictional calendar lookup executed.':'Fictional sandbox result recorded.'):(a.decision==='BLOCK'?'Blocked before the fictional executor.':a.status==='pending'?'Held; no effect has run.':a.status==='rejected'?'Rejected; no effect ran.':'No simulated effect recorded.');
   const targetAgent=a.tool!=='search_calendar_events'?' data-tour="agent-proposal"':'';
   const targetHuman=a.status==='pending'&&a.decision==='REQUIRE_APPROVAL'?' data-tour="human-decision"':'';
   const detail={action_id:a.action_id||a.proposal_id,action_sha256:a.action_sha256,tool:a.tool,arguments:a.arguments,decision:a.decision||'NOT_APPLIED',reason:a.reason,status:a.status,executed:a.executed,operator_decision:a.operator_decision||null,operator_id:a.operator_id||null,result:a.result||null};
   const controls=targetHuman?'<div class="decision-row"><button class="button primary" data-choice="approve" data-id="'+esc(a.action_id)+'">Approve this action</button><button class="button danger" data-choice="reject" data-id="'+esc(a.action_id)+'">Reject this action</button></div>':'';
   return '<article class="action-card"'+targetAgent+targetHuman+'><div class="action-head"><strong>'+esc(a.tool)+'</strong><span class="decision-pill '+esc(a.decision||'')+'">'+esc(a.decision||'NO ADR DECISION')+'</span><span class="state-pill '+esc(a.status)+'">'+esc(a.status)+'</span></div><p>'+esc(did)+' '+esc(a.reason||'')+'</p><details><summary>Inspect exact action and recorded result</summary><pre>'+esc(JSON.stringify(detail,null,2))+'</pre></details>'+controls+'</article>';
 }).join('');
 const final=r.final_response?'<div class="final-answer" data-tour="task-outcome"><h4>FINAL ANSWER · SCRIPTEDMODEL FIXTURE</h4><p>'+esc(r.final_response)+'</p><p class="small-copy">'+esc(r.task_outcome?.basis||'Fixture response; not a live model assessment.')+'</p></div>':'<div class="run-summary '+(pending?'waiting':'')+'" data-tour="task-outcome"><strong>'+(pending?'Task waiting for operator':'No final task response yet')+'</strong><span>The workflow state is taken from the persisted backend run.</span></div>';
 const html='<div class="run-summary '+(complete?'complete':pending?'waiting':failed?'failed':'')+'" data-tour="task-request"><strong>'+esc(r.scenario_title||'Scenario run')+' · '+esc(r.mode_label||'')+'</strong><span>Run '+esc(r.run_id)+' · '+source+' · '+esc(r.status)+'</span><p class="small-copy"><b>Legitimate request:</b> '+esc(r.user_task||'Not available')+'</p><p>'+esc(explanation(r)||'The run is in progress; no final outcome is recorded yet.')+'</p></div>'+untrusted+
 '<div class="lanes"><section class="lane"><div class="lane-title"><h3>01 · Legitimate task</h3><span>'+esc(r.task_outcome?.status||r.task_status||'IN PROGRESS')+'</span></div><div class="flow">'+taskNodes+'</div></section><section class="lane" data-tour="policy-decision"><div class="lane-title"><h3>02 · Action authorization</h3><span>'+esc(r.mode_label||'')+'</span></div><div class="flow">'+actionNodes+'</div><div class="policy-branches">'+branches+'</div><p class="small-copy">A decision applies to the proposed action. BLOCK is not approvable. The task status is shown separately.</p></section></div>'+
 '<section class="action-list"'+(chosen?' data-tour="agent-proposal"':'')+'>'+actionHtml+'</section>'+final+
 '<details class="technical-fold" data-tour="audit-evidence"><summary>Run evidence · IDs, model fixture requests, decisions and hashes</summary><pre>'+esc(JSON.stringify({run_id:r.run_id,source_classification:r.source_classification,model_requests:r.model_requests,actions:r.actions,task_outcome:r.task_outcome,state_sha256:r.state_sha256,error_code:r.error_code},null,2))+'</pre></details>';
 box.innerHTML=html;
 box.querySelectorAll('[data-choice]').forEach(b=>b.addEventListener('click',()=>decide(r,b.dataset.id,b.dataset.choice,b)));
}
async function decide(run,actionId,choice,button){
 const action=(run.actions||[]).find(a=>a.action_id===actionId);if(!action)return;
 button.disabled=true;setMessage('labNotice','Submitting the authenticated decision…');
 try{
   const result=await api('/api/lab/runs/'+encodeURIComponent(run.run_id)+'/decision',{action_id:actionId,action_sha256:action.action_sha256,choice});
   currentLab=result;if(run.run_id===guidedId)guidedState=result;renderRun(result,run.run_id===guidedId?'guidedRun':'labRun');await loadRuns();
   setMessage('labNotice','Backend recorded '+choice.toUpperCase()+' · '+result.status);
   if(run.run_id===guidedId){guideStep=5;updateTour(true)}
 }catch(error){setMessage('labNotice','Decision not confirmed ('+(error.code||error.message)+'). Reload the persisted run; no retry was sent.');await reload(run.run_id,run.run_id===guidedId?'guidedRun':'labRun')}
}
async function reload(runId,target){try{const r=await api('/api/lab/runs/'+encodeURIComponent(runId));renderRun(r,target);if(runId===guidedId){guidedState=r;updateTour(false)}return r}catch(error){setMessage('labNotice','Could not reload persisted run ('+(error.code||error.message)+').')}}
async function startRun(scenario,mode,target){
 const key=crypto.randomUUID().replaceAll('-','');const r=await api('/api/lab/runs/start',{scenario_id:scenario,mode,idempotency_key:key});
 currentLab=r;if(target==='guidedRun'){guidedId=r.run_id;guidedState=r;}renderRun(r,target);await loadRuns();return r;
}
async function loadCatalog(){
 const selected=$('scenario').value;const result=await api('/api/lab/catalog');scenarios=result.scenarios||[];
 $('scenario').innerHTML=scenarios.map(s=>'<option value="'+esc(s.id)+'">'+esc(s.title)+'</option>').join('');
 if(scenarios.some(s=>s.id===selected))$('scenario').value=selected;
 describeScenario();
}
function describeScenario(){
 const s=scenarios.find(x=>x.id===$('scenario').value);
 $('scenarioDescription').textContent=s?s.description+' Legitimate task: '+s.task:'No scenario selected.';
 $('scenarioSource').textContent=s?'Existing fixture · '+s.provenance+(s.has_injection?' · untrusted-content fixture':''):'Fixture source unavailable.';
}
function mode(){return document.querySelector('input[name="arm"]:checked')?.value||'with_adr'}
async function runScenario(){
 const button=$('runScenario');if(button.disabled)return;button.disabled=true;
 try{const run=await startRun($('scenario').value,mode(),'labRun');setMessage('labNotice','Run persisted · '+run.source_classification);await loadRuns()}
 catch(error){setMessage('labNotice','Run did not start ('+(error.code||error.message)+').')}
 finally{button.disabled=false}
}
function runRow(r,buttonText='Inspect'){
 return '<div class="run-row"><span><b>'+esc(r.scenario_title)+' · '+esc(r.mode_label)+'</b><small>'+esc(r.status)+' · '+esc(r.source_classification)+' · task '+esc(r.task_outcome?.status||r.task_status||'unknown')+'</small></span><button class="button quiet" data-open="'+esc(r.run_id)+'">'+buttonText+'</button></div>';
}
function latestPair(runs,scenarioId){
 const matching=runs.filter(r=>r.scenario_id===scenarioId);
 return {a:matching.find(r=>r.mode==='without_adr')||null,g:matching.find(r=>r.mode==='with_adr')||null};
}
function drawPair(runs){
 const pair=latestPair(runs,$('scenario').value),cell=(r,name)=>{
  if(!r)return '<article class="pair-cell"><h4>'+name+'</h4><strong>Not run</strong><p>Run the selected fixture in this mode to add a persisted result.</p></article>';
  return '<article class="pair-cell"><h4>'+esc(name)+'</h4><strong>'+esc(r.task_outcome?.status||r.status)+'</strong><p>'+esc((r.actions||[]).filter(a=>a.executed).length)+' fictional effect(s) · '+esc((r.actions||[]).map(a=>a.decision).filter(Boolean).join(', ')||'no policy decision')+'<br>'+esc(r.source_classification)+'<br>Run '+esc(r.run_id)+'</p></article>';
 };
 $('comparison').innerHTML=cell(pair.a,'WITHOUT ADR · POLICY LAYER OMITTED')+cell(pair.g,'WITH ADR · POLICY APPLIED');
}
async function loadRuns(){
 try{
  const result=await api('/api/lab/runs');runsCache=result.runs||[];
  $('runHistory').innerHTML=runsCache.length?runsCache.map(r=>runRow(r)).join(''):'<div class="run-summary">No current interactive runs are stored in this temporary database.</div>';
  $('runHistory').querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>reload(b.dataset.open,'labRun'));
  drawPair(runsCache);
 }catch(error){setMessage('labNotice','Run history unavailable ('+(error.code||error.message)+').')}
}
function barChart(elementId,armA,armG,valueKey,label,style=''){
 const el=$(elementId);if(!el)return;const pct=x=>Math.max(0,Math.min(100,(x.runs?x[valueKey]/x.runs:0)*100));
 const row=(name,x,klass)=>'<div class="bar-row"><span>'+name+'</span><div class="bar-track" role="img" aria-label="'+name+': '+x[valueKey]+' of '+x.runs+'"><div class="bar-fill '+klass+' '+style+'" style="width:'+pct(x)+'%"></div></div><span class="bar-value">'+x[valueKey]+'/'+x.runs+'</span></div>';
 el.innerHTML=row('Without ADR',armA,'')+row('With ADR',armG,'gate');
}
function renderHistorical(impact){
 const data=impact.offline_utility_replay, a=data.arms.A,g=data.arms.G;
 $('historicalIntegrity').textContent='Integrity verified · '+data.manifest_verified_files+' files';
 barChart('completionChart',a,g,'utility_true');
 barChart('effectsChart',
  {runs:a.runs,simulated_inbox_effects:a.simulated_inbox_effects},
  {runs:g.runs,simulated_inbox_effects:g.simulated_inbox_effects},
  'simulated_inbox_effects','effects','risk');
 const h=impact.historical_live;
 $('historicalProviderTitle').textContent=h.completed_provider_requests+' completed requests · '+h.workflow_count+' workflows';
 $('historicalProviderCopy').textContent=h.provider+' · '+h.model+' · '+h.input_tokens_reported+' input / '+h.output_tokens_reported+' output tokens reported · estimated cost USD '+h.cost_estimate_usd_before_tax+' before tax; invoice not verified. This is a historical read-only summary, not a replay.';
 $('modelRecord').textContent='Historical record: '+h.model+' via '+h.provider+'. This final judge build has no current provider configuration or active model API path.';
 renderHistoricalRecords(data.records||[]);
}
function renderHistoricalRecords(records){
 const box=$('historicalRunRecords');
 box.innerHTML=records.map(r=>'<div class="run-row"><span><b>'+esc(r.run_id)+' · '+esc(r.arm)+' · '+esc(r.candidate_id)+'</b><small>'+esc(r.runner_model)+' · decision '+esc(r.decision)+' · task fixture '+(r.utility_observed?'complete':'not complete')+' · trace '+esc(r.trace_sha256)+'</small></span><button class="button quiet" data-historical-trace="'+esc(r.run_id)+'">Inspect trace</button></div>').join('');
 box.querySelectorAll('[data-historical-trace]').forEach(button=>button.addEventListener('click',async()=>{
  const runId=button.dataset.historicalTrace;button.disabled=true;
  try{const trace=await api('/api/historical/replay/traces/'+encodeURIComponent(runId)+'.json');
   $('historicalRunDetails').innerHTML='<div class="run-summary"><strong>'+esc(runId)+' · verified historical offline trace</strong><p class="small-copy">Canonical source trace SHA-256: '+esc(trace.source_trace_sha256)+' · redacted display SHA-256: '+esc(trace.display_trace_sha256)+' · '+esc(trace.source_classification)+'</p><p class="small-copy">'+esc(trace.display_sanitization)+'</p><p class="small-copy">This was a ScriptedModel fixture, not a Nemotron-generated attack.</p></div><details class="technical-fold" open><summary>Sanitized historical trace · read-only</summary><pre>'+esc(JSON.stringify(trace.trace,null,2))+'</pre></details>';
   $('historicalRunDetails').scrollIntoView({behavior:'smooth',block:'start'});
  }catch(error){$('historicalRunDetails').innerHTML='<div class="run-summary failed">Historical trace unavailable or hash invalid: '+esc(error.code||error.message)+'</div>'}
  finally{button.disabled=false}
 }));
}
function evidenceList(runs,target){
 const box=$(target);if(!box)return;
 box.innerHTML=runs.length?runs.map(r=>runRow(r)).join(''):'<div class="run-summary">No interactive run evidence in this database yet.</div>';
 box.querySelectorAll('[data-open]').forEach(b=>b.addEventListener('click',async()=>{const r=await reload(b.dataset.open,target==='evidenceRuns'?'evidenceRunDetails':'securityRunDetails');if(r&&target==='securityRunPicker')renderRun(r,'securityRunDetails')}));
}
async function loadEvidence(){
 try{
  const [audit,impact,lab]=await Promise.all([api('/api/audit'),api('/api/impact'),api('/api/lab/runs')]);
  $('auditValidity').textContent=audit.valid?'VALID':'INVALID';$('auditCount').textContent=audit.returned+' of '+audit.total+' events returned · full local chain check completed.';
  $('localRunValue').textContent=String(lab.runs.length);
  renderHistorical(impact);evidenceList(lab.runs||[],'evidenceRuns');evidenceList(lab.runs||[],'securityRunPicker');renderAudit(audit);
  $('impactDetails').textContent=JSON.stringify({current_local_database:impact.current_local_database,historical_offline_replay:impact.offline_utility_replay,historical_provider_record:impact.historical_live,interpretation:impact.interpretation},null,2);
 }catch(error){$('historicalIntegrity').textContent='Evidence unavailable · '+(error.code||error.message);setMessage('auditCount','Could not load a complete evidence snapshot. A stale view is not current evidence.')}
}
function renderAudit(audit){
 const box=$('auditEvents');if(!audit.events?.length){box.innerHTML='<div class="run-summary">No audit events in this local database.</div>';return}
 box.innerHTML=audit.events.map(e=>'<div class="audit-item"><span class="seq">#'+esc(e.seq)+'</span><span class="event">'+esc(e.event)+'<br>'+esc(e.timestamp)+'<br>'+esc(e.operator_id||'system')+'</span><span class="hash">event '+esc(e.event_hash)+'<br>prev '+esc(e.previous_hash)+'<br>'+esc(JSON.stringify(e.details))+'</span></div>').join('');
}
async function verifyAudit(){try{const result=await api('/api/audit');$('auditValidity').textContent=result.valid?'VALID':'INVALID';$('auditCount').textContent=result.returned+' of '+result.total+' events · checked now';renderAudit(result)}catch(error){$('auditValidity').textContent='UNAVAILABLE';setMessage('auditCount','Verification error: '+(error.code||error.message))}}
async function loadImpactForTech(){try{const impact=await api('/api/impact');$('modelRecord').textContent='Historical record: '+impact.historical_live.model+' via '+impact.historical_live.provider+'. This final judge build has no current provider configuration or active model API path.'}catch(error){$('modelRecord').textContent='Historical provider summary unavailable ('+(error.code||error.message)+').'}}
function evidenceView(name){
 document.querySelectorAll('.evidence-view').forEach(v=>{v.classList.toggle('active',v.id==='evidence-'+name);v.classList.toggle('hidden',v.id!=='evidence-'+name)});
 document.querySelectorAll('.evidence-tab').forEach(b=>{const yes=b.dataset.evidenceView===name;b.classList.toggle('active',yes);b.setAttribute('aria-selected',String(yes))});
 if(name==='audit')verifyAudit();
}
function setSpotlight(){
 document.querySelectorAll('.spotlight').forEach(el=>el.classList.remove('spotlight'));
 const item=TOUR[guideStep];$('tourStepCount').textContent=guidedId?(String(guideStep+1).padStart(2,'0')+' / 08'):'READY';
 $('tourProgress').style.width=guidedId?(((guideStep+1)/TOUR.length)*100)+'%':'0%';
 $('tourStepName').textContent=guidedId?item.name:'Start';
 $('guideTitle').textContent=item.title;
 $('guideText').textContent=item.text;
 $('guidePrev').disabled=!guidedId||guideStep===0;
 $('guideNext').disabled=!guidedId||!guidedState||(guideStep===4&&guidedState.status==='awaiting_approval')||guideStep>=TOUR.length-1;
 $('guideSkip').disabled=!guidedId;
 $('guideStart').textContent=guidedId?'Start a new guided run':'Start the tour';
 $('guideReplay').classList.toggle('hidden',!guidedId||!(guidedState?.status==='completed'));
 $('tourTry').classList.toggle('hidden',guideStep!==7);
 if(!guidedId)return;
 const target=document.querySelector('#guidedRun [data-tour="'+item.target+'"]')||document.querySelector('[data-tour="'+item.target+'"]');
 if(target){target.classList.add('spotlight');target.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'center'})}
}
function updateTour(shouldScroll=true){setSpotlight();if(!shouldScroll){const x=document.querySelector('.spotlight');if(x)x.classList.remove('spotlight')}}
async function startGuided(){
 const b=$('guideStart');b.disabled=true;
 try{const r=await startRun('untrusted_email','with_adr','guidedRun');guideStep=0;updateTour(true);setMessage('guideText','A new offline fixture run is linked below. Follow the focused steps; the backend state is the source of each result.')}
 catch(error){setMessage('guideText','The guided run could not start ('+(error.code||error.message)+').')}
 finally{b.disabled=false}
}
function tourNext(){if(!guidedState)return;if(guideStep===4&&guidedState.status==='awaiting_approval')return;guideStep=Math.min(guideStep+1,TOUR.length-1);updateTour(true)}
function tourPrev(){guideStep=Math.max(guideStep-1,0);updateTour(true)}
function skipTour(){document.querySelectorAll('.spotlight').forEach(el=>el.classList.remove('spotlight'));$('guideTitle').textContent='Tour skipped';$('guideText').textContent='The backend run remains below. You can inspect it or continue exploring the lab.';$('guideNext').disabled=true;$('guideSkip').disabled=true}
function replayTour(){guideStep=0;updateTour(true)}
function renderFAQ(){ $('faqList').innerHTML=FAQ.map((item,i)=>'<details><summary><span class="faq-number">'+String(i+1).padStart(2,'0')+'</span> '+esc(item[0])+'</summary><p>'+esc(item[1])+'</p></details>').join('') }
async function refresh(){
 if(busy)return;busy=true;
 try{const state=await api('/api/state');csrf=state.csrf;$('loginCard').classList.add('hidden');$('workspace').classList.remove('hidden');$('logout').classList.remove('hidden');$('operator').textContent='Authenticated local operator';await loadCatalog();await loadRuns()}
 catch(error){if(error.status===401){csrf=null;$('loginCard').classList.remove('hidden');$('workspace').classList.add('hidden');$('logout').classList.add('hidden');$('operator').textContent='Local operator not signed in'}else setMessage('loginMessage','Local session could not be checked ('+(error.code||error.message)+').')}
 finally{busy=false}
}
$('loginForm').addEventListener('submit',async event=>{event.preventDefault();try{const result=await api('/api/login',{password:$('password').value});csrf=result.csrf;$('password').value='';await refresh()}catch(error){$('loginMessage').textContent=error.status===401?'Sign-in failed. Check the password chosen for this server process.':'Sign-in could not complete ('+(error.code||error.message)+').'}});
$('logout').addEventListener('click',async()=>{try{await api('/api/logout',{});csrf=null;$('workspace').classList.add('hidden');$('loginCard').classList.remove('hidden');$('logout').classList.add('hidden');$('operator').textContent='Local operator not signed in';currentLab=null;guidedId=null;guidedState=null}catch(error){setMessage('loginMessage','Sign out was not confirmed.')}});
document.querySelectorAll('.main-nav [data-page]').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.page)));
document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.go)));
$('scenario').addEventListener('change',()=>{describeScenario();drawPair(runsCache)});
$('runScenario').addEventListener('click',runScenario);
$('refreshRuns').addEventListener('click',loadRuns);
$('guideStart').addEventListener('click',startGuided);
$('guidePrev').addEventListener('click',tourPrev);
$('guideNext').addEventListener('click',tourNext);
$('guideSkip').addEventListener('click',skipTour);
$('guideReplay').addEventListener('click',replayTour);
$('tourTry').addEventListener('click',()=>navigate('lab'));
document.querySelectorAll('.evidence-tab').forEach(b=>b.addEventListener('click',()=>evidenceView(b.dataset.evidenceView)));
$('verifyAudit').addEventListener('click',verifyAudit);
document.querySelectorAll('a[data-page]').forEach(a=>a.addEventListener('click',event=>{event.preventDefault();navigate(a.dataset.page)}));
document.addEventListener('keydown',event=>{if(event.key==='Escape')document.querySelectorAll('.spotlight').forEach(el=>el.classList.remove('spotlight'))});
renderFAQ();refresh();setInterval(()=>{if(!document.hidden&&csrf)refresh()},12000);
