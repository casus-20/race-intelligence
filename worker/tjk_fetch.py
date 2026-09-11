import re
from datetime import date, datetime
from urllib.parse import urlencode

import pandas as pd
import requests
from bs4 import BeautifulSoup


# ============================================================
# TJK
# ============================================================

TJK_BASE_URL = (
    "https://www.tjk.org/TR/YarisSever/Info/Sehir/GunlukYarisProgrami"
)


# TJK şehir ID'leri
CITY_IDS = {
    "Adana": 1,
    "İzmir": 2,
    "İstanbul": 3,
    "Bursa": 4,
    "Ankara": 5,
    "Şanlıurfa": 6,
    "Elazığ": 7,
    "Diyarbakır": 8,
    "Kocaeli": 9,
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}


class TJKFetchError(Exception):
    pass


# ============================================================
# TARİH
# ============================================================

def format_tjk_date(value):
    """
    TJK tarih formatı:
    DD/MM/YYYY
    """

    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")

    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    value = str(value).strip()

    # YYYY-MM-DD
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        y, m, d = value.split("-")
        return f"{d}/{m}/{y}"

    # DD.MM.YYYY
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", value):
        return value.replace(".", "/")

    # DD/MM/YYYY
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        return value

    raise ValueError(
        f"Geçersiz tarih formatı: {value}"
    )


# ============================================================
# URL
# ============================================================

def build_program_url(race_date, city):
    """
    TJK günlük program URL'si.
    """

    if city not in CITY_IDS:
        raise ValueError(
            f"Bilinmeyen hipodrom: {city}"
        )

    date_text = format_tjk_date(race_date)
    city_id = CITY_IDS[city]

    params = {
        "Era": "today",
        "QueryParameter_Tarih": date_text,
        "SehirAdi": city,
        "SehirId": city_id,
    }

    return f"{TJK_BASE_URL}?{urlencode(params)}"


# ============================================================
# HTTP
# ============================================================

def fetch_program_html(
    race_date,
    city,
    timeout=30
):
    """
    TJK günlük program HTML'ini getirir.
    """

    url = build_program_url(
        race_date,
        city
    )

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout
        )

    except requests.RequestException as exc:
        raise TJKFetchError(
            f"TJK bağlantı hatası: {exc}"
        ) from exc

    if response.status_code != 200:
        raise TJKFetchError(
            f"TJK HTTP {response.status_code}"
        )

    if not response.text:
        raise TJKFetchError(
            "TJK boş cevap döndürdü."
        )

    response.encoding = (
        response.apparent_encoding
        or "utf-8"
    )

    return {
        "url": url,
        "status_code": response.status_code,
        "html": response.text,
    }


# ============================================================
# METİN TEMİZLEME
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    text = str(value)

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# KOŞU BAŞLIĞI
# ============================================================

def parse_race_heading(text):
    """
    Örnek:

    1. Koşu 17.45

    veya

    1. Koşu:17.45
    """

    text = clean_text(text)

    pattern = re.search(
        r"(\d+)\.\s*Koşu\s*:?\s*(\d{1,2}:\d{2})?",
        text,
        re.IGNORECASE
    )

    if not pattern:
        return None

    race_number = int(pattern.group(1))

    race_time = pattern.group(2)

    return {
        "race_number": race_number,
        "race_time": race_time,
        "title": text,
    }


# ============================================================
# KOŞU ŞARTLARI
# ============================================================

def parse_race_info(text):
    """
    Koşu açıklamasından mümkün olduğunca
    sınıf / yaş / kilo / mesafe / pist bilgisini çıkarır.
    """

    text = clean_text(text)

    result = {
        "condition": text,
        "class": None,
        "age": None,
        "weight": None,
        "distance": None,
        "track": None,
        "best_time": None,
    }

    # Mesafe + pist
    distance_match = re.search(
        r"(\d{3,4})\s*(Çim|Kum|Sentetik)",
        text,
        re.IGNORECASE
    )

    if distance_match:
        result["distance"] = int(
            distance_match.group(1)
        )

        result["track"] = (
            distance_match.group(2)
            .strip()
        )

    # E.İ.D.
    best_match = re.search(
        r"E\.İ\.D\.\s*:\s*([0-9:.]+)",
        text,
        re.IGNORECASE
    )

    if best_match:
        result["best_time"] = (
            best_match.group(1)
        )

    return result


