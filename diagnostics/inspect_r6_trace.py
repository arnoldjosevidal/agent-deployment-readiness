import json,sqlite3,sys
c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True)
for run in ('adr24-7262156a3ea7-d-a','adr24-7262156a3ea7-d-g'):
 print('\nRUN',run)
 rows=c.execute('SELECT seq,event FROM event_journal WHERE run_id=? ORDER BY seq',(run,)).fetchall()
 for seq,raw in rows:
  e=json.loads(raw.decode() if isinstance(raw,bytes) else raw)
  kind=e.get('type'); tool=e.get('tool')
  if kind in {'model_request','model_result','request','decision','execution_start','result','error','evaluation_result','episode_end'}:
   item={k:e.get(k) for k in ('type','event_id','parent_id','call_id','tool','decision','success','utility','error','response','result_redacted','normalized_arguments','untrusted_content_exposed','untrusted_surface','final_response_sha256') if k in e}
   print(seq,json.dumps(item,ensure_ascii=False)[:1200])
