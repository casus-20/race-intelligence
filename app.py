import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# 1. BU KOMUT HER ZAMAN EN ÜSTTE OLMALIDIR (TypeError hatasını önler)
st.set_page_config(
    page_title="Race Intelligence - TJK Analiz Motoru",
    page_layout="wide",
    initial_sidebar_state="expanded"
)

# Cloudflare Worker API URL (Worker v54.0)
WORKER_URL = "https://fragrant-hat-ae48.casus-20.workers.dev"

# --- YARDIMCI FONKSİYONLAR ---
@st.cache_data(ttl=600)
def fetch_api(endpoint, params=None):
    """Worker API'sine istek atan önbellekli fonksiyon"""
    try:
        url = f"{WORKER_URL}{endpoint}"
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            return response.json()
        return {"ok": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def time_to_sec(time_str):
    """Worker kodundaki timeSec() karşılığı: Dereceyi saniyeye çevirir."""
    if not time_str:
        return None
    try:
        clean_str = str(time_str).replace(":", ".").strip()
        parts = clean_str.split(".")
        if len(parts) == 3:
            return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 100
        elif len(parts) == 2:
            return int(parts[0]) + int(parts[1]) / 100
    except:
        pass
    return None

def calculate_speed_kmh(distance, time_str):
    """Worker kodundaki speedKmh() karşılığı: Son Hız (km/s)."""
    sec = time_to_sec(time_str)
    try:
        dist = float(distance)
        if sec and dist > 0:
            return round((dist / sec) * 3.6, 2)
    except:
        pass
    return None

# --- WORKER V54 TAM ANALİZ MOTORU ---
def run_v54_analysis(horses, race_meta, horse_details):
    """Worker kodundaki analyze() fonksiyonunun birebir Streamlit uyarlaması."""
    analyzed_horses = []
    
    # Koşmaz atları filtrele (isNR)
    active_horses = [h for h in horses if not any(kw in str(h.get("name", "")).lower() for kw in ["koşmaz", "kosmaz", "çekildi", "cekildi", "start almaz"])]
    if not active_horses:
        return []

    for horse in active_horses:
        h_name = horse.get("name", "")
        details = horse_details.get(h_name, {})
        history = details.get("history", [])
        workouts = details.get("workouts", [])
        
        # Son Hız (km/h) ve Son Koşu Tespiti
        last_speed_kmh = None
        last_race_info = {}
        for h_item in history:
            speed = calculate_speed_kmh(h_item.get("distance"), h_item.get("time"))
            if speed:
                last_speed_kmh = speed
                last_race_info = h_item
                break

        # En İyi İdman / Galop Derecesi (m1400..m200)
        best_workout_sec = None
        for w in workouts[:5]:
            for m_key in ["m1400", "m1200", "m1000", "m800", "m600", "m400", "m200"]:
                val = time_to_sec(w.get(m_key))
                if val and (best_workout_sec is None or val < best_workout_sec):
                    best_workout_sec = val

        try:
            hp = float(horse.get("hp", 0))
        except:
            hp = 0.0
        try:
            weight = float(horse.get("weight", 0))
        except:
            weight = 0.0

        analyzed_horses.append({
            "no": horse.get("no", ""),
            "name": h_name,
            "jockey": horse.get("jockey", "-"),
            "owner": horse.get("owner", "-"),
            "trainer": horse.get("trainer", "-"),
            "weight": weight,
            "hp": hp,
            "last6": horse.get("last6", "-"),
            "kgs": horse.get("kgs", "-"),
            "s20": horse.get("s20", "-"),
            "bestTime": horse.get("bestTime", "-"),
            "odds": horse.get("odds", "-"),
            "agf": horse.get("agf", "-"),
            "last_speed_kmh": last_speed_kmh,
            "last_race_date": last_race_info.get("date", "-"),
            "last_race_city": last_race_info.get("city", "-"),
            "last_race_dist": last_race_info.get("distance", "-"),
            "last_race_surf": last_race_info.get("surface", "-"),
            "best_workout_sec": best_workout_sec,
            "history": history,
            "workouts": workouts,
            "atId": horse.get("atId")
        })

    # Ağırlıklı Puanlama Algoritması (v54)
    max_hp = max([h["hp"] for h in analyzed_horses], default=100) or 1
    min_weight = min([h["weight"] for h in analyzed_horses if h["weight"] > 0], default=50) or 50
    max_weight = max([h["weight"] for h in analyzed_horses], default=60) or 60

    for h in analyzed_horses:
        hp_score = (h["hp"] / max_hp) * 100 if max_hp > 0 else 50
        weight_range = (max_weight - min_weight) or 1
        weight_score = ((max_weight - h["weight"]) / weight_range) * 100 if h["weight"] > 0 else 50
        speed_score = min(100, (h["last_speed_kmh"] / 60.0) * 100) if h["last_speed_kmh"] else 40
        workout_score = 70 if h["best_workout_sec"] else 30

        # Worker v54 Ağırlıkları
        final_score = (hp_score * 0.35) + (weight_score * 0.20) + (speed_score * 0.25) + (workout_score * 0.20)
        h["v54_score"] = round(final_score, 2)

    analyzed_horses.sort(key=lambda x: x["v54_score"], reverse=True)
    return analyzed_horses


# --- STREAMLIT ARAYÜZÜ ---
def main():
    st.title("🏇 Race Intelligence - TJK Analiz Sistemi")
    st.caption("Cloudflare Worker v54.0 Motoru ve Detaylı TJK Veri Tablosu")

    # Yan Menü: Şehir ve Tarih
    st.sidebar.header("🔍 Program Filtreleri")
    selected_date = st.sidebar.date_input("Yarış Tarihi", datetime.today())
    date_str = selected_date.strftime("%Y-%m-%d")

    # 1. /api/tjk/cities Uç Noktası
    with st.sidebar:
        with st.spinner("Şehirler yükleniyor..."):
            city_res = fetch_api("/api/tjk/cities", {"date": date_str})

    if not city_res.get("ok") or not city_res.get("cities"):
        st.warning(f"Seçilen tarihte ({date_str}) aktif yarış şehri bulunamadı.")
        return

    city_names = [c["name"] for c in city_res["cities"]]
    selected_city = st.sidebar.selectbox("Şehir Seçin", city_names)

    # 2. /api/tjk/data Uç Noktası (Günlük Program Verisi)
    st.header(f"📍 {selected_city} Yarış Programı ({date_str})")
    data_res = fetch_api("/api/tjk/data", {"date": date_str, "city": selected_city})

    if not data_res.get("ok") or not data_res.get("races"):
        st.error("Yarış programı verisi alınamadı.")
        return

    races = data_res["races"]
    st.success(f"Kaynak: **{data_res.get('source', 'TJK')}** | Koşu Sayısı: **{len(races)}** | Toplam At: **{data_res.get('horseCount', 0)}**")

    # Koşu Sekmeleri
    race_tabs = st.tabs([f"{r.get('no', i+1)}. Koşu ({r.get('time', '-')})" for i, r in enumerate(races)])

    for idx, tab in enumerate(race_tabs):
        race = races[idx]
        with tab:
            meta = race.get("meta", {})
            st.markdown(f"**Koşu Detayı:** {meta.get('raceName', meta.get('detail', 'Bilgi Yok'))}")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Mesafe", f"{meta.get('distance', '-')}m")
            c2.metric("Pist", meta.get("surface", "-"))
            c3.metric("Saat", race.get("time", "-"))
            c4.metric("E.İ.D", meta.get("eid", "-"))

            horses = race.get("horses", [])
            if not horses:
                st.info("Bu koşuda at bulunamadı.")
                continue

            # Tam V54 Analizi Çalıştır Butonu
            if st.button(f"{race.get('no')}. Koşu İçin /api/tjk/horsedata Verilerini Çek ve Analiz Et", key=f"btn_{idx}"):
                horse_details = {}
                progress_bar = st.progress(0)
                status_text = st.empty()

                # /api/tjk/horsedata Çağrıları
                for i, h in enumerate(horses):
                    h_name = h.get("name")
                    at_id = h.get("atId")
                    status_text.text(f"Geçmiş ve İdman Verisi Alınıyor ({i+1}/{len(horses)}): {h_name}")
                    
                    if at_id:
                        h_data = fetch_api("/api/tjk/horsedata", {"atId": at_id, "horse": h_name, "origin": h.get("origin", "")})
                        if h_data.get("ok"):
                            horse_details[h_name] = h_data
                    
                    progress_bar.progress((i + 1) / len(horses))

                status_text.success("Tüm at verileri başarıyla toplandı!")
                
                # V54 Analizini Hesapla
                results = run_v54_analysis(horses, meta, horse_details)
                df = pd.DataFrame(results)
                
                # Görsel Tablo
                df_display = df[[
                    "no", "name", "v54_score", "hp", "weight", "jockey", 
                    "last_speed_kmh", "last_race_date", "last_race_city", "last_race_dist", "last_race_surf",
                    "last6", "kgs", "s20", "bestTime", "odds", "agf"
                ]].copy()
                
                df_display.columns = [
                    "At No", "At İsmi", "V54 Skoru", "HP", "Sıklet", "Jokey", 
                    "Son Hız (km/s)", "Son Koşu Tarih", "Son Şehir", "Son Mesafe", "Son Pist",
                    "Son 6", "KGS", "s20", "En İyi Der.", "GNY", "AGF"
                ]

                st.subheader("📊 V54 Yapay Zeka Analiz & Sıralama Tablosu")
                st.dataframe(
                    df_display.style.highlight_max(subset=["V54 Skoru"], color="#d4edda"),
                    use_container_width=True
                )

                # At Detay İnceleme (Geçmiş Koşular & İdmanlar)
                st.subheader("🔍 At Bazlı Geçmiş Koşu ve İdman Detayları")
                selected_horse_name = st.selectbox("Detayını İncelemek İstediğiniz Atı Seçin", [h["name"] for h in results], key=f"sb_{idx}")
                
                selected_horse = next((h for h in results if h["name"] == selected_horse_name), None)
                if selected_horse:
                    col_h, col_w = st.columns(2)
                    with col_h:
                        st.markdown("#### 📜 Geçmiş Koşuları (/api/tjk/horse)")
                        if selected_horse["history"]:
                            st.dataframe(pd.DataFrame(selected_horse["history"]), use_container_width=True)
                        else:
                            st.info("Geçmiş koşu kaydı bulunamadı.")
                    with col_w:
                        st.markdown("#### 🏋️ İdman / Galop Kayıtları (/api/tjk/workouts)")
                        if selected_horse["workouts"]:
                            st.dataframe(pd.DataFrame(selected_horse["workouts"]), use_container_width=True)
                        else:
                            st.info("İdman kaydı bulunamadı.")

            else:
                # Varsayılan Günlük Bültendeki Tüm Alanlar
                df_simple = pd.DataFrame(horses)
                cols = [c for c in ["no", "name", "age", "origin", "weight", "jockey", "owner", "trainer", "st", "hp", "last6", "kgs", "s20", "bestTime", "odds", "agf"] if c in df_simple.columns]
                st.dataframe(df_simple[cols], use_container_width=True)

if __name__ == "__main__":
    main()
