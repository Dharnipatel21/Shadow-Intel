"""Small, dependency-free language helpers for supported investigation records."""
from __future__ import annotations

import re

LANGUAGES = {
    'en': {'name': 'English', 'tesseract': 'eng'},
    'hi': {'name': 'Hindi', 'tesseract': 'hin'},
    'ta': {'name': 'Tamil', 'tesseract': 'tam'},
    'te': {'name': 'Telugu', 'tesseract': 'tel'},
    'bn': {'name': 'Bengali', 'tesseract': 'ben'},
    'mr': {'name': 'Marathi', 'tesseract': 'mar'},
    'gu': {'name': 'Gujarati', 'tesseract': 'guj'},
}

def detect_language(text: str) -> str:
    """Detect the supported script without sending evidence to a third party."""
    if re.search(r'[\u0B80-\u0BFF]', text): return 'ta'
    if re.search(r'[\u0C00-\u0C7F]', text): return 'te'
    if re.search(r'[\u0980-\u09FF]', text): return 'bn'
    if re.search(r'[\u0A80-\u0AFF]', text): return 'gu'
    if re.search(r'[\u0900-\u097F]', text):
        # Marathi-specific particles make this otherwise shared script distinction useful.
        return 'mr' if any(marker in text for marker in ('आहे', 'आणि', 'मध्ये', 'च्या', 'करा', 'होते')) else 'hi'
    return 'en'

def language_name(code: str) -> str:
    return LANGUAGES.get(code, LANGUAGES['en'])['name']

def ocr_languages(available: list[str]) -> str:
    """Use every installed supported pack; this lets Tesseract detect mixed scripts."""
    packs = [item['tesseract'] for item in LANGUAGES.values() if item['tesseract'] in available]
    return '+'.join(packs or ['eng'])
