import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

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


TJK_URL = (
    "https://www.tjk.org/TR/YarisSever/Info/"
    "Sehir/GunlukYarisProgrami"
)


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
}


# ============================================================
# GENEL YARDIMCI FONKSİYONLAR
# ============================================================

def normalize_text(value: Any) -> str:
    """
    HTML içindeki metni normalize eder.
    """
    if value is None:
        return ""

    text = str(value)

    text = (
        text.replace("\xa0", " ")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("\t", " ")
    )

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_header(value: Any) -> str:
    """
    Tablo başlıklarını karşılaştırma için normalize eder.
    """
    text = normalize_text(value)

    replacements = {
        "At İsmi": "At İsmi",
        "At Ismi": "At İsmi",
        "AT İSMİ": "At İsmi",
        "At Adı": "At İsmi",
        "At Adi": "At İsmi",
        "Sıklet": "Sıklet",
        "Siklet": "Sıklet",
        "Jokey": "Jokey",
        "HP": "HP",
        "AGF": "AGF",
        "St": "St",
        "Yaş": "Yaş",
        "Yas": "Yaş",
        "KGS": "KGS",
        "Forma": "Forma",
        "Form": "Forma",
        "N": "N",
        "Gny": "Gny",
        "İdm": "İdm",
        "Idm": "İdm",
        "S20": "s20",
        "s20": "s20",
        "Son 6 Y.": "Son 6 Y.",
        "Son 6 Y": "Son 6 Y.",
        "En İyi D.": "En İyi D.",
        "En Iyi D.": "En İyi D.",
        "Orijin(Baba - Anne)": "Orijin(Baba - Anne)",
        "Orijin (Baba - Anne)": "Orijin(Baba - Anne)",
        "Sahip": "Sahip",
        "Antrenör": "Antrenör",
    }

    return replacements.get(text, text)


def clean_number(value: Any) -> str:
    """
    Numara gibi alanları temizler.
    """
    text = normalize_text(value)

    if not text:
        return ""

    match = re.search(r"\d{1,2}", text)

    if match:
        return match.group(0)

    return text


def format_date(selected_date: Any) -> str:
    """
    Tarihi TJK'nın beklediği DD.MM.YYYY formatına çevirir.
    """

    if isinstance(selected_date, datetime):
        selected_date = selected_date.date()

    if isinstance(selected_date, date):
        return selected_date.strftime("%d.%m.%Y")

    text = normalize_text(selected_date)

    if not text:
        return date.today().strftime("%d.%m.%Y")

    # YYYY-MM-DD
    match = re.fullmatch(
        r"(\d{4})-(\d{1,2})-(\d{1,2})",
        text
    )

    if match:
        year, month, day = match.groups()

        return (
            f"{int(day):02d}."
            f"{int(month):02d}."
            f"{int(year):04d}"
        )

    # DD.MM.YYYY
    match = re.fullmatch(
        r"(\d{1,2})\.(\d{1,2})\.(\d{4})",
        text
    )

    if match:
        day, month, year = match.groups()

        return (
            f"{int(day):02d}."
            f"{int(month):02d}."
            f"{int(year):04d}"
        )

    return text


# ============================================================
# TJK URL
# ============================================================

def build_program_url(
    selected_date: Any,
    city: str
) -> str:
    """
    TJK günlük yarış programı URL'sini oluşturur.
    """

    city_id = CITY_IDS.get(city)

    if city_id is None:
        raise ValueError(
            f"Geçersiz hipodrom: {city}"
        )

    tarih = format_date(selected_date)

    params = {
        "QueryParameter_Tarih": tarih,
        "SehirAdi": city,
        "SehirId": city_id,
    }

    from urllib.parse import urlencode

    return f"{TJK_URL}?{urlencode(params)}"


# ============================================================
# HTML GET
# ============================================================

