import streamlit as st
from datetime import date
from typing import Any, Dict, List

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
# SABİTLER
# ============================================================

ALL_CITIES = [
    "Adana",
    "İzmir",
    "İstanbul",
    "Bursa",
    "Ankara",
    "Şanlıurfa",
    "Elazığ",
    "Diyarbakır",
    "Kocaeli",
]


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

if "selected_race" not in st.session_state:
    st.session_state.selected_race = 1

if "program_data" not in st.session_state:
    st.session_state.program_data = None

if "loaded_date" not in st.session_state:
    st.session_state.loaded_date = None

if "loaded_city" not in st.session_state:
    st.session_state.loaded_city = None


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>

    .main-title {
        font-size: 32px;
        font-weight: 700;
        margin-bottom: 0px;
    }

    .sub-title {
        font-size: 15px;
        opacity: 0.75;
        margin-top: 0px;
        margin-bottom: 20px;
    }

    .race-info {
        padding: 12px 15px;
        border-radius: 8px;
        border: 1px solid rgba(128,128,128,0.25);
        margin-bottom: 15px;
    }

    .horse-card {
        padding: 12px;
        border-radius: 8px;
        border: 1px solid rgba(128,128,128,0.25);
        margin-bottom: 8px;
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
# YARDIMCI FONKSİYONLAR
# ============================================================

@st.cache_data(ttl=900, show_spinner=False)
def load_program(
    selected_date: date,
    city: str,
) -> Dict[str, Any]:
    """
    TJK programını getirir.
    """

    return get_program(
        selected_date,
        city,
    )


@st.cache_data(ttl=900, show_spinner=False)
def find_active_cities(
    selected_date: date,
) -> List[str]:
    """
    Seçilen tarihte gerçekten yarış programı bulunan
    hipodromları bulur.
    """

    active = []

    for city in ALL_CITIES:

        try:

            result = load_program(
                selected_date,
                city,
            )

            races = result.get(
                "races",
                [],
            )

            if races:
                active.append(city)

        except Exception:
            continue

    return active


def safe_int(value: Any):
    """
    Güvenli integer dönüşümü.
    """

    if value is None:
        return None

    text = str(value).strip()

    try:
        return int(float(text))
    except Exception:
        return None


def safe_float(value: Any):
    """
    Güvenli float dönüşümü.
    """

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    text = text.replace("%", "")
    text = text.replace(",", ".")

    try:
        return float(text)
    except Exception:
        return None


def display_value(
    value: Any,
    default: str = "-",
) -> str:
    """
    Boş değerleri '-' olarak gösterir.
    """

    if value is None:
        return default

    text = str(value).strip()

    if not text:
        return default

    return text


def get_horse_name(
    horse: Dict[str, Any],
) -> str:
    return display_value(
        horse.get("at_ismi")
        or horse.get("At İsmi")
    )


def get_horse_number(
    horse: Dict[str, Any],
) -> str:
    return display_value(
        horse.get("numara")
        or horse.get("N")
    )


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


def get_horse_form(
    horse: Dict[str, Any],
) -> str:
    return display_value(
        horse.get("form")
        or horse.get("Forma")
    )


def get_horse_st(
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


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("🏇 Yarış Programı")

selected_date = st.sidebar.date_input(
    "Tarih",
    value=date.today(),
)


# ============================================================
# AKTİF HİPODROMLARI BUL
# ============================================================

with st.sidebar:

    with st.spinner(
        "Yarış yapılan hipodromlar kontrol ediliyor..."
    ):

        active_cities = find_active_cities(
            selected_date
        )


if not active_cities:

    st.warning(
        f"{selected_date.strftime('%d.%m.%Y')} "
        "tarihinde yarış programı alınamadı."
    )

    st.info(
        "Tarih seçimini kontrol edin veya birkaç saniye sonra tekrar deneyin."
    )

    st.stop()


# ============================================================
# HİPODROM SEÇİMİ
# ============================================================

default_city_index = 0

if (
    st.session_state.loaded_city
    in active_cities
):
    default_city_index = active_cities.index(
        st.session_state.loaded_city
    )

selected_city = st.sidebar.selectbox(
    "Hipodrom",
    active_cities,
    index=default_city_index,
)


# ============================================================
# PROGRAMI GETİR BUTONU
# ============================================================

get_program_button = st.sidebar.button(
    "📥 PROGRAMI GETİR",
    use_container_width=True,
)


if get_program_button:

    with st.spinner(
        f"{selected_city} programı getiriliyor..."
    ):

        try:

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
# PROGRAM VERİSİ
# ============================================================

program_data = st.session_state.program_data


# Tarih veya hipodrom değiştiyse mevcut veriyi kullanma
if (
    program_data is not None
    and (
        st.session_state.loaded_date
        != selected_date
        or st.session_state.loaded_city
        != selected_city
    )
):

    program_data = None


# ============================================================
# OTOMATİK PROGRAM GETİR
# ============================================================

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

    except Exception as exc:

        st.error(
            "Beklenmeyen hata oluştu."
        )

        st.code(
            f"{type(exc).__name__}: {exc}"
        )

        st.stop()


# ============================================================
# PROGRAM KONTROLÜ
# ============================================================

if not isinstance(
    program_data,
    dict,
):

    st.error(
        "TJK'dan gelen program verisi geçersiz."
    )

    st.stop()


races = program_data.get(
    "races",
    [],
)


if not races:

    st.warning(
        f"{selected_city} — "
        f"{selected_date.strftime('%d.%m.%Y')} "
        "için koşu bulunamadı."
    )

    st.stop()


# ============================================================
# ÜST BİLGİ
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


# Çok fazla koşu varsa yatay kolonları küçült
race_columns = st.columns(
    len(races)
)


for index, race in enumerate(races):

    race_number = race.get(
        "race_number",
        index + 1,
    )

    race_time = display_value(
        race.get(
            "race_time"
        )
    )

    is_selected = (
        st.session_state.selected_race
        == race_number
    )

    button_label = str(
        race_number
    )

    if race_time != "-":
        button_label = (
            f"{race_number}\n"
            f"{race_time}"
        )

    with race_columns[index]:

        if st.button(
            button_label,
            key=f"race_button_{race_number}",
            use_container_width=True,
            type=(
                "primary"
                if is_selected
                else "secondary"
            ),
        ):

            st.session_state.selected_race = (
                race_number
            )

            st.rerun()


# ============================================================
# SEÇİLİ KOŞUYU BUL
# ============================================================

selected_race = None

for race in races:

    if (
        race.get("race_number")
        == st.session_state.selected_race
    ):

        selected_race = race

        break


# Eğer seçili yarış bulunamazsa ilk yarışı seç
if selected_race is None:

    selected_race = races[0]

    st.session_state.selected_race = (
        selected_race.get(
            "race_number",
            1,
        )
    )


# ============================================================
# KOŞU BİLGİLERİ
# ============================================================

race_number = selected_race.get(
    "race_number",
    "-",
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

condition = display_value(
    selected_race.get(
        "condition"
    )
)


st.markdown(
    "---"
)

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

    st.metric(
        "Şart",
        condition,
    )


# ============================================================
# ATLAR
# ============================================================

horses = selected_race.get(
    "horses",
    [],
)


st.subheader(
    f"Atlar ({len(horses)})"
)


if not horses:

    st.warning(
        "Seçilen koşuya ait at verisi henüz alınmadı."
    )

else:

    # --------------------------------------------------------
    # TABLO BAŞLIĞI
    # --------------------------------------------------------

    header_columns = st.columns(
        [
            0.5,
            2.2,
            0.7,
            1.2,
            1.8,
            0.8,
            0.9,
            1.0,
            0.9,
            0.9,
        ]
    )

    headers = [
        "No",
        "At",
        "Yaş",
        "Kilo",
        "Jokey",
        "HP",
        "AGF",
        "St",
        "KGS",
        "Form",
    ]

    for column, header in zip(
        header_columns,
        headers,
    ):

        with column:
            st.markdown(
                f"**{header}**"
            )


    # --------------------------------------------------------
    # AT SATIRLARI
    # --------------------------------------------------------

    for horse_index, horse in enumerate(
        horses
    ):

        columns = st.columns(
            [
                0.5,
                2.2,
                0.7,
                1.2,
                1.8,
                0.8,
                0.9,
                1.0,
                0.9,
                0.9,
            ]
        )

        horse_number = get_horse_number(
            horse
        )

        if horse_number == "-":
            horse_number = str(
                horse_index + 1
            )

        horse_name = get_horse_name(
            horse
        )

        horse_age = display_value(
            horse.get("yas")
            or horse.get("Yaş")
        )

        horse_weight = get_horse_weight(
            horse
        )

        horse_jockey = get_horse_jockey(
            horse
        )

        horse_hp = get_horse_hp(
            horse
        )

        horse_agf = get_horse_agf(
            horse
        )

        horse_st = get_horse_st(
            horse
        )

        horse_kgs = get_horse_kgs(
            horse
        )

        horse_form = get_horse_form(
            horse
        )

        values = [
            horse_number,
            horse_name,
            horse_age,
            horse_weight,
            horse_jockey,
            horse_hp,
            horse_agf,
            horse_st,
            horse_kgs,
            horse_form,
        ]

        for column, value in zip(
            columns,
            values,
        ):

            with column:

                st.write(
                    display_value(value)
                )

        st.divider()


# ============================================================
# ANALİZ SİSTEMİ
# ============================================================

st.markdown(
    "---"
)

st.subheader(
    "🧠 Analiz Sistemi"
)


st.write(
    "Yarış değerlendirmesinde kullanılacak ağırlıklar:"
)


weight_columns = st.columns(4)


weight_items = list(
    ANALYSIS_WEIGHTS.items()
)


for index, (
    criterion,
    weight,
) in enumerate(
    weight_items
):

    column = weight_columns[
        index % 4
    ]

    with column:

        st.metric(
            criterion,
            f"%{weight}",
        )


# ============================================================
# AĞIRLIK TOPLAMI
# ============================================================

raw_weight_total = sum(
    ANALYSIS_WEIGHTS.values()
)

normalized_total = (
    raw_weight_total
)


st.info(
    f"Ham ağırlık toplamı: "
    f"%{raw_weight_total}. "
    f"Final puanlama bu toplam üzerinden "
    f"normalize edilecektir."
)


# ============================================================
# SİSTEM DURUMU
# ============================================================

st.markdown(
    "---"
)

st.subheader(
    "⚙️ Sistem Durumu"
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

    total_horses = sum(
        len(
            race.get(
                "horses",
                [],
            )
        )
        for race in races
    )

    st.metric(
        "Toplam at",
        total_horses,
    )


with status4:

    st.metric(
        "Aktif hipodrom",
        len(active_cities),
    )


# ============================================================
# DEBUG
# ============================================================

with st.expander(
    "🔧 Teknik Debug"
):

    debug = program_data.get(
        "debug",
        {},
    )

    st.write(
        "Program sonucu:"
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
