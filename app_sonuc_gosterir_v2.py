"""BİZİM SKOR — SABİT KURAL MOTORU

Akıllı öğrenme / ML / AUC / otomatik ağırlık YOKTUR.

Toplam:
    KOŞU ŞARTI UYUMU (geçmiş yarış grupları toplamı, üst sınır yok)
  + PİST / MESAFE             0-100
  + PİST PERFORMANSI           0-100
  + GÜNCEL FORM                0-100
  + START / KULVAR             0-50

Koşu Şartı Uyumu:
- Şartlı, KV, Handikap ve Grup/Açık yarışlarının tamamı taranır.
- Her yarış önce kendi yarış grubuna ayrılır.
- Aynı grupta birden fazla yarış varsa o grubun yarış puanları toplanır ve
  yarış sayısına bölünür (grup ortalaması).
- Tüm farklı grup ortalamaları toplanır.
- Mesafe, aynı yarış grubunu bölmez; farklı mesafeler aynı grubun içinde kalır.
- Yarış puanı = yarış grubunun sınıf taban puanı x tabela katsayısı.
- BİZİM SKOR toplamı hiçbir yerde 1000'e veya başka bir üst sınıra kesilmez.
"""
from __future__ import annotations
from datetime import date, datetime
import math, re
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Yarış grubu / sınıf taban puanları
# ---------------------------------------------------------------------------
# Daha önceki sabit sınıf tablosundaki değerler korunur; tanınan numaralar için
# aynı mantık genişletilir. Bu tablo öğrenilmez ve çalışma sırasında değişmez.
CLASS_BASE = {
    "G1": 100.0, "G2": 90.0, "G3": 80.0,
    "A3": 80.0,
    "KV8": 70.0, "KV9": 70.0, "KV6": 60.0, "KV7": 60.0,
    "S5": 50.0, "S4": 40.0, "S3": 30.0, "S2": 20.0, "S1": 10.0,
    "H21": 50.0, "H16": 40.0, "H15": 30.0, "H14": 20.0,
    "MAIDEN": 10.0,
}

# Tabela katsayıları: bir yarışın sınıf puanına uygulanır.
FINISH_FACTOR = {
    1: 1.00,
    2: 0.80,
    3: 0.65,
    4: 0.50,
    5: 0.35,
}
OTHER_FINISH_FACTOR = 0.15

# ---------------------------------------------------------------------------
# Genel yardımcılar
# ---------------------------------------------------------------------------
def _first(d, keys, default=None):
    if not isinstance(d, dict):
        return default
    for k in keys:
        v = d.get(k)
        if v not in (None, "", "-"):
            return v
    return default


def _num(v):
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
    if re.fullmatch(r"\d{1,2}\.\d{2}\.\d{2}", s):
        return None
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
    if v is None:
        return None
    s = str(v).strip().replace(",", ".")
    m = re.fullmatch(r"(\d{1,2})\.(\d{2})\.(\d{2})", s)
    if m:
        return float(m.group(1))*60 + float(m.group(2)) + float(m.group(3))/100
    m = re.fullmatch(r"(\d{1,2}):([0-9]+(?:\.[0-9]+)?)", s)
    if m:
        return float(m.group(1))*60 + float(m.group(2))
    return _num(s)


def _norm(v):
    return (str(v or "").strip().lower()
            .replace("ı", "i").replace("ş", "s").replace("ğ", "g")
            .replace("ü", "u").replace("ö", "o").replace("ç", "c"))


def _clean_class(v):
    s = _norm(v)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _dt(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v or "").strip()
    for f in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], f).date()
        except Exception:
            pass
    return None


def _place(r):
    x = _num(_first(r, ["place", "sira", "S", "finish", "rank"], None))
    return x if x is not None and x > 0 else None


def _dist(r):
    return _num(_first(r, ["distance", "msf", "mesafe"], None))


def _wt(r):
    return _num(_first(r, ["weight", "kilo", "siklet", "Sıklet"], None))


def _hp(r):
    return _num(_first(r, ["hp", "HP", "handicap", "handikap", "rating", "RT"], None))


def _rt(r):
    return _time(_first(r, ["time", "derece", "Derece"], None))


def _surface(r):
    s = _norm(_first(r, ["surface", "pist", "Pist", "Surface", "trackSurface", "surfaceType", "track", "zemin"], ""))
    if s.startswith(("k:", "k-")) or s == "k" or any(x in s for x in ("kum", "dirt", "sand")):
        return "kum"
    if s.startswith(("c:", "c-", "cim:")) or s in ("c", "cim") or any(x in s for x in ("cim", "grass", "turf")):
        return "cim"
    if s.startswith(("s:", "s-")) or s == "s" or any(x in s for x in ("sentetik", "synthetic", "polytrack", "fiber")):
        return "sentetik"
    return s


def _city(r):
    return _norm(_first(r, ["city", "şehir", "sehir", "hipodrom"], ""))


