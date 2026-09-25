#!/usr/bin/env python3
"""Check actual OpenAI generation/SSE; optional bounded tool round trip."""
import argparse
import json
import os
import tempfile
import time
import urllib.request
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url',required=True,help='Includes /v1 or UI /api, no token in URL')
    p.add_argument('--model',required=True)
    p.add_argument('--token-env',help='Name of env var containing Bearer token; never print value')
    p.add_argument('--tools',action='store_true')
    p.add_argument('--no-thinking',action='store_true',help='Only for templates supporting enable_thinking')
    p.add_argument('--max-tokens',type=int,default=512)
    a=p.parse_args()
    if '?' in a.base_url or '@' in a.base_url: p.error('Use token-env, not credentials in URL')
    headers={'Content-Type':'application/json'}
    if a.token_env: headers['Authorization']='Bearer '+os.environ[a.token_env]
    base=a.base_url.rstrip('/')
    def request(path,body=None):
        return urllib.request.urlopen(urllib.request.Request(base+path,headers=headers,
            data=None if body is None else json.dumps(body).encode()),timeout=600)
    def payload(messages,**extra):
        body={'model':a.model,'messages':messages,'temperature':0,'max_tokens':a.max_tokens}
        if a.no_thinking: body['chat_template_kwargs']={'enable_thinking':False}
        body.update(extra)
        return body
    def chat(messages,**extra):
        with request('/chat/completions',payload(messages,**extra)) as r: return json.load(r)
    with request('/models') as r:
        assert a.model in [m['id'] for m in json.load(r)['data']], 'Wrong served model ID'
    start=time.monotonic()
    r=chat([{'role':'user','content':'What is 17 * 19? Reply with the integer only.'}])
    c=r['choices'][0]
    assert (c['message'].get('content') or '').strip()=='323' and c['finish_reason']=='stop',c
    print('PASS completed generation',round(time.monotonic()-start,2),'seconds',flush=True)
    answer=[];done=False;finish=None
    with request('/chat/completions',payload([{'role':'user','content':'Reply with exactly READY.'}],stream=True)) as r:
        for line in r:
            if not line.startswith(b'data: '): continue
            data=line[6:].strip()
            if data==b'[DONE]': done=True;break
            for c in json.loads(data).get('choices',[]):
                answer.append(c.get('delta',{}).get('content') or '')
                finish=c.get('finish_reason') or finish
    assert done and finish=='stop' and ''.join(answer).strip()=='READY',(done,finish,answer)
    print('PASS SSE',flush=True)
    if a.tools:
        with tempfile.TemporaryDirectory(prefix='model-smoke-') as folder:
            fixture=Path(folder)/'check.txt';fixture.write_text('WEBINAR-FILE-73921\n')
            tools=[{'type':'function','function':{'name':'read_check_file',
                'description':'Read the fixed check file','parameters':{'type':'object','properties':{},'additionalProperties':False}}}]
            messages=[{'role':'user','content':'Read the check file with the provided tool and return its contents.'}]
            r=chat(messages,tools=tools,tool_choice={'type':'function','function':{'name':'read_check_file'}})
            m=r['choices'][0]['message'];calls=m.get('tool_calls',[])
            assert len(calls)==1 and calls[0]['function']['name']=='read_check_file',m
            assert json.loads(calls[0]['function']['arguments'])=={}
            messages.append({'role':'assistant','content':m.get('content'),'tool_calls':calls})
            messages.append({'role':'tool','tool_call_id':calls[0]['id'],'content':fixture.read_text()})
            r=chat(messages,tools=tools,tool_choice='none');c=r['choices'][0]
            assert 'WEBINAR-FILE-73921' in (c['message'].get('content') or '') and c['finish_reason']=='stop'
        print('PASS real file tool round trip',flush=True)


if __name__=='__main__': main()