def fetch_program_html(
    selected_date: Any,
    city: str,
    timeout: int = 30
) -> str:
    """
    TJK günlük program HTML'ini getirir.
    """

    url = build_program_url(
        selected_date,
        city
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=timeout
    )

    response.raise_for_status()

    response.encoding = response.apparent_encoding or "utf-8"

    html = response.text

    if not html:
        raise RuntimeError(
            "TJK boş HTML döndürdü."
        )

    return html


# ============================================================
# TABLO SATIRLARINI ÇIKAR
# ============================================================

def extract_html_table_rows(table) -> List[List[str]]:
    """
    Bir HTML tablosundaki bütün satırları çıkarır.
    """

    rows = []

    for tr in table.find_all("tr"):
        cells = tr.find_all(
            ["th", "td"]
        )

        if not cells:
            continue

        row = []

        for cell in cells:
            text = normalize_text(
                cell.get_text(
                    " ",
                    strip=True
                )
            )

            row.append(text)

        if any(row):
            rows.append(row)

    return rows


# ============================================================
# BAŞLIK SATIRI BUL
# ============================================================

def find_header_row(
    rows: List[List[str]]
) -> Optional[int]:
    """
    At tablosunun başlık satırını bulur.

    Temel kontrol:
    At İsmi + Sıklet
    veya
    At İsmi + Jokey
    """

    for index, row in enumerate(rows):

        normalized = [
            normalize_header(x)
            for x in row
        ]

        joined = " | ".join(normalized)

        has_horse = (
            "At İsmi" in normalized
            or "At İsmi" in joined
        )

        has_weight = (
            "Sıklet" in normalized
            or "Sıklet" in joined
        )

        has_jockey = (
            "Jokey" in normalized
            or "Jokey" in joined
        )

        if has_horse and (
            has_weight or has_jockey
        ):
            return index

    return None


# ============================================================
# AT SATIRI OLUP OLMADIĞINI KONTROL
# ============================================================

def looks_like_horse_name(
    value: Any
) -> bool:
    """
    Hücrenin at ismi olma ihtimalini kontrol eder.
    """

    text = normalize_text(value)

    if not text:
        return False

    lower = text.lower()

    invalid_values = {
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
    }

    if lower in invalid_values:
        return False

    # Çok kısa tek karakterli hücreler genellikle başlıktır.
    if len(text) < 2:
        return False

    return True


# ============================================================
# TEK AT TABLOSU PARSE
# ============================================================

def parse_single_horse_table(
    table
) -> List[Dict[str, Any]]:
    """
    Tek bir HTML tablosundan atları çıkarır.
    """

    rows = extract_html_table_rows(table)

    if not rows:
        return []

    header_index = find_header_row(rows)

    if header_index is None:
        return []

    raw_headers = rows[header_index]

    headers = [
        normalize_header(x)
        for x in raw_headers
    ]

    # At İsmi sütununu bul
    horse_index = None

    for i, header in enumerate(headers):

        if header == "At İsmi":
            horse_index = i
            break

    if horse_index is None:
        return []

    horses = []

    for row in rows[
        header_index + 1:
    ]:

        if not row:
            continue

        # Satırı kolon sayısına eşitle
        if len(row) < len(headers):
            row = row + (
                [""] *
                (len(headers) - len(row))
            )

        elif len(row) > len(headers):
            row = row[:len(headers)]

        horse_name = normalize_text(
            row[horse_index]
        )

        if not looks_like_horse_name(
            horse_name
        ):
            continue

        # "Koşu" başlıklarına denk gelirse atlama
        if re.match(
            r"^\d{1,2}\s*\.?\s*Koşu",
            horse_name,
            re.IGNORECASE
        ):
            continue

        horse = {}

        for index, header in enumerate(headers):

            value = normalize_text(
                row[index]
            )

            if header:
                horse[header] = value

        # ----------------------------------------------------
        # Standart alanlar
        # ----------------------------------------------------

        horse["at_ismi"] = horse_name

        if "N" in horse:
            horse["numara"] = clean_number(
                horse["N"]
            )
        else:
            horse["numara"] = ""

        if "Yaş" in horse:
            horse["yas"] = horse["Yaş"]
        else:
            horse["yas"] = ""

        if "Sıklet" in horse:
            horse["siklet"] = horse["Sıklet"]
        else:
            horse["siklet"] = ""

        if "Jokey" in horse:
            horse["jokey"] = horse["Jokey"]
        else:
            horse["jokey"] = ""

        if "HP" in horse:
            horse["hp"] = horse["HP"]
        else:
            horse["hp"] = ""

        if "AGF" in horse:
            horse["agf"] = horse["AGF"]
        else:
            horse["agf"] = ""

        if "St" in horse:
            horse["st"] = horse["St"]
        else:
            horse["st"] = ""

        if "Forma" in horse:
            horse["form"] = horse["Forma"]
        else:
            horse["form"] = ""

        if "KGS" in horse:
            horse["kgs"] = horse["KGS"]
        else:
            horse["kgs"] = ""

        if "Gny" in horse:
            horse["gny"] = horse["Gny"]
        else:
            horse["gny"] = ""

        if "İdm" in horse:
            horse["idm"] = horse["İdm"]
        else:
            horse["idm"] = ""

        horses.append(horse)

    return horses


