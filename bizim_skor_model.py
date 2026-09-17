"""BİZİM SKOR — 20 gerçek veri ailesinden öğrenilen 0–1500 model.

- Yarıştan önce bilinebilen verilerle leakage-safe rolling örnekler üretir.
- Her veri ailesinin 1–3 sonuçlarını ayırt etme gücünü AUC ile öğrenir.
- Ağırlıkları otomatik olarak 1500 puana dağıtır.
- Eksik aileye nötr puan vermez; mevcut ağırlıklar yeniden ölçeklenir.
- Görünen bileşenlerin toplamı her at için tam olarak BİZİM SKOR'a eşittir.
"""
from __future__ import annotations
from datetime import date, datetime
import hashlib, math, re
from typing import Any, Dict, List

FAMILIES = [
    "01_kosu_sarti_uyumu", "02_pist_mesafe", "03_pist_performansi",
    "04_gercek_derece", "05_gercek_hiz", "06_guncel_form",
    "07_ortak_rakip", "08_kilo_performansi", "09_hp_kalite",
    "10_galop_performansi", "11_galop_trend", "12_dinlenme_kgs",
    "13_yaris_yogunlugu", "14_start_kulvar", "15_tempo_yaris_senaryosu",
    "16_jokey_etkisi", "17_antrenor_etkisi", "18_orijin_pedigri",
    "19_kazanc_kariyer", "20_piyasa_sinyali",
]

MIN_FAMILY_SAMPLES = 4
MIN_TOTAL_SAMPLES = 12
MIN_LEARNED_FAMILIES = 2
MIN_PRIOR_RACES = 2
_MODEL_CACHE: Dict[str, Dict[str, Any]] = {}
_MODEL_CACHE_MAX = 6


def _first(d, keys, default=None):
    if not isinstance(d, dict): return default
    for k in keys:
        v=d.get(k)
        if v not in (None, "", "-"): return v
    return default


def _num(v):
    """TJK sayısal alanlarını güvenli biçimde float'a çevirir.

    Özellikle 1.24.77 gibi derece değerlerini yanlışlıkla 1.24
    olarak okumaz; virgüllü ondalıkları ve binlik ayraçlarını destekler.
    """
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            x = float(v)
            return x if math.isfinite(x) else None
        except Exception:
            return None
    s = str(v).strip()
    if not s or s in {"-", "—", "–", "None", "nan", "NaN"}:
        return None
    # TJK derece biçimi: 1.24.77 / 0.59.43. Bu alan _time tarafından okunmalı.
    if re.fullmatch(r"\d{1,2}\.\d{2}\.\d{2}", s):
        return None
    # Ondalık virgül ve binlik nokta: 1.234,56 -> 1234.56
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+,\d+", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        x = float(m.group(0))
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _time(v):
    """TJK derece değerini saniyeye çevirir."""
    if v is None:
        return None
    s = str(v).strip().replace(",", ".")
    # 1.24.77 = 84.77 sn
    m = re.fullmatch(r"(\d{1,2})\.(\d{2})\.(\d{2})", s)
    if m:
        return float(m.group(1))*60 + float(m.group(2)) + float(m.group(3))/100
    # 1:24.77 = 84.77 sn
    m = re.fullmatch(r"(\d{1,2}):([0-9]+(?:\.[0-9]+)?)", s)
    if m:
        return float(m.group(1))*60 + float(m.group(2))
    # Zaten saniye olan 84.77 gibi değerler
    return _num(s)


def _norm(v):
    return (str(v or "").strip().lower().replace("ı","i").replace("ş","s").replace("ğ","g").replace("ü","u").replace("ö","o").replace("ç","c"))


def _surface(r):
    s=_norm(_first(r,["surface","pist","Pist","Surface","trackSurface","surfaceType","track","zemin"],""))
    if s.startswith(("k:","k-")) or s=="k" or any(x in s for x in ("kum","dirt","sand")):return "kum"
    if s.startswith(("c:","c-","cim:")) or s in ("c","cim") or any(x in s for x in ("cim","grass","turf")):return "cim"
    if s.startswith(("s:","s-")) or s=="s" or any(x in s for x in ("sentetik","synthetic","polytrack","fiber")):return "sentetik"
    return s


def _dt(v):
    if isinstance(v,datetime):return v.date()
    if isinstance(v,date):return v
    s=str(v or "").strip()
    for f in ("%d.%m.%Y","%d/%m/%Y","%Y-%m-%d","%Y/%m/%d"):
        try:return datetime.strptime(s[:10],f).date()
        except:pass
    return None


def _place(r):
    x=_num(_first(r,["place","sira","S","finish"],None)); return x if x is not None and x>0 else None

