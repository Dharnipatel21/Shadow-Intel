from __future__ import annotations
from pathlib import Path
from time import perf_counter
import hashlib, json, re, shutil
from urllib.parse import parse_qs, urlparse
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from . import store, auth, config, llm, export, data, language

app=FastAPI(title='ShadowIntel API',version='2.0')
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:3000','http://127.0.0.1:3000'],allow_origin_regex=r'^https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3})(:\d+)?$',allow_methods=['*'],allow_headers=['*'])
@app.exception_handler(Exception)
async def unexpected_error(request:Request, exc:Exception):
    return JSONResponse(status_code=500,content={'detail':f'{type(exc).__name__}: {exc}'})
# Make direct TestClient imports and CLI runs safe even when lifespan is not entered.
store.init()
@app.on_event('startup')
def startup(): store.init(); auth.init_auth()
ALL_CASES='ALL_CASES'
def case_scope(case_id):
    return None if case_id in (None, '', ALL_CASES) else case_id
def all_cases_summary():
    return {'id':ALL_CASES,'name':'All Cases','status':'ACTIVE','investigator':'','priority':'','stage':'','disclaimer':'All case records are included in this workspace view.'}
def case(): return store.one('SELECT * FROM cases LIMIT 1')
def entity_or_404(id):
    x=store.one('SELECT * FROM entities WHERE id=?',id)
    if not x: raise HTTPException(404,'Entity not found')
    return store.entity_intelligence([x])[0]

class SignupBody(BaseModel):
    email: str
    password: str
    name: str

class LoginBody(BaseModel):
    email: str
    password: str

class OtpVerifyBody(BaseModel):
    email: str
    code: str

class OtpResendBody(BaseModel):
    email: str

class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str

@app.post('/api/auth/signup')
def signup(body: SignupBody):
    if auth.get_user_by_email(body.email):
        raise HTTPException(409, 'An account with this email already exists.')
    uid, verify_token, otp_code = auth.create_user(body.email, body.password, body.name)
    if config.smtp_enabled():
        try:
            auth.send_otp_email(body.email, otp_code)
        except HTTPException:
            pass
    return {'id': uid, 'email': body.email, 'name': body.name, 'message': 'Account created. Check your email for the verification code.'}

@app.post('/api/auth/login')
def login(body: LoginBody):
    user = auth.get_user_by_email(body.email)
    if not user or not user['password_hash'] or not auth.verify_password(body.password, user['password_hash']):
        raise HTTPException(401, 'Invalid email or password.')
    if not user['is_verified']:
        raise HTTPException(403, 'Please verify your email with the OTP code before logging in.')
    token = auth.create_token(user['id'], user['email'])
    return {'token': token, 'user': {'id': user['id'], 'email': user['email'], 'name': user['name']}}

@app.post('/api/auth/verify-otp')
def verify_otp(body: OtpVerifyBody):
    user = auth.verify_otp(body.email, body.code)
    token = auth.create_token(user['id'], user['email'])
    return {'token': token, 'user': {'id': user['id'], 'email': user['email'], 'name': user['name']}}

@app.post('/api/auth/resend-otp')
def resend_otp(body: OtpResendBody):
    code = auth.regenerate_otp(body.email)
    if config.smtp_enabled():
        auth.send_otp_email(body.email, code)
    return {'message': 'Verification code resent.'}

@app.get('/api/auth/me')
def me(request: Request):
    authz = request.headers.get('authorization', '')
    if not authz.startswith('Bearer '):
        raise HTTPException(401, 'Missing bearer token.')
    payload = auth.decode_token(authz.removeprefix('Bearer '))
    user = auth.get_user_by_email(payload['email'])
    if not user:
        raise HTTPException(401, 'User not found.')
    return {'id': user['id'], 'email': user['email'], 'name': user['name']}

@app.post('/api/auth/change-password')
def change_password(body: ChangePasswordBody, request: Request):
    authz = request.headers.get('authorization', '')
    if not authz.startswith('Bearer '):
        raise HTTPException(401, 'Missing bearer token.')
    payload = auth.decode_token(authz.removeprefix('Bearer '))
    user = auth.get_user_by_email(payload['email'])
    if not user:
        raise HTTPException(401, 'User not found.')
    if not user['password_hash']:
        raise HTTPException(400, 'Password changes are unavailable for this account.')
    if not auth.verify_password(body.current_password, user['password_hash']):
        raise HTTPException(400, 'Current password is incorrect.')
    if len(body.new_password) < 8:
        raise HTTPException(400, 'New password must be at least 8 characters.')
    if body.current_password == body.new_password:
        raise HTTPException(400, 'New password must be different from the current password.')
    c = store.conn()
    c.execute('UPDATE users SET password_hash=? WHERE id=?', (auth.hash_password(body.new_password), user['id']))
    c.commit()
    c.close()
    return {'message': 'Password changed successfully.'}

@app.get('/api/auth/google/login')
def google_login():
    import secrets
    state = secrets.token_urlsafe(16)
    return {'url': auth.google_login_url(state)}

