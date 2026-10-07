import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
import pandas as pd
import re
import html as _html
from datetime import date, datetime
from typing import Any, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from tjk_fetch import get_program, get_horse_enrichment

# BİZİM SKOR: Uygulama ile aynı klasördeki sabit 5 bileşenli motoru
# zorunlu olarak yükle. Böylece Streamlit ortamında eski/başka bir
# "bizim_skor_model" modülünün yanlışlıkla import edilmesi engellenir.
import importlib.util as _importlib_util
from pathlib import Path as _Path

_BIZIM_MODEL_PATH = _Path(__file__).with_name("bizim_skor_model.py")
_BIZIM_SPEC = _importlib_util.spec_from_file_location(
    "race_intelligence_bizim_skor_model",
    _BIZIM_MODEL_PATH,
)
if _BIZIM_SPEC is None or _BIZIM_SPEC.loader is None:
    raise ImportError(f"BİZİM SKOR motoru bulunamadı: {_BIZIM_MODEL_PATH}")
_BIZIM_MODULE = _importlib_util.module_from_spec(_BIZIM_SPEC)
_BIZIM_SPEC.loader.exec_module(_BIZIM_MODULE)
calculate_bizim_ranking = _BIZIM_MODULE.calculate_bizim_ranking


# ============================================================
# SAYFA AYARLARI
# ============================================================
# BU UYGULAMADA GÖRÜNTÜ / KAYIT / ARŞİV ALMA MEKANİZMASI YOKTUR.
# Analiz yalnızca canlı TJK verisi ve sabit BİZİM SKOR motoru ile yapılır.


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
# BİZİM SKOR / SABİT 5 BİLEŞEN MOTORU
# ============================================================
# Eski manuel ağırlık sistemi tamamen kaldırıldı.
# Motor yalnızca gerçek TJK geçmişini kullanarak sabit 5 bileşeni hesaplar.
# Öğrenme / AUC / 20 aileli model yoktur.

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
if "_last_eid_click_token" not in st.session_state:
    st.session_state["_last_eid_click_token"] = ""


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
        border: 1px solid #b9c8d8;
        border-radius: 7px;
        overflow: hidden;
        background: #f8f3e7;
        color: #16324d;
        padding: 0 !important;
        box-sizing: border-box;
        display: block !important;
        box-shadow: none;
        text-transform: none !important;
    }
    .race-title-panel .race-header-line {
        width: 100%;
        min-height: 34px;
        box-sizing: border-box;
        padding: 5px 10px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        font-size: 15px;
        line-height: 1.15;
        font-weight: 900;
        white-space: nowrap;
        overflow: hidden;
    }
    .race-title-panel .race-header-detail {
        font-weight: 900;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .race-title-panel .race-prize-row {
        width: 100%;
        box-sizing: border-box;
        padding: 4px 10px;
        background: #f8f3e7;
        display: flex;
        align-items: center;
        gap: 28px;
        min-height: 28px;
        overflow: hidden;
    }
    .race-title-panel .race-prize-line {
        flex: 1 1 50%;
        min-width: 0;
        font-size: 12px;
        line-height: 1.25;
        font-weight: 700;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        color: #506f13;
    }
    .race-title-panel .race-prize-line .prize-label {
        font-weight: 900;
        color: #506f13;
    }
    .race-title-panel .race-owner-row {
        width: 100%;
        box-sizing: border-box;
        padding: 4px 10px 5px;
        background: #f8f3e7;
        min-height: 27px;
    }
    .race-title-panel .race-owner-row .race-prize-line {
        width: 100%;
    }
    @media (max-width: 900px) {
        .race-title-panel .race-header-line {
            font-size: 13px;
        }
        .race-title-panel .race-prize-row {
            gap: 12px;
        }
        .race-title-panel .race-prize-line {
            font-size: 11px;
        }
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
# ANALİZ KONTROLLERİ
# ============================================================

def _request_real_analysis():
    st.session_state["analysis_mode"] = "Gerçek veri"
    st.session_state["real_analysis_requested"] = True
    st.session_state["real_analysis_done"] = False


def _request_manual_analysis():
    st.session_state["analysis_mode"] = "Manuel"
    st.session_state["real_analysis_requested"] = False
    st.session_state["real_analysis_done"] = False


btn1, btn2, btn3, mode_col = st.columns([1.15, 1.15, 1.15, 0.65])
with btn1:
    st.empty()
with btn2:
    _real_clicked = st.button(
        "🔎 GERÇEK VERİ İLE ANALİZ ET",
        key="real_analysis_button_top",
        use_container_width=True,
        type="primary",
    )
    # Callback yerine tıklama sonucunu doğrudan state'e yazıyoruz.
    # Böylece Streamlit rerun sırasında gerçek analiz isteği kaybolmaz.
    if _real_clicked:
        st.session_state["analysis_mode"] = "Gerçek veri"
        st.session_state["real_analysis_requested"] = True
        st.session_state["real_analysis_done"] = False
with btn3:
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

    # TJK/Worker şehir kimlikleri artık doğrudan resmi şehir adıyla
    # eşleşiyor. Elazığ <-> Şanlıurfa ters eşlemesi KULLANILMAMALI.
    # Özellikle 21/09/2026 gibi dinamik programlarda yanlış hipodrom
    # gösterilmesini önlemek için seçilen şehir aynen gönderilir.
    data = get_program(
        selected_date,
        city,
    )

    if isinstance(data, dict):
        data = dict(data)
        # Ekranda her zaman kullanıcının seçtiği hipodrom adı gösterilir.
        data["city"] = city

    return data


# ============================================================
# SEÇİLEN TARİHTEKİ AKTİF HİPODROMLAR
# ============================================================

def load_active_cities(selected_date: date) -> List[str]:
    """
    Seçilen tarihte GERÇEKTEN yarış programı bulunan hipodromları bulur.

    ÖNEMLİ: Bu fonksiyon bilinçli olarak st.cache_data ile cache'lenmez.
    Worker geçici hata verdiğinde boş listenin 15 dakika cache'lenmesi,
    "Bu tarih için hipodrom listesi alınamadı" hatasına neden oluyordu.

    Her şehir en fazla 3 kez denenir. Aynı anda en fazla 2 Worker isteği
    gönderilir. Yalnızca races listesi dolu olan şehir aktif kabul edilir.
    Sonuç her zaman ALL_CITIES sırasına göre döndürülür.
    """
    cache_key = selected_date.isoformat()
    cached = st.session_state.get("_active_cities_cache", {})
    if isinstance(cached, dict):
        saved = cached.get(cache_key)
        if isinstance(saved, list) and saved:
            return [c for c in ALL_CITIES if c in saved]

    def check_city(city: str):
        for attempt in range(3):
            try:
                data = load_program(selected_date, city)
                if not isinstance(data, dict):
                    continue
                races = data.get("races", [])
                if isinstance(races, list) and len(races) > 0:
                    return city
            except Exception:
                # Geçici Worker/TJK hatasında şehir elenmesin; tekrar dene.
                pass
        return None

    active = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(check_city, city): city for city in ALL_CITIES}
        for future in as_completed(futures):
            try:
                city = future.result()
                if city:
                    active.append(city)
            except Exception:
                pass

    # Worker şehir sırasını koru; tamamlanma sırasını kullanma.
    active = [city for city in ALL_CITIES if city in active]

    # SADECE dolu sonuç cache'e alınır. Boş sonuç asla cache'lenmez.
    if active:
        cached = st.session_state.get("_active_cities_cache", {})
        if not isinstance(cached, dict):
            cached = {}
        cached[cache_key] = active
        st.session_state["_active_cities_cache"] = cached

    return active


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
    """TJK'nın gerçek koşu şartını başlıktan çıkarır.

    Önemli: ``Tüm Koşular`` bir filtre değeridir; koşu şartı değildir.
    TJK program parser'ının koruduğu ``meta.raw`` / ``raw`` başlığı varsa,
    şartı doğrudan o başlıktan çıkarıyoruz. Böylece örneğin:

        9. Koşu 18:00 Handikap 16/DHÖW /H1, 4 ve Yukarı Araplar 1500 Sentetik ...

    başlığından yalnızca gerçek şart:

        Handikap 16/DHÖW /H1, 4 ve Yukarı Araplar

    alınır.
    """
    def clean(value: Any) -> str:
        text = display_value(value, "") if value not in (None, "") else ""
        text = re.sub(r"\s+", " ", text).strip(" ,;-:")
        if text.lower() in {"tüm koşular", "tum kosular", "-"}:
            return ""
        return text

    race_no = get_race_number(race, 0)
    race_time = clean(race.get("race_time") or race.get("time"))
    distance = clean(race.get("distance"))
    surface = clean(race.get("surface"))

    # 1) TJK'nın ham koşu başlığından çıkar. Bu, önceki denemede eksik kalan
    # kritik kısımdır: condition alanı '-' olsa bile meta.raw gerçek başlığı taşır.
    raw_sources = []
    meta = race.get("meta")
    if isinstance(meta, dict):
        for key in ("raw", "detail", "raceDetail", "race_detail", "header", "raceHeader", "race_header"):
            value = clean(meta.get(key))
            if value:
                raw_sources.append(value)
    for key in ("raw", "detail", "raceDetail", "race_detail", "header", "raceHeader", "race_header"):
        value = clean(race.get(key))
        if value:
            raw_sources.append(value)

    for raw in raw_sources:
        # Bir raw metni birden fazla koşuyu içerebiliyorsa seçili koşunun
        # son "N. Koşu" işaretinden itibaren olan bölümünü kullan.
        marks = list(re.finditer(r"\b(\d{1,2})\.\s*Koşu\b", raw, flags=re.I))
        if marks:
            wanted = [m for m in marks if race_no and int(m.group(1)) == int(race_no)]
            raw = raw[(wanted[-1] if wanted else marks[-1]).start():]

        # Başlangıç: "9. Koşu 18:00". Saat yoksa sadece "9. Koşu".
        if race_no:
            prefix = rf"\b{int(race_no)}\.\s*Koşu\b"
        else:
            prefix = r"\b\d{1,2}\.\s*Koşu\b"
        m = re.search(prefix, raw, flags=re.I)
        if not m:
            continue
        tail = raw[m.end():].strip()

        if race_time and race_time != "-":
            # Saat formatı 18:00 / 18.00 vb. olabilir.
            tm = re.search(r"^\s*" + re.escape(race_time) + r"\s*", tail)
            if tm:
                tail = tail[tm.end():]
            else:
                tm = re.search(r"^\s*\d{1,2}[:.]\d{2}\s*", tail)
                if tm:
                    tail = tail[tm.end():]

        # İkramiye ve prim bölümlerine gelmeden önce kes.
        tail = re.split(
            r"\s+(?=(?:İkramiye|Ikramiye|Yetiştirici(?:lik)? Primi|Yetistirici(?:lik)? Primi|At\s*Sahibi\s*Primi)\s*[:\-]?)",
            tail,
            maxsplit=1,
            flags=re.I,
        )[0].strip(" ,;-:")

        # Mesafe + pist kısmından hemen önceki metin gerçek koşu şartıdır.
        if distance and distance != "-":
            dm = re.search(r"\b" + re.escape(distance) + r"\b", tail, flags=re.I)
            if dm:
                candidate = clean(tail[:dm.start()])
                if candidate:
                    return candidate

        # Mesafe alanı farklı biçimde geldiyse, pist adı üzerinden kes.
        if surface and surface != "-":
            sm = re.search(r"\b" + re.escape(surface) + r"\b", tail, flags=re.I)
            if sm:
                before_surface = tail[:sm.start()].strip()
                # Son sayı grubunu mesafe kabul edip çıkar.
                candidate = re.sub(r"\s+\d{3,4}\s*$", "", before_surface).strip(" ,;-:")
                candidate = clean(candidate)
                if candidate:
                    return candidate

        # Son çare: ham başlıktaki ilk anlamlı metin; ancak filtre/boş değer dönmesin.
        candidate = clean(tail)
        candidate = re.sub(r"\s+\d{3,4}\s+(?:Kum|Çim|Sentetik)\b.*$", "", candidate, flags=re.I)
        if candidate:
            return candidate

    # 2) Ham başlık yoksa doğrudan normalize edilmiş alanları kullan.
    candidates = []
    for key in (
        "condition", "raceCondition", "race_condition",
        "conditionName", "condition_name", "className", "class",
        "sinif", "sınıf", "raceName", "race_name", "kosu",
        "title", "name",
    ):
        value = clean(race.get(key))
        if value:
            candidates.append(value)

    if isinstance(meta, dict):
        for key in (
            "condition", "raceCondition", "race_condition",
            "conditionName", "condition_name", "className", "class",
            "sinif", "sınıf", "raceName", "race_name", "kosu",
            "title", "name", "detail",
        ):
            value = clean(meta.get(key))
            if value:
                candidates.append(value)

    for candidate in candidates:
        candidate = re.split(
            r"\s+(?=İkramiye\s*:|Ikramiye\s*:|Yetiştirici(?:lik)?\s+Primi\s*:|At\s*Sahibi\s*Primi\s*:)",
            candidate, maxsplit=1, flags=re.I,
        )[0]
        candidate = clean(candidate)
        if candidate:
            return candidate

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

@st.cache_data(ttl=10800, show_spinner=False)
def load_horse_enrichment(
    at_id: str,
    horse_name: str,
) -> Dict[str, Any]:
    try:
        # Cache anahtarı yalnızca at kimliği + isimdir.
        # Hız sürümünde gerçek TJK geçmişi doğrudan alınır;
        # yarış parametreleri burada kullanılmaz.
        return get_horse_enrichment(at_id, horse_name)
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
    progress_callback=None,
) -> List[Dict[str, Any]]:
    """Seçili koşudaki atları paralel zenginleştirir; TJK sırası korunur.

    Hız optimizasyonu:
    - Atlar tek tek beklenmez; en fazla 4 at aynı anda sorgulanır.
    - Her atın geçmiş + galop sorgusu tjk_fetch içinde zaten paraleldir.
    - At geçmişi/galop cache'i 180 dakika tutulur.
    """
    enriched = [dict(h) for h in horses if isinstance(h, dict)]
    if not enriched:
        return []

    total = len(enriched)

    def one(idx_item):
        idx, item = idx_item
        at_id = (
            item.get("atId") or item.get("at_id") or
            item.get("horseId") or item.get("horse_id") or
            item.get("horseKey") or item.get("horse_key") or
            item.get("id") or item.get("Id") or ""
        )
        name = get_horse_name(item)
        if not at_id:
            item["_history"] = []
            item["_workouts"] = []
            item["_enrichment_error"] = "TJK program kaydında atId bulunamadı."
            return idx, item, name

        try:
            data = load_horse_enrichment(str(at_id), name)
        except Exception as exc:
            data = {"ok": False, "history": [], "workouts": [], "error": str(exc)}

        history = data.get("history", []) if isinstance(data, dict) else []
        workouts = data.get("workouts", []) if isinstance(data, dict) else []
        item["_at_id"] = str(at_id)
        item["_history"] = history if isinstance(history, list) else []
        item["_workouts"] = workouts if isinstance(workouts, list) else []
        item["_enrichment_error"] = str(data.get("error") or "-") if isinstance(data, dict) else "-"
        if isinstance(data, dict) and data.get("historySource"):
            item["_history_source"] = data.get("historySource")

        if isinstance(data, dict):
            for key in (
                "totalEarnings", "total_earnings", "lifetimeEarnings", "lifetime_earnings",
                "careerEarnings", "career_earnings", "totalKazanc", "toplamKazanc",
                "toplam_kazanc", "kazanc", "Kazanç", "earnings", "earning",
            ):
                if data.get(key) not in (None, "", "-", 0, 0.0):
                    item["_tjk_total_earnings"] = data.get(key)
                    item["totalEarnings"] = data.get(key)
                    break
            for key in (
                "yearEarnings", "year_earnings", "yearlyEarnings", "yearly_earnings",
                "annualEarnings", "annual_earnings", "yearKazanc", "year_kazanc",
                "buYilKazanc", "bu_yil_kazanc",
            ):
                if data.get(key) not in (None, "", "-", 0, 0.0):
                    item["_tjk_year_earnings"] = data.get(key)
                    item["yearEarnings"] = data.get(key)
                    break
            if data.get("earnings") and isinstance(data.get("earnings"), dict):
                e = data["earnings"]
                total_value = e.get("total") or e.get("totalEarnings") or e.get("kazanc") or e.get("Kazanç")
                year_value = e.get("year") or e.get("yearEarnings") or e.get("yearly") or e.get("buYil")
                if total_value not in (None, "", "-", 0, 0.0):
                    item["_tjk_total_earnings"] = total_value
                    item["totalEarnings"] = total_value
                if year_value not in (None, "", "-", 0, 0.0):
                    item["_tjk_year_earnings"] = year_value
                    item["yearEarnings"] = year_value
            # Resmi toplam/yıllık kazanç Worker'da ayrı alan olarak yoksa
            # gerçek geçmiş satırlarındaki İkramiye/Kazanç alanlarından hesapla.
            if not item.get("_tjk_total_earnings") and item.get("_history"):
                total = 0.0
                year_total = 0.0
                current_year = date.today().year
                for _hr in item.get("_history", []):
                    if not isinstance(_hr, dict):
                        continue
                    _pv = _money_number(_first_value(_hr, [
                        "prize", "ikramiye", "Ikramiye", "İkramiye",
                        "Kazanç", "kazanc", "earnings", "earning",
                        "prizeAmount", "prize_amount",
                    ]))
                    total += _pv
                    if str(current_year) in str(_first_value(_hr, ["date", "tarih", "Tarih"], "")):
                        year_total += _pv
                if total > 0:
                    item["_tjk_total_earnings"] = total
                    item["totalEarnings"] = total
                if year_total > 0:
                    item["_tjk_year_earnings"] = year_total
                    item["yearEarnings"] = year_total

            if data.get("error"):
                item["_enrichment_error"] = str(data.get("error"))

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

        # SON KOŞU sütunu analiz edilen koşunun günündeki yarışı göstermez.
        # Seçili koşu tarihi T ise yalnızca tarih < T olan geçmiş yarışlar
        # arasından en yeni tarihli yarış gösterilir.
        item["_last_race"] = None
        try:
            _target_dt = None
            if target_date is not None:
                if isinstance(target_date, datetime):
                    _target_dt = target_date.date()
                elif isinstance(target_date, date):
                    _target_dt = target_date
                else:
                    _ts = str(target_date).strip()
                    for _fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
                        try:
                            _target_dt = datetime.strptime(_ts[:10], _fmt).date()
                            break
                        except Exception:
                            pass

            _eligible_last = []
            for row in item["_history"]:
                if not isinstance(row, dict):
                    continue
                _date_text = row.get("date") or row.get("tarih") or row.get("Tarih")
                _time_value = row.get("time") or row.get("derece") or row.get("Derece")
                if not _date_text or not _time_value:
                    continue

                _row_dt = None
                _rs = str(_date_text).strip()
                for _fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
                    try:
                        _row_dt = datetime.strptime(_rs[:10], _fmt).date()
                        break
                    except Exception:
                        pass

                # Tarih çözülemiyorsa bugünkü/son yarış olduğu varsayılıp
                # SON KOŞU sütununa alınmaz.
                if _row_dt is None:
                    continue

                # KRİTİK KURAL: aynı gün ve sonrası kesinlikle dışarıda.
                if _target_dt is not None and _row_dt >= _target_dt:
                    continue

                _eligible_last.append((_row_dt, row))

            if _eligible_last:
                _eligible_last.sort(key=lambda x: x[0], reverse=True)
                item["_last_race"] = _eligible_last[0][1]
        except Exception:
            item["_last_race"] = None
        return idx, item, name

    ordered = [None] * total
    done = 0
    # 5 worker x (history + workouts) = at most ~10 upstream requests.
    with ThreadPoolExecutor(max_workers=min(5, total)) as executor:
        futures = [executor.submit(one, pair) for pair in enumerate(enriched)]
        for future in as_completed(futures):
            idx, item, name = future.result()
            ordered[idx] = item
            done += 1
            if progress_callback:
                progress_callback(done, total, name)

    return ordered

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


