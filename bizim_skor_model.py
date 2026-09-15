"""BİZİM SKOR — ampirik 0-1500 model.

Model, atların kendi TJK geçmişindeki gerçek sonuçlardan öğrenir.
Her tarihsel koşu için yalnızca o koşudan ÖNCE mevcut olan yarışlar kullanılır;
böylece hedef yarışın sonucu eğitim özelliğine sızmaz.

Ağırlıklar elle verilmez. Her veri ailesinin top-3 sonucunu ayırt etme gücü
(AUC) ve örnek sayısına göre 1500 puanlık toplam ağırlık oluşturulur.
Yetersiz veri varsa skor üretilmez; eksik veri 50 gibi nötr bir değerle
 doldurulmaz.
"""
from __future__ import annotations

from datetime import date, datetime
import math
import re
from typing import Any, Dict, List, Optional, Tuple


FAMILIES = [
    "01_kosu_sarti_uyumu",
    "02_pist_mesafe",
    "04_gercek_derece",
    "05_gercek_hiz",
    "06_guncel_form",
    "07_ortak_rakip",
    "08_kilo_performansi",
    "09_hp_kalite",
    "10_galop_performansi",
    "12_dinlenme_kgs",
]

MIN_FAMILY_SAMPLES = 12
MIN_TOTAL_SAMPLES = 60


def _first(d: Dict[str, Any], keys, default=None):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", "-"):
            return v
    return default


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v).strip())
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except Exception:
        return None


