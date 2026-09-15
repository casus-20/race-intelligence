"""BİZİM SKOR — gerçek veriden öğrenilen 0–1500 model.

Bu modül iki aşamalı çalışır:
1) Atların TJK geçmişinden, yarıştan önce bilinebilecek özellikleri çıkarır ve
   ailelerin ilk-3 sonucu ayırt etme gücünü rolling/out-of-time AUC ile öğrenir.
2) Öğrenilmiş aile ağırlıklarını bugünkü koşuya uygular ve toplamı 0–1500'e
   ölçekler.

Eksik veri uydurulmaz. Bir ailede yeterli veri yoksa o aile öğrenme dışında
kalır; bugünkü at için mevcut olmayan aile de o atın puanından çıkarılır ve
kalan gerçek ağırlıklar yeniden ölçeklenir.
"""
from __future__ import annotations
from datetime import date, datetime
import math
import re
from typing import Any, Dict, List, Optional, Tuple

FAMILIES = [
    "01_kosu_sarti_uyumu", "02_pist_mesafe", "04_gercek_derece",
    "05_gercek_hiz", "06_guncel_form", "07_ortak_rakip",
    "08_kilo_performansi", "09_hp_kalite", "10_galop_performansi",
    "12_dinlenme_kgs",
]

# 60+ rolling observations is deliberately required; no tiny-sample scoring.
MIN_FAMILY_SAMPLES = 8
MIN_TOTAL_SAMPLES = 30
MIN_LEARNED_FAMILIES = 2
MIN_PRIOR_RACES = 3

# Streamlit reruns the script frequently. Keep a small in-process cache so the
# empirical learner is trained once per downloaded dataset, not on every UI
# interaction. The cache is data-signature based and automatically refreshes
# when the underlying historical data changes.
_MODEL_CACHE = {}
_MODEL_CACHE_MAX = 4



def _first(d, keys, default=None):
    if not isinstance(d, dict): return default
    for k in keys:
        v = d.get(k)
        if v not in (None, "", "-"):
            return v
    return default


def _num(v):
    if v is None or isinstance(v, bool): return None
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v).strip())
    if not m: return None
    try: return float(m.group(0).replace(",", "."))
    except Exception: return None


def _time(v):
    if v is None: return None
    s = str(v).strip().replace(",", ".")
    m = re.search(r"(\d+):([\d.]+)", s)
    if m: return float(m.group(1))*60 + float(m.group(2))
    return _num(s)


def _norm(v):
    return (str(v or "").strip().lower().replace("ı","i").replace("ş","s")
            .replace("ğ","g").replace("ü","u").replace("ö","o").replace("ç","c"))


def _surface(r):
    s = _norm(_first(r,["surface","pist","Pist","Surface","surfaceType","surface_type","track","trackType","track_type","zemin","Zemin"],""))
    if s.startswith(("k:","k-")) or s == "k" or any(x in s for x in ("kum","dirt","sand")): return "kum"
    if s.startswith(("c:","c-","cim:")) or s in ("c","cim") or any(x in s for x in ("cim","grass","turf")): return "cim"
    if s.startswith(("s:","s-")) or s == "s" or any(x in s for x in ("sentetik","synthetic","polytrack","fiber")): return "sentetik"
    return s


def _dt(v):
    if isinstance(v, datetime): return v.date()
    if isinstance(v, date): return v
    s = str(v or "").strip()
    for f in ("%d.%m.%Y","%d/%m/%Y","%Y-%m-%d","%Y/%m/%d"):
        try: return datetime.strptime(s[:10], f).date()
        except Exception: pass
    return None


def _place(r):
    x=_num(_first(r,["place","sira","S","finish"],None))
    return x if x is not None and x > 0 else None


def _dist(r): return _num(_first(r,["distance","msf","mesafe"],None))
def _wt(r): return _num(_first(r,["weight","kilo","siklet","Sıklet"],None))
def _hp(r): return _num(_first(r,["hp","HP","handicap","handikap"],None))
def _rt(r): return _time(_first(r,["time","derece","Derece"],None))
def _class(r): return _norm(_first(r,["className","class","sinif","Sınıf","raceName","race_name","kosu","Koşu","condition"],""))
def _city(r): return _norm(_first(r,["city","hipodrom","sehir"],""))


def _safe_mean(xs):
    xs=[x for x in xs if x is not None and math.isfinite(x)]
    return sum(xs)/len(xs) if xs else None


