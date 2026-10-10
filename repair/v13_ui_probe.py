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
    'программе улучшения пользовательского опыта',
    'Пользовательское соглашение Xiaomi Health Research',
    'политика конфиденциальности Xiaomi Health Research',
    'краткое изложение политики конфиденциальности',
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
        raise SystemExit('V13_UI_DUMP_MISSING_OR_EMPTY')
    root=ET.parse(p).getroot()
    nodes=list(root.iter('node'))
    texts=[(n.attrib.get('text','') or n.attrib.get('content-desc','')).strip() for n in nodes]
    if mode=='check':
        missing=[x for x in REQUIRED if not any(x in t for t in texts)]
        for item in REQUIRED:
            print('V13_UI_TEXT_'+str(REQUIRED.index(item)+1)+'='+('PASS' if any(item in t for t in texts) else 'MISSING')+':'+item)
        if missing:
            raise SystemExit('V13_RUSSIAN_ONBOARDING_NOT_VISIBLE:'+repr(missing))
        print('V13_RUSSIAN_ONBOARDING_VISIBLE=PASS')
        return
    if mode=='check-basic':
        onboarding_only=['Добро пожаловать','Наслаждайтесь здоровой жизнью','Не соглашаться и перейти в базовый режим']
        still_visible=[x for x in onboarding_only if any(x in t for t in texts)]
        if still_visible:
            raise SystemExit('V13_BASIC_MODE_DID_NOT_LEAVE_ONBOARDING:'+repr(still_visible))
        print('V13_BASIC_MODE_LEFT_ONBOARDING=PASS')
        print('V13_BASIC_MODE_UI_NODES='+str(len(nodes)))
        return
    if mode=='check-tab':
        global_shell={
            'Здоровье','Устройства','Профиль','Исследование здоровья Xiaomi',
            'Наслаждайтесь здоровой жизнью','健康','设备','我的','小米健康研究','畅享健康生活'
        }
        # App status-bar/nav-bar nodes are not in uiautomator's app XML on most
        # Android builds; remove only known global app shell labels, not content.
        substantive=sorted({t for t in texts if t and t not in global_shell})
        print('V16_TAB_TITLE='+needle)
        print('V16_TAB_VISIBLE_CONTENT_COUNT='+str(len(substantive)))
        print('V16_TAB_VISIBLE_CONTENT_SAMPLE='+repr(substantive[:50]))
        if substantive:
            print('V16_TAB_NOT_VISIBLY_EMPTY=YES')
        else:
            print('V16_TAB_BLANK_SCREEN_SUSPECTED=YES')
            raise SystemExit('V17_03_TAB_EMPTY:' + needle)
        return
    for n,t in zip(nodes,texts):
        if needle in t:
            b=bounds_center(n.attrib.get('bounds'))
            if b:
                print(f'{b[0]} {b[1]}')
                return
    raise SystemExit('V13_UI_TAP_TARGET_NOT_FOUND:'+needle)

if __name__=='__main__':
    if len(sys.argv) not in (3,4):
        raise SystemExit('usage: v13_ui_probe.py ui.xml check | ui.xml tap [text] | ui.xml check-basic')
    main(sys.argv[1],sys.argv[2],sys.argv[3] if len(sys.argv)==4 else 'Не соглашаться и перейти в базовый режим')
