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
if "selected_horse_index" not in st.session_state:
    st.session_state.selected_horse_index = None


# ============================================================
# ============================================================
# YENİ TJK GÖRSEL SİSTEMİ
# ============================================================

st.markdown(r"""
<style>
/* Sayfa */
section.main > div.block-container,
div[data-testid="stMainBlockContainer"] {
    max-width: none !important;
    width: 100% !important;
    padding: 12px 14px 28px 14px !important;
}
body, .stApp { background: #ffffff !important; }

/* Üst başlık */
.ri-top-title { font-size: 30px; font-weight: 900; color:#172235; margin:0 0 2px 0; }
.ri-top-sub { font-size:12px; color:#657286; margin-bottom:12px; }

/* Yarış seçim satırı */
.race-nav { display:flex; gap:8px; overflow-x:auto; padding:3px 0 9px 0; }
.race-nav::-webkit-scrollbar { height:6px; }
.race-nav::-webkit-scrollbar-thumb { background:#b7c2d1; border-radius:6px; }

/* Seçili koşu bilgi bandı: TJK/YB tarzı */
.tjk-race-head {
    display:flex; align-items:center; gap:10px; flex-wrap:wrap;
    background:#f08a18; color:#fff; border-radius:2px 2px 0 0;
    padding:8px 12px; font-size:14px; font-weight:800;
    border:1px solid #df7d0b;
}
.tjk-race-head .time { font-weight:950; }
.tjk-race-head .info { margin-left:auto; font-size:18px; }

/* Model butonları */
.model-actions { margin:9px 0 8px 0; }
.model-state {
    display:inline-block; padding:5px 9px; border-radius:4px;
    font-size:11px; font-weight:850; margin-left:7px;
}
.model-real { background:#e8f6ed; color:#18723a; }
.model-manual { background:#fff0df; color:#a65b05; }

/* Ana tablo */
.tjk-table-wrap { width:100%; overflow-x:auto; border:1px solid #d6dbe3; border-top:0; }
table.tjk-main {
    width:max-content; min-width:100%; border-collapse:collapse; table-layout:fixed;
    font-family:Arial,Helvetica,sans-serif; font-size:12px; color:#142033;
}
table.tjk-main th {
    background:#e1e5eb; color:#111827; font-weight:900; text-align:center;
    border:1px solid #c8ced7; padding:8px 7px; white-space:nowrap;
    height:38px; box-sizing:border-box;
}
table.tjk-main td {
    border:1px solid #d5dae1; padding:7px 7px; vertical-align:middle;
    text-align:center; height:58px; box-sizing:border-box; background:#f7f8fa;
}
table.tjk-main tr:nth-child(even) td { background:#eef1f5; }
table.tjk-main tr:hover td { background:#e3edf8; }
table.tjk-main tr.selected td { background:#d6ebff !important; box-shadow:inset 0 2px 0 #4b9ee8, inset 0 -2px 0 #4b9ee8; }
.tjk-cell-left { text-align:left !important; }
.tjk-horse-link { display:block; text-decoration:none; color:#1d3557; font-weight:900; }
.tjk-horse-name { font-size:13px; font-weight:950; color:#1c3557; line-height:1.15; }
.tjk-equip { color:#e33a35; font-size:11px; font-weight:850; margin-top:3px; }
.tjk-origin-sire { color:#1570c2; font-size:11px; line-height:1.15; margin-top:2px; }
.tjk-origin-dam { color:#e33a35; font-size:11px; line-height:1.15; margin-top:2px; }
.tjk-small { font-size:11px; color:#3e4d63; }
.tjk-weight { font-weight:900; color:#111827; line-height:1.15; }
.tjk-extra { color:#e36b32; font-size:10px; font-weight:800; margin-top:2px; }
.tjk-jockey { color:#1e477b; font-weight:850; line-height:1.15; }
.tjk-ap { color:#e33a35; font-size:10px; font-weight:850; margin-top:2px; }
.tjk-time { color:#e32f3b; font-weight:900; }
.tjk-agf { color:#1d6b36; font-weight:900; }
.tjk-score { font-weight:950; }
.tjk-linkish { color:#2671b9; font-weight:900; }

/* Ana tablo yatay kaydırma çubuğu görünür ama dikey yok */
.tjk-table-wrap::-webkit-scrollbar { height:10px; }
.tjk-table-wrap::-webkit-scrollbar-thumb { background:#9aa7b8; border-radius:8px; }
.tjk-table-wrap::-webkit-scrollbar-track { background:#edf0f4; }

/* Seçilen at detay başlığı */
.horse-detail-head {
    margin-top:18px; background:#26364a; color:#fff; padding:9px 12px;
    font-size:17px; font-weight:950; border-radius:3px 3px 0 0;
}
.horse-detail-sub { background:#f0f2f5; border:1px solid #d3d8df; border-top:0; padding:7px 12px; color:#4b5565; font-size:11px; }

/* Gerçek geçmiş / galop tabloları */
.detail-table-wrap { width:100%; overflow-x:auto; border:1px solid #d2d7df; }
table.detail-table { width:max-content; min-width:100%; border-collapse:collapse; font-size:11px; font-family:Arial,Helvetica,sans-serif; }
table.detail-table th { background:#aeb7c5; color:#111827; padding:8px 7px; border:1px solid #c7cdd5; font-weight:900; white-space:nowrap; }
table.detail-table td { padding:7px 7px; border:1px solid #d2d7df; white-space:nowrap; background:#f6f7f9; }
table.detail-table tr:nth-child(even) td { background:#e8edf3; }
table.detail-table .blue { color:#1c6db3; font-weight:850; }
table.detail-table .red { color:#e33a35; font-weight:850; }
table.detail-table .green { color:#208345; font-weight:850; }
table.detail-table .result { font-size:13px; font-weight:950; text-align:center; }

/* İstatistikler */
.stats-grid { display:grid; grid-template-columns:repeat(6,minmax(100px,1fr)); gap:8px; margin-top:10px; }
.stat-card { background:#f1f3f6; border:1px solid #d4d9e0; border-radius:4px; padding:10px; text-align:center; }
.stat-card .v { font-size:20px; font-weight:950; color:#1d3557; }
.stat-card .l { font-size:10px; color:#647084; font-weight:800; margin-top:2px; }

/* Streamlit expander sade */
div[data-testid="stExpander"] { border:1px solid #d2d7df !important; border-radius:4px !important; background:#fff !important; }

@media (max-width:900px) {
    .stats-grid { grid-template-columns:repeat(3,minmax(90px,1fr)); }
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="ri-top-title">🏇 RACE INTELLIGENCE</div>
<div class="ri-top-sub">TJK gerçek programı • gerçek koşu geçmişi • gerçek galop • analiz motoru</div>
""", unsafe_allow_html=True)

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
        return base, f"Fazla Kilo: {fm.group(1).replace(',', '.')}"
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
        label = "AP Apranti" if m.group(2).strip().upper() == "AP" else m.group(2).strip()
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
        data = load_horse_enrichment(str(at_id), name)
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

    with ThreadPoolExecutor(max_workers=min(6, max(1, len(enriched)))) as executor:
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


