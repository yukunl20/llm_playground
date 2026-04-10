from agent import run_parse_metrics
r22 = run_parse_metrics('LRCX', 2022)
r23 = run_parse_metrics('LRCX', 2023)
for m in r22['metrics']:
    if m['label'] == 'revenue': print('2022', m)
for m in r23['metrics']:
    if m['label'] == 'revenue': print('2023', m)