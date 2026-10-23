"""BİZİM SKOR — sabit 5 bileşenli kural motoru.

Bileşenler (toplam en çok 450 puan):
- Koşu Şartı Uyumu: 0-100. Geçmişte koşulan her yarış grubunun (taban puan x
  bitiriş katsayısı) ortalaması alınır; gruplar bugünkü koşunun sınıfına
  yakınlıklarına göre ağırlıklandırılıp ortalanır. Toplanmaz, tavanı 100'dür.
- Pist / Mesafe: 0-100
- Pist Performansı: 0-100
- Güncel Form: 0-100
- Start / Kulvar: 0-50

Öğrenme ve AUC yoktur; disk arşivi veya ekran görüntüsü mekanizması yoktur.
Atın yalnızca 1 geçmiş yarışı olsa bile mevcut verilerle skor hesaplanır.
Eksik veri olan bileşen 0 puan alır; at analizden çıkarılmaz.
Girdi sözlükleri DEĞİŞTİRİLMEZ (cache güvenliği için).
"""
from __future__ import annotations
from datetime import date, datetime
import math
import re
from typing import Any, Dict, List


# ------------------------------------------------------------
# Yardımcılar
# ------------------------------------------------------------
def _deep_first(obj, keys, default=None, _depth=0):
    """Alanı önce üst seviyede, bulunamazsa iç içe dict/list yapılarında arar."""
    if _depth > 6:
        return default
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if v not in (None, "", "-", [], {}) and not isinstance(v, (dict, list)):
                return v
        for v in obj.values():
            if isinstance(v, (dict, list)):
                found = _deep_first(v, keys, None, _depth + 1)
                if found not in (None, ""):
                    return found
    elif isinstance(obj, list):
        for v in obj[:20]:
            if isinstance(v, (dict, list)):
                found = _deep_first(v, keys, None, _depth + 1)
                if found not in (None, ""):
                    return found
    return default


def _first(d, keys, default=None):
    return _deep_first(d, keys, default) if isinstance(d, dict) else default


def _num(v):
    """TJK sayısal alanlarını güvenli biçimde float'a çevirir."""
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
    # 1.24.77 gibi dereceler sayı değildir.
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


def _norm(v):
    return (str(v or "").strip().lower().replace("ı", "i").replace("İ", "i")
            .replace("ş", "s").replace("ğ", "g").replace("ü", "u")
            .replace("ö", "o").replace("ç", "c"))


def _surface(r):
    s = _norm(_first(r, ["surface", "pist", "Pist", "Surface", "trackSurface",
                         "surfaceType", "track", "zemin"], ""))
    if s.startswith(("k:", "k-")) or s == "k" or any(x in s for x in ("kum", "dirt", "sand")):
        return "kum"
    if s.startswith(("c:", "c-", "cim:")) or s in ("c", "cim") or any(x in s for x in ("cim", "grass", "turf")):
        return "cim"
    if s.startswith(("s:", "s-")) or s == "s" or any(x in s for x in ("sentetik", "synthetic", "polytrack", "fiber")):
        return "sentetik"
    return s


_TR_MONTHS = {
    "oca": 1, "sub": 2, "mar": 3, "nis": 4, "may": 5, "haz": 6,
    "tem": 7, "agu": 8, "eyl": 9, "eki": 10, "kas": 11, "ara": 12,
}


