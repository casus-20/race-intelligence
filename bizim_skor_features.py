"""BİZİM SKOR gerçek TJK özellik çıkarma katmanı.

Bu dosya skor ağırlığı vermez ve skor hesaplamaz. TJK'dan indirilen gerçek
koşu geçmişi/galop verisini 20 özellik ailesine ayırır. 1500 puanlık model
ampirik eğitimden sonra ayrıca bağlanacaktır.
"""
from __future__ import annotations
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

try:
    from race_condition_engine import parse_race_condition, race_condition_signature, evaluate_eligibility
except Exception:
    parse_race_condition = race_condition_signature = evaluate_eligibility = None


def _first(d: Dict[str, Any], keys, default=None):
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
    m = re.search(r"(\d+):(\d+(?:\.\d+)?)", s)
    if m: return float(m.group(1))*60 + float(m.group(2))
    return _num(s)


def _norm(v):
    return (str(v or "").strip().lower().replace("ı","i").replace("ş","s")
            .replace("ğ","g").replace("ü","u").replace("ö","o").replace("ç","c"))


def _surface(row):
    s = _norm(_first(row,["surface","pist","Pist","Surface","trackSurface","track_surface",
                           "surfaceType","surface_type","track","trackType","track_type",
                           "zemin","Zemin","pistTuru","pist_turu","PistTuru","surfaceName",
                           "surface_name","pistAdi","pist_adi","zeminTuru","zemin_turu"],""))
    if s.startswith(("k:","k-")) or s == "k": return "kum"
    if s.startswith(("c:","c-","cim:")) or s in ("c","cim"): return "cim"
    if s.startswith(("s:","s-")) or s == "s": return "sentetik"
    if any(x in s for x in ("cim","grass","turf")): return "cim"
    if any(x in s for x in ("sentetik","synthetic","polytrack","fiber")): return "sentetik"
    if any(x in s for x in ("kum","dirt","sand")): return "kum"
    return s


def _dt(v):
    if isinstance(v, datetime): return v.date()
    if isinstance(v, date): return v
    s = str(v or "").strip()
    for f in ("%d.%m.%Y","%d/%m/%Y","%Y-%m-%d","%Y/%m/%d"):
        try: return datetime.strptime(s[:10], f).date()
        except Exception: pass
    m = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        try: return date(int(m.group(1)),int(m.group(2)),int(m.group(3)))
        except Exception: pass
    return None


def _history(h):
    x=h.get("_history",[])
    return [r for r in x if isinstance(r,dict)] if isinstance(x,list) else []


def _workouts(h):
    x=h.get("_workouts",[])
    return [r for r in x if isinstance(r,dict)] if isinstance(x,list) else []


def _place(r):
    x=_num(_first(r,["place","sira","S","finish"],None))
    return x if x is not None and x>0 else None


def _dist(r): return _num(_first(r,["distance","msf","mesafe"],None))
def _wt(r): return _num(_first(r,["weight","kilo","siklet","Sıklet"],None))
def _hp(r): return _num(_first(r,["hp","HP","handicap","handikap"],None))
def _rt(r): return _time(_first(r,["time","derece","Derece"],None))
def _class(r): return str(_first(r,["className","class","sinif","Sınıf","raceName","race_name","kosu","Koşu","condition"],"") or "")


def _stats(rows):
    p=[x for x in (_place(r) for r in rows) if x is not None]
    if not p: return {"sample":0}
    return {"sample":len(p),"wins":sum(x==1 for x in p),"top3":sum(x<=3 for x in p),
            "top5":sum(x<=5 for x in p),"avg_place":round(sum(p)/len(p),4),"best_place":min(p)}


def _time_stats(rows):
    vals=[]
    for r in rows:
        t,d=_rt(r),_dist(r)
        if t is not None and d and d>0: vals.append((t,t/(d/1000)))
    if not vals:return {"sample":0}
    raw=[x[0] for x in vals]; n=[x[1] for x in vals]
    return {"sample":len(vals),"best_time_sec":min(raw),"avg_time_sec":round(sum(raw)/len(raw),4),
            "best_sec_per_km":min(n),"avg_sec_per_km":round(sum(n)/len(n),4),"latest_sec_per_km":n[0]}


