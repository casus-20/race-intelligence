import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
import pandas as pd
import re
from datetime import date, datetime
from typing import Any, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from worker.tjk_fetch import get_program, get_horse_enrichment


# ============================================================
# SAYFA AYARLARI
# ============================================================

# UI_V4_REAL_DATA_STATUS_AND_REFRESH — eski yeşil/mavi tablo stili kaldırıldı
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
if "selected_horse_index" not in st.session_state:
    st.session_state.selected_horse_index = None
    st.session_state["_selected_detail_fetch_key"] = None
if "_selected_detail_fetch_key" not in st.session_state:
    st.session_state["_selected_detail_fetch_key"] = None


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>

    .main-title {
        font-size:27px;
        font-weight: 950;
        margin-top: 6px !important;
        margin-bottom: 8px;
        line-height: 1.15;
        padding-top: 0 !important;
        overflow: visible !important;
        position: relative;
        z-index: 5;
        text-align: center !important;
        width: 100% !important;
    }

    /* Sayfanın üst kenarı ile RACE INTELLIGENCE arasında yalnızca 15 mm boşluk. */
    section.main > div.block-container,
    div[data-testid="stMainBlockContainer"] {
        max-width: none !important;
        width: 100% !important;
        padding-top: 2.5mm !important;
        padding-left: 3.5mm !important;
        padding-right: 3.5mm !important;
    }

    /* EKRAN ÖLÇEĞİ: Chrome %100 iken uygulama yaklaşık %67 yoğunlukta
       görünür; ancak Streamlit'in tablo/iframe genişliği küçülmez.
       Önceki #root zoom yaklaşımı dataframe alanını ~%67 genişliğe düşürüyordu.
       Bu nedenle artık root'a zoom uygulanmıyor; içerik ölçüleri doğrudan
       kompaktlaştırılıyor ve ana alan tam genişlikte bırakılıyor. */
    html, body, #root {
        width: 100% !important;
        max-width: none !important;
        overflow-x: hidden !important;
    }

    /* Sidebar, %67 tarayıcı görünümüne yakın kompakt ölçüde. */
    section[data-testid="stSidebar"] {
        width: 150px !important;
        min-width: 150px !important;
        max-width: 150px !important;
    }
    section[data-testid="stSidebar"] > div {
        width: 150px !important;
    }

    /* Ana içerik tam kalan genişliği kullansın. */
    [data-testid="stAppViewContainer"] > .main {
        width: calc(100% - 150px) !important;
        max-width: none !important;
    }
    section.main > div.block-container,
    div[data-testid="stMainBlockContainer"] {
        max-width: none !important;
        width: 100% !important;
    }

    .ri-header {
        display: flex !important;
    }

    .sub-title {
        font-size:10px;
        opacity: 0.75;
        margin-bottom: 20px;
    }

    .horse-title {
        font-size:12px;
        font-weight: 700;
        margin-top: 15px;
        margin-bottom: 10px;
    }

    .ri-header {
        border: 0 !important;
        border-radius: 0 !important;
        padding: 0 !important;
        margin: 0 0 8px 0 !important;
        display: flex !important;
        align-items: center;
        justify-content: space-between;
        overflow: visible !important;
        min-height: 0 !important;
    }

    .ri-title {
        font-size: 26px;
        font-weight: 800;
        letter-spacing: .3px;
    }

    .ri-subtitle {
        font-size:10px;
        opacity: .72;
        margin-top: 3px;
    }

    .ri-clock {
        font-size:9px;
        font-weight: 800;
        opacity: .7;
        letter-spacing: 1px;
    }

    .condition-box {
        border: 1px solid rgba(80,130,190,.30);
        border-radius: 7px;
        padding: 10px 12px;
        margin: 6px 0 12px 0;
        font-size:10px;
        line-height: 1.55;
    }

    .model-note {
        font-size:9px;
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
        font-size:9px;
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
    /* Ana içerik alanını mümkün olduğunca geniş kullan. */
    section.main > div.block-container,
    div[data-testid="stMainBlockContainer"] {
        max-width: none !important;
        width: 100% !important;
        padding-top: 2.5mm !important;
        padding-left: 3.5mm !important;
        padding-right: 3.5mm !important;
    }

    .race-info-compact {
        margin-top: 1px !important;
        margin-bottom: 2px !important;
        padding: 0 !important;
        width: 100% !important;
    }

    .race-title-panel {
        width: 100% !important;
        min-height: 36px;
        border: 1px solid #b9c8d8;
        border-radius: 7px;
        background: #ffffff;
        color: #16324d;
        padding: 7px 12px;
        box-sizing: border-box;
        display: flex;
        align-items: center;
        gap: 16px;
        flex-wrap: nowrap;
        box-shadow: none;
        text-transform: uppercase;
    }
    .race-title-panel .race-title-main {
        font-size: 30px;
        line-height: 1.0;
        font-weight: 950;
        white-space: nowrap;
    }
    .race-title-panel .race-condition {
        font-size: 16px;
        line-height: 1.15;
        font-weight: 900;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        flex: 1 1 auto;
        min-width: 0;
    }
    .race-title-panel .analysis-inline {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 31px;
        padding: 4px 11px;
        border-radius: 5px;
        font-size:10px;
        font-weight: 950;
        background: #e8f1f8;
        color: #07579f;
        white-space: nowrap;
        margin-left: auto;
        text-transform: uppercase;
    }

    /* Seçili koşu / analiz bekleniyor paneli ana tablo ile aynı genişlikte. */
    .race-info-compact + .horse-title {
        margin-top: 0 !important;
    }

    /* Gerçek veri tabloları: yatay scrollbar yok, başlık tek sıra ve 15 mm. */
    .ri-real-table-wrap {
        width: 100%;
        overflow: hidden !important;
        border: 1px solid rgba(80,100,130,.35);
        border-radius: 7px;
    }
    table.ri-real-table {
        width: 100% !important;
        table-layout: fixed;
        border-collapse: collapse;
        font-size: 11px;
    }
    table.ri-real-table thead th {
        height: 15mm;
        min-height: 15mm;
        padding: 6px 5px;
        background: #0868c9;
        color: #ffffff;
        font-weight: 950;
        text-align: center;
        vertical-align: middle;
        border: 1px solid rgba(255,255,255,.25);
        white-space: nowrap;
    }
    table.ri-real-table tbody td {
        padding: 6px 5px;
        border: 1px solid rgba(100,120,140,.18);
        text-align: center;
        vertical-align: middle;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        font-weight: 800;
    }
    table.ri-real-table tbody tr:nth-child(odd) td {
        background: #ffffff;
        color: #17212b;
    }
    table.ri-real-table tbody tr:nth-child(even) td {
        background: #f1f3f5;
        color: #17212b;
    }
    .tjk-detail-table-wrap {
        width:100%; overflow-x:auto; border:0; border-radius:0; background:#0b1320;
        margin:0 !important; padding:0 !important;
    }
    table.tjk-detail-table {
        width:100%; min-width:1450px; border-collapse:collapse; table-layout:auto;
        font-size:14px; background:#0b1320; color:#f4f7fb;
    }
    table.tjk-detail-table thead th {
        height:44px; padding:0 10px; background:#aeb5c2; color:#0a1423;
        border-right:1px solid #8f98a8; border-bottom:1px solid #687486;
        font-weight:900; text-align:center; white-space:nowrap;
    }
    table.tjk-detail-table tbody td {
        height:42px; padding:5px 10px; background:#0d1727; color:#f5f7fa;
        border-right:1px solid #263346; border-bottom:1px solid #2a3749;
        text-align:center; vertical-align:middle; white-space:nowrap; font-weight:600;
    }
    table.tjk-detail-table tbody tr:nth-child(even) td { background:#202b3b; }
    table.tjk-detail-table tbody tr:hover td { background:#26364a; }
    table.tjk-detail-table td:nth-child(1), table.tjk-detail-table td:nth-child(2) { color:#eef3fb; }
    table.tjk-detail-table td:nth-child(8), table.tjk-detail-table td:nth-child(9) { color:#f2f6ff; }
    table.tjk-detail-table td:nth-child(14) { text-align:left; line-height:1.05; }
    table.tjk-detail-table .row-action {
        width:28px; min-width:28px; padding:0 !important; color:#8994a5 !important;
        font-size:13px; font-weight:900;
    }
    table.workout-detail { min-width:1100px; }
    table.workout-detail tbody td:nth-child(3) { color:#9fc8ff; }
    table.workout-detail tbody td:nth-child(4),
    table.workout-detail tbody td:nth-child(5),
    table.workout-detail tbody td:nth-child(6),
    table.workout-detail tbody td:nth-child(7),
    table.workout-detail tbody td:nth-child(8) { font-variant-numeric:tabular-nums; }

    .real-section-title {
        margin-top: 5px !important;
        margin-bottom: 4px !important;
        font-size: 17px;
        font-weight: 950;
    }

    .horse-title {
        margin-top: 10 !important;
        margin-bottom: 1px !important;
        line-height: 1.0 !important;
    }

    .analysis-badge {
        display:inline-block;
        padding:7px 12px;
        border-radius:5px;
        font-size:17px;
        font-weight:950;
        margin:1px 0 4px 0;
        border:1px solid rgba(20,80,130,.35);
        text-transform:uppercase;
    }
    .analysis-waiting { background:#eaf3fb; color:#075b9f; }
    .analysis-active { background:#e7f6ec; color:#147a35; }


    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# BAŞLIK — TJK YENİ YAPI
# ============================================================

st.markdown(
    """
    <div class="ri-header">
        <div>
            <div class="ri-title">🏇 RACE INTELLIGENCE</div>
            <div class="ri-subtitle">
                Gerçek TJK geçmişi + galop + analiz motoru
            </div>
        </div>
        <div class="ri-clock">TJK YENİ YAPI</div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# CANLI MODEL AYARLARI — SAYFANIN ÜSTÜ
# ============================================================

def _reset_model_weights():
    for criterion, value in DEFAULT_WEIGHTS.items():
        st.session_state[WEIGHT_KEYS[criterion]] = value
    st.session_state["analysis_mode"] = "Gerçek veri"
    st.session_state["real_analysis_requested"] = True
    st.session_state["real_analysis_done"] = False


def _request_real_analysis():
    st.session_state["analysis_mode"] = "Gerçek veri"
    st.session_state["real_analysis_requested"] = True
    st.session_state["real_analysis_done"] = False


def _request_manual_analysis():
    st.session_state["analysis_mode"] = "Manuel"
    st.session_state["real_analysis_requested"] = False
    st.session_state["real_analysis_done"] = True


if st.session_state.pop("_reset_model_next_run", False):
    for criterion, value in DEFAULT_WEIGHTS.items():
        st.session_state[WEIGHT_KEYS[criterion]] = value

# CANLI MODEL SAYFANIN EN ÜSTÜNDE
current_mode = st.session_state.get("analysis_mode", "Gerçek veri")
with st.expander("⚙️ CANLI MODEL AYARLARI", expanded=False):
    st.caption(
        "Ağırlıkları değiştirdiğinde yeni TJK isteği yapılmaz; mevcut gerçek verilerle skor yeniden hesaplanır."
    )
    weight_items = list(DEFAULT_WEIGHTS.items())
    cols = st.columns(4)
    for idx, (criterion, default_value) in enumerate(weight_items):
        key = WEIGHT_KEYS[criterion]
        with cols[idx % 4]:
            st.slider(criterion, min_value=0, max_value=40, key=key, step=1)

    ANALYSIS_WEIGHTS = current_weights()
    weight_total = sum(ANALYSIS_WEIGHTS.values())
    normalized = {
        k: (v * 100.0 / weight_total if weight_total else 0.0)
        for k, v in ANALYSIS_WEIGHTS.items()
    }
    st.markdown(
        f"<div class='ri-model-summary'><b>Ham toplam:</b> {weight_total} &nbsp;•&nbsp; <b>Normalize:</b> 100</div>",
        unsafe_allow_html=True,
    )
    st.caption(" • ".join(f"{k} %{normalized[k]:.1f}" for k in ANALYSIS_WEIGHTS))
    st.caption(f"Aktif analiz modu: **{current_mode}**")

# Fonksiyonlar CANLI MODEL AYARLARININ DIŞINDA
btn1, btn2, btn3, mode_col = st.columns([1.15, 1.15, 1.15, 0.65])
with btn1:
    st.markdown("<span class='ri-reset-marker'></span>", unsafe_allow_html=True)
    st.button(
        "↩️ VARSAYILANA DÖN",
        key="reset_model_button_top",
        use_container_width=True,
        on_click=_reset_model_weights,
    )
with btn2:
    st.markdown("<span class='ri-real-marker'></span>", unsafe_allow_html=True)
    st.button(
        "🔎 GERÇEK VERİ İLE ANALİZ ET",
        key="real_analysis_button_top",
        use_container_width=True,
        on_click=_request_real_analysis,
        type="primary",
    )
with btn3:
    st.markdown("<span class='ri-manual-marker'></span>", unsafe_allow_html=True)
    st.button(
        "🧠 MANUEL ANALİZ",
        key="manual_analysis_button_top",
        use_container_width=True,
        on_click=_request_manual_analysis,
        type="secondary",
    )
with mode_col:
    current_mode = st.session_state.get("analysis_mode", "Gerçek veri")
    badge = "Gerçek veri" if current_mode == "Gerçek veri" else "Manuel"
    st.markdown(
        f"<div class='ri-mode-badge'>Mod: <b>{badge}</b></div>",
        unsafe_allow_html=True,
    )


# ============================================================
# TJK VERİ DURUMU
# ============================================================

def fetch_program_with_status(selected_date, selected_city, label):
    """Programı alır; eski status/expander panelini ekrana basmaz."""
    try:
        return load_program(selected_date, selected_city)
    except Exception as exc:
        raise RuntimeError(f"{label}: {exc}") from exc

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
    """At adını TJK/YB hücrelerinden temizleyerek döndürür."""
    raw = display_value(
        horse.get("at_ismi")
        or horse.get("At İsmi")
        or horse.get("name")
        or horse.get("horseName")
    )
    if not raw or raw == "-":
        return raw

    raw = re.sub(r"\s*Image.*$", "", raw, flags=re.I).strip()

    # Program numarası adın içine gömülmüşse çıkar:
    # FRANKI CHA CHA (2) -> FRANKI CHA CHA
    raw = re.sub(r"\s*\(\d{1,2}\)\s*", " ", raw).strip()

    # Orijin alanındaki baba adı ad hücresine de taşınmışsa ayır.
    origin = display_value(
        horse.get("origin")
        or horse.get("orijin")
        or horse.get("Orijin")
        or horse.get("pedigree")
        or horse.get("baba_anne"),
        "",
    )
    if origin:
        sire = re.split(r"\s+-\s+", origin, maxsplit=1)[0].strip()
        if sire:
            raw = re.sub(
                r"\s+" + re.escape(sire) + r"\s*$",
                "",
                raw,
                flags=re.I,
            ).strip()

    # Orijin alanı boş kaldığında "... AUTHORIZED (IRE)" gibi
    # baba bilgisinin ad hücresine gömüldüğü kayıtları ayır.
    raw = re.sub(
        r"\s+[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9 .'/&-]{2,}\s+\([A-Z]{2,3}\)\s*$",
        "",
        raw,
    ).strip()

    return raw


def _split_origin(origin: Any) -> tuple[str, str]:
    """TJK Orijin alanını görseldeki Baba / Anne formatına ayırır.

    Örn: AUTHORIZED (IRE) - ROYAL CHICK / KANEKO
      -> AUTHORIZED (IRE)
      -> ROYAL CHICK / KANEKO
    """
    text = display_value(origin, "")
    if not text:
        return "", ""
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"\s+-\s+", text, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return text, ""


def get_horse_origin(
    horse: Dict[str, Any],
) -> str:
    """Baba / anne orijinini TJK alanından, gerekirse ad hücresinden al."""
    origin = display_value(
        horse.get("origin")
        or horse.get("orijin")
        or horse.get("Orijin")
        or horse.get("pedigree")
        or horse.get("baba_anne"),
        "",
    )
    if origin:
        return origin

    # Bazı günlük program cevaplarında Orijin kolonu boş, ancak At İsmi hücresinde
    # "AT ADI (No) BABA - ANNE / ANNE BABASI" biçimi geliyor.
    raw = display_value(
        horse.get("at_ismi")
        or horse.get("At İsmi")
        or horse.get("name")
        or horse.get("horseName"),
        "",
    )
    m = re.match(r"^.+?\s*\(\d{1,2}\)\s+(.+)$", raw)
    return m.group(1).strip() if m else ""


def _extract_equipment_from_text(text: Any) -> str:
    """TJK takı kodlarını, isim hücresine gömülmüşse de yakalar."""
    value = display_value(text, "")
    if not value:
        return ""
    # Takı kodları TJK'da boşlukla ayrılabilir: DB SK, KG SK, KG K GKR vb.
    m = re.search(
        r"(?:^|\s)((?:DB|KG|K|SKG|SK|GKR|G|D|B|H|TT|M|SGK)(?:\s+(?:DB|KG|K|SKG|SK|GKR|G|D|B|H|TT|M|SGK)){0,5})$",
        value,
        flags=re.I,
    )
    return m.group(1).upper().strip() if m else ""


def get_horse_equipment(horse: Dict[str, Any]) -> str:
    """Bugünkü programdaki gerçek Takı bilgisini alır."""
    direct = (
        horse.get("equipment")
        or horse.get("taki")
        or horse.get("Takı")
        or horse.get("takı")
    )
    if direct:
        return display_value(direct, "")
    # Bazı TJK sürümlerinde takı, At İsmi hücresinin içinde gelir.
    return _extract_equipment_from_text(
        horse.get("name") or horse.get("at_ismi") or horse.get("At İsmi")
    )


def get_horse_number(
    horse: Dict[str, Any],
    fallback: int,
) -> int:
    """TJK'nın gerçek at numarasını sayısal olarak döndürür.

    No sütununun Streamlit tarafından METİN olarak değil SAYI olarak
    sıralanabilmesi için burada daima int döndürülür. Böylece örneğin
    1, 2, 3 ... 14 sıralaması lexicographic (1, 10, 11...) olmaz.
    """
    value = (
        horse.get("numara")
        or horse.get("no")
        or horse.get("number")
        or horse.get("N")
        or horse.get("No")
        or horse.get("horseNo")
        or horse.get("horse_number")
    )

    if value is not None:
        # "9", "9.0", "9 -" gibi TJK/Worker varyasyonlarını güvenli biçimde çöz.
        m = re.search(r"\d+", str(value))
        if m:
            try:
                return int(m.group(0))
            except Exception:
                pass

    return int(fallback)


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

def _weight_parts(value: Any) -> tuple[str, str]:
    text = display_value(value, "")
    if not text:
        return "-", ""

    # TJK programlarında örn. "53 +1.20 Fazla Kilo" / "53,5" gibi
    # biçimler görülebilir. Ana kilo ilk satırda, fazla kilo ikinci satırda
    # gösterilir; veri kaybedilmez.
    m = re.match(
        r"^\s*(\d+(?:[.,]\d+)?)\s*(.*)$",
        text,
        flags=re.I,
    )
    if not m:
        return text, ""

    base = m.group(1).replace(",", ".")
    rest = (m.group(2) or "").strip()
    if not rest:
        return base, ""

    # Fazla kilo bilgisini aynı hücrede ikinci satıra taşır.
    fm = re.search(r"([+\-]\s*\d+(?:[.,]\d+)?)", rest)
    if fm:
        return base, fm.group(1).replace(',', '.').replace(" ", "")
    return base, rest


def get_horse_weight(
    horse: Dict[str, Any],
) -> str:
    base, extra = _weight_parts(
        horse.get("siklet")
        or horse.get("Sıklet")
        or horse.get("weight")
    )
    return f"{base}\n{extra}" if extra else base


def get_horse_jockey(
    horse: Dict[str, Any],
) -> str:
    text = display_value(
        horse.get("jokey")
        or horse.get("Jokey")
        or horse.get("jockey")
    , "")
    if not text:
        return "-"

    # TJK'da AP bazı sayfalarda yalnız "AP", bazılarında "AP Apranti"
    # olarak gelir. İkisini de görselde ikinci satıra taşırız.
    m = re.match(r"^(.*?)(?:\s+)(AP(?:\s+Apranti)?|Apranti)$", text, flags=re.I)
    if m:
        label = "Ap"
        return f"{m.group(1).strip()}\n{label}"
    return text


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
def load_horse_enrichment(
    at_id: str,
    horse_name: str,
    target_date: str = "",
    target_city: str = "",
    target_distance: str = "",
    target_surface: str = "",
    target_class: str = "",
) -> Dict[str, Any]:
    try:
        return get_horse_enrichment(
            at_id,
            horse_name,
            target_date=target_date,
            target_city=target_city,
            target_distance=target_distance,
            target_surface=target_surface,
            target_class=target_class,
        )
    except Exception as exc:
        return {
            "ok": False,
            "history": [],
            "workouts": [],
            "error": str(exc),
        }


def enrich_race_horses(
    horses: List[Dict[str, Any]],
    target_date: Any = None,
    target_city: str = "",
    target_distance: Any = None,
    target_surface: str = "",
    target_class: str = "",
) -> List[Dict[str, Any]]:
    enriched = [dict(h) for h in horses if isinstance(h, dict)]

    def one(item):
        # TJK programında kimlik alanı farklı isimlerle gelebilir.
        # At numarasını (no) ID olarak kullanmıyoruz; yalnızca gerçek at
        # kimliği alanlarını kabul ediyoruz.
        at_id = (
            item.get("atId")
            or item.get("at_id")
            or item.get("horseId")
            or item.get("horse_id")
            or item.get("horseKey")
            or item.get("horse_key")
            or item.get("id")
            or item.get("Id")
            or ""
        )
        name = get_horse_name(item)
        if not at_id:
            item["_history"] = []
            item["_workouts"] = []
            item["_enrichment_error"] = "TJK program kaydında atId bulunamadı."
            return item
        data = load_horse_enrichment(
            str(at_id),
            name,
            str(target_date or ""),
            str(target_city or ""),
            str(target_distance or ""),
            str(target_surface or ""),
            str(target_class or ""),
        )
        history = data.get("history", []) if isinstance(data, dict) else []
        workouts = data.get("workouts", []) if isinstance(data, dict) else []

        item["_at_id"] = str(at_id)
        item["_history"] = history if isinstance(history, list) else []
        item["_workouts"] = workouts if isinstance(workouts, list) else []
        if isinstance(data, dict) and data.get("error"):
            item["_enrichment_error"] = str(data.get("error"))

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
            if not isinstance(row, dict):
                continue
            has_date = row.get("date") or row.get("tarih")
            has_time = row.get("time") or row.get("derece")
            if has_date and has_time:
                item["_last_race"] = row
                break

        # Bu yılki kazanç: gerçek geçmişteki prize alanlarının toplamı.
        # Tarihi hedef yarış yılına göre hesaplamak için selected_date daha sonra eklenir.
        return item

    with ThreadPoolExecutor(max_workers=min(3, max(1, len(enriched)))) as executor:
        futures = [executor.submit(one, h) for h in enriched]
        return [f.result() for f in futures]


def _history_year(date_text: Any) -> int | None:
    m = re.search(r"(20\d{2})", str(date_text or ""))
    return int(m.group(1)) if m else None


def _money_number(value: Any) -> float:
    """TJK para alanını Türkçe binlik/ondalık gösterimiyle doğru parse eder.

    Örnek:
      292.000   -> 292000
      3.655.200 -> 3655200
      2.500,50  -> 2500.50
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    text = str(value).strip()
    if not text or text == "-":
        return 0.0

    text = text.replace("₺", "").replace("TL", "").replace("tl", "")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^0-9,.-]", "", text)
    if not text:
        return 0.0

    if "," in text:
        if "." in text:
            text = text.replace(".", "").replace(",", ".")
        else:
            tail = text.rsplit(",", 1)[-1]
            if len(tail) in (1, 2):
                text = text.replace(",", ".")
            else:
                text = text.replace(",", "")
    elif "." in text:
        parts = text.split(".")
        # TJK'da 292.000 / 3.655.200 biçimi binlik ayırıcıdır.
        if all(part.isdigit() for part in parts) and len(parts[-1]) == 3:
            text = "".join(parts)
        elif len(parts) > 2:
            text = "".join(parts)

    try:
        return float(text)
    except ValueError:
        return 0.0


def _format_tl(value: float) -> str:
    """Tabloda TJK görünümü: 3.655.200 ₺."""
    try:
        n = int(round(float(value)))
    except Exception:
        n = 0
    return f"{n:,}".replace(",", ".") + " ₺"


def _race_prize_total(horse: Dict[str, Any], target_year: int | None = None) -> float:
    """TJK geçmişindeki İkramiye toplamını hesaplar.

    TJK At Bilgileri ekranındaki "Kazanç" değeri yalnızca koşu
    ikramiyelerinin toplamı değildir; At Sahibi Primi de eklenir.
    Verilen FRANKI CHA CHA örneğinde 3.046.000 TL ikramiye + %20
    At Sahibi Primi = 3.655.200 TL olduğundan uygulamada resmi
    "Kazanç" karşılığı olarak ikramiye toplamı x 1,20 kullanılır.
    """
    total = 0.0
    for row in horse.get("_history", []):
        if not isinstance(row, dict):
            continue
        if target_year is not None and _history_year(
            row.get("date") or row.get("tarih")
        ) != target_year:
            continue
        total += _money_number(
            row.get("prize")
            or row.get("ikramiye")
            or row.get("Ikramiye")
        )
    return total


def total_earnings(horse: Dict[str, Any]) -> float:
    """TJK "Kazanç": ikramiye + At Sahibi Primi (%20)."""
    return round(_race_prize_total(horse) * 1.20, 2)


def year_earnings(horse: Dict[str, Any], target_year: int) -> float:
    """TJK yıllık "Kazanç": o yılın ikramiyesi + %20 At Sahibi Primi."""
    return round(_race_prize_total(horse, target_year) * 1.20, 2)


def latest_workout(horse: Dict[str, Any]) -> Dict[str, Any] | None:
    workouts = horse.get("_workouts", [])
    if not isinstance(workouts, list):
        return None
    for w in workouts:
        if not isinstance(w, dict):
            continue
        if any(
            str(w.get(k) or "").strip()
            for k in (
                "m400", "m600", "m800", "m1000", "m1200",
                "400", "600", "800", "1000", "1200",
                "time", "derece",
            )
        ):
            return w
    return None


def workout_display(horse: Dict[str, Any]) -> str:
    w = latest_workout(horse)
    if not w:
        return "-"
    for keys, label in (
        (("m1200", "1200"), "1200"),
        (("m1000", "1000"), "1000"),
        (("m800", "800"), "800"),
        (("m600", "600"), "600"),
        (("m400", "400"), "400"),
        (("time", "derece"), ""),
    ):
        value = _first_value(w, list(keys))
        value = display_value(value, "")
        if value:
            if label:
                return f"{value} ({label}m)"
            distance = display_value(_first_value(w, ["distance", "msf", "mesafe"]), "")
            return f"{value} ({distance}m)" if distance else value
    return "-"


def last_race_display(horse: Dict[str, Any]) -> str:
    """Ana tabloda SON KOŞU sütununda yalnızca gerçek dereceyi gösterir."""
    row = horse.get("_last_race")
    if not isinstance(row, dict):
        return "-"
    return display_value(
        _first_value(row, ["time", "derece", "Derece"]),
        "-",
    )


def best_race_detail(horse: Dict[str, Any]) -> Dict[str, str]:
    """TJK günlük programındaki En İyi D. tooltip bilgilerinin görünür karşılığı."""
    best = display_value(horse.get("bestTime"), "")
    if not best:
        return {}
    return {
        "Derece": best,
        "Hipodrom": display_value(horse.get("bestCity"), "-"),
        "Tarih": display_value(horse.get("bestDate"), "-"),
        "Mesafe": display_value(horse.get("bestDistance"), "-"),
        "Bilgi": display_value(horse.get("bestInfo"), "-"),
    }


def last_race_detail(horse: Dict[str, Any]) -> Dict[str, str]:
    row = horse.get("_last_race")
    if not isinstance(row, dict):
        return {}
    return {
        "Tarih": display_value(_first_value(row, ["date", "tarih", "Tarih"])),
        "Şehir": display_value(_first_value(row, ["city", "şehir", "Sehir"])),
        "Mesafe": display_value(_first_value(row, ["distance", "msf", "mesafe"])),
        "Pist": display_value(_first_value(row, ["surface", "pist"])),
        "Sıra": display_value(_first_value(row, ["place", "sira", "S"])),
        "Derece": display_value(_first_value(row, ["time", "derece", "Derece"])),
        "Sıklet": display_value(_first_value(row, ["weight", "kilo", "siklet"])),
        "Jokey": display_value(_first_value(row, ["jockey", "jokey"])),
        "HP": display_value(_first_value(row, ["hp", "HP"])),
        "Koşu": display_value(_first_value(row, ["raceName", "race_name", "kosu"])),
        "Sınıf": display_value(_first_value(row, ["className", "class", "sinif"])),
        "İkramiye": display_value(_first_value(row, ["prize", "ikramiye", "Ikramiye"])),
    }


def _first_value(row: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def _html_real_table(df: pd.DataFrame, widths=None) -> None:
    """Gerçek TJK verisini tek başlık satırında, yatay kaydırmasız gösterir."""
    if df.empty:
        return
    safe = df.copy().replace({None: "-", "": "-"}).fillna("-")
    html = safe.to_html(
        index=False,
        escape=True,
        classes="ri-real-table",
        border=0,
    )
    if widths:
        # Kolon sayısı fazla olduğunda table-layout fixed ile taşmayı engeller.
        pass
    st.markdown(
        f"<div class='ri-real-table-wrap'>{html}</div>",
        unsafe_allow_html=True,
    )


def _safe_video_url(row: Dict[str, Any]) -> str:
    """TJK'nin gerçek yarış video URL'sini döndürür; URL yoksa boş bırakır."""
    value = _first_value(row, [
        "videoUrl", "video_url", "video", "videoLink", "video_link",
        "urlVideo", "videoURL", "raceVideoUrl", "race_video_url",
    ])
    text = display_value(value, "")
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return ""


def _history_tables(history: List[Dict[str, Any]]) -> None:
    """TJK gerçek koşu geçmişi: sıralanabilir başlıklar + gerçek video bağlantısı."""
    if not history:
        st.warning("Bu at için TJK gerçek koşu geçmişi gelmedi.")
        return

    rows = []
    for row in history:
        if not isinstance(row, dict):
            continue
        owner = display_value(_first_value(row, ["owner", "sahip"]), "-")
        trainer = display_value(_first_value(row, ["trainer", "antrenor", "antrenör"]), "-")
        owner_trainer = f"{owner}\n{trainer}" if trainer != "-" else owner
        prize_raw = _first_value(row, ["prize", "ikramiye", "Ikramiye", "İkramiye"])
        prize = _format_tl(_money_number(prize_raw)) if prize_raw not in ("", None) else "₺0"
        rows.append({
            "Tarih": display_value(_first_value(row, ["date", "tarih", "Tarih"])),
            "Şehir": display_value(_first_value(row, ["city", "şehir", "Sehir"])),
            "Msf": display_value(_first_value(row, ["distance", "msf", "mesafe", "Msf"])),
            "Pist": display_value(_first_value(row, ["surface", "pist", "Pist"])),
            "Sonuç": display_value(_first_value(row, ["place", "sira", "Sıra", "S"])),
            "K Cinsi": display_value(_first_value(row, ["className", "class", "kcins", "K Cinsi", "raceType"])),
            "Grup": display_value(_first_value(row, ["group", "grup", "Grup"])),
            "Derece": display_value(_first_value(row, ["time", "derece", "Derece"])),
            "Jokey": display_value(_first_value(row, ["jockey", "jokey", "Jokey"])),
            "Kilo": display_value(_first_value(row, ["weight", "kilo", "siklet", "Sıklet"])),
            "Takı": display_value(_first_value(row, ["equipment", "taki", "takı", "Takı"])),
            "St": display_value(_first_value(row, ["post", "st", "start", "St"])),
            "HP": display_value(_first_value(row, ["hp", "HP"])),
            "Sahip / Antr.": owner_trainer,
            "AGF": display_value(_first_value(row, ["agf", "AGF"])),
            "Gny": display_value(_first_value(row, ["odds", "gny", "Gny"])),
            "İkramiye": prize,
            "Video": _safe_video_url(row),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        st.warning("TJK geçmişinde gösterilecek kayıt bulunamadı.")
        return

    # Native Streamlit DataFrame kullanılır: sütun başlıklarına tıklayınca
    # artan/azalan sıralama çalışır. Video sütunu gerçek URL'yi yeni sekmede açar.
    column_config = {
        "Tarih": st.column_config.TextColumn("Tarih", width=90),
        "Şehir": st.column_config.TextColumn("Şehir", width=95),
        "Msf": st.column_config.TextColumn("Msf", width=65),
        "Pist": st.column_config.TextColumn("Pist", width=90),
        "Sonuç": st.column_config.TextColumn("Sonuç", width=65),
        "K Cinsi": st.column_config.TextColumn("K Cinsi", width=110),
        "Grup": st.column_config.TextColumn("Grup", width=65),
        "Derece": st.column_config.TextColumn("Derece", width=80),
        "Jokey": st.column_config.TextColumn("Jokey", width=105),
        "Kilo": st.column_config.TextColumn("Kilo", width=65),
        "Takı": st.column_config.TextColumn("Takı", width=70),
        "St": st.column_config.TextColumn("St", width=45),
        "HP": st.column_config.TextColumn("HP", width=50),
        "Sahip / Antr.": st.column_config.TextColumn("Sahip / Antr.", width=155),
        "AGF": st.column_config.TextColumn("AGF", width=65),
        "Gny": st.column_config.TextColumn("Gny", width=65),
        "İkramiye": st.column_config.TextColumn("İkramiye", width=100),
        "Video": st.column_config.LinkColumn("Video", width=55, display_text="▶"),
    }
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
        height=min(760, 54 + len(df) * 43),
        row_height=42,
        key="history_detail_table",
    )


def _workout_tables(workouts: List[Dict[str, Any]]) -> None:
    """TJK gerçek galopları: sıralanabilir başlıklar + varsa gerçek video bağlantısı."""
    if not workouts:
        st.warning("Bu at için TJK gerçek galop kaydı gelmedi.")
        return

    rows = []
    for row in workouts:
        if not isinstance(row, dict):
            continue
        rows.append({
            "Tarih": display_value(_first_value(row, ["date", "tarih", "Tarih"])),
            "Şehir": display_value(_first_value(row, ["city", "track", "hipodrom", "şehir", "Sehir"])),
            "İ.Jokey": display_value(_first_value(row, ["jockey", "jokey", "rider", "binici"])),
            "1200": display_value(_first_value(row, ["m1200", "1200", "time1200"])),
            "1000": display_value(_first_value(row, ["m1000", "1000", "time1000"])),
            "800": display_value(_first_value(row, ["m800", "800", "time800"])),
            "600": display_value(_first_value(row, ["m600", "600", "time600"])),
            "400": display_value(_first_value(row, ["m400", "400", "time400"])),
            "Çalışma": display_value(_first_value(row, ["type", "tur", "Tür", "note", "not"])),
            "Pist": display_value(_first_value(row, ["surface", "pist"])),
            "Video": _safe_video_url(row),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        st.warning("TJK galop verisinde gösterilecek kayıt bulunamadı.")
        return

    column_config = {
        "Tarih": st.column_config.TextColumn("Tarih", width=90),
        "Şehir": st.column_config.TextColumn("Şehir", width=95),
        "İ.Jokey": st.column_config.TextColumn("İ.Jokey", width=100),
        "1200": st.column_config.TextColumn("1200", width=65),
        "1000": st.column_config.TextColumn("1000", width=65),
        "800": st.column_config.TextColumn("800", width=65),
        "600": st.column_config.TextColumn("600", width=65),
        "400": st.column_config.TextColumn("400", width=65),
        "Çalışma": st.column_config.TextColumn("Çalışma", width=90),
        "Pist": st.column_config.TextColumn("Pist", width=90),
        "Video": st.column_config.LinkColumn("Video", width=55, display_text="▶"),
    }
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
        height=min(760, 54 + len(df) * 43),
        row_height=42,
        key="workout_detail_table",
    )

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



def _class_level_from_text(value: Any) -> float | None:
    """TJK geçmişindeki koşu sınıfını tek bir sınıf seviyesine dönüştürür.

    Bu değer BİZİM SKOR veya ŞART UYUMU değildir.
    Amaç yalnızca atın son gerçek koşularında hangi sınıf seviyelerinde
    koştuğunu ölçmek ve bunu GÜNCEL SINIF olarak göstermek.

    Öncelik: açık sınıf > KV > Şartlı > Handikap.
    Handikaplarda H numarası doğrudan kullanılır.
    Şartlı koşularda Şartlı 1-5 sırası kullanılır.
    """
    text = str(value or "").upper().strip()
    if not text or text == "-":
        return None

    # Açık sınıf koşular
    for pat, score in (
        (r"\bG\s*1\b", 100.0),
        (r"\bG\s*2\b", 97.0),
        (r"\bG\s*3\b", 94.0),
        (r"\bAÇIK\b", 90.0),
    ):
        if re.search(pat, text):
            return score

    # Kısa vadeli / KV koşuları. KV numarası yükseldikçe sınıf seviyesi yükselir.
    m = re.search(r"\bKV\s*[- ]?\s*(\d+)\b", text)
    if m:
        n = int(m.group(1))
        return min(89.0, 70.0 + n * 2.0)

    # Şartlı 1-5.
    m = re.search(r"ŞARTLI\s*([1-5])\b|ŞART\s*([1-5])\b", text)
    if m:
        n = int(m.group(1) or m.group(2))
        return 35.0 + n * 7.0

    # Handikap H1-H18. H numarası sınıf seviyesini doğrudan temsil eder.
    m = re.search(r"\bH\s*(\d{1,2})\b", text)
    if m:
        n = int(m.group(1))
        return min(86.0, 30.0 + n * 3.0)

    # Satış / Maiden gibi diğer yarışlar.
    if "SATIŞ" in text or "SATIS" in text:
        m = re.search(r"(?:SATIŞ|SATIS)\s*[- ]?(\d+)", text)
        return 25.0 + (int(m.group(1)) if m else 1) * 3.0
    if "MAIDEN" in text:
        return 25.0

    return None


def _history_class_text(row: Dict[str, Any]) -> str:
    """Geçmiş yarış kaydındaki gerçek TJK sınıf/koşu adını al."""
    return display_value(_first_value(row, [
        "className", "class", "sinif", "Sınıf",
        "raceName", "race_name", "kosu", "Koşu",
    ]), "")


# ============================================================
# TJK-ONLY ŞART UYUMU ENDEKSİ
# ============================================================
# Bu skor yalnızca TJK'dan gelen koşu şartları ve TJK geçmiş
# koşu kayıtları üzerinden hesaplanır.
#
# KULLANILMAZ:
#   AGF / galop / jokey / Son 6 / Bizim Skor
#
# KULLANILIR:
#   Yarış tipi, sınıf, ırk, yaş, pist, mesafe, HP, kilo,
#   geçmiş koşu sonucu.
# ============================================================

def _su_text(value: Any) -> str:
    if value is None:
        return ""
    return (
        str(value).strip().upper()
        .replace("İ", "I")
        .replace("Ğ", "G")
        .replace("Ü", "U")
        .replace("Ş", "S")
        .replace("Ö", "O")
        .replace("Ç", "C")
    )


def _su_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = str(value).strip().replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def _su_class(value: Any) -> int | None:
    if value is None:
        return None
    s = _su_text(value)
    m = re.search(r"(?:H|SARTLI|KV)\s*[-/]?\s*(\d+)", s)
    return int(m.group(1)) if m else None


def _su_family(value: Any) -> str:
    s = _su_text(value).replace(" ", "").replace("-", "").replace("/", "")
    if s.startswith("H"):
        return "HANDIKAP"
    if "SARTLI" in s:
        return "SARTLI"
    if s.startswith("KV"):
        return "KV"
    if "MAIDEN" in s:
        return "MAIDEN"
    if s.startswith("G1"):
        return "G1"
    if s.startswith("G2"):
        return "G2"
    if s.startswith("G3"):
        return "G3"
    return s


def _su_race_type_score(past_type: Any, today_type: Any) -> float:
    p = _su_text(past_type).replace(" ", "").replace("-", "").replace("/", "")
    t = _su_text(today_type).replace(" ", "").replace("-", "").replace("/", "")
    if p == t and p:
        return 100.0

    pf = _su_family(p)
    tf = _su_family(t)

    if pf == tf:
        return 82.0

    if {pf, tf} <= {"HANDIKAP", "SARTLI"}:
        return 58.0

    if {pf, tf} <= {"KV", "G1", "G2", "G3"}:
        return 65.0

    return 30.0


def _su_class_score(past_class: Any, today_class: Any) -> float:
    if past_class is None or today_class is None:
        return 50.0
    d = abs(int(past_class) - int(today_class))
    if d == 0:
        return 100.0
    if d == 1:
        return 92.0
    if d == 2:
        return 82.0
    if d == 3:
        return 70.0
    if d == 4:
        return 58.0
    if d <= 6:
        return 42.0
    return 25.0


def _su_distance_score(past_distance: Any, today_distance: Any) -> float:
    p = _su_number(past_distance)
    t = _su_number(today_distance)
    if p is None or t is None:
        return 50.0
    d = abs(p - t)
    if d == 0:
        return 100.0
    if d <= 100:
        return 95.0
    if d <= 200:
        return 86.0
    if d <= 300:
        return 74.0
    if d <= 400:
        return 60.0
    if d <= 500:
        return 45.0
    if d <= 700:
        return 28.0
    return 10.0


def _su_weight_score(past_weight: Any, today_weight: Any) -> float:
    p = _su_number(past_weight)
    t = _su_number(today_weight)
    if p is None or t is None:
        return 50.0
    d = abs(p - t)
    if d == 0:
        return 100.0
    if d <= 1:
        return 97.0
    if d <= 2:
        return 92.0
    if d <= 3:
        return 85.0
    if d <= 4:
        return 76.0
    if d <= 5:
        return 65.0
    if d <= 6:
        return 52.0
    if d <= 8:
        return 38.0
    return 25.0


def _su_hp_score(past_hp: Any, today_hp: Any) -> float:
    p = _su_number(past_hp)
    t = _su_number(today_hp)
    if p is None or t is None:
        return 50.0
    d = abs(p - t)
    if d == 0:
        return 100.0
    if d <= 2:
        return 97.0
    if d <= 4:
        return 92.0
    if d <= 7:
        return 84.0
    if d <= 10:
        return 74.0
    if d <= 15:
        return 58.0
    if d <= 20:
        return 42.0
    return 25.0


def _su_finish_score(value: Any) -> float:
    p = _su_number(value)
    if p is None:
        return 50.0
    p = int(p)
    if p == 1:
        return 100.0
    if p == 2:
        return 96.0
    if p == 3:
        return 92.0
    if p == 4:
        return 86.0
    if p == 5:
        return 78.0
    if p == 6:
        return 68.0
    if p == 7:
        return 57.0
    if p == 8:
        return 47.0
    if p == 9:
        return 37.0
    return 25.0


def _su_parse_today(race: Dict[str, Any]) -> Dict[str, Any]:
    meta = race.get("meta") if isinstance(race.get("meta"), dict) else {}

    race_type = (
        race.get("condition")
        or meta.get("detail")
        or meta.get("raceName")
        or ""
    )

    distance = _su_number(
        race.get("distance") or meta.get("distance")
    )

    surface = (
        race.get("surface")
        or meta.get("surface")
        or ""
    )

    class_no = (
        race.get("class_no")
        or race.get("class")
        or _su_class(race_type)
    )

    breed = (
        race.get("breed")
        or race.get("irk")
        or meta.get("breed")
        or meta.get("irk")
        or ""
    )

    age_text = _su_text(
        race.get("age")
        or race.get("yas")
        or meta.get("age")
        or ""
    )

    ages = [int(x) for x in re.findall(r"\d+", age_text)]

    return {
        "race_type": race_type,
        "class_no": int(class_no) if class_no is not None else None,
        "breed": breed,
        "surface": surface,
        "distance": distance,
        "age_min": min(ages) if ages else None,
    }


def _su_history_row_match(
    horse: Dict[str, Any],
    row: Dict[str, Any],
    today: Dict[str, Any],
) -> float | None:

    if not isinstance(row, dict):
        return None

    # TJK geçmiş kaydındaki alan adlarını kullan.
    past_type = (
        row.get("raceName")
        or row.get("race_name")
        or row.get("kosu")
        or row.get("condition")
        or row.get("className")
        or row.get("class")
        or ""
    )

    past_class = (
        row.get("className")
        or row.get("class")
        or row.get("sinif")
        or _su_class(past_type)
    )

    past_breed = (
        row.get("breed")
        or row.get("irk")
        or row.get("horseType")
        or row.get("horse_type")
        or ""
    )

    today_breed = _su_text(today["breed"])

    # Geçmiş kaydında ırk açıkça varsa ve farklıysa kullanma.
    if past_breed and today_breed:
        if _su_text(past_breed) != today_breed:
            return None

    past_surface = (
        row.get("surface")
        or row.get("pist")
        or ""
    )

    today_surface = _su_text(today["surface"])

    # Aynı pist şartı zorunlu.
    if past_surface and today_surface:
        if _su_text(past_surface) != today_surface:
            return None

    past_distance = (
        row.get("distance")
        or row.get("msf")
        or row.get("mesafe")
    )

    past_weight = (
        row.get("weight")
        or row.get("kilo")
        or row.get("siklet")
    )

    past_hp = (
        row.get("hp")
        or row.get("HP")
        or row.get("rating")
    )

    place = (
        row.get("place")
        or row.get("sira")
        or row.get("S")
    )

    today_weight = (
        horse.get("weight")
        or horse.get("siklet")
        or horse.get("Sıklet")
    )

    today_hp = (
        horse.get("hp")
        or horse.get("HP")
        or horse.get("rating")
    )

    scores = {
        "race_type": _su_race_type_score(
            past_type,
            today["race_type"]
        ),
        "class": _su_class_score(
            _su_class(past_class),
            today["class_no"]
        ),
        "distance": _su_distance_score(
            past_distance,
            today["distance"]
        ),
        "weight": _su_weight_score(
            past_weight,
            today_weight
        ),
        "hp": _su_hp_score(
            past_hp,
            today_hp
        ),
        "finish": _su_finish_score(place),
    }

    # Eksik değerler 50 ile nötr kalır.
    # Pist + ırk eşleşmesi yukarıda filtrelenir.
    return (
        scores["race_type"] * 0.20
        + scores["class"] * 0.20
        + scores["distance"] * 0.20
        + scores["weight"] * 0.15
        + scores["hp"] * 0.15
        + scores["finish"] * 0.10
    )


def calculate_sart_uyumu(
    horse: Dict[str, Any],
    race: Dict[str, Any],
) -> Dict[str, Any]:

    today = _su_parse_today(race)

    history = horse.get("_history", [])

    if not isinstance(history, list):
        history = []

    matches = []

    for row in history:

        score = _su_history_row_match(
            horse,
            row,
            today
        )

        if score is None:
            continue

        matches.append({
            "score": score,
            "date": (
                row.get("date")
                or row.get("tarih")
                or ""
            ),
            "race": (
                row.get("raceName")
                or row.get("race_name")
                or row.get("kosu")
                or ""
            ),
            "distance": (
                row.get("distance")
                or row.get("msf")
                or row.get("mesafe")
                or ""
            ),
            "surface": (
                row.get("surface")
                or row.get("pist")
                or ""
            ),
            "weight": (
                row.get("weight")
                or row.get("kilo")
                or row.get("siklet")
                or ""
            ),
            "hp": (
                row.get("hp")
                or row.get("HP")
                or ""
            ),
            "finish": (
                row.get("place")
                or row.get("sira")
                or row.get("S")
                or ""
            ),
        })

    matches.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # En güçlü gerçek TJK şart eşleşmelerini kullan.
    selected = matches[:5]

    if not selected:
        return {
            "score": 50.0,
            "confidence": 0.0,
            "sample": 0,
            "matches": [],
        }

    # En iyi eşleşme daha belirleyicidir.
    rank_weights = [0.40, 0.25, 0.15, 0.12, 0.08]

    total = 0.0
    weight_sum = 0.0

    for i, item in enumerate(selected):
        w = rank_weights[i]
        total += item["score"] * w
        weight_sum += w

    score = total / weight_sum

    # Güven: gerçek TJK şart eşleşmesi sayısına göre.
    sample = len(matches)

    if sample >= 10:
        confidence = 100.0
    elif sample >= 7:
        confidence = 90.0
    elif sample >= 5:
        confidence = 80.0
    elif sample >= 3:
        confidence = 65.0
    elif sample >= 2:
        confidence = 45.0
    else:
        confidence = 30.0

    # Tek eşleşmenin skoru gereğinden fazla yükseltmesini önle.
    if sample == 1:
        score = score * 0.75 + 50.0 * 0.25
    elif sample == 2:
        score = score * 0.85 + 50.0 * 0.15

    return {
        "score": round(max(0.0, min(100.0, score)), 1),
        "confidence": confidence,
        "sample": sample,
        "matches": selected,
    }


def calculate_guncel_sinif(horse: Dict[str, Any], max_races: int = 5) -> float:
    """Atın son gerçek TJK yarışlarından güncel sınıf seviyesini hesaplar.

    - Galop, AGF, jokey, bugünkü kilo ve bugünkü HP kullanılmaz.
    - Yalnızca atın gerçek geçmiş yarışlarındaki sınıf/koşu bilgisi kullanılır.
    - En yeni yarış daha yüksek ağırlıklıdır.
    - Sınıf bilgisi olmayan kayıtlar puana dahil edilmez.
    """
    history = horse.get("_history", [])
    if not isinstance(history, list):
        return 50.0

    parsed = []
    for row in history:
        if not isinstance(row, dict):
            continue
        class_text = _history_class_text(row)
        level = _class_level_from_text(class_text)
        if level is None:
            continue
        parsed.append((row, level))
        if len(parsed) >= max_races:
            break

    if not parsed:
        return 50.0

    # TJK geçmişi yeni -> eski sıralı geliyor. Değilse tarih üzerinden sıralamayı
    # zorlamıyoruz; Worker'ın verdiği gerçek sıra korunuyor.
    weights = [1.00, 0.85, 0.70, 0.55, 0.40]
    used = weights[:len(parsed)]
    weighted = sum(level * w for (_, level), w in zip(parsed, used)) / sum(used)
    return round(max(0.0, min(100.0, weighted)), 1)


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

# Gün değiştiğinde önceki Streamlit widget state'inin (örn. 12/09)
# yeni günü (örn. 13/09) kilitlemesini engelle. Kullanıcı aynı gün
# farklı bir tarih seçerse seçimi korunur; yalnızca takvim günü değiştiğinde
# otomatik olarak bugüne geçilir.
try:
    from zoneinfo import ZoneInfo
    _today = datetime.now(ZoneInfo("Europe/Istanbul")).date()
except Exception:
    _today = date.today()
if st.session_state.get("_date_auto_sync_day") != _today:
    st.session_state["selected_date_widget"] = _today
    st.session_state["_date_auto_sync_day"] = _today

selected_date = st.sidebar.date_input(
    "Tarih",
    key="selected_date_widget",
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

# ============================================================
# PROGRAMI GETİR
# ============================================================

get_program_clicked = st.sidebar.button(
    "📥 PROGRAMI GETİR",
    key="program_get_button",
    use_container_width=True,
)

# Program özeti, program verisi alındıktan sonra sol panelde gösterilir.

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

# Program özeti races tanımlandıktan sonra gösterilir.
st.sidebar.markdown(
    f"<div class='sidebar-program-status'>"
    f"{selected_city} — {selected_date.strftime('%d/%m/%Y')} — "
    f"{len(races)} koşu bulundu.<br>"
    f"<b>✓ {len(races)} koşu • "
    f"{sum(len(r.get('horses', [])) for r in races if isinstance(r, dict))} at verisi alındı</b>"
    f"</div>",
    unsafe_allow_html=True,
)


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

# Üstteki yeşil program bilgi bandı bilinçli olarak kaldırıldı.
# Program bilgisi yalnızca sol panelde, PROGRAMI GETİR butonunun altında gösterilir.


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
            f"{race_number}. KOŞU {race_time}"
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
    st.session_state.selected_horse_index = None
    # GERÇEK VERİ modu varsayılandır: yeni koşu seçildiğinde geçmiş
    # yarış/galop verisini otomatik olarak hazırla. Aksi halde ŞART UYUMU
    # ve GÜNCEL SINIF, veri gelmeden zorunlu olarak 50.0 gösterirdi.
    st.session_state.real_analysis_requested = True
    st.session_state.real_analysis_done = False
    st.session_state["_last_race_signature"] = _current_race_signature

# ============================================================
# KOŞU BİLGİLERİ
# ============================================================

race_number = get_race_number(selected_race, 1)
race_time = display_value(selected_race.get("race_time"))
distance = display_value(selected_race.get("distance"))
surface = display_value(selected_race.get("surface"))
condition = get_race_condition(selected_race)

st.markdown(
    f"""<div class='race-info-compact'>
        <div class='race-title-panel'>
            <span class='race-title-main'>{race_time if race_time != '-' else ''}</span>
            <span class='race-condition'>{condition}</span>
            <span class='race-distance'>{distance} {surface}</span>
        </div>
    </div>""",
    unsafe_allow_html=True,
)


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


if not horses:

    st.warning(
        "Seçilen koşuya ait at verisi henüz alınmadı."
    )

else:

    # GERÇEK VERİYLE ANALİZ: Worker V1'in mevcut /api/tjk/horsedata
    # endpointi üzerinden her koşan atın geçmiş + galop verisini al.
    if st.session_state.get("real_analysis_requested"):
        # "GERÇEK VERİ İLE ANALİZ ET" her basıldığında yeni TJK isteği yapılabilsin.
        # Önceki başarısız/boş cevap cache'de tutulursa buton tekrar basıldığında
        # Worker'a hiç gitmeden aynı boş sonuç dönebilir.
        try:
            load_horse_enrichment.clear()
        except Exception:
            pass

        real_status = st.status(
            "🔄 TJK gerçek verileri çekiliyor...",
            expanded=True,
        )
        real_status.write(
            f"📡 {len(horses)} koşan at için gerçek koşu geçmişi + galop sorgulanıyor..."
        )
        real_status.write(
            f"🎯 Hedef: {selected_city} • {distance} • {surface} • {condition}"
        )
        try:
            horses = enrich_race_horses(
                horses,
                target_date=selected_date,
                target_city=selected_city,
                target_distance=distance,
                target_surface=surface,
                target_class=condition,
            )
            history_count = sum(
                len(h.get("_history", []))
                for h in horses
                if isinstance(h, dict)
            )
            workout_count = sum(
                len(h.get("_workouts", []))
                for h in horses
                if isinstance(h, dict)
            )
            st.session_state.real_analysis_done = True
            real_status.update(
                label=(
                    f"✅ Gerçek TJK verileri alındı • "
                    f"{history_count} koşu kaydı • {workout_count} galop kaydı"
                ),
                state="complete",
                expanded=False,
            )
        except Exception as exc:
            real_status.update(
                label="❌ Gerçek TJK veri analizi başarısız",
                state="error",
                expanded=True,
            )
            real_status.write(str(exc))
            st.error(f"Gerçek veri analizi sırasında hata: {exc}")
        selected_race["horses"] = horses
        st.session_state.real_analysis_requested = False

    ranking = calculate_ranking(horses, selected_race, selected_city)
    # Analiz sonucu horse_index üzerinden eşlenir.
    # Böylece TJK at numarası (No) ile analiz sırası (Sıra) birbirine karışmaz.
    by_index = {item["horse_index"]: item for item in ranking}

    # ========================================================
    # TJK YENİ ANA TABLO — TIKLANABİLİR SATIR + SIRALAMA/FİLTRE
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
        # GÜNCEL SINIF artık Güncel Form bileşeninden alınmaz.
        # Gerçek TJK geçmişindeki son yarışların sınıf seviyesinden hesaplanır.
        current_class = calculate_guncel_sinif(horse)
        sart_result = calculate_sart_uyumu(horse, selected_race)
        sart_uyumu = float(sart_result.get("score", 50.0))

        table_rows.append({
            "_horse_index": horse_index,
            "_horse_no": int(get_horse_number(horse, horse_index + 1)),
            "_rank": int(r["rank"]) if str(r["rank"]).isdigit() else 999999,
            # No = TJK'nın gerçek programdaki AT NUMARASI.
            # Analiz sırası ile at numarasını birbirine karıştırma.
            "No": int(get_horse_number(horse, horse_index + 1)),
            "At İsmi": "\n".join([x for x in (get_horse_name(horse), get_horse_equipment(horse)) if x]),
            "Yaş": get_horse_age(horse),
            "Orijin (Baba-Anne)": "\n".join([x for x in _split_origin(get_horse_origin(horse)) if x]),
            "Kilo": get_horse_weight(horse),
            "Jokey": get_horse_jockey(horse),
            "Sahip / Antrenör": "\n".join(
                [
                    owner if owner else "",
                    trainer if trainer else "",
                ]
            ).strip() or "-",
            "St": get_horse_start(horse),
            "HP": get_horse_hp(horse),
            "Son 6 Y.": form_digits,
            "KGS": get_horse_kgs(horse),
            "s20": display_value(horse.get("s20")),
            "EİD": display_value(horse.get("bestTime")),
            "Gny": display_value(horse.get("odds")),
            "AGF": get_horse_agf(horse),
            "BİZİM SKOR": r["score"],
            "ŞART UYUMU": sart_uyumu,
            "GÜNCEL SINIF": current_class,
            "SON GALOP": workout_display(horse),
            "SON KOŞU": last_race_display(horse),
            "BU YIL KAZANÇ": _format_tl(year_earnings(horse, target_year)),
            "TOPLAM KAZANÇ": _format_tl(total_earnings(horse)),
            "Sahip": owner or "-",
            "Antrenör": trainer or "-",
        })

    # Ekran sırası TJK programındaki gerçek AT NUMARASIDIR.
    # Analiz sırası (_rank) yalnızca BİZİM SKOR / analiz özetinde kullanılır.
    # Böylece program 1,2,3,4... şeklinde gelir; 3,2,4,9 gibi skor sıralaması
    # ana program tablosunun düzenini bozmaz.
    table_rows.sort(key=lambda row: (
        int(row.get("_horse_no", 999999)),
        int(row.get("_horse_index", 999999)),
    ))

    df = pd.DataFrame(table_rows)
    display_columns = [
        "No", "At İsmi", "Yaş", "Orijin (Baba-Anne)", "Kilo", "Jokey",
        "Sahip / Antrenör", "St", "HP", "Son 6 Y.", "KGS", "s20", "EİD", "Gny", "AGF",
        "BİZİM SKOR", "ŞART UYUMU", "GÜNCEL SINIF",
        "SON GALOP", "SON KOŞU", "BU YIL KAZANÇ", "TOPLAM KAZANÇ",
    ]
    df = pd.DataFrame(table_rows)
    df_display = df[display_columns].copy()
    df_display["No"] = pd.to_numeric(df_display["No"], errors="coerce").fillna(0).astype(int)

    # ------------------------------------------------------------------
    # V1-V6 ANA TABLO — AG GRID
    # ------------------------------------------------------------------
    # AG Grid yalnızca görüntüleme/etkileşim katmanıdır. Analiz hesapları,
    # TJK veri modeli ve sıralama mantığı Python tarafında aynen korunur.
    # _horse_index ve _last_surface seçim/render işlemleri için gizli alandır.
    df_grid = df_display.copy()
    df_grid["_horse_index"] = df["_horse_index"].values
    df_grid["_last_surface"] = [
        str((((horses[int(hidx)].get("_last_race") or {}).get("surface")) or ((horses[int(hidx)].get("_last_race") or {}).get("pist")) or ""))
        if str(hidx).strip().lstrip("-").isdigit() and 0 <= int(hidx) < len(horses) and isinstance(horses[int(hidx)], dict) else ""
        for hidx in df["_horse_index"].tolist()
    ]

    def _js_safe(v):
        return str(v if v is not None else "").replace("\\", "\\\\").replace("'", "\\'")

    cell_style_js = JsCode("""
    function(params) {
        const idx = params.data && params.data._horse_index;
        const selected = window.__ri_selected_horse_index;
        const base = (params.node.rowIndex % 2 === 0) ? '#ffffff' : '#f1f3f5';
        return {
            backgroundColor: (selected !== undefined && String(idx) === String(selected)) ? '#dceeff' : base,
            color: (selected !== undefined && String(idx) === String(selected)) ? '#062b55' : '#17212b',
            fontWeight: '700',
            fontSize: '12px',
            whiteSpace: 'pre-line',
            lineHeight: '1.15'
        };
    }
    """)

    def _esc_js_text(expr):
        # JavaScript helper body used inside renderers; all external cell data
        # is escaped before being inserted into HTML.
        return f"String({expr} ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\\"/g,'&quot;')"

    # AG Grid 29+ / streamlit-aggrid: direct HTML string returns may be rendered
    # as literal text. Use class-based cell renderers that create real DOM nodes.
    origin_renderer = JsCode(r"""
    class OriginRenderer {
        init(params) {
            const root = document.createElement('div');
            root.style.lineHeight = '1.18';
            root.style.whiteSpace = 'nowrap';
            const parts = String(params.value ?? '').split(/\r?\n/);
            const sire = document.createElement('span');
            sire.textContent = parts[0] || '';
            sire.style.color = '#1565c0';
            sire.style.fontWeight = '800';
            root.appendChild(sire);
            if (parts.length > 1) {
                root.appendChild(document.createElement('br'));
                const dam = document.createElement('span');
                dam.textContent = parts[1] || '';
                dam.style.color = '#111111';
                dam.style.fontWeight = '700';
                root.appendChild(dam);
            }
            this.eGui = root;
        }
        getGui() { return this.eGui; }
    }
    """)

    # At İsmi hücresine doğrudan tıklanabilir alan veriyoruz.
    # Tıklama satırı seçer; mevcut Python tarafındaki SELECTION_CHANGED akışı
    # da aynı anda çalışarak gerçek koşu + galop ayrıntılarını açar.
    horse_name_renderer = JsCode(r"""
    class HorseNameRenderer {
        init(params) {
            const root = document.createElement('span');
            const parts = String(params.value ?? '').split(/\r?\n/);
            const name = document.createElement('span');
            name.textContent = parts[0] || '';
            name.style.cursor = 'pointer';
            name.style.fontWeight = '800';
            name.title = 'Gerçek koşular ve galopları aç';
            name.addEventListener('click', function(e) {
                e.stopPropagation();
                if (params.node) {
                    params.node.setSelected(true);
                    if (params.api) params.api.ensureNodeVisible(params.node);
                }
            });
            root.appendChild(name);
            if (parts.length > 1 && parts[1]) {
                root.appendChild(document.createElement('br'));
                const eq = document.createElement('span');
                eq.textContent = parts.slice(1).join('\n');
                eq.style.fontWeight = '600';
                eq.style.fontSize = '11px';
                root.appendChild(eq);
            }
            this.eGui = root;
        }
        getGui() { return this.eGui; }
    }
    """)

    jockey_renderer = JsCode(r"""
    class JockeyRenderer {
        init(params) {
            const root = document.createElement('div');
            root.style.lineHeight = '1.18';
            const parts = String(params.value ?? '').split(/\r?\n/);
            parts.forEach((part, i) => {
                if (i > 0) root.appendChild(document.createElement('br'));
                const span = document.createElement('span');
                span.textContent = part;
                if (/^Ap$/i.test(part.trim())) {
                    span.style.color = '#d40000';
                    span.style.fontWeight = '900';
                }
                root.appendChild(span);
            });
            this.eGui = root;
        }
        getGui() { return this.eGui; }
    }
    """)

    owner_trainer_renderer = JsCode(r"""
    class OwnerTrainerRenderer {
        init(params) {
            const root = document.createElement('div');
            root.style.lineHeight = '1.18';
            const parts = String(params.value ?? '').split(/\r?\n/);
            const owner = document.createElement('span');
            owner.textContent = parts[0] || '';
            owner.style.color = '#1565c0';
            owner.style.fontWeight = '800';
            root.appendChild(owner);
            if (parts.length > 1) {
                root.appendChild(document.createElement('br'));
                const trainer = document.createElement('span');
                trainer.textContent = parts[1] || '';
                trainer.style.color = '#d40000';
                trainer.style.fontWeight = '800';
                root.appendChild(trainer);
            }
            this.eGui = root;
        }
        getGui() { return this.eGui; }
    }
    """)

    weight_renderer = JsCode(r"""
    class WeightRenderer {
        init(params) {
            const root = document.createElement('span');
            const v = String(params.value ?? '');
            const m = v.match(/^(.*?)(\s*\+\s*\d+(?:[.,]\d+)?)\s*$/);
            if (m) {
                const base = document.createTextNode(m[1]);
                root.appendChild(base);
                const extra = document.createElement('span');
                extra.textContent = m[2];
                extra.style.color = '#d40000';
                extra.style.fontWeight = '900';
                root.appendChild(extra);
            } else {
                root.textContent = v;
            }
            this.eGui = root;
        }
        getGui() { return this.eGui; }
    }
    """)

    eid_renderer = JsCode(r"""
    class EidRenderer {
        init(params) {
            const span = document.createElement('span');
            span.textContent = String(params.value ?? '');
            span.style.color = '#d40000';
            span.style.fontWeight = '900';
            this.eGui = span;
        }
        getGui() { return this.eGui; }
    }
    """)

    last_race_renderer = JsCode(r"""
    class LastRaceRenderer {
        init(params) {
            const span = document.createElement('span');
            span.textContent = String(params.value ?? '');
            const surf = String((params.data && params.data._last_surface) || '').toLowerCase();
            const isGrass = surf.includes('çim') || surf.includes('cim') || surf.includes('grass') || surf.includes('turf');
            span.style.color = isGrass ? '#138a36' : '#111111';
            span.style.fontWeight = '900';
            this.eGui = span;
        }
        getGui() { return this.eGui; }
    }
    """)

    selected_horse_index = st.session_state.get("selected_horse_index")

    grid_options = {
        "rowHeight": 44,
        "headerHeight": 38,
        "domLayout": "normal",
        "suppressRowClickSelection": False,
        "rowSelection": "single",
        "animateRows": False,
        "enableCellTextSelection": True,
        "ensureDomOrder": True,
        "defaultColDef": {
            "sortable": True,
            "filter": True,
            "resizable": True,
            "wrapText": True,
            "autoHeight": False,
        },
        "onGridReady": JsCode("""
            function(params) {
                window.__ri_selected_horse_index = %s;
            }
        """ % ("null" if selected_horse_index is None else str(int(selected_horse_index)))),
        "onCellClicked": JsCode("""
            function(params) {
                if (params.colDef && params.colDef.field === 'At İsmi' && params.node) {
                    params.node.setSelected(true);
                    if (params.data && params.data._horse_index !== undefined) {
                        window.__ri_selected_horse_index = params.data._horse_index;
                    }
                }
            }
        """),
        "onRowClicked": JsCode("""
            function(params) {
                if (params.data && params.data._horse_index !== undefined) {
                    window.__ri_selected_horse_index = params.data._horse_index;
                }
            }
        """),
    }

    gb = GridOptionsBuilder.from_dataframe(df_grid)
    gb.configure_default_column(
        sortable=True, filter=True, resizable=True,
        wrapText=True, autoHeight=False,
    )
    gb.configure_selection(selection_mode="single", use_checkbox=False)
    gb.configure_grid_options(**grid_options)

    # Sabit sütunlar.
    gb.configure_column("No", header_name="No", pinned="left", width=62, minWidth=55, maxWidth=75, type=["numericColumn"])
    gb.configure_column("At İsmi", header_name="At İsmi", pinned="left", width=145, minWidth=120, cellRenderer=horse_name_renderer)
    gb.configure_column("Yaş", width=55, minWidth=48)
    gb.configure_column("Orijin (Baba-Anne)", width=165, minWidth=145, cellRenderer=origin_renderer)
    gb.configure_column("Kilo", width=75, minWidth=65, cellRenderer=weight_renderer)
    gb.configure_column("Jokey", width=105, minWidth=90, cellRenderer=jockey_renderer)
    gb.configure_column("Sahip / Antrenör", width=150, minWidth=125, cellRenderer=owner_trainer_renderer)
    gb.configure_column("St", width=52, minWidth=45)
    gb.configure_column("HP", width=58, minWidth=50)
    gb.configure_column("Son 6 Y.", width=85, minWidth=70)
    gb.configure_column("KGS", width=58, minWidth=50)
    gb.configure_column("s20", width=58, minWidth=50)
    gb.configure_column("EİD", width=75, minWidth=65, cellRenderer=eid_renderer)
    gb.configure_column("Gny", width=60, minWidth=50)
    gb.configure_column("AGF", width=70, minWidth=60)
    gb.configure_column("BİZİM SKOR", width=105, minWidth=90)
    gb.configure_column("ŞART UYUMU", width=105, minWidth=90)
    gb.configure_column("GÜNCEL SINIF", width=110, minWidth=95)
    gb.configure_column("SON GALOP", width=95, minWidth=80)
    gb.configure_column("SON KOŞU", width=95, minWidth=80, cellRenderer=last_race_renderer)
    gb.configure_column("BU YIL KAZANÇ", width=115, minWidth=100)
    gb.configure_column("TOPLAM KAZANÇ", width=120, minWidth=105)
    gb.configure_column("_horse_index", hide=True)
    gb.configure_column("_last_surface", hide=True)

    grid_options = gb.build()
    grid_options["rowStyle"] = JsCode("""
        function(params) {
            const selected = window.__ri_selected_horse_index;
            if (selected !== undefined && selected !== null && params.data && String(params.data._horse_index) === String(selected)) {
                return {backgroundColor:'#dceeff', color:'#062b55', fontWeight:'700'};
            }
            return null;
        }
    """)
    grid_options["onSelectionChanged"] = JsCode("""
        function(params) {
            const rows = params.api.getSelectedRows();
            if (rows && rows.length) {
                const row = rows[0];
                if (row && row._horse_index !== undefined) {
                    window.__ri_selected_horse_index = row._horse_index;
                } else {
                    const nodes = params.api.getSelectedNodes();
                    if (nodes && nodes.length && nodes[0].data && nodes[0].data._horse_index !== undefined) {
                        window.__ri_selected_horse_index = nodes[0].data._horse_index;
                    }
                }
            } else {
                window.__ri_selected_horse_index = null;
            }
        }
    """)

    # Seçili atın başlangıçta vurgulanması.
    if selected_horse_index is not None:
        grid_options["onFirstDataRendered"] = JsCode("""
            function(params) {
                params.api.forEachNode(function(node) {
                    if (node.data && String(node.data._horse_index) === String(%d)) node.setSelected(true);
                });
            }
        """ % int(selected_horse_index))

    grid_height = min(760, max(150, 42 + len(df_grid) * 44))
    grid_response = AgGrid(
        df_grid,
        gridOptions=grid_options,
        height=grid_height,
        width="100%",
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        update_on=["selectionChanged"],
        data_return_mode="AS_INPUT",
        theme="streamlit",
        key="horse_table_aggrid",
    )

    # streamlit-aggrid 1.x dönen selected_rows tipini sürümler arasında
    # değiştirebildiği için hem dict/list hem DataFrame hem de GridReturn
    # nesnesini güvenli biçimde ele alıyoruz. Ayrıca bazı sürümlerde
    # _horse_index dönüşe dahil edilmezse nodeRowIndex geri dönüş yoludur.
    selected_rows = []
    try:
        selected_rows = grid_response.get("selected_rows") or []
    except Exception:
        try:
            selected_rows = grid_response.selected_rows or []
        except Exception:
            selected_rows = []

    if hasattr(selected_rows, "to_dict"):
        try:
            selected_rows = selected_rows.to_dict("records")
        except Exception:
            selected_rows = []

    if selected_rows:
        row0 = selected_rows[0] if isinstance(selected_rows, (list, tuple)) else None
        if row0 is None and isinstance(selected_rows, dict):
            row0 = selected_rows
        try:
            raw_index = row0.get("_horse_index") if isinstance(row0, dict) else None
            if raw_index is None and isinstance(row0, dict):
                node_info = row0.get("_selectedRowNodeInfo") or row0.get("_nodeInfo") or {}
                raw_index = node_info.get("nodeRowIndex")
            selected_horse_index = int(raw_index) if raw_index is not None else None
        except Exception:
            selected_horse_index = None
        if selected_horse_index is not None and 0 <= selected_horse_index < len(horses):
            selected_horse = horses[selected_horse_index]
            st.session_state.selected_horse_no = get_horse_number(
                selected_horse,
                selected_horse_index + 1,
            )
            st.session_state.selected_horse_index = selected_horse_index
            _detail_fetch_key = (str(selected_horse.get("atId") or selected_horse.get("at_id") or selected_horse.get("id") or ""), str(selected_horse_index), str(selected_date), str(selected_city), str(distance), str(surface), str(condition))

            if st.session_state.get("_selected_detail_fetch_key") != (str(selected_horse.get("atId") or selected_horse.get("at_id") or selected_horse.get("id") or ""), str(selected_horse_index), str(selected_date), str(selected_city), str(distance), str(surface), str(condition)):
                # Ana tablo satırına ilk tıklamada boş cache varsa temizle.
                # Böylece TJK geçmişi/galop verisi gerçekten yeniden sorgulanır.
                try:
                    load_horse_enrichment.clear()
                except Exception:
                    pass

                horse_status = st.status(
                    f"🔄 {get_horse_name(selected_horse)} için TJK gerçek koşu ve galop verileri çekiliyor...",
                    expanded=True,
                )
                horse_status.write("📡 Worker /api/tjk/horsedata sorgulanıyor...")
                horse_status.write(
                    f"🎯 Hedef yarış: {selected_city} • {distance} • {surface} • {condition}"
                )
                try:
                    enriched_one = enrich_race_horses(
                        [selected_horse],
                        target_date=selected_date,
                        target_city=selected_city,
                        target_distance=distance,
                        target_surface=surface,
                        target_class=condition,
                    )
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
                    st.session_state["_selected_detail_fetch_key"] = _detail_fetch_key
                except Exception as exc:
                    horse_status.update(
                        label="❌ At geçmişi/galop sorgusu başarısız",
                        state="error",
                        expanded=True,
                    )
                    st.error(str(exc))
                    st.session_state["_selected_detail_fetch_key"] = _detail_fetch_key

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
            # V3 — native tablo mimarisini bozmadan EİD ayrıntısını seçilen
            # at için aç/kapatılabilir bilgi alanında göster.
            eid_detail = best_race_detail(selected_horse)
            if eid_detail:
                with st.expander(f"🔴 EİD BİLGİSİ — {eid_detail.get('Derece', '-')}  •  aç / kapat", expanded=False):
                    eid_cols = st.columns(4)
                    eid_cols[0].metric("Derece", eid_detail.get("Derece", "-"))
                    eid_cols[1].write(f"**Hipodrom:** {eid_detail.get('Hipodrom', '-')}\n\n**Tarih:** {eid_detail.get('Tarih', '-')}")
                    eid_cols[2].write(f"**Mesafe:** {eid_detail.get('Mesafe', '-')}\n\n**Bilgi:** {eid_detail.get('Bilgi', '-')}")
                    eid_cols[3].caption("TJK programındaki En İyi Derece kaydı")
            st.subheader(
                f"🐎 {get_horse_number(selected_horse, 0)} - {get_horse_name(selected_horse)}"
            )

            st.markdown("<div class='selected-horse-card'>"
                        f"<div class='selected-horse-name'>{get_horse_name(selected_horse)}</div>"
                        f"<div class='selected-horse-origin'>{_split_origin(get_horse_origin(selected_horse))[0]}"
                        f"<br>{_split_origin(get_horse_origin(selected_horse))[1]}</div>"
                        "</div>", unsafe_allow_html=True)

            tab_all, tab_first, tab_stats, tab_work = st.tabs([
                "Tüm Yarışları", "1.'likleri", "İstatistikler", "Galoplar"
            ])

            history = selected_horse.get("_history", [])
            workouts = selected_horse.get("_workouts", [])

            if selected_horse.get("_enrichment_error"):
                st.warning(
                    "TJK gerçek veri sorgusu: "
                    + str(selected_horse.get("_enrichment_error"))
                )
            else:
                st.caption(
                    f"Gerçek TJK veri: {len(history)} koşu kaydı • "
                    f"{len(workouts)} galop kaydı"
                )

            with tab_all:
                _history_tables(history)

            with tab_first:
                firsts = []
                for h in history:
                    if not isinstance(h, dict):
                        continue
                    place = str(_first_value(h, ["place", "sira", "S"])).strip()
                    if re.match(r"^1(?:\.0)?$", place):
                        firsts.append(h)
                _history_tables(firsts) if firsts else st.info("TJK geçmişinde 1.'lik kaydı bulunamadı.")

            with tab_stats:
                total = len([h for h in history if isinstance(h, dict)])
                first = second = third = 0
                total_prize = 0.0
                year_prize = 0.0
                for h in history:
                    if not isinstance(h, dict):
                        continue
                    place = str(_first_value(h, ["place", "sira", "S"])).strip().replace(".", "")
                    if place == "1": first += 1
                    elif place == "2": second += 1
                    elif place == "3": third += 1
                    pv = _money_number(_first_value(h, ["prize", "ikramiye"]))
                    total_prize += pv
                    if _history_year(h) == selected_date.year:
                        year_prize += pv
                stat_rows = pd.DataFrame([
                    {"Gösterge":"TOPLAM KOŞU", "Değer":total},
                    {"Gösterge":"1.'lik", "Değer":first},
                    {"Gösterge":"2.'lik", "Değer":second},
                    {"Gösterge":"3.'lük", "Değer":third},
                    {"Gösterge":"Kazanç", "Değer":_format_tl(total_prize * 1.20)},
                    {"Gösterge":f"{selected_date.year} Kazancı", "Değer":_format_tl(year_prize * 1.20)},
                ])
                st.dataframe(stat_rows, use_container_width=True, hide_index=True, column_config={
                    "Gösterge": st.column_config.TextColumn("Gösterge", width=220),
                    "Değer": st.column_config.TextColumn("Değer", width=180),
                })

            with tab_work:
                _workout_tables(workouts)


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


# V7 son güvenlik CSS'i: başlık alanı hiçbir üst konteyner tarafından kırpılmasın.
st.markdown("""
<style>
section.main,
section.main > div,
section.main [data-testid="stMainBlockContainer"] {
    overflow: visible !important;
}
div.ri-header {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    height: auto !important;
    max-height: none !important;
    overflow: visible !important;
}
div.ri-title {
    display: block !important;
    visibility: visible !important;
    color: #FFFFFF !important;
    font-size: 40px !important;
    font-weight: 950 !important;
    line-height: 1.15 !important;
    white-space: nowrap !important;
    text-align: center !important;
    width: 100% !important;
    margin-top: 5mm !important;
}
div.ri-subtitle {
    display: block !important;
    visibility: visible !important;
}
</style>
""", unsafe_allow_html=True)