def _history(h):
    rows = h.get("_history", []) if isinstance(h, dict) else []
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _workouts(h):
    rows = h.get("_workouts", []) if isinstance(h, dict) else []
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _mean(xs):
    vals=[]
    for x in xs:
        try:
            y=float(x)
            if math.isfinite(y): vals.append(y)
        except Exception:
            pass
    return sum(vals)/len(vals) if vals else None


def _rate_score(rows):
    places=[_place(r) for r in rows]
    places=[p for p in places if p is not None]
    if not places:
        return None
    n=len(places)
    top3=sum(p<=3 for p in places)/n
    avg=max(0.0, min(1.0, 1-(sum(places)/n-1)/max(8.0, n**0.15*8)))
    return max(0.0, min(1.0, 0.65*top3+0.35*avg))


def _result_factor(place: Optional[float]) -> Optional[float]:
    if place is None:
        return None
    p=int(place)
    if p in FINISH_FACTOR:
        return FINISH_FACTOR[p]
    return OTHER_FINISH_FACTOR

# ---------------------------------------------------------------------------
# Koşu şartı grubu çözümleme
# ---------------------------------------------------------------------------
def normalize_race_group(value: Any) -> Optional[str]:
    """Geçmiş yarışın gerçek sınıf/koşu tipini sabit grup anahtarına çevirir."""
    s = _clean_class(value)
    if not s:
        return None

    # Grup / Açık
    m = re.search(r"\b(?:g|grup|group)\s*([1-3])\b", s)
    if m:
        return f"G{m.group(1)}"
    if re.search(r"\bacik\b", s):
        return "ACIK"

    # KV — numara grubun kimliğidir; mesafe bu anahtara dahil değildir.
    m = re.search(r"\bkv\s*[- ]?\s*(\d+)\b", s)
    if m:
        return f"KV{int(m.group(1))}"

    # Şartlı — bütün Şartlı numaraları kabul edilir.
    m = re.search(r"\b(?:s|sartli|sart)\s*[- ]?\s*(\d+)\b", s)
    if m:
        return f"S{int(m.group(1))}"

    # Handikap — H numarası grubun kimliğidir.
    m = re.search(r"\b(?:h|handikap|handicap)\s*[- ]?\s*(\d+)\b", s)
    if m:
        return f"H{int(m.group(1))}"

    if "maiden" in s:
        return "MAIDEN"

    return None


def class_base_points(group: Optional[str]) -> Optional[float]:
    if not group:
        return None
    if group in CLASS_BASE:
        return CLASS_BASE[group]

    # Önceden kullanılan sınıf mantığının numaralı gruplara genişletilmesi.
    m = re.fullmatch(r"KV(\d+)", group)
    if m:
        n=int(m.group(1))
        # KV6/7=60, KV8/9=70; sonraki numaralar da aynı sabit sınıf mantığıyla ilerler.
        return min(90.0, max(10.0, 50.0+n*2.5))

    m = re.fullmatch(r"S(\d+)", group)
    if m:
        n=int(m.group(1))
        # S1=10 ... S5=50; numara yükseldikçe 10 puan.
        return float(max(10, min(100, n*10)))

    m = re.fullmatch(r"H(\d+)", group)
    if m:
        n=int(m.group(1))
        # H14=20, H15=30, H16=40, H21=50 ile uyumlu sabit bant.
        return float(max(10, min(100, (n-12)*10)))

    if group == "ACIK":
        return 90.0
    return None


def _history_class_value(row: Dict[str, Any]) -> Tuple[Optional[str], Optional[float]]:
    text = _first(row, [
        "className", "class", "sinif", "Sınıf", "raceName", "race_name",
        "kosu", "Koşu", "condition", "raceClass", "raceType", "detail"
    ], "")
    group = normalize_race_group(text)
    base = class_base_points(group)
    factor = _result_factor(_place(row))
    if base is None or factor is None:
        return group, None
    return group, base * factor


def calculate_condition_score(prior: List[Dict[str, Any]]) -> Tuple[float, Dict[str, Dict[str, Any]]]:
    """Tüm tanınan yarış gruplarını ayrı ayrı ortalayıp sonra toplar."""
    buckets: Dict[str, List[float]] = {}
    for row in prior:
        group, value = _history_class_value(row)
        if not group or value is None:
            continue
        buckets.setdefault(group, []).append(value)

    group_details: Dict[str, Dict[str, Any]] = {}
    total = 0.0
    for group, values in sorted(buckets.items()):
        avg = sum(values) / len(values)
        total += avg
        group_details[group] = {
            "race_count": len(values),
            "race_points": [round(v, 2) for v in values],
            "average": round(avg, 2),
        }
    return round(total, 2), group_details

