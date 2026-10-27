import json
from adr_g64r.common import canonical,digest,scrub
class CommonSchemaError(ValueError):pass
def strict_loads(raw):
    if type(raw)is not str or len(raw.encode('utf-8'))>1500000:raise CommonSchemaError('COMMON_TOOL_SCHEMA_ERROR')
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise CommonSchemaError('COMMON_TOOL_SCHEMA_ERROR')
            result[k]=v
        return result
    def bad(_):raise CommonSchemaError('COMMON_TOOL_SCHEMA_ERROR')
    try:obj=json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
    except (ValueError,TypeError,RecursionError,UnicodeError):raise CommonSchemaError('COMMON_TOOL_SCHEMA_ERROR')from None
    if type(obj)is not dict:raise CommonSchemaError('COMMON_TOOL_SCHEMA_ERROR')
    try:canonical(obj)
    except (ValueError,TypeError,RecursionError):raise CommonSchemaError('COMMON_TOOL_SCHEMA_ERROR')from None
    return obj
def parse_call(runtime,name,raw):
    obj=strict_loads(raw)
    if name not in runtime.functions:raise CommonSchemaError('COMMON_TOOL_SCHEMA_ERROR')
    fn=runtime.functions[name]
    if set(obj)-set(fn.parameters.model_fields):raise CommonSchemaError('COMMON_TOOL_SCHEMA_ERROR')
    try:normalized=fn.parameters.model_validate_json(canonical(obj),strict=True).model_dump(mode='json')
    except Exception:raise CommonSchemaError('COMMON_TOOL_SCHEMA_ERROR')from None
    return obj,normalized
def argument_audit(raw):
    try:value=scrub(strict_loads(raw))
    except CommonSchemaError:value='[INVALID_JSON_HASH_ONLY]'
    return {'raw_arguments_sha256':digest(raw.encode('utf-8'))if type(raw)is str else None,'raw_arguments_redacted':value}
