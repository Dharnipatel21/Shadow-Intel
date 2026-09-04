"""Groq calls for evidence-grounded answers and structured extraction."""
from __future__ import annotations
import json
import re
import unicodedata
from . import config

SYSTEM_PROMPT = (
    "You are ShadowIntel's investigation assistant. You are given a question "
    "and a list of OBSERVED EVIDENCE lines retrieved from the case's evidence "
    "store and graph. Answer using ONLY the observed evidence provided. "
    "Never state or imply guilt, criminality, or legal responsibility. "
    "If the evidence is empty or insufficient, say so plainly. "
    "Keep the answer concise (3-6 sentences)."
)

def generate(question: str, observed_evidence: list[str], response_language: str = 'English') -> str:
    from groq import Groq

    client = Groq(api_key=config.GROQ_API_KEY)
    evidence_block = "\n".join(f"- {line}" for line in observed_evidence) or "(none)"
    completion = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + f" Reply in {response_language}, preserving evidence IDs and source wording where quoted."},
            {"role": "user", "content": f"Question: {question}\n\nOBSERVED EVIDENCE:\n{evidence_block}"},
        ],
        temperature=0.2,
        max_tokens=400,
    )
    return completion.choices[0].message.content.strip()

EXTRACTION_KEYS = {'entities', 'relationships', 'dates', 'locations', 'phones', 'accounts', 'transactions'}
ENTITY_TYPES = {
    'person': 'PERSON', 'people': 'PERSON', 'individual': 'PERSON',
    'organization': 'ORGANIZATION', 'organisation': 'ORGANIZATION', 'company': 'ORGANIZATION', 'org': 'ORGANIZATION',
    'location': 'LOCATION', 'place': 'LOCATION',
    'phone': 'PHONE', 'telephone': 'PHONE', 'mobile': 'PHONE',
    'account': 'ACCOUNT', 'bankaccount': 'ACCOUNT', 'bank account': 'ACCOUNT',
    'date': 'DATE', 'time': 'DATE', 'vehicle': 'VEHICLE', 'document': 'DOCUMENT',
}
PERSON_STOPWORDS = {'report', 'case', 'field', 'contact', 'reference', 'account', 'number', 'mobile', 'date', 'time', 'information', 'record', 'section', 'station', 'city', 'district', 'source', 'text'}
EXTRACTION_PROMPT = """Extract only facts explicitly present in SOURCE TEXT.
Return strict JSON with exactly these keys:
{"entities":[{"name":"...","type":"..."}],"relationships":[{"source":"...","target":"...","type":"..."}],"dates":["..."],"locations":["..."],"phones":["..."],"accounts":["..."],"transactions":[{"from":"...","to":"...","amount":"...","date":"..."}]}
Use empty arrays when a category is absent. Do not infer, normalize, resolve, summarize, or add facts. Every value must be copied from SOURCE TEXT; relationship and transaction endpoints must be copied entity/identifier text from SOURCE TEXT."""

def _normalized(value: str) -> str:
    return ''.join(character for character in value.casefold() if character.isalnum())

def _supported(value: str, source: str) -> bool:
    value_norm=_normalized(value)
    return bool(value_norm) and value_norm in _normalized(source)

def _entity_type(value: str) -> str:
    return ENTITY_TYPES.get(re.sub(r'[_-]+', ' ', value.strip().casefold()), '')

def _valid_entity_name(name: str, entity_type: str, source: str) -> bool:
    if not _supported(name, source) or any(character in name for character in '.!?;:'):
        return False
    words=name.strip().split()
    if not 1 <= len(words) <= 5 or any(not word.strip('()[],-').strip() for word in words):
        return False
    if entity_type == 'PERSON':
        if not 2 <= len(words) <= 4 or any(not all(character.isalpha() or unicodedata.category(character).startswith('M') or character in "'’-" for character in word) for word in words):
            return False
        return not any(word.casefold() in PERSON_STOPWORDS for word in words)
    if entity_type in {'PHONE', 'ACCOUNT', 'DATE'}:
        return bool(re.search(r'\d', name))
    return True

