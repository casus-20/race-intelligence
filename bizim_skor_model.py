"""BİZİM SKOR — kullanıcının sabit kuralları.

ÖNEMLİ: Bu dosyada öğrenme/adaptif ağırlık/ML/AUC yoktur.
Bütün katsayılar sabittir ve yalnızca kullanıcı tarafından tanımlanan
kurallar uygulanır.

Ana kategoriler:
01 Koşu Şartı Uyumu       max 100
02 Pist + Mesafe          max 100
03 Pist Performansı       max 100
04 Güncel Form             max 100
05 Start / Kulvar          max 60
Toplam ham skor            max 460
"""
from __future__ import annotations
from datetime import date, datetime
import math, re
from typing import Any, Dict, List

# Kullanıcının verdiği sınıf baz puanları.
CLASS_POINTS = {
    "G1": 100, "A1": 95, "G2": 90, "A2": 90, "H24": 90,
    "A3": 80, "G3": 80, "H23": 85, "KV-24": 90, "KV-18": 80,
    "KV-8": 70, "KV-9": 70, "H22": 80, "H21": 70, "H20": 75,
    "H19": 70, "H18": 65, "H17": 60, "KV-6": 60, "KV-7": 60,
    "H16": 50, "Şartlı 5": 50, "H15": 40, "Şartlı 4": 40,
    "H14": 30, "Şartlı 3": 30, "H13": 20, "Şartlı 19": 25,
    "Şartlı 2": 20, "Şartlı 27": 15, "Maiden": 10,
}
RESULT_COEFF = {1: 1.00, 2: 0.80, 3: 0.65, 4: 0.50, 5: 0.35}
DEFAULT_RESULT_COEFF = 0.15

# 02 Pist + Mesafe
DISTANCE_COEFF = {0: 1.00, 100: 0.85, 200: 0.70, 300: 0.55, 400: 0.40}


def _first(d, keys, default=None):
    if not isinstance(d, dict): return default
    for k in keys:
        v = d.get(k)
        if v not in (None, "", "-"):
            return v
    return default


def _norm(v):
    return (str(v or "").strip().lower()
            .replace("ı", "i").replace("ş", "s").replace("ğ", "g")
            .replace("ü", "u").replace("ö", "o").replace("ç", "c"))


def _num(v):
    if v is None or isinstance(v, bool): return None
    if isinstance(v, (int, float)):
        try: return float(v) if math.isfinite(float(v)) else None
        except Exception: return None
    s = str(v).strip()
    if not s or s in {"-", "—", "–", "None", "nan"}: return None
    if re.fullmatch(r"\d{1,2}\.\d{2}\.\d{2}", s): return None
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+,\d+", s):
        s = s.replace(".", "").replace(",", ".")
    else: s = s.replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    try: return float(m.group(0)) if m else None
    except Exception: return None


def _dt(v):
    if isinstance(v, datetime): return v.date()
    if isinstance(v, date): return v
    s = str(v or "").strip()
    for f in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try: return datetime.strptime(s[:10], f).date()
        except Exception: pass
    return None


def _surface(r):
    s = _norm(_first(r, ["surface","pist","Pist","Surface","trackSurface",
                         "surfaceType","surface_type","track","zemin","pistTuru"], ""))
    if s.startswith(("k:","k-")) or s == "k" or any(x in s for x in ("kum","dirt","sand")): return "kum"
    if s.startswith(("c:","c-","cim:")) or s in ("c","cim") or any(x in s for x in ("cim","grass","turf")): return "cim"
    if s.startswith(("s:","s-")) or s == "s" or any(x in s for x in ("sentetik","synthetic","polytrack","fiber")): return "sentetik"
    return s


def _city(r): return _norm(_first(r, ["city","şehir","sehir","hipodrom"], ""))
def _dist(r): return _num(_first(r, ["distance","msf","mesafe"], None))
def _place(r):
    x = _num(_first(r, ["place","sira","S","finish","position"], None))
    return int(x) if x is not None and x > 0 else None

def _weight(r): return _num(_first(r, ["weight","kilo","siklet","Sıklet"], None))
def _post(r): return _num(_first(r, ["post","start","kulvar","st","draw"], None))
def _name(r): return _norm(_first(r, ["name","horse","horseName","at","At İsmi"], ""))