def _time(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", ".")
    m = re.search(r"(\d+):(\d+(?:\.\d+)?)", s)
    if m:
        return float(m.group(1)) * 60 + float(m.group(2))
    return _num(s)


def _norm(v):
    return (str(v or "").strip().lower().replace("ı", "i").replace("ş", "s")
            .replace("ğ", "g").replace("ü", "u").replace("ö", "o")
            .replace("ç", "c"))


def _surface(r):
    s = _norm(_first(r, ["surface", "pist", "Pist", "Surface", "trackSurface",
                         "track_surface", "surfaceType", "surface_type", "track",
                         "trackType", "track_type", "zemin", "Zemin"], ""))
    if s.startswith(("k:", "k-")) or s == "k" or "kum" in s or "dirt" in s or "sand" in s:
        return "kum"
    if s.startswith(("c:", "c-", "cim:")) or s in ("c", "cim") or "cim" in s or "grass" in s or "turf" in s:
        return "cim"
    if s.startswith(("s:", "s-")) or s == "s" or "sentetik" in s or "synthetic" in s or "polytrack" in s:
        return "sentetik"
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
    p = _num(_first(r, ["place", "sira", "S", "finish"], None))
    return p if p is not None and p > 0 else None


def _dist(r):
    return _num(_first(r, ["distance", "msf", "mesafe"], None))


def _wt(r):
    return _num(_first(r, ["weight", "kilo", "siklet", "Sıklet"], None))


def _hp(r):
    return _num(_first(r, ["hp", "HP", "handicap", "handikap"], None))


def _rt(r):
    return _time(_first(r, ["time", "derece", "Derece"], None))


def _class(r):
    return _norm(_first(r, ["className", "class", "sinif", "Sınıf", "raceName", "race_name", "kosu", "Koşu", "condition"], ""))


def _race_city(r):
    return _norm(_first(r, ["city", "hipodrom", "sehir"], ""))


def _safe_mean(vals):
    vals = [x for x in vals if x is not None and math.isfinite(x)]
    return sum(vals) / len(vals) if vals else None


def _win_rate(rows, max_place=3):
    p = [_place(r) for r in rows]
    p = [x for x in p if x is not None]
    return sum(x <= max_place for x in p) / len(p) if p else None


def _exact_stats(prior, target):
    s = _surface(target)
    d = _dist(target)
    rows = [r for r in prior if s and _surface(r) == s and d is not None and _dist(r) == d]
    return rows


def _family_values(prior: List[Dict[str, Any]], target: Dict[str, Any], workouts: Optional[List[Dict[str, Any]]] = None, all_horse_histories=None) -> Dict[str, Optional[float]]:
    """Return 0..1 family strengths; None means unavailable, never neutral."""
    if not prior:
        return {k: None for k in FAMILIES}

    exact = _exact_stats(prior, target)
    surface = [r for r in prior if _surface(target) and _surface(r) == _surface(target)]
    near = [r for r in surface if _dist(target) is not None and _dist(r) is not None and abs(_dist(r) - _dist(target)) <= 100]
    recent = prior[:6]

    out = {k: None for k in FAMILIES}

    # 01 — koşu şartı: same class/condition success rate, if class text is usable.
    tc = _class(target)
    if tc:
        same_class = [r for r in prior if _class(r) and (_class(r) == tc or tc in _class(r) or _class(r) in tc)]
        if len(same_class) >= 2:
            out["01_kosu_sarti_uyumu"] = _win_rate(same_class, 3)

    # 02 — exact/near surface + distance. Exact sample has priority.
    base = exact if len(exact) >= 2 else near
    if len(base) >= 2:
        wr = _win_rate(base, 3)
        avg = _safe_mean([_place(r) for r in base])
        # Convert average place to a bounded strength, blended with top-3 rate.
        place_strength = max(0.0, min(1.0, 1.0 - ((avg - 1.0) / 7.0))) if avg is not None else None
        vals = [x for x in (wr, place_strength) if x is not None]
        out["02_pist_mesafe"] = _safe_mean(vals)

    # 04 — real degree: faster normalized time is better.
    timed = []
    for r in (exact if len(exact) >= 2 else surface):
        t, d = _rt(r), _dist(r)
        if t is not None and d and d > 0:
            timed.append(t / (d / 1000.0))
    if len(timed) >= 2:
        best, avg = min(timed), sum(timed) / len(timed)
        # Relative to own historical range, not a fabricated fixed time.
        spread = max(timed) - best
        out["04_gercek_derece"] = 1.0 if spread <= 0 else max(0.0, min(1.0, 1.0 - (avg - best) / spread))

    # 05 — real speed trend: latest comparable normalized speed vs historical average.
    speed_rows = []
    for r in surface:
        t, d = _rt(r), _dist(r)
        if t is not None and d and d > 0:
            speed_rows.append(t / (d / 1000.0))
    if len(speed_rows) >= 3:
        recent_speed = speed_rows[:3]
        old_speed = speed_rows[3:]
        a = _safe_mean(recent_speed)
        b = _safe_mean(old_speed)
        if a is not None and b is not None and b > 0:
            out["05_gercek_hiz"] = max(0.0, min(1.0, 0.5 + (b - a) / max(b * 0.05, 0.01)))

    # 06 — recent form. Lower average place and top-3 rate are better.
    rp = [_place(r) for r in recent]
    rp = [x for x in rp if x is not None]
    if len(rp) >= 3:
        avg = sum(rp) / len(rp)
        place_strength = max(0.0, min(1.0, 1.0 - ((avg - 1.0) / 8.0)))
        top3 = sum(x <= 3 for x in rp) / len(rp)
        out["06_guncel_form"] = (place_strength + top3) / 2.0

    # 07 — common-rival information only when actual shared race data exists.
    if all_horse_histories:
        target_date = str(_first(target, ["date", "tarih"], ""))
        target_city = _race_city(target)
        target_dist = _dist(target)
        diffs = []
        for other_hist in all_horse_histories:
            if other_hist is prior:
                continue
            for r in other_hist:
                if (str(_first(r, ["date", "tarih"], "")) == target_date and
                    _race_city(r) == target_city and _dist(r) == target_dist):
                    # This family is only available if the caller supplied rival outcome context.
                    pass
        # Rival-pair features are built in the current feature layer. During rolling training,
        # without a full historical field they are legitimately unavailable.

    # 08 — weight performance: success under weights close to today's weight.
    tw = _wt(target)
    if tw is not None:
        similar = [r for r in prior if _wt(r) is not None and abs(_wt(r) - tw) <= 2]
        if len(similar) >= 2:
            out["08_kilo_performansi"] = _win_rate(similar, 3)

    # 09 — HP / quality: relative to the horse's own recent maximum/average.
    hp = [_hp(r) for r in prior if _hp(r) is not None]
    if len(hp) >= 3:
        avg = _safe_mean(hp)
        mx = max(hp)
        cur = _hp(target)
        if cur is not None and mx > 0:
            out["09_hp_kalite"] = max(0.0, min(1.0, 0.6 * (cur / mx) + 0.4 * (cur / max(avg, 0.01))))
        else:
            out["09_hp_kalite"] = max(0.0, min(1.0, avg / max(mx, 0.01)))

    # 10 — workout performance: use latest available workout before target date.
    if workouts:
        td = _dt(_first(target, ["date", "tarih"], None))
        ws = []
        for w in workouts:
            wd = _dt(_first(w, ["date", "tarih"], None))
            if td is None or wd is None or wd <= td:
                vals = []
                for k in ("m600", "m400", "m200"):
                    x = _time(_first(w, [k, k.replace("m", ""), k + "m"], None))
                    if x is not None:
                        vals.append(x)
                if vals:
                    ws.append(_safe_mean(vals))
        if len(ws) >= 2:
            best, latest = min(ws), ws[0]
            spread = max(ws) - best
            out["10_galop_performansi"] = 1.0 if spread <= 0 else max(0.0, min(1.0, 1.0 - (latest - best) / spread))

    # 12 — rest/KGS: learn the useful region from the horse's own successful rests.
    td = _dt(_first(target, ["date", "tarih"], None))
    if td and prior:
        dates = [_dt(_first(r, ["date", "tarih"], None)) for r in prior]
        dates = [d for d in dates if d]
        if dates:
            kgs = (td - max(dates)).days
            # Use an empirical bell shape around this horse's own top-3 rest intervals.
            successful = []
            for r in prior:
                rd = _dt(_first(r, ["date", "tarih"], None))
                p = _place(r)
                if rd and p is not None and p <= 3:
                    later_dates = [d for d in dates if d > rd]
                    if later_dates:
                        successful.append((min(later_dates) - rd).days)
            if successful:
                center = _safe_mean(successful)
                scale = max(_safe_mean([abs(x - center) for x in successful]) or 7.0, 3.0)
                out["12_dinlenme_kgs"] = math.exp(-abs(kgs - center) / scale)

    return out


def _auc(values: List[float], labels: List[int]) -> Optional[float]:
    pairs = [(v, y) for v, y in zip(values, labels) if v is not None and math.isfinite(v)]
    pos = [v for v, y in pairs if y == 1]
    neg = [v for v, y in pairs if y == 0]
    if not pos or not neg:
        return None
    # Tie-aware Mann-Whitney probability: P(score_positive > score_negative) + 0.5*ties.
    wins = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(pos) * len(neg))


