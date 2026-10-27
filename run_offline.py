"""Network-denied, append-only output regression runner. No model episodes."""
from pathlib import Path
import argparse,datetime as dt,hashlib,io,json,os,platform,sys,time,unittest
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
def sources():
    return [{'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(ROOT.rglob('*')) if p.is_file() and not any(x in p.parts for x in ('.git','__pycache__','revision_backups')) and p.suffix in ('.py','.json','.html','.md','.txt','.cjs')]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--original-repo');parser.add_argument('--pattern',default='test*.py');a=parser.parse_args()
    out=Path(a.output).resolve()
    if out.is_relative_to(ROOT) or out==ROOT:raise SystemExit('OUTPUT_MUST_BE_OUTSIDE_SOURCE')
    if a.original_repo:os.environ['ADR_ORIGINAL_REPO']=str(Path(a.original_repo).resolve())
    else:os.environ.pop('ADR_ORIGINAL_REPO',None)
    before=sources();out.mkdir(parents=True,exist_ok=False);(out/'testdata').mkdir()
    os.environ['ADR_TEST_OUTPUT']=str(out/'testdata');os.environ['PYTHONDONTWRITEBYTECODE']='1'
    from network_guard import install
    denials=install(out,[ROOT/'crash_worker.py',ROOT/'wire_worker.py'])
    from adr_gateb.import_boundary import install as restrict_imports
    import_boundary=restrict_imports()
    import importlib.metadata
    dependencies={d.metadata['Name']:d.version for d in importlib.metadata.distributions()}
    (out/'DEPENDENCIES_OBSERVED.json').write_text(json.dumps(dependencies,indent=2,sort_keys=True),encoding='utf-8')
    class Result(unittest.TextTestResult):
        def startTest(self,test):super().startTest(test);self.case_status='PASS'
        def addError(self,test,err):self.case_status='ERROR';super().addError(test,err)
        def addFailure(self,test,err):self.case_status='FAIL';super().addFailure(test,err)
        def addSkip(self,test,reason):self.case_status='SKIP';super().addSkip(test,reason)
        def addSubTest(self,test,subtest,err):
            if err:self.case_status='FAIL'if issubclass(err[0],test.failureException)else'ERROR'
            super().addSubTest(test,subtest,err)
        def stopTest(self,test):cases.append({'test':test.id(),'status':self.case_status});super().stopTest(test)
    cases=[];log=io.StringIO();start=time.monotonic()
    suite=unittest.TestSuite(unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern=part)for part in a.pattern.split(','))
    result=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=Result).run(suite)
    after=sources();report={'classification':'EXECUTED_OFFLINE_PREPARATION_TESTS_NOT_MODEL_EPISODES','phase':'MVP_ETAPA1_INTEGRACION_OFFLINE','created_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'python':platform.python_version(),'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'cases':cases,'duration_seconds':time.monotonic()-start,'pass':result.wasSuccessful() and before==after,'source_unchanged':before==after,'import_boundary':import_boundary,'network_guard_denials':denials,'external_provider_calls':0,'model_episodes':0,'real_spend_usd':'0','s2_opened':False,'limitations':'Python audit hook denies socket calls in regression process; allowed workers are fixed and tested; not a universal native OS sandbox','failures_details':[{'test':t.id(),'traceback':e} for t,e in result.failures+result.errors]}
    for name,data in [('results.json',report),('tested_source_manifest.json',before)]:
        with (out/name).open('x',encoding='utf-8')as f:json.dump(data,f,indent=2)
    (out/'regression.log').write_text(log.getvalue(),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('tests_run','failures','errors','skipped','pass')}))
    if not report['pass']:raise SystemExit(1)
if __name__=='__main__':main()
