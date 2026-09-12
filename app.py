import streamlit as st
import pandas as pd
import re
from datetime import date
from typing import Any, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from worker.tjk_fetch import get_program, get_horse_enrichment


# ============================================================
# SAYFA AYARLARI
# ============================================================

st.set_page_config(
    page_title="Race Intelligence",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# HİPODROMLAR
# ============================================================

# Worker V1'de tanımlı şehirler.
# Arayüzde bunların tamamı gösterilmez; aşağıda seçilen tarih
# için gerçekten programı olanlar otomatik olarak filtrelenir.
ALL_CITIES = [
    "Ankara",
    "Kocaeli",
    "İstanbul",
    "Bursa",
    "İzmir",
    "Adana",
    "Elazığ",
    "Diyarbakır",
    "Şanlıurfa",
    "Antalya",
]


# ============================================================
# ANALİZ AĞIRLIKLARI
# ============================================================

DEFAULT_WEIGHTS = {
    "Pist / Mesafe": 22,
    "Ortak Rakip": 18,
    "Sınıf / HP": 14,
    "Güncel Form": 19,
    "Kilo": 12,
    "Derece": 8,
    "Galop / Tempo": 5,
    "Ham Hız": 3,
}

WEIGHT_KEYS = {
    "Pist / Mesafe": "w_pist",
    "Ortak Rakip": "w_ortak",
    "Sınıf / HP": "w_sinif",
    "Güncel Form": "w_form",
    "Kilo": "w_kilo",
    "Derece": "w_derece",
    "Galop / Tempo": "w_galop",
    "Ham Hız": "w_hiz",
}

for _criterion, _default in DEFAULT_WEIGHTS.items():
    if WEIGHT_KEYS[_criterion] not in st.session_state:
        st.session_state[WEIGHT_KEYS[_criterion]] = _default

def current_weights():
    return {
        criterion: int(st.session_state[WEIGHT_KEYS[criterion]])
        for criterion in DEFAULT_WEIGHTS
    }

ANALYSIS_WEIGHTS = current_weights()


# ============================================================
# SESSION STATE
# ============================================================

if "program_data" not in st.session_state:
    st.session_state.program_data = None

if "loaded_date" not in st.session_state:
    st.session_state.loaded_date = None

if "loaded_city" not in st.session_state:
    st.session_state.loaded_city = None

if "selected_race" not in st.session_state:
    st.session_state.selected_race = 1

if "analysis_mode" not in st.session_state:
    st.session_state.analysis_mode = "Gerçek veri"

if "real_analysis_requested" not in st.session_state:
    st.session_state.real_analysis_requested = False

if "real_analysis_done" not in st.session_state:
    st.session_state.real_analysis_done = False

if "selected_horse_no" not in st.session_state:
    st.session_state.selected_horse_no = None


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>

    .main-title {
        font-size: 32px;
        font-weight: 700;
        margin-bottom: 2px;
    }

    .sub-title {
        font-size: 15px;
        opacity: 0.75;
        margin-bottom: 20px;
    }

    .horse-title {
        font-size: 18px;
        font-weight: 700;
        margin-top: 15px;
        margin-bottom: 10px;
    }

    .ri-header {
        border: 1px solid rgba(128,128,128,.25);
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    .ri-title {
        font-size: 26px;
        font-weight: 800;
        letter-spacing: .3px;
    }

    .ri-subtitle {
        font-size: 13px;
        opacity: .72;
        margin-top: 3px;
    }

    .ri-clock {
        font-size: 12px;
        font-weight: 800;
        opacity: .7;
        letter-spacing: 1px;
    }

    .condition-box {
        border: 1px solid rgba(80,130,190,.30);
        border-radius: 7px;
        padding: 10px 12px;
        margin: 6px 0 12px 0;
        font-size: 13px;
        line-height: 1.55;
    }

    .model-note {
        font-size: 12px;
        opacity: .72;
        margin-top: -4px;
    }

    .race-condition-label {
        display:inline-block;
        margin-left:6px;
        padding:1px 6px;
        border-radius:5px;
        font-size:10px;
        font-weight:800;
        color:#fff;
    }

    .analysis-action {
        margin-top:4px;
    }

    .ri-table-wrap {
        width:100%;
        overflow-x:auto;
        border:1px solid rgba(80,100,130,.25);
        border-radius:7px;
    }

    .ri-table {
        border-collapse:collapse;
        width:100%;
        min-width:1180px;
        font-size:12px;
    }

    .ri-table th {
        background:#1268b3;
        color:#fff;
        font-weight:800;
        text-align:center;
        padding:8px 7px;
        border-right:1px solid rgba(255,255,255,.28);
        white-space:nowrap;
    }

    .ri-table td {
        padding:8px 7px;
        border-bottom:1px solid rgba(100,120,140,.18);
        border-right:1px solid rgba(100,120,140,.12);
        white-space:nowrap;
        text-align:center;
    }

    .ri-table td.horse-name {
        text-align:left;
        font-weight:800;
        min-width:150px;
    }

    .ri-table tr.rank1 { background:rgba(46,160,67,.16); }
    .ri-table tr.rank2 { background:rgba(255,193,7,.12); }
    .ri-table tr.rank3 { background:rgba(255,152,0,.10); }
    .ri-table tr:hover { background:rgba(80,130,190,.10); }

    .ri-table tr.selected-row td {
        background:#dff3ff !important;
        box-shadow:inset 3px 0 0 #0878d1;
        color:#16324d !important;
        font-weight:700;
    }

    .ri-table tr.rank1 td { background:rgba(46,160,67,.14); }
    .ri-table tr.rank2 td { background:rgba(255,193,7,.12); }
    .ri-table tr.rank3 td { background:rgba(255,152,0,.10); }


    .score-strong { font-weight:900; font-size:13px; }
    .analysis-badge {
        display:inline-block;
        padding:5px 10px;
        border-radius:5px;
        font-size:11px;
        font-weight:900;
        margin:2px 0 10px 0;
        border:1px solid rgba(20,80,130,.35);
    }
    .analysis-waiting { background:#eaf3fb; color:#075b9f; }
    .analysis-active { background:#e7f6ec; color:#147a35; }


    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# BAŞLIK — V34 GÖRÜNÜMÜ
# ============================================================

st.markdown(
    """
    <div class="ri-header">
        <div>
            <div class="ri-title">🏇 RACE INTELLIGENCE</div>
            <div class="ri-subtitle">
                Gerçek TJK geçmişi + galop + karşılaştırma motoru • V54 Worker uyumlu • kesin koşanlar
            </div>
        </div>
        <div class="ri-clock">CANLI MODEL</div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# TJK VERİ DURUMU
# ============================================================

def fetch_program_with_status(selected_date, selected_city, label):
    box = st.status(
        f"📡 {label}: {selected_city} için TJK verisi çekiliyor...",
        expanded=True,
    )
    box.write("TJK Günlük Yarış Programı isteği gönderiliyor...")
    try:
        result = load_program(selected_date, selected_city)
        races_count = len(result.get("races", [])) if isinstance(result, dict) else 0
        horse_count = (
            sum(len(r.get("horses", [])) for r in result.get("races", []))
            if isinstance(result, dict) else 0
        )
        box.write(f"✓ {races_count} koşu • {horse_count} at verisi alındı.")
        box.update(
            label=f"✅ {selected_city} TJK programı hazır",
            state="complete",
            expanded=False,
        )
        return result
    except Exception as exc:
        box.update(
            label=f"❌ {selected_city} TJK verisi alınamadı",
            state="error",
            expanded=True,
        )
        raise exc

# ============================================================
# PROGRAM GETİRME
# ============================================================

@st.cache_data(
    ttl=900,
    show_spinner=False,
)
def load_program(
    selected_date: date,
    city: str,
) -> Dict[str, Any]:

    return get_program(
        selected_date,
        city,
    )


# ============================================================
# SEÇİLEN TARİHTEKİ AKTİF HİPODROMLAR
# ============================================================

@st.cache_data(ttl=900, show_spinner=False)
def load_active_cities(selected_date: date) -> List[str]:
    """
    Yalnızca seçilen tarihte yarış programı dönen hipodromları bulur.

    Mevcut Worker V1 /api/tjk/data endpoint'i kullanılır;
    yeni Worker dosyası veya yeni API gerekmez.
    İstekler paralel yapılır, böylece şehirler tek tek beklenmez.
    """
    active = []

    def check_city(city: str):
        try:
            data = get_program(selected_date, city)
            races = data.get("races", []) if isinstance(data, dict) else []
            return city if isinstance(races, list) and len(races) > 0 else None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(check_city, city): city for city in ALL_CITIES}
        for future in as_completed(futures):
            city = future.result()
            if city:
                active.append(city)

    # Worker şehir sırasını koru; sonuçların tamamlanma sırasını kullanma.
    return [city for city in ALL_CITIES if city in active]


# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================

def display_value(
    value: Any,
    default: str = "-",
) -> str:

    if value is None:
        return default

    text = str(value).strip()

    if not text:
        return default

    return text


def get_race_number(
    race: Dict[str, Any],
    fallback: int,
) -> int:

    value = race.get(
        "race_number",
        fallback,
    )

    try:
        return int(value)
    except Exception:
        return fallback


def get_horse_name(
    horse: Dict[str, Any],
) -> str:

    return display_value(
        horse.get("at_ismi")
        or horse.get("At İsmi")
    )


def get_horse_number(
    horse: Dict[str, Any],
    fallback: int,
) -> str:

    value = (
        horse.get("numara")
        or horse.get("N")
    )

    return display_value(
        value,
        str(fallback),
    )


def get_horse_age(
    horse: Dict[str, Any],
) -> str:
    """
    TJK yaş kodunu okunabilir biçime çevirir.

    Örnek:
        3yde -> 3y Dişi İngiliz
        3yke -> 3y Erkek İngiliz
        3yda -> 3y Dişi Arap
        3yka -> 3y Erkek Arap
    """
    value = horse.get("yas") or horse.get("Yaş") or horse.get("age") or ""
    text = display_value(value)
    if text == "-":
        return "-"

    # Worker/TJK bazı satırlarda kodları boşluklu verir (ör. "3y k d").
    # Kodu yorumlayıp yanlış cinsiyet/ırk üretmek yerine yaş kısmını normalize ediyor,
    # TJK'nın geri kalan kodlarını aynen koruyoruz. Böylece veri uydurulmuyor.
    m = re.match(r"^(\d+)\s*y(?:\s+(.*))?$", text, flags=re.I)
    if m:
        age = m.group(1)
        rest = (m.group(2) or "").strip()
        return f"{age}y" + (f" {rest}" if rest else "")

    return text

def get_race_condition(race: Dict[str, Any]) -> str:
    """Koşu şartını Worker V1 meta.detail/meta.raceName üzerinden alır."""
    direct = race.get("condition")
    if direct:
        return display_value(direct)

    meta = race.get("meta")
    if isinstance(meta, dict):
        detail = meta.get("detail") or meta.get("raceName") or ""
        if detail:
            return display_value(detail)

    return "-"

def get_horse_weight(
    horse: Dict[str, Any],
) -> str:

    return display_value(
        horse.get("siklet")
        or horse.get("Sıklet")
    )


def get_horse_jockey(
    horse: Dict[str, Any],
) -> str:

    return display_value(
        horse.get("jokey")
        or horse.get("Jokey")
    )


def get_horse_hp(
    horse: Dict[str, Any],
) -> str:

    return display_value(
        horse.get("hp")
        or horse.get("HP")
    )


def get_horse_agf(
    horse: Dict[str, Any],
) -> str:

    return display_value(
        horse.get("agf")
        or horse.get("AGF")
    )


def get_horse_start(
    horse: Dict[str, Any],
) -> str:

    return display_value(
        horse.get("st")
        or horse.get("St")
    )


def get_horse_kgs(
    horse: Dict[str, Any],
) -> str:

    return display_value(
        horse.get("kgs")
        or horse.get("KGS")
    )


def get_horse_form(
    horse: Dict[str, Any],
) -> str:

    return display_value(
        horse.get("form")
        or horse.get("Forma")
    )




# ============================================================
# GERÇEK VERİ ZENGİNLEŞTİRME
# ============================================================

@st.cache_data(ttl=900, show_spinner=False)
def load_horse_enrichment(at_id: str, horse_name: str) -> Dict[str, Any]:
    try:
        return get_horse_enrichment(at_id, horse_name)
    except Exception as exc:
        return {
            "ok": False,
            "history": [],
            "workouts": [],
            "error": str(exc),
        }


def enrich_race_horses(horses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched = [dict(h) for h in horses if isinstance(h, dict)]

    def one(item):
        at_id = item.get("atId") or item.get("at_id") or ""
        name = get_horse_name(item)
        if not at_id:
            return item
        data = load_horse_enrichment(str(at_id), name)
        history = data.get("history", []) if isinstance(data, dict) else []
        workouts = data.get("workouts", []) if isinstance(data, dict) else []

        item["_history"] = history if isinstance(history, list) else []
        item["_workouts"] = workouts if isinstance(workouts, list) else []

        # V34: sahip / antrenör / bu yıl kazanç geçmiş gerçek yarışlardan.
        if item.get("owner") in (None, "") or item.get("trainer") in (None, ""):
            for row in item["_history"]:
                if not isinstance(row, dict):
                    continue
                if not item.get("owner") and row.get("owner"):
                    item["owner"] = row.get("owner")
                if not item.get("trainer") and row.get("trainer"):
                    item["trainer"] = row.get("trainer")
                if item.get("owner") and item.get("trainer"):
                    break

        # Son gerçek yarış: hedef tarihten önceki ilk geçerli kayıt.
        item["_last_race"] = None
        for row in item["_history"]:
            if isinstance(row, dict) and row.get("date") and row.get("time"):
                item["_last_race"] = row
                break

        # Bu yılki kazanç: gerçek geçmişteki prize alanlarının toplamı.
        # Tarihi hedef yarış yılına göre hesaplamak için selected_date daha sonra eklenir.
        return item

    with ThreadPoolExecutor(max_workers=min(6, max(1, len(enriched)))) as executor:
        futures = [executor.submit(one, h) for h in enriched]
        return [f.result() for f in futures]


def _history_year(date_text: Any) -> int | None:
    m = re.search(r"(20\d{2})", str(date_text or ""))
    return int(m.group(1)) if m else None


def _money_number(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).replace(".", "").replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else 0.0


def year_earnings(horse: Dict[str, Any], target_year: int) -> float:
    total = 0.0
    for row in horse.get("_history", []):
        if not isinstance(row, dict):
            continue
        if _history_year(row.get("date")) != target_year:
            continue
        total += _money_number(row.get("prize"))
    return total


def latest_workout(horse: Dict[str, Any]) -> Dict[str, Any] | None:
    workouts = horse.get("_workouts", [])
    if not isinstance(workouts, list):
        return None
    for w in workouts:
        if not isinstance(w, dict):
            continue
        if any(str(w.get(k) or "").strip() for k in ("m800", "m1000", "m1200", "m400")):
            return w
    return None


def workout_display(horse: Dict[str, Any]) -> str:
    w = latest_workout(horse)
    if not w:
        return "-"
    for key, label in (
        ("m800", "800"),
        ("m1000", "1000"),
        ("m1200", "1200"),
        ("m400", "400"),
    ):
        value = display_value(w.get(key), "")
        if value:
            return f"{value} ({label}m)"
    return "-"


def last_race_display(horse: Dict[str, Any]) -> str:
    row = horse.get("_last_race")
    if not isinstance(row, dict):
        return "-"
    time = display_value(row.get("time"), "")
    distance = display_value(row.get("distance"), "")
    surface = display_value(row.get("surface"), "")
    if time:
        return " • ".join(x for x in (time, f"{distance}m" if distance else "", surface) if x)
    return "-"


# ============================================================
# RANKING / ANALİZ MOTORU
# ============================================================

def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(',', '.')
    if not text:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def _time_seconds(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(',', '.')
    m = re.search(r"(\d+):(\d+(?:\.\d+)?)", text)
    if m:
        try:
            return float(m.group(1)) * 60.0 + float(m.group(2))
        except Exception:
            return None
    n = _number(text)
    return n


def _relative_scores(values: List[float | None], higher_is_better: bool = True) -> List[float]:
    usable = [v for v in values if v is not None]
    if len(usable) < 2 or max(usable) == min(usable):
        return [50.0 if v is None else 100.0 for v in values]
    lo, hi = min(usable), max(usable)
    out = []
    for v in values:
        if v is None:
            out.append(50.0)
        elif higher_is_better:
            out.append(100.0 * (v - lo) / (hi - lo))
        else:
            out.append(100.0 * (hi - v) / (hi - lo))
    return out


def _form_score(value: Any) -> float:
    digits = [int(x) for x in re.findall(r"[1-9]", str(value or ""))]
    if not digits:
        return 50.0
    # TJK formunda soldaki sonuç daha günceldir; güncele biraz daha fazla ağırlık ver.
    weights = [1.50, 1.30, 1.15, 1.00, 0.90, 0.80]
    used = digits[:6]
    w = weights[:len(used)]
    avg = sum(a * b for a, b in zip(used, w)) / sum(w)
    return max(0.0, min(100.0, 100.0 * (9.0 - avg) / 8.0))


def _pist_mesafe_score(horse: Dict[str, Any], race: Dict[str, Any], city: str) -> float:
    meta = race.get("meta") if isinstance(race.get("meta"), dict) else {}
    target_distance = _number(race.get("distance") or meta.get("distance"))
    target_surface = str(race.get("surface") or meta.get("surface") or "").strip().lower()

    history = horse.get("_history", [])
    matching = []
    for row in history:
        if not isinstance(row, dict):
            continue
        d = _number(row.get("distance"))
        s = str(row.get("surface") or "").strip().lower()
        if target_distance is not None and d == target_distance and target_surface:
            if target_surface.split()[0] in s:
                matching.append(row)

    places = [_number(x.get("place")) for x in matching]
    places = [x for x in places if x is not None and x > 0]
    if places:
        return sum(max(0.0, 100.0 - (p - 1.0) * 10.0) for p in places) / len(places)

    # Aynı pistte yakın mesafe varsa ikinci seviye.
    nearby = []
    for row in history:
        if not isinstance(row, dict):
            continue
        d = _number(row.get("distance"))
        s = str(row.get("surface") or "").strip().lower()
        if d is None or target_distance is None:
            continue
        if abs(d - target_distance) <= 100 and target_surface and target_surface.split()[0] in s:
            p = _number(row.get("place"))
            if p is not None and p > 0:
                nearby.append(p)
    if nearby:
        return sum(max(0.0, 90.0 - (p - 1.0) * 10.0) for p in nearby) / len(nearby)

    return 50.0


def calculate_ranking(
    horses: List[Dict[str, Any]],
    race: Dict[str, Any],
    city: str,
) -> List[Dict[str, Any]]:
    if not horses:
        return []

    hp_values = [_number(h.get("hp")) for h in horses]
    weight_values = [_number(h.get("weight") or h.get("siklet")) for h in horses]

    hp_scores = _relative_scores(hp_values, True)
    weight_scores = _relative_scores(weight_values, False)

    results = []
    for i, horse in enumerate(horses):
        pist = _pist_mesafe_score(horse, race, city)

        # Gerçek ortak rakip: aynı tarih + şehir + mesafe üzerinden geçmiş yarış kayıtları.
        common_scores = []
        for other in horses:
            if other is horse:
                continue
            for a in horse.get("_history", []):
                if not isinstance(a, dict):
                    continue
                for b in other.get("_history", []):
                    if not isinstance(b, dict):
                        continue
                    if (
                        str(a.get("date")) == str(b.get("date"))
                        and str(a.get("city")).lower() == str(b.get("city")).lower()
                        and str(a.get("distance")) == str(b.get("distance"))
                    ):
                        pa = _number(a.get("place"))
                        pb = _number(b.get("place"))
                        if pa is not None and pb is not None:
                            common_scores.append(100.0 if pa < pb else 0.0 if pa > pb else 50.0)
        ortak = sum(common_scores) / len(common_scores) if common_scores else 50.0

        sinif = hp_scores[i]
        form = _form_score(horse.get("form") or horse.get("last6"))
        kilo = weight_scores[i]

        # Gerçek geçmişteki derece / aynı pist normalize.
        times = []
        meta = race.get("meta") if isinstance(race.get("meta"), dict) else {}
        target_surface = str(race.get("surface") or meta.get("surface") or "").lower()
        for row in horse.get("_history", []):
            if not isinstance(row, dict):
                continue
            sec = _time_seconds(row.get("time"))
            dist = _number(row.get("distance"))
            surf = str(row.get("surface") or "").lower()
            if sec and dist and target_surface and target_surface.split()[0] in surf:
                times.append(sec / (dist / 1000.0))
        derece = 50.0
        if times:
            avg = sum(times) / len(times)
            derece = max(0.0, min(100.0, 100.0 - (avg - min(times)) / max(0.001, max(times) - min(times)) * 100.0)) if len(times) > 1 else 70.0

        w = latest_workout(horse)
        workout_values = []
        if w:
            for key in ("m1200", "m1000", "m800", "m600", "m400", "m200"):
                sec = _time_seconds(w.get(key))
                if sec is not None:
                    workout_values.append(sec)
        galop_raw = min(workout_values) if workout_values else None
        galop = 50.0 if galop_raw is None else max(0.0, min(100.0, 100.0 - galop_raw))

        last = horse.get("_last_race")
        hiz = 50.0
        if isinstance(last, dict):
            sec = _time_seconds(last.get("time"))
            dist = _number(last.get("distance"))
            if sec and dist:
                hiz = dist / sec * 3.6

        components = {
            "Pist / Mesafe": pist,
            "Ortak Rakip": ortak,
            "Sınıf / HP": sinif,
            "Güncel Form": form,
            "Kilo": kilo,
            "Derece": derece,
            "Galop / Tempo": galop,
            "Ham Hız": hiz,
        }

        weights = current_weights()
        total_w = sum(weights.values())
        ham = sum(components[k] * weights[k] for k in weights)
        final_score = ham / total_w if total_w else 0.0

        results.append({
            "horse_index": i,
            "score": round(final_score, 2),
            "components": components,
            "son_hiz": hiz,
            "galop": workout_display(horse),
        })

    results.sort(key=lambda x: (-x["score"], x["horse_index"]))
    for rank, item in enumerate(results, 1):
        item["rank"] = rank
        score = item["score"]
        item["label"] = (
            "Çok Güçlü" if score >= 75 else
            "Güçlü" if score >= 65 else
            "Şanslı" if score >= 55 else
            "Sürpriz" if score >= 45 else
            "Zayıf"
        )
    return results


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("🏇 Yarış Programı")


selected_date = st.sidebar.date_input(
    "Tarih",
    value=date.today(),
)


# ============================================================
# HİPODROM
# ============================================================

with st.sidebar:
    with st.spinner("TJK'daki aktif hipodromlar kontrol ediliyor..."):
        active_cities = load_active_cities(selected_date)

if not active_cities:
    st.sidebar.warning(
        f"{selected_date.strftime('%d/%m/%Y')} tarihinde TJK'dan yarış programı olan hipodrom bulunamadı."
    )
    st.info(
        "Bu tarih için hipodrom listesi alınamadı. TJK Worker bağlantısını kontrol edin."
    )
    st.stop()

if st.session_state.loaded_city in active_cities:
    default_city_index = active_cities.index(
        st.session_state.loaded_city
    )
else:
    default_city_index = 0

selected_city = st.sidebar.selectbox(
    "Hipodrom",
    active_cities,
    index=default_city_index,
)

st.sidebar.caption(
    f"{len(active_cities)} hipodromda yarış var • {selected_date.strftime('%d/%m/%Y')}"
)


# ============================================================
# PROGRAMI GETİR
# ============================================================

get_program_clicked = st.sidebar.button(
    "📥 PROGRAMI GETİR",
    use_container_width=True,
)


if get_program_clicked:

    # Önce eski programı temizle
    st.session_state.program_data = None

    st.session_state.loaded_date = None
    st.session_state.loaded_city = None

    try:

        result = fetch_program_with_status(
            selected_date,
            selected_city,
            "PROGRAM GETİR",
        )

        st.session_state.program_data = result
        st.session_state.loaded_date = selected_date
        st.session_state.loaded_city = selected_city
        st.session_state.selected_race = 1

    except Exception as exc:

        st.error(
            "Program alınırken hata oluştu."
        )

        st.code(
            f"{type(exc).__name__}: {exc}"
        )

        st.stop()


# ============================================================
# OTOMATİK PROGRAM YÜKLE
# ============================================================

program_data = st.session_state.program_data


if program_data is None:

    try:

        program_data = fetch_program_with_status(
            selected_date,
            selected_city,
            "PROGRAM HAZIRLANIYOR",
        )

        st.session_state.program_data = program_data
        st.session_state.loaded_date = selected_date
        st.session_state.loaded_city = selected_city
        st.session_state.selected_race = 1

    except Exception as exc:

        st.error(
            "Beklenmeyen hata oluştu."
        )

        st.code(
            f"{type(exc).__name__}: {exc}"
        )

        st.stop()


# ============================================================
# PROGRAM GEÇERLİ Mİ?
# ============================================================

if not isinstance(
    program_data,
    dict,
):

    st.error(
        "TJK'dan gelen program verisi geçersiz."
    )

    st.stop()


# ============================================================
# TARİH / HİPODROM DEĞİŞİKLİĞİ KONTROLÜ
# ============================================================

loaded_date = st.session_state.loaded_date
loaded_city = st.session_state.loaded_city


if (
    loaded_date != selected_date
    or loaded_city != selected_city
):

    try:

        program_data = fetch_program_with_status(
            selected_date,
            selected_city,
            "PROGRAM YENİLENİYOR",
        )

        st.session_state.program_data = program_data
        st.session_state.loaded_date = selected_date
        st.session_state.loaded_city = selected_city
        st.session_state.selected_race = 1

    except Exception as exc:

        st.error(
            "Program yenilenirken hata oluştu."
        )

        st.code(
            f"{type(exc).__name__}: {exc}"
        )

        st.stop()


# ============================================================
# KOŞULAR
# ============================================================

races = program_data.get(
    "races",
    [],
)


if not isinstance(
    races,
    list,
):

    races = []


if not races:

    st.warning(
        f"{selected_city} — "
        f"{selected_date.strftime('%d/%m/%Y')} "
        "için koşu bulunamadı."
    )

    st.info(
        "TJK'dan bu tarih ve hipodrom için "
        "koşu verisi alınamadı."
    )

    # Debug göster
    with st.expander(
        "🔧 Teknik Debug"
    ):

        st.json(
            program_data
        )

    st.stop()


# ============================================================
# PROGRAM BİLGİSİ
# ============================================================

st.success(
    f"{selected_city} — "
    f"{selected_date.strftime('%d/%m/%Y')} — "
    f"{len(races)} koşu bulundu."
)


# ============================================================
# KOŞU SEÇİMİ
# ============================================================

st.subheader("Koşular")


# Koşu butonları pist türüne göre V34 renk düzeninde boyanır.
_race_css = ["<style>"]
for _idx, _race in enumerate(races):
    _surface = str(_race.get("surface") or (_race.get("meta") or {}).get("surface") or "").lower()
    _is_dirt = "kum" in _surface
    _bg = "#b77a2b" if _is_dirt else "#239447"
    _race_css.append(
        f'.st-key-race_button_{get_race_number(_race, _idx + 1)} button'
        f'{{background:{_bg};border-color:{_bg};color:#fff;font-weight:800;}}'
    )
    _race_css.append(
        f'.st-key-race_button_{get_race_number(_race, _idx + 1)} button:hover'
        f'{{filter:brightness(1.08);color:#fff;}}'
    )
_race_css.append("</style>")
st.markdown("\n".join(_race_css), unsafe_allow_html=True)

race_columns = st.columns(
    len(races)
)


for index, race in enumerate(races):

    race_number = get_race_number(
        race,
        index + 1,
    )

    race_time = display_value(
        race.get("race_time")
    )

    if race_time != "-":

        label = (
            f"{race_number} {race_time}"
        )

    else:

        label = str(race_number)

    selected = (
        st.session_state.selected_race
        == race_number
    )

    with race_columns[index]:

        if st.button(
            label,
            key=f"race_button_{race_number}",
            use_container_width=True,
            type=(
                "primary"
                if selected
                else "secondary"
            ),
        ):

            st.session_state.selected_race = (
                race_number
            )

            st.rerun()


# ============================================================
# SEÇİLEN KOŞUYU BUL
# ============================================================

selected_race = None


for index, race in enumerate(races):

    race_number = get_race_number(
        race,
        index + 1,
    )

    if (
        race_number
        == st.session_state.selected_race
    ):

        selected_race = race

        break


# Eğer seçilen koşu bulunamazsa ilk koşuyu göster
if selected_race is None:

    selected_race = races[0]

    st.session_state.selected_race = (
        get_race_number(
            selected_race,
            1,
        )
    )


# Koşu değiştiğinde eski at seçimini ve eski analiz durumunu temizle.
_current_race_signature = (
    str(st.session_state.get("loaded_date")),
    str(st.session_state.get("loaded_city")),
    int(st.session_state.get("selected_race", 1)),
)
if st.session_state.get("_last_race_signature") != _current_race_signature:
    st.session_state.selected_horse_no = None
    st.session_state.real_analysis_requested = False
    st.session_state.real_analysis_done = False
    st.session_state["_last_race_signature"] = _current_race_signature

# ============================================================
# CANLI MODEL AYARLARI
# ============================================================

def _reset_model_weights():
    for criterion, value in DEFAULT_WEIGHTS.items():
        st.session_state[WEIGHT_KEYS[criterion]] = value
    st.session_state["analysis_mode"] = "Gerçek veri"
    st.session_state["real_analysis_requested"] = True


def _request_real_analysis():
    st.session_state["analysis_mode"] = "Gerçek veri"
    st.session_state["real_analysis_requested"] = True
    st.session_state["real_analysis_done"] = False


def _request_manual_analysis():
    st.session_state["analysis_mode"] = "Manuel"
    st.session_state["real_analysis_requested"] = False
    st.session_state["real_analysis_done"] = True


# Widget state'leri widget'lar oluşturulmadan önce güvenli şekilde sıfırlanır.
if st.session_state.pop("_reset_model_next_run", False):
    for criterion, value in DEFAULT_WEIGHTS.items():
        st.session_state[WEIGHT_KEYS[criterion]] = value

with st.expander("⚙️ CANLI MODEL AYARLARI", expanded=True):
    st.caption(
        "Kaydırıcıları değiştirdiğinde TJK'ya yeniden istek gönderilmez. "
        "Elde edilen gerçek veriler üzerinden puan ve sıralama yeniden hesaplanır."
    )

    weight_items = list(DEFAULT_WEIGHTS.items())
    cols = st.columns(4)

    for idx, (criterion, default_value) in enumerate(weight_items):
        key = WEIGHT_KEYS[criterion]
        with cols[idx % 4]:
            st.slider(
                criterion,
                min_value=0,
                max_value=40,
                key=key,
                step=1,
            )

    ANALYSIS_WEIGHTS = current_weights()
    weight_total = sum(ANALYSIS_WEIGHTS.values())
    normalized = {
        k: (v * 100.0 / weight_total if weight_total else 0.0)
        for k, v in ANALYSIS_WEIGHTS.items()
    }

    c1, c2, c3 = st.columns([1.15, 1.0, 1.0])
    with c1:
        st.button(
            "🔄 GERÇEK VERİYLE ANALİZ",
            key="real_analysis_button",
            use_container_width=True,
            on_click=_request_real_analysis,
        )
    with c2:
        st.button(
            "🧠 MANUEL ANALİZİ UYGULA",
            key="manual_analysis_button",
            use_container_width=True,
            on_click=_request_manual_analysis,
            type="primary",
        )
    with c3:
        st.button(
            "↩️ VARSAYILANLARA DÖN",
            key="reset_model_button",
            use_container_width=True,
            on_click=_reset_model_weights,
        )

    st.markdown(
        f"<div style='text-align:right;font-size:13px;margin-top:5px'>"
        f"<b>Ham: {weight_total}</b> • <b>Normalize: 100</b>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Normalize edilmiş: "
        + " • ".join(f"{k} %{normalized[k]:.1f}" for k in ANALYSIS_WEIGHTS)
    )
    st.caption(
        f"Analiz modu: **{st.session_state.get('analysis_mode', 'Gerçek veri')}**"
    )

# ============================================================
# KOŞU BİLGİLERİ
# ============================================================

race_number = get_race_number(selected_race, 1)
race_time = display_value(selected_race.get("race_time"))
distance = display_value(selected_race.get("distance"))
surface = display_value(selected_race.get("surface"))
condition = get_race_condition(selected_race)

st.markdown("---")

st.markdown(
    f"<h2 style='margin-bottom:6px'>{race_number}. Koşu {race_time if race_time != '-' else ''}</h2>",
    unsafe_allow_html=True,
)

analysis_badge = (
    "SKORLAMA AKTİF"
    if st.session_state.get("real_analysis_done")
    else "ANALİZ BEKLENİYOR"
)
st.markdown(
    f"<div class='analysis-badge {'analysis-active' if analysis_badge == 'SKORLAMA AKTİF' else 'analysis-waiting'}'>{analysis_badge}</div>",
    unsafe_allow_html=True,
)

st.markdown(
    f"<div class='condition-box'><b>{condition}</b></div>",
    unsafe_allow_html=True,
)

info1, info2, info3 = st.columns(3)
with info1:
    st.metric("Saat", race_time)
with info2:
    st.metric("Mesafe", f"{distance} m" if distance != "-" and "m" not in distance.lower() else distance)
with info3:
    st.metric("Pist", surface)


# ============================================================
# AT LİSTESİ
# ============================================================

# ============================================================
# AT LİSTESİ
# ============================================================

horses = selected_race.get(
    "horses",
    [],
)


if not isinstance(
    horses,
    list,
):

    horses = []


st.markdown(
    '<div class="horse-title">'
    f"🐎 Atlar ({len(horses)})"
    "</div>",
    unsafe_allow_html=True,
)


if not horses:

    st.warning(
        "Seçilen koşuya ait at verisi henüz alınmadı."
    )

else:

    # GERÇEK VERİYLE ANALİZ: Worker V1'in mevcut /api/tjk/horsedata
    # endpointi üzerinden her koşan atın geçmiş + galop verisini al.
    if st.session_state.get("real_analysis_requested"):
        analysis_status = st.status(
            "🔎 GERÇEK VERİYLE ANALİZ: TJK geçmiş koşu + galop verileri çekiliyor...",
            expanded=True,
        )
        analysis_status.write(
            f"{len(horses)} koşan at için gerçek geçmiş ve galop verileri sorgulanıyor..."
        )
        try:
            horses = enrich_race_horses(horses)
            ok_count = sum(
                1 for h in horses
                if h.get("_history") or h.get("_workouts")
            )
            analysis_status.write(
                f"✓ {ok_count}/{len(horses)} at için gerçek veri alındı."
            )
            analysis_status.update(
                label="✅ GERÇEK VERİ ANALİZİ TAMAMLANDI",
                state="complete",
                expanded=False,
            )
            st.session_state.real_analysis_done = True
        except Exception as exc:
            analysis_status.update(
                label="❌ GERÇEK VERİ ANALİZİ HATASI",
                state="error",
                expanded=True,
            )
            st.error(f"Gerçek veri analizi sırasında hata: {exc}")
        selected_race["horses"] = horses
        st.session_state.real_analysis_requested = False

    ranking = calculate_ranking(horses, selected_race, selected_city)
    by_index = {item["horse_index"]: item for item in ranking}

    # V34 analiz tablosu için sıralama indeksleri.
    by_index = {item["horse_index"]: item for item in ranking}

    # ========================================================
    # V34 TABLOSU — TIKLANABİLİR SATIR + BAŞLIK SIRALAMA/FİLTRE
    # ========================================================
    target_year = selected_date.year
    table_rows = []

    for horse_index, horse in enumerate(horses):
        if not isinstance(horse, dict):
            continue

        form = get_horse_form(horse)
        form_digits = "".join(re.findall(r"[0-9Xx-]", form)) if form != "-" else "-"
        r = by_index.get(
            horse_index,
            {"rank": "-", "score": 0.0, "label": "-", "components": {}},
        )

        owner = horse.get("owner") or ""
        trainer = horse.get("trainer") or ""
        for hist in horse.get("_history", []):
            if not isinstance(hist, dict):
                continue
            if not owner and hist.get("owner"):
                owner = hist.get("owner")
            if not trainer and hist.get("trainer"):
                trainer = hist.get("trainer")
            if owner and trainer:
                break

        comps = r.get("components", {})
        class_quality = float(comps.get("Sınıf / HP", 50.0))
        current_form = float(comps.get("Güncel Form", 50.0))

        table_rows.append({
            "_horse_index": horse_index,
            "Sıra": r["rank"],
            "No": get_horse_number(horse, horse_index + 1),
            "At İsmi / Orijin": get_horse_name(horse),
            "Yaş": get_horse_age(horse),
            "Sıklet": get_horse_weight(horse),
            "Jokey": get_horse_jockey(horse),
            "St": get_horse_start(horse),
            "HP": get_horse_hp(horse),
            "Son 6 Y.": form_digits,
            "KGS": get_horse_kgs(horse),
            "s20": display_value(horse.get("s20")),
            "En İyi D.": display_value(horse.get("bestTime")),
            "Gny": display_value(horse.get("odds")),
            "AGF": get_horse_agf(horse),
            "BİZİM SKOR": r["score"],
            "SINIF / KALİTE": round(class_quality, 1),
            "GÜNCEL SINIF": round(current_form, 1),
            "SINIF AVANTAJI": round(class_quality - current_form, 1),
            "SON GALOP": workout_display(horse),
            "SON KOŞU": last_race_display(horse),
            "BU YIL KAZANÇ": year_earnings(horse, target_year),
            "Sahip": owner or "-",
            "Antrenör": trainer or "-",
        })

    df = pd.DataFrame(table_rows)
    display_columns = [
        "Sıra", "No", "At İsmi / Orijin", "Yaş", "Sıklet", "Jokey",
        "St", "HP", "Son 6 Y.", "KGS", "s20", "En İyi D.", "Gny", "AGF",
        "BİZİM SKOR", "SINIF / KALİTE", "GÜNCEL SINIF", "SINIF AVANTAJI",
        "SON GALOP", "SON KOŞU", "BU YIL KAZANÇ", "Sahip", "Antrenör",
    ]
    df_display = df[display_columns].copy()

    column_config = {
        "Sıra": st.column_config.NumberColumn("Sıra", format="%d"),
        "No": st.column_config.TextColumn("No"),
        "At İsmi / Orijin": st.column_config.TextColumn("At İsmi / Orijin"),
        "BİZİM SKOR": st.column_config.NumberColumn("BİZİM SKOR", format="%.2f"),
        "SINIF / KALİTE": st.column_config.NumberColumn("SINIF / KALİTE", format="%.1f"),
        "GÜNCEL SINIF": st.column_config.NumberColumn("GÜNCEL SINIF", format="%.1f"),
        "SINIF AVANTAJI": st.column_config.NumberColumn("SINIF AVANTAJI", format="%.1f"),
        "BU YIL KAZANÇ": st.column_config.NumberColumn("BU YIL KAZANÇ", format="%,.0f ₺"),
    }

    def _row_style(row):
        rank = row.get("Sıra")
        if rank == 1:
            return ["background-color: rgba(46,160,67,.18); font-weight:700"] * len(row)
        if rank == 2:
            return ["background-color: rgba(255,193,7,.15); font-weight:700"] * len(row)
        if rank == 3:
            return ["background-color: rgba(255,152,0,.13); font-weight:700"] * len(row)
        return ["background-color: rgba(238,247,255,.85)"] * len(row)

    styled_df = (
        df_display.style
        .apply(_row_style, axis=1)
        .set_table_styles([
            {
                "selector": "th",
                "props": [
                    ("background-color", "#0b66b3"),
                    ("color", "white"),
                    ("font-weight", "800"),
                    ("font-size", "11px"),
                    ("text-align", "center"),
                ],
            },
            {
                "selector": "td",
                "props": [
                    ("font-size", "10px"),
                    ("white-space", "nowrap"),
                ],
            },
        ])
    )

    st.caption(
        "📊 Sütun başlığına tıklayarak artan/azalan sıralama yap. "
        "Tablonun araç çubuğundaki arama ile filtrele. "
        "Bir at satırına tıklayınca gerçek geçmiş ve galop bölümü açılır."
    )

    table_event = st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
        key="horse_table",
        on_select="rerun",
        selection_mode="single-row",
        height=430,
    )

    selected_rows = []
    try:
        selected_rows = list(table_event.selection.rows)
    except Exception:
        selected_rows = []

    if selected_rows:
        selected_display_row = int(selected_rows[0])
        if 0 <= selected_display_row < len(df):
            selected_horse_index = int(df.iloc[selected_display_row]["_horse_index"])
            selected_horse = horses[selected_horse_index]
            st.session_state.selected_horse_no = get_horse_number(
                selected_horse,
                selected_horse_index + 1,
            )

            if not selected_horse.get("_history") and not selected_horse.get("_workouts"):
                horse_status = st.status(
                    f"🐎 {get_horse_name(selected_horse)} için gerçek koşu ve galop verileri çekiliyor...",
                    expanded=True,
                )
                horse_status.write("Worker V1 /api/tjk/horsedata sorgulanıyor...")
                try:
                    enriched_one = enrich_race_horses([selected_horse])
                    if enriched_one:
                        horses[selected_horse_index] = enriched_one[0]
                        selected_race["horses"] = horses
                        selected_horse = horses[selected_horse_index]
                    if selected_horse.get("_history") or selected_horse.get("_workouts"):
                        horse_status.update(
                            label="✅ Atın gerçek koşu ve galop verileri hazır",
                            state="complete",
                            expanded=False,
                        )
                    else:
                        horse_status.update(
                            label="⚠️ TJK bu at için geçmiş/galop verisi döndürmedi",
                            state="complete",
                            expanded=True,
                        )
                except Exception as exc:
                    horse_status.update(
                        label="❌ At geçmişi/galop sorgusu başarısız",
                        state="error",
                        expanded=True,
                    )
                    st.error(str(exc))

    selected_no = st.session_state.get("selected_horse_no")
    if selected_no is not None:
        selected_horse = next(
            (
                h for h in horses
                if str(get_horse_number(h, 0)) == str(selected_no)
            ),
            None,
        )

        if selected_horse:
            st.markdown("---")
            st.subheader(
                f"🐎 {get_horse_number(selected_horse, 0)} - {get_horse_name(selected_horse)}"
            )

            d1, d2, d3, d4 = st.columns(4)
            with d1:
                st.metric("Son Galop", workout_display(selected_horse))
            with d2:
                st.metric(
                    "Bu Yıl Kazanç",
                    f"{year_earnings(selected_horse, selected_date.year):,.0f} ₺",
                )
            with d3:
                st.metric("Sahip", display_value(selected_horse.get("owner")))
            with d4:
                st.metric("Antrenör", display_value(selected_horse.get("trainer")))

            with st.expander("📋 GERÇEK KOŞU GEÇMİŞİ", expanded=True):
                hist = selected_horse.get("_history", [])
                if hist:
                    st.dataframe(
                        pd.DataFrame(hist),
                        use_container_width=True,
                        hide_index=True,
                        height=330,
                    )
                else:
                    st.warning("Bu at için TJK gerçek koşu geçmişi gelmedi.")

            with st.expander("🏇 GERÇEK GALOP KAYITLARI", expanded=True):
                workouts = selected_horse.get("_workouts", [])
                if workouts:
                    st.dataframe(
                        pd.DataFrame(workouts),
                        use_container_width=True,
                        hide_index=True,
                        height=260,
                    )
                else:
                    st.warning("Bu at için TJK gerçek galop kaydı gelmedi.")

    # Analiz özeti
    if ranking:
        top = ranking[0]
        top_horse = horses[top["horse_index"]]
        st.success(
            f"🏆 1. Sıra: {get_horse_number(top_horse, top['horse_index'] + 1)} "
            f"- {get_horse_name(top_horse)} • {top['score']:.2f} puan • {top['label']}"
        )
        if len(ranking) >= 3:
            summary = "  |  ".join(
                f"{x['rank']}. {get_horse_name(horses[x['horse_index']])} ({x['score']:.2f})"
                for x in ranking[:3]
            )
            st.caption(summary)

        with st.expander("📊 Puan kırılımını göster"):
            breakdown_rows = []
            for item in ranking:
                horse = horses[item["horse_index"]]
                row = {
                    "Sıra": item["rank"],
                    "No": get_horse_number(horse, item["horse_index"] + 1),
                    "At": get_horse_name(horse),
                    "Puan": item["score"],
                }
                row.update({k: round(v, 1) for k, v in item["components"].items()})
                breakdown_rows.append(row)
            st.dataframe(
                pd.DataFrame(breakdown_rows),
                use_container_width=True,
                hide_index=True,
                column_config={"Puan": st.column_config.NumberColumn("Puan", format="%.2f")},
            )
            st.caption(
                "Not: Günlük Worker verisinde ortak rakip geçmişi ayrı bir veri kümesi olarak gelmediği için "
                "Ortak Rakip kriteri şu aşamada nötr (%50) tutulur. Eksik veriye puan uydurulmaz. "
                "Ağırlık değişiklikleri üstteki canlı model ayarlarından uygulanır."
            )

    agf_values = [get_horse_agf(h) for h in horses if isinstance(h, dict)]
    if agf_values and all(v == "-" for v in agf_values):
        st.caption("AGF: TJK program kaynağında bu koşu için henüz değer yok; '-' gösteriliyor. Değer uydurulmaz.")


# ============================================================
# MODEL DURUMU
# ============================================================

st.markdown("---")
st.markdown(
    f"**CANLI MODEL:** Ham {sum(ANALYSIS_WEIGHTS.values())} • Normalize 100 • "
    f"Seçili koşu: {race_number}. koşu",
)
st.caption(
    "Model ağırlıkları üstteki CANLI MODEL AYARLARI bölümünden değiştirilebilir."
)

# ============================================================
# SİSTEM DURUMU
# ============================================================

st.markdown("---")


st.subheader(
    "⚙️ Sistem Durumu"
)


total_horses = 0


for race in races:

    race_horses = race.get(
        "horses",
        [],
    )

    if isinstance(
        race_horses,
        list,
    ):

        total_horses += len(
            race_horses
        )


status1, status2, status3, status4 = (
    st.columns(4)
)


with status1:

    st.metric(
        "TJK bağlantısı",
        "OK",
    )


with status2:

    st.metric(
        "Koşu sayısı",
        len(races),
    )


with status3:

    st.metric(
        "Toplam at",
        total_horses,
    )


with status4:

    st.metric(
        "Seçili hipodrom",
        selected_city,
    )


# ============================================================
# TEKNİK DEBUG
# ============================================================

with st.expander(
    "🔧 Teknik Debug"
):

    debug = program_data.get(
        "debug",
        {},
    )


    st.write(
        "Program özeti:"
    )


    st.json(
        {
            "ok": program_data.get(
                "ok"
            ),

            "source": program_data.get(
                "source"
            ),

            "date": program_data.get(
                "date"
            ),

            "city": program_data.get(
                "city"
            ),

            "race_count": program_data.get(
                "race_count"
            ),

            "total_horses": program_data.get(
                "total_horses"
            ),
        }
    )


    st.write(
        "Parser debug:"
    )


    st.json(
        debug
    )


    st.write(
        "Koşu bazında at sayıları:"
    )


    race_horse_counts = {}


    for index, race in enumerate(
        races
    ):

        number = get_race_number(
            race,
            index + 1,
        )

        race_horses = race.get(
            "horses",
            [],
        )

        if not isinstance(
            race_horses,
            list,
        ):

            race_horses = []


        race_horse_counts[
            str(number)
        ] = len(
            race_horses
        )


    st.json(
        race_horse_counts
    )


# ============================================================
# HAM AT VERİSİ
# ============================================================

show_raw_horses = st.checkbox(
    "Seçilen koşunun ham at verisini göster"
)


if show_raw_horses:

    st.json(
        horses
    )
