import streamlit as st
import pandas as pd
import re
from datetime import date
from typing import Any, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from worker.tjk_fetch import get_program


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
    best_distance = _number(horse.get("bestDistance"))
    best_city = str(horse.get("bestCity") or "").strip().lower()
    target_surface = str(race.get("surface") or meta.get("surface") or "").strip().lower()

    if best_distance is None:
        return 50.0

    distance_delta = abs(best_distance - target_distance) if target_distance is not None else 9999
    city_match = bool(best_city and city.strip().lower() in best_city)

    if distance_delta <= 1:
        return 100.0 if city_match else 85.0
    if distance_delta <= 100:
        return 75.0
    if distance_delta <= 200:
        return 65.0
    return 50.0


def calculate_ranking(horses: List[Dict[str, Any]], race: Dict[str, Any], city: str) -> List[Dict[str, Any]]:
    if not horses:
        return []

    hp_values = [_number(h.get("hp")) for h in horses]
    weight_values = [_number(h.get("weight") or h.get("siklet")) for h in horses]
    best_times = [_time_seconds(h.get("bestTime")) for h in horses]
    s20_values = [_number(h.get("s20")) for h in horses]

    hp_scores = _relative_scores(hp_values, True)
    weight_scores = _relative_scores(weight_values, False)
    degree_scores = _relative_scores(best_times, False)
    speed_scores = _relative_scores(s20_values, False)

    results = []
    for i, horse in enumerate(horses):
        pist = _pist_mesafe_score(horse, race, city)
        ortak = 50.0  # Ortak rakip geçmişi günlük program payload'ında bulunmuyor; nötr tutulur.
        sinif = hp_scores[i]
        form = _form_score(horse.get("form") or horse.get("last6"))
        kilo = weight_scores[i]
        derece = degree_scores[i]

        workout_time = _time_seconds(horse.get("workout"))
        # Galop zamanı okunabilir bir süre olarak gelirse karşılaştır; aksi halde nötr.
        workout_scores = _relative_scores(
            [_time_seconds(h.get("workout")) for h in horses],
            False,
        )
        galop = workout_scores[i] if workout_time is not None else 50.0
        hiz = speed_scores[i] if s20_values[i] is not None else 50.0

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
        ham = sum(components[k] * weights[k] for k in weights)
        final_score = ham / sum(weights.values()) if sum(weights.values()) else 0.0

        results.append({
            "horse_index": i,
            "score": round(final_score, 2),
            "components": components,
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

        with st.spinner(
            f"{selected_city} programı TJK'dan alınıyor..."
        ):

            result = load_program(
                selected_date,
                selected_city,
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

        with st.spinner(
            f"{selected_city} programı hazırlanıyor..."
        ):

            program_data = load_program(
                selected_date,
                selected_city,
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

        with st.spinner(
            f"{selected_city} programı yenileniyor..."
        ):

            program_data = load_program(
                selected_date,
                selected_city,
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
            f"{race_number}\n"
            f"{race_time}"
        )

    else:

        label = str(
            race_number
        )

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


# ============================================================
# CANLI MODEL AYARLARI
# ============================================================

with st.expander("⚙️ CANLI MODEL AYARLARI", expanded=True):
    st.caption(
        "Kaydırıcıları değiştirdiğinde puan ve sıralama anında yeniden hesaplanır. "
        "TJK'ya yeniden istek gönderilmez."
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
                help=f"{criterion} kriterinin model içindeki ham ağırlığı.",
            )

    ANALYSIS_WEIGHTS = current_weights()
    weight_total = sum(ANALYSIS_WEIGHTS.values())
    normalized = {
        k: (v * 100.0 / weight_total if weight_total else 0.0)
        for k, v in ANALYSIS_WEIGHTS.items()
    }

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("↩️ GERÇEK VERİYLE VARSAYILANLARA DÖN", use_container_width=True):
            for criterion, value in DEFAULT_WEIGHTS.items():
                st.session_state[WEIGHT_KEYS[criterion]] = value
            st.rerun()
    with c2:
        st.button(
            "🧠 MANUEL ANALİZİ UYGULA",
            use_container_width=True,
            type="primary",
        )
    with c3:
        st.markdown(
            f"<div style='text-align:right;padding-top:8px;font-size:13px;'>"
            f"<b>Ham: {weight_total}</b> • <b>Normalize: 100</b>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.caption(
        "Normalize edilmiş ağırlıklar: "
        + " • ".join(f"{k} %{normalized[k]:.1f}" for k in ANALYSIS_WEIGHTS)
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

    ranking = calculate_ranking(horses, selected_race, selected_city)
    by_index = {item["horse_index"]: item for item in ranking}

    table_rows = []

    for horse_index, horse in enumerate(horses):
        if not isinstance(horse, dict):
            continue

        form = get_horse_form(horse)
        form_digits = " ".join(re.findall(r"[0-9Xx-]", form)) if form != "-" else "-"
        r = by_index.get(horse_index, {"rank": "-", "score": 0, "label": "-"})

        table_rows.append({
            "Sıra": r["rank"],
            "No": get_horse_number(horse, horse_index + 1),
            "At": get_horse_name(horse),
            "Yaş": get_horse_age(horse),
            "Kilo": get_horse_weight(horse),
            "Jokey": get_horse_jockey(horse),
            "HP": get_horse_hp(horse),
            "AGF": get_horse_agf(horse),
            "St": get_horse_start(horse),
            "KGS": get_horse_kgs(horse),
            "Form": form_digits,
            "Puan": r["score"],
        })

    df = pd.DataFrame(table_rows)

    def ranking_row_style(row):
        styles = [""] * len(row)
        try:
            rank = int(row.get("Sıra", 999))
        except Exception:
            rank = 999
        if rank == 1:
            style = "font-weight:800; background-color: rgba(46, 160, 67, 0.18);"
        elif rank == 2:
            style = "font-weight:700; background-color: rgba(255, 193, 7, 0.12);"
        elif rank == 3:
            style = "font-weight:700; background-color: rgba(255, 152, 0, 0.10);"
        else:
            style = ""
        return [style] * len(row)

    styled = df.style.apply(ranking_row_style, axis=1)

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=min(600, 44 + max(1, len(table_rows)) * 42),
        column_config={
            "Sıra": st.column_config.NumberColumn("Sıra", width="small", format="%d"),
            "No": st.column_config.TextColumn("No", width="small"),
            "At": st.column_config.TextColumn("At", width="medium"),
            "Yaş": st.column_config.TextColumn("Yaş", width="medium"),
            "Kilo": st.column_config.TextColumn("Kilo", width="small"),
            "Jokey": st.column_config.TextColumn("Jokey", width="medium"),
            "HP": st.column_config.TextColumn("HP", width="small"),
            "AGF": st.column_config.TextColumn("AGF", width="small"),
            "St": st.column_config.TextColumn("St", width="small"),
            "KGS": st.column_config.TextColumn("KGS", width="small"),
            "Form": st.column_config.TextColumn("Form", width="medium"),
            "Puan": st.column_config.NumberColumn("Puan", width="small", format="%.2f"),
        },
    )

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