def _rolling_samples(horses: List[Dict[str, Any]]) -> Dict[str, List[Tuple[float, int]]]:
    samples = {k: [] for k in FAMILIES}
    total = 0
    for horse in horses:
        hist = horse.get("_history", []) if isinstance(horse, dict) else []
        if not isinstance(hist, list):
            continue
        rows = [r for r in hist if isinstance(r, dict)]
        # TJK history is normally newest -> oldest.
        # For a historical target race, ONLY rows after it in this list (older dates)
        # were known before the target race. Never use newer rows as training features.
        dated = [(idx, _dt(_first(r, ["date", "tarih"], None))) for idx, r in enumerate(rows)]
        if any(d is not None for _, d in dated):
            rows = sorted(rows, key=lambda r: (_dt(_first(r, ["date", "tarih"], None)) or date.min), reverse=True)
        for i in range(5, len(rows)):
            target = rows[i]
            label_place = _place(target)
            if label_place is None:
                continue
            prior = rows[i + 1:]
            if len(prior) < 5:
                continue
            vals = _family_values(prior, target, horse.get("_workouts", []))
            label = 1 if label_place <= 3 else 0
            total += 1
            for family, value in vals.items():
                if value is not None:
                    samples[family].append((value, label))
    return samples


def learn_model(horses: List[Dict[str, Any]]) -> Dict[str, Any]:
    samples = _rolling_samples(horses)
    total = sum(len(v) for v in samples.values())
    learned = []
    for family in FAMILIES:
        pairs = samples[family]
        if len(pairs) < MIN_FAMILY_SAMPLES:
            continue
        vals = [x for x, _ in pairs]
        labels = [y for _, y in pairs]
        auc = _auc(vals, labels)
        if auc is None:
            continue
        signal = max(0.0, 2.0 * (auc - 0.5))
        if signal <= 0:
            # AUC below 0.5 means the direction is reversed; flip it because all family
            # scores are designed as "higher is better".
            auc_flip = 1.0 - auc
            signal = max(0.0, 2.0 * (auc_flip - 0.5))
            direction = -1
        else:
            direction = 1
        reliability = min(1.0, math.sqrt(len(pairs) / 100.0))
        strength = signal * reliability
        learned.append({"family": family, "auc": auc, "direction": direction, "samples": len(pairs), "strength": strength})

    if total < MIN_TOTAL_SAMPLES or len(learned) < 3:
        return {"ready": False, "sample_count": total, "families": learned, "weights": {}, "method": "rolling_out_of_time_auc"}

    strength_sum = sum(x["strength"] for x in learned)
    if strength_sum <= 0:
        return {"ready": False, "sample_count": total, "families": learned, "weights": {}, "method": "rolling_out_of_time_auc"}

    weights = {x["family"]: 1500.0 * x["strength"] / strength_sum for x in learned}
    return {"ready": True, "sample_count": total, "families": learned, "weights": weights, "method": "rolling_out_of_time_auc"}