# ============================================================
# BÜTÜN AT TABLOLARINI BUL
# ============================================================

def parse_horse_tables(
    html: str
) -> List[List[Dict[str, Any]]]:
    """
    HTML içindeki bütün tabloları kontrol eder.
    At tablosu olanları bulur.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    horse_tables = []

    tables = soup.find_all("table")

    for table in tables:

        try:
            horses = parse_single_horse_table(
                table
            )

            if horses:
                horse_tables.append(
                    horses
                )

        except Exception:
            # Tek bir bozuk tablo diğerlerini
            # engellemesin.
            continue

    return horse_tables


# ============================================================
# YARIŞ BAŞLIKLARINI BUL
# ============================================================

def parse_race_headings(
    html: str
) -> List[Dict[str, Any]]:
    """
    HTML içerisindeki:

    1. Koşu 17.45
    2. Koşu 18.15

    gibi başlıkları bulur.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    candidates = []

    # Önce başlık elementleri
    elements = soup.find_all(
        ["h1", "h2", "h3", "h4", "th"]
    )

    # Sonra gerektiğinde bütün metin
    if not elements:
        elements = soup.find_all()

    seen = set()

    for element in elements:

        text = normalize_text(
            element.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        # Örnek:
        # 1. Koşu 17.45
        # 1.Koşu 17:45
        # 1. Koşu
        matches = re.finditer(
            r"(\d{1,2})\s*\.\s*Koşu"
            r"(?:\s+|-|—|–)*"
            r"(\d{1,2})[:.](\d{2})?",
            text,
            re.IGNORECASE
        )

        found_any = False

        for match in matches:

            found_any = True

            race_number = int(
                match.group(1)
            )

            hour = match.group(2)

            minute = match.group(3)

            if minute is not None:
                race_time = (
                    f"{int(hour):02d}:"
                    f"{int(minute):02d}"
                )
            else:
                race_time = ""

            key = (
                race_number,
                race_time
            )

            if key in seen:
                continue

            seen.add(key)

            candidates.append(
                {
                    "race_number": race_number,
                    "race_time": race_time,
                    "heading": text,
                }
            )

        # Saat bulunamayan:
        # "1. Koşu"
        if not found_any:

            simple_match = re.search(
                r"(\d{1,2})\s*\.\s*Koşu",
                text,
                re.IGNORECASE
            )

            if simple_match:

                race_number = int(
                    simple_match.group(1)
                )

                key = (
                    race_number,
                    ""
                )

                if key not in seen:

                    seen.add(key)

                    candidates.append(
                        {
                            "race_number": race_number,
                            "race_time": "",
                            "heading": text,
                        }
                    )

    # Yarış numarasına göre sırala
    candidates.sort(
        key=lambda x: x["race_number"]
    )

    # Aynı yarış numarasını tekilleştir
    races = []

    used_numbers = set()

    for race in candidates:

        number = race[
            "race_number"
        ]

        if number in used_numbers:
            continue

        used_numbers.add(number)

        races.append(race)

    return races


# ============================================================
# YARIŞ DETAYLARI
# ============================================================

def extract_race_details(
    html: str,
    race_number: int
) -> Dict[str, str]:
    """
    Yarışın saat, mesafe, pist ve şart bilgilerini
    mümkün olduğunca HTML'den çıkarır.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    result = {
        "race_time": "",
        "distance": "",
        "surface": "",
        "condition": "",
    }

    # --------------------------------------------------------
    # Yarış başlığını bul
    # --------------------------------------------------------

    race_pattern = re.compile(
        rf"{race_number}\s*\.\s*Koşu",
        re.IGNORECASE
    )

    heading_element = None

    for element in soup.find_all(
        ["h1", "h2", "h3", "h4", "th", "td", "div"]
    ):

        text = normalize_text(
            element.get_text(
                " ",
                strip=True
            )
        )

        if race_pattern.search(text):

            heading_element = element

            # Çok büyük kapsayıcıları tercih etme
            if len(text) < 500:
                break

    if heading_element is not None:

        heading_text = normalize_text(
            heading_element.get_text(
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

            result["race_time"] = (
                f"{int(time_match.group(1)):02d}:"
                f"{int(time_match.group(2)):02d}"
            )

    # --------------------------------------------------------
    # Yarış çevresindeki metni ara
    # --------------------------------------------------------

    text = normalize_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    # Saat bulunamadıysa genel HTML'den dene
    if not result["race_time"]:

        pattern = re.compile(
            rf"{race_number}\s*\.\s*Koşu"
            rf".{{0,150}}?"
            rf"(\d{{1,2}})[:.](\d{{2}})",
            re.IGNORECASE
        )

        match = pattern.search(
            text
        )

        if match:

            result["race_time"] = (
                f"{int(match.group(1)):02d}:"
                f"{int(match.group(2)):02d}"
            )

    # --------------------------------------------------------
    # Mesafe
    # --------------------------------------------------------

    distance_patterns = [
        r"\b(\d{3,4})\s*m\b",
        r"\b(\d{3,4})\s*metre\b",
    ]

    for pattern in distance_patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            result["distance"] = (
                f"{match.group(1)} m"
            )

            break

    # --------------------------------------------------------
    # Pist
    # --------------------------------------------------------

    surface_patterns = [
        (r"\bKum\b", "Kum"),
        (r"\bÇim\b", "Çim"),
        (r"\bSentetik\b", "Sentetik"),
    ]

    for pattern, surface in surface_patterns:

        if re.search(
            pattern,
            text,
            re.IGNORECASE
        ):

            result["surface"] = surface

            break

    return result


# ============================================================
# YARIŞLARI AT TABLOLARIYLA EŞLEŞTİR
# ============================================================

def attach_horses_to_races(
    races: List[Dict[str, Any]],
    horse_tables: List[List[Dict[str, Any]]]
) -> List[Dict[str, Any]]:
    """
    At tablolarını yarışlara sırayla bağlar.

    ÖNEMLİ:
    horse_tables burada mutlaka parametre olarak gelir.
    Böylece 'horse_tables is not defined' hatası oluşmaz.
    """

    for index, race in enumerate(races):

        if index < len(horse_tables):

            race["horses"] = (
                horse_tables[index]
            )

        else:

            race["horses"] = []

    return races


# ============================================================
# ANA PROGRAM PARSE
# ============================================================

def parse_program(
    html: str,
    selected_date: Any = None,
    city: str = ""
) -> Dict[str, Any]:
    """
    TJK HTML'ini komple parse eder.
    """

    if not html:
        raise ValueError(
            "Parse edilecek HTML boş."
        )

    # --------------------------------------------------------
    # 1. Yarışları bul
    # --------------------------------------------------------

    races = parse_race_headings(
        html
    )

    # --------------------------------------------------------
    # 2. AT TABLOLARINI MUTLAKA BURADA TANIMLA
    # --------------------------------------------------------

    horse_tables = parse_horse_tables(
        html
    )

    # --------------------------------------------------------
    # 3. Yarışlara atları bağla
    # --------------------------------------------------------

    races = attach_horses_to_races(
        races,
        horse_tables
    )

    # --------------------------------------------------------
    # 4. Yarış detaylarını doldur
    # --------------------------------------------------------

    for race in races:

        race_number = race.get(
            "race_number"
        )

        details = extract_race_details(
            html,
            race_number
        )

        # Başlıkta bulunan saat öncelikli
        if not race.get(
            "race_time"
        ):

            race["race_time"] = (
                details.get(
                    "race_time",
                    ""
                )
            )

        race["distance"] = (
            details.get(
                "distance",
                ""
            )
        )

        race["surface"] = (
            details.get(
                "surface",
                ""
            )
        )

        race["condition"] = (
            details.get(
                "condition",
                ""
            )
        )

    # --------------------------------------------------------
    # 5. Toplam at
    # --------------------------------------------------------

    total_horses = sum(
        len(
            race.get(
                "horses",
                []
            )
        )
        for race in races
    )

    # --------------------------------------------------------
    # 6. Debug bilgisi
    # --------------------------------------------------------

    debug = {
        "html_length": len(html),

        "visible_text_length": len(
            BeautifulSoup(
                html,
                "html.parser"
            ).get_text(
                " ",
                strip=True
            )
        ),

        "race_count": len(races),

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
                    []
                )
            )
            for race in races
        },

        "city": city,

        "date": format_date(
            selected_date
        )
        if selected_date is not None
        else "",

        "html_contains_at_ismi": (
            "At İsmi" in html
            or "At Ismi" in html
        ),

        "html_contains_jokey": (
            "Jokey" in html
        ),

        "html_contains_siklet": (
            "Sıklet" in html
            or "Siklet" in html
        ),
    }

    # --------------------------------------------------------
    # 7. Sonuç
    # --------------------------------------------------------

    return {
        "ok": True,
        "source": "TJK Günlük Yarış Programı",
        "date": format_date(
            selected_date
        )
        if selected_date is not None
        else "",
        "city": city,
        "races": races,
        "race_count": len(races),
        "total_horses": total_horses,
        "debug": debug,
    }


# ============================================================
# DIŞARIDAN ÇAĞRILAN ANA FONKSİYON
# ============================================================

def get_program(
    selected_date: Any,
    city: str
) -> Dict[str, Any]:
    """
    Uygulamanın kullanacağı ana fonksiyon.

    Akış:

    get_program()
        ↓
    fetch_program_html()
        ↓
    parse_program()
        ↓
    races + horses + debug
    """

    if city not in CITY_IDS:
        raise ValueError(
            f"Desteklenmeyen hipodrom: {city}"
        )

    html = fetch_program_html(
        selected_date,
        city
    )

    result = parse_program(
        html=html,
        selected_date=selected_date,
        city=city
    )

    return result


# ============================================================
# TEST AMAÇLI FONKSİYON
# ============================================================

def get_supported_cities() -> List[str]:
    """
    Desteklenen hipodromları döndürür.
    """

    return list(
        CITY_IDS.keys()
    )


# ============================================================
# DOĞRUDAN ÇALIŞTIRMA TESTİ
# ============================================================

if __name__ == "__main__":

    today = date.today()

    print(
        "TJK test başlıyor..."
    )

    print(
        "Tarih:",
        format_date(today)
    )

    print(
        "Hipodromlar:",
        ", ".join(
            get_supported_cities()
        )
    )

    try:

        test_city = "Bursa"

        print(
            f"{test_city} programı alınıyor..."
        )

        result = get_program(
            today,
            test_city
        )

        print(
            "OK:",
            result.get("ok")
        )

        print(
            "Koşu sayısı:",
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
            []
        ):

            print(
                f"{race.get('race_number')}. Koşu "
                f"{race.get('race_time')} "
                f"- "
                f"{len(race.get('horses', []))} at"
            )

    except Exception as exc:

        print(
            "HATA:",
            type(exc).__name__,
            str(exc)
        )
