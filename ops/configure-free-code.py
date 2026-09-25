#!/usr/bin/env python3
"""Create an isolated free-code profile for a local SSH-forwarded Anthropic endpoint."""
import argparse
import json
import shlex
from pathlib import Path
from urllib.parse import urlparse


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--profile',type=Path,required=True,help='New profile directory; never overwrites settings')
    p.add_argument('--launcher',type=Path,required=True)
    p.add_argument('--api-base',required=True,help='e.g. http://127.0.0.1:18081, without /v1')
    p.add_argument('--model',required=True)
    p.add_argument('--context',type=int,required=True)
    p.add_argument('--output-tokens',type=int,default=8192)
    p.add_argument('--effort',choices=['low','high','xhigh','max'],default='high')
    a=p.parse_args();url=urlparse(a.api_base)
    if url.hostname not in ['localhost','127.0.0.1','::1'] or url.scheme!='http' or url.path not in ['','/'] or url.query or url.username or url.fragment:
        p.error('This recipe uses loopback HTTP + SSH; API base has no path or credentials')
    if not 0<a.output_tokens<a.context: p.error('Output budget must be positive and smaller than context')
    binary=a.binary.expanduser().resolve();profile=a.profile.expanduser().resolve();launcher=a.launcher.expanduser().absolute()
    if not binary.is_file(): p.error('Compiled binary not found')
    if launcher.exists() or launcher.is_symlink() or (profile/'settings.json').exists(): p.error('Output already exists; inspect it and choose a new profile/launcher')
    env={'ANTHROPIC_BASE_URL':a.api_base.rstrip('/'),'ANTHROPIC_MODEL':a.model,
         'ANTHROPIC_API_KEY':'local-ssh-tunnel','ANTHROPIC_AUTH_TOKEN':'local-ssh-tunnel',
         'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC':'1','CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS':'1',
         'CLAUDE_CODE_MAX_CONTEXT_TOKENS':str(a.context),
         'CLAUDE_CODE_MAX_OUTPUT_TOKENS':str(a.output_tokens),'CLAUDE_CODE_EFFORT_LEVEL':a.effort,
         'ENABLE_TOOL_SEARCH':'false','FREE_CODE_LOGS_DISABLED':'1','FREE_CODE_LOGS_S3_DISABLED':'1',
         'CLAUDE_CODE_SUBAGENT_MODEL':a.model}
    # With a 1M server window the client must keep its 1M mode, or it caps itself lower.
    if a.context<1048576:env['CLAUDE_CODE_DISABLE_1M_CONTEXT']='1'
    for alias in ['FABLE','OPUS','SONNET','HAIKU']:env['ANTHROPIC_DEFAULT_'+alias+'_MODEL']=a.model
    profile.mkdir(parents=True,exist_ok=True,mode=0o700)
    (profile/'settings.json').write_text(json.dumps({'env':env,'model':a.model,'effortLevel':a.effort},indent=2)+'\n')
    launcher.parent.mkdir(parents=True,exist_ok=True)
    lines=['#!/bin/bash','set -euo pipefail',
           'unset CLAUDE_CODE_USE_OPENAI CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_VERTEX CLAUDE_CODE_USE_FOUNDRY',
           'unset CLAUDE_CODE_OAUTH_TOKEN CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR',
           'unset ANTHROPIC_UNIX_SOCKET ANTHROPIC_CUSTOM_HEADERS',
           'export CLAUDE_CONFIG_DIR='+shlex.quote(str(profile))]
    lines += ['export '+k+'='+shlex.quote(v) for k,v in env.items()]
    lines += ['exec '+shlex.quote(str(binary))+' "$@"']
    launcher.write_text('\n'.join(lines)+'\n');launcher.chmod(0o755)
    print('Profile and launcher created. Start the SSH tunnel, then run:',launcher)


if __name__=='__main__':main()
