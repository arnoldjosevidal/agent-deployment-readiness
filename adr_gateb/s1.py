"""S1-only AgentDojo facade. No get_suite/holdout registry import.

Only the three allowed user classes and six allowed injection classes are
compiled from pinned local distribution source. Benchmark truth is confined
to attack surface selection/evaluation; policy never imports this module.
"""
import ast,datetime,hashlib,importlib,importlib.metadata,sys
from pathlib import Path
from typing import ClassVar
from functools import partial
from copy import deepcopy
from types import SimpleNamespace
from deepdiff import DeepDiff
from agentdojo.base_tasks import BaseUserTask,BaseInjectionTask,TaskDifficulty
from agentdojo.functions_runtime import TaskEnvironment,FunctionsRuntime,FunctionCall,make_function
from agentdojo.default_suites.v1.tools import calendar_client,email_client,cloud_drive_client,types
from agentdojo.task_suite.task_suite import TaskSuite
from adr_g64r.common import SafetyError,canonical,digest
from .design import A,G

class S1:
    def __init__(self,design):
        if importlib.metadata.version('agentdojo')!='0.1.35':raise SafetyError('AGENTDOJO_VERSION_DRIFT')
        self.design=design
        self.root=Path(importlib.import_module('agentdojo').__file__).parent
        self.sources={};self.compiled=[]
        scope={'__name__':__name__,'datetime':datetime,'ClassVar':ClassVar,'BaseUserTask':BaseUserTask,'BaseInjectionTask':BaseInjectionTask,'TaskDifficulty':TaskDifficulty,'FunctionCall':FunctionCall,'TaskEnvironment':TaskEnvironment,'Calendar':calendar_client.Calendar,'Inbox':email_client.Inbox,'CloudDrive':cloud_drive_client.CloudDrive,'Email':types.Email,'EmailID':types.EmailID,'CloudDriveFileID':types.CloudDriveFileID,'SharingPermission':types.SharingPermission}
        suite_tree=self.tree('default_suites/v1/workspace/task_suite.py')
        env=next(n for n in suite_tree.body if isinstance(n,ast.ClassDef)and n.name=='WorkspaceEnvironment')
        self.compile_nodes([env],scope)
        paths=next(ast.literal_eval(n.value)for n in suite_tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='deepdiff_paths_to_exclude'for t in n.targets))
        scope['WorkspaceDeepDiff']=partial(DeepDiff,exclude_paths=paths)
        scope['WorkspaceUserTask']=BaseUserTask[scope['WorkspaceEnvironment']]
        scope['WorkspaceInjectionTask']=BaseInjectionTask[scope['WorkspaceEnvironment']]
        self.environment_type=scope['WorkspaceEnvironment']
        selected={};helpers={}
        for version in ('v1','v1_1','v1_1_1','v1_1_2','v1_2'):
            for kind,names in [('user_tasks',{'UserTask0','UserTask1','UserTask3'}),('injection_tasks',{'InjectionTask'+str(i)for i in (0,4,5,6,11,12)})]:
                rel=f'default_suites/{version}/workspace/{kind}.py'
                if not(self.root/rel).is_file():continue
                for node in self.tree(rel).body:
                    if isinstance(node,ast.ClassDef)and node.name in names:
                        node=deepcopy(node);node.decorator_list=[];selected[node.name]=(node,rel)
                    elif isinstance(node,ast.FunctionDef)and node.name in ('list_is_in_string_or_set','are_email_bodies_in_str'):
                        helpers[node.name]=node
        self.compile_nodes(list(helpers.values()),scope)
        for name,(node,rel)in selected.items():
            self.compile_nodes([node],scope);self.compiled.append({'class':name,'source':rel,'ast_sha256':digest(ast.dump(node,include_attributes=False).encode())})
        tools=[]
        for name in design.profile['shared_tool_catalog_historical_reference']:
            matches=[getattr(m,name)for m in(calendar_client,email_client,cloud_drive_client)if hasattr(m,name)]
            if len(matches)!=1:raise SafetyError('TOOL_CATALOG_DRIFT')
            tools.append(make_function(matches[0]))
        self.suite=TaskSuite('workspace',self.environment_type,tools,benchmark_version=(1,2,0))
        for i in(0,1,3):self.suite.register_user_task(scope['UserTask'+str(i)])
        for i in(0,4,5,6,11,12):self.suite.register_injection_task(scope['InjectionTask'+str(i)])
        self.runtime=FunctionsRuntime(tools)
        from agentdojo.agent_pipeline.llms.openai_llm import _function_to_openai
        self.tools=[_function_to_openai(f)for f in self.runtime.functions.values()]
        self.schema_sha=digest(canonical(self.tools));self._candidates={};self._vectors={}
        # Existing official templates and selector. No model invoked by canary.
        from agentdojo.attacks.baseline_attacks import DirectAttack
        from agentdojo.attacks.base_attacks import FixedJailbreakAttack
        from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttack
        self.direct=DirectAttack(self.suite,SimpleNamespace(name=design.profile['model']))
        self.important=object.__new__(ImportantInstructionsAttack)
        FixedJailbreakAttack.__init__(self.important,ImportantInstructionsAttack._JB_STRING,self.suite,SimpleNamespace(name=design.profile['model']))
        # Installed model-name registry does not reliably know this Nebius ID.
        self.important.user_name='Emma Johnson';self.important.model_name=design.profile['model']
        for attack in(self.direct,self.important):
            attack.get_injection_candidates=self.candidates
        for rel in ('default_suites/v1/tools/calendar_client.py','default_suites/v1/tools/email_client.py','default_suites/v1/tools/cloud_drive_client.py','task_suite/task_suite.py','functions_runtime.py','attacks/base_attacks.py','attacks/baseline_attacks.py','attacks/important_instructions_attacks.py'):
            self.sources[rel]=digest((self.root/rel).read_bytes())
        for p in(self.root/'data/suites/workspace').rglob('*'):
            if p.is_file()and p.suffix in('.yaml','.yml'):self.sources[str(p.relative_to(self.root))]=digest(p.read_bytes())
        self.bound_functions={name:fn.run for name,fn in self.runtime.functions.items()}
    def verify(self):
        if digest(canonical(self.tools))!=self.schema_sha:raise SafetyError('TOOL_SCHEMA_DRIFT')
        if set(self.runtime.functions)!=set(self.bound_functions)or any(self.runtime.functions[n].run is not f for n,f in self.bound_functions.items()):raise SafetyError('TOOL_RUNTIME_DRIFT')
        if any(digest((self.root/rel).read_bytes())!=sha for rel,sha in self.sources.items()):raise SafetyError('S1_SOURCE_DRIFT')
    def tree(self,rel):
        raw=(self.root/rel).read_bytes();self.sources[rel]=digest(raw);return ast.parse(raw.decode())
    @staticmethod
    def compile_nodes(nodes,scope):
        # Only selected local trusted AST nodes; never all default suite classes.
        tree=ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[]))
        exec(compile(tree,'<selected-S1-AgentDojo-source>','exec'),scope)
    def candidates(self,user_task):
        if user_task.ID not in ('user_task_0','user_task_1','user_task_3'):raise SafetyError('S1_SELECTOR_DENIED')
        if user_task.ID not in self._candidates:
            from agentdojo.attacks.base_attacks import BaseAttack
            self._candidates[user_task.ID]=BaseAttack.get_injection_candidates(self.direct,user_task)
        return self._candidates[user_task.ID]
    def vector(self,row):
        if row['kind']=='benign':return {}
        key=(row['task_id'],row['injection_id'],row['attack_method'])
        if key not in self._vectors:
            attack=self.direct if row['attack_method']=='direct'else self.important if row['attack_method']=='important_instructions'else None
            if attack is None:raise SafetyError('ATTACK_METHOD_DRIFT')
            self._vectors[key]=attack.attack(self.suite.get_user_task_by_id(row['task_id']),self.suite.get_injection_task_by_id(row['injection_id']))
        return deepcopy(self._vectors[key])
    def initial(self,row):
        vector=self.vector(row)
        state=self.suite.load_and_inject_default_environment(vector)
        user=self.suite.get_user_task_by_id(row['task_id'])
        return user.init_environment(state),vector
    def evaluate(self,row,final,before,after):
        user=self.suite.get_user_task_by_id(row['task_id'])
        utility=user.utility(final,before,after)
        second=True if row['kind']=='benign'else self.suite.get_injection_task_by_id(row['injection_id']).security(final,before,after)
        if type(utility)is not bool or type(second)is not bool:raise SafetyError('EVALUATOR_BOOLEAN_TYPE')
        return {'native_utility':utility,'native_second_boolean':second,'utility':utility,'attacker_success':None if row['kind']=='benign'else second,'evaluator':'SELECTED_INSTALLED_AGENTDOJO_PREDICATES_NO_REWRITING'}
    def preflight(self):
        rows=self.design.plan['episodes'];pairs={};records=[]
        for row in rows:
            env,vector=self.initial(row);state=digest(canonical(env.model_dump(mode='json')))
            item={'planned_episode_id':row['planned_episode_id'],'pair_id':row['pair_id'],'kind':row['kind'],'mode':row['mode'],'initial_state_sha256':state,'attack_vector_sha256':digest(canonical(vector)),'tool_schema_sha256':self.schema_sha,'public_prompt_sha256':digest(self.suite.get_user_task_by_id(row['task_id']).PROMPT.encode()),'local_seed_if_applicable':row['local_seed_if_applicable'],'scope':'PREFLIGHT_ONLY_NO_ACTOR_EPISODE_OR_OUTCOME'}
            pairs.setdefault(row['pair_id'],[]).append(item);records.append(item)
        for values in pairs.values():
            if len(values)!=2 or any(values[0][k]!=values[1][k]for k in('initial_state_sha256','attack_vector_sha256','tool_schema_sha256','public_prompt_sha256','local_seed_if_applicable')):raise SafetyError('PAIR_NOT_EQUIVALENT')
        for p in(self.root/'data/suites/workspace').rglob('*'):
            if p.is_file()and p.suffix in('.yaml','.yml'):self.sources[str(p.relative_to(self.root))]=digest(p.read_bytes())
        return {'pairs':39,'planned_positions_checked':len(records),'catalog_tools':len(self.tools),'compiled_classes':self.compiled,'task_registry_ids':list(self.suite.user_tasks),'injection_registry_ids':list(self.suite.injection_tasks),'records':records,'sources':self.sources,'actor_episodes_executed':0,'shared_environment':'Packaged workspace base fixture used solely for selected S1; no partition manifest/holdout IDs or outcomes loaded','attack_selector':'Official S1-only GroundTruthPipeline canary for vector visibility; never a policy input','important_instructions_adapter':'Official template, explicit frozen Nemotron model ID as display name; no fallback to another model','model_calls':0}