@app.get('/api/auth/google/callback')
def google_callback(code: str, state: str = ''):
    userinfo = auth.google_exchange_code(code)
    email = userinfo.get('email')
    name = userinfo.get('name', email)
    user = auth.get_user_by_email(email)
    if not user:
        uid, _, _ = auth.create_user(email, None, name, provider='google')
    else:
        uid = user['id']
    token = auth.create_token(uid, email)
    return RedirectResponse(f"{config.FRONTEND_BASE_URL}/auth/callback?token={token}")
@app.get('/api/health')
def health(): return {'status':'healthy','case':case()['name'],'database':str(store.DB)}
@app.get('/api/case')
def case_api(): return case()

class CaseCreateBody(BaseModel):
    name: str
    investigator: str = ''
    priority: str = 'MEDIUM'
    stage: str = 'EVIDENCE_INGESTION'
    status: str = 'ACTIVE'

class CaseUpdateBody(BaseModel):
    name: str | None = None
    status: str | None = None
    investigator: str | None = None
    priority: str | None = None
    stage: str | None = None

def validate_choice(value, choices, field):
    if value is not None and value not in choices:
        raise HTTPException(422, f"Invalid {field} '{value}'. Must be one of: {', '.join(choices)}.")

@app.get('/api/cases')
def cases_list():
    """Case Management: every case with live entity/evidence/relationship counts."""
    return {'cases': store.list_cases(), 'statuses': data.CASE_STATUSES, 'stages': data.CASE_STAGES, 'priorities': data.CASE_PRIORITIES}

@app.post('/api/cases')
def cases_create(body: CaseCreateBody):
    validate_choice(body.status, data.CASE_STATUSES, 'status')
    validate_choice(body.priority, data.CASE_PRIORITIES, 'priority')
    validate_choice(body.stage, data.CASE_STAGES, 'stage')
    if not body.name.strip():
        raise HTTPException(422, 'Case name is required.')
    return store.create_case(body.name.strip(), body.investigator.strip(), body.priority, body.stage, body.status)

@app.get('/api/cases/{case_id}')
def cases_detail(case_id: str):
    x = store.one('SELECT * FROM cases WHERE id=?', case_id)
    if not x: raise HTTPException(404, 'Case not found')
    return x

@app.patch('/api/cases/{case_id}')
def cases_update(case_id: str, body: CaseUpdateBody):
    validate_choice(body.status, data.CASE_STATUSES, 'status')
    validate_choice(body.priority, data.CASE_PRIORITIES, 'priority')
    validate_choice(body.stage, data.CASE_STAGES, 'stage')
    updated = store.update_case(case_id, name=body.name, status=body.status, investigator=body.investigator, priority=body.priority, stage=body.stage)
    if not updated: raise HTTPException(404, 'Case not found')
    return updated

@app.delete('/api/cases/{case_id}')
def cases_delete(case_id: str):
    if not store.one('SELECT id FROM cases WHERE id=?', case_id):
        raise HTTPException(404, 'Case not found')
    if not store.delete_case(case_id):
        raise HTTPException(400, 'Cannot delete the last remaining case.')
    return {'deleted': case_id}

BLACKBOARD_KINDS = ('ENTITY', 'EVIDENCE', 'NOTE', 'HYPOTHESIS')
BLACKBOARD_STATUSES = ('', 'OPEN', 'SUPPORTED', 'CHALLENGED', 'REJECTED')

class BlackboardItemCreate(BaseModel):
    case_id: str = 'CASE-SL-01'
    kind: str
    title: str
    content: str = ''
    ref_id: str | None = None
    status: str = ''
    x: float = 40.0
    y: float = 40.0
    color: str = 'amber'
    created_by: str = ''

class BlackboardItemUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    status: str | None = None
    x: float | None = None
    y: float | None = None
    color: str | None = None

class BlackboardConnectionCreate(BaseModel):
    case_id: str = 'CASE-SL-01'
    from_id: str
    to_id: str
    label: str = ''

@app.get('/api/blackboard')
def blackboard_get(case_id: str = 'CASE-SL-01'):
    """Live Investigation Blackboard: pinned entities/evidence, notes, hypotheses, and their connections."""
    if not store.one('SELECT id FROM cases WHERE id=?', case_id):
        raise HTTPException(404, 'Case not found')
    return store.list_blackboard(case_id)

@app.post('/api/blackboard/items')
def blackboard_item_create(body: BlackboardItemCreate):
    validate_choice(body.kind, BLACKBOARD_KINDS, 'kind')
    if body.status:
        validate_choice(body.status, BLACKBOARD_STATUSES, 'status')
    if not body.title.strip():
        raise HTTPException(422, 'A title is required.')
    if body.kind == 'ENTITY' and not (body.ref_id and store.one('SELECT id FROM entities WHERE id=?', body.ref_id)):
        raise HTTPException(422, 'A valid entity ref_id is required for an ENTITY card.')
    if body.kind == 'EVIDENCE' and not (body.ref_id and store.one('SELECT id FROM evidence WHERE id=?', body.ref_id)):
        raise HTTPException(422, 'A valid evidence ref_id is required for an EVIDENCE card.')
    try:
        return store.add_blackboard_item(body.case_id, body.kind, body.title.strip(), body.content.strip(), body.ref_id, body.status, body.x, body.y, body.color, body.created_by.strip())
    except ValueError as error:
        raise HTTPException(404, str(error))

