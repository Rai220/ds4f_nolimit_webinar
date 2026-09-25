import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('weights',ROOT/'ops/weights.py')
weights=importlib.util.module_from_spec(spec);spec.loader.exec_module(weights)


class WeightIntegrity(unittest.TestCase):
    def test_corruption_missing_and_traversal(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'part.safetensors').write_bytes(b'abcd')
            manifest={'repo':'owner/model','revision':'a'*40,'files':[{'name':'part.safetensors','size':4,'sha256':hashlib.sha256(b'abcd').hexdigest()}]}
            selected=weights.select(manifest)
            self.assertEqual(len(weights.verify(selected,root)['verified_weights']),1)
            (root/'part.safetensors').write_bytes(b'abce')
            with self.assertRaisesRegex(ValueError,'SHA256'):weights.verify(selected,root)
            (root/'part.safetensors').unlink()
            with self.assertRaises(FileNotFoundError):weights.verify(selected,root)
            for bad in ['../outside','/etc/passwd','a/../../outside','a\\b']:
                with self.assertRaises(ValueError):weights.safe_path(root,bad)
            (root/'outside').symlink_to(root.parent)
            with self.assertRaises(ValueError):weights.safe_path(root,'outside/file')

    def test_selection_is_explicit(self):
        m=json.loads((ROOT/'quantized-manifest.json').read_text())
        with self.assertRaises(ValueError):weights.select(m)
        exl=weights.select(m,'dealignai/DeepSeek-V4.1-Flash-UNCENSORED-EXL3-2.9bpw')
        self.assertEqual(len(exl['files']),39)
        self.assertEqual(len(weights.select(m,engram=True)['files']),2)
        exl=dict(exl,revision='main')
        with self.assertRaisesRegex(ValueError,'pinned'):weights.select(exl)