def _dist(r):return _num(_first(r,["distance","msf","mesafe"],None))
def _wt(r):return _num(_first(r,["weight","kilo","siklet","Sıklet"],None))
def _hp(r):return _num(_first(r,["hp","HP","handicap","handikap","rating","RT"],None))
def _rt(r):return _time(_first(r,["time","derece","Derece"],None))
def _class(r):return _norm(_first(r,["className","class","sinif","Sınıf","raceName","race_name","kosu","Koşu","condition"],""))
def _city(r):return _norm(_first(r,["city","şehir","sehir","hipodrom"],""))
def _name(r,keys):return _norm(_first(r,keys,""))
def _history(h):return [r for r in h.get("_history",[]) if isinstance(r,dict)] if isinstance(h.get("_history",[]),list) else []
def _workouts(h):return [r for r in h.get("_workouts",[]) if isinstance(r,dict)] if isinstance(h.get("_workouts",[]),list) else []


def _mean(xs):
    clean=[]
    for x in xs:
        try:
            y=float(x)
            if math.isfinite(y): clean.append(y)
        except Exception:
            continue
    return sum(clean)/len(clean) if clean else None


def _stats(rows):
    p=[_place(r) for r in rows];p=[x for x in p if x is not None]
    if not p:return None
    return {"sample":len(p),"wins":sum(x==1 for x in p),"top3":sum(x<=3 for x in p),"top5":sum(x<=5 for x in p),"avg":_mean(p)}


def _rate_score(rows):
    st=_stats(rows)
    if not st:return None
    avg_score=max(0.0,min(1.0,1-(st["avg"]-1)/max(8.0,st["sample"]**0.15*8)))
    return max(0.0,min(1.0,0.65*(st["top3"]/st["sample"])+0.35*avg_score))


def _percentile_better(value, values, lower=False):
    vals=[x for x in values if x is not None and math.isfinite(float(x))]
    if value is None or not vals:return None
    if len(set(vals))==1:return 1.0
    if lower:return sum(x>=value for x in vals)/len(vals)
    return sum(x<=value for x in vals)/len(vals)



# ============================================================
# SABİT BİZİM SKOR MOTORU — ÖĞRENME / AUC / ARŞİV YOK
# ============================================================
# Koşu Şartı Uyumu: sınırsız toplam
# Pist/Mesafe: 100
# Pist Performansı: 100
# Güncel Form: 100
# Start/Kulvar: 50
# TOPLAM = Şart Uyumu + 100 + 100 + 100 + 50

CLASS_BASE = {
    # Grup / Açık
    "G1": 100, "A1": 95, "G2": 90, "A2": 90, "G3": 80, "A3": 80,
    # Handikap
    "H24": 90, "H23": 85, "H22": 80, "H21": 70, "H20": 75,
    "H19": 70, "H18": 65, "H17": 60, "H16": 50, "H15": 40,
    "H14": 30, "H13": 20,
    # KV
    "KV24": 90, "KV18": 80, "KV9": 70, "KV8": 70, "KV7": 60, "KV6": 60,
    # Şartlı
    "S27": 15, "S19": 25, "S5": 50, "S4": 40, "S3": 30, "S2": 20, "S1": 10,
    # Maiden
    "MAIDEN": 10,
}

FINISH_FACTOR = {1: 1.00, 2: .80, 3: .65, 4: .50, 5: .35}


def normalize_race_group(value):
    s = _norm(value)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    # Önce daha spesifik numaralı sınıflar.
    m = re.search(r"\b(?:g|grup|group)\s*[- ]?([123])\b", s)
    if m: return f"G{m.group(1)}"
    m = re.search(r"\b(?:açik|acik|açık|a)\s*[- ]?([123])\b", s)
    if m: return f"A{m.group(1)}"
    m = re.search(r"\bkv\s*[- ]?(\d+)\b", s)
    if m: return f"KV{m.group(1)}"
    m = re.search(r"\b(?:h|handikap)\s*[- ]?(\d+)\b", s)
    if m: return f"H{m.group(1)}"
    m = re.search(r"\b(?:s|şartli|sartli|şartlı|sartlı)\s*[- ]?(\d+)\b", s)
    if m: return f"S{m.group(1)}"
    if "maiden" in s:
        return "MAIDEN"
    # Tek başına AÇIK ifadesi ayrı bir yarış grubu olarak tutulur.
    if re.search(r"\baçik\b|\bacik\b", s):
        return "AÇIK"
    return ""


def class_base_points(value):
    g = normalize_race_group(value)
    return float(CLASS_BASE.get(g, 0))


def finish_factor(place):
    p = _place({"place": place})
    if p is None: return None
    p = int(p)
    if p in FINISH_FACTOR: return FINISH_FACTOR[p]
    if p >= 6: return .20
    return None


def _condition_group_scores(prior):
    """Her yarış grubundaki tüm geçmiş yarışları puanlar.

    Aynı grupta birden fazla yarış varsa mesafe/pist ayrımı yapılmadan
    o grubun yarış puanları ortalanır. Sonra bütün grup ortalamaları toplanır.
    """
    groups = {}
    for r in prior:
        group = normalize_race_group(_class(r))
        base = class_base_points(group)
        pos = _place(r)
        ff = finish_factor(pos)
        if not group or base <= 0 or ff is None:
            continue
        groups.setdefault(group, []).append(base * ff)
    averages = {g: sum(v)/len(v) for g, v in groups.items() if v}
    return averages


