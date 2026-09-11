import streamlit as st
from datetime import date

from worker.tjk_fetch import get_program, TJKFetchError


# ============================================================
# SAYFA AYARLARI
# ============================================================

st.set_page_config(
    page_title="Race-Intelligence",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# SESSION STATE
# ============================================================

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
    st.session_state.horse_data = {}

if "in_flight" not in st.session_state:
    st.session_state.in_flight = {}

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None


# ============================================================
# BAŞLIK
# ============================================================

st.title("🏇 Race-Intelligence")
st.caption("TJK Yarış Analiz Platformu")


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("📅 Yarış Programı")

    selected_date = st.date_input(
        "Tarih",
        value=st.session_state.selected_date,
        format="DD/MM/YYYY"
    )

    cities = [
        "Adana",
        "Ankara",
        "Bursa",
        "Diyarbakır",
        "Elazığ",
        "İstanbul",
        "İzmir",
        "Kocaeli",
        "Şanlıurfa"
    ]

    selected_city = st.selectbox(
        "Hipodrom",
        cities,
        index=cities.index(
            st.session_state.selected_city
        )
    )

    st.divider()

    get_program_button = st.button(
        "🔄 PROGRAMI GETİR",
        use_container_width=True,
        type="primary"
    )


# ============================================================
# PROGRAMI TJK'DAN ÇEK
# ============================================================

if get_program_button:

    # Önce eski state'i temizle
    st.session_state.program_data = None
    st.session_state.selected_race = None
    st.session_state.race_data = None
    st.session_state.horse_data = {}
    st.session_state.analysis_result = None

    st.session_state.selected_date = selected_date
    st.session_state.selected_city = selected_city

    with st.spinner(
        f"{selected_city} yarış programı TJK'dan alınıyor..."
    ):

        try:

            program = get_program(
                selected_date,
                selected_city
            )

            if not program.get("ok"):
                st.error(
                    "TJK program verisi alınamadı."
                )

            else:

                st.session_state.program_data = program

                st.success(
                    f"{selected_city} programı alındı."
                )

        except TJKFetchError as exc:

            st.error(
                f"TJK veri çekme hatası: {exc}"
            )

        except Exception as exc:

            st.error(
                f"Beklenmeyen hata: {exc}"
            )


# ============================================================
# PROGRAM
# ============================================================

st.divider()

st.subheader("📋 Yarış Programı")


program = st.session_state.program_data


if program is None:

    st.info(
        "Tarih ve hipodrom seçerek "
        "PROGRAMI GETİR butonuna basın."
    )

else:

    race_count = program.get(
        "race_count",
        0
    )

    st.success(
        f"{program.get('city')} — "
        f"{program.get('date')} — "
        f"{race_count} koşu bulundu."
    )

    races = program.get(
        "races",
        []
    )

    if not races:

        st.warning(
            "Program sayfası açıldı fakat "
            "koşu verisi ayrıştırılamadı."
        )

    else:

        # ----------------------------------------------------
        # KOŞU SEÇİMİ
        # ----------------------------------------------------

        race_options = []

        for race in races:

            number = race.get(
                "race_number"
            )

            race_time = race.get(
                "race_time"
            )

            if race_time:

                label = (
                    f"{number}. Koşu "
                    f"— {race_time}"
                )

            else:

                label = (
                    f"{number}. Koşu"
                )

            race_options.append(
                label
            )

        selected_race_label = st.selectbox(
            "Koşu seç",
            race_options
        )

        selected_index = race_options.index(
            selected_race_label
        )

        selected_race = races[
            selected_index
        ]

        st.session_state.selected_race = (
            selected_race.get(
                "race_number"
            )
        )

        st.session_state.race_data = (
            selected_race
        )

        horses = selected_race.get(
            "horses",
            []
        )

        st.session_state.horse_data = horses


# ============================================================
# SEÇİLİ KOŞU
# ============================================================

if st.session_state.race_data:

    race = st.session_state.race_data

    st.divider()

    st.subheader(
        f"🏁 {race.get('race_number')}. Koşu"
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Koşu",
            str(
                race.get(
                    "race_number",
                    "-"
                )
            )
        )

    with col2:
        st.metric(
            "Saat",
            race.get(
                "race_time"
            ) or "-"
        )

    with col3:
        st.metric(
            "At Sayısı",
            len(
                race.get(
                    "horses",
                    []
                )
            )
        )


# ============================================================
# ATLAR
# ============================================================

st.divider()

st.subheader("🐎 Atlar")

horses = st.session_state.horse_data


if not horses:

    st.info(
        "Seçilen koşuya ait at verisi henüz alınmadı."
    )

else:

    st.write(
        f"**{len(horses)} at bulundu.**"
    )

    st.dataframe(
        horses,
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# ANALİZ MOTORU
# ============================================================

st.divider()

st.subheader("🧠 Analiz Motoru")

weights = {
    "Pist / Mesafe": 22,
    "Ortak Rakip": 18,
    "Sınıf / HP": 14,
    "Form": 19,
    "Kilo": 12,
    "Derece": 8,
    "Galop / Tempo": 5,
    "Hız": 3,
}

cols = st.columns(4)

items = list(weights.items())

for index, (name, weight) in enumerate(
    items[:4]
):

    with cols[index]:

        st.metric(
            name,
            f"%{weight}"
        )


cols = st.columns(4)

for index, (name, weight) in enumerate(
    items[4:]
):

    with cols[index]:

        st.metric(
            name,
            f"%{weight}"
        )


st.caption(
    "Ağırlık toplamı: %101 — "
    "nihai skor hesaplamasında 100 puana normalize edilecektir."
)


# ============================================================
# SİSTEM DURUMU
# ============================================================

st.divider()

st.subheader("⚙️ Sistem Durumu")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.success("Streamlit\n\nÇalışıyor")

with col2:
    st.success("TJK Fetch\n\nBağlı")

with col3:
    st.warning("Cache\n\nSıradaki aşama")

with col4:
    st.warning("Analiz\n\nSıradaki aşama")