def _history(h):
    rows = h.get("_history", []) if isinstance(h, dict) else []
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _class_key(value):
    """TJK sınıf metnini kullanıcının sabit sınıf tablosundaki anahtara çevirir."""
    s = _norm(value).replace("–", "-").replace("—", "-")
    if not s: return None
    # Önce özel / daha uzun ifadeler.
    patterns = [
        (r"\bg\s*1\b", "G1"), (r"\ba\s*1\b", "A1"),
        (r"\bg\s*2\b", "G2"), (r"\ba\s*2\b", "A2"),
        (r"\bg\s*3\b", "G3"), (r"\ba\s*3\b", "A3"),
        (r"\bkv\s*[- ]?24\b", "KV-24"), (r"\bkv\s*[- ]?18\b", "KV-18"),
        (r"\bkv\s*[- ]?9\b", "KV-9"), (r"\bkv\s*[- ]?8\b", "KV-8"),
        (r"\bkv\s*[- ]?7\b", "KV-7"), (r"\bkv\s*[- ]?6\b", "KV-6"),
        (r"\bh\s*24\b", "H24"), (r"\bh\s*23\b", "H23"),
        (r"\bh\s*22\b", "H22"), (r"\bh\s*21\b", "H21"),
        (r"\bh\s*20\b", "H20"), (r"\bh\s*19\b", "H19"),
        (r"\bh\s*18\b", "H18"), (r"\bh\s*17\b", "H17"),
        (r"\bh\s*16\b", "H16"), (r"\bh\s*15\b", "H15"),
        (r"\bh\s*14\b", "H14"), (r"\bh\s*13\b", "H13"),
        (r"\bsartli\s*5\b|\bsart\s*5\b", "Şartlı 5"),
        (r"\bsartli\s*4\b|\bsart\s*4\b", "Şartlı 4"),
        (r"\bsartli\s*3\b|\bsart\s*3\b", "Şartlı 3"),
        (r"\bsartli\s*2\b|\bsart\s*2\b", "Şartlı 2"),
        (r"\bsartli\s*19\b|\bsart\s*19\b", "Şartlı 19"),
        (r"\bsartli\s*27\b|\bsart\s*27\b", "Şartlı 27"),
        (r"\bmaiden\b", "Maiden"),
    ]
    for pat, key in patterns:
        if re.search(pat, s): return key
    return None


def _base_class(r):
    return CLASS_POINTS.get(_class_key(_first(r, ["className","class","sinif","Sınıf","raceName","race_name","kosu","Koşu","condition"], "")), None)


def _result_coeff(place):
    if place is None: return None
    return RESULT_COEFF.get(place, DEFAULT_RESULT_COEFF)


def _net_class(r):
    base = _base_class(r); rc = _result_coeff(_place(r))
    return base * rc if base is not None and rc is not None else None


def _mean(xs):
    xs = [float(x) for x in xs if x is not None]
    return sum(xs)/len(xs) if xs else None


def _win_rate(rows):
    places = [_place(r) for r in rows]; places = [p for p in places if p is not None]
    return sum(p == 1 for p in places)/len(places) if places else None


def _result_score(place):
    c = _result_coeff(place)
    return c if c is not None else None


def _recent_rows(h, n=None):
    rows = _history(h)
    dated = [(r, _dt(_first(r,["date","tarih"],None))) for r in rows]
    dated.sort(key=lambda x: x[1] or date.min, reverse=True)
    out = [r for r,_ in dated]
    return out[:n] if n else out


def _distance_coeff(diff):
    d = abs(float(diff))
    if d > 400: return 0.0
    if d <= 0: return 1.00
    if d <= 100: return 0.85
    if d <= 200: return 0.70
    if d <= 300: return 0.55
    return 0.40


def _same_track(rows, target):
    ts, tc = _surface(target), _city(target)
    return [r for r in rows if ts and _surface(r) == ts and tc and _city(r) == tc]


def _race_signature(r):
    return (str(_first(r,["date","tarih"],""))[:10], _city(r), _dist(r), _surface(r))


def _opponent_name(r):
    return _norm(_first(r,["horseName","horse","name","atName","at","rakip"],""))


def _opponents_from_history(r):
    """Geçmiş kayıtta rakip listesi varsa onu döndürür."""
    vals = []
    for k in ("opponents","rakipler","horses","rivals","raceHorses","field"):
        x = r.get(k) if isinstance(r,dict) else None
        if isinstance(x,list):
            for item in x:
                if isinstance(item,dict):
                    nm = _opponent_name(item)
                else: nm = _norm(item)
                if nm: vals.append(nm)
    return list(dict.fromkeys(vals))