def _dt(v):
    """Tarihi geniş biçim desteğiyle çözer; çözülemezse None."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v or "").strip()
    if not s:
        return None
    for f in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s[:10], f).date()
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except Exception:
        pass
    m = re.search(r"(\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{4}[./-]\d{1,2}[./-]\d{1,2})", s)
    if m:
        tok = m.group(1)
        for f in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
            try:
                return datetime.strptime(tok, f).date()
            except Exception:
                pass
    # "07 Eki 2026" / "7 Ekim 2026"
    m = re.search(r"(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]{3,})\.?\s+(\d{4})", s)
    if m:
        mon = _TR_MONTHS.get(_norm(m.group(2))[:3])
        if mon:
            try:
                return date(int(m.group(3)), mon, int(m.group(1)))
            except Exception:
                pass
    return None


def _row_date(r):
    return _dt(_first(r, ["date", "tarih", "Tarih", "raceDate", "race_date",
                          "kosuTarihi", "runDate", "run_date"], None))


def _place(r):
    x = _num(_first(r, ["place", "sira", "Sıra", "S", "finish", "finishPosition", "rank"], None))
    return x if x is not None and x > 0 else None


def _dist(r):
    return _num(_first(r, ["distance", "msf", "mesafe", "Msf"], None))


def _class(r):
    keys = ["className", "class", "sinif", "Sınıf", "raceName", "race_name",
            "kosu", "Koşu", "condition", "raceType", "raceCondition"]
    parts = []
    if isinstance(r, dict):
        for k in keys:
            v = r.get(k)
            if v not in (None, "", "-") and not isinstance(v, (dict, list)):
                parts.append(str(v))
    if not parts:
        v = _first(r, keys, "")
        parts = [str(v)] if v else []
    return " | ".join(parts)


def _history(h):
    rows = h.get("_history", []) if isinstance(h, dict) else []
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _mean(xs):
    clean = []
    for x in xs:
        try:
            y = float(x)
            if math.isfinite(y):
                clean.append(y)
        except Exception:
            continue
    return sum(clean) / len(clean) if clean else None


def _stats(rows):
    p = [_place(r) for r in rows]
    p = [x for x in p if x is not None]
    if not p:
        return None
    return {"sample": len(p), "wins": sum(x == 1 for x in p),
            "top3": sum(x <= 3 for x in p), "top5": sum(x <= 5 for x in p),
            "avg": _mean(p)}


_RATE_PRIOR = 0.30   # örneklem azken çekilecek nötr başarı oranı
_RATE_PRIOR_N = 3.0  # prior'ın "sanal örneklem" ağırlığı


def _rate_score(rows):
    """Top-3 oranı + ortalama sıra; küçük örneklem nötr değere doğru çekilir."""
    st = _stats(rows)
    if not st:
        return None
    n = st["sample"]
    avg_score = max(0.0, min(1.0, 1 - (st["avg"] - 1) / max(8.0, n ** 0.15 * 8)))
    raw = max(0.0, min(1.0, 0.65 * (st["top3"] / n) + 0.35 * avg_score))
    return (raw * n + _RATE_PRIOR * _RATE_PRIOR_N) / (n + _RATE_PRIOR_N)


# ------------------------------------------------------------
# Sınıf tablosu (app.py ile PAYLAŞILIR)
# ------------------------------------------------------------
CLASS_BASE = {
    "G1": 100, "A1": 95, "G2": 90, "A2": 90, "G3": 80, "A3": 80,
    "H24": 90, "H23": 85, "H22": 80, "H21": 70, "H20": 75,
    "H19": 70, "H18": 65, "H17": 60, "H16": 50, "H15": 40,
    "H14": 30, "H13": 20,
    "KV24": 90, "KV18": 80, "KV9": 70, "KV8": 70, "KV7": 60, "KV6": 60,
    "S27": 15, "S19": 25, "S5": 50, "S4": 40, "S3": 30, "S2": 20, "S1": 10,
    "MAIDEN": 10, "AÇIK": 90,
}

FINISH_FACTOR = {
    1: 1.00, 2: 0.95, 3: 0.90, 4: 0.85, 5: 0.80,
    6: 0.70, 7: 0.65, 8: 0.60, 9: 0.55, 10: 0.50,
    11: 0.45, 12: 0.40, 13: 0.35, 14: 0.30, 15: 0.25,
    16: 0.20, 17: 0.15, 18: 0.10,
}


def normalize_race_group(value):
    s = _norm(value)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    m = re.search(r"(?<![a-z0-9])(?:g|grup|group)\s*[- ]?([123])(?![0-9])", s)
    if m:
        return f"G{m.group(1)}"
    m = re.search(r"(?<![a-z0-9])(?:acik|a)\s*[- ]?([123])(?![0-9])", s)
    if m:
        return f"A{m.group(1)}"
    m = re.search(r"(?<![a-z0-9])kv\s*[- ]?(\d+)", s)
    if m:
        return f"KV{m.group(1)}"
    m = re.search(r"(?<![a-z0-9])(?:h|handikap)\s*[- ]?(\d+)", s)
    if m:
        return f"H{m.group(1)}"
    # "S" tek harf olarak yalnızca bitişik rakamla ("S3") veya Şartlı sözcüğüyle.
    m = re.search(r"(?:sartli|sart)\s*[- /]?(\d+)", s) or re.search(r"(?<![a-z0-9])s(\d+)(?![a-z0-9])", s)
    if m:
        return f"S{m.group(1)}"
    if "maiden" in s:
        return "MAIDEN"
    if re.search(r"(?<![a-z0-9])acik(?![a-z0-9])", s):
        return "AÇIK"
    return ""


def _class_fallback(group):
    """Tabloda olmayan numaralar için aynı mantıkla ara değer üretir."""
    m = re.fullmatch(r"(H|KV|S)(\d+)", group or "")
    if not m:
        return 0.0
    fam, n = m.group(1), int(m.group(2))
    if fam == "H":
        if n <= 12:
            return 10.0
        if n <= 16:
            return 20.0 + (n - 13) * 10.0
        return min(90.0, 50.0 + (n - 16) * 5.0)
    if fam == "KV":
        return max(40.0, min(90.0, 35.0 + n * 2.5))
    # Şartlı
    if n <= 5:
        return n * 10.0
    return 20.0


def class_base_points(value):
    g = normalize_race_group(value)
    if not g:
        return 0.0
    if g in CLASS_BASE:
        return float(CLASS_BASE[g])
    return float(_class_fallback(g))


def finish_factor(place):
    p = _num(place)
    if p is None or p <= 0:
        return None
    p = int(p)
    if p in FINISH_FACTOR:
        return FINISH_FACTOR[p]
    # 18. sıra ve sonrası için katsayı taban seviyede tutulur.
    return 0.10 if p > 18 else None


# ------------------------------------------------------------
# Bileşenler
# ------------------------------------------------------------
def _condition_group_scores(prior):
    """Her geçmiş koşunun sınıf taban puanını bitiriş katsayısıyla çarpar.

    Aynı koşu grubundaki yarışların ortalaması alınmaz; tüm geçerli geçmiş
    yarışların katkıları toplanır. Hedef tarih filtresi _current_values içinde
    uygulanır.
    """
    groups = {}
    for r in prior:
        group = normalize_race_group(_class(r))
        base = class_base_points(group)
        ff = finish_factor(_place(r))
        if not group or base <= 0 or ff is None:
            continue
        groups.setdefault(group, []).append(base * ff)
    return {g: sum(v) for g, v in groups.items() if v}


def calculate_condition_score(prior, today_condition=""):
    """Koşu şartı uyumu: tüm geçerli geçmiş yarışların sınıf puanları toplamı.

    Bilerek ortalama alınmaz ve 0-100 aralığına kırpılmaz; toplam puan
    geçmiş yarış sayısıyla artabilir.
    """
    sums = _condition_group_scores(prior)
    return sum(sums.values()), sums


def _distance_coeff(diff):
    """Sürekli mesafe katsayısı (1450 vs 1400 gibi 100'ün katı olmayan farklar dahil)."""
    if diff <= 0:
        return 1.00
    if diff <= 100:
        return .95
    if diff <= 200:
        return .90
    if diff <= 300:
        return .85
    if diff <= 400:
        return .80
    return None


def score_pist_mesafe(prior, target):
    surf = _surface(target)
    td = _dist(target)
    if not surf or td is None:
        return 0.0
    vals = []
    for r in prior:
        if _surface(r) != surf:
            continue
        d = _dist(r)
        p = _place(r)
        if d is None or p is None:
            continue
        coeff = _distance_coeff(abs(d - td))
        if coeff is None:
            continue
        ff = finish_factor(p)
        if ff is not None:
            vals.append(coeff * ff)
    if not vals:
        return 0.0
    return max(0.0, min(100.0, 100.0 * sum(vals) / len(vals)))


def score_pist_performansi(prior, target):
    surf = _surface(target)
    td = _dist(target)
    if not surf:
        return 0.0
    same = [r for r in prior if _surface(r) == surf and _place(r) is not None]
    near = [r for r in same if td is not None and _dist(r) is not None and abs(_dist(r) - td) <= 200]
    rows = near if len(near) >= 2 else same
    if not rows:
        return 0.0
    return max(0.0, min(100.0, 100.0 * (_rate_score(rows) or 0.0)))


def score_guncel_form(prior):
    rows = sorted(prior, key=lambda r: (_row_date(r) or date.min), reverse=True)[:6]
    weights = [1.00, .95, .90, .85, .80, .75]
    vals, used = [], []
    for w, r in zip(weights, rows):
        ff = finish_factor(_place(r))
        if ff is not None:
            vals.append(w * ff)
            used.append(w)
    if not vals:
        return 0.0
    return max(0.0, min(100.0, 100.0 * sum(vals) / sum(used)))




def _current_values(horse, race):
    meta = race.get("meta") if isinstance(race.get("meta"), dict) else {}
    target = {
        "surface": race.get("surface") or meta.get("surface", ""),
        "distance": race.get("distance") or meta.get("distance"),
        "condition": race.get("condition") or race.get("raceName") or meta.get("detail", ""),
        "date": race.get("date") or race.get("tarih"),
    }
    target_date = _dt(target.get("date"))
    if target_date is not None:
        prior = [r for r in _history(horse)
                 if _row_date(r) is not None and _row_date(r) < target_date]
    else:
        prior = []

    cond_total, groups = calculate_condition_score(prior, target["condition"])
    return {
        "kosu_sarti_uyumu": cond_total,
        "kosu_sarti_gruplari": groups,
        "pist_mesafe": score_pist_mesafe(prior, target),
        "pist_performansi": score_pist_performansi(prior, target),
        "guncel_form": score_guncel_form(prior),
    }


def calculate_bizim_ranking(horses, race):
    """Her atı, geçmiş yarış sayısından bağımsız olarak puanlar.

    Girdi sözlüklerini değiştirmez; yalnızca sonuç listesi döndürür.
    """
    if not isinstance(horses, list) or not horses or not isinstance(race, dict):
        return []
    results = []
    for idx, h in enumerate(horses):
        if not isinstance(h, dict):
            continue
        vals = _current_values(h, race)
        components = {
            "01_kosu_sarti_uyumu": round(vals["kosu_sarti_uyumu"], 2),
            "02_pist_mesafe": round(vals["pist_mesafe"], 2),
            "03_pist_performansi": round(vals["pist_performansi"], 2),
            "06_guncel_form": round(vals["guncel_form"], 2),
        }
        score = round(sum(components.values()), 2)
        results.append({
            "horse_index": idx, "score": score, "bizim_skor": score,
            "label": "BİZİM SKOR", "components": components,
            "condition_groups": {k: round(v, 2) for k, v in vals["kosu_sarti_gruplari"].items()},
            "model": {
                "method": "fixed_rule_no_learning",
                "learning": False,
                "max_total": None,
                "fixed_components": {
                    "kosu_sarti_uyumu": "unbounded", "pist_mesafe": 100,
                    "pist_performansi": 100, "guncel_form": 100,
                },
                "minimum_prior_races": 0,
            },
        })
    results.sort(key=lambda x: (-x["score"], x["horse_index"]))
    for rank, item in enumerate(results, 1):
        item["rank"] = rank
    return results
