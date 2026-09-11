import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup


# ============================================================
# TJK ŞEHİR ID'LERİ
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
# GÜNCEL TJK PROGRAM ADRESİ
# ============================================================

TJK_URL = (
    "https://www.tjk.org/"
    "TR/Yetistiricilik/Info/"
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
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": (
        "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
    ),
    "Referer": "https://www.tjk.org/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


# ============================================================
# METİN TEMİZLEME
# ============================================================

def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)

    text = text.replace("\xa0", " ")
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = text.replace("\t", " ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# BAŞLIK NORMALİZASYONU
# ============================================================

def normalize_header(value: Any) -> str:
    text = normalize_text(value).lower()

    replacements = {
        "ı": "i",
        "ş": "s",
        "ğ": "g",
        "ü": "u",
        "ö": "o",
        "ç": "c",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


# ============================================================
# TARİHİ DD/MM/YYYY FORMATINA ÇEVİR
# ============================================================

def format_date(value: Any) -> str:

    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")

    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    text = normalize_text(value)

    if not text:
        return date.today().strftime("%d/%m/%Y")

    # DD.MM.YYYY
    match = re.fullmatch(
        r"(\d{1,2})\.(\d{1,2})\.(\d{4})",
        text,
    )

    if match:
        day, month, year = match.groups()
        return f"{int(day):02d}/{int(month):02d}/{year}"

    # DD-MM-YYYY
    match = re.fullmatch(
        r"(\d{1,2})-(\d{1,2})-(\d{4})",
        text,
    )

    if match:
        day, month, year = match.groups()
        return f"{int(day):02d}/{int(month):02d}/{year}"

    # DD/MM/YYYY
    match = re.fullmatch(
        r"(\d{1,2})/(\d{1,2})/(\d{4})",
        text,
    )

    if match:
        day, month, year = match.groups()
        return f"{int(day):02d}/{int(month):02d}/{year}"

    # YYYY-MM-DD
    match = re.fullmatch(
        r"(\d{4})-(\d{1,2})-(\d{1,2})",
        text,
    )

    if match:
        year, month, day = match.groups()
        return f"{int(day):02d}/{int(month):02d}/{year}"

    return text


# ============================================================
# TJK PROGRAM URL'Sİ
# ============================================================

def build_program_url(
    city: str,
    tarih: Any,
) -> str:

    city = normalize_text(city)
    tarih = format_date(tarih)

    city_id = CITY_IDS.get(city)

    if city_id is None:
        raise ValueError(
            f"Desteklenmeyen hipodrom: {city}"
        )

    params = {
        "Era": "today",
        "QueryParameter_Tarih": tarih,
        "SehirAdi": city,
        "SehirId": city_id,
    }

    query = urlencode(
        params,
        encoding="utf-8",
    )

    return f"{TJK_URL}?{query}"


# ============================================================
# TJK'DAN HTML ÇEK
# ============================================================

def fetch_program_html(
    city: str,
    tarih: Any,
) -> Dict[str, Any]:

    url = build_program_url(
        city,
        tarih,
    )

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    try:

        response = session.get(
            url,
            timeout=30,
            allow_redirects=True,
        )

    except requests.RequestException as exc:

        raise RuntimeError(
            f"TJK bağlantı hatası: {exc}"
        ) from exc

    html = response.text or ""

    final_url = response.url

    content_type = response.headers.get(
        "content-type",
        "",
    )

    # --------------------------------------------------------
    # YÖNLENDİRME GEÇMİŞİ
    # --------------------------------------------------------

    history = []

    for item in response.history:

        history.append(
            {
                "status": item.status_code,
                "url": item.url,
                "location": item.headers.get(
                    "Location",
                    "",
                ),
            }
        )

    # --------------------------------------------------------
    # RESPONSE BAŞLANGICI
    # --------------------------------------------------------

    response_preview = normalize_text(
        html[:1500]
    )

    return {
        "html": html,
        "status_code": response.status_code,
        "url": url,
        "final_url": final_url,
        "content_type": content_type,
        "history": history,
        "response_preview": response_preview,
    }


# ============================================================
# HTML TABLO SATIRLARINI ÇIKAR
# ============================================================

def extract_html_table_rows(
    table,
) -> List[List[str]]:

    rows = []

    for tr in table.find_all("tr"):

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

            row.append(value)

        if any(row):
            rows.append(row)

    return rows


# ============================================================
# TABLO BAŞLIK SATIRINI BUL
# ============================================================

def find_header_row(
    rows: List[List[str]],
) -> Optional[int]:

    for index, row in enumerate(rows):

        normalized = [
            normalize_header(cell)
            for cell in row
        ]

        joined = " | ".join(
            normalized
        )

        has_horse = (
            "at ismi" in joined
            or "atismi" in joined
        )

        has_weight = (
            "siklet" in joined
            or "kilo" in joined
        )

        has_jockey = (
            "jokey" in joined
        )

        if has_horse and (
            has_weight
            or has_jockey
        ):
            return index

    return None


# ============================================================
# AT ADI KONTROLÜ
# ============================================================

def looks_like_horse_name(
    value: str,
) -> bool:

    text = normalize_text(value)

    if not text:
        return False

    normalized = normalize_header(
        text
    )

    invalid = {
        "at ismi",
        "atismi",
        "jokey",
        "siklet",
        "kilo",
        "hp",
        "agf",
        "kgs",
        "form",
    }

    if normalized in invalid:
        return False

    if re.match(
        r"^\d+\s*[\.\-]?\s*.+",
        text,
    ):
        return True

    if len(text) >= 3:
        return True

    return False


# ============================================================
# TEK AT TABLOSU
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

    headers = rows[
        header_index
    ]

    normalized_headers = [
        normalize_header(header)
        for header in headers
    ]

    horses = []

    for row in rows[
        header_index + 1:
    ]:

        if len(row) < 2:
            continue

        # ----------------------------------------------------
        # SATIR UZUNLUĞUNU BAŞLIĞA EŞİTLE
        # ----------------------------------------------------

        if len(row) < len(headers):

            row = row + [
                ""
            ] * (
                len(headers) - len(row)
            )

        elif len(row) > len(headers):

            row = row[
                :len(headers)
            ]

        # ----------------------------------------------------
        # SÖZLÜK OLUŞTUR
        # ----------------------------------------------------

        item = {}

        for index, header in enumerate(
            normalized_headers
        ):

            item[header] = (
                row[index]
                if index < len(row)
                else ""
            )

        # ----------------------------------------------------
        # NUMARA
        # ----------------------------------------------------

        number = ""

        for key in (
            "no",
            "n",
            "numara",
        ):

            if key in item:
                number = item[key]
                break

        # ----------------------------------------------------
        # AT ADI
        # ----------------------------------------------------

        horse_name = ""

        for key in (
            "at ismi",
            "atismi",
        ):

            if key in item:

                horse_name = item[
                    key
                ]

                break

        # ----------------------------------------------------
        # İLK SÜTUN NUMARA + İKİNCİ SÜTUN AT
        # ----------------------------------------------------

        if (
            not horse_name
            and len(row) >= 2
        ):

            if re.match(
                r"^\d+[\.\-]?$",
                row[0],
            ):

                number = row[0]
                horse_name = row[1]

        # ----------------------------------------------------
        # AT KONTROLÜ
        # ----------------------------------------------------

        if not looks_like_horse_name(
            horse_name
        ):
            continue

        # ----------------------------------------------------
        # AT ADI İÇİNDE NUMARA VARSA AYIR
        # ----------------------------------------------------

        match = re.match(
            r"^(\d+)\s*[\.\-]?\s*(.+)$",
            horse_name,
        )

        if match:

            if not number:
                number = match.group(1)

            horse_name = (
                match.group(2)
                .strip()
            )

        # ----------------------------------------------------
        # STANDART ALANLAR
        # ----------------------------------------------------

        item["no"] = normalize_text(
            number
        )

        item["at"] = normalize_text(
            horse_name
        )

        item["yas"] = (
            item.get("yas")
            or item.get("yaş")
            or ""
        )

        item["kilo"] = (
            item.get("siklet")
            or item.get("kilo")
            or ""
        )

        item["jokey"] = (
            item.get("jokey")
            or ""
        )

        item["hp"] = (
            item.get("hp")
            or ""
        )

        item["agf"] = (
            item.get("agf")
            or ""
        )

        item["st"] = (
            item.get("st")
            or ""
        )

        item["kgs"] = (
            item.get("kgs")
            or ""
        )

        item["form"] = (
            item.get("son 6 y.")
            or item.get("son 6 y")
            or item.get("form")
            or ""
        )

        item["raw"] = dict(
            item
        )

        horses.append(
            item
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

    for table in soup.find_all(
        "table"
    ):

        rows = extract_html_table_rows(
            table
        )

        if not rows:
            continue

        header_index = find_header_row(
            rows
        )

        if header_index is None:
            continue

        horses = parse_single_horse_table(
            table
        )

        if horses:
            horse_tables.append(
                horses
            )

    return horse_tables


# ============================================================
# KOŞU BAŞLIKLARINI BUL
# ============================================================

def parse_race_headings(
    html: str,
) -> List[Dict[str, str]]:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    headings = []

    seen = set()

    # --------------------------------------------------------
    # BAŞLIK ELEMANLARI
    # --------------------------------------------------------

    elements = soup.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "strong",
        ]
    )

    for element in elements:

        text = normalize_text(
            element.get_text(
                " ",
                strip=True,
            )
        )

        if not text:
            continue

        match = re.search(
            r"(\d+)\.\s*Koşu"
            r"(?:\s+(\d{1,2}[.:]\d{2}))?",
            text,
            re.IGNORECASE,
        )

        if not match:
            continue

        number = match.group(1)
        time = match.group(2) or ""

        key = (
            number,
            time,
        )

        if key in seen:
            continue

        seen.add(key)

        headings.append(
            {
                "no": number,
                "time": time,
                "title": text,
            }
        )

    # --------------------------------------------------------
    # BAŞLIKLARDA BULUNAMADIYSA TÜM METİN
    # --------------------------------------------------------

    if not headings:

        text = soup.get_text(
            "\n",
            strip=True,
        )

        pattern = re.compile(
            r"(\d+)\.\s*Koşu"
            r"(?:\s+(\d{1,2}[.:]\d{2}))?",
            re.IGNORECASE,
        )

        for match in pattern.finditer(
            text
        ):

            number = match.group(1)
            time = match.group(2) or ""

            key = (
                number,
                time,
            )

            if key in seen:
                continue

            seen.add(key)

            headings.append(
                {
                    "no": number,
                    "time": time,
                    "title": match.group(0),
                }
            )

    return headings


# ============================================================
# KOŞU DETAYLARI
# ============================================================

def extract_race_details(
    html: str,
    race_index: int,
    heading: Optional[
        Dict[str, str]
    ] = None,
) -> Dict[str, str]:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    result = {
        "time": "",
        "distance": "",
        "surface": "",
        "condition": "",
    }

    if heading:

        result["time"] = heading.get(
            "time",
            "",
        )

    race_number = race_index + 1

    race_pattern = re.compile(
        rf"{race_number}\.\s*Koşu",
        re.IGNORECASE,
    )

    node = None

    for element in soup.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "strong",
        ]
    ):

        text = normalize_text(
            element.get_text(
                " ",
                strip=True,
            )
        )

        if race_pattern.search(
            text
        ):

            node = element
            break

    if node:

        texts = []

        for sibling in node.find_all_next(
            limit=15
        ):

            text = normalize_text(
                sibling.get_text(
                    " ",
                    strip=True,
                )
            )

            if text:
                texts.append(text)

        joined = " ".join(
            texts
        )

    else:

        joined = soup.get_text(
            " ",
            strip=True,
        )

    # --------------------------------------------------------
    # MESAFE
    # --------------------------------------------------------

    distance_match = re.search(
        r"\b(\d{3,4})\s*(m|metre)\b",
        joined,
        re.IGNORECASE,
    )

    if distance_match:

        result["distance"] = (
            distance_match.group(1)
        )

    # --------------------------------------------------------
    # PİST
    # --------------------------------------------------------

    surface_match = re.search(
        r"\b(Kum|Çim|Sentetik|Suni)\b",
        joined,
        re.IGNORECASE,
    )

    if surface_match:

        result["surface"] = (
            surface_match.group(1)
        )

    # --------------------------------------------------------
    # KOŞU ŞARTI
    # --------------------------------------------------------

    condition_patterns = [
        r"(Maiden)",
        r"(Handikap\s*\d+)",
        r"(Şartlı\s*\d+)",
        r"(KV[-\s]?\d+)",
        r"(Satış\s*\d+)",
        r"(Gazi Koşusu)",
    ]

    for pattern in condition_patterns:

        match = re.search(
            pattern,
            joined,
            re.IGNORECASE,
        )

        if match:

            result["condition"] = (
                normalize_text(
                    match.group(1)
                )
            )

            break

    return result