@app.patch('/api/blackboard/items/{item_id}')
def blackboard_item_update(item_id: str, body: BlackboardItemUpdate):
    if body.status:
        validate_choice(body.status, BLACKBOARD_STATUSES, 'status')
    updated = store.update_blackboard_item(item_id, title=body.title, content=body.content, status=body.status, x=body.x, y=body.y, color=body.color)
    if not updated:
        raise HTTPException(404, 'Blackboard item not found')
    return updated

@app.delete('/api/blackboard/items/{item_id}')
def blackboard_item_delete(item_id: str):
    if not store.delete_blackboard_item(item_id):
        raise HTTPException(404, 'Blackboard item not found')
    return {'deleted': item_id}

@app.post('/api/blackboard/connections')
def blackboard_connection_create(body: BlackboardConnectionCreate):
    if body.from_id == body.to_id:
        raise HTTPException(422, 'Cannot connect a card to itself.')
    try:
        return store.add_blackboard_connection(body.case_id, body.from_id, body.to_id, body.label.strip())
    except ValueError as error:
        raise HTTPException(404, str(error))

@app.delete('/api/blackboard/connections/{connection_id}')
def blackboard_connection_delete(connection_id: str):
    if not store.delete_blackboard_connection(connection_id):
        raise HTTPException(404, 'Connection not found')
    return {'deleted': connection_id}

@app.get('/api/dashboard')
def dashboard(case_id:str='CASE-SL-01'):
    selected=store.one('SELECT * FROM cases WHERE id=?',case_id)
    if not selected: raise HTTPException(404,'Case not found')
    nodes=store.enrich(store.query('SELECT * FROM entities WHERE case_id=?',case_id)); alerts=store.detect_anomalies(); priority=sorted(nodes,key=lambda x:x['priority'],reverse=True)
    return {'case':case(),'kpis':{'entities':len(nodes),'relationships':len(store.query('SELECT id FROM relationships')),'anomalies':len(alerts),'priority':len([x for x in priority if x['priority']>=35]),'evidence':len(store.query('SELECT id FROM evidence'))},'priority':priority[:7],'anomalies':alerts[:5],'activity':store.query('SELECT * FROM events ORDER BY timestamp DESC LIMIT 7')}
@app.get('/api/dashboard/summary')
def dashboard_summary(case_id:str='CASE-SL-01'):
    """Single source for Command Center widgets, calculated from the live store."""
    scope=case_scope(case_id); selected=all_cases_summary() if scope is None else store.one('SELECT * FROM cases WHERE id=?',scope)
    if not selected: raise HTTPException(404,'Case not found')
    nodes=store.enrich(store.query('SELECT * FROM entities') if scope is None else store.query('SELECT * FROM entities WHERE case_id=?',scope))
    priority=sorted(nodes,key=lambda x:x['priority'],reverse=True)
    alerts=store.detect_anomalies()
    active_cases=store.query("SELECT id FROM cases WHERE status='ACTIVE'")
    return {
        'case':selected,
        'metrics':{
            'active_cases':len(active_cases),
            'entities':len(nodes),
            'relationships':len(store.query('SELECT id FROM relationships')),
            'high_priority_entities':len([x for x in priority if x['priority']>=35]),
            'anomaly_alerts':len(alerts),
        },
        'high_priority_entities':priority[:7],
        'anomaly_alerts':alerts[:5],
        'recent_activity':store.query('SELECT * FROM events ORDER BY timestamp DESC LIMIT 7'),
    }
@app.get('/api/entities')
def entities(q:str='',case_id:str='CASE-SL-01'):
    term=q.strip().casefold()
    scope=case_scope(case_id); items=store.query('SELECT * FROM entities') if scope is None else store.query('SELECT * FROM entities WHERE case_id=?',scope)
    if term:
        normalized_term=re.sub(r'[^a-z0-9]','',term)
        items=[item for item in items if any(
            term in value.casefold() or (normalized_term and normalized_term in re.sub(r'[^a-z0-9]','',value.casefold()))
            for value in [item['id'],item['label'],*item.get('aliases',[])]
        )]
    return store.entity_intelligence(items)
@app.get('/api/entities/{entity_id}')
def entity(entity_id:str):
    x=entity_or_404(entity_id); return {'entity':x,'case':case(),'connections':connections(entity_id),'timeline':entity_timeline(entity_id),'evidence':entity_evidence(entity_id),'anomalies':[a for a in store.detect_anomalies() if entity_id in a['entities']]}
