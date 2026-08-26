from fastapi.testclient import TestClient
try:  # supports both repository-root and backend working directories
    from app.main import app
    from app.data import DATA, analytics
except ModuleNotFoundError:
    from backend.app.main import app
    from backend.app.data import DATA, analytics
client=TestClient(app)
def test_synthetic_scale(): assert len(DATA['nodes']) >= 100 and len(DATA['edges']) >= 500
def test_graph_analytics(): assert analytics()['scores']['P-017'] > 0
def test_dashboard(): assert client.get('/api/dashboard').status_code == 200
def test_dashboard_summary_is_store_backed():
    response=client.get('/api/dashboard/summary')
    assert response.status_code == 200
    data=response.json()
    assert data['metrics']['entities'] >= 100
    assert data['metrics']['relationships'] >= 500
    assert data['metrics']['active_cases'] == 1
    assert len(data['high_priority_entities']) > 0
def test_entity_intelligence_is_ranked_and_searches_existing_identifiers():
    ranked=client.get('/api/entities').json()
    assert ranked and ranked[0]['importance_score'] >= ranked[-1]['importance_score']
    entity=next(x for x in ranked if x['type']=='Phone')
    phone_digits=''.join(character for character in entity['label'] if character.isdigit())
    phone_results=client.get('/api/entities',params={'q':phone_digits}).json()
    assert any(x['id']==entity['id'] for x in phone_results)
    account=next(x for x in ranked if x['type']=='BankAccount')
    account_results=client.get('/api/entities',params={'q':account['label'].replace('ACCT-','')}).json()
    assert any(x['id']==account['id'] for x in account_results)
    assert {'influence_score','centrality','connection_count','risk_score','importance_reasons','evidence_ids'} <= ranked[0].keys()
def test_entity_correlations_use_observed_cross_source_records():
    response=client.get('/api/entities/P-017/correlations')
    assert response.status_code==200 and response.json()
    correlation=response.json()[0]
    assert correlation['source_types'] and correlation['entities'] and correlation['evidence_ids']
    assert all(record['id'].startswith(('EV-','R-')) for record in correlation['records'])
    assert 'observed' in correlation['explanation'].lower()
def test_path(): assert client.get('/api/path?source=P-017&target=P-003').json()['path']
def test_timeline_supports_entity_and_event_type_filters():
    all_events=client.get('/api/timeline').json()
    assert all_events
    event=all_events[0]
    by_entity=client.get('/api/timeline',params={'entity':event['entities'][0]}).json()
    by_type=client.get('/api/timeline',params={'kind':event['type']}).json()
    assert by_entity and all(event['entities'][0] in item['entities'] for item in by_entity)
    assert by_type and all(item['type']==event['type'] for item in by_type)
def test_path_includes_real_alternatives_and_relationships():
    data=client.get('/api/graph/path?source=P-017&target=P-003').json()
    assert data['paths'] and data['paths'][0]['path'] == data['path']
    assert len(data['paths'][0]['relationships']) == len(data['path'])-1
def test_evidence_hash(): assert client.get('/api/evidence/E-001/verify').json()['verified']
def test_upload_mutates_persistent_case():
    before=client.get('/api/dashboard').json()['kpis']['evidence']
    response=client.post('/api/ingestion/upload',files={'file':('audit.txt',b'Aarav Sen met Nila Rao. Contact +91 99999 33333.','text/plain')})
    assert response.status_code == 200
    result=response.json()
    assert client.post(f"/api/evidence/{result['evidence_id']}/verify").json()['verified']
    assert client.get('/api/dashboard').json()['kpis']['evidence'] == before+1
def test_retrieval_and_report_are_data_backed():
    answer=client.post('/api/assistant/query',json={'question':'What does audit.txt say about Aarav Sen?'}).json()
    assert answer['provider']=='deterministic-retrieval' and answer['sources']
    report=client.post('/api/reports/generate').json()
    assert report['entities'] and report['system_findings']['key_entities']
    assert report['source_evidence']['integrity'] and report['source_evidence']['verified_count'] >= 1
    assert all(item['status'] in {'VERIFIED','MISSING_OR_MISMATCH'} for item in report['source_evidence']['integrity'])
def test_assistant_returns_supporting_entity_and_evidence_ids():
    response=client.post('/api/assistant/query',json={'question':'How are P-017 and P-003 connected?'})
    data=response.json()
    assert response.status_code==200 and data['provider']=='deterministic-retrieval'
    assert 'P-017' in data['entity_ids'] and 'P-003' in data['entity_ids']
    assert data['evidence_ids'] and all(item.startswith('E-') for item in data['evidence_ids'])
def test_assistant_states_when_data_is_insufficient():
    data=client.post('/api/assistant/query',json={'question':'zzzzzzzzzzzzzzzzzzzzzz'}).json()
    assert 'insufficient' in data['inference'].lower() and data['evidence_ids']==[]
