import json,sqlite3,sys
c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True)
for run in ('adr24-7262156a3ea7-d-a','adr24-7262156a3ea7-d-g'):
 print('\nRUN',run)
 for seq,raw in c.execute('SELECT seq,event FROM event_journal WHERE run_id=? AND seq>=9 ORDER BY seq',(run,)):
  e=json.loads(raw.decode() if isinstance(raw,bytes) else raw)
  print(seq,json.dumps(e,ensure_ascii=False)[:3500])
