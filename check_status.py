import urllib.request, json

req = urllib.request.Request('http://localhost:8000/api/auth/login/',
    data=json.dumps({'username':'admin','password':'admin123'}).encode(),
    headers={'Content-Type':'application/json'})
token = json.loads(urllib.request.urlopen(req).read())['access']

req2 = urllib.request.Request(
    'http://localhost:8000/api/agent/plan/d99820df-549c-4526-a611-72248ae3064b/status/',
    headers={'Authorization': f'Bearer {token}'})
d = json.loads(urllib.request.urlopen(req2).read())

print('Status:', d.get('status'))
print('Progress:', d.get('progress'), '%')
print('Step:', d.get('current_step'))
print('Error:', d.get('error_message') or 'None')
print('Started:', d.get('started_at','')[:19])
print('Finished:', d.get('finished_at','')[:19])

r = d.get('result') or {}
steps = r.get('steps', [])
if steps:
    print(f'\nPlan: {len(steps)} steps')
    for s in steps:
        iface = s.get('selected_interface') or {}
        name = iface.get('name', 'N/A')
        method = iface.get('method', '')
        print(f'  Step {s.get("step_index")}: {s.get("resolved_text","")} -> [{method}] {name}')
    chains = r.get('chains') or []
    if chains:
        print(f'\nChains: {len(chains)}')
        for i, c in enumerate(chains):
            print(f'  Chain {i+1}: {c.get("goal","")}')
            for step in c.get('steps', []):
                print(f'    - [{step.get("method","")}] {step.get("url","")}')
