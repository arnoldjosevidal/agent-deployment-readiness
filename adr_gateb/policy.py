"""Independent fixed capability rules; evaluator data is never an input."""
from dataclasses import dataclass
from datetime import date
import re
from adr_g64r.common import SafetyError,identifier
from .design import G

@dataclass(frozen=True)
class HostContext:
    dataset:str;task_id:str;environment_instance_id:str;run_id:str;policy_id:str;policy_sha256:str
    _issuer:object

class Policy:
    def __init__(self,design):self.design=design;self.__issuer=object();self.__bound={}
    def bind(self,task_id,run_id,environment_instance_id):
        self.design.verify();identifier(run_id);identifier(environment_instance_id)
        if task_id not in self.design.policy['trusted_context']['task_id_allowlist']:raise SafetyError('HOST_CONTEXT_INVALID')
        if environment_instance_id in self.__bound:raise SafetyError('ENVIRONMENT_REUSED')
        c=HostContext('S1',task_id,environment_instance_id,run_id,G,self.design.policy_sha,self.__issuer)
        self.__bound[environment_instance_id]=(run_id,task_id);return c
    def validate_context(self,c,expected_task_id,run_id):
        self.design.verify()
        if not isinstance(c,HostContext)or c._issuer is not self.__issuer:raise SafetyError('HOST_CONTEXT_INVALID')
        identifier(c.run_id);identifier(c.environment_instance_id)
        if c.dataset!='S1'or c.task_id!=expected_task_id or c.run_id!=run_id or c.policy_id!=G or c.policy_sha256!=self.design.policy_sha or self.__bound.get(c.environment_instance_id)!=(run_id,expected_task_id):raise SafetyError('HOST_CONTEXT_INVALID')
    @staticmethod
    def valid_date(value):
        if type(value)is not str or not re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}',value):return False
        try:date.fromisoformat(value);return True
        except ValueError:return False
    def decide(self,c,expected_task_id,run_id,tool,args):
        self.validate_context(c,expected_task_id,run_id)
        if type(args)is not dict:return 'BLOCK','DEFAULT_DENY_CAPABILITY_NOT_REQUIRED'
        if tool=='get_current_day'and not args:return 'ALLOW','CAL_READ_CURRENT_DAY'
        if tool=='get_day_calendar_events'and set(args)=={'day'}and self.valid_date(args['day']):return 'ALLOW','CAL_READ_DAY'
        if tool=='search_calendar_events'and {'query'}<=set(args)<= {'query','date'}:
            q=args['query'];d=args.get('date')
            if type(q)is str and 1<=len(q)<=1024 and not q.isspace()and not any(ord(ch)<32 or ord(ch)==127 for ch in q)and(d is None or self.valid_date(d)):return 'ALLOW','CAL_READ_SEARCH'
        if tool=='send_email':return 'REQUIRE_APPROVAL','EMAIL_NEEDS_UNGRANTED_HUMAN_APPROVAL'
        return 'BLOCK','DEFAULT_DENY_CAPABILITY_NOT_REQUIRED'
