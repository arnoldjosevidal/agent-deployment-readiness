import datetime as dt
import hashlib
import json
import math
import re

class SafetyError(RuntimeError): pass
class DuplicateRun(SafetyError): pass
class IntegrityError(SafetyError): pass

def utc(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec='microseconds')
def canonical(value): return (json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode('utf-8')
def digest(value): return hashlib.sha256(value).hexdigest()

def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',value):
        raise SafetyError('INVALID_ID')
    if re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',value):raise SafetyError('RESERVED_ID')
    return value

def scrub(value):
    """Redacción acotada; no certifica privacidad universal. Contadores no son secretos."""
    secret_names={'password','secret','api_key','apikey','access_token','refresh_token','authorization','security_code','credential'}
    if isinstance(value,dict):
        return {str(k):('[REDACTED]' if str(k).lower() in secret_names else scrub(v)) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [scrub(v) for v in value]
    if isinstance(value,str):
        value=re.sub(r'(?i)Bearer\s+\S+','Bearer [REDACTED]',value)
        return re.sub(r'(?i)(api[_-]?key|password|secret|security[_-]?code)\s*[:=]\s*[^\s,;]+',r'\1=[REDACTED]',value)
    if value is None or isinstance(value,(bool,int)):return value
    if isinstance(value,float) and math.isfinite(value):return value
    return {'unsupported_type':type(value).__name__}