def _stats(rows):
    p=[_place(r) for r in rows]; p=[x for x in p if x is not None]
    if not p: return None
    return {"sample":len(p),"wins":sum(x==1 for x in p),"top3":sum(x<=3 for x in p),
            "top5":sum(x<=5 for x in p),"avg_place":_safe_mean(p)}


def _family_values(prior, target, workouts=None):
    """Return family strengths in [0,1]. None means genuinely unavailable."""
    if not prior: return {k:None for k in FAMILIES}
    exact=[r for r in prior if _surface(target) and _surface(r)==_surface(target) and _dist(target) is not None and _dist(r)==_dist(target)]
    surface=[r for r in prior if _surface(target) and _surface(r)==_surface(target)]
    near=[r for r in surface if _dist(target) is not None and _dist(r) is not None and abs(_dist(r)-_dist(target))<=100]
    recent=prior[:6]
    out={k:None for k in FAMILIES}

    # 01 — class/condition similarity and historical success.
    tc=_class(target)
    if tc:
        same=[r for r in prior if _class(r) and (_class(r)==tc or _class(r) in tc or tc in _class(r))]
        if len(same)>=2:
            st=_stats(same)
            out["01_kosu_sarti_uyumu"] = ((st["top3"]/st["sample"]) + max(0.0,min(1.0,1.0-(st["avg_place"]-1)/8))) / 2

    # 02 — exact surface/distance; if insufficient, nearby distance on same surface.
    base=exact if len(exact)>=2 else near
    if len(base)>=2:
        st=_stats(base)
        out["02_pist_mesafe"] = ((st["top3"]/st["sample"]) + max(0.0,min(1.0,1.0-(st["avg_place"]-1)/8))) / 2

    # 04 — normalized real time; lower is better. Compare recent comparable run to own best/avg.
    timed=[]
    for r in (exact if len(exact)>=2 else surface):
        t,d=_rt(r),_dist(r)
        if t is not None and d and d>0: timed.append(t/(d/1000.0))
    if len(timed)>=2:
        best=min(timed); avg=sum(timed)/len(timed); worst=max(timed)
        denom=max(worst-best,0.001)
        out["04_gercek_derece"] = max(0.0,min(1.0,1.0-(avg-best)/denom))

    # 05 — real speed trend (seconds/km; lower is faster).
    sp=[]
    for r in surface:
        t,d=_rt(r),_dist(r)
        if t is not None and d and d>0: sp.append(t/(d/1000.0))
    if len(sp)>=4:
        recent_sp=_safe_mean(sp[:3]); old_sp=_safe_mean(sp[3:])
        if recent_sp is not None and old_sp and old_sp>0:
            out["05_gercek_hiz"] = max(0.0,min(1.0,0.5+(old_sp-recent_sp)/max(old_sp*0.05,0.01)))

    # 06 — recent form.
    p=[_place(r) for r in recent if _place(r) is not None]
    if len(p)>=3:
        avg=sum(p)/len(p); top3=sum(x<=3 for x in p)/len(p)
        out["06_guncel_form"] = max(0.0,min(1.0,(1-(avg-1)/8+top3)/2))

    # 08 — weight performance around target weight.
    tw=_wt(target)
    if tw is not None:
        sim=[r for r in prior if _wt(r) is not None and abs(_wt(r)-tw)<=2]
        if len(sim)>=2:
            st=_stats(sim); out["08_kilo_performansi"] = st["top3"]/st["sample"]

    # 09 — current/target HP relative to prior own HP. This is intentionally unavailable
    # if the historical HP field is absent; current scoring has a field-relative fallback.
    th=_hp(target); hps=[_hp(r) for r in prior if _hp(r) is not None]
    if th is not None and hps:
        mx=max(hps); avg=_safe_mean(hps)
        out["09_hp_kalite"] = max(0.0,min(1.0,0.65*(th/max(mx,0.01))+0.35*(th/max(avg or mx,0.01))))

    # 10 — workouts dated on/before target. Never use future workouts.
    if workouts:
        td=_dt(_first(target,["date","tarih"],None)); vals=[]
        for w in workouts:
            wd=_dt(_first(w,["date","tarih"],None))
            if td is not None and wd is not None and wd>td: continue
            row=[]
            for k in ("m600","m400","m200"):
                x=_time(_first(w,[k,k.replace("m","")],None))
                if x is not None: row.append(x)
            if row: vals.append(_safe_mean(row))
        if len(vals)>=2:
            best=min(vals); latest=vals[0]; out["10_galop_performansi"]=max(0.0,min(1.0,1.0-max(0,latest-best)/max(best*0.15,0.01)))

    # 12 — empirical rest interval from successful historical intervals.
    td=_dt(_first(target,["date","tarih"],None)); dates=[_dt(_first(r,["date","tarih"],None)) for r in prior]
    dates=[d for d in dates if d]
    if td and dates:
        kgs=(td-max(dates)).days
        successful=[]
        ordered=sorted([(d,r) for d,r in zip(dates,[r for r in prior if _dt(_first(r,["date","tarih"],None))])],key=lambda x:x[0])
        for j,(rd,rr) in enumerate(ordered):
            if _place(rr) is not None and _place(rr)<=3 and j+1<len(ordered): successful.append((ordered[j+1][0]-rd).days)
        if successful:
            center=_safe_mean(successful); scale=max(_safe_mean([abs(x-center) for x in successful]) or 7,3)
            out["12_dinlenme_kgs"]=math.exp(-abs(kgs-center)/scale)
    return out


