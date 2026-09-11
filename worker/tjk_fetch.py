import re
from datetime import date, datetime

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
    "Accept-Language": (
        "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
    ),
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

    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")

    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    value = str(value).strip()

    if not value:
        return ""

    if re.fullmatch(
        r"\d{4}-\d{2}-\d{2}",
        value
    ):
        year, month, day = value.split("-")
        return f"{day}/{month}/{year}"

    if re.fullmatch(
        r"\d{2}\.\d{2}\.\d{4}",
        value
    ):
        day, month, year = value.split(".")
        return f"{day}/{month}/{year}"

    if re.fullmatch(
        r"\d{2}/\d{2}/\d{4}",
        value
    ):
        return value

    return value


# =========================================================
# URL
# =========================================================

def build_program_url(
    race_date,
    city
):

    if city not in CITY_IDS:

        raise TJKFetchError(
            "Bilinmeyen hipodrom: "
            + str(city)
        )

    params = {
        "Era": "today",
        "QueryParameter_Tarih": format_date(
            race_date
        ),
        "SehirAdi": city,
        "SehirId": CITY_IDS[city],
    }

    request = requests.Request(
        "GET",
        TJK_URL,
        params=params
    ).prepare()

    return request.url


# =========================================================
# HTML GETİR
# =========================================================