# ============================================================
# ATLARI KOŞULARA BAĞLA
# ============================================================

def attach_horses_to_races(
    races: List[
        Dict[str, Any]
    ],
    horse_tables: List[
        List[Dict[str, Any]]
    ],
) -> List[
    Dict[str, Any]
]:

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
    city: str,
    tarih: str,
    metadata: Optional[
        Dict[str, Any]
    ] = None,
) -> Dict[str, Any]:

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
    # AT TABLOLARI
    # --------------------------------------------------------

    horse_tables = parse_horse_tables(
        html
    )

    # --------------------------------------------------------
    # KOŞU BAŞLIKLARI
    # --------------------------------------------------------

    headings = parse_race_headings(
        html
    )

    # --------------------------------------------------------
    # KOŞU SAYISI
    # --------------------------------------------------------

    race_count = max(
        len(headings),
        len(horse_tables),
    )

    races = []

    for index in range(
        race_count
    ):

        heading = (
            headings[index]
            if index < len(headings)
            else {}
        )

        details = extract_race_details(
            html,
            index,
            heading,
        )

        race = {
            "race_no": index + 1,
            "no": index + 1,
            "time": details.get(
                "time",
                "",
            ),
            "distance": details.get(
                "distance",
                "",
            ),
            "surface": details.get(
                "surface",
                "",
            ),
            "condition": details.get(
                "condition",
                "",
            ),
            "title": heading.get(
                "title",
                "",
            ),
            "horses": [],
        }

        races.append(
            race
        )

    # --------------------------------------------------------
    # ATLARI KOŞULARA BAĞLA
    # --------------------------------------------------------

    races = attach_horses_to_races(
        races,
        horse_tables,
    )

    # --------------------------------------------------------
    # TOPLAM AT
    # --------------------------------------------------------

    total_horses = sum(
        len(
            race.get(
                "horses",
                [],
            )
        )
        for race in races
    )

    horses_per_race = {}

    for race in races:

        horses_per_race[
            str(
                race["race_no"]
            )
        ] = len(
            race.get(
                "horses",
                [],
            )
        )

    # --------------------------------------------------------
    # DEBUG
    # --------------------------------------------------------

    normalized_html = normalize_header(
        html
    )

    debug = {
        "html_length": len(html),
        "visible_text_length": len(
            visible_text
        ),
        "html_table_count": len(
            soup.find_all("table")
        ),
        "race_count": len(races),
        "horse_table_count": len(
            horse_tables
        ),
        "total_horse_count": total_horses,
        "horses_per_race": horses_per_race,
        "city": city,
        "date": tarih,
        "contains_at_ismi": (
            "at ismi"
            in normalized_html
        ),
        "contains_jokey": (
            "jokey"
            in normalized_html
        ),
        "contains_siklet": (
            "siklet"
            in normalized_html
        ),
    }

    # --------------------------------------------------------
    # HTTP DEBUG
    # --------------------------------------------------------

    if metadata:

        debug.update(
            {
                "status_code": metadata.get(
                    "status_code"
                ),
                "requested_url": metadata.get(
                    "url"
                ),
                "final_url": metadata.get(
                    "final_url"
                ),
                "content_type": metadata.get(
                    "content_type"
                ),
                "redirect_history": metadata.get(
                    "history"
                ),
                "response_preview": metadata.get(
                    "response_preview"
                ),
            }
        )

    return {
        "ok": True,
        "source": "TJK Günlük Yarış Programı",
        "date": tarih,
        "city": city,
        "races": races,
        "race_count": len(races),
        "total_horses": total_horses,
        "debug": debug,
    }