def _history_tables(history: List[Dict[str, Any]]) -> None:
    """TJK gerçek koşu geçmişini tüm başlıkları tek satırda göster."""
    if not history:
        st.warning("Bu at için TJK gerçek koşu geçmişi gelmedi.")
        return

    rows = []
    for row in history:
        if not isinstance(row, dict):
            continue
        rows.append({
            "Tarih": _first_value(row, ["date", "tarih", "Tarih"]),
            "Şehir": _first_value(row, ["city", "şehir", "Sehir"]),
            "Mesafe": _first_value(row, ["distance", "msf", "mesafe"]),
            "Pist": _first_value(row, ["surface", "pist"]),
            "Derece/Sıra": _first_value(row, ["place", "sira", "S"]),
            "Derece": _first_value(row, ["time", "derece"]),
            "Kilo": _first_value(row, ["weight", "kilo", "siklet"]),
            "Jokey": _first_value(row, ["jockey", "jokey"]),
            "HP": _first_value(row, ["hp", "HP"]),
            "Takı": _first_value(row, ["equipment", "taki"]),
            "Start": _first_value(row, ["post", "st", "start"]),
            "Gny": _first_value(row, ["odds", "gny"]),
            "Grup": _first_value(row, ["group", "grup"]),
            "Koşu": _first_value(row, ["raceName", "race_name", "kosu"]),
            "Sınıf": _first_value(row, ["className", "class", "sinif"]),
            "Antrenör": _first_value(row, ["trainer", "antrenor"]),
            "Sahip": _first_value(row, ["owner", "sahip"]),
            "İkramiye": _first_value(row, ["prize", "ikramiye"]),
            "S20": _first_value(row, ["s20", "S20"]),
        })

    df = pd.DataFrame(rows)
    _html_real_table(df)