class Launcher(unittest.TestCase):
    def test_both_engines_and_spaces(self):
        for name,module in [('exl3-h200','vllm.entrypoints.openai.api_server'),('fp8-sglang','sglang.launch_server')]:
            p=subprocess.run(['bash',str(ROOT/'ops/run-model.sh'),str(ROOT/f'profiles/{name}.env.example'),'--dry-run'],capture_output=True,text=True,check=True)
            argv=shlex.split(p.stdout);self.assertIn(module,argv)
        with tempfile.TemporaryDirectory() as t:
            f=Path(t)/'profile.env'
            f.write_text('ENGINE=vllm\nPYTHON_BIN="/tmp/python with spaces"\nMODEL_PATH="/tmp/model with spaces"\nMODEL_ID=demo\nTP=1\nMAX_MODEL_LEN=4096\nEXTRA_ARGS=(--dtype bfloat16)\n')
            p=subprocess.run(['bash',str(ROOT/'ops/run-model.sh'),str(f),'--dry-run'],capture_output=True,text=True,check=True)
            argv=shlex.split(p.stdout)
            self.assertEqual(argv[0],'/tmp/python with spaces');self.assertIn('/tmp/model with spaces',argv)
            self.assertEqual(argv[-2:],['--dtype','bfloat16'])
            f.write_text(f.read_text().replace('TP=1','TP=0'))
            p=subprocess.run(['bash',str(ROOT/'ops/run-model.sh'),str(f),'--dry-run'],capture_output=True)
            self.assertNotEqual(p.returncode,0)

    def test_skill_profile_reproduces_measured_command(self):
        # The measured command has no quoted spaces, so a plain split is exact.
        ref=(ROOT/'reports/2026-09-23/fp8/serve-command.txt').read_text().splitlines()[0].split()
        p=subprocess.run(['bash',str(ROOT/'ops/run-model.sh'),str(ROOT/'skills/ds4-fp8-vllm/server-fp8.env.example'),'--dry-run'],capture_output=True,text=True,check=True)
        self.assertEqual(shlex.split(p.stdout),ref)
        # bench.sh stores the served command %q-quoted.
        ref=shlex.split((ROOT/'reports/2026-09-24/fp8/bench-20260924-fp8-tp8-dspark-seq32-1m/command.txt').read_text())
        p=subprocess.run(['bash',str(ROOT/'ops/run-model.sh'),str(ROOT/'skills/ds4-fp8-vllm/server-fp8-8gpu.env.example'),'--dry-run'],capture_output=True,text=True,check=True)
        self.assertEqual(shlex.split(p.stdout),ref)

    def test_incomplete_native_profile_rejected(self):
        p=subprocess.run(['bash',str(ROOT/'ops/run-model.sh'),str(ROOT/'profiles/native-vllm.env.example'),'--dry-run'],capture_output=True)
        self.assertNotEqual(p.returncode,0)

    def test_client_keeps_1m_mode_only_for_1m_window(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);binary=root/'cli';binary.write_text('#!/bin/bash\n');binary.chmod(0o755)
            for context,disabled in [(65536,True),(1048576,False)]:
                argv=[sys.executable,str(ROOT/'ops/configure-free-code.py'),'--binary',str(binary),'--profile',str(root/f'p{context}'),'--launcher',str(root/f'l{context}'),'--api-base','http://127.0.0.1:18083','--model','m','--context',str(context)]
                subprocess.run(argv,capture_output=True,check=True)
                env=json.loads((root/f'p{context}'/'settings.json').read_text())['env']
                self.assertEqual('CLAUDE_CODE_DISABLE_1M_CONTEXT' in env,disabled)
                self.assertEqual(env['CLAUDE_CODE_MAX_CONTEXT_TOKENS'],str(context))

    def test_generated_client_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='client with spaces ') as t:
            root=Path(t);binary=root/'fake cli';binary.write_text('#!/bin/bash\nprintf "%s\\n" "$ANTHROPIC_BASE_URL" "$CLAUDE_CONFIG_DIR" "$@"\n');binary.chmod(0o755)
            argv=[sys.executable,str(ROOT/'ops/configure-free-code.py'),'--binary',str(binary),'--profile',str(root/'profile'),'--launcher',str(root/'launch'),'--api-base','http://127.0.0.1:18081','--model','test-model','--context','65536']
            subprocess.run(argv,capture_output=True,check=True)
            p=subprocess.run([str(root/'launch'),'literal $HOME'],capture_output=True,text=True,check=True)
            self.assertEqual(p.stdout.splitlines(),['http://127.0.0.1:18081',str((root/'profile').resolve()),'literal $HOME'])
            self.assertNotEqual(subprocess.run(argv,capture_output=True).returncode,0)


