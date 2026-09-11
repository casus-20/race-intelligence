import streamlit as st
from datetime import date

from worker.tjk_fetch import (
    get_program,
    TJKFetchError
)


# =========================================================
# SAYFA AYARLARI
# =========================================================

st.set_page_config(
    page_title="Race-Intelligence",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="expanded"
)


# =========================================================
# ANALİZ AĞIRLIKLARI
# =========================================================

WEIGHTS = {
    "Pist / Mesafe": 22,
    "Ortak Rakip": 18,
    "Sınıf / HP": 14,
    "Form": 19,
    "Kilo": 12,
    "Derece": 8,
    "Galop / Tempo": 5,
    "Hız": 3,
}


# =========================================================
# TÜM TJK HİPODROMLARI
# =========================================================

ALL_CITIES = [
    "Adana",
    "Ankara",
    "Bursa",
    "Diyarbakır",
    "Elazığ",
    "İstanbul",
    "İzmir",
    "Kocaeli",
    "Şanlıurfa",
]


# =========================================================
# SESSION STATE
# =========================================================

if "program_data" not in st.session_state:
    st.session_state.program_data = None

if "active_cities" not in st.session_state:
    st.session_state.active_cities = None

if "active_cities_date" not in st.session_state:
    st.session_state.active_cities_date = None

if "selected_date" not in st.session_state:
    st.session_state.selected_date = date.today()

if "selected_city" not in st.session_state:
    st.session_state.selected_city = None

if "selected_race" not in st.session_state:
    st.session_state.selected_race = None

if "race_data" not in st.session_state:
    st.session_state.race_data = None

if "horse_data" not in st.session_state:
    st.session_state.horse_data = []

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

if "in_flight" not in st.session_state:
    st.session_state.in_flight = False


# =========================================================
# TARİHE GÖRE KOŞAN HİPODROMLARI BUL
# =========================================================

@st.cache_data(
    ttl=900,
    show_spinner=False
)
def find_active_cities(selected_date):
    """
    Seçilen tarihte gerçekten yarış programı bulunan
    hipodromları TJK üzerinden belirler.

    Sonuç sadece şehir isimlerinden oluşur.
    Böylece büyük HTML verileri session/cache içine
    taşınmaz.
    """

    active = []

    for city in ALL_CITIES:

        try:

            result = get_program(
                selected_date,
                city
            )

            races = result.get(
                "races",
                []
            )

            if races:

                active.append(city)

        except Exception:

            # Bir hipodromdan veri alınamazsa diğerlerini
            # kontrol etmeye devam et.
            continue

    return active


# =========================================================
# SEÇİLEN TARİH İÇİN HİPODROMLARI HAZIRLA
# =========================================================

current_date = st.session_state.selected_date


if (
    st.session_state.active_cities is None
    or
    st.session_state.active_cities_date != current_date
):

    with st.spinner(
        "Seçilen tarihte yarış olan hipodromlar kontrol ediliyor..."
    ):

        active_cities = find_active_cities(
            current_date
        )

    st.session_state.active_cities = (
        active_cities
    )

    st.session_state.active_cities_date = (
        current_date
    )


active_cities = (
    st.session_state.active_cities
    or []
)


# =========================================================
# İLK AKTİF HİPODROMU SEÇ
# =========================================================

if active_cities:

    if (
        st.session_state.selected_city
        not in active_cities
    ):

        st.session_state.selected_city = (
            active_cities[0]
        )

