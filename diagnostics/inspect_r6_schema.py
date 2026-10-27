import sqlite3,sys
c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True)
for name,sql in c.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"):
 print(name, sql)