def test_fir_extraction_rejects_ocr_noise_and_keeps_identifiers():
    try:
        from app.store import extract
    except ModuleNotFoundError:
        from backend.app.store import extract
    text='''FIR Report\nUnder Section 420 of the Act\nName: Rahul Sharma\nComplainant: Smt. Priya Nair\nDayi Tlme and Ihc Hon at Rankl Chennai\nMobile: +91 98765 43210, alternate 9876543211\nAccount No: 1234 5678 9012\nAmount Rs. 45,000 and INR 50000; OCR noise Rs.9\nCase No 12, District Station'''
    found=extract(text)
    assert 'Rahul Sharma' in found['names'] and 'Priya Nair' in found['names']
    assert not any('Section' in name or 'Tlme' in name or 'Rankl' in name for name in found['names'])
    assert found['phones']==['+919876543210','+919876543211']
    assert found['accounts']==['123456789012']
    assert any('45,000' in amount for amount in found['amounts']) and any('50000' in amount for amount in found['amounts'])
    assert not any(amount.endswith('9') for amount in found['amounts'])

def test_structured_extraction_requires_source_grounding():
    try:
        from app.llm import validate_extraction
    except ModuleNotFoundError:
        from backend.app.llm import validate_extraction
    payload={'entities':[{'name':'Aarav Sen','type':'Person'}],'relationships':[],'dates':[],'locations':[],'phones':[],'accounts':[],'transactions':[]}
    assert validate_extraction(payload,'Report names Aarav Sen.')['entities'][0]['name']=='Aarav Sen'
    payload['entities'][0]['name']='Invented Person'
    try:
        validate_extraction(payload,'Report names Aarav Sen.')
        assert False, 'unsupported LLM entity should be rejected'
    except ValueError:
        pass

def test_text_upload_uses_deterministic_fallback_when_llm_fails(monkeypatch):
    try:
        from app import llm
    except ModuleNotFoundError:
        from backend.app import llm
    monkeypatch.setattr(llm,'extract_structured',lambda text: (_ for _ in ()).throw(RuntimeError('test LLM failure')))
    response=client.post('/api/ingestion/upload',files={'file':('hybrid-fallback.txt',b'Aarav Sen met Nila Rao. Contact +91 99999 33333.','text/plain')})
    assert response.status_code==200
    result=response.json()
    assert 'deterministic fallback' in result['extraction_method']
    assert result['warnings'] and result['evidence_id'].startswith('E-')

def test_validated_llm_mapping_preserves_requested_fields():
    try:
        from app.llm import to_legacy_extraction, validate_extraction
    except ModuleNotFoundError:
        from backend.app.llm import to_legacy_extraction, validate_extraction
    source='Aarav Sen transferred INR 45000 to account 123456789 on 2026-08-26 in Harbor Gate.'
    payload={'entities':[{'name':'Aarav Sen','type':'Person'},{'name':'123456789','type':'BankAccount'}],'relationships':[{'source':'Aarav Sen','target':'123456789','type':'TRANSFERRED_TO'}],'dates':['2026-08-26'],'locations':['Harbor Gate'],'phones':[],'accounts':['123456789'],'transactions':[{'from':'Aarav Sen','to':'123456789','amount':'45000','date':'2026-08-26'}]}
    validated=validate_extraction(payload,source)
    legacy=to_legacy_extraction(validated)
    assert legacy['names']==['Aarav Sen'] and legacy['accounts']==['123456789'] and legacy['amounts']==['45000']

def test_sample_document_validation_rejects_person_false_positives_and_checks_relationship_types():
    try:
        from app.llm import validate_extraction
    except ModuleNotFoundError:
        from backend.app.llm import validate_extraction
    source=open('data/evidence/E-041_audit.txt',encoding='utf-8').read()
    base={'relationships':[],'dates':[],'locations':[],'phones':[],'accounts':[],'transactions':[]}
    valid={**base,'entities':[{'name':'Aarav Sen','type':'PERSON'},{'name':'Nila Rao','type':'PERSON'}]}
    assert len(validate_extraction(valid,source)['entities'])==2
    for false_name in ('Field Report','Aarav Sen met Nila Rao','Aarav'):
        invalid={**base,'entities':[{'name':false_name,'type':'PERSON'}]}
        try:
            validate_extraction(invalid,source)
            assert False, f'{false_name} should not be accepted as a PERSON'
        except ValueError:
            pass
    invalid_relationship={**valid,'relationships':[{'source':'Aarav Sen','target':'Unknown Entity','type':'ASSOCIATED_WITH'}]}
    try:
        validate_extraction(invalid_relationship,source)
        assert False, 'relationship with undeclared endpoint should be rejected'
    except ValueError:
        pass

def test_smart_city_pdf_fallback_keeps_only_explicit_person_name():
    try:
        import pdfplumber
        from app import store
    except ModuleNotFoundError:
        import pdfplumber
        from backend.app import store
    with pdfplumber.open('data/evidence/E-049_smart city sensors.pdf') as pdf:
        source='\n'.join(page.extract_text() or '' for page in pdf.pages)
    extracted=store.extract(source)
    person_values=[item['value'] for item in extracted['typed_entities'] if item['type']=='PERSON']
    assert person_values==['Kunal Sunil Pagar']
    assert not any(value in person_values for value in ('Smart City','Urban Living','Pagar What','Are Smart','City Sensors'))
