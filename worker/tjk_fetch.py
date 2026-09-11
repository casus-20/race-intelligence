import requests
from datetime import date, datetime


TJK_URL = "https://www.tjk.org/TR/YarisSever/Info/Sehir/GunlukYarisProgrami"


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
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "tr-TR,tr;q=0.9"
}


class TJKFetchError(Exception):
    pass


def format_date(value):

    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")

    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    value = str(value).strip()

    if "-" in value:
        parts = value.split("-")

        if len(parts) == 3:
            return parts[2] + "/" + parts[1] + "/" + parts[0]

    return value


def build_program_url(race_date, city):

    if city not in CITY_IDS:
        raise TJKFetchError(
            "Bilinmeyen hipodrom: " + str(city)
        )

    params = {
        "Era": "today",
        "QueryParameter_Tarih": format_date(race_date),
        "SehirAdi": city,
        "SehirId": CITY_IDS[city]
    }

    response = requests.Request(
        "GET",
        TJK_URL,
        params=params
    ).prepare()

    return response.url


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
            "TJK bağlantı hatası: " + str(exc)
        )

    if response.status_code != 200:

        raise TJKFetchError(
            "TJK HTTP hatası: "
            + str(response.status_code)
        )

    return {
        "url": url,
        "status_code": response.status_code,
        "html": response.text
    }


def get_program(race_date, city):

    result = fetch_program_html(
        race_date,
        city
    )

    html = result["html"]

    return {
        "ok": True,
        "source": "TJK",
        "date": format_date(race_date),
        "city": city,
        "url": result["url"],
        "http_status": result["status_code"],
        "html_length": len(html)
    }