class Adapter(unittest.TestCase):
    def test_pinned_patch_idempotency_and_version_guard(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);v=root/'vllm';v.mkdir();(v/'__init__.py').write_text('__version__="0.30.0"\n')
            n=v/'models/deepseek_v41/nvidia';n.mkdir(parents=True)
            (n/'engram.py').write_text('# NVIDIA class fixture\n')
            (n/'model.py').write_text('def init():\n        aux_stream_list = [torch.cuda.Stream() for _ in range(3)]\n')
            overlay=root/'overlay';overlay.mkdir()
            (overlay/'engram_file_backend.py').write_text('''import os, glob
def _load_cudart():
    paths = []
class Example:
    def __init__(
        self,
        cpu_offload: bool = False,
    ) -> None:
        del cpu_offload
        self.head_start = module.engram_head_shard_rank() * self.part_n_hash_cols
''')
            argv=[sys.executable,str(ROOT/'deploy/adapt-engram-v030.py'),'--overlay-dir',str(overlay)]
            env=dict(os.environ,PYTHONPATH=str(root))
            subprocess.run(argv,env=env,capture_output=True,check=True)
            targets=[overlay/'engram_file_backend.py',n/'engram.py',n/'model.py']
            before=[p.read_text() for p in targets]
            subprocess.run(argv,env=env,capture_output=True,check=True)
            self.assertEqual(before,[p.read_text() for p in targets])
            (v/'__init__.py').write_text('__version__="99.0.0-new-version"\n')
            self.assertNotEqual(subprocess.run(argv,env=env,capture_output=True).returncode,0)

    def test_fast_path_patch_guards(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);v=root/'vllm';v.mkdir();(v/'__init__.py').write_text('__version__="0.30.0"\n')
            spec=importlib.util.spec_from_file_location('fast_path',ROOT/'deploy/patch-fast-path.py')
            mod=importlib.util.module_from_spec(spec);saved=sys.modules.get('vllm')
            sys.modules['vllm']=type(sys)('vllm');sys.modules['vllm'].__version__='0.30.0'
            try:spec.loader.exec_module(mod)
            finally:
                if saved is None:del sys.modules['vllm']
                else:sys.modules['vllm']=saved
            fixtures={}
            for rel,_,edits in mod.EDITS:fixtures[rel]=fixtures.get(rel,'')+''.join(old for old,_ in edits)
            fixtures[mod.WORKER]='# fixture\nimport os\nimport time\nclass Worker(WorkerBase):\n    def determine_available_memory(self) -> int: ...\n    def compile_or_warm_up_model(self) -> None: ...\n'
            for rel,text in fixtures.items():(v/rel).parent.mkdir(parents=True,exist_ok=True);(v/rel).write_text(text)
            argv=[sys.executable,'-B',str(ROOT/'deploy/patch-fast-path.py')];env=dict(os.environ,PYTHONPATH=str(root))
            subprocess.run(argv,env=env,capture_output=True,check=True)
            once={rel:(v/rel).read_text() for rel in fixtures}
            for rel,marker,_ in mod.EDITS:self.assertIn(marker,once[rel])
            self.assertIn(mod.WORKER_MARK,once[mod.WORKER])
            subprocess.run(argv,env=env,capture_output=True,check=True)
            self.assertEqual(once,{rel:(v/rel).read_text() for rel in fixtures})
            for rel,text in fixtures.items():(v/rel).write_text(text)
            (v/mod.RUNNER).write_text(fixtures[mod.RUNNER].replace('assert len(result) == 2','assert len(result) == 3'))
            self.assertNotEqual(subprocess.run(argv,env=env,capture_output=True).returncode,0)
            self.assertEqual((v/mod.EXL3).read_text(),fixtures[mod.EXL3])
            (v/'__init__.py').write_text('__version__="99.0.0-new-version"\n')
            self.assertNotEqual(subprocess.run(argv,env=env,capture_output=True).returncode,0)

    def test_ui_preview_apply_idempotence(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);app=root/'model-ui';app.mkdir();launcher=root/'launch.sh'
            launcher.write_text(f'#!/bin/bash\n# No model = no UI\npty {app}/venv/bin/python {app}/app.py\n')
            (app/'app.js').write_text("const rd = delta.reasoning_content || '';\n")
            (app/'index.html').write_text('<input id="chat-max-tokens" min="1" max="16384" value="2048">')
            argv=[sys.executable,str(ROOT/'ops/configure-model-ui.py'),'--api-base','http://127.0.0.1:19999','--model','new-model','--app-dir',str(app),'--launcher',str(launcher)]
            files=[launcher,app/'app.js',app/'index.html'];before=[f.read_text() for f in files]
            subprocess.run(argv,capture_output=True,check=True)
            self.assertEqual(before,[f.read_text() for f in files])
            subprocess.run(argv+['--apply'],capture_output=True,check=True)
            first=[f.read_text() for f in files]
            subprocess.run(argv+['--apply'],capture_output=True,check=True)
            self.assertEqual(first,[f.read_text() for f in files])
            self.assertIn('delta.reasoning',first[1]);self.assertIn('max="4096"',first[2])