def _workout_tables(workouts: List[Dict[str, Any]]) -> None:
    """TJK gerçek galop kayıtlarını tek başlık satırında göster."""
    if not workouts:
        st.warning("Bu at için TJK gerçek galop kaydı gelmedi.")
        return

    rows = []
    for row in workouts:
        if not isinstance(row, dict):
            continue
        rows.append({
            "Tarih": _first_value(row, ["date", "tarih", "Tarih"]),
            "Şehir": _first_value(row, ["city", "şehir", "Sehir"]),
            "Mesafe": _first_value(row, ["distance", "msf", "mesafe"]),
            "Pist": _first_value(row, ["surface", "pist"]),
            "Derece": _first_value(row, ["time", "derece"]),
            "400": _first_value(row, ["m400", "400", "time400"]),
            "600": _first_value(row, ["m600", "600", "time600"]),
            "800": _first_value(row, ["m800", "800", "time800"]),
            "1000": _first_value(row, ["m1000", "1000", "time1000"]),
            "1200": _first_value(row, ["m1200", "1200", "time1200"]),
            "Kilo": _first_value(row, ["weight", "kilo", "siklet"]),
            "Binici": _first_value(row, ["rider", "binici"]),
            "Jokey": _first_value(row, ["jockey", "jokey"]),
            "Tür": _first_value(row, ["type", "tur", "Tür"]),
            "Not": _first_value(row, ["note", "not", "aciklama"]),
        })

    df = pd.DataFrame(rows)
    _html_real_table(df)


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
# ============================================================
# SIDEBAR / PROGRAM
# ============================================================

st.sidebar.title("🏇 Yarış Programı")
selected_date = st.sidebar.date_input("Tarih", value=date.today())

with st.sidebar:
    with st.spinner("TJK'daki aktif hipodromlar kontrol ediliyor..."):
        active_cities = load_active_cities(selected_date)

if not active_cities:
    st.sidebar.warning(f"{selected_date.strftime('%d/%m/%Y')} tarihinde TJK'dan yarış programı bulunamadı.")
    st.stop()

if st.session_state.loaded_city in active_cities:
    default_city_index = active_cities.index(st.session_state.loaded_city)
else:
    default_city_index = 0

selected_city = st.sidebar.selectbox("Hipodrom", active_cities, index=default_city_index)
get_program_clicked = st.sidebar.button("📥 PROGRAMI GETİR", use_container_width=True)

if get_program_clicked:
    st.session_state.program_data = None
    st.session_state.loaded_date = None
    st.session_state.loaded_city = None
    st.session_state.selected_race = 1
    st.session_state.selected_horse_no = None
    st.session_state.selected_horse_index = None
    try:
        result = fetch_program_with_status(selected_date, selected_city, "PROGRAM GETİR")
        st.session_state.program_data = result
        st.session_state.loaded_date = selected_date
        st.session_state.loaded_city = selected_city
        try: st.query_params.clear()
        except Exception: pass
    except Exception as exc:
        st.error(f"Program alınırken hata oluştu: {exc}")
        st.stop()

program_data = st.session_state.program_data
if program_data is None:
    try:
        program_data = fetch_program_with_status(selected_date, selected_city, "PROGRAM HAZIRLANIYOR")
        st.session_state.program_data = program_data
        st.session_state.loaded_date = selected_date
        st.session_state.loaded_city = selected_city
        st.session_state.selected_race = 1
    except Exception as exc:
        st.error(f"Program alınamadı: {exc}")
        st.stop()

if not isinstance(program_data, dict):
    st.error("TJK'dan gelen program verisi geçersiz.")
    st.stop()

