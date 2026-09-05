"""Deterministic, entirely fictional Operation ShadowLink demo data."""
from __future__ import annotations
from datetime import datetime, timedelta
import hashlib, random
import networkx as nx

CASE = {
    "id": "CASE-SL-01",
    "name": "Operation ShadowLink",
    "status": "ACTIVE",
    "investigator": "Investigator A. Menon",
    "priority": "HIGH",
    "stage": "RELATIONSHIP_ANALYSIS",
    "disclaimer": "ShadowIntel assists investigation and evidence analysis. It does not determine guilt, criminality, or legal responsibility.",
}
CASE_STATUSES = ["ACTIVE", "ON_HOLD", "PENDING_REVIEW", "CLOSED", "ARCHIVED"]
CASE_STAGES = ["EVIDENCE_INGESTION", "ENTITY_EXTRACTION", "RELATIONSHIP_ANALYSIS", "RISK_DETECTION", "INVESTIGATOR_REVIEW", "REPORT_GENERATION"]
CASE_PRIORITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
RNG = random.Random(42)
FIRST = ["Aarav","Meera","Kabir","Isha","Rohan","Nila","Vikram","Tara","Dev","Anaya","Rehan","Maya"]
LAST = ["Sen","Kapoor","Iyer","Malik","Das","Rao","Bose","Khan","Shah","Nair"]
LOCATIONS=["Harbor Gate","Cedar Market","North Station","Riverpoint","Atlas Warehouse","Old Mill","Linden Park","East Terminal","Meridian Hotel","Quarry Road","West Plaza","Canal Yard","Aurora Cafe","Summit Tower","South Depot"]

def stamp(i): return (datetime(2026,7,1,8)+timedelta(hours=i*3)).isoformat()

