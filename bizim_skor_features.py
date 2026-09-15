"""Race Intelligence - 20 family feature extraction.
No arbitrary 0-100 score and no neutral 50 imputation.
"""
from __future__ import annotations
from datetime import date, datetime
import math,re
from typing import Any,Dict,List,Optional

FAMILY_NAMES={1:'KOŞU ŞARTI UYUMU',2:'PİST + MESAFE',3:'PİST PERFORMANSI',4:'GERÇEK DERECE',5:'GERÇEK HIZ',6:'GÜNCEL FORM',7:'ORTAK RAKİP',8:'KİLO PERFORMANSI',9:'HP / KALİTE',10:'GALOP PERFORMANSI',11:'GALOP FORMU / TREND',12:'DİNLENME / KGS',13:'YARIŞ YOĞUNLUĞU',14:'START / KULVAR',15:'TEMPO / YARIŞ SENARYOSU',16:'JOKEY ETKİSİ',17:'ANTRENÖR ETKİSİ',18:'ORİJİN / PEDİGRİ',19:'KAZANÇ / KARİYER KALİTESİ',20:'PİYASA SİNYALİ'}

def num(v):
    if v is None or isinstance(v,bool): return None
    try:
        if isinstance(v,(int,float)): return float(v) if math.isfinite(float(v)) else None
        m=re.search(r'-?\d+(?:[\.,]\d+)?',str(v).replace(',','.'))
        return float(m.group()) if m else None
    except Exception:return None

def txt(v): return '' if v is None else str(v).strip()
def dist(r): return num(r.get('distance') or r.get('msf') or r.get('mesafe'))
def place(r): return next((x for k in ('place','sira','S','finish','finishPosition') if (x:=num(r.get(k))) is not None and x>0),None)
def weight(r): return next((num(r.get(k)) for k in ('weight','kilo','siklet','Sıklet') if num(r.get(k)) is not None),None)
def hp(r): return next((num(r.get(k)) for k in ('hp','HP','rating') if num(r.get(k)) is not None),None)
def surf(v):
    s=txt(v).upper()
    if not s:return ''
    if s.startswith('K') or 'KUM' in s:return 'KUM'
    if s.startswith('Ç') or 'ÇİM' in s or 'CIM' in s:return 'ÇİM'
    if s.startswith('S') or 'SENTET' in s:return 'SENTETİK'
    return s
def dt(v):
    if isinstance(v,datetime):return v.date()
    if isinstance(v,date):return v
    s=txt(v)[:10]
    for f in ('%Y-%m-%d','%d.%m.%Y','%d/%m/%Y','%Y/%m/%d'):
        try:return datetime.strptime(s,f).date()
        except:pass
    return None
def secs(v):
    s=txt(v).replace(',','.')
    m=re.search(r'(\d+):(\d+(?:\.\d+)?)',s)
    if m:return int(m.group(1))*60+float(m.group(2))
    return num(s)
def raceclass(v):
    s=txt(v).upper()
    for p in (r'HANDİKAP\s*[- ]?\s*(\d+)',r'\bH\s*(\d+)',r'ŞARTLI\s*(\d+)',r'ŞART\s*(\d+)',r'\bKV\s*[- ]?\s*(\d+)',r'\bG\s*(\d+)'):
        m=re.search(p,s)
        if m:return int(m.group(1))
    return None
def history(h): return [r for r in h.get('_history',[]) if isinstance(r,dict)]
def workouts(h): return [r for r in h.get('_workouts',[]) if isinstance(r,dict)]
def last(rows,n):
    rr=rows[:]
    if any(dt(r.get('date') or r.get('tarih')) for r in rr): rr.sort(key=lambda r:dt(r.get('date') or r.get('tarih')) or date.min,reverse=True)
    return rr[:n]
def rate(xs): return sum(xs)/len(xs) if xs else None
def mean(xs): return sum(xs)/len(xs) if xs else None