def _today(race):
    meta=race.get("meta") if isinstance(race.get("meta"),dict) else {}
    return {"distance":_num(_first(race,["distance"],_first(meta,["distance"],None))),
            "surface":_surface({"surface":_first(race,["surface"],_first(meta,["surface"],""))}),
            "class":str(_first(race,["condition","race_type","raceName"],_first(meta,["detail","raceName","condition"],"")) or "")}


def _common(horse, horses):
    own={}
    for r in _history(horse):
        key=(str(_first(r,["date","tarih"],"")),_norm(_first(r,["city","hipodrom","sehir"],"")),_dist(r))
        p=_place(r)
        if key[0] and key[2] is not None and p is not None: own[key]=p
    c=[]
    for other in horses:
        if other is horse: continue
        for r in _history(other):
            key=(str(_first(r,["date","tarih"],"")),_norm(_first(r,["city","hipodrom","sehir"],"")),_dist(r))
            if key in own:
                p=_place(r)
                if p is not None:c.append(p-own[key])
    return {"shared_races":len(c),"better_than_rival":sum(x>0 for x in c),"same":sum(x==0 for x in c),
            "worse_than_rival":sum(x<0 for x in c),"avg_place_diff":round(sum(c)/len(c),4) if c else None}


def _workout(h):
    ws=_workouts(h)[:5]
    out={"sample":len(ws)}
    if not ws:return out
    for k in ("m1200","m1000","m800","m600","m400","m200"):
        vals=[_time(_first(w,[k,k.replace("m",""),k+"m"],None)) for w in ws]
        vals=[x for x in vals if x is not None]
        if vals:
            out[f"latest_{k}"]=vals[0];out[f"avg_{k}_last5"]=round(sum(vals)/len(vals),4);out[f"best_{k}_last5"]=min(vals)
    d=_dt(_first(ws[0],["date","tarih"],None))
    if d:out["latest_date"]=d.isoformat()
    return out


def _rest(history,target):
    ds=[_dt(_first(r,["date","tarih"],None)) for r in history]
    ds=[d for d in ds if d]
    if not ds or not target:return {"sample":0}
    return {"sample":len(ds),"days_since_last_race":(target-ds[0]).days,
            "races_last30":sum(0<=(target-d).days<=30 for d in ds),
            "races_last60":sum(0<=(target-d).days<=60 for d in ds),
            "races_last90":sum(0<=(target-d).days<=90 for d in ds)}


def _identity(h, names):
    cur=str(_first(h,names,"") or ""); n=_norm(cur); vals=[_norm(_first(r,names,"")) for r in _history(h)]
    vals=[x for x in vals if x]
    return {"current":cur,"history_sample":len(vals),"same_identity_count":sum(x==n for x in vals) if n else 0}


