import streamlit as st
from datetime import date, datetime

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
    layout="wide"
)


# =========================================================
# BAŞLIK
# =========================================================

st.title("🏇 Race-Intelligence")

st.caption(
    "TJK Yarış Analiz Platformu"
)


# =========================================================
# SESSION STATE
# =========================================================

if "program_data" not in st.session_state:
    st.session_state.program_data = None

if "selected_date" not in st.session_state:
    st.session_state.selected_date = date.today()

if "selected_city" not in st.session_state:
    st.session_state.selected_city = "İstanbul"

if "selected_race" not in st.session_state:
    st.session_state.selected_race = None

if "race_data" not in st.session_state:
    st.session_state.race_data = None

if "horse_data" not in st.session_state:
    st.session_state.horse_data = []

if "in_flight" not in st.session_state:
    st.session_state.in_flight = False

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None


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
# HİPODROMLAR
# =========================================================

CITIES = [
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
# SIDEBAR
# =========================================================

with st.sidebar:

    st.header("🗓️ Yarış Programı")

    selected_date = st.date_input(
        "Tarih",
        value=st.session_state.selected_date,
        format="DD/MM/YYYY"
    )

    selected_city = st.selectbox(
        "Hipodrom",
        CITIES,
        index=CITIES.index(
            st.session_state.selected_city
        )
        if st.session_state.selected_city in CITIES
        else 0
    )

    st.session_state.selected_date = selected_date
    st.session_state.selected_city = selected_city

    st.divider()

    get_program_button = st.button(
        "🔄 PROGRAMI GETİR",
        use_container_width=True,
        type="primary"
    )


# =========================================================
# PROGRAM GETİR
# =========================================================

if get_program_button:

    st.session_state.in_flight = True

    try:

        with st.spinner(
            f"{selected_city} programı TJK'dan alınıyor..."
        ):

            program = get_program(
                selected_date,
                selected_city
            )

        st.session_state.program_data = program

        # Yeni program geldiğinde seçimleri sıfırla
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

program_data = st.session_state.program_data


if program_data is not None:

    # -----------------------------------------------------
    # GENEL DURUM
    # -----------------------------------------------------

    races = program_data.get(
        "races",
        []
    )

    st.divider()

    st.header("📋 Yarış Programı")

    st.success(
        f"{selected_city} — "
        f"{selected_date.strftime('%d/%m/%Y')} — "
        f"{len(races)} koşu bulundu."
    )


    # -----------------------------------------------------
    # PARSER DEBUG
    # -----------------------------------------------------

    debug_data = program_data.get(
        "debug",
        {}
    )

    if debug_data:

        with st.expander(
            "🔧 TJK Parser Debug",
            expanded=True
        ):

            st.subheader(
                "TJK'dan Gelen Veri"
            )

            col1, col2, col3 = st.columns(3)

            with col1:

                st.metric(
                    "HTML uzunluğu",
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
                    "Koşu bulundu:",
                    debug_data.get(
                        "has_kosu_text",
                        False
                    )
                )

            with col2:

                st.write(
                    "At İsmi bulundu:",
                    debug_data.get(
                        "has_at_ismi_text",
                        False
                    )
                )

            with col3:

                st.write(
                    "Jokey bulundu:",
                    debug_data.get(
                        "has_jokey_text",
                        False
                    )
                )

            with col4:

                st.write(
                    "Koşu regex:",
                    debug_data.get(
                        "race_pattern_count",
                        0
                    )
                )


            st.divider()

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


            st.divider()

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


            # -------------------------------------------------
            # PARSER HATASI
            # -------------------------------------------------

            if program_data.get(
                "parse_error"
            ):

                st.error(
                    "Parser hatası: "
                    + str(
                        program_data.get(
                            "parse_error"
                        )
                    )
                )


            # -------------------------------------------------
            # HTML BAŞLANGICI
            # -------------------------------------------------
html_start = debug_data.get(
    "html_start",
    ""
)

if html_start:

    with st.expander(
        "TJK HTML ham verisini göster",
        expanded=False
    ):

        st.code(
            html_start,
            language="html"
        )
            html_start = debug_data.get(
                "html_start",
                ""
            )

            if html_start:

                st.subheader(
                    "TJK HTML başlangıcı"
                )

                st.code(
                    html_start,
                    language="html"
                )


    # -----------------------------------------------------
    # KOŞU SEÇİMİ
    # -----------------------------------------------------

    if races:

        st.subheader(
            "🏁 Koşu Seç"
        )

        race_options = []

        for race in races:

            race_number = race.get(
                "race_number",
                ""
            )

            race_time = race.get(
                "race_time",
                ""
            )

            if race_time:

                label = (
                    f"{race_number}. Koşu "
                    f"— {race_time}"
                )

            else:

                label = (
                    f"{race_number}. Koşu"
                )

            race_options.append(
                label
            )


        # Mevcut seçim
        default_index = 0

        if st.session_state.selected_race:

            previous_number = (
                st.session_state.selected_race.get(
                    "race_number"
                )
            )

            for i, race in enumerate(races):

                if race.get(
                    "race_number"
                ) == previous_number:

                    default_index = i
                    break


        selected_label = st.selectbox(
            "Koşu",
            race_options,
            index=default_index
        )


        selected_index = race_options.index(
            selected_label
        )

        selected_race = races[
            selected_index
        ]

        st.session_state.selected_race = (
            selected_race
        )

        st.session_state.race_data = (
            selected_race
        )

        horses = selected_race.get(
            "horses",
            []
        )

        st.session_state.horse_data = (
            horses
        )


        # -------------------------------------------------
        # SEÇİLİ KOŞU BİLGİLERİ
        # -------------------------------------------------

        st.divider()

        st.header("🏇 Seçilen Koşu")

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
        # AT LİSTESİ
        # -------------------------------------------------

        st.divider()

        st.header("🐎 Atlar")

        if horses:

            st.success(
                f"{len(horses)} at verisi bulundu."
            )

            # DataFrame oluştur
            try:

                horse_rows = []

                for horse in horses:

                    row = dict(horse)

                    # İç sistem alanını kullanıcıya
                    # tekrar göstermemek için kaldır
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

            except Exception as exc:

                st.error(
                    "At tablosu gösterilemedi: "
                    + str(exc)
                )

        else:

            st.info(
                "Seçilen koşuya ait at verisi "
                "henüz alınmadı."
            )


    # -----------------------------------------------------
    # KOŞU YOK
    # -----------------------------------------------------

    else:

        st.warning(
            "Program sayfası açıldı fakat "
            "koşu verisi ayrıştırılamadı."
        )

        st.info(
            "Yukarıdaki "
            "'TJK Parser Debug' bölümündeki "
            "değerler parser sorununun kaynağını "
            "belirlemek için kullanılacaktır."
        )


# =========================================================
# ANALİZ MOTORU
# =========================================================

st.divider()

st.header("🧠 Analiz Motoru")

weight_columns = st.columns(4)

weight_items = list(
    WEIGHTS.items()
)

for index, (
    name,
    weight
) in enumerate(weight_items):

    column = weight_columns[
        index % 4
    ]

    with column:

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
# ANALİZ MOTORU DURUMU
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
# GELİŞTİRME DURUMU
# =========================================================

st.divider()

with st.expander(
    "ℹ️ Race-Intelligence Mimari Durumu"
):

    st.write(
        """
        **Worker katmanı**
        
        • TJK Fetch  
        • Cache  
        • Horse-data cache  
        • Request dedup  
        • Kontrollü concurrency  
        • Temiz API  
        
        **Analiz katmanı**
        
        • Pist / Mesafe — %22  
        • Ortak Rakip — %18  
        • Sınıf / HP — %14  
        • Form — %19  
        • Kilo — %12  
        • Derece — %8  
        • Galop / Tempo — %5  
        • Hız — %3  
        
        **Toplam ağırlık: %101**
        
        Nihai skor daha sonra:
        
        `HAM SKOR / 101 × 100`
        
        şeklinde normalize edilecektir.
        """
    )