def target(race):
    m=race.get('meta') if isinstance(race.get('meta'),dict) else {}
    return {'distance':dist({'distance':race.get('distance') or m.get('distance')}),'surface':surf(race.get('surface') or m.get('surface')),'condition':txt(race.get('condition') or m.get('detail') or m.get('raceName'))}

def same(r,t,tol=0):
    d=dist(r); td=t['distance']; s=surf(r.get('surface') or r.get('pist')); ts=t['surface']
    return (not ts or not s or s==ts) and (td is None or d is None or abs(d-td)<=tol)

def extract(h,race,all_horses=None,target_date=None,target_year=None):
    rows=history(h); ws=workouts(h); t=target(race); all_horses=all_horses or [h]; td=dt(target_date) or date.today()
    exact=[r for r in rows if same(r,t,0)]; near=[r for r in rows if same(r,t,100)]
    surf_rows=[r for r in rows if surf(r.get('surface') or r.get('pist'))==t['surface']]
    places=[place(r) for r in rows if place(r) is not None]; ep=[place(r) for r in exact if place(r) is not None]
    times=[secs(r.get('time') or r.get('derece') or r.get('süre')) for r in near]; times=[x for x in times if x and x>0]
    speeds=[]
    for r in surf_rows:
        d=dist(r); s=secs(r.get('time') or r.get('derece') or r.get('süre'))
        if d and s and s>0:speeds.append(d/s*3.6)
    hpvals=[hp(x) for x in rows if hp(x) is not None]
    weights=[weight(x) for x in rows if weight(x) is not None]
    current_w=weight(h)
    sim=[place(x) for x in rows if current_w is not None and weight(x) is not None and abs(weight(x)-current_w)<=1 and place(x) is not None]
    recent=last(rows,6); rp=[place(x) for x in recent if place(x) is not None]
    w5=last(ws,5); wt=[]
    for w in w5:
        for k in ('m600','600','m400','400','m200','200','time','derece'):
            x=secs(w.get(k))
            if x and x>0: wt.append(x); break
    dates=[dt(x.get('date') or x.get('tarih')) for x in rows]; dates=[x for x in dates if x]
    same_j=[x for x in rows if txt(x.get('jockey') or x.get('jokey') or x.get('Jokey'))==txt(h.get('jockey') or h.get('jokey') or h.get('Jokey')) and txt(h.get('jockey') or h.get('jokey') or h.get('Jokey'))]
    same_t=[x for x in rows if txt(x.get('trainer') or x.get('antrenor') or x.get('Antrenör'))==txt(h.get('trainer') or h.get('antrenor') or h.get('Antrenör')) and txt(h.get('trainer') or h.get('antrenor') or h.get('Antrenör'))]
    feats={
      1:{'sample':len([x for x in rows if raceclass(x.get('raceName') or x.get('className') or x.get('race_type'))==raceclass(t['condition'])]),'same_class_win_rate':rate([place(x)==1 for x in rows if raceclass(x.get('raceName') or x.get('className') or x.get('race_type'))==raceclass(t['condition']) and place(x) is not None])},
      2:{'exact_sample':len(exact),'exact_win_rate':rate([place(x)==1 for x in exact if place(x) is not None]),'exact_top3_rate':rate([place(x)<=3 for x in exact if place(x) is not None]),'exact_avg_place':mean(ep),'near_100m_sample':len(near)},
      3:{'surface_sample':len(surf_rows),'surface_win_rate':rate([place(x)==1 for x in surf_rows if place(x) is not None]),'surface_top3_rate':rate([place(x)<=3 for x in surf_rows if place(x) is not None])},
      4:{'sample':len(times),'best_time':min(times) if times else None,'avg_time':mean(times)},
      5:{'sample':len(speeds),'best_speed_kmh':max(speeds) if speeds else None,'avg_speed_kmh':mean(speeds),'recent_avg_speed_kmh':mean([x for r in last(surf_rows,6) for x in [((dist(r) or 0)/((secs(r.get('time') or r.get('derece') or r.get('süre')) or 0)*1.0)*3.6) if dist(r) and secs(r.get('time') or r.get('derece') or r.get('süre')) else None] if x])},
      6:{'sample_10':len(places),'sample_6':len(rp),'avg_place_6':mean(rp),'win_rate_6':rate([x==1 for x in rp]),'top3_rate_6':rate([x<=3 for x in rp])},
      7:{'shared_race_links':0,'shared_opponents_detected':0},
      8:{'today_weight':current_w,'historical_avg_weight':mean(weights),'similar_weight_sample':len(sim),'similar_weight_avg_place':mean(sim),'similar_weight_top3_rate':rate([x<=3 for x in sim])},
      9:{'current_hp':hp(h),'historical_avg_hp':mean(hpvals),'max_hp':max(hpvals) if hpvals else None,'recent_avg_hp':mean([hp(x) for x in recent if hp(x) is not None])},
      10:{'sample_5':len(w5),'timed_sample':len(wt),'best_recent_time':min(wt) if wt else None,'avg_recent_time':mean(wt)},
      11:{'sample':len(wt),'recent_to_previous_change':(wt[0]-wt[-1]) if len(wt)>=2 else None},
      12:{'days_since_last_race':(td-dates[0]).days if dates else None},
      13:{'races_30d':sum(0<=(td-x).days<=30 for x in dates),'races_60d':sum(0<=(td-x).days<=60 for x in dates),'races_90d':sum(0<=(td-x).days<=90 for x in dates)},
      14:{'current_post':num(h.get('st') or h.get('St') or h.get('start')),'historical_post_sample':len([x for x in rows if num(x.get('post') or x.get('start') or x.get('kulvar')) is not None])},
      15:{'sample':0,'observed':[]},
      16:{'horse_jockey_sample':len(same_j),'horse_jockey_avg_place':mean([place(x) for x in same_j if place(x) is not None]),'horse_jockey_win_rate':rate([place(x)==1 for x in same_j if place(x) is not None])},
      17:{'horse_trainer_sample':len(same_t),'horse_trainer_avg_place':mean([place(x) for x in same_t if place(x) is not None]),'horse_trainer_win_rate':rate([place(x)==1 for x in same_t if place(x) is not None])},
      18:{'origin':txt(h.get('origin') or h.get('orijin') or h.get('Orijin')),'origin_present':bool(txt(h.get('origin') or h.get('orijin') or h.get('Orijin')))},
      19:{'history_prize_sample':sum(1 for x in rows if any(num(x.get(k)) is not None for k in ('prize','ikramiye','earnings','kazanc','kazanç')))},
      20:{'odds':num(h.get('odds') or h.get('gny') or h.get('Gny')),'agf':num(h.get('agf') or h.get('AGF'))}
    }
    # Common-rival links: exact shared date/city/distance/race signature.
    mine=set((txt(x.get('date') or x.get('tarih')),txt(x.get('city') or x.get('hipodrom')),dist(x),txt(x.get('raceName') or x.get('kosu'))) for x in rows)
    links=0; opponents=0
    for o in all_horses:
        if o is h: continue
        os=set((txt(x.get('date') or x.get('tarih')),txt(x.get('city') or x.get('hipodrom')),dist(x),txt(x.get('raceName') or x.get('kosu'))) for x in history(o))
        n=len(mine & os)
        if n: links+=n; opponents+=1
    feats[7]={'shared_race_links':links,'shared_opponents_detected':opponents}
    return {'data_ready':bool(rows or ws),'history_count':len(rows),'workout_count':len(ws),'families':{FAMILY_NAMES[i]:{'family_id':i,'features':feats[i]} for i in range(1,21)}}

def attach_feature_vectors(horses,race,target_date=None):
    out=[]
    for h in horses:
        x=dict(h)
        x['_feature_vector']=extract(x,race,horses,target_date=getattr(target_date,'isoformat',lambda:target_date)(),target_year=(target_date.year if hasattr(target_date,'year') else None))
        out.append(x)
    return out

def empirical_score(*args,**kwargs):
    # Bilerek None: öğrenilmiş gerçek sonuç ağırlıkları henüz verilmeden skor üretilmez.
    return None