def build_feature_vector(horse, race, all_horses=None, target_date=None):
    hs=_history(horse); ws=_workouts(horse); horses=all_horses or [horse]; t=_today(race)
    td=_dt(target_date) or _dt(_first(race,["date","tarih"],None))
    exact=[r for r in hs if t["surface"] and _surface(r)==t["surface"] and t["distance"] is not None and _dist(r)==t["distance"]]
    near=[r for r in hs if t["surface"] and _surface(r)==t["surface"] and t["distance"] is not None and _dist(r) is not None and abs(_dist(r)-t["distance"])<=100]
    surf=[r for r in hs if t["surface"] and _surface(r)==t["surface"]]
    recent=hs[:6]
    hp=[_hp(r) for r in hs if _hp(r) is not None]; weights=[_wt(r) for r in hs if _wt(r) is not None]
    classes=[_class(r) for r in recent if _class(r)]
    condition=None; elig=None
    if parse_race_condition:
        try:
            rc=parse_race_condition(race); condition=rc.to_dict() if hasattr(rc,"to_dict") else None
            if evaluate_eligibility: elig=evaluate_eligibility(horse,race)
        except Exception: pass
    sig=None
    if parse_race_condition and race_condition_signature:
        try:sig=race_condition_signature(parse_race_condition(race))
        except Exception:pass
    rest=_rest(hs,td)
    return {
      "data_version":1,"data_ready":bool(hs or ws),"history_count":len(hs),"workout_count":len(ws),
      "01_kosu_sarti_uyumu":{"today_class":t["class"],"history_class_sample":len(classes),"condition":condition,"condition_signature":sig,"eligibility":elig},
      "02_pist_mesafe":{"target_surface":t["surface"],"target_distance":t["distance"],"exact_sample":len(exact),"exact_wins":_stats(exact).get("wins",0),"exact_top3":_stats(exact).get("top3",0),"exact_top5":_stats(exact).get("top5",0),"exact_avg_place":_stats(exact).get("avg_place"),"near_sample":len(near),"near_avg_place":_stats(near).get("avg_place")},
      "03_pist_performansi":_stats(surf),
      "04_gercek_derece":{"exact":_time_stats(exact),"same_surface":_time_stats(surf),"recent":_time_stats(recent)},
      "05_gercek_hiz":{"exact_best_sec_per_km":_time_stats(exact).get("best_sec_per_km"),"exact_avg_sec_per_km":_time_stats(exact).get("avg_sec_per_km"),"surface_best_sec_per_km":_time_stats(surf).get("best_sec_per_km"),"surface_avg_sec_per_km":_time_stats(surf).get("avg_sec_per_km"),"recent_latest_sec_per_km":_time_stats(recent).get("latest_sec_per_km")},
      "06_guncel_form":_stats(recent),
      "07_ortak_rakip":_common(horse,horses),
      "08_kilo_performansi":{"today_weight":_wt(horse),"history_sample":len(weights),"history_avg_weight":round(sum(weights)/len(weights),4) if weights else None,"history_min_weight":min(weights) if weights else None,"history_max_weight":max(weights) if weights else None},
      "09_hp_kalite":{"today_hp":_hp(horse),"history_sample":len(hp),"history_avg_hp":round(sum(hp)/len(hp),4) if hp else None,"history_max_hp":max(hp) if hp else None,"history_min_hp":min(hp) if hp else None},
      "10_galop_performansi":_workout(horse),
      "11_galop_trend":{"workout_sample":len(ws),"recent_workout_count":min(len(ws),5)},
      "12_dinlenme_kgs":rest,
      "13_yaris_yogunlugu":{"races_last30":rest.get("races_last30"),"races_last60":rest.get("races_last60"),"races_last90":rest.get("races_last90")},
      "14_start_kulvar":{"history_sample":sum(_num(_first(r,["post","start","kulvar","st"],None)) is not None for r in hs)},
      "15_tempo_yaris_senaryosu":{"position_fields_available":any(any(k in r for k in ("position","pos","tempo","split","ilk400","ilk600")) for r in hs)},
      "16_jokey_etkisi":_identity(horse,["jockey","jokey","Jokey"]),
      "17_antrenor_etkisi":_identity(horse,["trainer","antrenor","Antrenör"]),
      "18_orijin_pedigri":{"origin":str(_first(horse,["origin","orijin","Orijin","pedigree","baba_anne"],"") or "")},
      "19_kazanc_kariyer":{"total":_first(horse,["_tjk_total_earnings","totalEarnings","total_earnings","lifetimeEarnings","careerEarnings","totalKazanc","toplamKazanc","kazanc","Kazanç","earnings"],None),"year":_first(horse,["_tjk_year_earnings","yearEarnings","year_earnings","yearlyEarnings","annualEarnings","yearKazanc","buYilKazanc"],None)},
      "20_piyasa_sinyali":{"odds":_num(_first(horse,["odds","gny","Gny"],None)),"agf":_num(_first(horse,["agf","AGF"],None))},
    }


def attach_feature_vectors(horses, race, target_date=None):
    out=[dict(h) for h in horses if isinstance(h,dict)]
    for h in out:
        f=build_feature_vector(h,race,out,target_date)
        h["_feature_vector"]=f; h["_feature_data_ready"]=bool(f["data_ready"])
        h["_feature_history_count"]=f["history_count"]; h["_feature_workout_count"]=f["workout_count"]
        h["_bizim_skor"]=None
    return out


def calculate_bizim_ranking(horses, race):
    # Ampirik 1500 puan modeli bağlanana kadar bilinçli olarak puan üretmez.
    return []