else:

    st.session_state.selected_city = None


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.header("🗓️ Yarış Programı")

    new_date = st.date_input(
        "Tarih",
        value=st.session_state.selected_date,
        format="DD/MM/YYYY"
    )


    # -----------------------------------------------------
    # TARİH DEĞİŞTİYSE AKTİF HİPODROMLARI YENİLE
    # -----------------------------------------------------

    if new_date != st.session_state.selected_date:

        st.session_state.selected_date = new_date

        st.session_state.program_data = None
        st.session_state.selected_race = None
        st.session_state.race_data = None
        st.session_state.horse_data = []
        st.session_state.analysis_result = None

        st.session_state.active_cities = None
        st.session_state.active_cities_date = None

        st.rerun()


    # -----------------------------------------------------
    # SADECE O GÜN KOŞAN HİPODROMLAR
    # -----------------------------------------------------

    if active_cities:

        selected_city = st.selectbox(
            "Hipodrom",
            active_cities,
            index=(
                active_cities.index(
                    st.session_state.selected_city
                )
                if st.session_state.selected_city
                in active_cities
                else 0
            )
        )

        st.session_state.selected_city = (
            selected_city
        )

    else:

        st.error(
            "Bu tarihte programı alınabilen "
            "aktif hipodrom bulunamadı."
        )

        selected_city = None


    st.divider()


    # -----------------------------------------------------
    # PROGRAM BUTONU
    # -----------------------------------------------------

    get_program_button = st.button(
        "🔄 PROGRAMI GETİR",
        use_container_width=True,
        type="primary",
        disabled=not bool(active_cities)
    )


# =========================================================
# ANA BAŞLIK
# =========================================================

st.title("🏇 Race-Intelligence")

st.caption(
    "TJK Yarış Analiz Platformu"
)


# =========================================================
# AKTİF HİPODROMLAR BİLGİSİ
# =========================================================

if active_cities:

    st.caption(
        "Bugün yarış olan hipodromlar: "
        + " • ".join(active_cities)
    )


# =========================================================
# PROGRAMI GETİR
# =========================================================

if (
    get_program_button
    and selected_city
):

    st.session_state.in_flight = True

    try:

        with st.spinner(
            f"{selected_city} programı TJK'dan alınıyor..."
        ):

            program = get_program(
                st.session_state.selected_date,
                selected_city
            )

        st.session_state.program_data = (
            program
        )

        st.session_state.selected_race = None
        st.session_state.race_data = None
        st.session_state.horse_data = []
        st.session_state.analysis_result = None

        st.session_state.in_flight = False

        if program.get("ok", False):

            st.success(
                f"{selected_city} programı alındı."
            )

        else:

            st.warning(
                "TJK programı alındı ancak "
                "ayrıştırma sırasında sorun oluştu."
            )

    except TJKFetchError as exc:

        st.session_state.in_flight = False

        st.error(
            "TJK bağlantı hatası: "
            + str(exc)
        )

    except Exception as exc:

        st.session_state.in_flight = False

        st.error(
            "Beklenmeyen hata: "
            + str(exc)
        )


# =========================================================
# PROGRAM VERİSİ
# =========================================================

program_data = (
    st.session_state.program_data
)


