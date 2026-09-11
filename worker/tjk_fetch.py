import re
from datetime import date, datetime
from io import StringIO

import pandas as pd
import requests
from bs4 import BeautifulSoup


# =========================================================
# TJK AYARLARI
# =========================================================

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
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,"
        "*/*;q=0.8"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}


# =========================================================
# HATA SINIFI
# =========================================================

class TJKFetchError(Exception):
    pass


# =========================================================
# TARİH
# =========================================================

def format_date(value):
    """
    Tarihi TJK'nın beklediği DD/MM/YYYY formatına çevirir.
    """

    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")

    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    value = str(value).strip()

    if not value:
        return ""

    # YYYY-MM-DD
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        year, month, day = value.split("-")
        return f"{day}/{month}/{year}"

    # DD.MM.YYYY
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", value):
        day, month, year = value.split(".")
        return f"{day}/{month}/{year}"

    # DD/MM/YYYY
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        return value

    return value


# =========================================================
# TJK URL OLUŞTURMA
# =========================================================

def build_program_url(race_date, city):
    """
    TJK günlük yarış programı URL'sini oluşturur.
    """

    if city not in CITY_IDS:
        raise TJKFetchError(
            "Bilinmeyen hipodrom: " + str(city)
        )

    params = {
        "Era": "today",
        "QueryParameter_Tarih": format_date(race_date),
        "SehirAdi": city,
        "SehirId": CITY_IDS[city],
    }

    request = requests.Request(
        "GET",
        TJK_URL,
        params=params,
    ).prepare()

    return request.url


# =========================================================
# TJK HTML ÇEKME
# =========================================================

def fetch_program_html(race_date, city):
    """
    TJK günlük program sayfasını indirir.
    """

    url = build_program_url(
        race_date,
        city
    )

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
        )

    except requests.RequestException as exc:
        raise TJKFetchError(
            "TJK bağlantı hatası: " + str(exc)
        )

    if response.status_code != 200:
        raise TJKFetchError(
            "TJK HTTP hatası: "
            + str(response.status_code)
        )

    # TJK Türkçe karakterlerinin bozulmaması için
    response.encoding = response.apparent_encoding or "utf-8"

    return {
        "url": url,
        "status_code": response.status_code,
        "html": response.text,
    }


# =========================================================
# METİN TEMİZLEME
# =========================================================

