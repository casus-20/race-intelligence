import re
from datetime import date, datetime
from urllib.parse import urlencode

import pandas as pd
import requests
from bs4 import BeautifulSoup


# ============================================================
# TJK AYARLARI
# ============================================================

TJK_BASE_URL = (
    "https://www.tjk.org/TR/YarisSever/Info/Sehir/GunlukYarisProgrami"
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


class TJKFetchError(Exception):
    pass


# ============================================================
# TARİH
# ============================================================

def format_tjk_date(value):

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

    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        return value

    raise ValueError(
        f"Geçersiz tarih: {value}"
    )


# ============================================================
# URL
# ============================================================

def build_program_url(race_date, city):

    if city not in CITY_IDS:
        raise ValueError(
            f"Bilinmeyen hipodrom: {city}"
        )

    params = {
        "Era": "today",
        "QueryParameter_Tarih": format_tjk_date(race_date),
        "SehirAdi": city,
        "SehirId": CITY_IDS[city],
    }

    return f"{TJK_BASE_URL}?{urlencode(params)}"


# ============================================================
# TJK HTML
# ============================================================

def fetch_program_html(
    race_date,
    city,
    timeout=30
):

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
            f"TJK HTTP hatası: {response.status_code}"
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
# TEMİZLEME
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    text = str(value)

    text = text.replace("\xa0", " ")

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# KOŞU NUMARASI
# ============================================================

def extract_race_number(text):

    text = clean_text(text)

    patterns = [
        r"(\d+)\.\s*Koşu",
        r"(\d+)\s*\.\s*Koşu",
        r"(\d+)\s*Koşu",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            return int(
                match.group(1)
            )

    return None


# ============================================================
# SAAT
# ============================================================

def extract_time(text):

    text = clean_text(text)

    match = re.search(
        r"\b(\d{1,2}:\d{2})\b",
        text
    )

    if match:
        return match.group(1)

    return None


# ============================================================
# KOŞU BAŞLIKLARI
# ============================================================

def find_races(soup):

    races = []

    # Öncelikle tüm metin içeren elementleri kontrol ediyoruz.
    elements = soup.find_all(
        ["div", "span", "td", "th", "h1", "h2", "h3", "h4", "h5"]
    )

    seen = set()

    for element in elements:

        text = clean_text(
            element.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        race_number = extract_race_number(
            text
        )

        if race_number is None:
            continue

        # Çok uzun parent/container metinlerini ele
        if len(text) > 250:
            continue

        race_time = extract_time(
            text
        )

        key = (
            race_number,
            race_time
        )

        if key in seen:
            continue

        seen.add(key)

        races.append({
            "race_number": race_number,
            "race_time": race_time,
            "title": text,
            "horses": [],
        })

    # Numaraya göre sırala
    races.sort(
        key=lambda x: x["race_number"]
    )

    # Aynı koşunun tekrarlarını temizle
    result = []
    numbers = set()

    for race in races:

        number = race["race_number"]

        if number in numbers:
            continue

        numbers.add(number)

        result.append(race)

    return result


# ============================================================
# SÜTUN NORMALİZASYONU
# ============================================================

def normalize_column_name(value):

    text = clean_text(value)

    text_lower = text.lower()

    mapping = {

        "n": "number",

        "at i̇smi": "horse_name",
        "at ismi": "horse_name",
        "at adı": "horse_name",
        "at adi": "horse_name",

        "yaş": "age",
        "yas": "age",

        "sıklet": "weight",
        "siklet": "weight",

        "jokey": "jockey",

        "sahip": "owner",

        "antrenör": "trainer",
        "antrenor": "trainer",

        "st": "start",

        "hp": "hp",

        "son 6 y.": "last6",
        "son 6": "last6",

        "kgs": "kgs",

        "s20": "s20",

        "en iyi d.": "best_time",
        "en iyi d": "best_time",

        "gny": "odds",

        "agf": "agf",

        "i̇dm": "workout",
        "idm": "workout",

        "forma": "form",

        "orijin": "origin",
    }

    if text_lower in mapping:
        return mapping[text_lower]

    return text


# ============================================================
# DATAFRAME SÜTUNLARI
# ============================================================

def normalize_dataframe_columns(df):

    columns = []

    for column in df.columns:

        # MultiIndex
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

            name = " ".join(parts)

        else:

            name = clean_text(column)

        columns.append(
            normalize_column_name(name)
        )

    df.columns = columns

    return df


# ============================================================
# AT TABLOSU MU?
# ============================================================

def looks_like_horse_table(df):

    if df is None or df.empty:
        return False

    columns = [
        normalize_column_name(
            str(column)
        ).lower()
        for column in df.columns
    ]

    joined = " ".join(columns)

    indicators = [
        "horse_name",
        "weight",
        "jockey",
        "hp",
        "last6",
        "agf",
        "workout",
        "start",
    ]

    score = 0

    for indicator in indicators:

        if indicator in joined:
            score += 1

    return score >= 2


# ============================================================
# AT TABLOSU PARSE
# ============================================================

def dataframe_to_horses(df):

    if df is None or df.empty:
        return []

    df = df.copy()

    df = normalize_dataframe_columns(
        df
    )

    # MultiIndex kolonlarını tekrar kontrol et
    if isinstance(
        df.columns,
        pd.MultiIndex
    ):

        df.columns = [
            clean_text(
                " ".join(
                    str(x)
                    for x in column
                    if str(x).lower() != "nan"
                )
            )
            for column in df.columns
        ]

    horses = []

    for _, row in df.iterrows():

        item = {}

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

            item[column] = value

        # At adını bul
        horse_name = None

        for key in [
            "horse_name",
            "At İsmi",
            "At Ismi",
            "At Adı",
        ]:

            if key in item:

                value = item[key]

                if value:
                    horse_name = value
                    break

        # At adı bulunamazsa ilk anlamlı
        # string kolonlardan birini kontrol et
        if not horse_name:

            for key, value in item.items():

                if not value:
                    continue

                value_text = str(value)

                if (
                    len(value_text) >= 2
                    and not re.fullmatch(
                        r"\d+",
                        value_text
                    )
                    and ":" not in value_text
                ):

                    # Kolon adı at ismine benziyorsa
                    if any(
                        word in key.lower()
                        for word in [
                            "at",
                            "isim",
                            "horse"
                        ]
                    ):

                        horse_name = value_text
                        break

        if not horse_name:
            continue

        item["horse_name"] = horse_name

        horses.append(item)

    return horses


# ============================================================
# TÜM HTML TABLOLARINI OKU
# ============================================================

def extract_horse_tables(html):

    try:

        dataframes = pd.read_html(
            html
        )

    except Exception:

        return []

    result = []

    for index, df in enumerate(
        dataframes
    ):

        if df is None or df.empty:
            continue

        df = normalize_dataframe_columns(
            df
        )

        if not looks_like_horse_table(
            df
        ):
            continue

        horses = dataframe_to_horses(
            df
        )

        if not horses:
            continue

        result.append({
            "table_index": index,
            "horses": horses,
        })

    return result


# ============================================================
# KOŞU BİLGİLERİ
# ============================================================

def extract_race_details(
    soup,
    race_number
):

    text = soup.get_text(
        " ",
        strip=True
    )

    # Basit mesafe / pist tespiti
    pattern = re.compile(
        rf"{race_number}\.\s*Koşu"
        rf".{{0,120}}?"
        rf"(\d{{3,4}})\s*"
        rf"(Çim|Kum|Sentetik)",
        re.IGNORECASE
    )

    match = pattern.search(
        text
    )

    if match:

        distance = int(
            match.group(1)
        )

        track = match.group(2)

    else:

        distance = None
        track = None

    return {
        "distance": distance,
        "track": track,
    }


# ============================================================
# PROGRAM PARSE
# ============================================================

def parse_program_html(
    html,
    race_date=None,
    city=None
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # --------------------------------------------------------
    # KOŞULAR
    # --------------------------------------------------------

    races = find_races(
        soup
    )

    # --------------------------------------------------------
    # TÜM AT TABLOLARI
    # --------------------------------------------------------

    horse_tables = extract_horse_tables(
        html
    )

    # --------------------------------------------------------
    # TABLOLARI KOŞULARA SIRAYLA DAĞIT
    # --------------------------------------------------------

    for index, race in enumerate(
        races
    ):

        if index < len(
            horse_tables
        ):

            race["horses"] = (
                horse_tables[index]["horses"]
            )

        details = extract_race_details(
            soup,
            race["race_number"]
        )

        race.update(
            details
        )

    # --------------------------------------------------------
    # SONUÇ
    # --------------------------------------------------------

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

    data["http_status"] = (
        result["status_code"]
    )

    return dataimport re
from datetime import date, datetime
from urllib.parse import urlencode

import pandas as pd
import requests
from bs4 import BeautifulSoup


# ============================================================
# TJK AYARLARI
# ============================================================

TJK_BASE_URL = (
    "https://www.tjk.org/TR/YarisSever/Info/Sehir/GunlukYarisProgrami"
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


class TJKFetchError(Exception):
    pass


# ============================================================
# TARİH
# ============================================================

def format_tjk_date(value):

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

    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        return value

    raise ValueError(
        f"Geçersiz tarih: {value}"
    )


# ============================================================
# URL
# ============================================================

def build_program_url(race_date, city):

    if city not in CITY_IDS:
        raise ValueError(
            f"Bilinmeyen hipodrom: {city}"
        )

    params = {
        "Era": "today",
        "QueryParameter_Tarih": format_tjk_date(race_date),
        "SehirAdi": city,
        "SehirId": CITY_IDS[city],
    }

    return f"{TJK_BASE_URL}?{urlencode(params)}"


# ============================================================
# TJK HTML
# ============================================================

def fetch_program_html(
    race_date,
    city,
    timeout=30
):

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
            f"TJK HTTP hatası: {response.status_code}"
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
# TEMİZLEME
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    text = str(value)

    text = text.replace("\xa0", " ")

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# KOŞU NUMARASI
# ============================================================

def extract_race_number(text):

    text = clean_text(text)

    patterns = [
        r"(\d+)\.\s*Koşu",
        r"(\d+)\s*\.\s*Koşu",
        r"(\d+)\s*Koşu",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            return int(
                match.group(1)
            )

    return None


# ============================================================
# SAAT
# ============================================================

def extract_time(text):

    text = clean_text(text)

    match = re.search(
        r"\b(\d{1,2}:\d{2})\b",
        text
    )

    if match:
        return match.group(1)

    return None


# ============================================================
# KOŞU BAŞLIKLARI
# ============================================================

def find_races(soup):

    races = []

    # Öncelikle tüm metin içeren elementleri kontrol ediyoruz.
    elements = soup.find_all(
        ["div", "span", "td", "th", "h1", "h2", "h3", "h4", "h5"]
    )

    seen = set()

    for element in elements:

        text = clean_text(
            element.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        race_number = extract_race_number(
            text
        )

        if race_number is None:
            continue

        # Çok uzun parent/container metinlerini ele
        if len(text) > 250:
            continue

        race_time = extract_time(
            text
        )

        key = (
            race_number,
            race_time
        )

        if key in seen:
            continue

        seen.add(key)

        races.append({
            "race_number": race_number,
            "race_time": race_time,
            "title": text,
            "horses": [],
        })

    # Numaraya göre sırala
    races.sort(
        key=lambda x: x["race_number"]
    )

    # Aynı koşunun tekrarlarını temizle
    result = []
    numbers = set()

    for race in races:

        number = race["race_number"]

        if number in numbers:
            continue

        numbers.add(number)

        result.append(race)

    return result


# ============================================================
# SÜTUN NORMALİZASYONU
# ============================================================

def normalize_column_name(value):

    text = clean_text(value)

    text_lower = text.lower()

    mapping = {

        "n": "number",

        "at i̇smi": "horse_name",
        "at ismi": "horse_name",
        "at adı": "horse_name",
        "at adi": "horse_name",

        "yaş": "age",
        "yas": "age",

        "sıklet": "weight",
        "siklet": "weight",

        "jokey": "jockey",

        "sahip": "owner",

        "antrenör": "trainer",
        "antrenor": "trainer",

        "st": "start",

        "hp": "hp",

        "son 6 y.": "last6",
        "son 6": "last6",

        "kgs": "kgs",

        "s20": "s20",

        "en iyi d.": "best_time",
        "en iyi d": "best_time",

        "gny": "odds",

        "agf": "agf",

        "i̇dm": "workout",
        "idm": "workout",

        "forma": "form",

        "orijin": "origin",
    }

    if text_lower in mapping:
        return mapping[text_lower]

    return text


# ============================================================
# DATAFRAME SÜTUNLARI
# ============================================================

def normalize_dataframe_columns(df):

    columns = []

    for column in df.columns:

        # MultiIndex
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

            name = " ".join(parts)

        else:

            name = clean_text(column)

        columns.append(
            normalize_column_name(name)
        )

    df.columns = columns

    return df


# ============================================================
# AT TABLOSU MU?
# ============================================================

def looks_like_horse_table(df):

    if df is None or df.empty:
        return False

    columns = [
        normalize_column_name(
            str(column)
        ).lower()
        for column in df.columns
    ]

    joined = " ".join(columns)

    indicators = [
        "horse_name",
        "weight",
        "jockey",
        "hp",
        "last6",
        "agf",
        "workout",
        "start",
    ]

    score = 0

    for indicator in indicators:

        if indicator in joined:
            score += 1

    return score >= 2


# ============================================================
# AT TABLOSU PARSE
# ============================================================

def dataframe_to_horses(df):

    if df is None or df.empty:
        return []

    df = df.copy()

    df = normalize_dataframe_columns(
        df
    )

    # MultiIndex kolonlarını tekrar kontrol et
    if isinstance(
        df.columns,
        pd.MultiIndex
    ):

        df.columns = [
            clean_text(
                " ".join(
                    str(x)
                    for x in column
                    if str(x).lower() != "nan"
                )
            )
            for column in df.columns
        ]

    horses = []

    for _, row in df.iterrows():

        item = {}

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

            item[column] = value

        # At adını bul
        horse_name = None

        for key in [
            "horse_name",
            "At İsmi",
            "At Ismi",
            "At Adı",
        ]:

            if key in item:

                value = item[key]

                if value:
                    horse_name = value
                    break

        # At adı bulunamazsa ilk anlamlı
        # string kolonlardan birini kontrol et
        if not horse_name:

            for key, value in item.items():

                if not value:
                    continue

                value_text = str(value)

                if (
                    len(value_text) >= 2
                    and not re.fullmatch(
                        r"\d+",
                        value_text
                    )
                    and ":" not in value_text
                ):

                    # Kolon adı at ismine benziyorsa
                    if any(
                        word in key.lower()
                        for word in [
                            "at",
                            "isim",
                            "horse"
                        ]
                    ):

                        horse_name = value_text
                        break

        if not horse_name:
            continue

        item["horse_name"] = horse_name

        horses.append(item)

    return horses


# ============================================================
# TÜM HTML TABLOLARINI OKU
# ============================================================

def extract_horse_tables(html):

    try:

        dataframes = pd.read_html(
            html
        )

    except Exception:

        return []

    result = []

    for index, df in enumerate(
        dataframes
    ):

        if df is None or df.empty:
            continue

        df = normalize_dataframe_columns(
            df
        )

        if not looks_like_horse_table(
            df
        ):
            continue

        horses = dataframe_to_horses(
            df
        )

        if not horses:
            continue

        result.append({
            "table_index": index,
            "horses": horses,
        })

    return result


# ============================================================
# KOŞU BİLGİLERİ
# ============================================================

def extract_race_details(
    soup,
    race_number
):

    text = soup.get_text(
        " ",
        strip=True
    )

    # Basit mesafe / pist tespiti
    pattern = re.compile(
        rf"{race_number}\.\s*Koşu"
        rf".{{0,120}}?"
        rf"(\d{{3,4}})\s*"
        rf"(Çim|Kum|Sentetik)",
        re.IGNORECASE
    )

    match = pattern.search(
        text
    )

    if match:

        distance = int(
            match.group(1)
        )

        track = match.group(2)

    else:

        distance = None
        track = None

    return {
        "distance": distance,
        "track": track,
    }


# ============================================================
# PROGRAM PARSE
# ============================================================

def parse_program_html(
    html,
    race_date=None,
    city=None
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # --------------------------------------------------------
    # KOŞULAR
    # --------------------------------------------------------

    races = find_races(
        soup
    )

    # --------------------------------------------------------
    # TÜM AT TABLOLARI
    # --------------------------------------------------------

    horse_tables = extract_horse_tables(
        html
    )

    # --------------------------------------------------------
    # TABLOLARI KOŞULARA SIRAYLA DAĞIT
    # --------------------------------------------------------

    for index, race in enumerate(
        races
    ):

        if index < len(
            horse_tables
        ):

            race["horses"] = (
                horse_tables[index]["horses"]
            )

        details = extract_race_details(
            soup,
            race["race_number"]
        )

        race.update(
            details
        )

    # --------------------------------------------------------
    # SONUÇ
    # --------------------------------------------------------

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

    data["http_status"] = (
        result["status_code"]
    )

    return data