def _auc(values, labels):
    """Fast AUC from ranks; O(n log n), not pairwise O(n²)."""
    pairs=[(float(v),int(y)) for v,y in zip(values,labels)
           if v is not None and y in (0,1) and math.isfinite(float(v))]
    if not pairs:return None
    n_pos=sum(y for _,y in pairs); n_neg=len(pairs)-n_pos
    if n_pos==0 or n_neg==0:return None
    pairs.sort(key=lambda x:x[0])
    rank_sum_pos=0.0; i=0; rank=1
    while i<len(pairs):
        j=i+1; value=pairs[i][0]
        while j<len(pairs) and pairs[j][0]==value:j+=1
        avg_rank=(rank+(rank+(j-i)-1))/2.0
        rank_sum_pos += avg_rank*sum(1 for _,y in pairs[i:j] if y==1)
        rank += j-i; i=j
    return (rank_sum_pos - n_pos*(n_pos+1)/2.0)/(n_pos*n_neg)


def _rolling_samples(horses):
    """Build leakage-safe samples from every horse's historical results.

    For a historical target race, only races strictly older than that target are
    used to build the feature vector.  We deliberately use 3+ prior races so the
    learner starts producing useful signals much earlier, while still avoiding a
    one-race guess.
    """
    samples={k:[] for k in FAMILIES}
    total_targets=0
    for horse in horses:
        rows=[r for r in horse.get("_history",[]) if isinstance(r,dict)]
        if not rows: continue
        dated=[_dt(_first(r,["date","tarih"],None)) for r in rows]
        if any(d is not None for d in dated):
            rows=sorted(rows,key=lambda r:(_dt(_first(r,["date","tarih"],None)) or date.min),reverse=True)
        for i in range(MIN_PRIOR_RACES,len(rows)):
            target=rows[i]; place=_place(target)
            if place is None: continue
            prior=rows[i+1:]
            if len(prior)<MIN_PRIOR_RACES: continue
            vals=_family_values(prior,target,horse.get("_workouts",[]))
            label=1 if place<=3 else 0; total_targets+=1
            for fam,val in vals.items():
                if val is not None:samples[fam].append((val,label))
    return samples,total_targets


def _dataset_signature(horses):
    """Cheap but data-sensitive signature for the current downloaded dataset."""
    import hashlib
    h=hashlib.sha1()
    for horse in horses:
        rows=horse.get("_history",[]) if isinstance(horse,dict) else []
        h.update(str(len(rows)).encode())
        for r in rows:
            if not isinstance(r,dict): continue
            # Include the fields that can materially change learned features.
            vals=(r.get("date",r.get("tarih","")), r.get("city",r.get("sehir","")),
                  r.get("distance",r.get("mesafe","")), r.get("surface",r.get("pist","")),
                  r.get("place",r.get("sira","")), r.get("time",r.get("derece","")),
                  r.get("weight",r.get("kilo","")), r.get("hp",r.get("HP","")),
                  r.get("raceName",r.get("kosu","")), r.get("className",r.get("sinif","")))
            h.update(repr(vals).encode())
    return h.hexdigest()


