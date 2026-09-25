"""Point the stock Vast Model UI at EXL3; keep Caddy authentication and ports."""
from pathlib import Path
p=Path('/opt/supervisor-scripts/model-ui.sh')
s=p.read_text()
anchor='pty /opt/model-ui/venv/bin/python /opt/model-ui/app.py'
settings='''export MODEL_UI_API_BASE=http://127.0.0.1:18080
export MODEL_NAME=deepseek-v4.1-flash
export MODEL_UI_DEFAULT_TAB=chat
export MODEL_UI_CHAT_CAPS=all
unset MODEL_UI_IMAGE_CAPS MODEL_UI_VIDEO_CAPS MODEL_UI_TTS_CAPS MODEL_UI_STT_CAPS MODEL_UI_PROMPT_WRAPPER
'''
if settings not in s:
    assert s.count(anchor)==1
    p.write_text(s.replace(anchor,settings+anchor))
p=Path('/opt/model-ui/app.js');s=p.read_text()
old="const rd = delta.reasoning_content || '';"
new="const rd = delta.reasoning_content || delta.reasoning || '';"
assert s.count(old)==1 or new in s
p.write_text(s.replace(old,new))
p=Path('/opt/model-ui/index.html');s=p.read_text()
old='id="chat-max-tokens" min="1" max="16384"'
new='id="chat-max-tokens" min="1" max="4096"'
assert s.count(old)==1 or new in s
p.write_text(s.replace(old,new))
print('Configured Model UI; run supervisorctl restart model-ui')