def build():
 people=[]; phones=[]; accounts=[]; orgs=[]; evidence=[]; events=[]; edges=[]
 for i in range(60):
  name=f"{FIRST[i%len(FIRST)]} {LAST[(i*3)%len(LAST)]}"
  people.append({"id":f"P-{i+1:03}","label":name,"type":"Person","aliases":[name.split()[0].lower()+str(i+1)] if i%9==0 else [],"confidence":round(.83+(i%17)/100,2),"case_id":CASE['id']})
 for i in range(30): phones.append({"id":f"PH-{i+1:03}","label":f"+91 555 {100000+i:06}","type":"Phone","confidence":.99})
 for i in range(20): accounts.append({"id":f"BA-{i+1:03}","label":f"ACCT-{470000+i}","type":"BankAccount","confidence":.99})
 for i in range(10): orgs.append({"id":f"ORG-{i+1:02}","label":f"{['Northstar','Cedar','Atlas','Meridian','Aurora'][i%5]} {['Logistics','Trading'][i%2]}","type":"Organization","confidence":.92})
 locations=[{"id":f"L-{i+1:02}","label":x,"type":"Location","confidence":.95} for i,x in enumerate(LOCATIONS)]
 nodes=people+phones+accounts+orgs+locations
 def edge(a,b,t,idx,conf=.86,eid=None): edges.append({"id":f"R-{len(edges)+1:04}","source":a,"target":b,"type":t,"timestamp":stamp(idx),"confidence":conf,"evidence_id":eid or f"E-{idx%26+1:03}"})
 # ownership / employment
 for i in range(30): edge(people[i]['id'],phones[i]['id'],"OWNS",i,.99)
 for i in range(20): edge(people[i+5]['id'],accounts[i]['id'],"OWNS",i+30,.99)
 for i in range(50): edge(people[i]['id'],orgs[i%10]['id'],"WORKS_FOR",i+50,.82)
 # Communities, normal calls and cross-community bridge P-017 discovered via structure
 for i in range(330):
  group=(i//110)*20; a=group+(i*7)%20; b=group+(i*11+3)%20
  if a==b: b=(b+1)%60
  edge(phones[a%30]['id'],phones[b%30]['id'],"CALLED",100+i,.78+(i%20)/100)
  events.append({"id":f"EV-C-{i:03}","type":"Call","timestamp":stamp(100+i),"title":"CDR communication record","entities":[phones[a%30]['id'],phones[b%30]['id']],"source":f"E-{i%20+1:03}","confidence":.88})
 # explicit structural bridge, not labelled in text
 for j,p in enumerate([2,24,45,8,35]): edge("P-017",people[p]['id'],"ASSOCIATED_WITH",450+j,.9)
 # transactions, including rapid sequence
 for i in range(120):
  a=f"BA-{(i%20)+1:03}"; b=f"BA-{((i*7+5)%20)+1:03}"; amount=RNG.randint(9000,85000)
  if 92<=i<=95: a,b,amount=[("BA-003","BA-011",185000),("BA-011","BA-017",184500),("BA-017","BA-006",183900),("BA-006","BA-014",183200)][i-92]
  edge(a,b,"TRANSFERRED_TO",500+i,.91 if i>=92 and i<=95 else .8,f"E-{21+i%6:03}")
  events.append({"id":f"EV-T-{i:03}","type":"Transaction","timestamp":stamp(500+i),"title":f"Transfer of INR {amount:,}","entities":[a,b],"amount":amount,"source":f"E-{21+i%6:03}","confidence":.94})
 # visits and one co-location
 for i in range(150):
  p=people[(i*5)%60]['id']; loc=locations[(i*3)%15]['id']
  if i in (120,121): p,loc=("P-017" if i==120 else "P-036"),"L-05"
  edge(p,loc,"VISITED",700+i,.79,f"E-{i%20+1:03}")
  events.append({"id":f"EV-L-{i:03}","type":"Location","timestamp":stamp(700+i),"title":"Observed location record","entities":[p,loc],"source":f"E-{i%20+1:03}","confidence":.8})
 reports=[]
 for i in range(26):
  p=people[(i*2)%60]; phone=phones[i%30]
  text=f"Field report {i+1}: {p['label']} (alias {p['aliases'][0] if p['aliases'] else p['label'].split()[0]}) was mentioned near {LOCATIONS[i%15]}. Contact reference {phone['label']}; amount INR {12000+i*725}."
  eid=f"E-{i+1:03}"; digest=hashlib.sha256(text.encode()).hexdigest()
  evidence.append({"id":eid,"source":f"report_{i+1:02}.txt","document_type":"Field report","created_at":stamp(i),"hash":digest,"integrity":"VERIFIED","preview":text,"entities":[p['id'],phone['id']],"audit":["uploaded","processed","analyzed"]})
  reports.append({"id":f"DOC-{i+1:03}","text":text,"evidence_id":eid})
 # add evidence rows for CDR/financial data
 for i in range(26,40):
  text=f"Synthetic {('CDR' if i<34 else 'transaction')} dataset segment {i-25} for Operation ShadowLink."
  evidence.append({"id":f"E-{i+1:03}","source":f"dataset_{i-25:02}.csv","document_type":"CDR" if i<34 else "Transaction ledger","created_at":stamp(i),"hash":hashlib.sha256(text.encode()).hexdigest(),"integrity":"VERIFIED","preview":text,"entities":[],"audit":["uploaded","processed"]})

 # ---- SCALE-UP: extra entities/activity appended after the original deterministic set. ----
 # Original IDs (P-017, BA-003, PH-017, L-05, P-036, E-001..E-040 etc.) are untouched, so every
 # anomaly, test and hardcoded reference above still resolves exactly as before.
 for i in range(60,150):
  name=f"{FIRST[i%len(FIRST)]} {LAST[(i*3)%len(LAST)]}"
  people.append({"id":f"P-{i+1:03}","label":name,"type":"Person","aliases":[name.split()[0].lower()+str(i+1)] if i%11==0 else [],"confidence":round(.80+(i%19)/100,2),"case_id":CASE['id']})
 for i in range(30,100): phones.append({"id":f"PH-{i+1:03}","label":f"+91 555 {100000+i:06}","type":"Phone","confidence":.98})
 for i in range(20,100): accounts.append({"id":f"BA-{i+1:03}","label":f"ACCT-{470000+i}","type":"BankAccount","confidence":.98})
 org_prefixes=["Northstar","Cedar","Atlas","Meridian","Aurora","Vertex","Harborline","Silverline","Bluewave","Ironpeak"]
 org_suffixes=["Logistics","Trading","Holdings","Freight","Consulting","Imports","Ventures"]
 for i in range(10,100): orgs.append({"id":f"ORG-{i+1:02}","label":f"{org_prefixes[i%len(org_prefixes)]} {org_suffixes[i%len(org_suffixes)]} {i//len(org_prefixes)}","type":"Organization","confidence":.9})
 extra_loc_names=["Falcon Yard","Crescent Bridge","Pine Junction","Sable Wharf","Ember Court","Granite Row","Delta Freightway","Marsh Landing","Copper Mill","Ivy Crossing","Union Depot","Cobalt Square","Redwood Dock","Frontier Gate","Wren Terminal","Solstice Yard","Vantage Point","Brookline Wharf","Cinder Row","Hazel Crossing","Beacon Pier","Lantern District","Fennel Market","Timber Yard","Onyx Terminal","Willow Bend","Sterling Docks","Marigold Plaza","Basalt Row","Thistle Landing","Amber Crossing","Nightingale Court","Zephyr Terminal","Coral Bay Depot","Slate Junction"]
 loc_stems=["Sector","Grid","District","Zone","Block"]
 while len(extra_loc_names)<85: extra_loc_names.append(f"{loc_stems[len(extra_loc_names)%len(loc_stems)]} {len(extra_loc_names)+1} Yard")
 for i,x in enumerate(extra_loc_names): locations.append({"id":f"L-{i+16:02}","label":x,"type":"Location","confidence":.93})
 nodes=people+phones+accounts+orgs+locations  # rebuild with the extras included

 for i in range(30,100): edge(people[i]['id'],phones[i]['id'],"OWNS",2000+i,.97)
 for i in range(20,100): edge(people[i+5]['id'],accounts[i]['id'],"OWNS",2200+i,.97)
 for i in range(50,150): edge(people[i]['id'],orgs[i%len(orgs)]['id'],"WORKS_FOR",2500+i,.81)
 for i in range(470):
  group=(i//134)*25; a=group+(i*7)%25; b=group+(i*11+3)%25
  if a==b: b=(b+1)%100
  pa,pb=phones[a%100]['id'],phones[b%100]['id']
  edge(pa,pb,"CALLED",3000+i,.77+(i%22)/100)
  events.append({"id":f"EV-C2-{i:03}","type":"Call","timestamp":stamp(3000+i),"title":"CDR communication record","entities":[pa,pb],"source":f"E-{(i%40)+1:03}","confidence":.87})
 for i in range(280):
  a=f"BA-{(i%100)+1:03}"; b=f"BA-{((i*7+5)%100)+1:03}"; amount=RNG.randint(7000,92000)
  edge(a,b,"TRANSFERRED_TO",4000+i,.8,f"E-{21+(i%20):03}")
  events.append({"id":f"EV-T2-{i:03}","type":"Transaction","timestamp":stamp(4000+i),"title":f"Transfer of INR {amount:,}","entities":[a,b],"amount":amount,"source":f"E-{21+(i%20):03}","confidence":.9})
 all_location_ids=[l['id'] for l in locations]
 for i in range(350):
  p=people[(i*5)%150]['id']; loc=all_location_ids[(i*3)%len(all_location_ids)]
  edge(p,loc,"VISITED",5000+i,.78,f"E-{(i%40)+1:03}")
  events.append({"id":f"EV-L2-{i:03}","type":"Location","timestamp":stamp(5000+i),"title":"Observed location record","entities":[p,loc],"source":f"E-{(i%40)+1:03}","confidence":.79})
 for i in range(26,100):
  p=people[(i*3)%150]; phone=phones[i%100]
  text=f"Field report {i+1}: {p['label']} (alias {p['aliases'][0] if p['aliases'] else p['label'].split()[0]}) was mentioned near {(LOCATIONS+extra_loc_names)[i%(len(LOCATIONS)+len(extra_loc_names))]}. Contact reference {phone['label']}; amount INR {12000+i*725}."
  eid=f"E-{i+15:03}"; digest=hashlib.sha256(text.encode()).hexdigest()
  evidence.append({"id":eid,"source":f"report_{i+1:02}.txt","document_type":"Field report","created_at":stamp(900+i),"hash":digest,"integrity":"VERIFIED","preview":text,"entities":[p['id'],phone['id']],"audit":["uploaded","processed","analyzed"]})
  reports.append({"id":f"DOC-{i+1:03}","text":text,"evidence_id":eid})
 # ---- end scale-up ----

 return {"nodes":nodes,"edges":edges,"events":sorted(events,key=lambda x:x['timestamp'],reverse=True),"evidence":evidence,"reports":reports}

DATA=build()

def analytics():
 g=nx.Graph(); g.add_nodes_from(n['id'] for n in DATA['nodes']); g.add_edges_from((e['source'],e['target']) for e in DATA['edges'])
 degree=nx.degree_centrality(g); between=nx.betweenness_centrality(g); page=nx.pagerank(g)
 communities=list(nx.algorithms.community.greedy_modularity_communities(g)); c={n:i+1 for i,x in enumerate(communities) for n in x}
 scores={n:round(100*(.35*degree.get(n,0)+.35*between.get(n,0)+.3*page.get(n,0))/max(.0001,max(.35*degree[x]+.35*between[x]+.3*page[x] for x in g)),1) for n in g}
 return {"degree":degree,"betweenness":between,"pagerank":page,"communities":c,"scores":scores,"graph":g}

def anomalies():
 return [
  {"id":"AN-001","type":"Rapid transfer sequence","severity":"HIGH","confidence":.93,"timestamp":stamp(592),"entities":["BA-003","BA-011","BA-017","BA-006"],"explanation":"Four high-value transfers appear within a narrow time window.","evidence":["E-021","E-022","E-023","E-024"]},
  {"id":"AN-002","type":"Communication burst","severity":"MEDIUM","confidence":.88,"timestamp":stamp(321),"entities":["PH-017","PH-006","PH-025"],"explanation":"Communication frequency exceeds the synthetic baseline for this cluster.","evidence":["E-002","E-007"]},
  {"id":"AN-003","type":"Location overlap","severity":"MEDIUM","confidence":.84,"timestamp":stamp(820),"entities":["P-017","P-036","L-05"],"explanation":"Two entities have records at Atlas Warehouse in the same activity window.","evidence":["E-001","E-006"]},
 ]