# ============================================================
# ANA PROGRAM FONKSİYONU
# ============================================================

def get_program(
    city: str,
    tarih: Any,
) -> Dict[str, Any]:

    city = normalize_text(
        city
    )

    tarih = format_date(
        tarih
    )

    metadata = fetch_program_html(
        city,
        tarih,
    )

    html = metadata.get(
        "html",
        "",
    )

    # --------------------------------------------------------
    # HTTP HATA KONTROLÜ
    # --------------------------------------------------------

    if metadata.get(
        "status_code"
    ) != 200:

        return {
            "ok": False,
            "source": (
                "TJK Günlük Yarış Programı"
            ),
            "date": tarih,
            "city": city,
            "races": [],
            "race_count": 0,
            "total_horses": 0,
            "error": (
                "TJK HTTP "
                f"{metadata.get('status_code')}"
            ),
            "debug": {
                "status_code": metadata.get(
                    "status_code"
                ),
                "requested_url": metadata.get(
                    "url"
                ),
                "final_url": metadata.get(
                    "final_url"
                ),
                "content_type": metadata.get(
                    "content_type"
                ),
                "redirect_history": metadata.get(
                    "history"
                ),
                "html_length": len(
                    html
                ),
                "response_preview": metadata.get(
                    "response_preview"
                ),
            },
        }

    # --------------------------------------------------------
    # PARSE
    # --------------------------------------------------------

    result = parse_program(
        html,
        city,
        tarih,
        metadata,
    )

    # --------------------------------------------------------
    # KISA / BOŞ CEVAP KONTROLÜ
    # --------------------------------------------------------

    if len(
        html.strip()
    ) < 5000:

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

        result["debug"][
            "warning"
        ] = (
            "TJK yanıtı beklenenden kısa. "
            "Program sayfası yerine boş, "
            "hata veya doğrulama sayfası "
            "dönmüş olabilir."
        )

        result["debug"][
            "response_preview"
        ] = normalize_text(
            html[:1500]
        )

        result["debug"][
            "visible_preview"
        ] = visible_text[:1500]

    return result


# ============================================================
# DESTEKLENEN HİPODROMLAR
# ============================================================

def get_supported_cities() -> List[str]:

    return list(
        CITY_IDS.keys()
    )
