import requests
from bs4 import BeautifulSoup
from datetime import date
from urllib.parse import quote


TJK_URL = "https://www.tjk.org/TR/YarisSever/Info/Page/GunlukYarisProgrami"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


class TJKFetchError(Exception):
    """TJK veri çekme hatası."""
    pass


def _format_date(value):
    """
    date / datetime / string değerini TJK formatına çevirir.
    Örnek:
        2026-09-12
        ->
        12/09/2026
    """

    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    value = str(value).strip()

    if "-" in value:
        try:
            y, m, d = value.split("-")
            return f"{d}/{m}/{y}"
        except Exception:
            pass

    return value


def build_program_url(race_date, city):
    """
    TJK günlük yarış programı URL'sini oluşturur.
    """

    formatted_date = _format_date(race_date)

    return (
        f"{TJK_URL}"
        f"?QueryParameter_Tarih={quote(formatted_date)}"
        f"&SehirAdi={quote(city)}"
    )


def fetch_program_page(race_date, city, timeout=30):
    """
    TJK program sayfasını indirir.
    """

    url = build_program_url(race_date, city)

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

    response.encoding = response.apparent_encoding or "utf-8"

    return response.text, url


def parse_program(html, city=None, race_date=None):
    """
    TJK günlük program HTML'ini temel yarış yapısına dönüştürür.
    """

    soup = BeautifulSoup(html, "html.parser")

    races = []

    # TJK sayfasındaki h3 başlıklarından
    # '1. Koşu 13.30' benzeri başlıkları yakala.
    headings = soup.find_all(["h2", "h3", "h4"])

    for heading in headings:

        text = " ".join(
            heading.get_text(" ", strip=True).split()
        )

        if "Koşu" not in text:
            continue

        # Örnek:
        # 1. Koşu 13.30
        race_number = None
        race_time = None

        parts = text.split()

        if len(parts) >= 3:

            try:
                race_number = int(parts[0].replace(".", ""))
            except Exception:
                race_number = None

            for part in parts:
                if ":" not in part:
                    continue

                if len(part) == 5:
                    race_time = part
                    break

        races.append({
            "race_number": race_number,
            "race_time": race_time,
            "title": text,
            "horses": []
        })

    # Aynı koşu başlıklarının tekrarlarını temizle
    unique = {}

    for race in races:

        key = (
            race["race_number"],
            race["race_time"],
            race["title"]
        )

        if key not in unique:
            unique[key] = race

    races = list(unique.values())

    races.sort(
        key=lambda x: (
            x["race_number"]
            if x["race_number"] is not None
            else 999
        )
    )

    return {
        "ok": True,
        "source": "TJK Günlük Yarış Programı",
        "date": _format_date(race_date) if race_date else None,
        "city": city,
        "url": None,
        "race_count": len(races),
        "races": races,
    }


def get_program(race_date, city):
    """
    Ana TJK program fonksiyonu.

    Streamlit'in kullanacağı ana giriş noktası budur.
    """

    html, url = fetch_program_page(
        race_date,
        city
    )

    data = parse_program(
        html,
        city=city,
        race_date=race_date
    )

    data["url"] = url

    return data
