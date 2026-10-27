"""Trabajador controlado para colisiones y muerte de proceso inducida."""
from pathlib import Path
import os
import sys
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
sys.dont_write_bytecode=True
from network_guard import install
install(os.environ['ADR_TEST_OUTPUT'],__file__)
from adr_g64r.storage import EvidenceStore
from adr_g64r.common import DuplicateRun
from helpers import sample,executor,call,run
target,stage=sys.argv[1:3]
s=EvidenceStore(target)
def fault(where):
    if where==stage:os._exit(73)
if stage=='journal':
    def sink(e):
        s.record_event(e)
        if e['type']=='decision':os._exit(73)
    ex=executor('sample',sink);run(ex,[call('read',{'id':'safe'})])
elif stage=='transport_after_reservation':
    from adr_g64r.transport import OfflineTransport,FixtureReply
    from test_transport import limits
    t=OfflineTransport(s,'budget',limits())
    t.request('req',2,[FixtureReply()],fault=lambda _:os._exit(73))
else:
    rid=stage if stage in ('distinctA','distinctB') else 'sample'
    try:s.commit(rid,sample(rid),fault=fault if stage!='concurrent' else None)
    except DuplicateRun:raise SystemExit(23)