if st.session_state.loaded_date != selected_date or st.session_state.loaded_city != selected_city:
    try:
        program_data = fetch_program_with_status(selected_date, selected_city, "PROGRAM YENİLENİYOR")
        st.session_state.program_data = program_data
        st.session_state.loaded_date = selected_date
        st.session_state.loaded_city = selected_city
        st.session_state.selected_race = 1
        st.session_state.selected_horse_no = None
        st.session_state.selected_horse_index = None
        try: st.query_params.clear()
        except Exception: pass
    except Exception as exc:
        st.error(f"Program yenilenemedi: {exc}")
        st.stop()

races = program_data.get("races", [])
if not isinstance(races, list) or not races:
    st.warning(f"{selected_city} — {selected_date.strftime('%d/%m/%Y')} için koşu bulunamadı.")
    st.stop()

# ============================================================
# KOŞU SEÇİMİ
# ============================================================

st.markdown("### Koşular")
_race_css = ["<style>"]
for _idx, _race in enumerate(races):
    _surface = str(_race.get("surface") or (_race.get("meta") or {}).get("surface") or "").lower()
    _bg = "#e98b19" if "kum" in _surface else "#159447"
    _race_css.append(f'.st-key-race_button_{get_race_number(_race,_idx+1)} button{{background:{_bg};border-color:{_bg};color:#fff;font-weight:900;}}')
    _race_css.append(f'.st-key-race_button_{get_race_number(_race,_idx+1)} button:hover{{filter:brightness(1.06);color:#fff;}}')
_race_css.append("</style>")
st.markdown("\n".join(_race_css), unsafe_allow_html=True)

race_columns = st.columns(len(races))
for index, race in enumerate(races):
    race_number_i = get_race_number(race, index + 1)
    race_time_i = display_value(race.get("race_time"))
    label_i = f"{race_number_i}. Koşu {race_time_i}" if race_time_i != "-" else f"{race_number_i}. Koşu"
    with race_columns[index]:
        if st.button(label_i, key=f"race_button_{race_number_i}", use_container_width=True, type="primary" if st.session_state.selected_race == race_number_i else "secondary"):
            st.session_state.selected_race = race_number_i
            st.session_state.selected_horse_no = None
            st.session_state.selected_horse_index = None
            st.session_state.real_analysis_requested = True
            st.session_state.real_analysis_done = False
            try: st.query_params.clear()
            except Exception: pass
            st.rerun()

selected_race = next((r for i,r in enumerate(races) if get_race_number(r,i+1) == st.session_state.selected_race), races[0])
race_number = get_race_number(selected_race, 1)
st.session_state.selected_race = race_number

_current_race_signature = (str(st.session_state.get("loaded_date")), str(st.session_state.get("loaded_city")), int(race_number))
if st.session_state.get("_last_race_signature") != _current_race_signature:
    st.session_state.selected_horse_no = None
    st.session_state.selected_horse_index = None
    st.session_state.real_analysis_requested = True
    st.session_state.real_analysis_done = False
    st.session_state["_last_race_signature"] = _current_race_signature

# ============================================================
# SEÇİLİ KOŞU BAŞLIĞI
# ============================================================

race_time = display_value(selected_race.get("race_time"))
distance = display_value(selected_race.get("distance"))
surface = display_value(selected_race.get("surface"))
condition = get_race_condition(selected_race)

st.markdown(
    f"""<div class="tjk-race-head"><span class="time">{race_time}</span><span>|</span><span>{condition}</span><span>, {distance} {surface}</span><span class="info">ℹ</span></div>""",
    unsafe_allow_html=True,
)

# ============================================================
# MODEL BUTONLARI — EXPANDER DIŞINDA
# ============================================================

def _reset_model_weights():
    for criterion, value in DEFAULT_WEIGHTS.items():
        st.session_state[WEIGHT_KEYS[criterion]] = value
    st.session_state.analysis_mode = "Gerçek veri"
    st.session_state.real_analysis_requested = True
    st.session_state.real_analysis_done = False

def _request_real_analysis():
    st.session_state.analysis_mode = "Gerçek veri"
    st.session_state.real_analysis_requested = True
    st.session_state.real_analysis_done = False

def _request_manual_analysis():
    st.session_state.analysis_mode = "Manuel"
    st.session_state.real_analysis_requested = False
    st.session_state.real_analysis_done = True

