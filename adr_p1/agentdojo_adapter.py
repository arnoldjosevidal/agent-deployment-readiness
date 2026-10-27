"""Pinned AgentDojo boundary. No suite loading and no SDK request helper."""
import importlib.metadata
from .transport import MODEL
from adr_g64r.common import SafetyError

class AgentDojoAdapter:
    def __init__(self,transport,authorization,certificate_provider,request_id_provider):
        self.transport=transport;self.authorization=authorization
        self.certificate_provider=certificate_provider;self.request_id_provider=request_id_provider
    def query(self,query,runtime,env,messages,extra_args):
        if importlib.metadata.version('agentdojo')!='0.1.35':raise SafetyError('AGENTDOJO_VERSION_DRIFT')
        from agentdojo.agent_pipeline.llms.openai_llm import _message_to_openai,_function_to_openai,_openai_to_assistant_message
        from openai.types.chat import ChatCompletionMessage
        converted=[_message_to_openai(m,MODEL) for m in messages]
        developers=[m for m in converted if m['role']=='developer']
        if len(developers)>1:raise SafetyError('MULTIPLE_SYSTEM_MESSAGES')
        for m in developers:m['role']='system'
        tools=[_function_to_openai(f) for f in runtime.functions.values()]
        certificate=self.certificate_provider(converted,tools,self.transport.limits)
        result=self.transport.request(self.request_id_provider(),converted,tools=tools,authorization=self.authorization,token_certificate=certificate)
        output=_openai_to_assistant_message(ChatCompletionMessage.model_validate(result['choices'][0]['message']))
        return query,runtime,env,[*messages,output],extra_args