@app.get('/api/entities/{entity_id}/connections')
def connections(entity_id:str): entity_or_404(entity_id); return store.query('SELECT * FROM relationships WHERE source=? OR target=? ORDER BY timestamp DESC',entity_id,entity_id)
@app.get('/api/entities/{entity_id}/timeline')
def entity_timeline(entity_id:str): entity_or_404(entity_id); return [x for x in store.query('SELECT * FROM events ORDER BY timestamp DESC') if entity_id in x['entities']]
@app.get('/api/entities/{entity_id}/evidence')
def entity_evidence(entity_id:str): entity_or_404(entity_id); return [x for x in store.query('SELECT * FROM evidence ORDER BY created_at DESC') if entity_id in x['entities']]
@app.get('/api/entities/{entity_id}/correlations')
def entity_correlations(entity_id:str): entity_or_404(entity_id); return store.cross_source_correlations(entity_id)
@app.get('/api/graph')
def graph(q:str='',focus:str='',hops:int=Query(0,ge=0,le=3),type:str='',case_id:str='CASE-SL-01'):
    scope=case_scope(case_id); nodes=store.enrich(store.query('SELECT * FROM entities') if scope is None else store.query('SELECT * FROM entities WHERE case_id=?',scope)); node_ids={x['id'] for x in nodes}; edges=[x for x in store.query('SELECT * FROM relationships') if x['source'] in node_ids and x['target'] in node_ids]
    import networkx as nx
    g=nx.Graph(); g.add_nodes_from(node_ids); g.add_edges_from((x['source'],x['target']) for x in edges); selected=set(g.nodes)
    if focus:
        if focus not in g: raise HTTPException(404,'Graph entity not found')
        import networkx as nx; selected=set(nx.single_source_shortest_path_length(g,focus,cutoff=max(hops,1)).keys())
    if q: selected &= {x['id'] for x in nodes if q.lower() in x['label'].lower() or q.lower() in x['id'].lower()}
    if type: selected &= {x['id'] for x in nodes if x['type'].lower()==type.lower()}
    return {'nodes':[x for x in nodes if x['id'] in selected],'edges':[x for x in edges if x['source'] in selected and x['target'] in selected]}
@app.get('/api/graph/entity/{entity_id}')
def graph_entity(entity_id:str,hops:int=Query(1,ge=1,le=3)): return graph(focus=entity_id,hops=hops)
@app.get('/api/graph/neighborhood')
def neighborhood(entity_id:str,hops:int=Query(1,ge=1,le=3)): return graph(focus=entity_id,hops=hops)
@app.get('/api/graph/path')
@app.get('/api/path')
def path(source:str,target:str,max_paths:int=Query(5,ge=1,le=10)):
    import networkx as nx
    g,_=store.graph()
    limit=max_paths if isinstance(max_paths,int) else 5
    try: paths=list(__import__('itertools').islice(nx.all_shortest_paths(g,source,target),limit))
    except (nx.NetworkXNoPath,nx.NodeNotFound): return {'path':[],'relationships':[],'paths':[],'message':'No observed path in the current graph.'}
    def path_relationships(ids):
        relationships=[]
        for a,b in zip(ids,ids[1:]):
            matches=store.query('SELECT * FROM relationships WHERE (source=? AND target=?) OR (source=? AND target=?) ORDER BY confidence DESC',a,b,b,a)
            if matches: relationships.append(matches[0])
        return relationships
    alternatives=[{'path':ids,'relationships':path_relationships(ids)} for ids in paths]
    primary=alternatives[0]
    return {'path':primary['path'],'relationships':primary['relationships'],'paths':alternatives,'message':f'Found {len(alternatives)} observed shortest path(s).'}
@app.get('/api/anomalies')
def anomalies(case_id:str='CASE-SL-01'): return store.detect_anomalies(case_scope(case_id))
@app.get('/api/anomalies/{anomaly_id}')
def anomaly(anomaly_id:str):
    x=next((x for x in store.detect_anomalies() if x['id']==anomaly_id),None)
    if not x: raise HTTPException(404,'Anomaly not found')
    return x
@app.post('/api/anomalies/analyze')
def analyze(): return {'status':'completed','anomalies':store.detect_anomalies()}
@app.get('/api/timeline')
def timeline(entity:str='',kind:str='',start:str='',end:str='',source:str='',case_id:str='CASE-SL-01'):
    scope=case_scope(case_id)
    events=store.query('SELECT events.* FROM events LEFT JOIN evidence ON evidence.id=events.source ORDER BY events.timestamp DESC') if scope is None else store.query('SELECT events.* FROM events LEFT JOIN evidence ON evidence.id=events.source WHERE evidence.case_id=? OR (evidence.id IS NULL AND ?=?) ORDER BY events.timestamp DESC',scope,scope,'CASE-SL-01')
    return [x for x in events if (not entity or entity in x['entities']) and (not kind or x['type'].lower()==kind.lower()) and (not start or x['timestamp']>=start) and (not end or x['timestamp']<=end) and (not source or x['source']==source)]
@app.get('/api/evidence')
def evidence(q:str='',case_id:str='CASE-SL-01'):
    scope=case_scope(case_id); items=store.query('SELECT * FROM evidence ORDER BY created_at DESC') if scope is None else store.query('SELECT * FROM evidence WHERE case_id=? ORDER BY created_at DESC',scope)
    return [x for x in items if not q or q.lower() in (x['id']+x['source']+x['extracted_text']).lower()]
@app.get('/api/evidence/{evidence_id}')
def evidence_detail(evidence_id:str):
    x=store.one('SELECT * FROM evidence WHERE id=?',evidence_id)
    if not x: raise HTTPException(404,'Evidence not found')
    return x

@app.get('/api/evidence/{evidence_id}/file')
def evidence_file(evidence_id: str):
    """Serve the original locally stored evidence file for supported workspace previews."""
    item = evidence_detail(evidence_id)
    source = Path(item['path'])
    if not source.is_file():
        raise HTTPException(404, 'Stored evidence file not found')
    return FileResponse(source, filename=source.name)