def fetch_program_html(
    race_date,
    city
):

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
            "TJK bağlantı hatası: "
            + str(exc)
        )

    if response.status_code != 200:

        raise TJKFetchError(
            "TJK HTTP hatası: "
            + str(response.status_code)
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


# =========================================================
# METİN TEMİZLE
# =========================================================

def clean_text(value):

    if value is None:
        return ""

    text = str(value)

    if text.lower() == "nan":
        return ""

    text = text.replace(
        "\xa0",
        " "
    )

    text = text.replace(
        "\n",
        " "
    )

    text = text.replace(
        "\r",
        " "
    )

    text = text.replace(
        "\t",
        " "
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =========================================================
# SÜTUN NORMALİZASYONU
# =========================================================

def normalize_column(
    value
):

    if isinstance(
        value,
        tuple
    ):

        parts = []

        for item in value:

            text = clean_text(
                item
            )

            if text:
                parts.append(text)

        value = " ".join(parts)

    value = clean_text(
        value
    )

    normalized = {
        "Forma": "Forma",
        "N": "N",
        "At İsmi": "At İsmi",
        "At Ismi": "At İsmi",
        "AT İSMİ": "At İsmi",
        "AT ISMI": "At İsmi",
        "Yaş": "Yaş",
        "Yas": "Yaş",
        "Orijin(Baba - Anne)": "Orijin",
        "Orijin (Baba - Anne)": "Orijin",
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

    return normalized.get(
        value,
        value
    )


# =========================================================
# TABLE SATIRLARINI OKU
# =========================================================

def extract_html_table_rows(
    table
):

    rows = []

    for tr in table.find_all(
        "tr"
    ):

        cells = tr.find_all(
            ["th", "td"]
        )

        if not cells:
            continue

        row = []

        for cell in cells:

            text = clean_text(
                cell.get_text(
                    " ",
                    strip=True
                )
            )

            row.append(
                text
            )

        if row:
            rows.append(row)

    return rows


# =========================================================
# BAŞLIK SATIRINI BUL
# =========================================================

def find_header_row(
    rows
):

    for index, row in enumerate(
        rows
    ):

        normalized = [
            normalize_column(
                cell
            )
            for cell in row
        ]

        text = " | ".join(
            normalized
        ).lower()

        if (
            "at ismi" in text
            and "sıklet" in text
        ):

            return (
                index,
                normalized
            )

        # Bazı TJK tablolarında Sıklet
        # başlığı farklı işlenebilir.
        if (
            "at ismi" in text
            and "jokey" in text
        ):

            return (
                index,
                normalized
            )

    return (
        None,
        None
    )


# =========================================================
# AT TABLOSUNU PARSE ET
# =========================================================

def parse_single_horse_table(
    table
):

    rows = extract_html_table_rows(
        table
    )

    if not rows:
        return []


    header_index, headers = (
        find_header_row(
            rows
        )
    )

    if header_index is None:
        return []


    # -----------------------------------------------------
    # Sütunları standartlaştır
    # -----------------------------------------------------

    headers = [
        normalize_column(
            header
        )
        for header in headers
    ]


    # Aynı isimli sütunları benzersiz yap
    final_headers = []

    used = {}

    for header in headers:

        if not header:

            header = (
                f"Kolon_{len(final_headers)}"
            )

        if header not in used:

            used[header] = 1
            final_headers.append(
                header
            )

        else:

            used[header] += 1

            final_headers.append(
                f"{header}_{used[header]}"
            )


    # -----------------------------------------------------
    # AT İSMİ KOLONUNU BUL
    # -----------------------------------------------------

    horse_column_index = None

    for index, header in enumerate(
        final_headers
    ):

        if header == "At İsmi":

            horse_column_index = index
            break


    if horse_column_index is None:
        return []


    horses = []


    # -----------------------------------------------------
    # VERİ SATIRLARI
    # -----------------------------------------------------

    for row in rows[
        header_index + 1:
    ]:

        if not row:
            continue


        # Kolon sayısını eşitle
        values = list(row)

        if len(values) < len(
            final_headers
        ):

            values.extend(
                [""] * (
                    len(final_headers)
                    - len(values)
                )
            )

        elif len(values) > len(
            final_headers
        ):

            values = values[
                :len(final_headers)
            ]


        # At adı
        horse_name = clean_text(
            values[
                horse_column_index
            ]
        )


        # -------------------------------------------------
        # Geçersiz satırlar
        # -------------------------------------------------

        if not horse_name:
            continue

        if horse_name.lower() in [
            "at ismi",
            "at",
            "isim"
        ]:
            continue


        # -------------------------------------------------
        # Yarış başlığı satırlarını engelle
        # -------------------------------------------------

        if "koşu" in horse_name.lower():

            continue


        # -------------------------------------------------
        # At nesnesi
        # -------------------------------------------------

        horse = {}

        for index, header in enumerate(
            final_headers
        ):

            if index >= len(
                values
            ):
                value = ""

            else:
                value = values[index]

            horse[header] = clean_text(
                value
            )


        # -------------------------------------------------
        # Standart alan
        # -------------------------------------------------

        horse["at_ismi"] = horse_name


        # -------------------------------------------------
        # Ek kolay alanlar
        # -------------------------------------------------

        horse["numara"] = (
            horse.get(
                "N",
                ""
            )
        )

        horse["yas"] = (
            horse.get(
                "Yaş",
                ""
            )
        )

        horse["siklet"] = (
            horse.get(
                "Sıklet",
                ""
            )
        )

        horse["jokey"] = (
            horse.get(
                "Jokey",
                ""
            )
        )

        horse["hp"] = (
            horse.get(
                "HP",
                ""
            )
        )

        horse["agf"] = (
            horse.get(
                "AGF",
                ""
            )
        )

        horse["st"] = (
            horse.get(
                "St",
                ""
            )
        )

        horse["form"] = (
            horse.get(
                "Son 6 Y.",
                ""
            )
        )

        horses.append(
            horse
        )


    return horses


# =========================================================
# TÜM AT TABLOLARINI BUL
# =========================================================

def parse_horse_tables(
    html
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    tables = soup.find_all(
        "table"
    )

    horse_tables = []


    for table in tables:

        horses = (
            parse_single_horse_table(
                table
            )
        )

        if horses:

            horse_tables.append(
                horses
            )


    return horse_tables


# =========================================================
# KOŞU BAŞLIKLARI
# =========================================================

def parse_race_headings(
    html
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # Script/style kaldır
    for tag in soup.find_all(
        ["script", "style"]
    ):

        tag.decompose()


    # Önce HTML başlıklarını kontrol et
    elements = soup.find_all(
        ["h1", "h2", "h3", "h4", "th"]
    )


    races = []

    seen = set()


    for element in elements:

        text = clean_text(
            element.get_text(
                " ",
                strip=True
            )
        )

        if "Koşu" not in text:
            continue


        match = re.search(
            r"(\d{1,2})\s*\.\s*Koşu"
            r"(?:\s+|[—–-]\s*)"
            r"(\d{1,2}[:.]\d{2})?",
            text,
            flags=re.IGNORECASE
        )


        if not match:
            continue


        try:

            race_number = int(
                match.group(1)
            )

        except Exception:

            continue


        race_time = ""

        if match.group(2):

            race_time = (
                match.group(2)
                .replace(
                    ".",
                    ":"
                )
            )


        if race_number in seen:
            continue


        seen.add(
            race_number
        )


        races.append(
            {
                "race_number": race_number,
                "race_time": race_time,
                "horses": [],
            }
        )


    # HTML başlıklarından bulunamazsa
    # bütün metinden ara
    if not races:

        text = clean_text(
            soup.get_text(
                " ",
                strip=True
            )
        )


        matches = re.findall(
            r"(\d{1,2})\s*\.\s*Koşu"
            r"(?:\s+|[—–-]\s*)"
            r"(\d{1,2}[:.]\d{2})?",
            text,
            flags=re.IGNORECASE
        )


        for match in matches:

            try:

                race_number = int(
                    match[0]
                )

            except Exception:

                continue


            if race_number in seen:
                continue


            seen.add(
                race_number
            )


            race_time = ""

            if len(match) > 1:

                race_time = (
                    match[1]
                    .replace(
                        ".",
                        ":"
                    )
                )


            races.append(
                {
                    "race_number": race_number,
                    "race_time": race_time,
                    "horses": [],
                }
            )


    races.sort(
        key=lambda item:
        item["race_number"]
    )


    return races


# =========================================================
# KOŞU NUMARASI FALLBACK
# =========================================================

def parse_race_numbers_fallback(
    html
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )


    matches = re.findall(
        r"(\d{1,2})\s*\.\s*Koşu",
        text,
        flags=re.IGNORECASE
    )


    races = []

    seen = set()


    for number in matches:

        try:

            race_number = int(
                number
            )

        except Exception:

            continue


        if race_number in seen:
            continue


        seen.add(
            race_number
        )


        races.append(
            {
                "race_number": race_number,
                "race_time": "",
                "horses": [],
            }
        )


    races.sort(
        key=lambda item:
        item["race_number"]
    )


    return races


# =========================================================
# KOŞU DETAYLARI
# =========================================================

def extract_race_details(
    soup,
    race_number
):

    details = {
        "race_condition": "",
        "distance": "",
        "surface": "",
        "prize": "",
    }


    if soup is None:
        return details


    # -----------------------------------------------------
    # İlgili koşu başlığını bul
    # -----------------------------------------------------

    target = None


    for element in soup.find_all(
        ["h1", "h2", "h3", "h4", "th"]
    ):

        text = clean_text(
            element.get_text(
                " ",
                strip=True
            )
        )


        if re.match(
            rf"^{race_number}\s*\.\s*Koşu\b",
            text,
            flags=re.IGNORECASE
        ):

            target = element
            break


    if target is None:

        return details


    # -----------------------------------------------------
    # Koşu başlığı
    # -----------------------------------------------------

    heading_text = clean_text(
        target.get_text(
            " ",
            strip=True
        )
    )


    # Saat
    time_match = re.search(
        r"\b(\d{1,2})[:.](\d{2})\b",
        heading_text
    )


    if time_match:

        details["race_time"] = (
            f"{time_match.group(1)}:"
            f"{time_match.group(2)}"
        )


    # -----------------------------------------------------
    # Başlıktan sonraki metin
    # -----------------------------------------------------

    next_elements = []

    current = target.find_next_sibling()

    counter = 0


    while current is not None:

        text = clean_text(
            current.get_text(
                " ",
                strip=True
            )
        )


        if text:

            # Sonraki koşuya geldik
            if re.match(
                r"^\d{1,2}\s*\.\s*Koşu\b",
                text,
                flags=re.IGNORECASE
            ):

                break


            next_elements.append(
                text
            )


        current = current.find_next_sibling()

        counter += 1

        if counter > 20:
            break


    context = " ".join(
        next_elements
    )


    # Eğer sibling yapısı yoksa
    # sayfanın genel metninden yaklaşık bölüm al.
    if not context:

        full_text = clean_text(
            soup.get_text(
                " ",
                strip=True
            )
        )


        pattern = (
            rf"{race_number}\s*\.\s*Koşu"
        )


        match = re.search(
            pattern,
            full_text,
            flags=re.IGNORECASE
        )


        if match:

            remaining = full_text[
                match.end():
            ]


            next_match = re.search(
                r"\d{1,2}\s*\.\s*Koşu",
                remaining,
                flags=re.IGNORECASE
            )


            if next_match:

                context = remaining[
                    :next_match.start()
                ]

            else:

                context = remaining[
                    :1500
                ]


    # -----------------------------------------------------
    # Mesafe
    # -----------------------------------------------------

    distance_match = re.search(
        r"\b(\d{3,4})\s*(?:m|M)\b",
        context
    )


    if distance_match:

        details["distance"] = (
            distance_match.group(1)
            + " m"
        )


    # -----------------------------------------------------
    # Pist
    # -----------------------------------------------------

    if re.search(
        r"\bKum\b",
        context,
        flags=re.IGNORECASE
    ):

        details["surface"] = "Kum"

    elif re.search(
        r"\bÇim\b",
        context,
        flags=re.IGNORECASE
    ):

        details["surface"] = "Çim"

    elif re.search(
        r"\bSentetik\b",
        context,
        flags=re.IGNORECASE
    ):

        details["surface"] = "Sentetik"


    # -----------------------------------------------------
    # Koşu şartı
    # -----------------------------------------------------

    condition_patterns = [
        r"(ŞARTLI\s*\d+[^,]*)",
        r"(HANDİKAP\s*\d+[^,]*)",
        r"(KV[- ]?\d+[^,]*)",
        r"(MAIDEN[^,]*)",
    ]


    for pattern in condition_patterns:

        match = re.search(
            pattern,
            heading_text + " " + context,
            flags=re.IGNORECASE
        )


        if match:

            details["race_condition"] = clean_text(
                match.group(1)
            )

            break


    return details


# =========================================================
# PROGRAM PARSE
# =========================================================

def parse_program(
    html,
    race_date,
    city
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )


    # -----------------------------------------------------
    # KOŞULAR
    # -----------------------------------------------------

    races = parse_race_headings(
        html
    )


    if not races:

        races = parse_race_numbers_fallback(
            html
        )


    # -----------------------------------------------------
    # AT TABLOLARI
    # -----------------------------------------------------

    horse_tables = parse_horse_tables(
        html
    )


    # -----------------------------------------------------
    # KOŞULARA AT TABLOLARINI BAĞLA
    # -----------------------------------------------------

    for index, race in enumerate(
        races
    ):

        if index < len(
            horse_tables
        ):

            race["horses"] = (
                horse_tables[index]
            )

        else:

            race["horses"] = []


        # Koşu detayları
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

    result = fetch_program_html(
        race_date,
        city
    )


    html = result["html"]


    # -----------------------------------------------------
    # PROGRAM PARSE
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
    # GÜVENLİK
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


    # -----------------------------------------------------
    # URL / HTTP
    # -----------------------------------------------------

    parsed["url"] = result["url"]

    parsed["http_status"] = (
        result["status_code"]
    )


    # =====================================================
    # DEBUG
    # =====================================================

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


    parsed_races = parsed.get(
        "races",
        []
    )


    total_horses = sum(
        len(
            race.get(
                "horses",
                []
            )
        )
        for race in parsed_races
    )


    parsed["debug"] = {

        "html_length": len(
            html
        ),

        "visible_text_length": len(
            visible_text
        ),

        "has_kosu_text": (
            "Koşu"
            in visible_text
        ),

        "has_at_ismi_text": (
            "At İsmi"
            in visible_text
        ),

        "has_jokey_text": (
            "Jokey"
            in visible_text
        ),

        "table_count": len(
            soup.find_all(
                "table"
            )
        ),

        "h1_count": len(
            soup.find_all(
                "h1"
            )
        ),

        "h2_count": len(
            soup.find_all(
                "h2"
            )
        ),

        "h3_count": len(
            soup.find_all(
                "h3"
            )
        ),

        "h4_count": len(
            soup.find_all(
                "h4"
            )
        ),

        "race_pattern_count": len(
            re.findall(
                r"\d{1,2}\s*\.\s*Koşu",
                visible_text,
                flags=re.IGNORECASE
            )
        ),

        "horse_table_count": len(
            horse_tables
        ),

        "parsed_race_count": len(
            parsed_races
        ),

        "total_horse_count": (
            total_horses
        ),

        "html_start": html[:1500],
    }


    # =====================================================
    # KOŞU BAŞINA AT SAYISI DEBUG
    # =====================================================

    parsed["debug"][
        "horses_per_race"
    ] = {

        str(
            race.get(
                "race_number"
            )
        ): len(
            race.get(
                "horses",
                []
            )
        )

        for race in parsed_races
    }


    return parsed