st.markdown("<div class='model-actions'></div>", unsafe_allow_html=True)
a1, a2, a3, a4 = st.columns([1.2,1.2,1.15,1.6])
with a1:
    st.button("↩ Varsayılana Dön", key="reset_model_button", use_container_width=True, on_click=_reset_model_weights)
with a2:
    st.button("🔎 Gerçek Veri ile Analiz Et", key="real_analysis_button", use_container_width=True, on_click=_request_real_analysis)
with a3:
    st.button("🧠 Manuel Analiz", key="manual_analysis_button", use_container_width=True, on_click=_request_manual_analysis)
with a4:
    mode_label = st.session_state.get("analysis_mode", "Gerçek veri")
    cls = "model-real" if mode_label == "Gerçek veri" else "model-manual"
    st.markdown(f"<div style='text-align:right;padding:7px 0;color:#4d596a;font-size:12px'>Mod: <span class='model-state {cls}'>{mode_label}</span></div>", unsafe_allow_html=True)

# ============================================================
# CANLI MODEL AYARLARI — ANA TABLONUN HEMEN ÜSTÜNDE
# ============================================================

with st.expander("⚙️ CANLI MODEL AYARLARI", expanded=False):
    st.caption("Ağırlık değişiklikleri mevcut gerçek TJK verisi üzerinden yeniden hesaplanır.")
    cols = st.columns(4)
    for idx, (criterion, default_value) in enumerate(DEFAULT_WEIGHTS.items()):
        with cols[idx % 4]:
            st.slider(criterion, 0, 40, key=WEIGHT_KEYS[criterion], step=1)
    ANALYSIS_WEIGHTS = current_weights()
    total_w = sum(ANALYSIS_WEIGHTS.values())
    normalized = {k:(v*100/total_w if total_w else 0) for k,v in ANALYSIS_WEIGHTS.items()}
    st.caption(" • ".join(f"{k}: %{normalized[k]:.1f}" for k in ANALYSIS_WEIGHTS))

# ============================================================
# GERÇEK VERİ ANALİZİ
# ============================================================

horses = selected_race.get("horses", [])
if not isinstance(horses, list): horses = []

if not horses:
    st.warning("Seçilen koşuya ait at verisi yok.")
    st.stop()

if st.session_state.get("real_analysis_requested"):
    analysis_status = st.status("🔎 TJK gerçek geçmiş + galop verileri hazırlanıyor...", expanded=True)
    analysis_status.write(f"{len(horses)} koşan at sorgulanıyor...")
    try:
        horses = enrich_race_horses(horses)
        selected_race["horses"] = horses
        ok_count = sum(1 for h in horses if h.get("_history") or h.get("_workouts"))
        analysis_status.update(label=f"✅ Gerçek veri hazır • {ok_count}/{len(horses)} at", state="complete", expanded=False)
        st.session_state.real_analysis_done = True
    except Exception as exc:
        analysis_status.update(label="❌ Gerçek veri analizi hatası", state="error", expanded=True)
        st.error(str(exc))
    st.session_state.real_analysis_requested = False

ranking = calculate_ranking(horses, selected_race, selected_city)
by_index = {item["horse_index"]: item for item in ranking}

# ============================================================
# ANA TABLO VERİSİ
# ============================================================