def clean_text(value):
    """
    HTML/tablo hücrelerindeki gereksiz boşlukları temizler.
    """

    if value is None:
        return ""

    if isinstance(value, float):
        if pd.isna(value):
            return ""

    text = str(value)

    text = text.replace("\xa0", " ")
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = text.replace("\t", " ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# =========================================================
# SÜTUN İSMİ NORMALİZASYONU
# =========================================================

def normalize_column(value):
    """
    DataFrame sütun adını standart hale getirir.
    """

    if isinstance(value, tuple):
        parts = []

        for item in value:
            text = clean_text(item)

            if text and text.lower() != "nan":
                parts.append(text)

        value = " ".join(parts)

    value = clean_text(value)

    replacements = {
        "At İsmi": "At İsmi",
        "At Ismi": "At İsmi",
        "AT İSMİ": "At İsmi",
        "AT ISMI": "At İsmi",
        "At": "At İsmi",
        "Forma": "Forma",
        "N": "N",
        "Yaş": "Yaş",
        "Yas": "Yaş",
        "Orijin(Baba - Anne)": "Orijin",
        "Orijin": "Orijin",
        "Sıklet": "Sıklet",
        "Siklet": "Sıklet",
        "Jokey": "Jokey",
        "Sahip": "Sahip",
        "Antrenör": "Antrenör",
        "Antrenor": "Antrenör",
        "St": "St",
        "HP": "HP",
        "Son 6 Y.": "Son 6 Y.",
        "Son 6 Y": "Son 6 Y.",
        "KGS": "KGS",
        "s20": "s20",
        "En İyi D.": "En İyi D.",
        "En Iyi D.": "En İyi D.",
        "Gny": "Gny",
        "AGF": "AGF",
        "İdm": "İdm",
        "Idm": "İdm",
    }

    return replacements.get(value, value)


def normalize_columns(df):
    """
    DataFrame sütunlarını normalize eder.
    """

    df = df.copy()

    new_columns = []

    for column in df.columns:
        new_columns.append(
            normalize_column(column)
        )

    df.columns = new_columns

    return df


# =========================================================
# AT TABLOSU MU?
# =========================================================

def is_horse_table(df):
    """
    Bir DataFrame'in yarıştaki at tablosu olup olmadığını
    anlamaya çalışır.
    """

    if df is None:
        return False

    if df.empty:
        return False

    columns = [
        clean_text(column).lower()
        for column in df.columns
    ]

    column_text = " ".join(columns)

    horse_keywords = [
        "at ismi",
        "forma",
        "jokey",
        "sıklet",
        "siklet",
        "hp",
        "agf",
        "kgs",
    ]

    score = 0

    for keyword in horse_keywords:
        if keyword in column_text:
            score += 1

    # At tablosunda en az iki güçlü işaret arıyoruz.
    return score >= 2


# =========================================================
# HORSE DATAFRAME TEMİZLEME
# =========================================================

def parse_horse_dataframe(df):
    """
    Ham HTML tablosunu temiz ve kullanılabilir at listesine çevirir.
    """

    df = normalize_columns(df)

    # Tamamen boş satırları kaldır
    df = df.dropna(
        axis=0,
        how="all"
    )

    # Tamamen boş sütunları kaldır
    df = df.dropna(
        axis=1,
        how="all"
    )

    if df.empty:
        return []

    horses = []

    for _, row in df.iterrows():

        horse = {}

        for column in df.columns:
            value = row[column]

            if pd.isna(value):
                value = ""

            horse[column] = clean_text(value)

        # At ismini bul
        horse_name = ""

        possible_names = [
            "At İsmi",
            "At",
            "At Adı",
            "AtAdi",
        ]

        for name_column in possible_names:
            if name_column in horse:
                if horse[name_column]:
                    horse_name = horse[name_column]
                    break

        # At ismi yoksa satırı alma
        if not horse_name:
            continue

        # Başlık satırı yanlışlıkla veri olarak geldiyse
        if horse_name.lower() in [
            "at ismi",
            "at",
            "isim",
        ]:
            continue

        horse["at_ismi"] = horse_name

        horses.append(horse)

    return horses


# =========================================================
# TÜM AT TABLOLARINI BUL
# =========================================================

def parse_horse_tables(html):
    """
    Sayfadaki HTML tablolarını pandas ile okur ve
    at tablolarını seçer.
    """

    horse_tables = []

    try:
        tables = pd.read_html(
            StringIO(html)
        )
    except Exception:
        return horse_tables

    for table in tables:

        try:
            normalized = normalize_columns(table)

            if is_horse_table(normalized):

                horses = parse_horse_dataframe(
                    normalized
                )

                if horses:
                    horse_tables.append(
                        horses
                    )

        except Exception:
            continue

    return horse_tables


# =========================================================
# YARIŞ BAŞLIKLARINI BUL
# =========================================================

def parse_race_headings(html):
    """
    TJK HTML içinden:

    1. Koşu 17.45
    2. Koşu 18.15

    gibi yarış başlıklarını bulur.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # Script/style içeriklerini temizle
    for tag in soup(
        ["script", "style"]
    ):
        tag.decompose()

    text = soup.get_text(
        " ",
        strip=True
    )

    text = clean_text(text)

    races = []

    # Öncelikle normal yapı
    patterns = [
        r"(\d{1,2})\s*\.\s*Koşu\s*[—–-]?\s*(\d{1,2}:\d{2})",
        r"(\d{1,2})\s*\.\s*Koşu\s+(\d{1,2}:\d{2})",
        r"(\d{1,2})\.\s*Koşu.*?(\d{1,2}:\d{2})",
    ]

    matches = []

    for pattern in patterns:

        try:
            found = re.findall(
                pattern,
                text,
                flags=re.IGNORECASE
            )

            if found:
                matches = found
                break

        except Exception:
            continue

    seen = set()

    for match in matches:

        try:
            race_number = int(
                match[0]
            )

            race_time = clean_text(
                match[1]
            )

        except Exception:
            continue

        if race_number in seen:
            continue

        seen.add(race_number)

        races.append(
            {
                "race_number": race_number,
                "race_time": race_time,
                "horses": [],
            }
        )

    # Sıralama
    races.sort(
        key=lambda item: item[
            "race_number"
        ]
    )

    return races


# =========================================================
# DAHA GENİŞ KOŞU BAŞLIĞI ARAMA
# =========================================================

def parse_race_numbers_fallback(html):
    """
    Normal regex hiçbir şey bulamazsa sadece koşu
    numaralarını arar.

    Örnek:
    1. Koşu
    2. Koşu
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    for tag in soup(
        ["script", "style"]
    ):
        tag.decompose()

    text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    found = re.findall(
        r"(\d{1,2})\s*\.\s*Koşu",
        text,
        flags=re.IGNORECASE
    )

    races = []

    seen = set()

    for number in found:

        try:
            race_number = int(number)
        except Exception:
            continue

        if race_number in seen:
            continue

        seen.add(race_number)

        races.append(
            {
                "race_number": race_number,
                "race_time": "",
                "horses": [],
            }
        )

    races.sort(
        key=lambda item: item[
            "race_number"
        ]
    )

    return races


# =========================================================
# YARIŞ DETAYLARI
# =========================================================

def extract_race_details(
    soup,
    race_number
):
    """
    Yarışın mümkün olan ek bilgilerini bulur.
    """

    details = {
        "race_condition": "",
        "distance": "",
        "surface": "",
        "prize": "",
    }

    if soup is None:
        return details

    # Sayfadaki tüm metin
    text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    # Yarış bölümünü yaklaşık olarak bulmaya çalış.
    pattern = (
        r""
        + str(race_number)
        + r"\s*\.\s*Koşu"
    )

    match = re.search(
        pattern,
        text,
        flags=re.IGNORECASE
    )

    if not match:
        return details

    start = match.start()

    # Bir sonraki koşuya kadar olan bölümü al
    next_pattern = (
        r"\d{1,2}\s*\.\s*Koşu"
    )

    next_match = re.search(
        next_pattern,
        text[
            match.end():
        ],
        flags=re.IGNORECASE
    )

    if next_match:
        end = (
            match.end()
            + next_match.start()
        )
    else:
        end = min(
            len(text),
            match.end() + 2000
        )

    race_text = text[
        start:end
    ]

    # Mesafe
    distance_match = re.search(
        r"(\d{3,4})\s*(?:m|M)\b",
        race_text
    )

    if distance_match:
        details["distance"] = (
            distance_match.group(1)
            + " m"
        )

    # Pist
    surface_patterns = [
        (r"\bKum\b", "Kum"),
        (r"\bÇim\b", "Çim"),
        (r"\bSentetik\b", "Sentetik"),
    ]

    for pattern, value in surface_patterns:

        if re.search(
            pattern,
            race_text,
            flags=re.IGNORECASE
        ):
            details["surface"] = value
            break

    return details


# =========================================================
# PROGRAM PARSER
# =========================================================

def parse_program(
    html,
    race_date,
    city
):
    """
    TJK HTML'sini Race-Intelligence program formatına çevirir.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # -----------------------------------------------------
    # 1. Koşuları bul
    # -----------------------------------------------------

    races = parse_race_headings(
        html
    )

    # Eğer saatli başlık bulunamazsa
    # sadece koşu numaralarını bul.
    if not races:
        races = parse_race_numbers_fallback(
            html
        )

    # -----------------------------------------------------
    # 2. At tablolarını bul
    # -----------------------------------------------------

    horse_tables = parse_horse_tables(
        html
    )

    # -----------------------------------------------------
    # 3. Koşulara at tablolarını sırayla bağla
    # -----------------------------------------------------

    for index, race in enumerate(races):

        if index < len(horse_tables):

            race["horses"] = (
                horse_tables[index]
            )

        else:

            race["horses"] = []

        # Yarış detayları
        details = extract_race_details(
            soup,
            race["race_number"]
        )

        race.update(
            details
        )

    # -----------------------------------------------------
    # 4. Genel sonuç
    # -----------------------------------------------------

    return {
        "ok": True,
        "source": "TJK",
        "date": format_date(
            race_date
        ),
        "city": city,
        "url": "",
        "http_status": 200,
        "races": races,
    }


# =========================================================
# ANA FONKSİYON
# =========================================================

def get_program(
    race_date,
    city
):
    """
    Race-Intelligence tarafından çağrılan ana fonksiyon.
    """

    result = fetch_program_html(
        race_date,
        city
    )

    html = result["html"]

    # -----------------------------------------------------
    # Parser
    # -----------------------------------------------------

    try:

        parsed = parse_program(
            html,
            race_date,
            city
        )

    except Exception as exc:

        parsed = {
            "ok": False,
            "source": "TJK",
            "date": format_date(
                race_date
            ),
            "city": city,
            "url": result["url"],
            "http_status": result[
                "status_code"
            ],
            "races": [],
            "parse_error": str(exc),
        }

    # -----------------------------------------------------
    # Güvenlik
    # -----------------------------------------------------

    if not isinstance(
        parsed,
        dict
    ):

        parsed = {
            "ok": False,
            "source": "TJK",
            "date": format_date(
                race_date
            ),
            "city": city,
            "url": result["url"],
            "http_status": result[
                "status_code"
            ],
            "races": [],
            "parse_error": (
                "Parser geçersiz sonuç döndürdü."
            ),
        }

    # URL ve HTTP bilgilerini kesinleştir
    parsed["url"] = result["url"]
    parsed["http_status"] = result[
        "status_code"
    ]

    # -----------------------------------------------------
    # DEBUG BİLGİLERİ
    # -----------------------------------------------------

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    visible_text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    parsed["debug"] = {
        "html_length": len(html),

        "visible_text_length": len(
            visible_text
        ),

        "has_kosu_text": (
            "Koşu" in visible_text
        ),

        "has_at_ismi_text": (
            "At İsmi" in visible_text
        ),

        "has_jokey_text": (
            "Jokey" in visible_text
        ),

        "table_count": len(
            soup.find_all("table")
        ),

        "h1_count": len(
            soup.find_all("h1")
        ),

        "h2_count": len(
            soup.find_all("h2")
        ),

        "h3_count": len(
            soup.find_all("h3")
        ),

        "h4_count": len(
            soup.find_all("h4")
        ),

        "race_pattern_count": len(
            re.findall(
                r"\d{1,2}\s*\.\s*Koşu",
                visible_text,
                flags=re.IGNORECASE
            )
        ),

        "horse_table_count": len(
            parse_horse_tables(html)
        ),

        "parsed_race_count": len(
            parsed.get(
                "races",
                []
            )
        ),

        "html_start": html[:1500],
    }

    return parsed