def _official_earnings_value(horse: Dict[str, Any], year: int | None = None) -> float:
    """Worker/TJK'dan gelen resmi Kazanç değerini kullanır.

    Öncelik:
      1) enrichment sırasında kaydedilen _tjk_total_earnings / _tjk_year_earnings
      2) Worker'ın doğrudan döndürdüğü resmi alanlar
    Burada artık %20 tahmini yapılmaz.
    """
    if year is None:
        keys = (
            "_tjk_total_earnings",
            "totalEarnings", "total_earnings",
            "lifetimeEarnings", "lifetime_earnings",
            "careerEarnings", "career_earnings",
            "totalKazanc", "toplamKazanc", "toplam_kazanc",
            "kazanc", "Kazanç", "earnings", "earning",
        )
    else:
        keys = (
            "_tjk_year_earnings",
            "yearEarnings", "year_earnings",
            "yearlyEarnings", "yearly_earnings",
            "annualEarnings", "annual_earnings",
            "yearKazanc", "year_kazanc",
            "buYilKazanc", "bu_yil_kazanc",
        )
    for key in keys:
        if key in horse and horse.get(key) not in (None, "", "-", 0, 0.0):
            value = _money_number(horse.get(key))
            if value > 0:
                return value
    return 0.0


def _race_prize_total(horse: Dict[str, Any], target_year: int | None = None) -> float:
    """Geçmiş satırlarından yalnızca ikramiye toplamını hesaplar.

    Bu yalnızca resmi TJK Kazanç alanı hiç gelmezse son çare fallback'tir.
    Resmi Kazanç mevcutsa total_earnings/year_earnings onu kullanır.
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
            or row.get("İkramiye")
            or row.get("prizeAmount")
            or row.get("prize_amount")
        )
    return total


def total_earnings(horse: Dict[str, Any]) -> float:
    """Ana tabloda TJK'nın resmi toplam Kazanç değerini gösterir."""
    official = _official_earnings_value(horse)
    if official > 0:
        return round(official, 2)
    # Resmi alan yoksa mevcut geçmiş verisini yanlış %20 ile şişirmemek için
    # yalnızca gerçek ikramiye toplamını döndür.
    return round(_race_prize_total(horse), 2)


def year_earnings(horse: Dict[str, Any], target_year: int) -> float:
    """Ana tabloda TJK'nın resmi yıllık Kazanç değerini gösterir."""
    official = _official_earnings_value(horse, target_year)
    if official > 0:
        return round(official, 2)
    return round(_race_prize_total(horse, target_year), 2)

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
    """Ana tabloda yalnızca en son galobun 400 m derecesini göster."""
    w = latest_workout(horse)
    if not w:
        return "-"
    value = display_value(
        _first_value(w, ["m400", "400", "400m", "m_400", "time400"]),
        "",
    )
    return f"{value} (400)" if value else "-"


def _normalize_surface_for_table(value: Any) -> str:
    """Son 6 Y. renkleri için TJK pist adını standartlaştırır."""
    text = str(value or "").strip().lower()
    text = (
        text.replace("ı", "i")
        .replace("ş", "s")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ç", "c")
    )
    # TJK geçmişinde pist çoğu zaman K:Normal / Ç:Normal / S:Normal
    # biçiminde gelir. Prefix doğrudan pist türünü belirler.
    if text.startswith("k:") or text.startswith("k-") or text == "k":
        return "kum"
    if text.startswith("ç:") or text.startswith("c:") or text.startswith("c-") or text.startswith("cim:") or text == "ç" or text == "c":
        return "cim"
    if text.startswith("s:") or text.startswith("s-") or text == "s":
        return "sentetik"
    if any(x in text for x in ("cim", "grass", "turf")):
        return "cim"
    if any(x in text for x in ("sentetik", "synthetic", "polytrack", "fiber")):
        return "sentetik"
    if any(x in text for x in ("kum", "dirt", "sand")):
        return "kum"
    return ""


def _last_six_surface_data(horse: Dict[str, Any], target_date: Any = None) -> str:
    """Ana tabloda Son 6 Y. rakamlarının pist türünü taşıyan gizli veri."""
    history = horse.get("_history", [])
    if not isinstance(history, list):
        return ""

    # Son 6 Y. ile renkler aynı yarış kayıtlarından gelmeli.
    # Seçili yarış tarihi verilmişse aynı gün/gelecek kayıtları çıkarıyoruz;
    # böylece sonuç sonrası eklenen güncel yarış renkleri bir pozisyon kaydırmıyor.
    if target_date is not None:
        history = _rating_history_before_target(horse, target_date)

    values = []
    for row in history[:6]:
        if not isinstance(row, dict):
            values.append("")
            continue
        surface = _normalize_surface_for_table(
            row.get("surface")
            or row.get("pist")
            or row.get("Pist")
            or row.get("Surface")
            or row.get("trackSurface")
            or row.get("track_surface")
            or row.get("surfaceType")
            or row.get("surface_type")
            or row.get("track")
            or row.get("trackType")
            or row.get("track_type")
            or row.get("zemin")
            or row.get("Zemin")
            or row.get("pistTuru")
            or row.get("pist_turu")
            or row.get("PistTuru")
            or row.get("surfaceName")
            or row.get("surface_name")
            or row.get("pistAdi")
            or row.get("pist_adi")
            or row.get("zeminTuru")
            or row.get("zemin_turu")
            or ""
        )
        values.append(surface)

    return "|".join(values)


def _race_finish_label(horse: Dict[str, Any], race: Dict[str, Any], horse_index: int, target_date: Any = None, target_city_name: str = "") -> str:
    """Analiz edilen yarışın TJK gerçek sonucunu bulur.

    Bu gösterim BİZİM SKOR hesabına dahil değildir. Amaç yalnızca yarış
    sonuçlandıktan sonra At İsmi'nin sonunda (1.), (2.) gibi sonucu göstermektir.
    Bir at aynı gün normalde tek yarış koştuğu için, tarih + atın geçmişindeki
    sonuç kaydı birincil eşleştirmedir; şehir/mesafe gibi alanlar yalnızca
    destekleyici doğrulama olarak kullanılır.
    """
    def _position(value: Any) -> int | None:
        if isinstance(value, dict):
            for k in ("finish", "place", "sira", "S", "result", "sonuc", "position", "finishPosition", "finish_position", "rank"):
                if value.get(k) not in (None, "", "-"):
                    return _position(value.get(k))
            return None
        if value is None:
            return None
        m = re.search(r"\d+", str(value).strip())
        if not m:
            return None
        try:
            n = int(m.group(0))
            return n if n > 0 else None
        except Exception:
            return None

    def _parse_date(value: Any):
        if value in (None, "", "-"):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(text[:10], fmt).date()
            except Exception:
                pass
        return None

    # 1) Program sonucunda doğrudan sonuç varsa kullan.
    for key in ("finish", "place", "sira", "S", "result", "sonuc", "position", "finishPosition", "finish_position", "rank"):
        if horse.get(key) not in (None, "", "-"):
            pos = _position(horse.get(key))
            if pos is not None:
                return f"({pos}.)"

    # 2) Yarışın sonuç haritası varsa at numarasıyla eşleştir.
    no = get_horse_number(horse, horse_index + 1)
    for container in (race.get("results"), race.get("result"), race.get("resultMap"), race.get("result_map"), race.get("finish")):
        if isinstance(container, dict):
            for key in (no, str(no), horse.get("no"), horse.get("numara")):
                if key in container:
                    pos = _position(container.get(key))
                    if pos is not None:
                        return f"({pos}.)"

    target_dt = _parse_date(target_date or race.get("date") or race.get("tarih") or race.get("Tarih"))
    if target_dt is not None:
        same_day = []
        for row in horse.get("_history", []):
            if not isinstance(row, dict):
                continue
            row_dt = _parse_date(row.get("date") or row.get("tarih") or row.get("Tarih"))
            if row_dt != target_dt:
                continue
            pos = _position(row.get("place") or row.get("sira") or row.get("S") or row.get("finish") or row.get("position") or row.get("finishPosition") or row.get("rank"))
            if pos is not None:
                same_day.append((row, pos))

        # En güçlü eşleşme: atın geçmişinde hedef tarihteki sonuç.
        if same_day:
            target_city = str(target_city_name or race.get("city") or race.get("hipodrom") or "").strip().lower()
            target_distance = re.sub(r"\D", "", str(race.get("distance") or race.get("mesafe") or ""))
            target_surface = str(race.get("surface") or race.get("pist") or "").strip().lower()
            for row, pos in same_day:
                row_city = str(row.get("city") or row.get("şehir") or row.get("sehir") or row.get("hipodrom") or "").strip().lower()
                row_distance = re.sub(r"\D", "", str(row.get("distance") or row.get("mesafe") or row.get("msf") or ""))
                row_surface = str(row.get("surface") or row.get("pist") or row.get("zemin") or "").strip().lower()
                city_ok = not target_city or not row_city or target_city in row_city or row_city in target_city
                distance_ok = not target_distance or not row_distance or target_distance == row_distance
                surface_ok = not target_surface or not row_surface or target_surface in row_surface or row_surface in target_surface
                if city_ok and distance_ok and surface_ok:
                    return f"({pos}.)"
            # Aynı gün için tek sonuç varsa diğer alanlar eksik olsa bile kabul et.
            if len(same_day) == 1:
                return f"({same_day[0][1]}.)"

    # Koşmaz/çekildi bilgisi varsa göster.
    status_text = " ".join(str(horse.get(k, "")) for k in ("name", "horse", "horseName", "status", "durum", "note", "aciklama"))
    try:
        status_text += " " + str(get_horse_equipment(horse))
    except Exception:
        pass
    if re.search(r"koşmaz|kosmaz|çekildi|cekildi|start almaz", status_text, re.I):
        return "(Koşmaz)"
    return ""


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
    """EİD için TJK programı + gerçek geçmişten tamamlanan bilgi."""
    best = display_value(horse.get("bestTime"), "")
    if not best:
        return {}

    city = display_value(horse.get("bestCity"), "")
    date = display_value(horse.get("bestDate"), "")
    distance = display_value(horse.get("bestDistance"), "")
    info = display_value(horse.get("bestInfo"), "")

    # Günlük programdaki EİD hücresi yalnızca derece içeriyorsa, aynı
    # dereceyi atın gerçek geçmişinde arayıp hipodrom/tarih/mesafeyi tamamla.
    for row in horse.get("_history", []):
        if not isinstance(row, dict):
            continue
        row_time = display_value(_first_value(row, ["time", "derece", "Derece"]), "")
        if row_time and row_time == best:
            city = city or display_value(_first_value(row, ["city", "şehir", "Sehir"]), "")
            date = date or display_value(_first_value(row, ["date", "tarih", "Tarih"]), "")
            distance = distance or display_value(_first_value(row, ["distance", "msf", "mesafe"]), "")
            info = info or display_value(_first_value(row, ["surface", "pist", "Pist"]), "")
            break

    return {
        "Derece": best,
        "Hipodrom": city or "-",
        "Tarih": date or "-",
        "Mesafe": distance or "-",
        "Bilgi": info or "-",
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
        "condition", "detail", "raceCondition", "race_condition",
    ]), "")



# ============================================================
# REYTİNG — YENİ 9 FAKTÖRLÜ, TARİH-SIZDIRMALI MOTOR
# ============================================================
# REYTİNG yalnızca hedef koşunun tarihinden ÖNCEKİ gerçek TJK geçmişini
# kullanır. Hedef koşunun kendisi, aynı günkü sonuçlar veya gelecekteki
# kayıtlar hiçbir faktöre giremez.
#
# Ana ağırlıklar:
#   Ortak rakip + kilo farkı  %23
#   Kilo uyumu               %17
#   Güncel form              %15
#   Normalize derece         %10
#   Pist / mesafe            %12
#   Sınıf uyumu               %9
#   Tempo                     %6
#   Galop / hazırlık          %6
#   Ham hız                   %2
#
# Her alt puan 0-100 aralığındadır; toplam REYTİNG de 0-100'dür.
# ============================================================

_RATING_WEIGHTS = {
    "Ortak Rakip + Kilo": 0.23,
    "Kilo Uyumu": 0.17,
    "Güncel Form": 0.15,
    "Normalize Derece": 0.10,
    "Pist / Mesafe": 0.12,
    "Sınıf Uyumu": 0.09,
    "Tempo": 0.06,
    "Galop / Hazırlık": 0.06,
    "Ham Hız": 0.02,
}

_RATING_FORM_WEIGHTS = (0.30, 0.22, 0.17, 0.13, 0.10, 0.08)
_RATING_FORM_POINTS = {
    1: 100.0, 2: 90.0, 3: 80.0, 4: 70.0, 5: 60.0,
    6: 50.0, 7: 40.0, 8: 30.0, 9: 20.0,
}
_RATING_FINISH_FACTOR = {
    1: 1.00, 2: 0.90, 3: 0.80, 4: 0.70, 5: 0.60,
}

def _rating_place_number(value: Any) -> int | None:
    if value is None:
        return None
    m = re.search(r"\d+", str(value).strip())
    if not m:
        return None
    try:
        return int(m.group(0))
    except Exception:
        return None

def _rating_finish_points(place: Any) -> float:
    p = _rating_place_number(place)
    if p is None or p <= 0:
        return 10.0
    return _RATING_FORM_POINTS.get(p, 10.0)

def _rating_parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except Exception:
            pass
    return None

def _rating_history_before_target(
    horse: Dict[str, Any],
    target_date: Any = None,
) -> list[Dict[str, Any]]:
    """Sadece tarih < hedef tarih kayıtlarını döndürür."""
    history = horse.get("_history", [])
    if not isinstance(history, list):
        return []

    target_dt = _rating_parse_date(target_date) if target_date is not None else None
    out = []
    for row in history:
        if not isinstance(row, dict):
            continue
        if target_dt is None:
            out.append(row)
            continue
        row_dt = _rating_parse_date(_first_value(row, [
            "date", "tarih", "Tarih", "raceDate", "race_date", "kosuTarihi"
        ]))
        # Tarih çözülemeyen kayıt, veri sızıntısını önlemek için kullanılmaz.
        if row_dt is not None and row_dt < target_dt:
            out.append(row)

    out.sort(
        key=lambda r: _rating_parse_date(_first_value(
            r, ["date", "tarih", "Tarih", "raceDate", "race_date", "kosuTarihi"]
        )) or date.min,
        reverse=True,
    )
    return out

def _rating_surface(value: Any) -> str:
    try:
        return str(_normalize_surface_for_table(value) or "").strip().lower()
    except Exception:
        s = str(value or "").strip().lower()
        s = s.replace("sentetik", "sentetik").replace("synthetic", "sentetik")
        s = s.replace("çim", "çim").replace("grass", "çim")
        s = s.replace("kum", "kum").replace("dirt", "kum")
        return s

def _rating_distance(row: Dict[str, Any]) -> float | None:
    return _number(_first_value(row, [
        "distance", "msf", "mesafe", "Msf"
    ]))

