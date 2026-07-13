import json, django, os, sys
os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
django.setup()
from apps.agent.models import AgentTask

t = AgentTask.objects.get(id=12)
sr = t.step_results or {}
im = sr.get('interface_matching', {})
print('=== interface_matching stage ===')
print('status:', im.get('status'))
output = im.get('output', {})
print('match_count:', output.get('match_count'))
matches = output.get('matches', [])
for m in matches:
    print(f'  step {m.get("step_index")}: selected_id={m.get("selected_interface_id")} conf={m.get("confidence")} reason={m.get("reason","")[:100]}')
    iface = m.get('selected_interface') or {}
    if iface:
        print(f'    -> [{iface.get("method","")}] {iface.get("name","")}')

# Also check the LLM trace from result
r = t.result or {}
trace = r.get('llm_trace', {})
im_trace = trace.get('interface_matching', {})
print('\n=== interface_matching LLM trace ===')
print('provider:', im_trace.get('provider'))
print('model:', im_trace.get('model'))

# Check candidates_by_step
cbs = r.get('candidates_by_step', [])
print(f'\n=== candidates_by_step: {len(cbs)} items ===')
for item in cbs:
    cands = item.get('candidates', [])
    print(f'  step_index={item.get("step_index")} step_text={item.get("step_text","")[:40]} candidates={len(cands)}')
    for c in cands[:3]:
        print(f'    id={c.get("interface_id")} name={c.get("name","")[:30]} pre_score={c.get("pre_score",0):.4f}')
