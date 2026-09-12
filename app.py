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

ANALYSIS_WEIGHTS = {
    "Pist / Mesafe": 22,
    "Ortak Rakip": 18,
    "Sınıf / HP": 14,
    "Güncel Form": 19,
    "Kilo": 12,
    "Derece": 8,
    "Galop / Tempo": 5,
    "Ham Hız": 3,
}


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

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# BAŞLIK
# ============================================================

st.markdown(
    '<div class="main-title">🏇 Race Intelligence</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="sub-title">'
    "TJK yarış programı ve yarış analiz sistemi"
    "</div>",
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

    compact = re.sub(r"\s+", "", text.lower())
    match = re.match(r"^(\d+)y([dk])([ea])$", compact)
    if match:
        age, sex_code, breed_code = match.groups()
        sex = {"d": "Dişi", "k": "Erkek"}.get(sex_code, sex_code)
        breed = {"e": "İngiliz", "a": "Arap"}.get(breed_code, breed_code)
        return f"{age}y {sex} {breed}"

    # Bazı kaynaklarda boşluklu/uzun yazım gelebilir.
    match = re.match(r"^(\d+)y?([dk])([ea])?$", compact)
    if match:
        age, sex_code, breed_code = match.groups()
        sex = {"d": "Dişi", "k": "Erkek"}.get(sex_code, sex_code)
        breed = {"e": "İngiliz", "a": "Arap"}.get(breed_code, breed_code or "")
        return f"{age}y {sex}" + (f" {breed}" if breed else "")

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
# KOŞU BİLGİLERİ
# ============================================================

race_number = get_race_number(
    selected_race,
    1,
)

race_time = display_value(
    selected_race.get(
        "race_time"
    )
)

distance = display_value(
    selected_race.get(
        "distance"
    )
)

surface = display_value(
    selected_race.get(
        "surface"
    )
)

condition = get_race_condition(selected_race)


st.markdown("---")


st.subheader(
    f"{race_number}. Koşu"
)


info1, info2, info3, info4 = st.columns(4)


with info1:

    st.metric(
        "Saat",
        race_time,
    )


with info2:

    st.metric(
        "Mesafe",
        distance,
    )


with info3:

    st.metric(
        "Pist",
        surface,
    )


with info4:

    st.markdown("**Şart**")
    st.write(condition)


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

    table_rows = []

    for horse_index, horse in enumerate(horses):
        if not isinstance(horse, dict):
            continue

        form = get_horse_form(horse)
        form_digits = " ".join(re.findall(r"[0-9Xx-]", form)) if form != "-" else "-"

        table_rows.append({
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
        })

    df = pd.DataFrame(table_rows)

    def form_row_style(row):
        styles = [""] * len(row)
        form_value = str(row.get("Form", ""))
        digits = [int(x) for x in re.findall(r"[1-9]", form_value)]
        if not digits:
            return styles
        avg = sum(digits) / len(digits)
        if avg <= 3:
            style = "font-weight:700; background-color: rgba(46, 160, 67, 0.14);"
        elif avg <= 5:
            style = "background-color: rgba(255, 193, 7, 0.10);"
        else:
            style = "background-color: rgba(220, 53, 69, 0.08);"
        return [style] * len(row)

    styled = df.style.apply(form_row_style, axis=1)

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=min(520, 44 + max(1, len(table_rows)) * 42),
        column_config={
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
        },
    )

    agf_values = [get_horse_agf(h) for h in horses if isinstance(h, dict)]
    if agf_values and all(v == "-" for v in agf_values):
        st.caption("AGF: TJK program kaynağında bu koşu için henüz değer yok; '-' gösteriliyor. Değer uydurulmaz.")


# ============================================================
# ANALİZ SİSTEMİ
# ============================================================

st.markdown("---")


st.subheader(
    "🧠 Analiz Sistemi"
)


st.write(
    "Yarış değerlendirmesinde kullanılacak kriter ağırlıkları:"
)


weight_columns = st.columns(4)


for index, (
    criterion,
    weight,
) in enumerate(
    ANALYSIS_WEIGHTS.items()
):

    with weight_columns[
        index % 4
    ]:

        st.metric(
            criterion,
            f"%{weight}",
        )


# ============================================================
# AĞIRLIK TOPLAMI
# ============================================================

weight_total = sum(
    ANALYSIS_WEIGHTS.values()
)


st.info(
    f"Ham ağırlık toplamı: %{weight_total}. "
    "Final skorunda bu toplam normalize edilecektir."
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
