#!/usr/bin/env python3
"""Validate Russian onboarding UI XML and optionally return button tap coordinates."""
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED = [
    'Добро пожаловать',
    'Исследование здоровья Xiaomi',
    'Наслаждайтесь здоровой жизнью',
    'Согласен',
    'Не соглашаться и перейти в базовый режим',
]

def bounds_center(value):
    m = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', value or '')
    if not m: return None
    x1,y1,x2,y2=map(int,m.groups())
    if x2<=x1 or y2<=y1: return None
    return ((x1+x2)//2,(y1+y2)//2)

def main(path, mode='check', needle='Не соглашаться и перейти в базовый режим'):
    p=Path(path)
    if not p.is_file() or p.stat().st_size < 50:
        raise SystemExit('V11_UI_DUMP_MISSING_OR_EMPTY')
    root=ET.parse(p).getroot()
    nodes=list(root.iter('node'))
    texts=[(n.attrib.get('text','') or n.attrib.get('content-desc','')).strip() for n in nodes]
    if mode=='check':
        missing=[x for x in REQUIRED if not any(x in t for t in texts)]
        for item in REQUIRED:
            print('V11_UI_TEXT_'+str(REQUIRED.index(item)+1)+'='+('PASS' if any(item in t for t in texts) else 'MISSING')+':'+item)
        if missing:
            raise SystemExit('V11_RUSSIAN_ONBOARDING_NOT_VISIBLE:'+repr(missing))
        print('V11_RUSSIAN_ONBOARDING_VISIBLE=PASS')
        return
    for n,t in zip(nodes,texts):
        if needle in t:
            b=bounds_center(n.attrib.get('bounds'))
            if b:
                print(f'{b[0]} {b[1]}')
                return
    raise SystemExit('V11_UI_TAP_TARGET_NOT_FOUND:'+needle)

if __name__=='__main__':
    if len(sys.argv) not in (3,4):
        raise SystemExit('usage: v11_ui_probe.py ui.xml check | ui.xml tap [text]')
    main(sys.argv[1],sys.argv[2],sys.argv[3] if len(sys.argv)==4 else 'Не соглашаться и перейти в базовый режим')
