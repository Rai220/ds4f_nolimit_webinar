#!/usr/bin/env python3
"""Adapt the inspected Vast Model UI layout. Preview by default; --apply writes files."""
import argparse
import re
import shlex
from pathlib import Path
from urllib.parse import urlparse


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--api-base',required=True,help='Backend root, without /v1')
    p.add_argument('--model',required=True)
    p.add_argument('--app-dir',type=Path,default=Path('/opt/model-ui'))
    p.add_argument('--launcher',type=Path,default=Path('/opt/supervisor-scripts/model-ui.sh'))
    p.add_argument('--max-output',type=int,default=4096)
    p.add_argument('--apply',action='store_true')
    a=p.parse_args();u=urlparse(a.api_base)
    if u.scheme not in ['http','https'] or not u.hostname or u.path not in ['','/'] or u.query or u.username or u.fragment:
        p.error('API base must be a root URL with no credentials')
    if a.max_output<2048:p.error('At least 2048 to preserve the stock default slider value')
    launcher=a.launcher.read_text();anchor=f'pty {a.app_dir}/venv/bin/python {a.app_dir}/app.py'
    if launcher.count(anchor)!=1: p.error('Launcher layout changed; inspect manually')
    start='# BEGIN model-backend-config';end='# END model-backend-config'
    if start in launcher:
        if launcher.count(start)!=1 or launcher.count(end)!=1:p.error('Ambiguous existing config')
        launcher=re.sub(re.escape(start)+r'.*?'+re.escape(end)+'\n\n?','',launcher,flags=re.S)
    # Replace only the known prior configuration from this deployment kit.
    previous='''export MODEL_UI_API_BASE=http://127.0.0.1:18080
export MODEL_NAME=deepseek-v4.1-flash
export MODEL_UI_DEFAULT_TAB=chat
export MODEL_UI_CHAT_CAPS=all
unset MODEL_UI_IMAGE_CAPS MODEL_UI_VIDEO_CAPS MODEL_UI_TTS_CAPS MODEL_UI_STT_CAPS MODEL_UI_PROMPT_WRAPPER
'''
    launcher=launcher.replace(previous,'')
    config=start+'\nexport MODEL_UI_API_BASE='+shlex.quote(a.api_base.rstrip('/'))+'\nexport MODEL_NAME='+shlex.quote(a.model)+'''\nexport MODEL_UI_DEFAULT_TAB=chat
export MODEL_UI_CHAT_CAPS=all
unset MODEL_UI_IMAGE_CAPS MODEL_UI_VIDEO_CAPS MODEL_UI_TTS_CAPS MODEL_UI_STT_CAPS MODEL_UI_PROMPT_WRAPPER
'''+end+'\n'
    # Place after environment loading but before the initial MODEL_NAME check.
    marker='# No model = no UI'
    if launcher.count(marker)!=1:p.error('Missing model guard; inspect launcher manually')
    launcher=launcher.replace(marker,config+'\n'+marker)
    jsfile=a.app_dir/'app.js';js=jsfile.read_text()
    old="const rd = delta.reasoning_content || '';";new="const rd = delta.reasoning_content || delta.reasoning || '';"
    if old not in js and new not in js:p.error('Reasoning renderer changed; inspect manually')
    js=js.replace(old,new)
    htmlfile=a.app_dir/'index.html';html=htmlfile.read_text()
    html,count=re.subn(r'(id="chat-max-tokens" min="1" max=")\d+(" )',lambda m:m[1]+str(a.max_output)+m[2],html)
    if count!=1:p.error('Token slider layout changed; inspect manually')
    for file,body in [(a.launcher,launcher),(jsfile,js),(htmlfile,html)]:
        print(('Write' if a.apply else 'Preview'),file)
        if a.apply:file.write_text(body)
    print('Caddy/auth/ports untouched. After applying: supervisorctl restart model-ui')


if __name__=='__main__':main()
