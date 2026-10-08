#!/usr/bin/env python3
import json, os, re, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import xml.etree.ElementTree as ET

ZH_RE=re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff]')
URL_RE=re.compile(r'^(?:https?://|ftp://)',re.I)
PLACEHOLDER_RE=re.compile(r'%(?:\d+\$)?[a-zA-Z]|%[0-9]+|\$[A-Za-z0-9_]+|\\[ntr]|<[^>]+>')
LOCALE_CODES={'af','am','ar','bg','bn','ca','cs','da','de','el','en','es','fa','fi','fr','he','hi','hr','hu','id','in','it','iw','ja','ko','ms','nb','nl','no','pl','pt','ro','ru','sk','sl','sr','sv','sw','ta','th','tr','uk','ur','vi','zh'}
OVERRIDES={
 '小米运动健康':'Mi Fitness', '小米运动健康APP':'Mi Fitness', '小米运动健康 App':'Mi Fitness',
 '血压':'артериальное давление','动态血压':'суточное мониторирование АД','无感血压':'бесконтактное измерение АД',
 '心率':'частота пульса','睡眠':'сон','健康研究':'исследование здоровья','血压健康研究':'исследование артериального давления',
 '风险评估问卷':'Анкета оценки риска','最新结果':'Последний результат','网络连接失败，请重试':'Не удалось подключиться к сети, повторите попытку',
 '获取评价列表:开始时间:':'Получение списка оценок: время начала:','删除失败':'Не удалось удалить','数据同步失败':'Не удалось синхронизировать данные',
 'yyyy年MM月dd日':'dd.MM.yyyy','yyyy年M月':'MM.yyyy','yyyy年M月d':'dd.MM.yyyy','yyyy年M月d日':'dd.MM.yyyy',
 'M月d':'d.MM','M月d日':'d.MM','M月d日 HH:mm':'d.MM HH:mm'
}

def protect(s):
    vals=[]
    def f(m): vals.append(m.group(0)); return f'__P{len(vals)-1}__'
    return PLACEHOLDER_RE.sub(f,s),vals

def valid_translation(src,out):
    if not out or ZH_RE.search(out): return False
    a=sorted(protected_tokens(src)); b=sorted(protected_tokens(out))
    return a==b

def protected_tokens(s): return PLACEHOLDER_RE.findall(s)

def translate_one(s):
    if s in OVERRIDES:return OVERRIDES[s]
    safe,vals=protect(s)
    q=urllib.parse.quote(safe,safe='')
    url='https://translate.googleapis.com/translate_a/single?client=gtx&sl=zh-CN&tl=ru&dt=t&q='+q
    for i in range(6):
        try:
            with urllib.request.urlopen(url,timeout=20) as r:
                data=json.loads(r.read().decode('utf-8'))
            out=''.join(x[0] for x in data[0] if x and x[0])
            for n,v in enumerate(vals): out=out.replace(f'__P{n}__',v)
            if valid_translation(s,out): return out
        except Exception: pass
        time.sleep(0.75*(i+1))
    return s

def should_translate(text, attrs):
    if not text or not text.strip() or not ZH_RE.search(text): return False
    if attrs.get('translatable','true')=='false': return False
    if URL_RE.search(text.strip()): return False
    if text.strip().startswith('@') or text.strip().startswith('?'): return False
    return True