if program_data is not None:

    races = program_data.get(
        "races",
        []
    )


    # =====================================================
    # YARIŞ PROGRAMI
    # =====================================================

    st.divider()

    st.header("📋 Yarış Programı")

    st.success(
        f"{st.session_state.selected_city} — "
        f"{st.session_state.selected_date.strftime('%d/%m/%Y')} "
        f"— {len(races)} koşu bulundu."
    )


    # =====================================================
    # TJK PARSER DEBUG
    # =====================================================

    debug_data = program_data.get(
        "debug",
        {}
    )

    if debug_data:

        with st.expander(
            "🔧 TJK Parser Debug",
            expanded=False
        ):

            col1, col2, col3 = st.columns(3)

            with col1:

                st.metric(
                    "HTML",
                    debug_data.get(
                        "html_length",
                        0
                    )
                )

            with col2:

                st.metric(
                    "Görünen metin",
                    debug_data.get(
                        "visible_text_length",
                        0
                    )
                )

            with col3:

                st.metric(
                    "HTML table",
                    debug_data.get(
                        "table_count",
                        0
                    )
                )


            col1, col2, col3, col4 = st.columns(4)

            with col1:

                st.write(
                    "Koşu:",
                    "✅"
                    if debug_data.get(
                        "has_kosu_text",
                        False
                    )
                    else "❌"
                )

            with col2:

                st.write(
                    "At İsmi:",
                    "✅"
                    if debug_data.get(
                        "has_at_ismi_text",
                        False
                    )
                    else "❌"
                )

            with col3:

                st.write(
                    "Jokey:",
                    "✅"
                    if debug_data.get(
                        "has_jokey_text",
                        False
                    )
                    else "❌"
                )

            with col4:

                st.write(
                    "Koşu regex:",
                    debug_data.get(
                        "race_pattern_count",
                        0
                    )
                )


            col1, col2, col3, col4 = st.columns(4)

            with col1:

                st.write(
                    "H1:",
                    debug_data.get(
                        "h1_count",
                        0
                    )
                )

            with col2:

                st.write(
                    "H2:",
                    debug_data.get(
                        "h2_count",
                        0
                    )
                )

            with col3:

                st.write(
                    "H3:",
                    debug_data.get(
                        "h3_count",
                        0
                    )
                )

            with col4:

                st.write(
                    "H4:",
                    debug_data.get(
                        "h4_count",
                        0
                    )
                )


            col1, col2 = st.columns(2)

            with col1:

                st.metric(
                    "Bulunan at tablosu",
                    debug_data.get(
                        "horse_table_count",
                        0
                    )
                )

            with col2:

                st.metric(
                    "Ayrıştırılan koşu",
                    debug_data.get(
                        "parsed_race_count",
                        0
                    )
                )


            parse_error = program_data.get(
                "parse_error"
            )

            if parse_error:

                st.error(
                    "Parser hatası: "
                    + str(parse_error)
                )


            html_start = debug_data.get(
                "html_start",
                ""
            )

            if html_start:

                show_html = st.checkbox(
                    "TJK HTML başlangıcını göster",
                    value=False
                )

                if show_html:

                    st.code(
                        html_start,
                        language="html"
                    )


    # =====================================================
    # KOŞULAR
    # =====================================================

    if races:

        st.divider()

        st.subheader(
            "🏁 Koşu Seç"
        )


        # -------------------------------------------------
        # YATAY KOŞU BUTONLARI
        # -------------------------------------------------

        race_columns = st.columns(
            len(races)
        )


        current_race_number = None

        if st.session_state.selected_race:

            current_race_number = (
                st.session_state.selected_race.get(
                    "race_number"
                )
            )


        for index, race in enumerate(
            races
        ):

            race_number = race.get(
                "race_number",
                index + 1
            )

            race_time = race.get(
                "race_time",
                ""
            )


            if race_time:

                button_label = (
                    f"{race_number}\n"
                    f"{race_time}"
                )

            else:

                button_label = (
                    f"{race_number}"
                )


            is_selected = (
                current_race_number
                == race_number
            )


            with race_columns[index]:

                if is_selected:

                    clicked = st.button(
                        button_label,
                        key=(
                            f"race_selected_"
                            f"{race_number}"
                        ),
                        use_container_width=True,
                        type="primary"
                    )

                else:

                    clicked = st.button(
                        button_label,
                        key=(
                            f"race_"
                            f"{race_number}"
                        ),
                        use_container_width=True
                    )


                if clicked:

                    st.session_state.selected_race = (
                        race
                    )

                    st.session_state.race_data = (
                        race
                    )

                    st.session_state.horse_data = (
                        race.get(
                            "horses",
                            []
                        )
                    )

                    st.session_state.analysis_result = (
                        None
                    )

                    st.rerun()


        # -------------------------------------------------
        # İLK KOŞUYU OTOMATİK SEÇ
        # -------------------------------------------------

        if st.session_state.selected_race is None:

            first_race = races[0]

            st.session_state.selected_race = (
                first_race
            )

            st.session_state.race_data = (
                first_race
            )

            st.session_state.horse_data = (
                first_race.get(
                    "horses",
                    []
                )
            )


        # -------------------------------------------------
        # SEÇİLEN KOŞU
        # -------------------------------------------------

        selected_race = (
            st.session_state.selected_race
        )

        selected_race_number = (
            selected_race.get(
                "race_number"
            )
        )


        # Güncel race objesini bul
        for race in races:

            if race.get(
                "race_number"
            ) == selected_race_number:

                selected_race = race

                st.session_state.selected_race = (
                    race
                )

                st.session_state.race_data = (
                    race
                )

                st.session_state.horse_data = (
                    race.get(
                        "horses",
                        []
                    )
                )

                break


        # =================================================
        # SEÇİLEN KOŞU BİLGİLERİ
        # =================================================

        st.divider()

        st.header(
            f"🏇 {selected_race_number}. Koşu"
        )


        col1, col2, col3, col4 = st.columns(4)

        with col1:

            st.metric(
                "Koşu",
                str(
                    selected_race.get(
                        "race_number",
                        "-"
                    )
                )
            )

        with col2:

            st.metric(
                "Saat",
                selected_race.get(
                    "race_time",
                    "-"
                ) or "-"
            )

        with col3:

            st.metric(
                "Mesafe",
                selected_race.get(
                    "distance",
                    "-"
                ) or "-"
            )

        with col4:

            st.metric(
                "Pist",
                selected_race.get(
                    "surface",
                    "-"
                ) or "-"
            )


        # -------------------------------------------------
        # KOŞU ŞARTI
        # -------------------------------------------------

        race_condition = selected_race.get(
            "race_condition",
            ""
        )

        if race_condition:

            st.info(
                "Koşu şartı: "
                + str(race_condition)
            )


        # =================================================
        # ATLAR
        # =================================================

        st.divider()

        st.header("🐎 Atlar")

        horses = selected_race.get(
            "horses",
            []
        )


        if horses:

            st.success(
                f"{len(horses)} at verisi bulundu."
            )

            horse_rows = []

            for horse in horses:

                row = dict(horse)

                row.pop(
                    "at_ismi",
                    None
                )

                horse_rows.append(
                    row
                )


            if horse_rows:

                st.dataframe(
                    horse_rows,
                    use_container_width=True,
                    hide_index=True
                )

        else:

            st.info(
                "Seçilen koşuya ait at verisi "
                "henüz alınmadı."
            )


    # =====================================================
    # KOŞU BULUNAMADI
    # =====================================================

    else:

        st.warning(
            "Program sayfası açıldı fakat "
            "koşu verisi ayrıştırılamadı."
        )


