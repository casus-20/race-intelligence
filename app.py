import streamlit as st
from datetime import date

# ============================================================
# PAGE CONFIG
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

# Program State
if "program_data" not in st.session_state:
    st.session_state.program_data = None

if "selected_date" not in st.session_state:
    st.session_state.selected_date = date.today()

if "selected_city" not in st.session_state:
    st.session_state.selected_city = None

# Race State
if "selected_race" not in st.session_state:
    st.session_state.selected_race = None

if "race_data" not in st.session_state:
    st.session_state.race_data = None

# Horse State
if "horse_data" not in st.session_state:
    st.session_state.horse_data = {}

# Request State
if "in_flight" not in st.session_state:
    st.session_state.in_flight = {}

# Analysis State
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None


# ============================================================
# HEADER
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
        value=st.session_state.selected_date
    )

    cities = [
        "İstanbul",
        "Ankara",
        "İzmir",
        "Bursa",
        "Adana",
        "Kocaeli",
        "Elazığ",
        "Şanlıurfa",
        "Diyarbakır"
    ]

    selected_city = st.selectbox(
        "Hipodrom",
        cities
    )

    st.divider()

    get_program = st.button(
        "🔄 PROGRAMI GETİR",
        use_container_width=True
    )


# ============================================================
# UPDATE PROGRAM STATE
# ============================================================

if get_program:

    st.session_state.selected_date = selected_date
    st.session_state.selected_city = selected_city

    # TJK fetch katmanı henüz bağlanmadı.
    # Bir sonraki aşamada burası Worker/FETCH katmanına bağlanacak.

    st.session_state.program_data = None
    st.session_state.selected_race = None
    st.session_state.race_data = None
    st.session_state.horse_data = {}
    st.session_state.analysis_result = None

    st.info(
        f"Program isteği hazırlandı: "
        f"{selected_date.strftime('%d.%m.%Y')} - {selected_city}"
    )


# ============================================================
# CURRENT PROGRAM
# ============================================================

st.subheader("📋 Yarış Programı")

if st.session_state.program_data is None:

    st.info(
        "Henüz program verisi alınmadı. "
        "Soldan tarih ve hipodrom seçip PROGRAMI GETİR butonuna basın."
    )

else:

    st.success("Program verisi hazır.")


# ============================================================
# RACE STATE
# ============================================================

st.divider()

st.subheader("🏁 Koşu")

if st.session_state.race_data is None:

    st.info("Henüz bir koşu seçilmedi.")

else:

    st.success(
        f"Seçili koşu: {st.session_state.selected_race}"
    )


# ============================================================
# HORSE STATE
# ============================================================

st.divider()

st.subheader("🐎 Atlar")

if not st.session_state.horse_data:

    st.info("Henüz at verisi alınmadı.")

else:

    st.write(
        st.session_state.horse_data
    )


# ============================================================
# ANALYSIS
# ============================================================

st.divider()

st.subheader("🧠 Analiz Motoru")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Pist / Mesafe", "%22")

with col2:
    st.metric("Ortak Rakip", "%18")

with col3:
    st.metric("Sınıf / HP", "%14")

with col4:
    st.metric("Form", "%19")


col5, col6, col7, col8 = st.columns(4)

with col5:
    st.metric("Kilo", "%12")

with col6:
    st.metric("Derece", "%8")

with col7:
    st.metric("Galop / Tempo", "%5")

with col8:
    st.metric("Hız", "%3")


# ============================================================
# SYSTEM STATUS
# ============================================================

st.divider()

st.subheader("⚙️ Sistem Durumu")

status1, status2, status3, status4 = st.columns(4)

with status1:
    st.write("🟢 Streamlit")
    st.caption("Çalışıyor")

with status2:
    st.write("🟡 TJK Fetch")
    st.caption("Bağlanacak")

with status3:
    st.write("🟡 Cache")
    st.caption("Bağlanacak")

with status4:
    st.write("🟡 Analiz")
    st.caption("Bağlanacak")