@app.post('/api/evidence/{evidence_id}/verify')
@app.get('/api/evidence/{evidence_id}/verify')
def verify(evidence_id:str):
    import hashlib
    x=evidence_detail(evidence_id); p=Path(x['path']); actual=hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    return {'id':evidence_id,'verified':actual==x['hash'],'stored_hash':x['hash'],'actual_hash':actual,'message':'SHA-256 matches the stored evidence record.' if actual==x['hash'] else 'SHA-256 mismatch or source file missing.'}
def ocr_image(image):
    """Run genuine local Tesseract OCR or clearly state why it cannot run."""
    binary=shutil.which('tesseract')
    if not binary:
        candidate=Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe')
        binary=str(candidate) if candidate.exists() else None
    if not binary:
        raise HTTPException(422,'Image OCR unavailable: the Tesseract system binary was not found. Install Tesseract and add it to PATH, then retry.')
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd=binary
        available=pytesseract.get_languages(config='')
        return pytesseract.image_to_string(image, lang=language.ocr_languages(available))
    except Exception as e:
        raise HTTPException(422,f'Image OCR unavailable: {e}')
def document_text(file,raw):
    suffix=Path(file.filename or '').suffix.lower()
    if suffix in {'.png','.jpg','.jpeg','.tiff','.bmp'}:
        try:
            from PIL import Image
            import io
            text=ocr_image(Image.open(io.BytesIO(raw))); return text,'OCR',language.language_name(language.detect_language(text))
        except HTTPException: raise
        except Exception as e: raise HTTPException(422,f'Image could not be decoded for OCR: {e}')
    if suffix=='.pdf':
        try:
            import io, pdfplumber
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                pages=list(pdf.pages); text='\n'.join(page.extract_text() or '' for page in pages).strip()
                if text: return text,'PDF text',language.language_name(language.detect_language(text))
                # Scanned PDF: render each page then send it through the exact same OCR service.
                rendered=[page.to_image(resolution=200).original for page in pages]
            text='\n'.join(ocr_image(image) for image in rendered).strip()
            if not text: raise HTTPException(422,'Scanned PDF OCR completed but no readable text was found.')
            return text,'OCR',language.language_name(language.detect_language(text))
        except HTTPException: raise
        except ImportError: raise HTTPException(422,'PDF extraction requires pdfplumber. Install backend requirements with python -m pip install -r requirements.txt.')
        except Exception as e: raise HTTPException(422,f'PDF text extraction failed: {e}')
    text=raw.decode('utf-8','ignore'); return text,'plain text',language.language_name(language.detect_language(text))
def youtube_video_id(url):
    parsed=urlparse(url)
    if parsed.netloc in {'youtu.be','www.youtu.be'}: return parsed.path.strip('/').split('/')[0]
    if 'youtube.com' in parsed.netloc:
        return parse_qs(parsed.query).get('v',[''])[0] or (parsed.path.split('/')[2] if parsed.path.startswith('/shorts/') else '')
    return ''
def youtube_text(url):
    video_id=youtube_video_id(url)
    if not video_id: raise HTTPException(422,'Invalid YouTube URL. Provide a youtube.com/watch?v=... or youtu.be/... link.')
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript=YouTubeTranscriptApi().fetch(video_id)
        text=' '.join(item.text for item in transcript)
    except Exception as e:
        raise HTTPException(422,f'YouTube transcript unavailable for this video: {e}')
    if not text.strip(): raise HTTPException(422,'YouTube transcript unavailable: no caption text was returned.')
    return text,video_id
@app.post('/api/ingestion/upload')
@app.post('/api/ingest')
async def ingest(file:UploadFile|None=File(None), url:str|None=Form(None), case_id:str=Form('CASE-SL-01')):
    if not store.one('SELECT id FROM cases WHERE id=?', case_id): raise HTTPException(404, 'Case not found')
    began=perf_counter(); raw=await file.read() if file else b''
    if url:
        if file: raise HTTPException(422,'Provide either a file or a YouTube URL, not both.')
        text,video_id=youtube_text(url); raw=text.encode('utf-8'); detected_language=language.language_name(language.detect_language(text)); result=store.add_upload(f'youtube_{video_id}.txt',raw,text,'YouTube transcript','transcript',case_id=case_id,language=detected_language)
    else:
        if not file or not raw: raise HTTPException(422,'Provide a non-empty file or a YouTube URL.')
        text,method,detected_language=document_text(file,raw)
        suffix=Path(file.filename or '').suffix.lower()
        extracted=store.extract(text); structured=extracted; extraction_method=method; warnings=[]
        if suffix in {'.txt','.pdf'} and method in {'plain text','PDF text'}:
            try:
                structured=llm.extract_structured(text)
                extracted=llm.to_legacy_extraction(structured)
                extraction_method='LLM structured JSON'
            except Exception as error:
                warnings.append(f'LLM extraction unavailable or failed validation; deterministic extraction used: {error}')
                extraction_method=f'{method} (deterministic fallback)'
        result=store.add_upload(file.filename or 'upload',raw,text,method,extraction_method,extracted=extracted,structured_extraction=structured,warnings=warnings,case_id=case_id,language=detected_language)
    # Real rule-generated result for the final ingestion pipeline stage.
    result['anomaly_count']=len(store.detect_anomalies())
    result['language']=detected_language; result['duration_ms']=round((perf_counter()-began)*1000,2); return result