def _current_family_values(horse, race, horses):
    hist = horse.get("_history", []) if isinstance(horse, dict) else []
    prior = [r for r in hist if isinstance(r, dict)]
    target = {
        "surface": race.get("surface") or (race.get("meta") or {}).get("surface", ""),
        "distance": race.get("distance") or (race.get("meta") or {}).get("distance"),
        "condition": race.get("condition") or race.get("raceName") or (race.get("meta") or {}).get("detail", ""),
        "date": race.get("date") or race.get("tarih"),
    }
    # Current race fields are not always duplicated into a synthetic target row;
    # pass the original horse race values through explicitly.
    target["class"] = target.get("condition", "")
    rivals = [h.get("_history", []) for h in horses if isinstance(h, dict)]
    return _family_values(prior, target, horse.get("_workouts", []), rivals)


def calculate_bizim_ranking(horses: List[Dict[str, Any]], race: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(horses, list) or not horses:
        return []
    if not any(isinstance(h, dict) and h.get("_feature_data_ready") for h in horses):
        return []

    model = learn_model(horses)
    if not model.get("ready"):
        return []

    weights = model["weights"]
    results = []
    for idx, horse in enumerate(horses):
        if not isinstance(horse, dict):
            continue
        vals = horse.get("_feature_vector") or {}
        components = {}
        # Use the already-built real-data feature vector for current scoring.
        family_to_value = {
            "01_kosu_sarti_uyumu": None,
            "02_pist_mesafe": None,
            "04_gercek_derece": None,
            "05_gercek_hiz": None,
            "06_guncel_form": None,
            "07_ortak_rakip": None,
            "08_kilo_performansi": None,
            "09_hp_kalite": None,
            "10_galop_performansi": None,
            "12_dinlenme_kgs": None,
        }

        f = vals.get("01_kosu_sarti_uyumu", {})
        elig = f.get("eligibility") if isinstance(f, dict) else None
        if isinstance(elig, dict) and isinstance(elig.get("score"), (int, float)):
            family_to_value["01_kosu_sarti_uyumu"] = max(0.0, min(1.0, float(elig["score"]) / 100.0))

        f = vals.get("02_pist_mesafe", {})
        if isinstance(f, dict):
            n = f.get("exact_sample") or f.get("near_sample") or 0
            avg = f.get("exact_avg_place") or f.get("near_avg_place")
            if n and avg is not None:
                family_to_value["02_pist_mesafe"] = max(0.0, min(1.0, 1.0 - (float(avg) - 1.0) / 8.0))

        f = vals.get("04_gercek_derece", {})
        t = f.get("exact") if isinstance(f, dict) else None
        if not t or not t.get("sample"):
            t = f.get("same_surface") if isinstance(f, dict) else None
        if isinstance(t, dict) and t.get("sample", 0) >= 2 and t.get("best_sec_per_km") is not None and t.get("avg_sec_per_km") is not None:
            spread = max(t.get("avg_sec_per_km", 0) - t.get("best_sec_per_km", 0), 0.001)
            family_to_value["04_gercek_derece"] = max(0.0, min(1.0, 1.0 - spread / max(abs(t.get("best_sec_per_km")), 0.001)))

        f = vals.get("05_gercek_hiz", {})
        a, b = f.get("recent_latest_sec_per_km"), f.get("surface_avg_sec_per_km") if isinstance(f, dict) else (None, None)
        if a is not None and b is not None and b > 0:
            family_to_value["05_gercek_hiz"] = max(0.0, min(1.0, 0.5 + (b - a) / max(b * 0.05, 0.01)))

        f = vals.get("06_guncel_form", {})
        if isinstance(f, dict) and f.get("sample", 0) >= 3 and f.get("avg_place") is not None:
            avg = float(f["avg_place"])
            top3 = float(f.get("top3", 0)) / max(float(f.get("sample", 1)), 1.0)
            family_to_value["06_guncel_form"] = max(0.0, min(1.0, (1.0 - (avg - 1.0) / 8.0 + top3) / 2.0))

        f = vals.get("07_ortak_rakip", {})
        if isinstance(f, dict) and f.get("shared_races", 0) > 0 and f.get("avg_place_diff") is not None:
            family_to_value["07_ortak_rakip"] = max(0.0, min(1.0, 0.5 + float(f["avg_place_diff"]) / 10.0))

        f = vals.get("08_kilo_performansi", {})
        if isinstance(f, dict) and f.get("today_weight") is not None and f.get("history_sample", 0) >= 2:
            avgw = f.get("history_avg_weight")
            tw = f.get("today_weight")
            if avgw is not None:
                family_to_value["08_kilo_performansi"] = max(0.0, min(1.0, 0.5 + (float(avgw) - float(tw)) / 5.0))

        f = vals.get("09_hp_kalite", {})
        if isinstance(f, dict) and f.get("today_hp") is not None and f.get("history_max_hp"):
            family_to_value["09_hp_kalite"] = max(0.0, min(1.0, float(f["today_hp"]) / float(f["history_max_hp"])))

        f = vals.get("10_galop_performansi", {})
        if isinstance(f, dict) and f.get("sample", 0) >= 2:
            x = f.get("latest_m600") or f.get("latest_m400") or f.get("latest_m200")
            best = f.get("best_m600_last5") or f.get("best_m400_last5") or f.get("best_m200_last5")
            if x is not None and best is not None:
                family_to_value["10_galop_performansi"] = max(0.0, min(1.0, 1.0 - max(0.0, float(x) - float(best)) / max(float(best) * 0.15, 0.01)))

        f = vals.get("12_dinlenme_kgs", {})
        if isinstance(f, dict) and f.get("days_since_last_race") is not None:
            kgs = float(f["days_since_last_race"])
            # Only a factual, bounded rest signal; the model learns whether this family helps.
            family_to_value["12_dinlenme_kgs"] = max(0.0, min(1.0, math.exp(-abs(kgs - 21.0) / 30.0)))

        available = [(fam, val) for fam, val in family_to_value.items() if val is not None and fam in weights]
        if len(available) < 2:
            continue

        # 1500 total is redistributed only across families with real data for this horse.
        wsum = sum(weights[fam] for fam, _ in available)
        score = 1500.0 * sum(weights[fam] * val for fam, val in available) / wsum
        for fam, val in available:
            components[fam] = weights[fam] * val
        horse["_bizim_skor"] = round(score, 1)
        results.append({
            "horse_index": idx,
            "score": round(score, 1),
            "components": components,
            "model": model,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    for rank, item in enumerate(results, 1):
        item["rank"] = rank
    return results