def _rating_weight_value(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None

def _rating_row_weight(row: Dict[str, Any]) -> float | None:
    return _rating_weight_value(_first_value(row, [
        "weight", "kilo", "siklet", "Sıklet"
    ]))

def _rating_target_weight(horse: Dict[str, Any]) -> float | None:
    try:
        return _rating_weight_value(get_horse_weight(horse).split("\n")[0])
    except Exception:
        return _rating_weight_value(_first_value(horse, [
            "siklet", "Sıklet", "weight", "kilo"
        ]))

def _rating_recency_factor(row: Dict[str, Any], target_date: Any) -> float:
    target_dt = _rating_parse_date(target_date)
    row_dt = _rating_parse_date(_first_value(row, [
        "date", "tarih", "Tarih", "raceDate", "race_date", "kosuTarihi"
    ]))
    if target_dt is None or row_dt is None:
        return 0.50
    days = max(0, (target_dt - row_dt).days)
    if days <= 30: return 1.00
    if days <= 60: return 0.90
    if days <= 90: return 0.80
    if days <= 180: return 0.65
    if days <= 365: return 0.50
    return 0.30

def _rating_distance_proximity(history_distance: float | None, target_distance: float | None) -> float:
    if history_distance is None or target_distance is None:
        return 50.0
    diff = abs(float(history_distance) - float(target_distance))
    if diff <= 0.01: return 100.0
    if diff <= 100: return 95.0
    if diff <= 200: return 85.0
    if diff <= 300: return 70.0
    if diff <= 400: return 55.0
    return 35.0

def _rating_weight_similarity(history_weight: float | None, target_weight: float | None) -> float:
    if history_weight is None or target_weight is None:
        return 50.0
    diff = abs(history_weight - target_weight)
    if diff <= 0.01: return 100.0
    if diff <= 1: return 95.0
    if diff <= 2: return 90.0
    if diff <= 3: return 80.0
    if diff <= 4: return 70.0
    if diff <= 5: return 60.0
    if diff <= 6: return 50.0
    return 35.0

def _rating_row_race_key(row: Dict[str, Any]) -> tuple:
    """Aynı yarışta koşmuş atları geçmiş kayıtlarından eşleştirir."""
    dt = _rating_parse_date(_first_value(row, [
        "date", "tarih", "Tarih", "raceDate", "race_date", "kosuTarihi"
    ]))
    city = str(_first_value(row, [
        "city", "şehir", "Sehir", "hipodrom", "track"
    ]) or "").strip().lower()
    dist = _rating_distance(row)
    surface = _rating_surface(_first_value(row, [
        "surface", "pist", "Pist", "trackSurface", "track_surface",
        "surfaceType", "surface_type", "track", "trackType", "track_type"
    ]))
    race_name = str(_first_value(row, [
        "raceName", "race_name", "kosu", "Koşu", "className", "class", "condition"
    ]) or "").strip().lower()
    # Tarih + hipodrom + mesafe + pist temel anahtar.
    # Yarış adı varsa anahtarı güçlendirir, ancak boşsa eşleştirme yine yapılabilir.
    return (
        dt.isoformat() if dt else "",
        re.sub(r"\s+", " ", city),
        round(dist, 1) if dist is not None else "",
        surface,
        re.sub(r"\s+", " ", race_name),
    )

def _rating_shared_race_keys(
    h1: Dict[str, Any],
    h2: Dict[str, Any],
    target_date: Any,
) -> list[tuple[Dict[str, Any], Dict[str, Any]]]:
    a = _rating_history_before_target(h1, target_date)
    b = _rating_history_before_target(h2, target_date)
    # Aynı yarış adı boş olduğunda daha gevşek anahtar da denenir.
    idx = {}
    for row in b:
        k = _rating_row_race_key(row)
        idx.setdefault(k, []).append(row)

    pairs = []
    used = set()
    for row_a in a:
        k = _rating_row_race_key(row_a)
        candidates = idx.get(k, [])
        if not candidates:
            base = k[:4]
            candidates = []
            for kb, rows in idx.items():
                if kb[:4] == base:
                    candidates.extend(rows)
        for row_b in candidates:
            pair_key = (id(row_a), id(row_b))
            if pair_key in used:
                continue
            used.add(pair_key)
            pairs.append((row_a, row_b))
            break
    return pairs

def _rating_common_opponent_score(
    horse: Dict[str, Any],
    horses: List[Dict[str, Any]],
    target_date: Any,
) -> float:
    """Bugünkü alandaki rakiplerle geçmişteki ortak yarışları karşılaştırır."""
    target_no = str(horse.get("_at_id") or horse.get("atId") or id(horse))
    values = []

    for other in horses:
        if not isinstance(other, dict):
            continue
        other_no = str(other.get("_at_id") or other.get("atId") or id(other))
        if other_no == target_no:
            continue

        for own_row, other_row in _rating_shared_race_keys(horse, other, target_date):
            own_p = _rating_finish_points(_first_value(own_row, ["place", "sira", "Sıra", "S"]))
            oth_p = _rating_finish_points(_first_value(other_row, ["place", "sira", "Sıra", "S"]))
            own_w = _rating_row_weight(own_row)
            oth_w = _rating_row_weight(other_row)

            # Daha iyi sıra = pozitif; rakibe göre kilo avantajı = pozitif.
            score = 50.0 + 0.50 * (own_p - oth_p)
            if own_w is not None and oth_w is not None:
                score += 2.5 * (oth_w - own_w)

            score = max(0.0, min(100.0, score))
            values.append((score, _rating_recency_factor(own_row, target_date)))

    if not values:
        return 50.0

    return max(0.0, min(100.0,
        sum(v * w for v, w in values) / sum(w for _, w in values)
    ))

def _rating_field_weight_advantage(
    horse: Dict[str, Any],
    horses: List[Dict[str, Any]],
) -> float:
    own = _rating_target_weight(horse)
    if own is None:
        return 50.0
    others = [
        _rating_target_weight(h)
        for h in horses
        if isinstance(h, dict) and h is not horse
    ]
    others = [x for x in others if x is not None]
    if not others:
        return 50.0
    avg = sum(others) / len(others)
    return max(0.0, min(100.0, 50.0 + (avg - own) * 8.0))

def _rating_historical_weight_fit(
    horse: Dict[str, Any],
    target_date: Any,
) -> float:
    target_weight = _rating_target_weight(horse)
    history = _rating_history_before_target(horse, target_date)
    if target_weight is None or not history:
        return 50.0

    vals = []
    for row in history:
        rw = _rating_row_weight(row)
        if rw is None:
            continue
        sim = _rating_weight_similarity(rw, target_weight) / 100.0
        rec = _rating_recency_factor(row, target_date)
        vals.append((_rating_finish_points(_first_value(
            row, ["place", "sira", "Sıra", "S"]
        )), sim * rec))

    if not vals:
        return 50.0
    return max(0.0, min(100.0, sum(v*w for v,w in vals) / sum(w for _,w in vals)))

def _rating_weight_response(
    horse: Dict[str, Any],
    target_date: Any,
) -> float:
    """En az 3 geçmiş koşu varsa kilonun performansla ilişkisini ölçer."""
    history = _rating_history_before_target(horse, target_date)
    pairs = []
    for row in history[:30]:
        w = _rating_row_weight(row)
        p = _rating_place_number(_first_value(row, ["place", "sira", "Sıra", "S"]))
        if w is not None and p is not None:
            pairs.append((w, _rating_finish_points(p)))
    if len(pairs) < 3:
        return 50.0

    xbar = sum(x for x,_ in pairs) / len(pairs)
    ybar = sum(y for _,y in pairs) / len(pairs)
    den = sum((x-xbar)**2 for x,_ in pairs)
    if den <= 1e-9:
        return 50.0
    slope = sum((x-xbar)*(y-ybar) for x,y in pairs) / den
    # Negatif slope: kilo arttıkça performans düşüyor -> bugünkü kilo daha riskli.
    # Pozitif slope: geçmişte ağır kiloda da iyi performans -> avantaj.
    return max(0.0, min(100.0, 50.0 - slope * 8.0))

def _rating_weight_score(
    horse: Dict[str, Any],
    horses: List[Dict[str, Any]],
    target_date: Any,
) -> float:
    return max(0.0, min(100.0,
        0.40 * _rating_field_weight_advantage(horse, horses)
        + 0.35 * _rating_historical_weight_fit(horse, target_date)
        + 0.25 * _rating_weight_response(horse, target_date)
    ))

def _rating_last_six_form(horse: Dict[str, Any], target_date: Any) -> float:
    history = _rating_history_before_target(horse, target_date)[:6]
    if not history:
        return 50.0
    vals = []
    for row in history:
        p = _rating_place_number(_first_value(row, ["place", "sira", "Sıra", "S"]))
        vals.append(_rating_finish_points(p))
    weights = _RATING_FORM_WEIGHTS[:len(vals)]
    return max(0.0, min(100.0, sum(v*w for v,w in zip(vals, weights)) / sum(weights)))

def _rating_distance_performance(
    horse: Dict[str, Any],
    target_distance: float | None,
    target_surface: str,
    target_date: Any,
) -> float:
    history = _rating_history_before_target(horse, target_date)
    if not history:
        return 50.0

    surface_target = _rating_surface(target_surface)
    vals = []
    for row in history:
        surface = _rating_surface(_first_value(row, [
            "surface", "pist", "Pist", "Surface", "trackSurface", "track_surface"
        ]))
        if not surface_target or surface != surface_target:
            continue
        dist = _rating_distance(row)
        prox = _rating_distance_proximity(dist, target_distance) / 100.0
        rec = _rating_recency_factor(row, target_date)
        vals.append((_rating_finish_points(_first_value(
            row, ["place", "sira", "Sıra", "S"]
        )), prox * rec))

    # Aynı pist deneyimi yoksa cezalandırma yok: nötr.
    if not vals:
        return 50.0
    return max(0.0, min(100.0, sum(v*w for v,w in vals) / sum(w for _,w in vals)))

def _rating_distance_component(
    horse: Dict[str, Any],
    target_distance: float | None,
    target_surface: str,
    target_date: Any,
) -> float:
    """Pist/mesafe = %35 mesafe + %30 pist + %20 benzer kilo + %15 güncellik."""
    history = _rating_history_before_target(horse, target_date)
    if not history:
        return 50.0

    target_weight = _rating_target_weight(horse)
    surface_target = _rating_surface(target_surface)

    distance_vals = []
    surface_vals = []
    weight_vals = []
    recency_vals = []

    for row in history:
        rec = _rating_recency_factor(row, target_date)
        dist = _rating_distance(row)
        rw = _rating_row_weight(row)
        row_surface = _rating_surface(_first_value(row, [
            "surface", "pist", "Pist", "Surface", "trackSurface", "track_surface"
        ]))

        distance_vals.append((_rating_distance_proximity(dist, target_distance), rec))

        if surface_target and row_surface == surface_target:
            surface_vals.append((_rating_finish_points(_first_value(
                row, ["place", "sira", "Sıra", "S"]
            )), rec))

        weight_vals.append((_rating_weight_similarity(rw, target_weight), rec))
        recency_vals.append((rec * 100.0, 1.0))

    def weighted(vals, default=50.0):
        if not vals:
            return default
        return sum(v*w for v,w in vals) / sum(w for _,w in vals)

    m = weighted(distance_vals)
    p = weighted(surface_vals, 50.0)
    k = weighted(weight_vals)
    g = weighted(recency_vals)

    return max(0.0, min(100.0,
        0.35*m + 0.30*p + 0.20*k + 0.15*g
    ))

def _rating_time_seconds(value: Any) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace(",", ".")
    if not s or s == "-":
        return None

    # 2:18.34 / 2.18.34 / 2'18"34
    m = re.search(r"^(\d+)[\.:'](\d{1,2})[\.:](\d{1,2})$", s)
    if m:
        a, b, c = map(int, m.groups())
        return a * 60.0 + b + c / (100.0 if len(m.group(3)) == 2 else 10.0)

    m = re.search(r"^(\d+):(\d{1,2})(?:\.(\d+))?$", s)
    if m:
        a = int(m.group(1)); b = int(m.group(2))
        frac = float("0." + (m.group(3) or "0"))
        return a * 60.0 + b + frac

    return None

def _rating_normalized_degree_scores(
    horses: List[Dict[str, Any]],
    target_distance: float | None,
    target_surface: str,
    target_date: Any,
) -> dict[int, float]:
    """Önceki tüm yarışlardan mesafe/pist eşdeğer hızını çıkarıp 0-100 normalize eder."""
    surface_target = _rating_surface(target_surface)
    pool = []
    own_raw = {}

    for idx, horse in enumerate(horses):
        if not isinstance(horse, dict):
            continue
        hist = _rating_history_before_target(horse, target_date)
        for row in hist:
            dist = _rating_distance(row)
            sec = _rating_time_seconds(_first_value(row, ["time", "derece", "Derece"]))
            if dist is None or sec is None or sec <= 0:
                continue
            # Hedef yüzey varsa aynı yüzey tercih edilir; farklı pistler de
            # normalize hız havuzuna girer, çünkü bu faktör pistten bağımsız
            # ham dereceyi değil normalize edilmiş performansı ölçer.
            prox = _rating_distance_proximity(dist, target_distance) / 100.0
            if prox < 0.55:
                continue
            rec = _rating_recency_factor(row, target_date)
            speed = dist / sec
            pool.append(speed)
            own_raw.setdefault(idx, []).append((speed, prox * rec, dist, sec))

    if not pool:
        return {i: 50.0 for i in range(len(horses))}

    lo = min(pool)
    hi = max(pool)
    if hi <= lo:
        return {i: 50.0 for i in range(len(horses))}

    out = {}
    for idx in range(len(horses)):
        vals = own_raw.get(idx, [])
        if not vals:
            out[idx] = 50.0
            continue
        scores = []
        for speed, w, _, _ in vals:
            score = 100.0 * (speed - lo) / (hi - lo)
            scores.append((score, w))
        out[idx] = max(0.0, min(100.0,
            sum(v*w for v,w in scores) / sum(w for _,w in scores)
        ))
    return out

def _rating_class_group(value: Any) -> str:
    s = str(value or "").strip().lower()
    s = (s.replace("ı", "i").replace("ş", "s").replace("ğ", "g")
           .replace("ü", "u").replace("ö", "o").replace("ç", "c"))
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    m = re.search(r"\b(?:g|grup|group)\s*[- ]?([123])\b", s)
    if m: return f"G{m.group(1)}"
    m = re.search(r"\b(?:acik|açik|açık|a)\s*[- ]?([123])\b", s)
    if m: return f"A{m.group(1)}"
    m = re.search(r"\bkv\s*[- ]?(\d+)\b", s)
    if m: return f"KV{m.group(1)}"
    m = re.search(r"\b(?:h|handikap)\s*[- ]?(\d+)\b", s)
    if m: return f"H{m.group(1)}"
    m = re.search(r"\b(?:s|sartli|sartlı)\s*[- ]?(\d+)\b", s)
    if m: return f"S{m.group(1)}"
    if "maiden" in s:
        return "MAIDEN"
    return ""

_RATING_CLASS_BASE = {
    "G1": 100.0, "A1": 95.0, "G2": 90.0, "A2": 90.0, "G3": 80.0, "A3": 80.0,
    "KV24": 90.0, "KV18": 80.0, "KV9": 70.0, "KV8": 70.0, "KV7": 60.0, "KV6": 60.0,
    "H24": 90.0, "H23": 85.0, "H22": 80.0, "H21": 70.0, "H20": 75.0,
    "H19": 70.0, "H18": 65.0, "H17": 60.0, "H16": 50.0, "H15": 40.0,
    "H14": 30.0, "H13": 20.0,
    "S27": 15.0, "S19": 25.0, "S5": 50.0, "S4": 40.0, "S3": 30.0,
    "S2": 20.0, "S1": 10.0, "MAIDEN": 10.0,
}

def _rating_class_value(row: Dict[str, Any]) -> float | None:
    group = _rating_class_group(_first_value(row, [
        "className", "class", "sinif", "Sınıf", "raceName", "race_name", "kosu", "Koşu", "condition"
    ]))
    base = _RATING_CLASS_BASE.get(group)
    if base is None:
        # H ve KV gibi sınıflar tablo dışında kalırsa mevcut sınıf
        # dönüştürücüsünü kullanmayı dene.
        raw = _first_value(row, [
            "className", "class", "sinif", "Sınıf", "raceName", "race_name", "kosu", "Koşu", "condition"
        ])
        lv = _class_level_from_text(raw)
        if lv is not None:
            base = lv
    if base is None:
        return None
    place = _rating_place_number(_first_value(row, ["place", "sira", "Sıra", "S"]))
    if place is None:
        return base * 0.50
    factor = _RATING_FINISH_FACTOR.get(place, 0.50)
    return base * factor

def _rating_target_class_value(race: Dict[str, Any]) -> float:
    raw = get_race_condition(race)
    group = _rating_class_group(raw)
    if group in _RATING_CLASS_BASE:
        return _RATING_CLASS_BASE[group]
    lv = _class_level_from_text(raw)
    return lv if lv is not None else 50.0

def _rating_class_score(
    horse: Dict[str, Any],
    race: Dict[str, Any],
    target_date: Any,
) -> float:
    target = _rating_target_class_value(race)
    history = _rating_history_before_target(horse, target_date)
    vals = []
    for row in history:
        v = _rating_class_value(row)
        if v is None:
            continue
        rec = _rating_recency_factor(row, target_date)
        # Bugünkü sınıfa yakın geçmiş daha güçlü referans.
        proximity = max(0.25, 1.0 - abs(v-target)/100.0)
        vals.append((v, rec * proximity))
    if not vals:
        return 50.0

    hist = sum(v*w for v,w in vals) / sum(w for _,w in vals)
    # Geçmiş sınıf seviyesi bugünkü seviyeye ne kadar yakınsa o kadar yüksek.
    similarity = max(0.0, 100.0 - abs(hist - target))
    return max(0.0, min(100.0, 0.55*similarity + 0.45*hist))

def _rating_style_value(row: Dict[str, Any]) -> str:
    text = str(_first_value(row, [
        "style", "runningStyle", "running_style", "koşuStili", "kosuStili",
        "stili", "stil", "position", "pozisyon"
    ]) or "").lower()
    if any(x in text for x in ("önde", "onde", "lider", "front")): return "front"
    if any(x in text for x in ("takip", "lideri takip", "stalker")): return "stalker"
    if any(x in text for x in ("orta", "middle")): return "middle"
    if any(x in text for x in ("bekle", "closer", "close", "sprint")): return "closer"
    return ""

def _rating_infer_style(history: list[Dict[str, Any]]) -> str:
    for row in history[:6]:
        s = _rating_style_value(row)
        if s:
            return s
    return ""

def _rating_tempo_score(
    horse: Dict[str, Any],
    horses: List[Dict[str, Any]],
    target_date: Any,
) -> float:
    """Geçmiş koşu stili varsa alanın muhtemel temposuyla uyumunu ölçer."""
    styles = []
    own_style = _rating_infer_style(_rating_history_before_target(horse, target_date))
    for h in horses:
        if not isinstance(h, dict):
            continue
        s = _rating_infer_style(_rating_history_before_target(h, target_date))
        if s:
            styles.append(s)

    # TJK geçmişinde stil alanı yoksa nötr; veri uydurulmaz.
    if not own_style or not styles:
        return 50.0

    front = styles.count("front")
    stalker = styles.count("stalker")
    middle = styles.count("middle")
    closer = styles.count("closer")
    fast_pressure = front + stalker

    if fast_pressure >= max(3, len(styles)*0.45):
        expected = "closer" if closer else "stalker"
    elif fast_pressure <= max(1, len(styles)*0.20):
        expected = "front" if front else "stalker"
    else:
        expected = "stalker"

    matrix = {
        ("front","front"):75, ("front","stalker"):90, ("front","middle"):65, ("front","closer"):45,
        ("stalker","front"):80, ("stalker","stalker"):90, ("stalker","middle"):80, ("stalker","closer"):65,
        ("middle","front"):55, ("middle","stalker"):80, ("middle","middle"):90, ("middle","closer"):80,
        ("closer","front"):95, ("closer","stalker"):90, ("closer","middle"):80, ("closer","closer"):70,
    }
    return float(matrix.get((own_style, expected), 50))

def _rating_gallop_score(horse: Dict[str, Any], target_date: Any) -> float:
    workouts = horse.get("_workouts", [])
    if not isinstance(workouts, list) or not workouts:
        return 50.0

    target_dt = _rating_parse_date(target_date)
    vals = []
    for row in workouts:
        if not isinstance(row, dict):
            continue
        dt = _rating_parse_date(_first_value(row, ["date", "tarih", "Tarih"]))
        if target_dt is not None and (dt is None or dt >= target_dt):
            continue
        # Galopta bulunan en hızlı ölçümü kullan.
        nums = []
        for key in ("1200","1000","800","600","400","m1200","m1000","m800","m600","m400","time1200","time1000","time800","time600","time400"):
            sec = _rating_time_seconds(row.get(key))
            if sec and sec > 0:
                nums.append(sec)
        if not nums:
            continue
        # Mesafe bilinmiyorsa zamanın kendisini diğer galoplarla karşılaştırmak
        # yerine sadece recency + tutarlılık kullanıyoruz.
        rec = _rating_recency_factor(
            {"date": dt.isoformat() if dt else ""}, target_date
        )
        vals.append((min(nums), rec))

    if not vals:
        return 50.0

    vals.sort(key=lambda x: x[0])
    best = vals[0][0]
    worst = vals[-1][0]
    if worst <= best:
        return 75.0

    weighted_avg = sum(v*w for v,w in vals) / sum(w for _,w in vals)
    # Hızlı galop = daha yüksek; farkı sınırlı tut.
    relative = 100.0 - ((weighted_avg - best) / max(0.01, worst-best)) * 50.0
    return max(0.0, min(100.0, relative))

def _rating_raw_speed_score(
    horse: Dict[str, Any],
    horses: List[Dict[str, Any]],
    target_distance: float | None,
    target_surface: str,
    target_date: Any,
) -> float:
    """Ham hız: geçmişteki en iyi normalize edilmiş m/s hızının alan içindeki yeri."""
    def best_speed(h):
        vals = []
        for row in _rating_history_before_target(h, target_date):
            d = _rating_distance(row)
            sec = _rating_time_seconds(_first_value(row, ["time", "derece", "Derece"]))
            if d and sec and sec > 0:
                prox = _rating_distance_proximity(d, target_distance) / 100.0
                if prox >= 0.70:
                    vals.append((d/sec, prox * _rating_recency_factor(row, target_date)))
        if not vals:
            return None
        return max(vals, key=lambda x:x[0])[0]

    all_speeds = [best_speed(h) for h in horses if isinstance(h, dict)]
    all_speeds = [x for x in all_speeds if x is not None]
    own = best_speed(horse)
    if own is None or not all_speeds:
        return 50.0
    lo, hi = min(all_speeds), max(all_speeds)
    if hi <= lo:
        return 50.0
    return max(0.0, min(100.0, 100.0*(own-lo)/(hi-lo)))

def _calculate_rating_for_race(
    horses: List[Dict[str, Any]],
    race: Dict[str, Any],
) -> list[Dict[str, Any]]:
    target_date = race.get("date")
    target_distance = _number(race.get("distance"))
    target_surface = display_value(race.get("surface"), "")
    norm_degree = _rating_normalized_degree_scores(
        horses, target_distance, target_surface, target_date
    )

    results = []
    for idx, horse in enumerate(horses):
        if not isinstance(horse, dict):
            continue

        # KESİN KURAL:
        # Hedef tarihten önce en az 1 gerçek yarış yoksa REYTİNG hesaplanmaz.
        eligible_history = _rating_history_before_target(horse, target_date)
        if not eligible_history:
            continue

        components = {
            "Ortak Rakip + Kilo": _rating_common_opponent_score(horse, horses, target_date),
            "Kilo Uyumu": _rating_weight_score(horse, horses, target_date),
            "Güncel Form": _rating_last_six_form(horse, target_date),
            "Normalize Derece": norm_degree.get(idx, 50.0),
            "Pist / Mesafe": _rating_distance_component(
                horse, target_distance, target_surface, target_date
            ),
            "Sınıf Uyumu": _rating_class_score(horse, race, target_date),
            "Tempo": _rating_tempo_score(horse, horses, target_date),
            "Galop / Hazırlık": _rating_gallop_score(horse, target_date),
            "Ham Hız": _rating_raw_speed_score(
                horse, horses, target_distance, target_surface, target_date
            ),
        }

        score = sum(
            components[key] * _RATING_WEIGHTS[key]
            for key in _RATING_WEIGHTS
        )

        results.append({
            "horse_index": idx,
            "score": round(max(0.0, min(100.0, score)), 2),
            "components": {k: round(v, 2) for k,v in components.items()},
        })

    results.sort(key=lambda x: (-x["score"], x["horse_index"]))
    for rank, item in enumerate(results, 1):
        item["rank"] = rank
        item["label"] = (
            "ÇOK GÜÇLÜ" if item["score"] >= 80 else
            "GÜÇLÜ" if item["score"] >= 70 else
            "ORTA" if item["score"] >= 55 else
            "ZAYIF"
        )
    return results

@st.cache_data(ttl=10800, show_spinner=False)
def calculate_rating_cached(horses: List[Dict[str, Any]], race: Dict[str, Any]):
    """REYTİNG için 180 dk cache; anahtar yarış tarihi/koşu ve gerçek geçmişi içerir."""
    return _calculate_rating_for_race(horses, race)
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
        scores["race_type"] * 0.30
        + scores["class"] * 0.30
        + scores["distance"] * 0.20
        + scores["weight"] * 0.5
        + scores["hp"] * 0.5
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
        confidence = 70.0
    elif sample >= 2:
        confidence = 60.0
    else:
        confidence = 50.0

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


def calculate_guncel_sinif(
    horse: Dict[str, Any],
    target_date: Any,
    target_race: Dict[str, Any],
    max_races: int = 5,
) -> Dict[str, Any]:
    """GÜNCEL SINIF farkını hedef koşu tarihinden önceki yarışlardan hesaplar.

    1) Yalnızca row_date < target_date olan geçmiş yarışlar kullanılır.
    2) Bu geçmiş yarışlardan ağırlıklı GÜNCEL SINIF puanı hesaplanır.
    3) Hedef koşunun sınıf puanı ayrıca hesaplanır.
    4) Sonuç = GÜNCEL SINIF PUANI - HEDEF KOŞU SINIF PUANI.

    Sonuç pozitifse "+5", negatifse "-5" biçiminde gösterilir.
    Tarihi doğrulanamayan geçmiş kayıtları güvenli tarafta kalmak için
    hesaba dahil edilmez; böylece hedef koşunun sonucu geçmişe sızmaz.
    """
    history = horse.get("_history", [])
    if not isinstance(history, list):
        history = []

    target_dt = _rating_parse_date(target_date)
    parsed = []

    for row in history:
        if not isinstance(row, dict):
            continue
        row_dt = _rating_parse_date(_first_value(row, [
            "date", "tarih", "Tarih",
            "raceDate", "race_date", "kosuTarihi"
        ]))
        if target_dt is None or row_dt is None or row_dt >= target_dt:
            continue

        class_text = _history_class_text(row)
        level = _class_level_from_text(class_text)
        if level is None:
            continue
        parsed.append((row_dt, row, level))

    # En yeni geçmiş yarıştan eskiye doğru sırala.
    parsed.sort(key=lambda x: x[0], reverse=True)
    parsed = parsed[:max_races]

    # Hedef tarihten önce sınıf bilgisi taşıyan gerçek yarış yoksa
    # GÜNCEL SINIF hesaplanmaz; yapay 50 puan verilmez.
    if not parsed:
        return {
            "score": None,
            "race_class_score": None,
            "difference": None,
            "display": "—",
            "race_class": get_race_condition(target_race),
            "history_count": 0,
        }

    weights = [1.00, 0.90, 0.80, 0.70, 0.60]
    used = weights[:len(parsed)]
    current_class = sum(item[2] * w for item, w in zip(parsed, used)) / sum(used)
    current_class = round(max(0.0, min(100.0, current_class)), 1)

    # Hedef koşunun sınıf puanı: aynı sınıf eşleştirme sistemi kullanılır.
    race_class_text = get_race_condition(target_race)
    race_class_score = _rating_target_class_value(target_race)

    # Veri bulunamazsa mevcut nötr değer korunur.
    if race_class_score is None:
        race_class_score = 50.0

    difference = round(current_class - float(race_class_score), 1)

    return {
        "score": current_class,
        "race_class_score": round(float(race_class_score), 1),
        "difference": difference,
        "display": f"{difference:+g}",
        "race_class": race_class_text,
        "history_count": len(parsed),
    }


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
    _race_no_for_css = get_race_number(_race, _idx + 1)
    _is_selected_for_css = st.session_state.selected_race == _race_no_for_css
    _bg = "#ff4b4b" if _is_selected_for_css else ("#b77a2b" if _is_dirt else "#239447")
    _race_css.append(
        f'.st-key-race_button_{_race_no_for_css} button'
        f'{{background:{_bg} !important;border-color:{_bg} !important;color:#fff !important;font-weight:800;}}'
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


def _select_race(race_number: int) -> None:
    # Streamlit button callback: seçimi rerun'dan önce session_state'a yazar.
    # Böylece koşu geçişi başka bir state/reset işlemi tarafından ezilmez.
    st.session_state.selected_race = int(race_number)
    st.session_state.selected_horse_no = None
    st.session_state.selected_horse_index = None
    st.session_state.real_analysis_requested = False
    st.session_state.real_analysis_done = False


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

        st.button(
            label,
            key=f"race_button_{race_number}",
            use_container_width=True,
            type=(
                "primary"
                if selected
                else "secondary"
            ),
            on_click=_select_race,
            args=(race_number,),
        )


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
    # Koşu değiştiğinde önceki koşunun seçili atı/gerçek veri ayrıntısı
    # kesinlikle yeni koşuya taşınmayacak.
    st.session_state.selected_horse_no = None
    st.session_state.selected_horse_index = None
    st.session_state["_selected_detail_fetch_key"] = None
    st.session_state["_last_eid_click_token"] = ""
    # Kullanıcı aynı rerun içinde GERÇEK VERİ butonuna bastıysa isteği
    # kesinlikle silme. Eski sürümde bu blok butondan sonra çalıştığı için
    # ilk tıklamada real_analysis_requested tekrar False olabiliyordu.
    if not st.session_state.get("real_analysis_requested", False):
        st.session_state.real_analysis_done = False
    st.session_state["_last_race_signature"] = _current_race_signature

# ============================================================
# KOŞU BAŞLIĞI / İKRAMİYE GÖRSEL YARDIMCILARI
# ============================================================

def _race_value(race: Dict[str, Any], keys: List[str]) -> Any:
    if not isinstance(race, dict):
        return ""
    for key in keys:
        value = race.get(key)
        if value not in (None, ""):
            return value
    meta = race.get("meta")
    if isinstance(meta, dict):
        for key in keys:
            value = meta.get(key)
            if value not in (None, ""):
                return value
    return ""


def _format_prize_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, dict):
        parts = []
        for key in ("1", "2", "3", "4", "5", "first", "second", "third", "fourth", "fifth"):
            if key in value and value[key] not in (None, ""):
                parts.append(str(value[key]).strip())
        return "  ".join(parts) if parts else str(value)
    if isinstance(value, (list, tuple)):
        parts = []
        for item in value:
            if isinstance(item, dict):
                no = item.get("no") or item.get("rank") or item.get("sira") or ""
                amount = item.get("amount") or item.get("value") or item.get("prize") or item.get("ikramiye") or ""
                if amount != "":
                    parts.append(f"{no}.){amount}" if no else str(amount))
            elif item not in (None, ""):
                parts.append(str(item).strip())
        return "  ".join(parts)
    return str(value).strip()


def _race_prize_text(race: Dict[str, Any]) -> str:
    value = _race_value(
        race,
        [
            "prize", "prizes", "ikramiye", "ikramiyeler",
            "prizeText", "prize_text", "prizeInfo", "prize_info",
            "ikramiyeText", "ikramiye_text", "ikramiyeInfo",
        ],
    )
    text = _format_prize_text(value)
    if text:
        return text
    horses_for_prize = race.get("horses") if isinstance(race, dict) else None
    if isinstance(horses_for_prize, list):
        for h in horses_for_prize[:1]:
            if isinstance(h, dict):
                text = _format_prize_text(
                    _first_value(
                        h,
                        ["prize", "prizes", "ikramiye", "ikramiyeler",
                         "prizeText", "prize_text", "ikramiyeText", "ikramiye_text"],
                    )
                )
                if text:
                    return text
    return ""


def _race_prize_lines(race: Dict[str, Any]) -> tuple[str, str, str]:
    """TJK resmi koşu başlığındaki üç ikramiye satırını gerçek veriden çıkarır.

    Kaynak önceliği:
    1) Worker'ın ayrı prize/breeder/owner alanları
    2) Worker'ın meta alanları
    3) Worker'ın meta.raw alanı. Günlük TJK program parser'ı koşu tablosundan
       hemen önceki ham başlığı burada korur; İkramiye / Yetiştirici Primi /
       At Sahibi Primi bölümleri bu metinden doğrudan okunur.

    Veri yoksa "-" gösterilir; tutar uydurulmaz.
    """
    def pick(keys):
        value = _race_value(race, keys)
        if value not in (None, ""):
            return value
        horses = race.get("horses") if isinstance(race, dict) else None
        if isinstance(horses, list) and horses and isinstance(horses[0], dict):
            return _first_value(horses[0], keys)
        return ""

    base_value = pick([
        "prize", "prizes", "ikramiye", "ikramiyeler",
        "prizeText", "prize_text", "prizeInfo", "prize_info",
        "ikramiyeText", "ikramiye_text", "ikramiyeInfo",
    ])
    breeder_value = pick([
        "breederPrize", "breeder_prize", "breederPremium", "breeder_premium",
        "yettiriciPrize", "yetistiriciPrize", "yetistirici_primi",
        "yetiştiriciPrimi", "yetiştiricilikPrimi", "yeticilik_primi",
        "breeder", "breederPrizes",
    ])
    owner_value = pick([
        "ownerPrize", "owner_prize", "ownerPremium", "owner_premium",
        "atSahibiPrimi", "at_sahibi_primi", "atSahibiPrize",
        "ownerPrizes",
    ])

    base_text = _format_prize_text(base_value)
    breeder_text = _format_prize_text(breeder_value)
    owner_text = _format_prize_text(owner_value)

    meta = race.get("meta") if isinstance(race, dict) else None
    raw_sources = []
    if isinstance(meta, dict):
        raw_sources.extend([
            display_value(meta.get("raw"), ""),
            display_value(meta.get("detail"), ""),
            display_value(meta.get("raceName"), ""),
        ])
    raw_sources.extend([
        display_value(race.get("raw"), "") if isinstance(race, dict) else "",
        display_value(race.get("condition"), "") if isinstance(race, dict) else "",
    ])
    raw_detail = re.sub(r"\s+", " ", " ".join(x for x in raw_sources if x)).strip()
    # meta.raw önceki koşunun son kısmını da içerebilir. Son "N. Koşu"
    # başlığından itibaren alarak yalnızca seçili koşunun ikramiye bloğunu kullan.
    _race_marks = list(re.finditer(r"\b\d{1,2}\.\s*Koşu\b", raw_detail, flags=re.I))
    if _race_marks:
        raw_detail = raw_detail[_race_marks[-1].start():]

    # TJK ham başlıkta etiketler bazen "Ikramiye", "Yetistirici Primi"
    # şeklinde noktasız gelebilir. Türkçe karakterli/karaktersiz iki biçimi kabul et.
    combined = " ".join(x for x in (base_text, breeder_text, owner_text, raw_detail) if x)

    if combined:
        # Önce açık etiketli bölümleri ayır.
        label = r"(?:Yetiştirici|Yetistirici|Yetiştiricilik|Yetistiricilik)\s+Primi"
        owner_label = r"At\s*Sahibi\s*Primi"
        base_label = r"(?:İkramiye|Ikramiye)"

        def section_text(pattern, stop_patterns):
            if stop_patterns:
                stop = "|".join(stop_patterns)
                expr = pattern + r"\s*[:\-]?\s*(.*?)(?=\s+(?:" + stop + r")\s*[:\-]?\s*|$)"
            else:
                expr = pattern + r"\s*[:\-]?\s*(.*)$"
            m = re.search(expr, combined, re.I)
            return m.group(1).strip(" ;,-:") if m else ""

        if not breeder_text:
            breeder_text = section_text(label, [owner_label])
        if not owner_text:
            owner_text = section_text(owner_label, [])
        if not base_text:
            base_text = section_text(base_label, [label, owner_label])

    # TJK programında 1-5 tutarları "1.) 545.000 t" biçiminde gelir.
    def amounts(text):
        vals = []
        for m in re.finditer(
            r"(?:\b[1-5]\s*\.?\s*\)?\s*)?(\d{1,3}(?:[\.,]\d{3})+(?:[\.,]\d+)?)\s*(?:TL|t)\b",
            text or "",
            re.I,
        ):
            raw = m.group(1).replace(".", "").replace(",", ".")
            try:
                vals.append(float(raw))
            except Exception:
                pass
        return vals[:5]

    base_amounts = amounts(base_text)
    breeder_amounts = amounts(breeder_text)
    owner_amounts = amounts(owner_text)

    def fmt_amounts(vals):
        if not vals:
            return ""
        def f(v):
            if abs(v - round(v)) < 1e-9:
                return f"{int(round(v)):,}".replace(",", ".") + " t"
            return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " t"
        return "  ".join(f"{i+1}.) {f(v)}" for i, v in enumerate(vals))

    # TJK programında ayrı prim alanları gelmezse, resmi programdaki oranları
    # kullanarak yalnızca ana ikramiye listesinden türet. Ana veri yoksa türetme yok.
    if base_amounts and not breeder_amounts:
        breeder_amounts = [round(v * 0.30) for v in base_amounts]
    if base_amounts and not owner_amounts:
        owner_amounts = [round(v * 0.20) for v in base_amounts]

    return (
        fmt_amounts(base_amounts) or base_text,
        fmt_amounts(breeder_amounts) or breeder_text,
        fmt_amounts(owner_amounts) or owner_text,
    )


def _race_surface_color(surface_value: Any) -> tuple[str, str]:
    normalized = _normalize_surface_for_table(surface_value)
    if normalized == "cim":
        return "#239447", "#ffffff"
    if normalized == "sentetik":
        return "#7b2cbf", "#ffffff"
    return "#b77a2b", "#ffffff"


def _race_id_for_link(race: Dict[str, Any]) -> str:
    value = _race_value(
        race,
        ["raceId", "race_id", "kosuId", "kosu_id", "id", "Id", "raceNoId"],
    )
    return str(value).strip() if value not in (None, "") else ""


# ============================================================
# KOŞU BİLGİLERİ
# ============================================================

race_number = get_race_number(selected_race, 1)
race_time = display_value(selected_race.get("race_time"))
distance = display_value(selected_race.get("distance"))
surface = display_value(selected_race.get("surface"))
condition = get_race_condition(selected_race)

_race_bg, _race_fg = "#ff4b4b", "#ffffff"
_race_id = _race_id_for_link(selected_race)
_date_q = selected_date.strftime("%d/%m/%Y")
_daily_url = (
    "https://www.tjk.org/TR/YarisSever/Info/Page/GunlukYarisProgrami"
    f"?QueryParameter_Tarih={_date_q}&Era=tomorrow&1=1"
)
_race_href = f"{_daily_url}#{_race_id}" if _race_id else _daily_url
_race_title = (
    f"{race_number}. Koşu {race_time}" if race_time != "-" else f"{race_number}. Koşu"
)
_prize_text, _breeder_prize_text, _owner_prize_text = _race_prize_lines(selected_race)
_best_for_header = display_value(selected_race.get("bestTime"), "")
if not _best_for_header:
    _best_for_header = display_value(
        _race_value(selected_race, ["bestTime", "best_time", "eid", "EİD"]),
        "",
    )

_race_first_line = (
    f"<a href='{_html.escape(_race_href, quote=True)}' target='_blank' "
    f"style='color:{_race_fg};text-decoration:none;'>{_html.escape(_race_title)}</a>"
    f"<span class='race-header-detail'>&nbsp;|&nbsp; {_html.escape(condition)}</span>"
    f"<span class='race-header-detail'>&nbsp;|&nbsp; {_html.escape(distance)} {_html.escape(surface)}</span>"
)
if _best_for_header:
    _race_first_line += f"<span class='race-header-detail'>&nbsp;|&nbsp; EİD: {_html.escape(_best_for_header)}</span>"

def _prize_line(label: str, text: str) -> str:
    return (
        f"<div class='race-prize-line'><span class='prize-label'>{label}:</span> {_html.escape(text or '-')}</div>"
    )

_ikramiye_html = _prize_line("İkramiye", _prize_text)
_breeder_html = _prize_line("Yetiştirici Primi", _breeder_prize_text)
_owner_html = _prize_line("At Sahibi Primi", _owner_prize_text)

st.markdown(
    f"""<div class='race-info-compact'>
        <div class='race-title-panel'>
            <div class='race-header-line' style='background:{_race_bg};color:{_race_fg};'>
                {_race_first_line}
            </div>
            <div class='race-prize-row'>
                {_ikramiye_html}
                {_breeder_html}
            </div>
            <div class='race-owner-row'>
                {_owner_html}
            </div>
        </div>
    </div>""",
    unsafe_allow_html=True,
)


# ============================================================
# 180 DAKİKALIK ANALİZ CACHE
# ============================================================
# Aynı tarih + hipodrom + koşu + at geçmişi ile yapılan analiz 180 dakika
# bellekte tutulur. Cache hit olduğunda TJK geçmişi/galop yeniden çekilmez
# ve BİZİM SKOR motoru yeniden çalıştırılmaz.
@st.cache_data(ttl=10800, show_spinner=False)
def calculate_bizim_ranking_cached(horses: List[Dict[str, Any]], race: Dict[str, Any]):
    return calculate_bizim_ranking(horses, race)


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

    # GERÇEK VERİYLE ANALİZ — yalnızca kullanıcı butona bastığında çalışır.
    if st.session_state.get("real_analysis_requested"):
        real_status = st.status(
            f"🔄 TJK gerçek verileri indiriliyor ve işleniyor... 0/{len(horses)} at",
            expanded=True,
        )
        progress = st.progress(0, text=f"0/{len(horses)} at işlendi")

        def _real_progress(done, total, horse_name):
            progress.progress(done / total if total else 1.0, text=f"{done}/{total} at işlendi • {horse_name}")
            real_status.update(
                label=f"🔄 TJK gerçek verileri indiriliyor ve işleniyor... {done}/{total} at",
                state="running",
                expanded=True,
            )

        try:
            horses = enrich_race_horses(
                horses,
                target_date=selected_date,
                target_city=selected_city,
                target_distance=distance,
                target_surface=surface,
                target_class=condition,
                progress_callback=_real_progress,
            )

            # Gerçek veri çekimi bittikten sonra aynı koşunun state'ini
            # mutlaka güncelle. BİZİM SKOR bir sonraki satırda bu yeni veriyi kullanır.
            selected_race["horses"] = horses
            history_count = sum(len(h.get("_history", [])) for h in horses if isinstance(h, dict))
            workout_count = sum(len(h.get("_workouts", [])) for h in horses if isinstance(h, dict))
            missing_atid = sum(1 for h in horses if isinstance(h, dict) and not h.get("_at_id"))
            st.session_state.real_analysis_done = True
            progress.progress(1.0, text=f"{len(horses)}/{len(horses)} at işlendi")
            real_status.update(
                label=f"✅ Gerçek TJK verileri tamamlandı • {len(horses)}/{len(horses)} at • {history_count} koşu • {workout_count} galop",
                state="complete",
                expanded=False,
            )
            st.caption("🧠 Analiz sonucu 180 dakika bellekte tutulacak; aynı tarih/hipodrom/koşu tekrar açılırsa yeniden hesaplanmayacak.")
            if missing_atid:
                st.warning(f"{missing_atid} atta TJK AtId bulunamadı; bu at için gerçek geçmiş sorgulanamaz.")

            # Gerçek veri 0 geldiğinde nedenini kullanıcıya görünür yap.
            if history_count == 0:
                debug_rows = []
                for _h in horses:
                    if not isinstance(_h, dict):
                        continue
                    debug_rows.append({
                        "At": get_horse_name(_h),
                        "AtId": _h.get("_at_id") or _h.get("atId") or "-",
                        "Geçmiş": len(_h.get("_history", []) or []),
                        "Galop": len(_h.get("_workouts", []) or []),
                        "Hata": str(_h.get("_enrichment_error") or "-")[:180],
                    })
                with st.expander("🔧 GERÇEK VERİ TEKNİK DURUMU", expanded=True):
                    st.dataframe(debug_rows, use_container_width=True, hide_index=True)
                    st.caption("Geçmiş 0 ise önce AtId, sonra Worker/TJK doğrudan bağlantısı ve ayrıştırma sonucu kontrol edilir.")
        except Exception as exc:
            real_status.update(
                label="❌ Gerçek TJK veri analizi başarısız",
                state="error",
                expanded=True,
            )
            st.error(f"Gerçek veri analizi sırasında hata: {exc}")
            # Eski/önbellekli skorun yeni analiz sonucu gibi görünmesini engelle.
            horses = [dict(h) for h in horses]
        finally:
            st.session_state.real_analysis_requested = False


    # BİZİM SKOR için hedef koşu tarihi açıkça sabitlenir.
    # Geçmiş hesaplarında yalnızca bu tarihten ÖNCEKİ gün ve daha eski
    # yarışlar kullanılmalıdır; aynı gün ve sonraki kayıtlar kullanılmaz.
    selected_race["date"] = selected_date.isoformat()
    # BİZİM SKOR'a yalnızca gerçek analizde kullanılan güncel horse listesi
    # gönderilir. Böylece eski state/cache sonucu kullanılmaz.
    _ranking_input = horses if isinstance(horses, list) else []
    ranking = calculate_bizim_ranking_cached(_ranking_input, selected_race)

    # Gerçek veri analizi sonrası motorun gerçekten yeni veriyi gördüğünü kontrol et.
    if st.session_state.get("real_analysis_done"):
        _hist_total = sum(len(h.get("_history", [])) for h in horses if isinstance(h, dict))
        _work_total = sum(len(h.get("_workouts", [])) for h in horses if isinstance(h, dict))
        if not ranking:
            st.error(
                f"BİZİM SKOR sonuç üretmedi. Motor girdisi: {len(_ranking_input)} at. "
                f"Model: {_BIZIM_MODEL_PATH.name}. "
                "Bu durumda artık veri çekimi değil, motor girdisinin yapısı kontrol edilmelidir."
            )
            # Boş sonuç oluştuğunda sessizce devam etmek yerine gerçek giriş
            # yapısını göster; böylece hata doğrudan teşhis edilebilir.
            with st.expander("🔧 BİZİM SKOR GİRİŞ KONTROLÜ", expanded=True):
                st.write({
                    "horse_count": len(_ranking_input),
                    "horse_type": type(_ranking_input).__name__,
                    "race_type": type(selected_race).__name__,
                    "race_date": selected_race.get("date"),
                    "model_file": str(_BIZIM_MODEL_PATH),
                    "model_function": getattr(calculate_bizim_ranking, "__module__", "-"),
                })
                if _ranking_input:
                    st.write({
                        "first_horse_type": type(_ranking_input[0]).__name__,
                        "first_horse_keys": list(_ranking_input[0].keys())[:30]
                        if isinstance(_ranking_input[0], dict) else [],
                        "first_history_count": len(_ranking_input[0].get("_history", []))
                        if isinstance(_ranking_input[0], dict) else 0,
                    })
        elif _hist_total == 0:
            st.warning("Gerçek analiz tamamlandı fakat TJK koşu geçmişi 0 geldi. Worker /api/tjk/horse yanıtı kontrol edilmeli.")

    # BİZİM SKOR ile REYTİNG birbirinden tamamen ayrıdır.
    # REYTİNG kendi 9 faktörlü motoruyla, yalnızca hedef tarihten önceki
    # gerçek geçmişi kullanarak hesaplanır.
    rating_results = calculate_rating_cached(_ranking_input, selected_race)
    rating_by_index = {item["horse_index"]: item for item in rating_results}

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
            {"rank": "-", "score": None, "label": "-", "components": {}},
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
        # GÜNCEL SINIF gerçek TJK geçmişindeki son yarışların sınıf seviyesinden hesaplanır.
        current_class_result = calculate_guncel_sinif(horse, selected_date, selected_race)
        current_class = current_class_result["display"]
        # REYTİNG ayrı 9 faktörlü motorun sonucudur.
        rating_result = rating_by_index.get(horse_index, {})
        rating_score = rating_result.get("score", "—")

        table_rows.append({
            "_horse_index": horse_index,
            "_horse_no": int(get_horse_number(horse, horse_index + 1)),
            "_rank": int(r["rank"]) if str(r["rank"]).isdigit() else 999999,
            # No = TJK'nın gerçek programdaki AT NUMARASI.
            # Analiz sırası ile at numarasını birbirine karıştırma.
            "No": int(get_horse_number(horse, horse_index + 1)),
            "At İsmi": "\n".join(
                [x for x in (
                    get_horse_name(horse),
                    get_horse_equipment(horse),
                ) if x]
            ),
            "_race_finish": _race_finish_label(horse, selected_race, horse_index, target_date=selected_date, target_city_name=selected_city),
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
            "BİZİM SKOR": (
                round(float(r["score"]), 2)
                if r.get("score") is not None else "—"
            ),
            "REYTİNG": rating_score,
            "GÜNCEL SINIF": current_class,
            "SON GALOP": workout_display(horse),
            "SON KOŞU": last_race_display(horse),
            "BU YIL KAZANÇ": _format_tl(year_earnings(horse, target_year)),
            "TOPLAM KAZANÇ": _format_tl(total_earnings(horse)),
            "Sahip": owner or "-",
            "Antrenör": trainer or "-",
        })

    # KRİTİK: Ana tablo sırası TJK bülteninden gelen horses listesidir.
    # At numarasına, skora veya analiz rank'ına göre yeniden sıralama YOK.
    # _horse_index bülten sırasını temsil eder.
    table_rows.sort(key=lambda row: int(row.get("_horse_index", 999999)))

    df = pd.DataFrame(table_rows)
    display_columns = [
        "No", "At İsmi", "Yaş", "Orijin (Baba-Anne)", "Kilo", "Jokey",
        "Sahip / Antrenör", "St", "HP", "Son 6 Y.", "KGS", "s20", "EİD", "Gny", "AGF",
        "BİZİM SKOR", "REYTİNG", "GÜNCEL SINIF",
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
    df_grid["_race_finish"] = df["_race_finish"].values
    df_grid["_horse_index"] = df["_horse_index"].values
    df_grid["_last_surface"] = [
        str((((horses[int(hidx)].get("_last_race") or {}).get("surface")) or ((horses[int(hidx)].get("_last_race") or {}).get("pist")) or ""))
        if str(hidx).strip().lstrip("-").isdigit() and 0 <= int(hidx) < len(horses) and isinstance(horses[int(hidx)], dict) else ""
        for hidx in df["_horse_index"].tolist()
    ]
    # SON KOŞU bilgi balonu için gerçek geçmiş kaydının ayrıntılarını gizli alanlara taşı.
    def _last_race_meta_for_table(h):
        row = h.get("_last_race") if isinstance(h, dict) else None
        if not isinstance(row, dict):
            return ("", "", "", "", "", "", "", "", "", "", "")
        return (
            display_value(_first_value(row, ["date", "tarih", "Tarih"]), ""),
            display_value(_first_value(row, ["city", "şehir", "Sehir"]), ""),
            display_value(_first_value(row, ["distance", "msf", "mesafe"]), ""),
            display_value(_first_value(row, ["surface", "pist", "Pist"]), ""),
            display_value(_first_value(row, ["place", "sira", "S"]), ""),
            display_value(_first_value(row, ["weight", "kilo", "siklet"]), ""),
            display_value(_first_value(row, ["jockey", "jokey"]), ""),
            display_value(_first_value(row, ["hp", "HP"]), ""),
            display_value(_first_value(row, ["raceName", "race_name", "kosu"]), ""),
            display_value(_first_value(row, ["className", "class", "sinif"]), ""),
            display_value(_first_value(row, ["prize", "ikramiye", "Ikramiye"]), ""),
        )

    _last_meta = [
        _last_race_meta_for_table(horses[int(hidx)])
        if str(hidx).strip().lstrip("-").isdigit() and 0 <= int(hidx) < len(horses) and isinstance(horses[int(hidx)], dict)
        else ("", "", "", "", "", "", "", "", "", "", "")
        for hidx in df["_horse_index"].tolist()
    ]
    df_grid["_last_date"] = [x[0] for x in _last_meta]
    df_grid["_last_city"] = [x[1] for x in _last_meta]
    df_grid["_last_distance"] = [x[2] for x in _last_meta]
    # _last_surface zaten yukarıda kullanılıyor; aynı gerçek değeri burada da koruyoruz.
    df_grid["_last_place"] = [x[4] for x in _last_meta]
    df_grid["_last_weight"] = [x[5] for x in _last_meta]
    df_grid["_last_jockey"] = [x[6] for x in _last_meta]
    df_grid["_last_hp"] = [x[7] for x in _last_meta]
    df_grid["_last_race_name"] = [x[8] for x in _last_meta]
    df_grid["_last_class"] = [x[9] for x in _last_meta]
    df_grid["_last_prize"] = [x[10] for x in _last_meta]

    df_grid["_form_surfaces"] = [
        _last_six_surface_data(horses[int(hidx)], selected_date)
        if str(hidx).strip().lstrip("-").isdigit() and 0 <= int(hidx) < len(horses) and isinstance(horses[int(hidx)], dict) else ""
        for hidx in df["_horse_index"].tolist()
    ]

    def _js_safe(v):
        return str(v if v is not None else "").replace("\\", "\\\\").replace("'", "\\'")

    cell_style_js = JsCode("""
    function(params) {
        const idx = params.data && params.data._horse_index;
        const selected = window.__ri_selected_horse_index;
        const base = '#e8e8e8';
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

    st.markdown("""
    <style>
    .ag-theme-streamlit .ag-cell.ri-eid-cell { overflow: visible !important; }
    .ag-theme-streamlit .ag-cell.ri-last-race-cell { overflow: visible !important; }
    .ag-theme-streamlit .ag-root-wrapper,
    .ag-theme-streamlit .ag-root,
    .ag-theme-streamlit .ag-body-viewport,
    .ag-theme-streamlit .ag-center-cols-viewport,
    .ag-theme-streamlit .ag-center-cols-container,
    .ag-theme-streamlit .ag-pinned-left-cols-container {
        background: #e8e8e6 !important;
    }
    .ag-theme-streamlit .ag-row,
    .ag-theme-streamlit .ag-row-even {
        background: #e8e8e6 !important;
    }
    .ag-theme-streamlit .ag-row-odd {
        background: #f4f4f2 !important;
    }
    .ag-theme-streamlit .ag-row .ag-cell {
        background: inherit !important;
        vertical-align: middle !important;
    }
    .ag-theme-streamlit .ag-row .ag-cell.ri-left-centered-cell {
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        text-align: left !important;
        overflow: hidden !important;
    }
    .ag-theme-streamlit .ag-pinned-left-cols-container .ag-row .ag-cell {
        background: inherit !important;
    }
    .ag-theme-streamlit .ag-tooltip { display:none !important; }
    </style>
    """, unsafe_allow_html=True)

    # AG Grid 29+ / streamlit-aggrid: direct HTML string returns may be rendered
    # as literal text. Use class-based cell renderers that create real DOM nodes.
    horse_name_renderer = JsCode(r"""
    class HorseNameRenderer {
        init(params) {
            const root = document.createElement('div');
            root.style.width = '100%';
            root.style.height = '100%';
            root.style.display = 'flex';
            root.style.flexDirection = 'column';
            root.style.alignItems = 'flex-start';
            root.style.justifyContent = 'center';
            root.style.textAlign = 'left';
            root.style.overflow = 'hidden';
            root.style.lineHeight = '1.08';
            root.style.boxSizing = 'border-box';

            const parts = String(params.value ?? '').split(/\r?\n/).filter(x => x !== '');
            const nameLine = document.createElement('div');
            nameLine.style.display = 'flex';
            nameLine.style.alignItems = 'baseline';
            nameLine.style.width = '100%';
            nameLine.style.minWidth = '0';
            nameLine.style.overflow = 'hidden';
            nameLine.style.whiteSpace = 'nowrap';

            const base = document.createElement('span');
            base.textContent = parts.length ? parts[0] : '';
            base.style.color = '#d40000';
            base.style.fontWeight = '900';
            base.style.fontSize = '13px';
            base.style.whiteSpace = 'nowrap';
            base.style.overflow = 'hidden';
            base.style.textOverflow = 'clip';
            nameLine.appendChild(base);

            const result = String((params.data && params.data._race_finish) || '').trim();
            if (result) {
                const wrap = document.createElement('span');
                wrap.style.marginLeft = '4px';
                wrap.style.fontSize = '12px';
                wrap.style.fontWeight = '950';
                wrap.style.whiteSpace = 'nowrap';
                wrap.style.flex = '0 0 auto';
                const m = result.match(/^\((.*?)\)$/);
                if (m) {
                    const l = document.createElement('span'); l.textContent = '('; l.style.color = '#1565c0';
                    const v = document.createElement('span'); v.textContent = m[1]; v.style.color = '#126b2f'; v.style.fontWeight = '950';
                    const rr = document.createElement('span'); rr.textContent = ')'; rr.style.color = '#1565c0';
                    wrap.appendChild(l); wrap.appendChild(v); wrap.appendChild(rr);
                } else {
                    wrap.textContent = result;
                    wrap.style.color = '#126b2f';
                }
                nameLine.appendChild(wrap);
            }
            root.appendChild(nameLine);

            for (let i = 1; i < parts.length; i++) {
                const span = document.createElement('span');
                span.textContent = parts[i];
                span.style.color = '#f1c40f';
                span.style.fontWeight = '900';
                span.style.whiteSpace = 'nowrap';
                span.style.maxWidth = '100%';
                span.style.overflow = 'hidden';
                span.style.textOverflow = 'clip';
                span.style.display = 'block';
                span.style.fontSize = '12px';
                root.appendChild(span);
            }
            this.eGui = root;
        }
        refresh(params) { return false; }
        getGui() { return this.eGui; }
    }
    """)

    origin_renderer = JsCode(r"""
    class OriginRenderer {
        init(params) {
            const root = document.createElement('div');
            root.style.width = '100%';
            root.style.height = '100%';
            root.style.display = 'flex';
            root.style.flexDirection = 'column';
            root.style.alignItems = 'flex-start';
            root.style.justifyContent = 'center';
            root.style.textAlign = 'left';
            root.style.overflow = 'hidden';
            root.style.lineHeight = '1.05';

            const parts = String(params.value ?? '').split(/\r?\n/).filter(x => x !== '');
            parts.forEach((part, i) => {
                const span = document.createElement('span');
                span.textContent = part;
                span.style.whiteSpace = 'nowrap';
                span.style.maxWidth = '100%';
                span.style.overflow = 'hidden';
                span.style.textOverflow = 'clip';
                span.style.display = 'block';
                span.style.fontSize = '13px';
                span.style.fontWeight = i === 0 ? '800' : '700';
                span.style.color = i === 0 ? '#1565c0' : '#800020';
                root.appendChild(span);
            });

            this.eGui = root;
            const fit = () => root.querySelectorAll('span').forEach(span => {
                let size = 13;
                span.style.fontSize = size + 'px';
                while (size > 8 && span.scrollWidth > root.clientWidth) {
                    size -= 0.5;
                    span.style.fontSize = size + 'px';
                }
            });
            requestAnimationFrame(fit);
        }
        refresh(params) { return false; }
        getGui() { return this.eGui; }
    }
    """)

    jockey_renderer = JsCode(r"""
    class JockeyRenderer {
        init(params) {
            const root = document.createElement('div');
            root.style.width = '100%';
            root.style.height = '100%';
            root.style.display = 'flex';
            root.style.flexDirection = 'column';
            root.style.alignItems = 'flex-start';
            root.style.justifyContent = 'center';
            root.style.textAlign = 'left';
            root.style.overflow = 'hidden';
            root.style.lineHeight = '1.08';
            const parts = String(params.value ?? '').split(/\r?\n/);
            parts.forEach((part, i) => {
                if (i > 0) root.appendChild(document.createElement('br'));
                const span = document.createElement('span');
                span.textContent = part;
                span.style.color = '#138a36';
                span.style.fontWeight = '900';
                span.style.whiteSpace = 'nowrap';
                span.style.maxWidth = '100%';
                span.style.overflow = 'hidden';
                span.style.display = 'block';
                span.style.fontSize = '13px';
                root.appendChild(span);
            });
            this.eGui = root;
            requestAnimationFrame(() => {
                root.querySelectorAll('span').forEach(span => {
                    let size = 13;
                    span.style.fontSize = size + 'px';
                    while (size > 8 && span.scrollWidth > root.clientWidth) {
                        size -= 0.5;
                        span.style.fontSize = size + 'px';
                    }
                });
            });
        }
        refresh(params) { return false; }
        getGui() { return this.eGui; }
    }
    """)

    owner_trainer_renderer = JsCode(r"""
    class OwnerTrainerRenderer {
        init(params) {
            const root = document.createElement('div');
            root.style.width = '100%';
            root.style.height = '100%';
            root.style.display = 'flex';
            root.style.flexDirection = 'column';
            root.style.alignItems = 'flex-start';
            root.style.justifyContent = 'center';
            root.style.textAlign = 'left';
            root.style.overflow = 'hidden';
            root.style.lineHeight = '1.05';

            const parts = String(params.value ?? '').split(/\r?\n/).filter(x => x !== '');
            parts.forEach((part, i) => {
                const span = document.createElement('span');
                span.textContent = part;
                span.style.whiteSpace = 'nowrap';
                span.style.maxWidth = '100%';
                span.style.overflow = 'hidden';
                span.style.textOverflow = 'clip';
                span.style.display = 'block';
                span.style.fontSize = '13px';
                span.style.fontWeight = '800';
                span.style.color = i === 0 ? '#1565c0' : '#d40000';
                root.appendChild(span);
            });

            this.eGui = root;
            const fit = () => root.querySelectorAll('span').forEach(span => {
                let size = 13;
                span.style.fontSize = size + 'px';
                while (size > 8 && span.scrollWidth > root.clientWidth) {
                    size -= 0.5;
                    span.style.fontSize = size + 'px';
                }
            });
            requestAnimationFrame(fit);
        }
        refresh(params) { return false; }
        getGui() { return this.eGui; }
    }
    """)

    compact_black_renderer = JsCode(r"""
    class CompactBlackRenderer {
        init(params) {
            const span = document.createElement('span');
            span.textContent = String(params.value ?? '');
            span.style.display = 'block';
            span.style.width = '100%';
            span.style.overflow = 'hidden';
            span.style.whiteSpace = 'nowrap';
            span.style.textOverflow = 'clip';
            span.style.textAlign = 'left';
            span.style.fontWeight = '900';
            span.style.fontSize = '13px';
            this.eGui = span;
            requestAnimationFrame(() => {
                let size = 13;
                while (size > 8 && span.scrollWidth > span.clientWidth) {
                    size -= 0.5;
                    span.style.fontSize = size + 'px';
                }
            });
        }
        refresh(params) { return false; }
        getGui() { return this.eGui; }
    }
    """)

    hp_renderer = JsCode(r"""
    class HpRenderer {
        init(params) {
            const span = document.createElement('span');
            span.textContent = String(params.value ?? '');
            span.style.display = 'block';
            span.style.width = '100%';
            span.style.overflow = 'hidden';
            span.style.whiteSpace = 'nowrap';
            span.style.textOverflow = 'clip';
            span.style.textAlign = 'left';
            span.style.fontWeight = '900';
            span.style.fontSize = '13px';
            span.style.color = '#d40000';
            this.eGui = span;
            requestAnimationFrame(() => {
                let size = 13;
                while (size > 8 && span.scrollWidth > span.clientWidth) {
                    size -= 0.5;
                    span.style.fontSize = size + 'px';
                }
            });
        }
        refresh(params) { return false; }
        getGui() { return this.eGui; }
    }
    """)

    kgs_renderer = JsCode(r"""
    class KgsRenderer {
        init(params) {
            const span = document.createElement('span');
            span.textContent = String(params.value ?? '');
            span.style.display = 'block';
            span.style.width = '100%';
            span.style.overflow = 'hidden';
            span.style.whiteSpace = 'nowrap';
            span.style.textOverflow = 'clip';
            span.style.textAlign = 'left';
            span.style.fontWeight = '900';
            span.style.fontSize = '13px';
            span.style.color = '#e67e00';
            this.eGui = span;
            requestAnimationFrame(() => {
                let size = 13;
                while (size > 8 && span.scrollWidth > span.clientWidth) {
                    size -= 0.5;
                    span.style.fontSize = size + 'px';
                }
            });
        }
        refresh(params) { return false; }
        getGui() { return this.eGui; }
    }
    """)

    weight_renderer = JsCode(r"""
    class WeightRenderer {
        init(params) {
            const root = document.createElement('div');
            root.style.width = '100%';
            root.style.height = '100%';
            root.style.display = 'flex';
            root.style.flexDirection = 'column';
            root.style.alignItems = 'flex-start';
            root.style.justifyContent = 'center';
            root.style.textAlign = 'left';
            root.style.overflow = 'hidden';
            root.style.lineHeight = '1.0';

            const v = String(params.value ?? '').trim();
            const m = v.match(/^(.*?)(?:\s*(\+\s*\d+(?:[.,]\d+)?))\s*$/);

            const base = document.createElement('span');
            base.textContent = m ? m[1].trim() : v;
            base.style.color = '#000000';
            base.style.fontWeight = '900';
            base.style.fontSize = '13px';
            base.style.whiteSpace = 'nowrap';
            base.style.overflow = 'hidden';
            base.style.textOverflow = 'clip';
            base.style.maxWidth = '100%';
            root.appendChild(base);

            if (m) {
                const extra = document.createElement('span');
                extra.textContent = m[2].replace(/\s+/g, '');
                extra.style.color = '#d40000';
                extra.style.fontWeight = '400';
                extra.style.fontSize = '10px';
                extra.style.whiteSpace = 'nowrap';
                extra.style.maxWidth = '100%';
                extra.style.overflow = 'hidden';
                extra.style.textOverflow = 'clip';
                root.appendChild(extra);
            }

            this.eGui = root;
            requestAnimationFrame(() => {
                let size = 13;
                while (size > 8 && base.scrollWidth > root.clientWidth) {
                    size -= 0.5;
                    base.style.fontSize = size + 'px';
                }
                if (m) {
                    let extraSize = 10;
                    const extra = root.children[1];
                    while (extraSize > 8 && extra.scrollWidth > root.clientWidth) {
                        extraSize -= 0.5;
                        extra.style.fontSize = extraSize + 'px';
                    }
                }
            });
        }
        refresh(params) { return false; }
        getGui() { return this.eGui; }
    }
    """)

    eid_renderer = JsCode(r"""
    class EidRenderer {
        init(params) {
            const span = document.createElement('span');
            const degree = String(params.value ?? '').trim();
            const city = String((params.data && params.data._best_city) || '').trim();
            const date = String((params.data && params.data._best_date) || '').trim();
            const distance = String((params.data && params.data._best_distance) || '').trim();
            const info = String((params.data && params.data._best_info) || '').trim();

            span.textContent = degree;
            span.style.color = '#d40000';
            span.style.fontWeight = '900';
            span.style.cursor = 'help';
            span.style.position = 'relative';
            span.style.display = 'inline-block';

            let message = '';
            if (city || date) {
                const hipodrom = /hipodrom/i.test(city) ? city : (city ? city + ' Hipodromu' : 'TJK Hipodromu');
                message = 'Bu derece ' + hipodrom + "'nda " + (date || 'belirtilen tarihte') + ' yapılmıştır.';
            } else if (degree) {
                message = 'En İyi Derece: ' + degree;
            }
            if (distance) message += '\nMesafe: ' + distance;
            if (info) message += '\n' + info;

            span.addEventListener('mouseenter', function() {
                if (!message) return;
                if (window.__ri_remove_eid_tooltip) window.__ri_remove_eid_tooltip();

                const tooltip = document.createElement('div');
                tooltip.textContent = message;
                tooltip.style.position = 'fixed';
                tooltip.style.zIndex = '2147483647';
                tooltip.style.width = '250px';
                tooltip.style.maxWidth = '300px';
                tooltip.style.padding = '10px';
                tooltip.style.background = '#ffffff';
                tooltip.style.color = '#ff0000';
                tooltip.style.border = '1px solid #ff0000';
                tooltip.style.borderRadius = '6px';
                tooltip.style.boxShadow = '0 4px 10px rgba(0,0,0,0.25)';
                tooltip.style.textAlign = 'center';
                tooltip.style.whiteSpace = 'pre-line';
                tooltip.style.fontSize = '14px';
                tooltip.style.fontWeight = '600';
                tooltip.style.lineHeight = '1.35';
                tooltip.style.pointerEvents = 'none';

                document.body.appendChild(tooltip);
                window.__ri_eid_tooltip = tooltip;

                const r = span.getBoundingClientRect();
                const tw = tooltip.offsetWidth;
                const th = tooltip.offsetHeight;
                let left = r.left + (r.width / 2) - (tw / 2);
                let top = r.top - th - 10;
                left = Math.max(8, Math.min(left, window.innerWidth - tw - 8));
                if (top < 8) top = r.bottom + 10;
                tooltip.style.left = left + 'px';
                tooltip.style.top = top + 'px';
            });

            span.addEventListener('mouseleave', function() {
                if (window.__ri_remove_eid_tooltip) window.__ri_remove_eid_tooltip();
            });

            this.eGui = span;
        }
        getGui() { return this.eGui; }
    }
    """)

    start_renderer = JsCode(r"""
    class StartRenderer {
        init(params) {
            const root = document.createElement('div');
            root.style.width = '100%';
            root.style.height = '100%';
            root.style.display = 'flex';
            root.style.flexDirection = 'column';
            root.style.alignItems = 'center';
            root.style.justifyContent = 'center';
            root.style.textAlign = 'center';
            root.style.lineHeight = '1.05';
            root.style.whiteSpace = 'normal';
            const raw = String(params.value ?? '').trim();
            const m = raw.match(/^\s*(\d+)\s*(?:[-–—:]?\s*)?(.*)$/);
            const number = document.createElement('div');
            number.textContent = m ? m[1] : raw;
            number.style.color = '#000000';
            number.style.fontWeight = '900';
            number.style.fontSize = '13px';
            root.appendChild(number);
            const detail = document.createElement('div');
            const rest = m ? m[2].trim() : '';
            const tokens = rest.split(/(\bDS\b|\bTS\b)/gi);
            tokens.forEach(token => {
                if (!token) return;
                const span = document.createElement('span');
                span.textContent = token;
                if (/^(DS|TS)$/i.test(token.trim())) {
                    span.style.color = '#d40000';
                    span.style.fontWeight = '500';
                } else {
                    span.style.color = '#000000';
                    span.style.fontWeight = '400';
                }
                detail.appendChild(span);
            });
            detail.style.fontSize = '9px';
            detail.style.fontWeight = '400';
            detail.style.color = '#000000';
            root.appendChild(detail);
            this.eGui = root;
        }
        getGui() { return this.eGui; }
    }
    """)

    form_renderer = JsCode(r"""
    class FormRenderer {
        init(params) {
            const root = document.createElement('div');
            root.style.whiteSpace = 'nowrap';
            root.style.fontWeight = '900';
            const text = String(params.value ?? '');
            const surfaces = String((params.data && params.data._form_surfaces) || '').split('|');
            const chars = Array.from(text);
            chars.forEach((ch, i) => {
                const span = document.createElement('span');
                span.textContent = ch;
                span.style.fontWeight = '900';
                const rawSurf = String(surfaces[i] || '').trim();
                const surf = rawSurf.toLowerCase()
                    .replace(/ı/g,'i').replace(/ş/g,'s').replace(/ğ/g,'g')
                    .replace(/ü/g,'u').replace(/ö/g,'o').replace(/ç/g,'c');
                if (/^(c|cim|grass|turf)(?:[:\s-]|$)/.test(surf) || surf.includes('cim') || surf.includes('grass') || surf.includes('turf')) span.style.color = '#138a36';
                else if (/^(k|kum|dirt)(?:[:\s-]|$)/.test(surf) || surf.includes('kum') || surf.includes('dirt')) span.style.color = '#8b5a2b';
                else if (/^(s|sentetik|synthetic)(?:[:\s-]|$)/.test(surf) || surf.includes('sentetik') || surf.includes('synthetic') || surf.includes('polytrack') || surf.includes('fiber')) span.style.color = '#7b2cbf';
                else span.style.color = '#000000';
                root.appendChild(span);
                if (i < chars.length - 1) {
                    const space = document.createElement('span');
                    space.textContent = ' ';
                    root.appendChild(space);
                }
            });
            this.eGui = root;
        }
        getGui() { return this.eGui; }
    }
    """)

    agf_renderer = JsCode(r"""
    class AgfRenderer {
        init(params) {
            const span = document.createElement('span');
            span.textContent = String(params.value ?? '');
            span.style.display = 'block';
            span.style.width = '100%';
            span.style.overflow = 'hidden';
            span.style.whiteSpace = 'nowrap';
            span.style.textOverflow = 'clip';
            span.style.textAlign = 'left';
            span.style.color = '#138a36';
            span.style.fontWeight = '900';
            span.style.fontSize = '13px';
            this.eGui = span;
            requestAnimationFrame(() => {
                let size = 13;
                while (size > 8 && span.scrollWidth > span.clientWidth) {
                    size -= 0.5;
                    span.style.fontSize = size + 'px';
                }
            });
        }
        refresh(params) { return false; }
        getGui() { return this.eGui; }
    }
    """)

    workout_renderer = JsCode(r"""
    class WorkoutRenderer {
        init(params) {
            const root = document.createElement('span');
            root.style.display = 'block';
            root.style.width = '100%';
            root.style.overflow = 'hidden';
            root.style.whiteSpace = 'nowrap';
            root.style.textAlign = 'left';
            root.style.fontWeight = '900';
            root.style.color = '#8b5a2b';
            root.style.fontSize = '13px';
            const text = String(params.value ?? '');
            const m = text.match(/^(.*?)(\s*\(600\))$/i);
            if (m) {
                const main = document.createElement('span');
                main.textContent = m[1].trim();
                main.style.fontWeight = '900';
                root.appendChild(main);
                const suffix = document.createElement('span');
                suffix.textContent = m[2];
                suffix.style.fontSize = '10px';
                suffix.style.fontWeight = '700';
                suffix.style.marginLeft = '2px';
                root.appendChild(suffix);
            } else {
                root.textContent = text;
            }
            this.eGui = root;
            requestAnimationFrame(() => {
                let size = 13;
                while (size > 8 && root.scrollWidth > root.clientWidth) {
                    size -= 0.5;
                    root.style.fontSize = size + 'px';
                }
            });
        }
        refresh(params) { return false; }
        getGui() { return this.eGui; }
    }
    """)

    def _best_meta_for_table(h):
        best = display_value(h.get("bestTime"), "")
        city = display_value(h.get("bestCity"), "")
        date = display_value(h.get("bestDate"), "")
        distance = display_value(h.get("bestDistance"), "")
        info = display_value(h.get("bestInfo"), "")
        if best:
            for row in h.get("_history", []):
                if not isinstance(row, dict):
                    continue
                row_time = display_value(_first_value(row, ["time", "derece", "Derece"]), "")
                if row_time == best:
                    city = city or display_value(_first_value(row, ["city", "şehir", "Sehir"]), "")
                    date = date or display_value(_first_value(row, ["date", "tarih", "Tarih"]), "")
                    distance = distance or display_value(_first_value(row, ["distance", "msf", "mesafe"]), "")
                    info = info or display_value(_first_value(row, ["surface", "pist", "Pist"]), "")
                    break
        return city, date, distance, info

    _best_meta = [
        _best_meta_for_table(horses[int(hidx)])
        if str(hidx).strip().lstrip("-").isdigit() and 0 <= int(hidx) < len(horses) and isinstance(horses[int(hidx)], dict)
        else ("", "", "", "")
        for hidx in df["_horse_index"].tolist()
    ]
    df_grid["_best_city"] = [x[0] for x in _best_meta]
    df_grid["_best_date"] = [x[1] for x in _best_meta]
    df_grid["_best_distance"] = [x[2] for x in _best_meta]
    df_grid["_best_info"] = [x[3] for x in _best_meta]
    df_grid["_eid_click_token"] = ["" for _ in range(len(df_grid))]
    df_grid["_horse_click_token"] = ["" for _ in range(len(df_grid))]
    last_race_renderer = JsCode(r"""
    class LastRaceRenderer {
        init(params) {
            const span = document.createElement('span');
            const degree = String(params.value ?? '').trim();
            const data = params.data || {};
            const date = String(data._last_date || '').trim();
            const city = String(data._last_city || '').trim();
            const distance = String(data._last_distance || '').trim();
            const surface = String(data._last_surface || '').trim();
            const place = String(data._last_place || '').trim();
            const weight = String(data._last_weight || '').trim();
            const jockey = String(data._last_jockey || '').trim();
            const hp = String(data._last_hp || '').trim();
            const raceName = String(data._last_race_name || '').trim();
            const raceClass = String(data._last_class || '').trim();
            const prize = String(data._last_prize || '').trim();

            span.textContent = degree || '-';
            const normalized = surface.toLowerCase()
                .replace(/ı/g,'i').replace(/ş/g,'s').replace(/ğ/g,'g')
                .replace(/ü/g,'u').replace(/ö/g,'o').replace(/ç/g,'c');
            if (/^(c|cim|grass|turf)(?:[:\s-]|$)/.test(normalized) || normalized.includes('cim') || normalized.includes('grass') || normalized.includes('turf')) {
                span.style.color = '#138a36';
            } else if (/^(k|kum|dirt)(?:[:\s-]|$)/.test(normalized) || normalized.includes('kum') || normalized.includes('dirt')) {
                span.style.color = '#8b5a2b';
            } else if (/^(s|sentetik|synthetic)(?:[:\s-]|$)/.test(normalized) || normalized.includes('sentetik') || normalized.includes('synthetic') || normalized.includes('polytrack') || normalized.includes('fiber')) {
                span.style.color = '#7b2cbf';
            } else {
                span.style.color = '#000000';
            }
            span.style.fontWeight = '900';
            span.style.cursor = 'help';
            span.style.position = 'relative';
            span.style.display = 'inline-block';

            let message = '';
            if (degree) message += 'Son Koşu Derecesi: ' + degree;
            if (city) message += (message ? '\n' : '') + 'Hipodrom: ' + city;
            if (date) message += (message ? '\n' : '') + 'Tarih: ' + date;
            if (distance) message += (message ? '\n' : '') + 'Mesafe: ' + distance;
            if (surface) message += (message ? '\n' : '') + 'Pist: ' + surface;
            if (place) message += (message ? '\n' : '') + 'Sıra: ' + place;
            if (weight) message += (message ? '\n' : '') + 'Sıklet: ' + weight;
            if (jockey) message += (message ? '\n' : '') + 'Jokey: ' + jockey;
            if (hp) message += (message ? '\n' : '') + 'HP: ' + hp;
            if (raceName) message += (message ? '\n' : '') + 'Koşu: ' + raceName;
            if (raceClass) message += (message ? '\n' : '') + 'Sınıf: ' + raceClass;
            if (prize) message += (message ? '\n' : '') + 'İkramiye: ' + prize;

            span.addEventListener('mouseenter', function() {
                if (!message) return;
                if (window.__ri_remove_last_race_tooltip) window.__ri_remove_last_race_tooltip();
                if (window.__ri_remove_eid_tooltip) window.__ri_remove_eid_tooltip();

                const tooltip = document.createElement('div');
                tooltip.textContent = message;
                tooltip.style.position = 'fixed';
                tooltip.style.zIndex = '2147483647';
                tooltip.style.width = '270px';
                tooltip.style.maxWidth = '320px';
                tooltip.style.padding = '10px 12px';
                tooltip.style.background = '#ffffff';
                tooltip.style.color = '#ff0000';
                tooltip.style.border = '1px solid #ff0000';
                tooltip.style.borderRadius = '6px';
                tooltip.style.boxShadow = '0 4px 10px rgba(0,0,0,0.25)';
                tooltip.style.textAlign = 'left';
                tooltip.style.whiteSpace = 'pre-line';
                tooltip.style.fontSize = '13px';
                tooltip.style.fontWeight = '700';
                tooltip.style.lineHeight = '1.4';
                tooltip.style.pointerEvents = 'none';

                document.body.appendChild(tooltip);
                window.__ri_last_race_tooltip = tooltip;

                const r = span.getBoundingClientRect();
                const tw = tooltip.offsetWidth;
                const th = tooltip.offsetHeight;
                let left = r.left + (r.width / 2) - (tw / 2);
                let top = r.top - th - 10;
                left = Math.max(8, Math.min(left, window.innerWidth - tw - 8));
                if (top < 8) top = r.bottom + 10;
                tooltip.style.left = left + 'px';
                tooltip.style.top = top + 'px';
            });

            span.addEventListener('mouseleave', function() {
                if (window.__ri_remove_last_race_tooltip) window.__ri_remove_last_race_tooltip();
            });

            this.eGui = span;
        }
        getGui() { return this.eGui; }
    }
    """)

    selected_horse_index = st.session_state.get("selected_horse_index")
    selected_horse = None

    grid_options = {
        "rowHeight": 52,
        "headerHeight": 38,
        "domLayout": "autoHeight",
        "suppressRowClickSelection": True,
        "rowSelection": "single",
        "animateRows": False,
        "enableCellTextSelection": True,
        "tooltipShowDelay": 0,
        "tooltipHideDelay": 0,
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
                window.__ri_last_race_tooltip = null;
                window.__ri_remove_last_race_tooltip = function() {
                    const t = window.__ri_last_race_tooltip;
                    if (t && t.parentNode) t.parentNode.removeChild(t);
                    window.__ri_last_race_tooltip = null;
                };
                window.__ri_eid_tooltip = null;
                window.__ri_remove_eid_tooltip = function() {
                    const t = window.__ri_eid_tooltip;
                    if (t && t.parentNode) t.parentNode.removeChild(t);
                    window.__ri_eid_tooltip = null;
                };
            }
        """ % ("null" if selected_horse_index is None else str(int(selected_horse_index)))),
        "onCellMouseOver": JsCode("""
            function(params) {
                if (!params.column || params.column.getColId() !== 'EİD') return;
                if (!params.data) return;

                if (window.__ri_remove_eid_tooltip) window.__ri_remove_eid_tooltip();

                const city = String(params.data._best_city || '').trim();
                const date = String(params.data._best_date || '').trim();
                const distance = String(params.data._best_distance || '').trim();
                const info = String(params.data._best_info || '').trim();
                const degree = String(params.data['EİD'] || '').trim();
                if (!city && !date && !distance && !info) return;

                let message = '';
                if (city || date) {
                    const hipodrom = /hipodrom/i.test(city) ? city : (city ? city + ' Hipodromu' : 'TJK Hipodromu');
                    message = 'Bu derece ' + hipodrom + "'nda " + (date || 'belirtilen tarihte') + ' yapılmıştır.';
                } else {
                    message = 'En İyi Derece: ' + (degree || '-');
                }
                if (distance) message += '\nMesafe: ' + distance;
                if (info) message += '\n' + info;

                const tooltip = document.createElement('div');
                tooltip.textContent = message;
                tooltip.style.position = 'fixed';
                tooltip.style.zIndex = '2147483647';
                tooltip.style.width = '250px';
                tooltip.style.maxWidth = '300px';
                tooltip.style.padding = '10px';
                tooltip.style.background = '#ffffff';
                tooltip.style.color = '#ff0000';
                tooltip.style.border = '1px solid #ff0000';
                tooltip.style.borderRadius = '6px';
                tooltip.style.boxShadow = '0 4px 10px rgba(0,0,0,0.15)';
                tooltip.style.textAlign = 'center';
                tooltip.style.whiteSpace = 'pre-line';
                tooltip.style.fontSize = '14px';
                tooltip.style.fontWeight = '600';
                tooltip.style.lineHeight = '1.35';
                tooltip.style.pointerEvents = 'none';

                document.body.appendChild(tooltip);
                window.__ri_eid_tooltip = tooltip;

                const cell = params.event && params.event.currentTarget ? params.event.currentTarget : null;
                const r = cell && cell.getBoundingClientRect ? cell.getBoundingClientRect() : null;
                if (!r) return;
                const tw = tooltip.offsetWidth;
                const th = tooltip.offsetHeight;
                let left = r.left + (r.width / 2) - (tw / 2);
                let top = r.top - th - 10;
                left = Math.max(8, Math.min(left, window.innerWidth - tw - 8));
                if (top < 8) top = r.bottom + 10;
                tooltip.style.left = left + 'px';
                tooltip.style.top = top + 'px';
            }
        """),
        "onCellMouseOut": JsCode("""
            function(params) {
                if (params.column && params.column.getColId() === 'EİD') {
                    if (window.__ri_remove_eid_tooltip) window.__ri_remove_eid_tooltip();
                }
            }
        """),
        "onCellClicked": JsCode("""
            function(params) {
                if (params.colDef && params.colDef.field === 'At İsmi' && params.node) {
                    params.node.setDataValue('_horse_click_token', String(Date.now()));
                    params.node.setSelected(true);
                    if (params.data && params.data._horse_index !== undefined) {
                        window.__ri_selected_horse_index = params.data._horse_index;
                    }
                }
            }
        """),
    }

    gb = GridOptionsBuilder.from_dataframe(df_grid)
    gb.configure_default_column(
        sortable=True, filter=True, resizable=True,
        wrapText=True, autoHeight=False,
        cellStyle=cell_style_js,
    )
    gb.configure_selection(selection_mode="single", use_checkbox=False)
    gb.configure_grid_options(**grid_options)

    # Sabit sütunlar.
    gb.configure_column("No", header_name="No", pinned="left", width=62, minWidth=55, maxWidth=75, type=["numericColumn"], cellStyle=JsCode("function(params){return {color:'#000000',fontWeight:'900'};}"))
    gb.configure_column("At İsmi", header_name="At İsmi", pinned="left", width=145, minWidth=145, maxWidth=145, resizable=False, cellRenderer=horse_name_renderer, cellClass="ri-left-centered-cell")
    gb.configure_column("Yaş", width=55, minWidth=55, maxWidth=55, resizable=False, cellStyle=JsCode("function(params){return {color:'#000000',fontWeight:'900'};}"), cellClass="ri-left-centered-cell")
    gb.configure_column("Orijin (Baba-Anne)", width=165, minWidth=165, maxWidth=165, resizable=False, cellRenderer=origin_renderer, cellClass="ri-left-centered-cell")
    gb.configure_column("Kilo", width=75, minWidth=75, maxWidth=75, resizable=False, cellRenderer=weight_renderer, cellClass="ri-left-centered-cell")
    gb.configure_column("Jokey", width=105, minWidth=105, maxWidth=105, resizable=False, cellRenderer=jockey_renderer, cellClass="ri-left-centered-cell")
    gb.configure_column("Sahip / Antrenör", width=150, minWidth=150, maxWidth=150, resizable=False, cellRenderer=owner_trainer_renderer, cellClass="ri-left-centered-cell")
    gb.configure_column("St", width=78, minWidth=78, maxWidth=78, resizable=False, cellRenderer=start_renderer, cellClass="ri-left-centered-cell")
    gb.configure_column("HP", width=58, minWidth=58, maxWidth=58, resizable=False, cellRenderer=hp_renderer, cellClass="ri-left-centered-cell")
    gb.configure_column("Son 6 Y.", width=85, minWidth=85, maxWidth=85, resizable=False, cellRenderer=form_renderer, cellClass="ri-left-centered-cell")
    gb.configure_column("KGS", width=58, minWidth=58, maxWidth=58, resizable=False, cellRenderer=kgs_renderer, cellClass="ri-left-centered-cell")
    gb.configure_column("s20", width=58, minWidth=58, maxWidth=58, resizable=False, cellRenderer=compact_black_renderer, cellClass="ri-left-centered-cell", cellStyle=JsCode("function(params){return {color:'#0f766e',fontWeight:'900'};}"))
    gb.configure_column(
        "EİD", width=75, minWidth=65, cellRenderer=eid_renderer, cellClass="ri-eid-cell"
    )
    gb.configure_column("Gny", width=60, minWidth=60, maxWidth=60, resizable=False, cellStyle=JsCode("function(params){return {color:'#00a6b2',fontWeight:'900'};}"), cellClass="ri-left-centered-cell")
    gb.configure_column("AGF", width=70, minWidth=70, maxWidth=70, resizable=False, cellRenderer=agf_renderer, cellClass="ri-left-centered-cell")
    # BİZİM SKOR / REYTİNG / GÜNCEL SINIF: sayı hücresinin içinde dairesel gösterim.
    # Her sütunda ilk 5 değer koyu yeşilden açık yeşile renklendirilir.
    # GÜNCEL SINIF farkında negatif değer kırmızı, pozitif değer mavi yazılır.
    _score_circle_renderer = JsCode(r"""
    class ScoreCircleRenderer {
        init(params) {
            const root = document.createElement('div');
            root.style.width = '100%';
            root.style.height = '100%';
            root.style.display = 'flex';
            root.style.alignItems = 'center';
            root.style.justifyContent = 'center';
            root.style.boxSizing = 'border-box';
            root.style.overflow = 'hidden';

            const value = Number(String(params.value == null ? '' : params.value).replace('+',''));
            if (!isFinite(value) || !params.api) {
                const plain = document.createElement('span');
                plain.textContent = params.value == null ? '' : String(params.value);
                plain.style.fontWeight = '900';
                plain.style.fontSize = '13px';
                root.appendChild(plain);
                this.eGui = root;
                return;
            }

            const field = params.colDef.field;
            const values = [];
            params.api.forEachNodeAfterFilterAndSort(function(node) {
                if (!node.data) return;
                const x = Number(String(node.data[field] == null ? '' : node.data[field]).replace('+',''));
                if (isFinite(x)) values.push(x);
            });

            let bg = '#f3c84b';
            let fg = '#111111';
            let border = '#d6a900';

            // ------------------------------------------------------------
            // BİZİM SKOR: en yüksek 4 mavi tonları, en düşük 3 kırmızı tonları,
            // ortadakiler sarı tonları. Mavi/kırmızı yazı beyaz, sarı siyah.
            // ------------------------------------------------------------
            if (field === 'BİZİM SKOR') {
                const sorted = values.slice().sort(function(a,b){ return b-a; });
                const idx = sorted.indexOf(value);
                const rankHigh = idx + 1;
                const sortedAsc = values.slice().sort(function(a,b){ return a-b; });
                const rankLow = sortedAsc.indexOf(value) + 1;

                if (rankHigh <= Math.min(4, sorted.length)) {
                    const blues = ['#063b73','#0a4f96','#1769aa','#4b8fc9'];
                    bg = blues[rankHigh - 1] || blues[3];
                    border = '#052f5f';
                    fg = '#ffffff';
                } else if (rankLow <= Math.min(3, sorted.length)) {
                    const reds = ['#8b0000','#b22222','#dc4b4b'];
                    bg = reds[rankLow - 1] || reds[2];
                    border = '#6f0000';
                    fg = '#ffffff';
                } else {
                    const ratio = sorted.length > 1 ? idx / (sorted.length - 1) : 0.5;
                    bg = ratio < 0.5 ? '#f7d774' : '#f1bd3a';
                    border = '#c99618';
                    fg = '#111111';
                }
            }

            // ------------------------------------------------------------
            // GÜNCEL SINIF:
            // Negatiflerde 0'a en yakın ilk 4 kırmızı tonları,
            // en düşük/uzak 3 negatif mor tonları, ortadakiler sarı.
            // Pozitiflerde en düşük 4 kırmızı, en yüksek 3 mor,
            // ortadakiler sarı. Kırmızı/mor yazı beyaz.
            // ------------------------------------------------------------
            else if (field === 'GÜNCEL SINIF') {
                if (value < 0) {
                    const neg = values.filter(function(x){ return x < 0; }).sort(function(a,b){ return b-a; });
                    const pos = values.filter(function(x){ return x > 0; }).sort(function(a,b){ return a-b; });
                    const rankNearZero = neg.indexOf(value) + 1;
                    const rankMostNegative = neg.slice().sort(function(a,b){ return a-b; }).indexOf(value) + 1;

                    // NEGATİF GÜNCEL SINIF: 0'a en yakın ilk 3 değer yeşil tonları.
                    // Diğer mevcut renk kuralları aynen korunur.
                    if (rankNearZero <= Math.min(3, neg.length)) {
                        const greens = ['#0b5d2a','#2f8f4e','#6fbd7f'];
                        bg = greens[rankNearZero - 1] || greens[2];
                        border = '#08451f';
                        fg = '#ffffff';
                    } else if (rankNearZero === 4) {
                        const red = '#e34b4b';
                        bg = red;
                        border = '#720000';
                        fg = '#ffffff';
                    } else if (rankMostNegative <= Math.min(3, neg.length)) {
                        const purples = ['#3b0a57','#5a1875','#7b3f98'];
                        bg = purples[rankMostNegative - 1] || purples[2];
                        border = '#2d0642';
                        fg = '#ffffff';
                    } else {
                        bg = '#f3c84b';
                        border = '#d6a900';
                        fg = '#111111';
                    }
                } else if (value > 0) {
                    const pos = values.filter(function(x){ return x > 0; }).sort(function(a,b){ return a-b; });
                    const rankLow = pos.indexOf(value) + 1;
                    const rankHigh = pos.slice().sort(function(a,b){ return b-a; }).indexOf(value) + 1;
                    if (rankLow <= Math.min(4, pos.length)) {
                        const reds = ['#8b0000','#a91515','#c92a2a','#e34b4b'];
                        bg = reds[rankLow - 1] || reds[3];
                        border = '#720000';
                        fg = '#ffffff';
                    } else if (rankHigh <= Math.min(3, pos.length)) {
                        const purples = ['#3b0a57','#5a1875','#7b3f98'];
                        bg = purples[rankHigh - 1] || purples[2];
                        border = '#2d0642';
                        fg = '#ffffff';
                    } else {
                        bg = '#f3c84b';
                        border = '#d6a900';
                        fg = '#111111';
                    }
                } else {
                    bg = '#f3c84b';
                    border = '#d6a900';
                    fg = '#111111';
                }
            }

            // REYTİNG: mevcut yeşil ilk 5 görünümü korunur.
            else if (field === 'REYTİNG') {
                const sorted = values.slice().sort(function(a,b){ return b-a; });
                const rank = sorted.indexOf(value) + 1;
                if (rank <= 5) {
                    const greens = ['#0b5d2a','#167a3d','#299653','#4caf6b','#79c98b'];
                    bg = greens[rank - 1] || greens[4];
                    border = '#0a4d24';
                    fg = '#ffffff';
                } else {
                    bg = '#f3c84b';
                    border = '#d6a900';
                    fg = '#111111';
                }
            }

            const circle = document.createElement('span');
            circle.textContent = String(params.value);
            circle.style.display = 'inline-flex';
            circle.style.alignItems = 'center';
            circle.style.justifyContent = 'center';
            circle.style.width = '42px';
            circle.style.height = '42px';
            circle.style.minWidth = '42px';
            circle.style.borderRadius = '50%';
            circle.style.boxSizing = 'border-box';
            circle.style.background = bg;
            circle.style.border = '2px solid ' + border;
            circle.style.color = fg;
            circle.style.fontWeight = '900';
            circle.style.fontSize = '13px';
            circle.style.lineHeight = '1';
            circle.style.textAlign = 'center';
            circle.style.whiteSpace = 'nowrap';
            circle.style.boxShadow = 'inset 0 0 0 1px rgba(255,255,255,.18)';

            root.appendChild(circle);
            this.eGui = root;
        }
        refresh(params) { return false; }
        getGui() { return this.eGui; }
    }
    """)

    gb.configure_column("BİZİM SKOR", width=105, minWidth=90, cellRenderer=_score_circle_renderer,
                        cellStyle=JsCode("function(params){return {textAlign:'center',padding:'1px 0'};}"))
    gb.configure_column("REYTİNG", width=105, minWidth=90, cellRenderer=_score_circle_renderer,
                        cellStyle=JsCode("function(params){return {textAlign:'center',padding:'1px 0'};}"))
    # GÜNCEL SINIF sıralaması: negatiflerde 0'a en yakın negatiften başlayarak,
    # ardından daha düşük negatifler; sonra 0 ve pozitifler küçükten büyüğe.
    # Örnek: -1, -5, -7, -8, +1, +3, +20
    _guncel_sinif_comparator = JsCode(r"""
    function(a, b) {
        function num(v) {
            if (v === null || v === undefined || v === '') return null;
            var n = Number(String(v).replace('+','').replace(',', '.'));
            return isFinite(n) ? n : null;
        }
        var x = num(a), y = num(b);
        if (x === null && y === null) return 0;
        if (x === null) return 1;
        if (y === null) return -1;
        if (x === y) return 0;
        if (x < 0 && y < 0) return y - x;
        if (x < 0 && y >= 0) return -1;
        if (x >= 0 && y < 0) return 1;
        return x - y;
    }
    """)
    gb.configure_column(
        "GÜNCEL SINIF", width=110, minWidth=95,
        cellRenderer=_score_circle_renderer,
        comparator=_guncel_sinif_comparator,
        filter="agNumberColumnFilter",
        filterParams=JsCode(r"""{
            numberParser: function(params) {
                if (params === null || params === undefined || params === '') return null;
                var n = Number(String(params).replace('+','').replace(',', '.'));
                return isFinite(n) ? n : null;
            }
        }"""),
        cellStyle=JsCode("function(params){return {textAlign:'center',padding:'1px 0'};}")
    )
    gb.configure_column("SON GALOP", width=95, minWidth=95, maxWidth=95, resizable=False, cellRenderer=workout_renderer, cellClass="ri-left-centered-cell")
    gb.configure_column("SON KOŞU", width=95, minWidth=80, cellRenderer=last_race_renderer, cellClass="ri-last-race-cell")
    gb.configure_column("BU YIL KAZANÇ", width=115, minWidth=100, cellStyle=JsCode("function(params){return {color:'#800020',fontWeight:'900'};}"))
    gb.configure_column("TOPLAM KAZANÇ", width=120, minWidth=105, cellStyle=JsCode("function(params){return {color:'#800020',fontWeight:'900'};}"))
    gb.configure_column("_horse_index", hide=True)
    gb.configure_column("_last_surface", hide=True)
    gb.configure_column("_last_date", hide=True)
    gb.configure_column("_last_city", hide=True)
    gb.configure_column("_last_distance", hide=True)
    gb.configure_column("_last_place", hide=True)
    gb.configure_column("_last_weight", hide=True)
    gb.configure_column("_last_jockey", hide=True)
    gb.configure_column("_last_hp", hide=True)
    gb.configure_column("_race_finish", hide=True)
    gb.configure_column("_last_race_name", hide=True)
    gb.configure_column("_last_class", hide=True)
    gb.configure_column("_last_prize", hide=True)
    gb.configure_column("_form_surfaces", hide=True)
    gb.configure_column("_best_city", hide=True)
    gb.configure_column("_best_date", hide=True)
    gb.configure_column("_eid_click_token", hide=True)
    gb.configure_column("_horse_click_token", hide=True)

    grid_options = gb.build()
    grid_options["getRowStyle"] = JsCode("""
        function(params) {
            const selected = window.__ri_selected_horse_index;
            if (selected !== undefined && selected !== null && params.data && String(params.data._horse_index) === String(selected)) {
                return {backgroundColor:'#dceeff', color:'#062b55', fontWeight:'700'};
            }
            return {backgroundColor: (params.node && params.node.rowIndex % 2 === 1) ? '#f4f4f2' : '#e8e8e6'};
        }
    """)
    grid_options["onSelectionChanged"] = JsCode("""
        function(params) {
            const rows = params.api.getSelectedRows();
            if (rows && rows.length && rows[0]._horse_index !== undefined) {
                window.__ri_selected_horse_index = rows[0]._horse_index;
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

    grid_height = max(150, 42 + len(df_grid) * 44)
    grid_response = AgGrid(
        df_grid,
        gridOptions=grid_options,
        height=grid_height,
        width="100%",
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        update_mode="SELECTION_CHANGED",
        data_return_mode="AS_INPUT",
        theme="streamlit",
        # Her koşunun AgGrid state'i ayrı tutulmalı. Aynı key kullanılırsa
        # önceki koşunun seçili satırı yeni koşuya taşınabilir ve TJK geçmişi
        # yanlış koşunun tablosunun altında açılabilir.
        key=f"horse_table_aggrid_{race_number}_{selected_date.isoformat()}_{selected_city}",
    )

    raw_selected_rows = None
    try:
        raw_selected_rows = grid_response.get("selected_rows")
    except Exception:
        raw_selected_rows = None

    if isinstance(raw_selected_rows, pd.DataFrame):
        selected_rows = raw_selected_rows.to_dict(orient="records")
    elif isinstance(raw_selected_rows, list):
        selected_rows = raw_selected_rows
    elif raw_selected_rows is not None:
        try:
            selected_rows = list(raw_selected_rows)
        except Exception:
            selected_rows = []
    else:
        selected_rows = []

    # ÖNEMLİ: Ana tablonun herhangi bir hücresine tıklamak veri çekmez.
    # Koşu + galop zenginleştirmesi yalnızca "At İsmi" hücresinden gelen
    # özel tıklama token'ı varsa çalışır.
    horse_name_clicked = False
    if not selected_rows:
        try:
            returned_data = grid_response.get("data")
            if isinstance(returned_data, pd.DataFrame):
                token_rows = returned_data[returned_data["_horse_click_token"].astype(str).str.strip() != ""] if "_horse_click_token" in returned_data.columns else pd.DataFrame()
                if not token_rows.empty:
                    selected_rows = token_rows.to_dict(orient="records")
                    horse_name_clicked = True
            elif isinstance(returned_data, list):
                token_rows = [r for r in returned_data if isinstance(r, dict) and str(r.get("_horse_click_token") or "").strip()]
                if token_rows:
                    selected_rows = token_rows
                    horse_name_clicked = True
        except Exception:
            pass

    if selected_rows:
        horse_name_clicked = horse_name_clicked or bool(str(selected_rows[0].get("_horse_click_token") or "").strip())
        st.session_state["_last_eid_click_token"] = ""

        try:
            selected_horse_index = int(selected_rows[0].get("_horse_index"))
        except Exception:
            selected_horse_index = None
        if selected_horse_index is not None and 0 <= selected_horse_index < len(horses):
            selected_horse = horses[selected_horse_index]
            st.session_state.selected_horse_no = get_horse_number(
                selected_horse,
                selected_horse_index + 1,
            )
            st.session_state.selected_horse_index = selected_horse_index
            _detail_fetch_key = (
                str(race_number),
                str(selected_horse.get("atId") or selected_horse.get("at_id") or selected_horse.get("id") or ""),
                str(selected_horse_index),
                str(selected_date),
                str(selected_city),
                str(distance),
                str(surface),
                str(condition),
            )

            if horse_name_clicked and st.session_state.get("_selected_detail_fetch_key") != _detail_fetch_key:
                # Ana tablo satırına ilk tıklamada boş cache varsa temizle.
                # Böylece TJK geçmişi/galop verisi gerçekten yeniden sorgulanır.
                horse_status = st.status(
                    f"🔄 {get_horse_name(selected_horse)} için TJK gerçek koşu ve galop verileri çekiliyor...",
                    expanded=True,
                )
                horse_status.write("📡 TJK koşu geçmişi ve galop verisi sorgulanıyor...")
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

    # AgGrid bazı sürümlerde SELECTION_CHANGED sonucunu ilk tıklamada
    # Streamlit'e geri taşımayabilir. Session state / JS seçiminden devam et.
    if selected_horse is None:
        fallback_index = st.session_state.get("selected_horse_index")
        if isinstance(fallback_index, int) and 0 <= fallback_index < len(horses):
            selected_horse = horses[fallback_index]

    selected_no = st.session_state.get("selected_horse_no")
    if selected_no is not None and selected_horse is None:
        # Yalnızca mevcut koşunun seçili index'i üzerinden geri yükle.
        # At numarasına göre global arama yapılması farklı koşulardaki
        # seçimlerin birbirine karışmasına yol açabilir.
        current_index = st.session_state.get("selected_horse_index")
        if isinstance(current_index, int) and 0 <= current_index < len(horses):
            selected_horse = horses[current_index]

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
                    pv = _money_number(_first_value(h, ["prize", "ikramiye", "Ikramiye", "İkramiye", "prizeAmount", "prize_amount", "earnings", "kazanc", "Kazanç"]))
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
                "REYTİNG: Ortak Rakip+Kilo %23 • Kilo Uyumu %17 • Güncel Form %15 • Normalize Derece %10 • "
                "Pist/Mesafe %12 • Sınıf %9 • Tempo %6 • Galop %6 • Ham Hız %2. "
                "Hesapta yalnızca hedef koşu tarihinden önceki veriler kullanılır."
            )

    agf_values = [get_horse_agf(h) for h in horses if isinstance(h, dict)]
    if agf_values and all(v == "-" for v in agf_values):
        st.caption("AGF: TJK program kaynağında bu koşu için henüz değer yok; '-' gösteriliyor. Değer uydurulmaz.")


# ============================================================
# MODEL DURUMU
# ============================================================

st.markdown("---")
st.markdown(
    f"**REYTİNG MOTORU:** Ortak Rakip+Kilo %23 • Kilo Uyumu %17 • Form %15 • Normalize Derece %10 • "
    f"Pist/Mesafe %12 • Sınıf %9 • Tempo %6 • Galop %6 • Ham Hız %2 • Seçili koşu: {race_number}. koşu",
)
st.caption(
    "REYTİNG yalnızca yarış tarihinden önceki TJK geçmişi ve yarış öncesi galop verileriyle hesaplanır; aynı günkü sonuç REYTİNG'e girmez."
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
    min-height: 72px !important;
    max-height: none !important;
    overflow: visible !important;
    padding-top: 16px !important;
    box-sizing: border-box !important;
}
div.ri-title {
    display: block !important;
    visibility: visible !important;
    color: #FFFFFF !important;
    font-size: 40px !important;
    font-weight: 950 !important;
    line-height: 1.25 !important;
    height: auto !important;
    min-height: 50px !important;
    white-space: nowrap !important;
    text-align: center !important;
    width: 100% !important;
    margin-top: 0 !important;
    margin-bottom: 2px !important;
    padding-top: 2px !important;
    overflow: visible !important;
}
div.ri-subtitle {
    display: block !important;
    visibility: visible !important;
}
</style>
""", unsafe_allow_html=True)
