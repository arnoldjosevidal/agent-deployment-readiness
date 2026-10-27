from copy import deepcopy
import hashlib,json
from pathlib import Path
from adr_g64r.common import SafetyError,canonical,digest

FREEZE_ID='ADR_GATE_A_MVP_FREEZE_V1_20261015'
MANIFEST_SHA='138e0fa5f51574f2c58ab4d42959cef4dfe038554087a2a6febd0a6b75a9564b'
A='A_NO_GATE';G='G_CALENDAR_READONLY_V1'
class Design:
    def __init__(self,path):
        self.path=Path(path).resolve();self.verify_files()
        self._policy=self._read('POLITICA_PORTERO_INDEPENDIENTE_V1.json')
        self._profile=self._read('PERFIL_COMPARABILIDAD_V1.json')
        self._plan=self._read('PLAN_78_EPISODIOS_V1.json')
        self._bindings=[digest(canonical(x))for x in(self._policy,self._profile,self._plan)]
        self.policy_sha=hashlib.sha256((self.path/'POLITICA_PORTERO_INDEPENDIENTE_V1.json').read_bytes()).hexdigest()
        self.profile_sha=hashlib.sha256((self.path/'PERFIL_COMPARABILIDAD_V1.json').read_bytes()).hexdigest()
    def _read(self,name):return json.loads((self.path/name).read_text(encoding='utf-8'))
    def verify_files(self):
        raw=(self.path/'MANIFEST_SHA256.json').read_bytes()
        if digest(raw)!=MANIFEST_SHA:raise SafetyError('FREEZE_MANIFEST_DRIFT')
        m=json.loads(raw)
        for r in m['files']:
            p=(self.path/r['path']).resolve()
            if not p.is_relative_to(self.path)or not p.is_file()or digest(p.read_bytes())!=r['sha256']:raise SafetyError('FREEZE_PAYLOAD_DRIFT')
        if self._read('SELLADO_DOCUMENTAL.json')['manifest_sha256']!=MANIFEST_SHA:raise SafetyError('FREEZE_SEAL_DRIFT')
    def verify(self):
        self.verify_files()
        if self._bindings!=[digest(canonical(x))for x in(self._policy,self._profile,self._plan)]:raise SafetyError('IN_MEMORY_DESIGN_DRIFT')
    @property
    def profile(self):return deepcopy(self._profile)
    @property
    def policy(self):return deepcopy(self._policy)
    @property
    def plan(self):return deepcopy(self._plan)
    def row(self,planned_id):
        self.verify()
        rows=[r for r in self._plan['episodes']if r['planned_episode_id']==planned_id]
        if len(rows)!=1:raise SafetyError('UNPLANNED_EPISODE_OR_S2')
        return deepcopy(rows[0])