def validate_extraction(payload: object, source: str) -> dict:
    if not isinstance(payload, dict) or set(payload) != EXTRACTION_KEYS:
        raise ValueError('LLM extraction must contain exactly the required JSON keys.')
    if not all(isinstance(payload[key], list) for key in EXTRACTION_KEYS):
        raise ValueError('LLM extraction fields must all be arrays.')
    entities=[]
    entity_types={}
    for item in payload['entities']:
        if not isinstance(item, dict) or set(item) != {'name','type'} or not all(isinstance(item[key], str) and item[key].strip() for key in item):
            raise ValueError('Invalid entity object in LLM extraction.')
        entity_type=_entity_type(item['type'])
        name=item['name'].strip()
        if not entity_type or not _valid_entity_name(name,entity_type,source): raise ValueError('Entity is invalid, unsupported, or an ungrounded phrase.')
        key=_normalized(name)
        if key in entity_types and entity_types[key] != entity_type: raise ValueError('Entity has conflicting types.')
        entity_types[key]=entity_type
        entities.append({'name':name,'type':entity_type})
    relationships=[]
    for item in payload['relationships']:
        if not isinstance(item, dict) or set(item) != {'source','target','type'} or not all(isinstance(item[key], str) and item[key].strip() for key in item):
            raise ValueError('Invalid relationship object in LLM extraction.')
        source_name=item['source'].strip(); target_name=item['target'].strip()
        source_type=entity_types.get(_normalized(source_name)); target_type=entity_types.get(_normalized(target_name))
        if not source_type or not target_type: raise ValueError('Relationship endpoint must reference a declared entity.')
        relationships.append({'source':source_name,'target':target_name,'type':item['type'].strip()})
    scalar_fields=('dates','locations','phones','accounts')
    for field in scalar_fields:
        if not all(isinstance(value,str) and value.strip() and _supported(value,source) for value in payload[field]):
            raise ValueError(f'Unsupported {field} value in LLM extraction.')
    transactions=[]
    for item in payload['transactions']:
        if not isinstance(item, dict) or set(item) != {'from','to','amount','date'} or not all(isinstance(item[key],str) and item[key].strip() for key in item):
            raise ValueError('Invalid transaction object in LLM extraction.')
        from_name=item['from'].strip(); to_name=item['to'].strip()
        if not entity_types.get(_normalized(from_name)) or not entity_types.get(_normalized(to_name)):
            raise ValueError('Transaction endpoint must reference a declared entity.')
        transactions.append({key:item[key].strip() for key in ('from','to','amount','date')})
    return {'entities':entities,'relationships':relationships,**{field:[value.strip() for value in payload[field]] for field in scalar_fields},'transactions':transactions}

def extract_structured(source: str) -> dict:
    """Extract strict, source-grounded JSON or raise so callers can fall back."""
    if not config.groq_enabled(): raise RuntimeError('LLM extraction is not configured.')
    from groq import Groq
    completion=Groq(api_key=config.GROQ_API_KEY).chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[{'role':'system','content':EXTRACTION_PROMPT},{'role':'user','content':f'SOURCE TEXT:\n{source}'}],
        temperature=0,
        response_format={'type':'json_object'},
    )
    content=completion.choices[0].message.content or ''
    return validate_extraction(json.loads(content),source)

def to_legacy_extraction(payload: dict) -> dict:
    """Map validated LLM output into the existing deterministic storage shape."""
    names=[item['name'] for item in payload['entities'] if item['type'].casefold() not in {'phone','bankaccount','account'}]
    amounts=[item['amount'] for item in payload['transactions']]
    typed_entities=[{'value':item['name'],'type':item['type']} for item in payload['entities']]
    typed_entities += [{'value':phone,'type':'PHONE'} for phone in payload['phones']]
    typed_entities += [{'value':account,'type':'ACCOUNT'} for account in payload['accounts']]
    return {'typed_entities':typed_entities,'names':list(dict.fromkeys(names)),'phones':list(dict.fromkeys(payload['phones'])),'accounts':list(dict.fromkeys(payload['accounts'])),'vehicles':[],'amounts':list(dict.fromkeys(amounts))}