target_year = selected_date.year
table_rows = []
for horse_index, horse in enumerate(horses):
    if not isinstance(horse, dict): continue
    r = by_index.get(horse_index, {"rank":999999,"score":0.0,"components":{}})
    owner = horse.get("owner") or ""
    trainer = horse.get("trainer") or ""
    for hist in horse.get("_history", []):
        if isinstance(hist, dict):
            owner = owner or hist.get("owner") or ""
            trainer = trainer or hist.get("trainer") or ""
            if owner and trainer: break
    sire, dam = _split_origin(get_horse_origin(horse))
    base_w, extra_w = _weight_parts(horse.get("siklet") or horse.get("weight"))
    jockey = get_horse_jockey(horse)
    jparts = jockey.split("\n",1)
    last6 = "".join(re.findall(r"[0-9Xx-]", get_horse_form(horse))) if get_horse_form(horse) != "-" else "-"
    table_rows.append({
        "_horse_index":horse_index,
        "_rank":int(r.get("rank",999999)),
        "No":get_horse_number(horse,horse_index+1),
        "At":get_horse_name(horse),
        "Ekipman":get_horse_equipment(horse),
        "Baba":sire,
        "Anne":dam,
        "Yaş":get_horse_age(horse),
        "Kilo":base_w,
        "Fazla":extra_w,
        "Jokey":jparts[0],
        "AP":jparts[1] if len(jparts)>1 else "",
        "Sahip":owner,
        "Antrenör":trainer,
        "St":get_horse_start(horse),
        "HP":get_horse_hp(horse),
        "Son6":last6,
        "KGS":get_horse_kgs(horse),
        "S20":display_value(horse.get("s20")),
        "EİD":display_value(horse.get("bestTime")),
        "Gny":display_value(horse.get("odds")),
        "AGF":get_horse_agf(horse),
        "BİZİM SKOR":float(r.get("score",0)),
        "ŞART UYUMU":float(calculate_sart_uyumu(horse,selected_race).get("score",50.0)),
        "GÜNCEL SINIF":float(calculate_guncel_sinif(horse)),
        "SON GALOP":workout_display(horse),
        "SON KOŞU":last_race_display(horse),
        "BU YIL":_format_tl(year_earnings(horse,target_year)),
        "TOPLAM":_format_tl(total_earnings(horse)),
    })

table_rows.sort(key=lambda x:(x["_rank"],str(x["No"])))

# ============================================================
# HTML ANA TABLO — 2. RESİMİN DÜZENİ
# ============================================================

def esc(v):
    import html
    return html.escape(str(v if v not in (None,"") else "-"))

def main_table_html(rows, selected_idx=None):
    widths = [42,175,58,150,88,120,145,42,48,62,48,54,68,65,75,95,95,95,100,100,115,120]
    headers = ["No","At İsmi","Yaş","Orijin (Baba-Anne)","Kilo","Jokey","Sahip / Antrenör","St","HP","Son 6","KGS","S20","EİD","Gny","AGF","BİZİM SKOR","ŞART UYUMU","GÜNCEL SINIF","SON GALOP","SON KOŞU","BU YIL KAZANÇ","TOPLAM KAZANÇ"]
    html=['<div class="tjk-table-wrap"><table class="tjk-main"><thead><tr>']
    for h,w in zip(headers,widths): html.append(f'<th style="width:{w}px;min-width:{w}px">{esc(h)}</th>')
    html.append('</tr></thead><tbody>')
    for row in rows:
        sel = ' selected' if selected_idx is not None and row['_horse_index']==selected_idx else ''
        # Whole row is a real selection link via Streamlit query parameter.
        href=f'?horse={row["_horse_index"]}'
        origin_html=''
        if row['Baba']: origin_html += f'<div class="tjk-origin-sire">{esc(row["Baba"])}</div>'
        if row['Anne']: origin_html += f'<div class="tjk-origin-dam">{esc(row["Anne"])}</div>'
        equip=f'<div class="tjk-equip">{esc(row["Ekipman"])}</div>' if row['Ekipman'] else ''
        weight=f'<div class="tjk-weight">{esc(row["Kilo"])}</div>' + (f'<div class="tjk-extra">{esc(row["Fazla"])}</div>' if row['Fazla'] else '')
        jockey=f'<div class="tjk-jockey">{esc(row["Jokey"])}</div>' + (f'<div class="tjk-ap">{esc(row["AP"])}</div>' if row['AP'] else '')
        owner=(f'<div class="tjk-small">{esc(row["Sahip"])}</div>' if row['Sahip'] else '') + (f'<div class="tjk-small">{esc(row["Antrenör"])}</div>' if row['Antrenör'] else '')
        horse_html=f'<a class="tjk-horse-link" href="{href}"><div class="tjk-horse-name">{esc(row["At"])}</div>{equip}</a>'
        cells=[
            f'<a class="tjk-horse-link" href="{href}">{esc(row["No"])}</a>',
            horse_html,
            esc(row['Yaş']), origin_html or "-", weight, jockey, owner, esc(row['St']), esc(row['HP']), esc(row['Son6']), esc(row['KGS']), esc(row['S20']),
            f'<span class="tjk-time">{esc(row["EİD"])}</span>', esc(row['Gny']), f'<span class="tjk-agf">{esc(row["AGF"])}</span>',
            f'<span class="tjk-score">{row["BİZİM SKOR"]:.2f}</span>', f'<span class="tjk-score">{row["ŞART UYUMU"]:.1f}</span>', f'<span class="tjk-score">{row["GÜNCEL SINIF"]:.1f}</span>',
            esc(row['SON GALOP']), esc(row['SON KOŞU']), esc(row['BU YIL']), esc(row['TOPLAM'])
        ]
        html.append(f'<tr class="{sel}">')
        for i,c in enumerate(cells):
            cls=' class="tjk-cell-left"' if i in (1,3,5,6) else ''
            html.append(f'<td{cls}>{c}</td>')
        html.append('</tr>')
    html.append('</tbody></table></div>')
    return ''.join(html)