def _field_index(horses):
    """Bugünkü 10 atın her birinin geçmişteki ortak rakiplerini bağlamak için isim indeksi."""
    idx = {}
    for h in horses:
        if not isinstance(h,dict): continue
        nm = _name(h)
        if nm: idx[nm] = h
    return idx


def _common_opponent_score(horse, horses):
    """Rakip kalitesi ağı.

    Bugünkü koşudaki tüm atların tüm geçmiş koşuları taranır. Aynı rakiple
    karşılaşmalar bulunabildiğinde, rakibin o geçmiş yarıştaki sınıf puanı
    ve sonucu üzerinden rakip gücü hesaplanır. Kendi atının rakibe karşı
    sonucu ayrıca ağırlanır. Veri yoksa HP'ye geri dönülmez.
    """
    field_names = {_name(h) for h in horses if isinstance(h,dict) and _name(h)}
    if not field_names: return None
    # Bugünkü rakiplerin geçmişteki isimleri ve her rakibin net sınıf performansı.
    opponent_strength = {}
    for h in horses:
        if not isinstance(h,dict): continue
        for r in _history(h):
            for nm in _opponents_from_history(r):
                if nm in field_names: continue
                net = _net_class(r)
                if net is not None:
                    opponent_strength.setdefault(nm, []).append(net)
    if not opponent_strength: return None
    # Atın doğrudan karşılaştığı güçlü rakipleri bul.
    own = _history(horse)
    strengths=[]; outcomes=[]
    for r in own:
        for nm in _opponents_from_history(r):
            vals = opponent_strength.get(nm)
            if vals:
                strengths.append(_mean(vals))
                p=_place(r)
                if p is not None: outcomes.append(_result_coeff(p))
    if not strengths: return None
    # 0..1: rakip gücü, sabit 100 baz puan üzerinden normalize edilir.
    strength_norm = max(0.0,min(1.0,_mean(strengths)/100.0))
    outcome_norm = _mean(outcomes) if outcomes else 0.5
    # Güçlü rakip + iyi sonuç kombinasyonu.
    return max(0.0,min(1.0,0.70*strength_norm + 0.30*outcome_norm))


def _condition_score(horse, race, horses):
    """01 — Koşu şartı uyumu: sınıf geçmişi + rakip kalitesi ağı."""
    hist = _history(horse)
    if not hist: return None
    target_class = _class_key(_first(race,["className","class","sinif","raceName","race_name","condition"],""))
    target_base = CLASS_POINTS.get(target_class)
    if target_base is None:
        # Hedef sınıf okunamıyorsa sınıf puanı üretme; veri uydurma.
        class_part = None
    else:
        nets = [_net_class(r) for r in hist]
        nets = [x for x in nets if x is not None]
        # Hedef sınıfa eşit/üst sınıf geçmişi daha doğrudan uyum verisi.
        if nets:
            class_part = max(0.0,min(1.0,_mean([min(1.0,x/max(target_base,1)) for x in nets])))
        else: class_part=None
    rival = _common_opponent_score(horse, horses)
    if class_part is None and rival is None: return None
    if class_part is None: return 100*rival
    if rival is None: return 100*class_part
    # Sabit: sınıf uyumu %60, ortak rakip ağı %40. Öğrenme yok.
    return 100*(0.60*class_part + 0.40*rival)


def _pist_distance_score(horse, race):
    """02 — Her geçmiş yarış için sonuç katsayısı × mesafe katsayısı.
    Aynı pist + aynı mesafe en değerli veridir. Sonuç 0..100'e çevrilir.
    """
    hist = _history(horse)
    ts, td = _surface(race), _dist(race)
    if not ts or td is None: return None
    vals=[]; weights=[]
    for r in hist:
        if _surface(r) != ts or _dist(r) is None: continue
        dc = _distance_coeff(_dist(r)-td)
        if dc <= 0: continue
        rc = _result_coeff(_place(r))
        if rc is None: continue
        vals.append(rc*dc); weights.append(dc)
    if not vals: return None
    # Mesafe yakınlığı zaten ağırlık; tekrar aynı veriyi iki kez cezalandırmıyoruz.
    return 100*sum(vals)/sum(weights)