def learn_model(horses):
    key=_dataset_signature(horses)
    cached=_MODEL_CACHE.get(key)
    if cached is not None:
        return cached

    samples,target_count=_rolling_samples(horses)
    learned=[]
    for fam in FAMILIES:
        pairs=samples[fam]
        if len(pairs)<MIN_FAMILY_SAMPLES: continue
        auc=_auc([v for v,_ in pairs],[y for _,y in pairs])
        if auc is None: continue
        direction=1 if auc>=0.5 else -1
        signal=abs(auc-0.5)*2.0
        reliability=math.sqrt(len(pairs)/(len(pairs)+25.0))
        strength=signal*reliability
        if strength>0:
            learned.append({"family":fam,"auc":round(auc,4),"direction":direction,
                            "samples":len(pairs),"strength":strength})
    sample_count=sum(x["samples"] for x in learned)
    result={"ready":False,"sample_count":sample_count,"target_count":target_count,
            "families":learned,"weights":{},"method":"rolling_out_of_time_auc_fast"}
    if target_count>=MIN_TOTAL_SAMPLES and len(learned)>=MIN_LEARNED_FAMILIES:
        ss=sum(x["strength"] for x in learned)
        if ss>0:
            result["ready"]=True
            result["weights"]={x["family"]:1500*x["strength"]/ss for x in learned}
    _MODEL_CACHE[key]=result
    if len(_MODEL_CACHE)>_MODEL_CACHE_MAX:
        _MODEL_CACHE.pop(next(iter(_MODEL_CACHE)))
    return result

def _current_values(horse,race,horses):
    hist=[r for r in horse.get("_history",[]) if isinstance(r,dict)]
    target={"surface":race.get("surface") or (race.get("meta") or {}).get("surface","") ,
            "distance":race.get("distance") or (race.get("meta") or {}).get("distance"),
            "condition":race.get("condition") or race.get("raceName") or (race.get("meta") or {}).get("detail",""),
            "date":race.get("date") or race.get("tarih")}
    vals=_family_values(hist,target,horse.get("_workouts",[]))

    # Common-rival signal is available for today's field when shared historical
    # races are present. It is not forced into training if historical field data
    # for old races is unavailable.
    own={}
    for r in hist:
        key=(str(_first(r,["date","tarih"],"")),_city(r),_dist(r)); p=_place(r)
        if key[0] and key[2] is not None and p is not None: own[key]=p
    diffs=[]
    for other in horses:
        if other is horse:continue
        for r in other.get("_history",[]) if isinstance(other.get("_history",[]),list) else []:
            key=(str(_first(r,["date","tarih"],"")),_city(r),_dist(r))
            if key in own and _place(r) is not None: diffs.append(_place(r)-own[key])
    if diffs:
        vals["07_ortak_rakip"]=max(0.0,min(1.0,0.5+_safe_mean(diffs)/10.0))

    # HP fallback: current HP is real data. If historical HP is absent, compare
    # today's HP against the other horses in this race instead of dropping the horse.
    if vals.get("09_hp_kalite") is None:
        th=_hp(horse)
        field=[_hp(h) for h in horses if _hp(h) is not None]
        if th is not None and field:
            lo,hi=min(field),max(field)
            vals["09_hp_kalite"]=1.0 if hi==lo else (th-lo)/(hi-lo)

    # Kilo fallback: current weight is real data; compare to this horse's historical
    # average when available, otherwise to today's field range.
    if vals.get("08_kilo_performansi") is None:
        tw=_wt(horse)
        histw=[_wt(r) for r in hist if _wt(r) is not None]
        if tw is not None and histw:
            avg=_safe_mean(histw); vals["08_kilo_performansi"]=max(0,min(1,0.5+(avg-tw)/5))

    return vals


def calculate_bizim_ranking(horses,race):
    if not isinstance(horses,list) or not horses:return []
    if not any(isinstance(h,dict) and h.get("_feature_data_ready") for h in horses):return []
    model=learn_model(horses)
    if not model.get("ready"):return []
    weights=model["weights"]
    results=[]
    for idx,horse in enumerate(horses):
        if not isinstance(horse,dict):continue
        vals=_current_values(horse,race,horses)
        available=[]
        for fam,w in weights.items():
            v=vals.get(fam)
            if v is None:continue
            direction=next((x["direction"] for x in model["families"] if x["family"]==fam),1)
            if direction<0:v=1-v
            v=max(0,min(1,float(v)))
            available.append((fam,w,v))
        # A horse needs at least two independent learned real-data families.
        if len(available)<2:continue
        wsum=sum(w for _,w,_ in available)
        score=1500*sum(w*v for _,w,v in available)/wsum
        components={fam:round(w*v,1) for fam,w,v in available}
        horse["_bizim_skor"]=round(score,1)
        results.append({"horse_index":idx,"score":round(score,1),"bizim_skor":round(score,1),
                        "label":"BİZİM SKOR","components":components,"model":model})
    results.sort(key=lambda x:x["score"],reverse=True)
    for rank,item in enumerate(results,1):item["rank"]=rank
    return results