# Query param ile satır seçimi. No yerine gerçek horse index kullanılır.
selected_idx=None
try:
    q=st.query_params.get("horse")
    if q not in (None,""):
        selected_idx=int(q)
except Exception:
    selected_idx=None
if selected_idx is not None and not any(r['_horse_index']==selected_idx for r in table_rows):
    selected_idx=None

st.markdown(main_table_html(table_rows,selected_idx), unsafe_allow_html=True)

# ============================================================
# SEÇİLEN AT — GERÇEK TJK GÖRÜNÜMÜ
# ============================================================

if selected_idx is not None:
    selected_horse = horses[selected_idx]
    st.session_state.selected_horse_index = selected_idx
    st.session_state.selected_horse_no = get_horse_number(selected_horse, selected_idx+1)
    # Satır tıklaması sonrası veri eksikse yalnız o at için gerçek veri çek.
    if not selected_horse.get("_history") and not selected_horse.get("_workouts"):
        try:
            one = enrich_race_horses([selected_horse])
            if one:
                horses[selected_idx]=one[0]
                selected_race["horses"]=horses
                selected_horse=horses[selected_idx]
        except Exception as exc:
            st.warning(f"Atın gerçek geçmişi alınamadı: {exc}")

    origin=get_horse_origin(selected_horse)
    sire,dam=_split_origin(origin)
    st.markdown(f'<div class="horse-detail-head">{esc(get_horse_name(selected_horse))} ({esc(get_horse_number(selected_horse,selected_idx+1))})</div>',unsafe_allow_html=True)
    st.markdown(f'<div class="horse-detail-sub"><b>{esc(sire)}</b>{" / "+esc(dam) if dam else ""} &nbsp; • &nbsp; Kazanç: {esc(_format_tl(total_earnings(selected_horse)))}</div>',unsafe_allow_html=True)

    hist=selected_horse.get("_history",[])
    if not isinstance(hist,list): hist=[]
    workouts=selected_horse.get("_workouts",[])
    if not isinstance(workouts,list): workouts=[]

    tab1,tab2,tab3,tab4=st.tabs(["Tüm Yarışları","1.'likleri","İstatistikler","Galoplar"])

    def history_html(rows):
        h=['<div class="detail-table-wrap"><table class="detail-table"><thead><tr>']
        cols=["Tarih","Şehir","Msf","Pist","Sonuç","K Cinsi","Grup","Derece","Jokey","Kilo","Takı","St","HP","Sahip / Antr.","AGF","Gny","İkramiye"]
        for c in cols:h.append(f'<th>{esc(c)}</th>')
        h.append('</tr></thead><tbody>')
        for r in rows:
            if not isinstance(r,dict): continue
            place=_first_value(r,["place","sira","S"])
            owner=_first_value(r,["owner","sahip"]); trainer=_first_value(r,["trainer","antrenor"])
            ownerantr=f'{owner}<br>{trainer}' if owner or trainer else '-'
            prize=_first_value(r,["prize","ikramiye"])
            cells=[_first_value(r,["date","tarih"]),_first_value(r,["city","şehir"]),_first_value(r,["distance","msf"]),_first_value(r,["surface","pist"]),place,_first_value(r,["className","class","sinif"]),_first_value(r,["group","grup"]),_first_value(r,["time","derece"]),_first_value(r,["jockey","jokey"]),_first_value(r,["weight","kilo"]),_first_value(r,["equipment","taki"]),_first_value(r,["post","st"]),_first_value(r,["hp","HP"]),ownerantr,_first_value(r,["agf","AGF"]),_first_value(r,["odds","gny"]),prize]
            h.append('<tr>')
            for i,c in enumerate(cells):
                cls='result' if i==4 else ('blue' if i in (1,8) else ('green' if i==14 else ''))
                h.append(f'<td class="{cls}">{c if "<br>" in str(c) else esc(c)}</td>')
            h.append('</tr>')
        h.append('</tbody></table></div>')
        return ''.join(h)

    with tab1:
        st.markdown(history_html(hist),unsafe_allow_html=True)
    with tab2:
        wins=[r for r in hist if isinstance(r,dict) and str(_first_value(r,["place","sira","S"])).strip() in {"1","1."}]
        st.markdown(history_html(wins),unsafe_allow_html=True)
        if not wins: st.info("Gerçek geçmişte 1.'lik kaydı bulunamadı.")
    with tab3:
        def place_num(r):
            s=str(_first_value(r,["place","sira","S"])); m=re.search(r"\d+",s); return int(m.group()) if m else None
        places=[place_num(r) for r in hist if isinstance(r,dict)]
        valid=[x for x in places if x is not None]
        stats=[("TOPLAM",len(hist)),("1.'lik",sum(x==1 for x in valid)),("2.'lik",sum(x==2 for x in valid)),("3.'lük",sum(x==3 for x in valid)),("4.'lük",sum(x==4 for x in valid)),("5.'lik",sum(x==5 for x in valid))]
        st.markdown('<div class="stats-grid">'+''.join(f'<div class="stat-card"><div class="v">{v}</div><div class="l">{l}</div></div>' for l,v in stats)+'</div>',unsafe_allow_html=True)
        st.markdown(f'<div class="stats-grid">{("<div class=\"stat-card\"><div class=\"v\">"+esc(_format_tl(total_earnings(selected_horse)))+"</div><div class=\"l\">TOPLAM KAZANÇ</div></div>")}{("<div class=\"stat-card\"><div class=\"v\">"+esc(_format_tl(year_earnings(selected_horse,target_year)))+"</div><div class=\"l\">{target_year} KAZANÇ</div></div>")}</div>',unsafe_allow_html=True)
    with tab4:
        rows=[]
        for w in workouts:
            if not isinstance(w,dict): continue
            rows.append([_first_value(w,["date","tarih"]),_first_value(w,["city","şehir"]),_first_value(w,["jockey","jokey","rider","binici"]),_first_value(w,["m1200","1200"]),_first_value(w,["m1000","1000"]),_first_value(w,["m800","800"]),_first_value(w,["m600","600"]),_first_value(w,["m400","400"]),_first_value(w,["type","tur","Tür"]),_first_value(w,["surface","pist"]),_first_value(w,["note","not","aciklama"])])
        hh=['<div class="detail-table-wrap"><table class="detail-table"><thead><tr>']
        for c in ["Tarih","Şehir","İ.Jokey","1200","1000","800","600","400","Çalışma","Pist","Not"]: hh.append(f'<th>{c}</th>')
        hh.append('</tr></thead><tbody>')
        for row in rows:
            hh.append('<tr>'+''.join(f'<td>{esc(v)}</td>' for v in row)+'</tr>')
        hh.append('</tbody></table></div>')
        st.markdown(''.join(hh),unsafe_allow_html=True)
        if not rows: st.info("Bu at için gerçek TJK galop kaydı bulunamadı.")

# ============================================================
# ALT SİSTEM DURUMU / DEBUG
# ============================================================

with st.expander("⚙️ Sistem Durumu", expanded=False):
    total_horses=sum(len(r.get("horses",[])) for r in races if isinstance(r,dict))
    c1,c2,c3,c4=st.columns(4)
    c1.metric("TJK bağlantısı","OK")
    c2.metric("Koşu sayısı",len(races))
    c3.metric("Toplam at",total_horses)
    c4.metric("Hipodrom",selected_city)

with st.expander("🔧 Teknik Debug", expanded=False):
    st.json(program_data.get("debug",{}))

with st.expander("📦 Ham At Verisi", expanded=False):
    st.json(horses)
