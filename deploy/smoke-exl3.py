"""Exercise real EXL3 generation, SSE, and a bounded file-reading tool round trip."""
import json
import sys
import time
import urllib.request
from pathlib import Path

base = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:18080').rstrip('/')
def call(path, payload=None):
    req = urllib.request.Request(base + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)
def chat(messages, **kwargs):
    p={'model':'deepseek-v4.1-flash','messages':messages,'max_tokens':256,
       'temperature':0,'chat_template_kwargs':{'enable_thinking':False}}
    p.update(kwargs)
    return call('/v1/chat/completions', p)
start=time.monotonic()
models=call('/v1/models')
assert 'deepseek-v4.1-flash' in [m['id'] for m in models['data']]
r=chat([{'role':'user','content':'What is 17 * 19? Reply with the integer only.'}])
c=r['choices'][0]
assert (c['message'].get('content') or '').strip()=='323',c
assert c['finish_reason']=='stop',c
print('PASS arithmetic',json.dumps(r.get('usage')), 'elapsed_s',round(time.monotonic()-start,2),flush=True)
p={'model':'deepseek-v4.1-flash','messages':[{'role':'user','content':'Reply with exactly READY.'}],
   'max_tokens':32,'temperature':0,'stream':True,'chat_template_kwargs':{'enable_thinking':False}}
req=urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(p).encode(),headers={'Content-Type':'application/json'})
parts=[];done=False
with urllib.request.urlopen(req,timeout=600) as response:
    for line in response:
        if not line.startswith(b'data: '):continue
        data=line[6:].strip()
        if data==b'[DONE]':done=True;break
        d=json.loads(data)
        for choice in d.get('choices',[]):parts.append(choice.get('delta',{}).get('content') or '')
assert done and ''.join(parts).strip()=='READY',(done,parts)
print('PASS streaming + DONE',flush=True)
fixture=Path('/tmp/ds41-webinar-check.txt')
marker='WEBINAR-EXL3-73921'
fixture.write_text(marker+'\n')
tools=[{'type':'function','function':{'name':'read_webinar_file','description':'Read the webinar check file.',
        'parameters':{'type':'object','properties':{},'additionalProperties':False}}}]
messages=[{'role':'user','content':'Read the webinar check file using the tool. Return its contents exactly.'}]
r=chat(messages,tools=tools,tool_choice={'type':'function','function':{'name':'read_webinar_file'}})
m=r['choices'][0]['message'];calls=m.get('tool_calls') or []
assert len(calls)==1,m
f=calls[0]['function'];assert f['name']=='read_webinar_file' and json.loads(f['arguments'])=={},f
messages.append({'role':'assistant','content':m.get('content'),'tool_calls':calls})
messages.append({'role':'tool','tool_call_id':calls[0]['id'],'content':fixture.read_text()})
r=chat(messages,tools=tools,tool_choice='none')
assert marker in (r['choices'][0]['message'].get('content') or ''),r
assert r['choices'][0]['finish_reason']=='stop',r
print('PASS file tool round trip',flush=True)
print('PASS all smoke checks',flush=True)