# =========================================================
# PROGRAM YÜKLENMEDİYSE
# =========================================================

elif not active_cities:

    st.warning(
        "Seçilen tarihte yarış programı "
        "bulunamadı."
    )


# =========================================================
# ANALİZ MOTORU
# =========================================================

st.divider()

st.header("🧠 Analiz Motoru")


# =========================================================
# AĞIRLIKLAR
# =========================================================

weight_items = list(
    WEIGHTS.items()
)


for row_start in range(
    0,
    len(weight_items),
    4
):

    columns = st.columns(4)

    row_items = weight_items[
        row_start:row_start + 4
    ]


    for index, (
        name,
        weight
    ) in enumerate(row_items):

        with columns[index]:

            st.metric(
                name,
                f"%{weight}"
            )


st.caption(
    "Ağırlık toplamı: %101 — "
    "nihai skor hesaplamasında "
    "100 puana normalize edilecektir."
)


# =========================================================
# SİSTEM DURUMU
# =========================================================

st.divider()

st.header("⚙️ Sistem Durumu")

status_columns = st.columns(4)


with status_columns[0]:

    st.success(
        "Streamlit\n\nÇalışıyor"
    )


with status_columns[1]:

    if program_data is not None:

        st.success(
            "TJK Fetch\n\nBağlı"
        )

    else:

        st.warning(
            "TJK Fetch\n\nBekliyor"
        )


with status_columns[2]:

    st.warning(
        "Cache\n\nSıradaki aşama"
    )


with status_columns[3]:

    st.warning(
        "Analiz\n\nSıradaki aşama"
    )


# =========================================================
# MİMARİ DURUMU
# =========================================================

st.divider()

with st.expander(
    "ℹ️ Race-Intelligence Mimari Durumu",
    expanded=False
):

    st.markdown(
        """
### Worker Katmanı

- TJK Fetch
- Cache
- Horse-data cache
- Request dedup
- Kontrollü concurrency
- Temiz API

### Analiz Katmanı

- Pist / Mesafe — **%22**
- Ortak Rakip — **%18**
- Sınıf / HP — **%14**
- Form — **%19**
- Kilo — **%12**
- Derece — **%8**
- Galop / Tempo — **%5**
- Hız — **%3**

### Skor Normalizasyonu

**Nihai Skor = HAM SKOR / 101 × 100**
"""
    )
