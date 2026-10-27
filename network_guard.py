"""Defensa adicional Python durante regresión; no sandbox universal del SO."""
import os
from pathlib import Path
import sys
import subprocess

def install(output_root,worker):
    root=Path(output_root).resolve();workers=[Path(w).resolve() for w in (worker if isinstance(worker,(list,tuple)) else [worker])];blocked=[]
    def hook(event,args):
        if event in ('socket.connect','socket.getaddrinfo','socket.sendto','os.system'):
            blocked.append({'event':event});raise PermissionError('OFFLINE_NETWORK_DISABLED')
        if event=='subprocess.Popen':
            command=args[1]
            allowed=False
            for worker in workers:
                if type(command) in (list,tuple):
                    allowed=allowed or (list(map(str,command[:4]))==[sys.executable,'-I','-B',str(worker)])
                elif isinstance(command,str):
                    prefix=subprocess.list2cmdline([sys.executable,'-I','-B',str(worker)])
                    allowed=allowed or ((command==prefix or command.startswith(prefix+' ')) and (args[0] is None or Path(args[0]).resolve()==Path(sys.executable).resolve()))
            if not allowed:raise PermissionError('UNAPPROVED_SUBPROCESS')
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            p=Path(os.fsdecode(args[0])).resolve();mode=args[1] or '';flags=args[2]
            if p.name in ('split_manifest.json','.env') or p.suffix=='.key' or any(x.lower() in ('s2','holdout') for x in p.parts):raise PermissionError('SEALED_OR_SECRET_SOURCE')
            if (any(x in mode for x in 'wax+') or flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)) and not p.is_relative_to(root):raise PermissionError('WRITE_OUTSIDE_REGRESSION_OUTPUT')
        if event in ('os.mkdir','os.remove','os.rmdir','os.chmod','os.utime'):
            if not Path(args[0]).resolve().is_relative_to(root):raise PermissionError('MUTATION_OUTSIDE_OUTPUT')
        if event in ('os.rename','os.link','os.symlink'):
            if any(not Path(x).resolve().is_relative_to(root) for x in args[:2]):raise PermissionError('MUTATION_OUTSIDE_OUTPUT')
    sys.addaudithook(hook);return blocked