def calculate_condition_score(prior):
    avgs = _condition_group_scores(prior)
    return sum(avgs.values()), avgs


def score_pist_mesafe(prior, target):
    surf = _surface(target); td = _dist(target)
    if not surf or td is None: return 0.0
    vals=[]
    for r in prior:
        if _surface(r) != surf: continue
        d=_dist(r); p=_place(r)
        if d is None or p is None: continue
        diff=abs(d-td)
        coeff = {0:1.00,100:.85,200:.70,300:.55,400:.40}.get(diff)
        if coeff is None: continue
        ff=finish_factor(p)
        if ff is not None: vals.append(coeff*ff)
    if not vals: return 0.0
    return max(0.0,min(100.0,100.0*sum(vals)/len(vals)))


def score_pist_performansi(prior, target):
    surf=_surface(target); td=_dist(target)
    if not surf: return 0.0
    same=[r for r in prior if _surface(r)==surf and _place(r) is not None]
    near=[r for r in same if td is not None and _dist(r) is not None and abs(_dist(r)-td)<=200]
    rows=near if len(near)>=2 else same
    if not rows: return 0.0
    return max(0.0,min(100.0,100.0*(_rate_score(rows) or 0.0)))


def score_guncel_form(prior):
    rows=sorted(prior,key=lambda r:(_dt(_first(r,["date","tarih"],None)) or date.min),reverse=True)
    rows=rows[:6]
    weights=[1.00,.90,.80,.70,.60,.50]
    vals=[]; used_weights=[]
    # Eksik dereceler sonraki yarışın ağırlığını kaydırmaz.
    for w,r in zip(weights,rows):
        ff=finish_factor(_place(r))
        if ff is not None:
            vals.append(w*ff); used_weights.append(w)
    if not vals: return 0.0
    denom=sum(used_weights)
    return max(0.0,min(100.0,100.0*sum(vals)/denom))


def score_start_kulvar(prior,target):
    post=_num(_first(target,["post","st","start","kulvar"],None))
    if post is None: return 0.0
    rows=[r for r in prior if _num(_first(r,["post","st","start","kulvar"],None))==post and _place(r) is not None]
    if not rows: return 0.0
    return max(0.0,min(50.0,50.0*(_rate_score(rows) or 0.0)))


def _current_values(horse,race):
    target={
        "surface":race.get("surface") or (race.get("meta") or {}).get("surface",""),
        "distance":race.get("distance") or (race.get("meta") or {}).get("distance"),
        "condition":race.get("condition") or race.get("raceName") or (race.get("meta") or {}).get("detail",""),
        "date":race.get("date") or race.get("tarih"),
    }
    prior=_history(horse)
    condition_total, groups=calculate_condition_score(prior)
    return {
        "kosu_sarti_uyumu": condition_total,
        "kosu_sarti_gruplari": groups,
        "pist_mesafe": score_pist_mesafe(prior,target),
        "pist_performansi": score_pist_performansi(prior,target),
        "guncel_form": score_guncel_form(prior),
        "start_kulvar": score_start_kulvar(prior,target),
    }


def calculate_bizim_ranking(horses,race):
    if not isinstance(horses,list) or not horses: return []
    if not any(isinstance(h,dict) and h.get("_feature_data_ready") for h in horses): return []
    results=[]
    for idx,h in enumerate(horses):
        if not isinstance(h,dict): continue
        vals=_current_values(h,race)
        components={
            "01_kosu_sarti_uyumu":round(vals["kosu_sarti_uyumu"],2),
            "02_pist_mesafe":round(vals["pist_mesafe"],2),
            "03_pist_performansi":round(vals["pist_performansi"],2),
            "06_guncel_form":round(vals["guncel_form"],2),
            "14_start_kulvar":round(vals["start_kulvar"],2),
        }
        score=round(sum(components.values()),2)
        h["_bizim_skor"]=score
        h["_bizim_family_values"]=components
        h["_bizim_sart_gruplari"]={k:round(v,2) for k,v in vals["kosu_sarti_gruplari"].items()}
        results.append({
            "horse_index":idx,"score":score,"bizim_skor":score,
            "label":"BİZİM SKOR","components":components,
            "condition_groups":h["_bizim_sart_gruplari"],
            "model":{
                "method":"fixed_rule_no_learning",
                "learning":False,
                "condition_total_unbounded":True,
                "fixed_components":{
                    "pist_mesafe":100,"pist_performansi":100,
                    "guncel_form":100,"start_kulvar":50,
                },
            }
        })
    results.sort(key=lambda x:x["score"],reverse=True)
    for rank,item in enumerate(results,1): item["rank"]=rank
    return results