class FreeCodeSkill(unittest.TestCase):
    SKILL=ROOT/'skills/free-code-deepseek/scripts'

    def agent(self,*args):
        return subprocess.run([sys.executable,str(self.SKILL/'tunnel-agent.py'),*args],capture_output=True,text=True)

    def test_tunnel_agent_modes_and_no_overwrite(self):
        import plistlib
        with tempfile.TemporaryDirectory(prefix='tunnel dir ') as t:
            root=Path(t);script=root/'ssh-exec-tunnel.py';script.write_text('#\n')
            common=['--label','local.x-tunnel','--tunnel-script',str(script),'--local-port','18083','--ssh-target','u@h',
                    '--ssh-port','2222','--ssh-key','/k','--remote-port','18080','--log-dir',str(root/'logs')]
            self.assertNotEqual(self.agent('--mode','exec',*common,'--platform','launchd','--print').returncode,0)
            p=self.agent('--mode','exec',*common,'--remote-bridge','/srv/tcpbridge.py','--platform','launchd','--print')
            d=plistlib.loads(p.stdout.encode())
            self.assertEqual(d['ProgramArguments'][1:],[str(script.resolve()),'--local-port','18083','--ssh-target','u@h','--ssh-port','2222',
                             '--remote-bridge','/srv/tcpbridge.py','--remote-port','18080','--ssh-key','/k'])
            self.assertTrue(d['KeepAlive']);self.assertNotIn('EnvironmentVariables',d)
            d=plistlib.loads(self.agent('--mode','forward',*common,'--platform','launchd','--print').stdout.encode())
            self.assertEqual(d['ProgramArguments'],['/bin/bash',str(script.resolve())])
            self.assertEqual(d['EnvironmentVariables'],{'SSH_TARGET':'u@h','SSH_PORT':'2222','LOCAL_PORT':'18083','REMOTE_PORT':'18080','SSH_KEY':'/k'})
            # systemd cannot take the space in this temp path without escaping: refuse, do not guess.
            self.assertNotEqual(self.agent('--mode','forward',*common,'--platform','systemd','--print').returncode,0)
            for bad in [['--ssh-target','-oProxyCommand=x'],['--local-port','0'],['--label','a/b']]:
                argv=list(common);i=argv.index(bad[0]);argv[i+1]=bad[1]
                self.assertNotEqual(self.agent('--mode','forward',*argv,'--print').returncode,0,bad)
            out=root/'svc.plist'
            self.assertEqual(self.agent('--mode','forward',*common,'--platform','launchd','--out',str(out)).returncode,0)
            first=out.read_text()
            self.assertNotEqual(self.agent('--mode','forward',*common,'--platform','launchd','--out',str(out)).returncode,0)
            self.assertEqual(first,out.read_text())

    def test_systemd_unit(self):
        with tempfile.TemporaryDirectory() as t:
            script=Path(t)/'tunnel.sh';script.write_text('#\n')
            p=self.agent('--mode','forward','--platform','systemd','--label','x','--tunnel-script',str(script),
                         '--local-port','18081','--ssh-target','root@1.2.3.4','--ssh-port','40022','--remote-port','18080','--print')
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertIn('Environment="SSH_PORT=40022"',p.stdout);self.assertIn(f'ExecStart=/bin/bash {script.resolve()}',p.stdout)
            self.assertIn('Restart=always',p.stdout)

    def test_verify_summarize(self):
        spec=importlib.util.spec_from_file_location('fc_verify',self.SKILL/'verify.py')
        v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
        lines=[json.dumps({'type':'system','subtype':'init','model':'m','permissionMode':'bypassPermissions','claude_code_version':'2.1.251'}),
               'not json',
               json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':'x'},{'type':'tool_use','name':'Bash','input':{}}]}}),
               json.dumps({'type':'result','subtype':'success','is_error':True,'num_turns':2,'result':'r',
                           'permission_denials':[{'tool_name':'Write'}]})]
        s=v.summarize(lines)
        self.assertEqual((s['model'],s['permission_mode'],s['tools'],s['is_error'],s['denials'],s['turns']),
                         ('m','bypassPermissions',['Bash'],True,['Write'],2))
        self.assertIsNone(v.summarize([])['is_error'])


if __name__=='__main__':unittest.main()
