import re
from datetime import date, datetime
from urllib.parse import urlencode

import pandas as pd
import requests
from bs4 import BeautifulSoup


# ============================================================
# TJK AYARLARI
# ============================================================

TJK_URL = (
    "https://www.tjk.org/TR/YarisSever/Info/Sehir/"
    "GunlukYarisProgrami"
)

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
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


class TJKFetchError(Exception):
    pass


# ============================================================
# TARİH
# ============================================================

def format_date(value):

    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")

    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    value = str(value).strip()

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        y, m, d = value.split("-")
        return f"{d}/{m}/{y}"

    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", value):
        return value.replace(".", "/")

    return value


# ============================================================
# URL
# ============================================================

def build_program_url(race_date, city):

    if city not in CITY_IDS:
        raise TJKFetchError(
            f"Bilinmeyen hipodrom: {city}"
        )

    params = {
        "QueryParameter_Tarih": format_date(race_date),
        "SehirAdi": city,
        "SehirId": CITY_IDS[city],
    }

    return (
        TJK_URL
        + "?"
        + urlencode(params)
    )


# ============================================================
# TJK'DAN HTML AL
# ============================================================

def fetch_program_html(race_date, city):

    url = build_program_url(
        race_date,
        city
    )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

    except requests.RequestException as exc:

        raise TJKFetchError(
            f"TJK bağlantı hatası: {exc}"
        )

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

    return response.text, url


# ============================================================
# METİN TEMİZLE
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    value = str(value)

    value = value.replace(
        "\xa0",
        " "
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


# ============================================================
# KOŞU BAŞLIKLARINI BUL
# ============================================================

def parse_race_headings(soup):

    races = []

    # TJK programında koşular h3 olarak geliyor.
    headings = soup.find_all(
        ["h2", "h3", "h4"]
    )

    for heading in headings:

        text = clean_text(
            heading.get_text(
                " ",
                strip=True
            )
        )

        match = re.search(
            r"(\d+)\.\s*Koşu\s+(\d{1,2}:\d{2})",
            text,
            re.IGNORECASE
        )

        if not match:
            continue

        number = int(
            match.group(1)
        )

        time = match.group(2)

        races.append({
            "race_number": number,
            "race_time": time,
            "title": text,
            "horses": []
        })

    # Tekilleştir
    unique = {}

    for race in races:

        number = race["race_number"]

        if number not in unique:
            unique[number] = race

    races = list(
        unique.values()
    )

    races.sort(
        key=lambda x: x["race_number"]
    )

    return races


# ============================================================
# SÜTUN ADLARINI NORMALİZE ET
# ============================================================

def normalize_column(value):

    text = clean_text(value)

    # Türkçe karakterleri bozmadan
    # bilinen başlıkları standartlaştır.
    mapping = {

        "N": "number",

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

        "Forma": "form",
    }

    return mapping.get(
        text,
        text
    )


# ============================================================
# DATAFRAME KOLONLARINI DÜZELT
# ============================================================

def normalize_columns(df):

    new_columns = []

    for column in df.columns:

        if isinstance(
            column,
            tuple
        ):

            parts = []

            for part in column:

                part = clean_text(part)

                if (
                    part
                    and part.lower() != "nan"
                ):
                    parts.append(part)

            column = " ".join(parts)

        new_columns.append(
            normalize_column(
                column
            )
        )

    df.columns = new_columns

    return df


# ============================================================
# AT TABLOSU KONTROLÜ
# ============================================================

def is_horse_table(df):

    if df.empty:
        return False

    columns = [
        str(column)
        for column in df.columns
    ]

    text = " ".join(
        columns
    ).lower()

    score = 0

    checks = [
        "at i̇smi",
        "at ismi",
        "yaş",
        "sıklet",
        "jokey",
        "hp",
        "son 6",
        "kgs",
        "agf",
        "i̇dm",
        "idm",
    ]

    for item in checks:

        if item.lower() in text:
            score += 1

    return score >= 3


# ============================================================
# AT TABLOSUNU PARSE ET
# ============================================================

def parse_horse_dataframe(df):

    df = df.copy()

    df = normalize_columns(
        df
    )

    horses = []

    for _, row in df.iterrows():

        horse = {}

        for column in df.columns:

            value = row[column]

            try:

                if pd.isna(value):
                    value = None

            except Exception:
                pass

            if value is not None:
                value = clean_text(
                    value
                )

            horse[column] = value

        horse_name = horse.get(
            "horse_name"
        )

        if not horse_name:
            continue

        horses.append(
            horse
        )

    return horses


# ============================================================
# HTML'DEKİ AT TABLOLARINI BUL
# ============================================================

def parse_horse_tables(html):

    try:

        tables = pd.read_html(
            html
        )

    except Exception:

        return []

    result = []

    for table in tables:

        if table is None:
            continue

        if table.empty:
            continue

        if not is_horse_table(
            table
        ):
            continue

        horses = parse_horse_dataframe(
            table
        )

        if horses:

            result.append(
                horses
            )

    return result


# ============================================================
# KOŞU BİLGİSİ
# ============================================================

def extract_race_details(
    soup,
    race_number
):

    text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    pattern = re.compile(
        rf"{race_number}\.\s*Koşu"
        rf".{{0,500}}?"
        rf"(\d{{3,4}})\s*"
        rf"(Kum|Çim|Sentetik)",
        re.IGNORECASE
    )

    match = pattern.search(
        text
    )

    if not match:

        return {
            "distance": None,
            "track": None
        }

    return {
        "distance": int(
            match.group(1)
        ),
        "track": match.group(2)
    }


# ============================================================
# PROGRAM PARSER
# ============================================================

def parse_program(
    html,
    race_date,
    city
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    races = parse_race_headings(
        soup
    )

    horse_tables = parse_horse_tables(
        html
    )

    # TJK sayfasındaki at tablolarını
    # koşularla sırayla eşleştir.
    for index, race in enumerate(
        races
    ):

        if index < len(
            horse_tables
        ):

            race["horses"] = (
                horse_tables[index]
            )

        details = extract_race_details(
            soup,
            race["race_number"]
        )

        race.update(
            details
        )

    return {
        "ok": True,
        "source": "TJK",
        "date": format_date(
            race_date
        ),
        "city": city,
        "race_count": len(races),
        "races": races
    }


# ============================================================
# ANA FONKSİYON
# ============================================================

def get_program(
    race_date,
    city
):

    html, url = fetch_program_html(
        race_date,
        city
    )

    data = parse_program(
        html,
        race_date,
        city
    )

    data["url"] = url

    return data