# ---------------------------------------------------------------------------
# Sabit 100 / 100 / 100 / 50 bileşenleri
# ---------------------------------------------------------------------------
def score_pist_mesafe(prior, target):
    surf=_surface(target); dist=_dist(target)
    if not surf or dist is None: return 0.0
    rows=[r for r in prior if _surface(r)==surf and _dist(r) is not None]
    if not rows: return 0.0
    weighted=[]
    for r in rows:
        d=abs(_dist(r)-dist)
        if d==0: dc=1.0
        elif d<=100: dc=.85
        elif d<=200: dc=.70
        elif d<=300: dc=.55
        elif d<=400: dc=.40
        else: dc=0.0
        rf=_result_factor(_place(r))
        if rf is not None and dc>0: weighted.append(rf*dc)
    if not weighted: return 0.0
    return round(100*sum(weighted)/len(weighted),2)


def score_pist_performansi(prior, target):
    surf=_surface(target); dist=_dist(target)
    same_surf=[r for r in prior if surf and _surface(r)==surf]
    same_dist=[r for r in same_surf if dist is not None and _dist(r) is not None and abs(_dist(r)-dist)<=200]
    city=_city(target)
    same_city=[r for r in same_surf if city and _city(r)==city]
    parts=[]
    if same_surf: parts.append(_rate_score(same_surf))
    if same_dist: parts.append(_rate_score(same_dist))
    if same_city: parts.append(_rate_score(same_city))
    parts=[x for x in parts if x is not None]
    if not parts: return 0.0
    return round(100*sum(parts)/len(parts),2)


def score_guncel_form(prior):
    recent=prior[:6]
    vals=[_place(r) for r in recent if _place(r) is not None]
    if not vals: return 0.0
    # Son 6 yarışta sabit katsayılar: 1.00, .90, .80, .70, .60, .50
    w=[1.00,.90,.80,.70,.60,.50][:len(vals)]
    result=[]
    for p,ww in zip(vals,w):
        rf=_result_factor(p) or OTHER_FINISH_FACTOR
        result.append(rf*ww)
    base=sum(result)/sum(w)
    # Son yarışın ilk 6 içindeki değişimi ayrıca trend olarak değil, sabit bir
    # tamamlayıcı olarak kullanıyoruz; öğrenme yoktur.
    return round(100*max(0.0,min(1.0,base)),2)


def score_start_kulvar(prior, target):
    post=_num(_first(target,["post","st","start","kulvar"],None))
    if post is None: return 0.0
    rows=[r for r in prior if _num(_first(r,["post","st","start","kulvar"],None))==post]
    if not rows: return 0.0
    return round(50*(_rate_score(rows) or 0.0),2)

# ---------------------------------------------------------------------------
def _target_from_race(race):
    meta=race.get("meta") or {} if isinstance(race,dict) else {}
    return {
        "surface": race.get("surface") or meta.get("surface", ""),
        "distance": race.get("distance") or meta.get("distance"),
        "condition": race.get("condition") or race.get("raceName") or meta.get("detail", ""),
        "date": race.get("date") or race.get("tarih"),
        "city": race.get("city") or race.get("şehir") or race.get("sehir") or meta.get("city", ""),
    }


def calculate_bizim_ranking(horses, race):
    """Her atı yalnızca sabit kurallarla puanlar; öğrenme modeli çalıştırmaz."""
    if not isinstance(horses, list) or not horses:
        return []

    target=_target_from_race(race if isinstance(race,dict) else {})
    results=[]
    for idx,h in enumerate(horses):
        if not isinstance(h,dict):
            continue
        prior=sorted(_history(h), key=lambda r: (_dt(_first(r,["date","tarih"],None)) or date.min), reverse=True)
        condition_total, group_details=calculate_condition_score(prior)
        pist_mesafe=score_pist_mesafe(prior,target)
        pist_perf=score_pist_performansi(prior,target)
        form=score_guncel_form(prior)
        kulvar=score_start_kulvar(prior,target)
        components={
            "01_kosu_sarti_uyumu": condition_total,
            "02_pist_mesafe": pist_mesafe,
            "03_pist_performansi": pist_perf,
            "04_guncel_form": form,
            "05_start_kulvar": kulvar,
        }
        score=round(condition_total+pist_mesafe+pist_perf+form+kulvar,2)
        h["_bizim_skor"]=score
        h["_bizim_family_values"]=components.copy()
        h["_bizim_sart_gruplari"]=group_details
        results.append({
            "horse_index":idx,
            "score":score,
            "bizim_skor":score,
            "label":"BİZİM SKOR",
            "components":components,
            "condition_groups":group_details,
            "model":{
                "learning":False,
                "method":"fixed_rule_no_learning",
                "condition_score_unbounded":True,
                "fixed_caps":{
                    "pist_mesafe":100,
                    "pist_performansi":100,
                    "guncel_form":100,
                    "start_kulvar":50,
                },
                "total_formula":"kosu_sarti_uyumu + 100 + 100 + 100 + 50",
            },
        })

    results.sort(key=lambda x:x["score"], reverse=True)
    for rank,item in enumerate(results,1):
        item["rank"]=rank
    return results
