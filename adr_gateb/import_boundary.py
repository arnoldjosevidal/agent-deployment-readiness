"""Skip eager package initializers which register every benchmark partition.

The installed modules themselves are unmodified; namespace packages load only
explicit selected implementation modules, not load_suites or workspace registries.
"""
import importlib.util,sys,types
from pathlib import Path
from adr_g64r.common import SafetyError
def install():
    spec=importlib.util.find_spec('agentdojo')
    if spec is None:
        raise SafetyError('AGENTDOJO_RUNTIME_UNAVAILABLE')
    if spec.origin:
        root=Path(spec.origin).parent
    else:
        locations=spec.submodule_search_locations
        root=Path(next(iter(locations),None)) if locations else None
        if root is None:
            raise SafetyError('AGENTDOJO_RUNTIME_LOCATION_UNAVAILABLE')
    for name in ('agentdojo.task_suite','agentdojo.agent_pipeline','agentdojo.agent_pipeline.llms','agentdojo.attacks'):
        if name in sys.modules:raise RuntimeError('EAGER_AGENTDOJO_IMPORT_BEFORE_S1_BOUNDARY')
        package=types.ModuleType(name);package.__path__=[str(root.joinpath(*name.split('.')[1:]))]
        package.__package__=name;package.__spec__=importlib.util.spec_from_loader(name,loader=None,is_package=True)
        sys.modules[name]=package
    return {'mechanism':'Namespace-only parents; installed explicit modules reused without eager registries','skipped_initializers':['task_suite/__init__.py','agent_pipeline/__init__.py','agent_pipeline/llms/__init__.py','attacks/__init__.py']}