def _pist_performance_score(horse, race):
    """03 — 50 + 25 + 25."""
    hist=_history(horse); ts=_surface(race); td=_dist(race); tc=_city(race)
    if not hist or not ts: return None
    same_pist=[r for r in hist if _surface(r)==ts]
    same_city_pist=[r for r in same_pist if tc and _city(r)==tc]
    same_dist=[r for r in same_pist if td is not None and _dist(r) is not None and abs(_dist(r)-td)<=200]
    win1=_win_rate(same_pist)
    win2=_win_rate(same_dist)
    win3=_win_rate(same_city_pist)
    parts=[]
    if win1 is not None: parts.append(50*win1)
    if win2 is not None: parts.append(25*win2)
    if win3 is not None: parts.append(25*win3)
    if not parts: return None
    # Eksik veri nötr puan değildir; mevcut alt kategorilerin maksimumu yeniden ölçeklenir.
    max_available=sum([50 if win1 is not None else 0,25 if win2 is not None else 0,25 if win3 is not None else 0])
    return 100*sum(parts)/max_available if max_available else None


def _form_component(rows):
    places=[_place(r) for r in rows]; places=[p for p in places if p is not None]
    if not places:return None
    return _mean([_result_score(p) for p in places])


def _trend_score(horse):
    rows=_recent_rows(horse,6)
    if len(rows)<4:return None
    # Son 3 ile önceki 3'ün sonuç katsayısı farkı; daha iyi sonuç = daha yüksek.
    a=_form_component(rows[:3]); b=_form_component(rows[3:6])
    if a is None or b is None:return None
    return max(0.0,min(100.0,50.0+(a-b)*100.0))


def _guncel_form_score(horse):
    rows=_recent_rows(horse,6)
    if not rows:return None
    comps=[]; maxp=0
    # Son yarış 25, son 3 25, son 6 25, trend 25.
    one=_form_component(rows[:1]); three=_form_component(rows[:3]); six=_form_component(rows[:6]); trend=_trend_score(horse)
    if one is not None: comps.append((25,one)); maxp+=25
    if three is not None: comps.append((25,three)); maxp+=25
    if six is not None: comps.append((25,six)); maxp+=25
    if trend is not None: comps.append((25,trend)); maxp+=25
    if not comps:return None
    return sum(w*(v/100.0) for w,v in comps)/maxp*100 if maxp else None


def _kulvar_score(horse,race):
    """05 — bugünkü kulvar + aynı mesafe kulvarı + aynı şehir/pist kulvarı."""
    hist=_history(horse); post=_post(race); td=_dist(race); ts=_surface(race); tc=_city(race)
    if post is None:return None
    same_post=[r for r in hist if _post(r)==post]
    same_dist_post=[r for r in hist if _post(r)==post and td is not None and _dist(r) is not None and abs(_dist(r)-td)<=100]
    same_track_post=[r for r in hist if _post(r)==post and ts and _surface(r)==ts and tc and _city(r)==tc]
    vals=[]; maxp=0
    for rows,w in ((same_post,20),(same_dist_post,20),(same_track_post,20)):
        sc=_form_component(rows)
        if sc is not None:
            vals.append(w*sc/100.0); maxp+=w
    if not vals:return None
    return sum(vals)/maxp*60 if maxp else None


def _details(horse,race,horses):
    c1=_condition_score(horse,race,horses)
    c2=_pist_distance_score(horse,race)
    c3=_pist_performance_score(horse,race)
    c4=_guncel_form_score(horse)
    c5=_kulvar_score(horse,race)
    comps={
        "01_kosu_sarti_uyumu": c1,
        "02_pist_mesafe": c2,
        "03_pist_performansi": c3,
        "04_guncel_form": c4,
        "05_start_kulvar": c5,
    }
    score=sum(v for v in comps.values() if v is not None)
    return comps, round(score,2)


def calculate_bizim_ranking(horses, race):
    if not isinstance(horses,list) or not horses:return []
    results=[]
    for idx,h in enumerate(horses):
        if not isinstance(h,dict):continue
        comps,score=_details(h,race,horses)
        h["_bizim_skor"]=score
        h["_bizim_family_values"]={k:round(v,2) for k,v in comps.items() if v is not None}
        results.append({
            "horse_index":idx,
            "score":score,
            "bizim_skor":score,
            "label":"BİZİM SKOR",
            "components":h["_bizim_family_values"],
            "model":{
                "method":"kullanici_sabit_yontemi",
                "learning":False,
                "max_score":460,
                "weights":{"01_kosu_sarti_uyumu":100,"02_pist_mesafe":100,"03_pist_performansi":100,"04_guncel_form":100,"05_start_kulvar":60},
            },
        })
    results.sort(key=lambda x:x["score"], reverse=True)
    for rank,item in enumerate(results,1):item["rank"]=rank
    return results


# Eski kodun olası yardımcı çağrılarını kırmamak için.
def _current_values(horse,race,horses):
    comps,_=_details(horse,race,horses)
    return comps
