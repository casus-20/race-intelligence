import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup


# ============================================================
# TJK HİPODROM ID'LERİ
# ============================================================

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


# ============================================================
# TJK PROGRAM URL
# ============================================================

TJK_URL = (
    "https://www.tjk.org/"
    "TR/YarisSever/Info/"
    "Sehir/GunlukYarisProgrami"
)


# ============================================================
# HTTP BAŞLIKLARI
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": (
        "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
    ),
    "Connection": "keep-alive",
}


# ============================================================
# GENEL METİN TEMİZLEME
# ============================================================

def normalize_text(value: Any) -> str:

    if value is None:
        return ""

    text = str(value)

    text = (
        text
        .replace("\xa0", " ")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("\t", " ")
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# BAŞLIK NORMALİZASYONU
# ============================================================

def normalize_header(value: Any) -> str:

    text = normalize_text(value)

    replacements = {
        "At İsmi": "At İsmi",
        "At Ismi": "At İsmi",
        "AT İSMİ": "At İsmi",

        "At Adı": "At İsmi",
        "At Adi": "At İsmi",

        "N": "N",

        "Yaş": "Yaş",
        "Yas": "Yaş",

        "Sıklet": "Sıklet",
        "Siklet": "Sıklet",

        "Jokey": "Jokey",

        "Sahip": "Sahip",

        "Antrenör": "Antrenör",

        "St": "St",

        "HP": "HP",

        "KGS": "KGS",

        "s20": "s20",
        "S20": "s20",

        "Son 6 Y.": "Son 6 Y.",
        "Son 6 Y": "Son 6 Y.",

        "En İyi D.": "En İyi D.",
        "En Iyi D.": "En İyi D.",

        "Gny": "Gny",

        "AGF": "AGF",

        "İdm": "İdm",
        "Idm": "İdm",

        "Forma": "Forma",

        "Orijin(Baba - Anne)": (
            "Orijin(Baba - Anne)"
        ),

        "Orijin (Baba - Anne)": (
            "Orijin(Baba - Anne)"
        ),
    }

    return replacements.get(
        text,
        text,
    )


# ============================================================
# TARİH FORMATLAMA
# ============================================================

def format_date(
    selected_date: Any,
) -> str:
    """
    TJK program sorgusu için:

    DD/MM/YYYY

    formatını kullanır.
    """

    if isinstance(
        selected_date,
        datetime,
    ):

        selected_date = (
            selected_date.date()
        )

    if isinstance(
        selected_date,
        date,
    ):

        return selected_date.strftime(
            "%d/%m/%Y"
        )

    text = normalize_text(
        selected_date
    )

    if not text:

        return date.today().strftime(
            "%d/%m/%Y"
        )

    # YYYY-MM-DD
    match = re.fullmatch(
        r"(\d{4})-(\d{1,2})-(\d{1,2})",
        text,
    )

    if match:

        year, month, day = (
            match.groups()
        )

        return (
            f"{int(day):02d}/"
            f"{int(month):02d}/"
            f"{int(year):04d}"
        )

    # DD.MM.YYYY
    match = re.fullmatch(
        r"(\d{1,2})\."
        r"(\d{1,2})\."
        r"(\d{4})",
        text,
    )

    if match:

        day, month, year = (
            match.groups()
        )

        return (
            f"{int(day):02d}/"
            f"{int(month):02d}/"
            f"{int(year):04d}"
        )

    # DD/MM/YYYY
    match = re.fullmatch(
        r"(\d{1,2})/"
        r"(\d{1,2})/"
        r"(\d{4})",
        text,
    )

    if match:

        day, month, year = (
            match.groups()
        )

        return (
            f"{int(day):02d}/"
            f"{int(month):02d}/"
            f"{int(year):04d}"
        )

    return text


# ============================================================
# PROGRAM URL OLUŞTUR
# ============================================================

def build_program_url(
    selected_date: Any,
    city: str,
) -> str:

    city_id = CITY_IDS.get(
        city
    )

    if city_id is None:

        raise ValueError(
            f"Geçersiz hipodrom: {city}"
        )

    tarih = format_date(
        selected_date
    )

    params = {
        "Era": "today",
        "QueryParameter_Tarih": tarih,
        "SehirAdi": city,
        "SehirId": city_id,
    }

    return (
        f"{TJK_URL}?"
        f"{urlencode(params)}"
    )


# ============================================================
# HTML GET
# ============================================================

def fetch_program_html(
    selected_date: Any,
    city: str,
    timeout: int = 30,
) -> str:

    url = build_program_url(
        selected_date,
        city,
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=timeout,
        allow_redirects=True,
    )

    if response.status_code != 200:

        raise requests.HTTPError(
            (
                f"TJK HTTP {response.status_code}. "
                f"URL: {response.url}"
            ),
            response=response,
        )

    response.encoding = (
        response.apparent_encoding
        or "utf-8"
    )

    html = response.text

    if not html:

        raise RuntimeError(
            "TJK boş HTML döndürdü."
        )

    return html


# ============================================================
# HTML TABLO SATIRLARINI ÇIKAR
# ============================================================

def extract_html_table_rows(
    table,
) -> List[List[str]]:

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

            value = normalize_text(
                cell.get_text(
                    " ",
                    strip=True,
                )
            )

            row.append(
                value
            )

        if any(row):

            rows.append(
                row
            )

    return rows


# ============================================================
# AT TABLOSU BAŞLIĞINI BUL
# ============================================================

def find_header_row(
    rows: List[List[str]],
) -> Optional[int]:

    for index, row in enumerate(
        rows
    ):

        headers = [
            normalize_header(
                value
            )
            for value in row
        ]

        has_horse = (
            "At İsmi" in headers
        )

        has_weight = (
            "Sıklet" in headers
        )

        has_jockey = (
            "Jokey" in headers
        )

        has_number = (
            "N" in headers
        )

        if (
            has_horse
            and (
                has_weight
                or has_jockey
                or has_number
            )
        ):

            return index

    return None


# ============================================================
# AT İSMİ KONTROL
# ============================================================

def looks_like_horse_name(
    value: Any,
) -> bool:

    text = normalize_text(
        value
    )

    if not text:
        return False

    lower = text.lower()

    invalid = {
        "at ismi",
        "at adı",
        "at adi",
        "koşu",
        "kosu",
        "forma",
        "jokey",
        "sıklet",
        "siklet",
        "toplam",
        "agf",
        "hp",
        "horse name",
    }

    if lower in invalid:
        return False

    if len(text) < 2:
        return False

    return True


# ============================================================
# TEK AT TABLOSU PARSE
# ============================================================

def parse_single_horse_table(
    table,
) -> List[Dict[str, Any]]:

    rows = extract_html_table_rows(
        table
    )

    if not rows:
        return []

    header_index = find_header_row(
        rows
    )

    if header_index is None:
        return []

    headers = [
        normalize_header(
            value
        )
        for value in rows[
            header_index
        ]
    ]

    # --------------------------------------------------------
    # AT İSMİ SÜTUNU
    # --------------------------------------------------------

    horse_index = None

    for index, header in enumerate(
        headers
    ):

        if header == "At İsmi":

            horse_index = index

            break

    if horse_index is None:
        return []

    # --------------------------------------------------------
    # ATLARI OKU
    # --------------------------------------------------------

    horses = []

    for row in rows[
        header_index + 1:
    ]:

        if not row:
            continue

        # Kolon sayısını eşitle
        if len(row) < len(headers):

            row = row + (
                [""] *
                (
                    len(headers)
                    - len(row)
                )
            )

        elif len(row) > len(headers):

            row = row[
                :len(headers)
            ]

        horse_name = normalize_text(
            row[horse_index]
        )

        if not looks_like_horse_name(
            horse_name
        ):
            continue

        # ----------------------------------------------------
        # Koşu başlığına denk gelirse geç
        # ----------------------------------------------------

        if re.match(
            r"^\d{1,2}\s*\.?\s*Koşu",
            horse_name,
            re.IGNORECASE,
        ):

            continue

        horse = {}

        # ----------------------------------------------------
        # Ham kolonları sakla
        # ----------------------------------------------------

        for index, header in enumerate(
            headers
        ):

            if not header:
                continue

            horse[
                header
            ] = normalize_text(
                row[index]
            )

        # ----------------------------------------------------
        # Standart alanlar
        # ----------------------------------------------------

        horse["at_ismi"] = (
            horse_name
        )

        horse["numara"] = (
            horse.get("N", "")
        )

        horse["yas"] = (
            horse.get("Yaş", "")
        )

        horse["siklet"] = (
            horse.get("Sıklet", "")
        )

        horse["jokey"] = (
            horse.get("Jokey", "")
        )

        horse["hp"] = (
            horse.get("HP", "")
        )

        horse["agf"] = (
            horse.get("AGF", "")
        )

        horse["st"] = (
            horse.get("St", "")
        )

        horse["form"] = (
            horse.get("Forma", "")
        )

        horse["kgs"] = (
            horse.get("KGS", "")
        )

        horse["gny"] = (
            horse.get("Gny", "")
        )

        horse["idm"] = (
            horse.get("İdm", "")
        )

        horses.append(
            horse
        )

    return horses


# ============================================================
# TÜM AT TABLOLARINI BUL
# ============================================================

def parse_horse_tables(
    html: str,
) -> List[List[Dict[str, Any]]]:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    horse_tables = []

    tables = soup.find_all(
        "table"
    )

    for table in tables:

        try:

            horses = (
                parse_single_horse_table(
                    table
                )
            )

            if horses:

                horse_tables.append(
                    horses
                )

        except Exception:

            continue

    return horse_tables


# ============================================================
# YARIŞ BAŞLIKLARINI BUL
# ============================================================

def parse_race_headings(
    html: str,
) -> List[Dict[str, Any]]:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    candidates = []

    # Önce başlık elementleri
    elements = soup.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
            "th",
        ]
    )

    seen = set()

    for element in elements:

        text = normalize_text(
            element.get_text(
                " ",
                strip=True,
            )
        )

        if not text:
            continue

        # ----------------------------------------------------
        # Örn:
        #
        # 1. Koşu 17.45
        # 2. Koşu 18.15
        # ----------------------------------------------------

        matches = re.finditer(
            r"(\d{1,2})\s*\.\s*Koşu"
            r"(?:\s+|[-—–]\s*)?"
            r"(\d{1,2})[:.](\d{2})",
            text,
            re.IGNORECASE,
        )

        found = False

        for match in matches:

            found = True

            number = int(
                match.group(1)
            )

            hour = int(
                match.group(2)
            )

            minute = int(
                match.group(3)
            )

            race_time = (
                f"{hour:02d}:"
                f"{minute:02d}"
            )

            key = (
                number,
                race_time,
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            candidates.append(
                {
                    "race_number": number,
                    "race_time": race_time,
                    "heading": text,
                }
            )

        # ----------------------------------------------------
        # Saat bulunamayan başlık
        # ----------------------------------------------------

        if not found:

            simple = re.search(
                r"(\d{1,2})\s*\.\s*Koşu",
                text,
                re.IGNORECASE,
            )

            if simple:

                number = int(
                    simple.group(1)
                )

                key = (
                    number,
                    "",
                )

                if key not in seen:

                    seen.add(
                        key
                    )

                    candidates.append(
                        {
                            "race_number": number,
                            "race_time": "",
                            "heading": text,
                        }
                    )

    # --------------------------------------------------------
    # Son çare: bütün görünür metin
    # --------------------------------------------------------

    if not candidates:

        text = normalize_text(
            soup.get_text(
                " ",
                strip=True,
            )
        )

        pattern = re.compile(
            r"(\d{1,2})\s*\.\s*Koşu"
            r"(?:\s+|[-—–]\s*)?"
            r"(\d{1,2})[:.](\d{2})?",
            re.IGNORECASE,
        )

        for match in pattern.finditer(
            text
        ):

            number = int(
                match.group(1)
            )

            hour = match.group(2)

            minute = match.group(3)

            if (
                hour
                and minute
            ):

                race_time = (
                    f"{int(hour):02d}:"
                    f"{int(minute):02d}"
                )

            else:

                race_time = ""

            candidates.append(
                {
                    "race_number": number,
                    "race_time": race_time,
                    "heading": (
                        match.group(0)
                    ),
                }
            )

    # --------------------------------------------------------
    # Sırala
    # --------------------------------------------------------

    candidates.sort(
        key=lambda item: (
            item["race_number"],
            item["race_time"],
        )
    )

    # --------------------------------------------------------
    # Aynı yarış numarasını tekilleştir
    # --------------------------------------------------------

    races = []

    used = set()

    for race in candidates:

        number = race[
            "race_number"
        ]

        if number in used:
            continue

        used.add(
            number
        )

        races.append(
            race
        )

    return races


# ============================================================
# YARIŞ DETAYLARINI BUL
# ============================================================

def extract_race_details(
    html: str,
    race_number: int,
) -> Dict[str, str]:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    result = {
        "race_time": "",
        "distance": "",
        "surface": "",
        "condition": "",
    }

    # --------------------------------------------------------
    # İLGİLİ KOŞU BAŞLIĞINI BUL
    # --------------------------------------------------------

    race_heading = None

    pattern = re.compile(
        rf"{race_number}\s*\.\s*Koşu",
        re.IGNORECASE,
    )

    for element in soup.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
            "th",
        ]
    ):

        text = normalize_text(
            element.get_text(
                " ",
                strip=True,
            )
        )

        if pattern.search(text):

            race_heading = text

            break

    # --------------------------------------------------------
    # SAAT
    # --------------------------------------------------------

    if race_heading:

        match = re.search(
            r"\b(\d{1,2})[:.](\d{2})\b",
            race_heading,
        )

        if match:

            result["race_time"] = (
                f"{int(match.group(1)):02d}:"
                f"{int(match.group(2)):02d}"
            )

    # --------------------------------------------------------
    # KOŞU BİLGİSİNE YAKIN METİN
    # --------------------------------------------------------

    search_text = ""

    if race_heading:

        # Başlığın kendisi
        search_text = race_heading

    # Genel metinden de destek al
    full_text = normalize_text(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    # --------------------------------------------------------
    # MESAFE
    # --------------------------------------------------------

    distance_patterns = [
        r"\b(\d{3,4})\s*m\b",
        r"\b(\d{3,4})\s*metre\b",
    ]

    for pattern_distance in (
        distance_patterns
    ):

        match = re.search(
            pattern_distance,
            search_text,
            re.IGNORECASE,
        )

        if match:

            result["distance"] = (
                f"{match.group(1)} m"
            )

            break

    # Eğer başlıkta yoksa genel metinde ara
    if not result["distance"]:

        for pattern_distance in (
            distance_patterns
        ):

            match = re.search(
                pattern_distance,
                full_text,
                re.IGNORECASE,
            )

            if match:

                result["distance"] = (
                    f"{match.group(1)} m"
                )

                break

    # --------------------------------------------------------
    # PİST
    # --------------------------------------------------------

    surface_candidates = [
        ("Sentetik", "Sentetik"),
        ("Kum", "Kum"),
        ("Çim", "Çim"),
        ("Fiber Kum", "Fiber Kum"),
        ("All Weather", "Sentetik"),
    ]

    for needle, value in (
        surface_candidates
    ):

        if re.search(
            rf"\b{re.escape(needle)}\b",
            search_text,
            re.IGNORECASE,
        ):

            result["surface"] = value

            break

    if not result["surface"]:

        for needle, value in (
            surface_candidates
        ):

            if re.search(
                rf"\b{re.escape(needle)}\b",
                full_text,
                re.IGNORECASE,
            ):

                result["surface"] = value

                break

    return result


# ============================================================
# ATLARI YARIŞLARA BAĞLA
# ============================================================

def attach_horses_to_races(
    races: List[Dict[str, Any]],
    horse_tables: List[
        List[Dict[str, Any]]
    ],
) -> List[Dict[str, Any]]:

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

    return races


# ============================================================
# ANA PARSER
# ============================================================

def parse_program(
    html: str,
    selected_date: Any = None,
    city: str = "",
) -> Dict[str, Any]:

    if not html:

        raise ValueError(
            "Parse edilecek HTML boş."
        )

    # --------------------------------------------------------
    # 1. KOŞULAR
    # --------------------------------------------------------

    races = parse_race_headings(
        html
    )

    # --------------------------------------------------------
    # 2. AT TABLOLARI
    # --------------------------------------------------------

    horse_tables = (
        parse_horse_tables(
            html
        )
    )

    # --------------------------------------------------------
    # 3. ATLARI KOŞULARA BAĞLA
    # --------------------------------------------------------

    races = attach_horses_to_races(
        races,
        horse_tables,
    )

    # --------------------------------------------------------
    # 4. DETAYLAR
    # --------------------------------------------------------

    for race in races:

        number = race.get(
            "race_number"
        )

        details = (
            extract_race_details(
                html,
                number,
            )
        )

        if not race.get(
            "race_time"
        ):

            race["race_time"] = (
                details.get(
                    "race_time",
                    "",
                )
            )

        race["distance"] = (
            details.get(
                "distance",
                "",
            )
        )

        race["surface"] = (
            details.get(
                "surface",
                "",
            )
        )

        race["condition"] = (
            details.get(
                "condition",
                "",
            )
        )

    # --------------------------------------------------------
    # 5. TOPLAM AT
    # --------------------------------------------------------

    total_horses = 0

    for race in races:

        total_horses += len(
            race.get(
                "horses",
                [],
            )
        )

    # --------------------------------------------------------
    # 6. GÖRÜNÜR METİN
    # --------------------------------------------------------

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    visible_text = normalize_text(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    # --------------------------------------------------------
    # 7. DEBUG
    # --------------------------------------------------------

    debug = {
        "html_length": len(
            html
        ),

        "visible_text_length": len(
            visible_text
        ),

        "html_table_count": len(
            soup.find_all(
                "table"
            )
        ),

        "race_count": len(
            races
        ),

        "horse_table_count": len(
            horse_tables
        ),

        "total_horse_count": (
            total_horses
        ),

        "horses_per_race": {
            str(
                race.get(
                    "race_number"
                )
            ): len(
                race.get(
                    "horses",
                    [],
                )
            )
            for race in races
        },

        "city": city,

        "date": (
            format_date(
                selected_date
            )
            if selected_date is not None
            else ""
        ),

        "contains_at_ismi": (
            "At İsmi" in html
            or "At Ismi" in html
        ),

        "contains_jokey": (
            "Jokey" in html
        ),

        "contains_siklet": (
            "Sıklet" in html
            or "Siklet" in html
        ),

        "url": (
            build_program_url(
                selected_date,
                city,
            )
            if city
            else ""
        ),
    }

    # --------------------------------------------------------
    # 8. SONUÇ
    # --------------------------------------------------------

    return {
        "ok": True,

        "source": (
            "TJK Günlük Yarış Programı"
        ),

        "date": (
            format_date(
                selected_date
            )
            if selected_date is not None
            else ""
        ),

        "city": city,

        "races": races,

        "race_count": len(
            races
        ),

        "total_horses": (
            total_horses
        ),

        "debug": debug,
    }


# ============================================================
# ANA DIŞ FONKSİYON
# ============================================================

def get_program(
    selected_date: Any,
    city: str,
) -> Dict[str, Any]:

    if city not in CITY_IDS:

        raise ValueError(
            f"Desteklenmeyen hipodrom: {city}"
        )

    html = fetch_program_html(
        selected_date,
        city,
    )

    return parse_program(
        html=html,
        selected_date=selected_date,
        city=city,
    )


# ============================================================
# DESTEKLENEN HİPODROMLAR
# ============================================================

def get_supported_cities() -> List[str]:

    return list(
        CITY_IDS.keys()
    )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    test_date = date.today()

    test_city = "Ankara"

    print(
        "================================"
    )

    print(
        "TJK TEST"
    )

    print(
        "================================"
    )

    print(
        "Tarih:",
        format_date(
            test_date
        )
    )

    print(
        "Hipodrom:",
        test_city
    )

    try:

        url = build_program_url(
            test_date,
            test_city,
        )

        print(
            "URL:",
            url
        )

        result = get_program(
            test_date,
            test_city,
        )

        print(
            "OK:",
            result.get(
                "ok"
            )
        )

        print(
            "Koşu:",
            result.get(
                "race_count"
            )
        )

        print(
            "Toplam at:",
            result.get(
                "total_horses"
            )
        )

        print(
            "Debug:"
        )

        print(
            result.get(
                "debug"
            )
        )

        for race in result.get(
            "races",
            [],
        ):

            print(
                f"{race.get('race_number')}. Koşu "
                f"{race.get('race_time')} "
                f"{race.get('distance')} "
                f"{race.get('surface')} "
                f"At: "
                f"{len(race.get('horses', []))}"
            )

    except Exception as exc:

        print(
            "HATA:",
            type(exc).__name__,
            str(exc)
        )