@app.get('/api/ingestion/jobs')
def jobs(case_id:str='CASE-SL-01'):
    items=store.query('SELECT * FROM jobs WHERE case_id=? ORDER BY created_at DESC',case_id)
    for item in items: item['result']=json.loads(item['result'])
    return items
@app.get('/api/ingestion/jobs/{job_id}')
def job(job_id:str):
    x=store.one('SELECT * FROM jobs WHERE id=?',job_id)
    if not x: raise HTTPException(404,'Ingestion job not found')
    x['result']=json.loads(x['result']); return x
def question_entities(question):
    q=question.lower(); return [x for x in store.enrich(store.query('SELECT * FROM entities')) if x['label'].lower() in q or x['id'].lower() in q]
def _confidence_score(rel, docs, alerts, matched):
    """Deterministic 0-100 score computed only from what was actually retrieved. Never a probability of guilt."""
    score=min(len(rel),4)*15 + min(len(docs),4)*10 + min(len(alerts),3)*8 + (10 if len(matched)>=2 else 0)
    return max(5, min(score, 97))
def _confidence_label(score):
    return 'HIGH' if score>=70 else 'MEDIUM' if score>=40 else 'LOW'
def _evidence_gaps(rel, docs, alerts, matched):
    gaps=[]
    if len(matched)>=2 and not rel: gaps.append('No confirmed graph relationship links the named entities; only indirect evidence, if any, was found.')
    if not docs: gaps.append('No source evidence document text was retrieved for this question.')
    if matched and not alerts: gaps.append('No anomaly or risk signal is currently linked to the matched entities.')
    return gaps
def _next_step(rel, docs, alerts, gaps):
    if not rel and not docs and not alerts: return 'Ingest additional evidence mentioning these entities, then re-ask this question.'
    if rel and not alerts: return 'Review the linked relationship evidence in Network Explorer and check whether either entity also appears in an anomaly.'
    if alerts and not rel: return 'Open the linked anomaly in Anomaly & Risk Analysis to review its contributing evidence.'
    if docs and not rel and not alerts: return 'Open the cited evidence in Evidence & Reports to verify the source and provenance.'
    return 'Cross-check the cited evidence IDs against the entity dossier before including this finding in a report.'
