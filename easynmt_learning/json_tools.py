import json, re

def extract_json(text):
    value=(text or '').strip()
    value=re.sub(r'^```(?:json)?\s*','',value,flags=re.I)
    value=re.sub(r'\s*```$','',value)
    try:return json.loads(value)
    except json.JSONDecodeError:
        for start in [i for i,c in enumerate(value) if c in '[{']:
            for end in range(len(value),start,-1):
                try:return json.loads(value[start:end])
                except json.JSONDecodeError:pass
    raise ValueError('AI returned invalid JSON')