def add_child(parent, kind, elem, cache):
    if kind=='string':
        if should_translate(elem.text, elem.attrib):
            e=ET.SubElement(parent,'string',dict(elem.attrib)); e.text=cache.get(elem.text,elem.text)
            return True
        return False
    if kind in ('string-array','array'):
        items=list(elem.findall('item'))
        trans=False
        vals=[]
        for it in items:
            t=it.text
            if should_translate(t,it.attrib):
                vals.append(cache.get(t,t)); trans=True
            else: vals.append(t)
        if trans:
            e=ET.SubElement(parent,kind,dict(elem.attrib))
            for it,t in zip(items,vals):
                x=ET.SubElement(e,'item',dict(it.attrib)); x.text=t
            return True
        return False
    if kind=='plurals':
        items=list(elem.findall('item')); trans=False; vals=[]
        for it in items:
            t=it.text
            if should_translate(t,it.attrib): vals.append(cache.get(t,t)); trans=True
            else: vals.append(t)
        if trans:
            e=ET.SubElement(parent,'plurals',dict(elem.attrib))
            for it,t in zip(items,vals):
                x=ET.SubElement(e,'item',dict(it.attrib)); x.text=t
            return True
        return False
    if kind=='item' and elem.attrib.get('type')=='string':
        if should_translate(elem.text,elem.attrib):
            e=ET.SubElement(parent,'item',dict(elem.attrib)); e.text=cache.get(elem.text,elem.text); return True
    return False

def qualifier_target(dirname):
    q=dirname[len('values'):]
    if not q: return 'values-ru'
    parts=q[1:].split('-')
    if any(p in LOCALE_CODES or p.startswith('r') and len(p)==3 and p[1:].isupper() for p in parts): return None
    return 'values-ru'+q

def main(root,cache_path):
    root=Path(root)
    files=[]; targets=[]
    for d in sorted(root.glob('res/values*')):
        if not d.is_dir(): continue
        outdir=qualifier_target(d.name)
        if not outdir: continue
        for f in d.glob('*.xml'):
            try: tree=ET.parse(f)
            except Exception: continue
            for elem in tree.getroot():
                kind=elem.tag.split('}')[-1]
                vals=[]
                if kind=='string': vals=[elem.text]
                elif kind in ('string-array','array','plurals'): vals=[x.text for x in elem.findall('item')]
                elif kind=='item' and elem.attrib.get('type')=='string': vals=[elem.text]
                for t in vals:
                    if should_translate(t,elem.attrib): targets.append(t)
            files.append((f,outdir))
    cache={}
    if os.path.exists(cache_path):
        try: cache=json.load(open(cache_path,encoding='utf-8'))
        except Exception: cache={}
    unique=list(dict.fromkeys(targets)); todo=[s for s in unique if s not in cache]
    print(f'TRANSLATE_TARGETS={len(unique)} TODO={len(todo)}',flush=True)
    with ThreadPoolExecutor(max_workers=8) as ex:
        fs={ex.submit(translate_one,s):s for s in todo}
        for i,f in enumerate(as_completed(fs),1):
            s=fs[f]
            try: cache[s]=f.result()
            except Exception: cache[s]=s
            if i%50==0: print(f'TRANSLATED={i}/{len(todo)}',flush=True)
    json.dump(cache,open(cache_path,'w',encoding='utf-8'),ensure_ascii=False,indent=2)

    made=0; translated=0
    for f,outdir in files:
        tree=ET.parse(f); root_el=tree.getroot(); items=[]
        for elem in root_el:
            kind=elem.tag.split('}')[-1]
            if kind in ('string','string-array','array','plurals') or (kind=='item' and elem.attrib.get('type')=='string'):
                holder=ET.Element('resources')
                if add_child(holder,kind,elem,cache): items.append((kind, list(holder)[0]))
        if not items: continue
        od=root/outdir/ f.name if False else None
        target=root/'res'/outdir
        target.mkdir(parents=True,exist_ok=True)
        newroot=ET.Element('resources')
        for _,e in items: newroot.append(e)
        ET.ElementTree(newroot).write(target/f.name,encoding='utf-8',xml_declaration=True)
        made+=1; translated+=sum(1 for _,e in items)
    print(f'RU_OVERLAY_FILES={made}',flush=True)
    print(f'RU_OVERLAY_RESOURCES={translated}',flush=True)

if __name__=='__main__': main(*__import__('sys').argv[1:])
