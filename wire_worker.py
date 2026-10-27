"""Private child boundary; no SDK retries, redirects or streaming.

No CLI runner for episodes. Only the parent transport supplies the live packet.
Fixtures install a network-denying audit hook before executing their branch.
"""
import json,sys,time,os

CURRENT_STAGE='worker_start'
CURRENT_AUDIT_DETAIL=None

if os.environ.get('ADR_TEST_OUTPUT'):
    endpoint=os.environ.get('ADR_TEST_HTTP_ENDPOINT','')
    local_test_port=None
    try:
        if endpoint.startswith('http://127.0.0.1:'):
            local_test_port=int(endpoint.split(':',2)[2].split('/',1)[0])
    except (ValueError,IndexError):
        local_test_port=None
    def deny_regression_network(event,args):
        global CURRENT_AUDIT_DETAIL
        if not event.startswith('socket.'):return
        if local_test_port and event=='socket.getaddrinfo' and args[0]=='127.0.0.1' and args[1]==local_test_port:return
        if local_test_port and event=='socket.connect' and len(args)>1 and isinstance(args[1],tuple) and args[1][0]=='127.0.0.1' and args[1][1]==local_test_port:return
        # Socket operations are permitted only after creation; all connect
        # events remain restricted to the exact test loopback endpoint above.
        if local_test_port and event in {'socket.__new__','socket.send','socket.recv','socket.recv_into','socket.getsockopt','socket.shutdown','socket.close'}:return
        target=''
        if event=='socket.connect' and len(args)>1 and isinstance(args[1],tuple):
            target=f"{args[1][0]}:{args[1][1]}"
        elif event=='socket.getaddrinfo' and len(args)>1:
            target=f"{args[0]}:{args[1]}"
        CURRENT_AUDIT_DETAIL=f"{event}:{target}"
        raise PermissionError('REGRESSION_NETWORK_DISABLED')
    sys.addaudithook(deny_regression_network)

def main():
    global CURRENT_STAGE
    CURRENT_STAGE='packet_read'
    packet=json.load(sys.stdin)
    if packet.get('mode')=='OFFLINE_FIXTURE':
        def deny(event,args):
            if event.startswith('socket.'):raise PermissionError('OFFLINE_WORKER')
        sys.addaudithook(deny)
        if packet.get('action')=='sleep':time.sleep(3)
        if packet.get('action')=='network':
            import socket
            socket.create_connection(('example.invalid',443))
        print(json.dumps({'fixture':True,'external_requests':0}));return
    if packet.get('mode')=='LOCAL_TEST_HTTP':
        if not os.environ.get('ADR_TEST_OUTPUT'):raise RuntimeError('TEST_MODE_REQUIRED')
        import http.client,urllib.parse
        endpoint=urllib.parse.urlsplit(packet.get('endpoint',''))
        if endpoint.scheme!='http' or endpoint.hostname!='127.0.0.1' or endpoint.port is None or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
            raise RuntimeError('LOOPBACK_ENDPOINT_REQUIRED')
        payload=packet['payload'];key=packet.get('key');timeout=packet['timeout_ms']/1000
        if key!='LOCAL_TEST_ONLY_NOT_A_SECRET' or not 0<timeout<=30:raise RuntimeError('INVALID_LOCAL_TEST_PACKET')
        CURRENT_STAGE='local_http_connect'
        conn=http.client.HTTPConnection('127.0.0.1',endpoint.port,timeout=timeout)
        try:
            CURRENT_STAGE='local_http_send'
            conn.request('POST',endpoint.path or '/v1/chat/completions',json.dumps(payload).encode(),{'Authorization':'Bearer '+key,'Content-Type':'application/json'})
            CURRENT_STAGE='local_http_response_headers'
            response=conn.getresponse()
            if response.status!=200:raise RuntimeError('LOCAL_TEST_STATUS')
            CURRENT_STAGE='local_http_response_body'
            raw=response.read(1_500_001)
            if len(raw)>1_500_000:raise RuntimeError('RESPONSE_TOO_LARGE')
            CURRENT_STAGE='local_http_json_parse'
            result=json.loads(raw)
            CURRENT_STAGE='local_http_complete'
            print(json.dumps(result));return
        finally:conn.close()
    if packet.get('mode')!='LIVE_AUTHORIZED':raise RuntimeError('PARENT_AUTHORIZATION_REQUIRED')
    import http.client,ssl
    payload=packet['payload'];key=packet['key'];timeout=packet['timeout_ms']/1000
    if not 0<timeout<=300 or not key or '\r' in key or '\n' in key:raise RuntimeError('INVALID_PACKET')
    CURRENT_STAGE='tls_setup'
    conn=http.client.HTTPSConnection('api.tokenfactory.nebius.com',timeout=timeout,context=ssl.create_default_context())
    try:
        CURRENT_STAGE='https_send'
        conn.request('POST','/v1/chat/completions',json.dumps(payload).encode(),{'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        CURRENT_STAGE='https_response_headers'
        response=conn.getresponse()
        if response.status!=200:raise RuntimeError('PROVIDER_STATUS')
        CURRENT_STAGE='https_response_body'
        raw=response.read(1_500_001)
        if len(raw)>1_500_000:raise RuntimeError('RESPONSE_TOO_LARGE')
        CURRENT_STAGE='https_json_parse'
        result=json.loads(raw)
        CURRENT_STAGE='https_complete'
        print(json.dumps(result))
    finally:conn.close()

if __name__=='__main__':
    try:main()
    except BaseException as exc:
        sys.stderr.write(json.dumps({'wire_error':{'stage':CURRENT_STAGE,'type':type(exc).__name__,'audit':CURRENT_AUDIT_DETAIL}})+'\n')
        sys.exit(2)
