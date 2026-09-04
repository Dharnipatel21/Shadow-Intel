"""SQLite persistence and local investigation services for ShadowIntel.

SQLite is the reliable default; Neo4j can be added behind the same graph API without
changing callers. All live API values are read from this store, never frontend state.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import hashlib, json, re, sqlite3, uuid
from collections import defaultdict
from difflib import SequenceMatcher
import networkx as nx
from .data import DATA, CASE
from .risk import enrich_anomalies

ROOT=Path(__file__).resolve().parents[1]; DATA_DIR=ROOT/'data'; EVIDENCE_DIR=DATA_DIR/'evidence'; DB=DATA_DIR/'shadowintel.db'
def now(): return datetime.now().isoformat(timespec='seconds')
def conn():
    DATA_DIR.mkdir(exist_ok=True); EVIDENCE_DIR.mkdir(exist_ok=True)
    c=sqlite3.connect(DB, timeout=10)
    c.execute('PRAGMA busy_timeout=10000')
    c.row_factory=sqlite3.Row
    return c
def _row(r): return dict(r) if r else None
def _loads(row, fields=('aliases','entities','audit')):
    d=dict(row)
    for f in fields:
        if f in d and d[f]: d[f]=json.loads(d[f])
    return d
CASE_COLUMNS = ('id','name','status','investigator','priority','stage','disclaimer','created_at','updated_at')
def _migrate_cases_table(c):
    """Add case-management columns to an already-existing cases table without losing data."""
    existing={row[1] for row in c.execute('PRAGMA table_info(cases)').fetchall()}
    additions={'investigator':"TEXT DEFAULT ''",'priority':"TEXT DEFAULT 'MEDIUM'",'stage':"TEXT DEFAULT 'EVIDENCE_INGESTION'",'created_at':"TEXT DEFAULT ''",'updated_at':"TEXT DEFAULT ''"}
    for column,ddl in additions.items():
        if column not in existing: c.execute(f'ALTER TABLE cases ADD COLUMN {column} {ddl}')
def init(force=False):
    if force and DB.exists(): DB.unlink()
    c=conn(); c.executescript('''
    CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY,name TEXT,status TEXT,disclaimer TEXT);
    CREATE TABLE IF NOT EXISTS entities(id TEXT PRIMARY KEY,label TEXT,type TEXT,aliases TEXT,confidence REAL,case_id TEXT,created_at TEXT);
    CREATE TABLE IF NOT EXISTS relationships(id TEXT PRIMARY KEY,source TEXT,target TEXT,type TEXT,timestamp TEXT,confidence REAL,evidence_id TEXT,provenance TEXT);
    CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY,source TEXT,document_type TEXT,created_at TEXT,hash TEXT,path TEXT,extracted_text TEXT,entities TEXT,audit TEXT,case_id TEXT,language TEXT DEFAULT 'English');
    CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,type TEXT,timestamp TEXT,title TEXT,entities TEXT,amount REAL,source TEXT,confidence REAL);
    CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,source TEXT,status TEXT,created_at TEXT,result TEXT,case_id TEXT);
    CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,created_at TEXT,content TEXT);
    CREATE TABLE IF NOT EXISTS assistant_messages(id TEXT PRIMARY KEY,case_id TEXT NOT NULL,question TEXT NOT NULL,answer TEXT NOT NULL,language TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS blackboard_items(
        id TEXT PRIMARY KEY,case_id TEXT NOT NULL,kind TEXT NOT NULL,ref_id TEXT,title TEXT NOT NULL,
        content TEXT,status TEXT,x REAL NOT NULL,y REAL NOT NULL,color TEXT,created_by TEXT,
        created_at TEXT NOT NULL,updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS blackboard_connections(
        id TEXT PRIMARY KEY,case_id TEXT NOT NULL,from_id TEXT NOT NULL,to_id TEXT NOT NULL,
        label TEXT,created_at TEXT NOT NULL
    );
    ''')
    _migrate_cases_table(c)
    for table in ('evidence', 'jobs'):
        columns={row[1] for row in c.execute(f'PRAGMA table_info({table})').fetchall()}
        if 'case_id' not in columns: c.execute(f'ALTER TABLE {table} ADD COLUMN case_id TEXT')
    evidence_columns={row[1] for row in c.execute('PRAGMA table_info(evidence)').fetchall()}
    if 'language' not in evidence_columns: c.execute("ALTER TABLE evidence ADD COLUMN language TEXT DEFAULT 'English'")
    c.execute('UPDATE evidence SET case_id=? WHERE case_id IS NULL', (CASE['id'],))
    c.execute('UPDATE jobs SET case_id=? WHERE case_id IS NULL', (CASE['id'],))
    c.commit()
    if c.execute('SELECT count(*) FROM cases').fetchone()[0]: c.close(); return
    c.execute('INSERT INTO cases(id,name,status,investigator,priority,stage,disclaimer,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
        (CASE['id'],CASE['name'],CASE['status'],CASE['investigator'],CASE['priority'],CASE['stage'],CASE['disclaimer'],now(),now()))
    for n in DATA['nodes']:
        c.execute('INSERT INTO entities VALUES(?,?,?,?,?,?,?)',(n['id'],n['label'],n['type'],json.dumps(n.get('aliases',[])),n.get('confidence',.8),CASE['id'],now()))
    for e in DATA['edges']:
        c.execute('INSERT INTO relationships VALUES(?,?,?,?,?,?,?,?)',(e['id'],e['source'],e['target'],e['type'],e['timestamp'],e['confidence'],e.get('evidence_id'), 'synthetic-generator'))
    for e in DATA['evidence']:
        text=e['preview']; path=EVIDENCE_DIR/f"{e['id']}.txt"; path.write_text(text,encoding='utf-8')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        c.execute('INSERT INTO evidence(id,source,document_type,created_at,hash,path,extracted_text,entities,audit,case_id,language) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(e['id'],e['source'],e['document_type'],e['created_at'],digest,str(path),text,json.dumps(e.get('entities',[])),json.dumps(e.get('audit',[])),CASE['id'],'English'))
    for e in DATA['events']:
        c.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?)',(e['id'],e['type'],e['timestamp'],e['title'],json.dumps(e['entities']),e.get('amount'),e['source'],e['confidence']))
    c.commit(); c.close()
def list_cases():
    """All cases with live entity/evidence/anomaly counts for the Case Management view."""
    cases=query('SELECT * FROM cases ORDER BY created_at DESC')
    for item in cases:
        item['entity_count']=one('SELECT count(*) AS n FROM entities WHERE case_id=?',item['id'])['n']
        item['evidence_count']=one('SELECT count(*) AS n FROM evidence WHERE case_id=?',item['id'])['n']
        entity_ids=[entity['id'] for entity in query('SELECT id FROM entities WHERE case_id=?',item['id'])]
        item['relationship_count']=one('SELECT count(*) AS n FROM relationships WHERE source IN ({}) OR target IN ({})'.format(','.join('?'*len(entity_ids)) or "''",','.join('?'*len(entity_ids)) or "''"), *(entity_ids + entity_ids))['n'] if entity_ids else 0
    return cases
def create_case(name,investigator='',priority='MEDIUM',stage='EVIDENCE_INGESTION',status='ACTIVE',disclaimer=None):
    cid='CASE-'+uuid.uuid4().hex[:8].upper()
    disclaimer=disclaimer or CASE['disclaimer']; timestamp=now()
    c=conn(); c.execute('INSERT INTO cases(id,name,status,investigator,priority,stage,disclaimer,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
        (cid,name,status,investigator,priority,stage,disclaimer,timestamp,timestamp)); c.commit(); c.close()
    return one('SELECT * FROM cases WHERE id=?',cid)
def update_case(case_id,**fields):
    existing=one('SELECT * FROM cases WHERE id=?',case_id)
    if not existing: return None
    allowed={k:v for k,v in fields.items() if v is not None and k in ('name','status','investigator','priority','stage')}
    if not allowed: return existing
    allowed['updated_at']=now()
    assignments=', '.join(f'{column}=?' for column in allowed)
    c=conn(); c.execute(f'UPDATE cases SET {assignments} WHERE id=?',(*allowed.values(),case_id)); c.commit(); c.close()
    return one('SELECT * FROM cases WHERE id=?',case_id)
def delete_case(case_id):
    remaining=one('SELECT count(*) AS n FROM cases')['n']
    if remaining<=1: return False
    c=conn(); c.execute('DELETE FROM cases WHERE id=?',(case_id,)); c.commit(); c.close()
    return True
def query(sql,*args):
    c=conn(); rows=c.execute(sql,args).fetchall(); c.close(); return [_loads(r) for r in rows]
def one(sql,*args):
    c=conn(); r=c.execute(sql,args).fetchone(); c.close(); return _loads(r) if r else None
def graph():
    nodes=query('SELECT * FROM entities'); edges=query('SELECT * FROM relationships')
    g=nx.Graph(); g.add_nodes_from(x['id'] for x in nodes); g.add_edges_from((x['source'],x['target']) for x in edges)
    degree=nx.degree_centrality(g) if len(g) else {}; between=nx.betweenness_centrality(g) if len(g) else {}; pagerank=nx.pagerank(g) if len(g) else {}
    groups=list(nx.community.greedy_modularity_communities(g)) if g.number_of_edges() else []
    community={node:i+1 for i,group in enumerate(groups) for node in group}; raw={n:.35*degree.get(n,0)+.35*between.get(n,0)+.3*pagerank.get(n,0) for n in g}; maximum=max(raw.values(),default=1)
    return g,{"degree":degree,"betweenness":between,"pagerank":pagerank,"community":community,"priority":{n:round(100*v/maximum,1) for n,v in raw.items()}}
def enrich(items):
    _,a=graph()
    return [dict(x,priority=a['priority'].get(x['id'],0),community=a['community'].get(x['id'],0),centrality=round(a['betweenness'].get(x['id'],0),4)) for x in items]
def entity_intelligence(items):
    """Rank existing entities from live graph, relationship, anomaly, and evidence records."""
    enriched=enrich(items); relationships=query('SELECT * FROM relationships'); evidence=query('SELECT * FROM evidence')
    connection_count=defaultdict(int); linked_evidence=defaultdict(set)
    for relationship in relationships:
        connection_count[relationship['source']]+=1; connection_count[relationship['target']]+=1
        if relationship.get('evidence_id'):
            linked_evidence[relationship['source']].add(relationship['evidence_id']); linked_evidence[relationship['target']].add(relationship['evidence_id'])
    for item in evidence:
        for entity_id in item.get('entities',[]): linked_evidence[entity_id].add(item['id'])
    risks=defaultdict(list)
    for alert in detect_anomalies():
        for entity_id in alert.get('entities',[]): risks[entity_id].append(alert)
    maximum_connections=max(connection_count.values(),default=1) or 1
    result=[]
    for entity in enriched:
        entity_id=entity['id']; connections=connection_count[entity_id]; risk_score=max((float(alert.get('hybrid_risk_score',alert.get('confidence',0)*100)) for alert in risks[entity_id]),default=0.0)
        influence=float(entity.get('priority',0)); importance=round(.55*influence+.25*(100*connections/maximum_connections)+.20*risk_score,1)
        reasons=[f"Influence score {influence:.1f} is calculated from the current NetworkX degree, betweenness, and PageRank signals.",f"{connections} observed relationship(s) connect this entity to the live case graph."]
        if risk_score: reasons.append(f"Highest linked anomaly risk score is {risk_score:.1f} from existing case indicators.")
        if linked_evidence[entity_id]: reasons.append(f"Linked to {len(linked_evidence[entity_id])} available evidence item(s).")
        result.append(dict(entity,connection_count=connections,influence_score=round(influence,1),risk_score=round(risk_score,1),importance_score=importance,importance_reasons=reasons,evidence_ids=sorted(linked_evidence[entity_id])))
    return sorted(result,key=lambda entity:entity['importance_score'],reverse=True)
def cross_source_correlations(entity_id):
    """Return only observed cross-type event pairs sharing or connecting entities."""
    relationships=query('SELECT * FROM relationships')
    relationship_by_pair={(edge['source'],edge['target']):edge for edge in relationships}
    relationship_by_pair.update({(edge['target'],edge['source']):edge for edge in relationships})
    scope={entity_id}
    scope.update(right for left,right in relationship_by_pair if left==entity_id)
    events=[event for event in query('SELECT * FROM events ORDER BY timestamp DESC') if set(event.get('entities',[])) & scope]
    entities={item['id']:item['label'] for item in query('SELECT id,label FROM entities')}
    result=[]; seen=set()
    for index,first in enumerate(events):
        for second in events[index+1:]:
            if first['type']==second['type']: continue
            shared=set(first['entities']) & set(second['entities'])
            bridge=next((relationship_by_pair.get((left,right)) for left in first['entities'] for right in second['entities'] if left!=right and relationship_by_pair.get((left,right))),None)
            if not shared and not bridge: continue
            event_ids=tuple(sorted((first['id'],second['id']))); bridge_id=bridge['id'] if bridge else None
            key=(event_ids,bridge_id)
            if key in seen: continue
            seen.add(key)
            involved=list(dict.fromkeys(first['entities']+second['entities']))
            evidence_ids=list(dict.fromkeys([value for value in [first.get('source'),second.get('source'),bridge.get('evidence_id') if bridge else None] if value]))
            result.append({'id':f"COR-{first['id']}-{second['id']}",'entities':[{'id':item,'label':entities.get(item,item)} for item in involved],'source_types':[first['type'],second['type']]+(['relationship'] if bridge else []),'records':[{'id':first['id'],'kind':'event','type':first['type'],'timestamp':first['timestamp']},{'id':second['id'],'kind':'event','type':second['type'],'timestamp':second['timestamp']}]+([{'id':bridge['id'],'kind':'relationship','type':bridge['type'],'timestamp':bridge['timestamp']}] if bridge else []),'evidence_ids':evidence_ids,'explanation':f"Observed {first['type'].lower()} record {first['id']} and {second['type'].lower()} record {second['id']} {'share entity ' + ', '.join(sorted(shared)) if shared else 'are connected by relationship ' + bridge['id']} ."})
            if len(result)>=30: return result
    return result
def resolve(label, kind='Person'):
    norm=lambda x: re.sub(r'[^a-z0-9]','',x.lower())
    target=norm(label); candidates=query('SELECT * FROM entities WHERE type=?',kind)
    for x in candidates:
        values=[x['label']]+x['aliases']
        score=max(SequenceMatcher(None,target,norm(v)).ratio() for v in values)
        if target in [norm(v) for v in values] or score>=.94: return x['id'],round(score,2)
    return None,0.0
FIR_NAME_STOPWORDS={
    'section','district','act','report','station','impression','diary','entry','item','case','fir','police','court','date','time','day','month','year','rank','crime','information','general','number','no','name','address','signature','place','complaint','complainant','accused','investigation','officer','sub','form','amount','account','mobile'
}
OCR_NOISE_WORDS={'tlme','cfennai','oistrict','ihc','hon','rankl','dayi','ltem','sectlon','pollce','statlon'}
DOCUMENT_HEADER_WORDS={'powered','criminal','network','intelligence','platform','product','vision','eight','core','pages','module','command','center','explorer','entity','risk','reports','recommended','technical','architecture','frontend','use','cytoscape','cypher','graph','data','science','supabase','storage','docker','model','demo','impact','open','visual','direction','requirements','build','built','strategy','claude','scaffold','relationship','finder','timeline','master','instruction','give','analysis','assistant','aura','pro','code','free','can','this','be'}
def _clean_name(candidate):
    words=candidate.replace('\n',' ').split()
    if len(words)<2 or any(not word.isalpha() or len(word)<2 for word in words): return None
    normalized=[word.lower() for word in words]
    if any(word in FIR_NAME_STOPWORDS or word in OCR_NOISE_WORDS or word in DOCUMENT_HEADER_WORDS for word in normalized): return None
    # OCR frequently creates title-cased fragments with confused l/I or malformed words.
    if any(re.search(r'(?:tlme|cfennai|oistrict|ihc|rankl)',word.lower()) or re.search(r'[a-z][A-Z]',word) for word in words): return None
    return ' '.join(words)
def _unique(values): return list(dict.fromkeys(values))
def extract(text):
    """Conservative FIR-aware deterministic extraction with OCR-noise rejection."""
    labeled=[]
    for line in text.splitlines():
        match=re.search(r'\b(?:name|complainant|accused)\s*:\s*(?:shri|smt)\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})|\b(?:name|complainant|accused)\s*:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})',line,re.I)
        if match:
            candidate=next(group for group in match.groups() if group)
            cleaned=_clean_name(candidate)
            if cleaned: labeled.append(cleaned)
        for honorific in re.findall(r'\b(?:Shri|Smt)\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})',line):
            cleaned=_clean_name(honorific)
            if cleaned: labeled.append(cleaned)
    names=_unique(labeled)
    phones=[]
    for match in re.finditer(r'(?<!\d)(?:\+91[\s-]?|91[\s-]?)?([6-9]\d(?:[\s-]?\d){8})(?!\d)',text):
        digits=re.sub(r'\D','',match.group(1)); phones.append('+91'+digits)
    accounts=[]
    account_pattern=r'(?i)\b(?:account(?:\s*(?:no\.?|number))?|a/c|acct(?:ount)?)\s*[:#-]?\s*([0-9][0-9\s-]{7,22}[0-9])'
    for match in re.finditer(account_pattern,text):
        digits=re.sub(r'\D','',match.group(1))
        if 9<=len(digits)<=18: accounts.append(digits)
    vehicles=re.findall(r'\b[A-Z]{2}\s?\d{2}\s?[A-Z]{1,3}\s?\d{3,4}\b',text)
    amounts=[]
    for match in re.finditer(r'(?i)(?:₹|INR\s*|Rs\.?\s*)((?:[1-9]\d{0,2}(?:,\d{2,3})+)|(?:[1-9]\d{2,}))(?:\.\d{1,2})?',text):
        amount=match.group(0).strip()
        if len(re.sub(r'\D','',match.group(1)))>=3: amounts.append(amount)
    typed_entities=(
        [{"value":name,"type":"PERSON"} for name in names]
        + [{"value":phone,"type":"PHONE"} for phone in _unique(phones)]
        + [{"value":account,"type":"ACCOUNT"} for account in _unique(accounts)]
    )
    return {"typed_entities":typed_entities,"names":names,"phones":_unique(phones),"accounts":_unique(accounts),"vehicles":_unique(vehicles),"amounts":_unique(amounts)}
def next_id(prefix, table):
    ids=query(f"SELECT id FROM {table} WHERE id LIKE ?",prefix+'%')
    highest=max((int(row['id'].rsplit('-',1)[-1]) for row in ids if row['id'].rsplit('-',1)[-1].isdigit()),default=0)
    return f"{prefix}{highest+1:03}"
def add_upload(filename, raw, text, document_type='Uploaded document', extraction_method='plain text', extracted=None, structured_extraction=None, warnings=None, case_id=CASE['id'], language='English'):
    c=conn()
    try:
        if not one('SELECT id FROM cases WHERE id=?', case_id): raise ValueError('Case not found')
        evidence_id=next_id('E-', 'evidence'); job_id=str(uuid.uuid4()); path=EVIDENCE_DIR/f'{evidence_id}_{Path(filename).name}'; path.write_bytes(raw)
        digest=hashlib.sha256(raw).hexdigest(); extracted=extracted or extract(text); ids=[]; resolutions=[]
        person_names=[item['value'] for item in extracted.get('typed_entities',[]) if item.get('type')=='PERSON']
        for label in person_names:
            eid,score=resolve(label)
            if not eid:
                eid=next_id('P-','entities'); c.execute('INSERT INTO entities VALUES(?,?,?,?,?,?,?)',(eid,label,'Person','[]',.78,case_id,now())); c.commit()
            ids.append(eid); resolutions.append({"mention":label,"entity_id":eid,"confidence":score or .78})
        for label,typ,prefix in [(x,'Phone','PH-') for x in extracted['phones']]+[(x,'BankAccount','BA-') for x in extracted['accounts']]+[(x,'Vehicle','V-') for x in extracted['vehicles']]:
            eid,score=resolve(label,typ)
            if not eid:
                eid=next_id(prefix,'entities'); c.execute('INSERT INTO entities VALUES(?,?,?,?,?,?,?)',(eid,label,typ,'[]',.99,case_id,now())); c.commit()
            ids.append(eid); resolutions.append({"mention":label,"entity_id":eid,"confidence":score or .99})
        doc=next_id('DOC-','entities'); c.execute('INSERT INTO entities VALUES(?,?,?,?,?,?,?)',(doc,filename,'Document','[]',1,case_id,now())); c.commit()
        c.execute('INSERT INTO evidence(id,source,document_type,created_at,hash,path,extracted_text,entities,audit,case_id,language) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(evidence_id,filename,document_type,now(),digest,str(path),text,json.dumps(ids),json.dumps(['uploaded','text extracted','entities resolved',f'language detected: {language}']),case_id,language))
        rels=0
        for eid in set(ids):
            rid=next_id('R-','relationships'); c.execute('INSERT INTO relationships VALUES(?,?,?,?,?,?,?,?)',(rid,eid,doc,'MENTIONED_IN',now(),.84,evidence_id,'upload extraction')); c.commit(); rels+=1
        if len(ids)>1:
            rid=next_id('R-','relationships'); c.execute('INSERT INTO relationships VALUES(?,?,?,?,?,?,?,?)',(rid,ids[0],ids[1],'ASSOCIATED_WITH',now(),.65,evidence_id,'co-mentioned uploaded document')); c.commit(); rels+=1
        event_id=next_id('EV-U-','events'); c.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?)',(event_id,'Document',now(),f'Uploaded and extracted: {filename}',json.dumps(ids+[doc]),None,evidence_id,.9))
        result_extraction=dict(structured_extraction or extracted)
        result_extraction.pop('names',None)
        result={"job_id":job_id,"source":filename,"status":"completed","extraction_method":extraction_method,"records_processed":max(1,len(text.splitlines())),"entities_extracted":len(ids),"relationships_created":rels,"events_created":1,"validation_errors":[],"warnings":warnings or [],"extraction":result_extraction,"text_snippet":text[:500],"resolutions":resolutions,"evidence_id":evidence_id,"duration_ms":0}
        c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)',(job_id,filename,'completed',now(),json.dumps(result),case_id)); c.commit(); return result
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
def detect_anomalies(case_id=None):
    if case_id:
        events=query('SELECT events.* FROM events LEFT JOIN evidence ON evidence.id=events.source WHERE evidence.case_id=? OR (evidence.id IS NULL AND ?=?) ORDER BY events.timestamp', case_id, case_id, CASE['id'])
    else:
        events=query('SELECT * FROM events ORDER BY timestamp')
    out=[]
    tx=[x for x in events if x['type']=='Transaction' and x.get('amount')]
    if tx:
        threshold=sorted(x['amount'] for x in tx)[max(0,int(len(tx)*.95)-1)]
        for x in tx:
            if x['amount']>=threshold: out.append({"id":'AN-T-'+x['id'],"type":"Unusual transaction amount","severity":"HIGH","confidence":.87,"timestamp":x['timestamp'],"entities":x['entities'],"explanation":f"Transfer of INR {x['amount']:,.0f} is in the top 5% of recorded transaction amounts.","evidence":[x['source']]})
    calls=[x for x in events if x['type']=='Call']; buckets={}
    for x in calls: buckets.setdefault(x['timestamp'][:10],[]).append(x)
    if buckets:
        day,items=max(buckets.items(),key=lambda z:len(z[1])); baseline=sum(map(len,buckets.values()))/len(buckets)
        if len(items)>baseline*1.25: out.append({"id":'AN-C-'+day,"type":"Communication burst","severity":"MEDIUM","confidence":.82,"timestamp":items[0]['timestamp'],"entities":list(dict.fromkeys(sum((x['entities'] for x in items),[])))[:8],"explanation":f"{len(items)} communication records on {day}, above the daily baseline of {baseline:.1f}.","evidence":list(dict.fromkeys(x['source'] for x in items))[:5]})
    locations={}
    for x in events:
        if x['type']=='Location' and len(x['entities'])>1: locations.setdefault((x['timestamp'][:10],x['entities'][-1]),[]).append(x)
    for (day,loc),items in locations.items():
        people=list(dict.fromkeys(x['entities'][0] for x in items))
        if len(people)>1: out.append({"id":'AN-L-'+day+loc,"type":"Location overlap","severity":"MEDIUM","confidence":.8,"timestamp":items[0]['timestamp'],"entities":people+[loc],"explanation":f"{len(people)} entities have observed activity at {loc} on {day}.","evidence":list(dict.fromkeys(x['source'] for x in items))})
    risk_graph, analytics=graph()
    return enrich_anomalies(out[:30], risk_graph, analytics)
def _ensure_blackboard_schema():
    """Keep the optional case-board migration safe for databases created before it existed."""
    c=conn()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS blackboard_items(
        id TEXT PRIMARY KEY,case_id TEXT NOT NULL,kind TEXT NOT NULL,ref_id TEXT,title TEXT NOT NULL,
        content TEXT,status TEXT,x REAL NOT NULL,y REAL NOT NULL,color TEXT,created_by TEXT,
        created_at TEXT NOT NULL,updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS blackboard_connections(
        id TEXT PRIMARY KEY,case_id TEXT NOT NULL,from_id TEXT NOT NULL,to_id TEXT NOT NULL,
        label TEXT,created_at TEXT NOT NULL
    );
    ''')
    c.commit(); c.close()
def retrieve(question, case_id=CASE['id']):
    # Keep Unicode words intact so retrieval works for every supported script.
    tokens={x.casefold() for x in re.findall(r'[\w-]{2,}',question,flags=re.UNICODE)}
    evidence=query('SELECT * FROM evidence') if case_id in (None, '', 'ALL_CASES') else query('SELECT * FROM evidence WHERE case_id=?', case_id)
    scored=[]
    for e in evidence:
        corpus=(e['source']+' '+e['extracted_text']).casefold(); score=sum(t in corpus for t in tokens)
        if score: scored.append((score,e))
    return [e for _,e in sorted(scored,key=lambda x:x[0],reverse=True)[:6]]
def list_blackboard(case_id):
    """Live corkboard for a case: pinned entities/evidence, notes, and hypotheses plus the strings connecting them."""
    _ensure_blackboard_schema()
    items=query('SELECT * FROM blackboard_items WHERE case_id=? ORDER BY created_at', case_id)
    connections=query('SELECT * FROM blackboard_connections WHERE case_id=? ORDER BY created_at', case_id)
    return {'items':items,'connections':connections}
def add_blackboard_item(case_id, kind, title, content='', ref_id=None, status='', x=40.0, y=40.0, color='amber', created_by=''):
    if not one('SELECT id FROM cases WHERE id=?', case_id): raise ValueError('Case not found')
    item_id=next_id('BB-','blackboard_items'); timestamp=now()
    c=conn(); c.execute('INSERT INTO blackboard_items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (item_id,case_id,kind,ref_id,title,content,status,x,y,color,created_by,timestamp,timestamp)); c.commit(); c.close()
    return one('SELECT * FROM blackboard_items WHERE id=?', item_id)
def update_blackboard_item(item_id, **fields):
    existing=one('SELECT * FROM blackboard_items WHERE id=?', item_id)
    if not existing: return None
    allowed={k:v for k,v in fields.items() if v is not None and k in ('title','content','status','x','y','color')}
    if not allowed: return existing
    allowed['updated_at']=now()
    assignments=', '.join(f'{column}=?' for column in allowed)
    c=conn(); c.execute(f'UPDATE blackboard_items SET {assignments} WHERE id=?', (*allowed.values(), item_id)); c.commit(); c.close()
    return one('SELECT * FROM blackboard_items WHERE id=?', item_id)
def delete_blackboard_item(item_id):
    if not one('SELECT id FROM blackboard_items WHERE id=?', item_id): return False
    c=conn()
    c.execute('DELETE FROM blackboard_connections WHERE from_id=? OR to_id=?', (item_id, item_id))
    c.execute('DELETE FROM blackboard_items WHERE id=?', (item_id,))
    c.commit(); c.close()
    return True
def add_blackboard_connection(case_id, from_id, to_id, label=''):
    if not one('SELECT id FROM blackboard_items WHERE id=? AND case_id=?', from_id, case_id): raise ValueError('Source card not found in this case')
    if not one('SELECT id FROM blackboard_items WHERE id=? AND case_id=?', to_id, case_id): raise ValueError('Target card not found in this case')
    connection_id=next_id('BC-','blackboard_connections'); timestamp=now()
    c=conn(); c.execute('INSERT INTO blackboard_connections VALUES(?,?,?,?,?,?)', (connection_id,case_id,from_id,to_id,label,timestamp)); c.commit(); c.close()
    return one('SELECT * FROM blackboard_connections WHERE id=?', connection_id)
def delete_blackboard_connection(connection_id):
    if not one('SELECT id FROM blackboard_connections WHERE id=?', connection_id): return False
    c=conn(); c.execute('DELETE FROM blackboard_connections WHERE id=?', (connection_id,)); c.commit(); c.close()
    return True

def add_assistant_message(case_id, question, answer, language):
    if case_id != 'ALL_CASES' and not one('SELECT id FROM cases WHERE id=?', case_id): raise ValueError('Case not found')
    message_id=next_id('CHAT-', 'assistant_messages'); timestamp=now()
    c=conn(); c.execute('INSERT INTO assistant_messages VALUES(?,?,?,?,?,?)', (message_id,case_id,question,json.dumps(answer),language,timestamp)); c.commit(); c.close()
    return one('SELECT * FROM assistant_messages WHERE id=?', message_id)

def list_assistant_messages(case_id):
    items=query('SELECT * FROM assistant_messages ORDER BY created_at ASC') if case_id in (None, '', 'ALL_CASES') else query('SELECT * FROM assistant_messages WHERE case_id=? ORDER BY created_at ASC', case_id)
    for item in items: item['answer']=json.loads(item['answer'])
    return items