ASSISTANT_COPY={
    'en':('No sufficiently relevant observed evidence was retrieved for this question.','The available case data is insufficient to answer this question. No inference is made.','Review the cited evidence and entity IDs before acting on this result.'),
    'hi':('इस प्रश्न के लिए पर्याप्त प्रेक्षित साक्ष्य नहीं मिला।','उपलब्ध केस डेटा इस प्रश्न का उत्तर देने के लिए अपर्याप्त है। कोई निष्कर्ष नहीं निकाला गया है।','इस परिणाम पर कार्रवाई से पहले उद्धृत साक्ष्य और इकाई आईडी की समीक्षा करें।'),
    'ta':('இந்தக் கேள்விக்குப் போதுமான பதிவுசெய்யப்பட்ட சான்றுகள் கிடைக்கவில்லை.','இந்தக் கேள்விக்குப் பதிலளிக்க கிடைக்கக்கூடிய வழக்குத் தரவு போதுமானதல்ல. எந்த முடிவும் எடுக்கப்படவில்லை.','இந்த முடிவில் நடவடிக்கை எடுப்பதற்கு முன் மேற்கோள் சான்றுகளையும் அலகு ஐடிகளையும் சரிபார்க்கவும்.'),
    'te':('ఈ ప్రశ్నకు తగిన పరిశీలిత సాక్ష్యం లభించలేదు.','ఈ ప్రశ్నకు సమాధానం ఇవ్వడానికి అందుబాటులో ఉన్న కేసు డేటా సరిపోదు. ఎలాంటి నిర్ధారణ చేయలేదు.','ఈ ఫలితంపై చర్య తీసుకునే ముందు పేర్కొన్న సాక్ష్యం మరియు ఎంటిటీ ఐడీలను సమీక్షించండి.'),
    'bn':('এই প্রশ্নের জন্য যথেষ্ট পর্যবেক্ষিত প্রমাণ পাওয়া যায়নি।','এই প্রশ্নের উত্তর দেওয়ার জন্য উপলব্ধ মামলার তথ্য যথেষ্ট নয়। কোনো অনুমান করা হয়নি।','এই ফলাফলের ভিত্তিতে পদক্ষেপ নেওয়ার আগে উদ্ধৃত প্রমাণ ও সত্তার আইডি পর্যালোচনা করুন।'),
    'mr':('या प्रश्नासाठी पुरेसा निरीक्षित पुरावा मिळाला नाही.','या प्रश्नाचे उत्तर देण्यासाठी उपलब्ध प्रकरणातील माहिती अपुरी आहे. कोणताही निष्कर्ष काढलेला नाही.','या निकालावर कारवाई करण्यापूर्वी उद्धृत पुरावे आणि घटक आयडी तपासा.'),
    'gu':('આ પ્રશ્ન માટે પૂરતા અવલોકિત પુરાવા મળ્યા નથી.','આ પ્રશ્નનો જવાબ આપવા માટે ઉપલબ્ધ કેસ ડેટા અપૂરતો છે. કોઈ અનુમાન કરવામાં આવ્યું નથી.','આ પરિણામ પર કાર્યવાહી કરતા પહેલાં ઉલ્લેખિત પુરાવા અને એન્ટિટી આઈડીની સમીક્ષા કરો.'),
}
OBSERVED_COPY={
    'en': lambda count, relationships: f"Retrieved {count} evidence-backed observation(s)." if not relationships else f"{relationships} observed graph relationship(s) connect the identified entities.",
    'hi': lambda count, relationships: f"{count} साक्ष्य-आधारित अवलोकन प्राप्त हुए।" if not relationships else f"{relationships} देखे गए ग्राफ संबंध पहचानी गई इकाइयों को जोड़ते हैं।",
    'ta': lambda count, relationships: f"{count} சான்று அடிப்படையிலான பதிவுகள் கிடைத்தன." if not relationships else f"{relationships} கவனிக்கப்பட்ட வரைபட உறவுகள் அடையாளம் காணப்பட்ட அலகுகளை இணைக்கின்றன.",
    'te': lambda count, relationships: f"{count} సాక్ష్య ఆధారిత పరిశీలనలు లభించాయి." if not relationships else f"{relationships} పరిశీలించిన గ్రాఫ్ సంబంధాలు గుర్తించిన ఎంటిటీలను కలుపుతున్నాయి.",
    'bn': lambda count, relationships: f"{count}টি প্রমাণ-ভিত্তিক পর্যবেক্ষণ পাওয়া গেছে।" if not relationships else f"{relationships}টি পর্যবেক্ষিত গ্রাফ সম্পর্ক চিহ্নিত সত্তাগুলিকে সংযুক্ত করে।",
    'mr': lambda count, relationships: f"{count} पुरावा-आधारित निरीक्षणे मिळाली." if not relationships else f"{relationships} निरीक्षित ग्राफ संबंध ओळखलेल्या घटकांना जोडतात.",
    'gu': lambda count, relationships: f"{count} પુરાવા આધારિત અવલોકનો મળ્યા." if not relationships else f"{relationships} અવલોકિત ગ્રાફ સંબંધો ઓળખાયેલી એન્ટિટીઓને જોડે છે.",
}
def answer(question, case_id='CASE-SL-01'):
    question_language=language.detect_language(question); response_language=language.language_name(question_language); copy=ASSISTANT_COPY[question_language]; scope=case_scope(case_id)
    docs=store.retrieve(question, scope); matched=[x for x in question_entities(question) if scope is None or x.get('case_id') == scope]; rel=[]
    if len(matched)>=2: rel=path(matched[0]['id'],matched[1]['id'])['relationships']
    alerts=[alert for alert in store.detect_anomalies() if any(entity['id'] in alert.get('entities',[]) for entity in matched)]
    sources=list(dict.fromkeys([d['id'] for d in docs]+[r['evidence_id'] for r in rel if r.get('evidence_id')]+[evidence for alert in alerts for evidence in alert.get('evidence',[])]))
    entity_ids=list(dict.fromkeys([entity['id'] for entity in matched]+[entity for doc in docs for entity in doc.get('entities',[])]+[entity for relationship in rel for entity in (relationship['source'],relationship['target'])]))
    observed=[f"{r['type']}: {r['source']} → {r['target']} at {r['timestamp']} (evidence {r['evidence_id']})." for r in rel]+[f"{d['source']}: {d['extracted_text'][:180]}" for d in docs[:3]]+[f"{alert['type']}: {alert['explanation']} (evidence {', '.join(alert.get('evidence',[]))})." for alert in alerts[:3]]
    gaps=_evidence_gaps(rel, docs, alerts, matched)
    if not observed:
        return {'provider':'deterministic-retrieval','language':response_language,'finding':copy[0],'observed_evidence':[],'inference':copy[1],'confidence':'LOW','confidence_score':5,'why':[copy[0]],'next_step':copy[2],'evidence_gaps':[copy[0]],'sources':[],'evidence_ids':[],'entity_ids':entity_ids}
    finding=OBSERVED_COPY[question_language](len(observed), len(rel))
    score=_confidence_score(rel, docs, alerts, matched)
    confidence=_confidence_label(score)
    why=[]
    if matched: why.append(f"Matched {len(matched)} named entity/entities in the question: {', '.join(x['id'] for x in matched)}.")
    if rel: why.append(f"Found {len(rel)} confirmed graph relationship(s) directly linking the matched entities.")
    if docs: why.append(f"Retrieved {len(docs)} evidence document(s) whose text contains terms from the question.")
    if alerts: why.append(f"Linked {len(alerts)} anomaly/risk signal(s) involving the matched entities.")
    why.append(f"Confidence score {score}/100 reflects only what is directly observed above; it is not a probability of guilt.")
    provider='deterministic-retrieval'
    if config.groq_enabled():
        try:
            finding=llm.generate(question, observed, response_language)
            provider='groq-llm'
        except Exception as error:
            finding=f"{finding} (LLM answer unavailable: {error})"
    return {'provider':provider,'language':response_language,'finding':finding,'observed_evidence':observed,'inference':copy[1] if question_language!='en' else 'The retrieved records may indicate an association for investigator review; they do not establish guilt or legal responsibility.','confidence':confidence,'confidence_score':score,'why':why,'next_step':copy[2] if question_language!='en' else _next_step(rel, docs, alerts, gaps),'evidence_gaps':gaps,'sources':sources,'evidence_ids':sources,'entity_ids':entity_ids}