# ============================================================
# AT TABLOSU
# ============================================================

def normalize_columns(columns):
    result = []

    for column in columns:
        text = clean_text(column)

        replacements = {
            "At İsmi": "horse_name",
            "At Ismi": "horse_name",
            "Yaş": "age",
            "Orijin(Baba - Anne)": "origin",
            "Sıklet": "weight",
            "Jokey": "jockey",
            "Sahip": "owner",
            "Antrenör": "trainer",
            "St": "start",
            "HP": "hp",
            "Son 6 Y.": "last6",
            "KGS": "kgs",
            "s20": "s20",
            "En İyi D.": "best_time",
            "Gny": "odds",
            "AGF": "agf",
            "İdm": "workout",
            "N": "number",
            "Forma": "form",
        }

        result.append(
            replacements.get(text, text)
        )

    return result


def parse_horse_table(table):
    """
    Bir HTML tablosunu at listesine çevirir.
    """

    try:
        frames = pd.read_html(
            str(table)
        )
    except Exception:
        return []

    if not frames:
        return []

    df = frames[0]

    if df.empty:
        return []

    # MultiIndex varsa düzleştir
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join(
                str(x)
                for x in col
                if str(x) != "nan"
            ).strip()
            for col in df.columns
        ]

    df.columns = normalize_columns(
        df.columns
    )

    horses = []

    for _, row in df.iterrows():

        item = {}

        for column in df.columns:

            value = row[column]

            if pd.isna(value):
                value = None
            else:
                value = clean_text(value)

            item[column] = value

        # Gerçek at satırı olup olmadığını kontrol et
        horse_name = item.get("horse_name")

        if not horse_name:
            continue

        horses.append(item)

    return horses


# ============================================================
# PROGRAM PARSER
# ============================================================

def parse_program_html(
    html,
    race_date=None,
    city=None
):
    """
    TJK HTML'inden yarış programını çıkarır.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    races = []

    # --------------------------------------------------------
    # Önce başlıkları bul
    # --------------------------------------------------------

    headings = soup.find_all(
        ["h2", "h3", "h4"]
    )

    race_headings = []

    for heading in headings:

        text = clean_text(
            heading.get_text(
                " ",
                strip=True
            )
        )

        parsed = parse_race_heading(
            text
        )

        if parsed:
            race_headings.append(
                (heading, parsed)
            )

    # --------------------------------------------------------
    # Her koşunun çevresindeki tabloları bul
    # --------------------------------------------------------

    for index, (heading, race) in enumerate(
        race_headings
    ):

        current = heading

        next_heading = None

        if index + 1 < len(race_headings):
            next_heading = race_headings[
                index + 1
            ][0]

        tables = []

        while current is not None:

            current = current.find_next()

            if current is None:
                break

            if next_heading is not None:
                if current == next_heading:
                    break

            if current.name == "table":
                tables.append(current)

        # İlk uygun tabloyu at tablosu kabul et
        horses = []

        for table in tables:

            parsed_horses = parse_horse_table(
                table
            )

            if parsed_horses:
                horses = parsed_horses
                break

        race["horses"] = horses

        races.append(race)

    # --------------------------------------------------------
    # Duplicate koşuları temizle
    # --------------------------------------------------------

    unique = {}

    for race in races:

        key = race["race_number"]

        if key not in unique:
            unique[key] = race

    races = list(
        unique.values()
    )

    races.sort(
        key=lambda x: x["race_number"]
    )

    return {
        "ok": True,
        "source": "TJK Günlük Yarış Programı",
        "date": (
            format_tjk_date(race_date)
            if race_date
            else None
        ),
        "city": city,
        "race_count": len(races),
        "races": races,
    }


# ============================================================
# ANA FONKSİYON
# ============================================================

def get_program(
    race_date,
    city
):
    """
    Streamlit tarafından çağrılacak
    ana fonksiyon.
    """

    result = fetch_program_html(
        race_date,
        city
    )

    data = parse_program_html(
        result["html"],
        race_date=race_date,
        city=city
    )

    data["url"] = result["url"]
    data["http_status"] = result["status_code"]

    return data