@app.post('/api/assistant/query')
@app.post('/api/assistant')
def assistant(payload:dict):
    case_id=payload.get('case_id','CASE-SL-01'); question=payload.get('question','').strip()
    if not question: raise HTTPException(422, 'A question is required.')
    result=answer(question, case_id)
    try: store.add_assistant_message(case_id, question, result, result['language'])
    except ValueError as error: raise HTTPException(404, str(error))
    return result
@app.get('/api/assistant/history')
def assistant_history(case_id: str='CASE-SL-01'):
    scope=case_scope(case_id)
    if scope is None: return store.list_assistant_messages(None)
    if not store.one('SELECT id FROM cases WHERE id=?', scope): raise HTTPException(404, 'Case not found')
    return store.list_assistant_messages(scope)
@app.post('/api/reports/generate')
@app.get('/api/report')
def report():
    d=dashboard(); all_evidence=store.query('SELECT * FROM evidence ORDER BY created_at DESC'); all_relationships=store.query('SELECT * FROM relationships ORDER BY confidence DESC');
    integrity=[]
    for item in all_evidence:
        source=Path(item['path']); actual=hashlib.sha256(source.read_bytes()).hexdigest() if source.exists() else None
        integrity.append({'id':item['id'],'source':item['source'],'status':'VERIFIED' if actual==item['hash'] else 'MISSING_OR_MISMATCH','stored_hash':item['hash'],'actual_hash':actual})
    correlations=[]; correlation_keys=set()
    ranked_entities=sorted(store.enrich(store.query('SELECT * FROM entities')),key=lambda entity:entity['priority'],reverse=True)
    for entity in ranked_entities:
        for correlation in store.cross_source_correlations(entity['id']):
            key=tuple(sorted(record['id'] for record in correlation['records']))
            if key not in correlation_keys: correlation_keys.add(key); correlations.append(correlation)
            if len(correlations)>=12: break
        if len(correlations)>=12: break
    evidence_ids=list(dict.fromkeys([item['id'] for item in all_evidence if item['id'] in {x for relationship in all_relationships[:12] for x in [relationship.get('evidence_id')]}]+[evidence for alert in d['anomalies'] for evidence in alert.get('evidence',[])]+[event['source'] for event in d['activity'] if event.get('source')]))
    rid='REP-'+str(len(store.query('SELECT id FROM reports'))+1).zfill(3); content={'id':rid,'title':f"{d['case']['name']} - Investigation Summary",'generated':store.now(),'case':d['case'],'executive_summary':f"Current database: {d['kpis']['entities']} entities, {d['kpis']['relationships']} observed relationships, {d['kpis']['anomalies']} detected indicators.",'entities':d['priority'][:5],'anomalies':d['anomalies'],'timeline_highlights':d['activity'][:5],'system_findings':{'key_entities':d['priority'][:7],'important_relationships':all_relationships[:12],'cross_source_correlations':correlations,'risk_anomalies':d['anomalies'],'timeline_highlights':d['activity'][:7]},'source_evidence':{'evidence_ids':evidence_ids,'integrity':integrity,'verified_count':sum(item['status']=='VERIFIED' for item in integrity),'issue_count':sum(item['status']!='VERIFIED' for item in integrity)},'methodology':'Persistent SQLite case store; NetworkX graph analytics; rule-based risk indicators; observed cross-source correlations; SHA-256 verification against stored evidence files.','disclaimer':d['case']['disclaimer']}
    c=store.conn(); c.execute('INSERT INTO reports VALUES(?,?,?)',(rid,content['generated'],json.dumps(content))); c.commit(); c.close(); return content
@app.get('/api/reports/{report_id}')
def report_detail(report_id:str):
    x=store.one('SELECT * FROM reports WHERE id=?',report_id)
    if not x: raise HTTPException(404,'Report not found')
    return json.loads(x['content'])
@app.get('/api/reports/{report_id}/export/docx')
def report_export_docx(report_id:str):
    x=store.one('SELECT * FROM reports WHERE id=?',report_id)
    if not x: raise HTTPException(404,'Report not found')
    content=json.loads(x['content'])
    buffer=export.report_to_docx(content)
    return StreamingResponse(buffer,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',headers={'Content-Disposition':f'attachment; filename="{report_id}.docx"'})
@app.get('/api/reports/{report_id}/export/pdf')
def report_export_pdf(report_id:str):
    x=store.one('SELECT * FROM reports WHERE id=?',report_id)
    if not x: raise HTTPException(404,'Report not found')
    content=json.loads(x['content'])
    buffer=export.report_to_pdf(content)
    return StreamingResponse(buffer,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{report_id}.pdf"'})
    
