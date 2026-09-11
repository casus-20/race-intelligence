import requests
from datetime import date, datetime
from typing import Any, Dict, List


# =========================================================
# RACE INTELLIGENCE
# TJK VERİ KAYNAĞI
# =========================================================

WORKER_URL = "https://fragrant-hat-ae48.raceanaliz.workers.dev"

API_DATA = f"{WORKER_URL}/api/tjk/data"
API_HEALTH = f"{WORKER_URL}/api/health"


# =========================================================
# ŞEHİR LİSTESİ
# =========================================================

CITY_IDS = {
    "Ankara": 5,
    "Kocaeli": 9,
    "İstanbul": 3,
    "Bursa": 4,
    "İzmir": 1,
    "Adana": 2,
    "Elazığ": 7,
    "Diyarbakır": 6,
    "Şanlıurfa": 8,
    "Antalya": 10,
}


# =========================================================
# YARDIMCI FONKSİYONLAR
# =========================================================

def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(str(value).replace("\xa0", " ").split()).strip()


def normalize_date(value: Any) -> str:
    """
    Streamlit date_input:
        datetime.date
        veya YYYY-MM-DD

    Worker API:
        YYYY-MM-DD
    """

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    text = normalize_text(value)

    if not text:
        return date.today().isoformat()

    # YYYY-MM-DD
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text

    # DD/MM/YYYY
    if len(text) == 10 and text[2] == "/" and text[5] == "/":
        dd = text[0:2]
        mm = text[3:5]
        yyyy = text[6:10]
        return f"{yyyy}-{mm}-{dd}"

    # DD.MM.YYYY
    if len(text) == 10 and text[2] == "." and text[5] == ".":
        dd = text[0:2]
        mm = text[3:5]
        yyyy = text[6:10]
        return f"{yyyy}-{mm}-{dd}"

    return text


def format_date_tr(value: Any) -> str:
    iso = normalize_date(value)

    try:
        y, m, d = iso.split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return iso


# =========================================================
# WORKER BAĞLANTISI
# =========================================================

def fetch_worker(
    date_value: Any,
    city: str,
    timeout: int = 45,
) -> Dict[str, Any]:

    iso_date = normalize_date(date_value)
    city = normalize_text(city)

    if not city:
        raise ValueError("Hipodrom belirtilmedi.")

    if city not in CITY_IDS:
        raise ValueError(
            f"Bilinmeyen hipodrom: {city}. "
            f"Desteklenenler: {', '.join(CITY_IDS.keys())}"
        )

    params = {
        "date": iso_date,
        "city": city,
    }

    try:
        response = requests.get(
            API_DATA,
            params=params,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Race-Intelligence-Streamlit/34 "
                    "(TJK Gateway Client)"
                ),
                "Accept": "application/json,text/plain,*/*",
                "Cache-Control": "no-cache",
            },
        )
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Race Intelligence Worker bağlantısı başarısız: {exc}"
        ) from exc

    response_text = response.text or ""

    if response.status_code != 200:
        raise RuntimeError(
            f"Worker HTTP {response.status_code}: "
            f"{response_text[:500]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "Worker geçerli JSON döndürmedi. "
            f"İlk cevap: {response_text[:500]}"
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            "Worker cevabı beklenen JSON nesnesi değil."
        )

    if not data.get("ok", False):
        error = normalize_text(
            data.get("error")
            or data.get("message")
            or "Worker veri alamadı."
        )

        raise RuntimeError(
            f"TJK Worker hatası: {error}"
        )

    return data


# =========================================================
# ANA PROGRAM ÇEKME
# =========================================================

def get_program(
    date_value: Any,
    city: str,
) -> Dict[str, Any]:

    iso_date = normalize_date(date_value)
    city = normalize_text(city)

    data = fetch_worker(
        date_value=iso_date,
        city=city,
    )

    races = data.get("races", [])

    if not isinstance(races, list):
        races = []

    # -----------------------------------------------------
    # Worker'dan gelen gerçek değerleri koru
    # -----------------------------------------------------

    race_count = data.get(
        "raceCount",
        len(races),
    )

    horse_count = data.get(
        "horseCount",
        sum(
            len(r.get("horses", []))
            for r in races
            if isinstance(r, dict)
        ),
    )

    # -----------------------------------------------------
    # Debug bilgisi
    # -----------------------------------------------------

    total_horses = 0
    horses_per_race = {}

    for race in races:

        if not isinstance(race, dict):
            continue

        horses = race.get("horses", [])

        if not isinstance(horses, list):
            horses = []

        race_no = race.get(
            "no",
            len(horses_per_race) + 1,
        )

        horses_per_race[str(race_no)] = len(horses)

        total_horses += len(horses)

    # -----------------------------------------------------
    # Streamlit'in beklediği standart cevap
    # -----------------------------------------------------

    result = {
        "ok": True,
        "source": data.get(
            "source",
            "TJK Günlük Yarış Programı",
        ),
        "date": iso_date,
        "date_tr": format_date_tr(iso_date),
        "city": city,

        "races": races,

        "race_count": int(race_count or len(races)),
        "raceCount": int(race_count or len(races)),

        "total_horses": int(
            total_horses
            if total_horses
            else horse_count or 0
        ),

        "horse_count": int(
            horse_count
            if horse_count is not None
            else total_horses
        ),

        "horseCount": int(
            horse_count
            if horse_count is not None
            else total_horses
        ),

        "status": data.get("status"),

        "source_url": data.get("sourceUrl", ""),

        "debug": {
            "transport": "Cloudflare Worker",
            "worker_url": API_DATA,
            "date": iso_date,
            "date_tr": format_date_tr(iso_date),
            "city": city,
            "city_id": CITY_IDS.get(city),

            "worker_status": data.get("status"),

            "race_count": len(races),

            "total_horse_count": total_horses,

            "horses_per_race": horses_per_race,

            "source": data.get(
                "source",
                "TJK Günlük Yarış Programı",
            ),

            "source_url": data.get(
                "sourceUrl",
                "",
            ),
        },
    }

    return result


# =========================================================
# TEK AT / YARDIMCI VERİ NORMALİZASYONU
# =========================================================

def normalize_horse(horse: Dict[str, Any]) -> Dict[str, Any]:

    if not isinstance(horse, dict):
        return {}

    result = dict(horse)

    # Eski Worker farklı isimlendirme kullansa bile
    # Streamlit tarafında tek alan adı kullanabilmek için
    # güvenli alias'lar.

    if "name" not in result:
        result["name"] = (
            result.get("horse")
            or result.get("horseName")
            or result.get("At İsmi")
            or ""
        )

    if "no" not in result:
        result["no"] = (
            result.get("number")
            or result.get("s")
            or result.get("S")
            or ""
        )

    if "weight" not in result:
        result["weight"] = (
            result.get("siklet")
            or result.get("Sıklet")
            or result.get("kilo")
            or ""
        )

    if "hp" not in result:
        result["hp"] = (
            result.get("HP")
            or result.get("rating")
            or result.get("RT")
            or ""
        )

    if "trainer" not in result:
        result["trainer"] = (
            result.get("antrenor")
            or result.get("Antrenörü")
            or result.get("trainerName")
            or ""
        )

    if "owner" not in result:
        result["owner"] = (
            result.get("sahip")
            or result.get("Sahip")
            or result.get("ownerName")
            or ""
        )

    if "age" not in result:
        result["age"] = (
            result.get("yas")
            or result.get("Yaş")
            or ""
        )

    if "last6" not in result:
        result["last6"] = (
            result.get("son6")
            or result.get("Son 6 Y.")
            or result.get("lastSix")
            or ""
        )

    if "jockey" not in result:
        result["jockey"] = (
            result.get("jokey")
            or result.get("Jokey")
            or result.get("jockeyName")
            or ""
        )

    return result


def normalize_program(program: Dict[str, Any]) -> Dict[str, Any]:

    if not isinstance(program, dict):
        return {
            "ok": False,
            "races": [],
            "race_count": 0,
            "total_horses": 0,
        }

    races = program.get("races", [])

    normalized_races = []

    for index, race in enumerate(races, start=1):

        if not isinstance(race, dict):
            continue

        item = dict(race)

        if not item.get("no"):
            item["no"] = index

        horses = item.get("horses", [])

        if not isinstance(horses, list):
            horses = []

        item["horses"] = [
            normalize_horse(h)
            for h in horses
            if isinstance(h, dict)
        ]

        if "meta" not in item or not isinstance(
            item["meta"],
            dict,
        ):
            item["meta"] = {}

        normalized_races.append(item)

    program["races"] = normalized_races

    program["race_count"] = len(
        normalized_races
    )

    program["raceCount"] = len(
        normalized_races
    )

    total = sum(
        len(r["horses"])
        for r in normalized_races
    )

    program["total_horses"] = total
    program["horse_count"] = total
    program["horseCount"] = total

    return program


# =========================================================
# DIŞARIDAN KULLANILAN FONKSİYONLAR
# =========================================================

def get_supported_cities() -> List[str]:
    return list(CITY_IDS.keys())


def get_city_id(city: str) -> int:
    city = normalize_text(city)

    if city not in CITY_IDS:
        raise ValueError(
            f"Bilinmeyen hipodrom: {city}"
        )

    return CITY_IDS[city]


def worker_health() -> Dict[str, Any]:

    try:

        response = requests.get(
            API_HEALTH,
            timeout=15,
            headers={
                "User-Agent":
                    "Race-Intelligence-Streamlit/34",
                "Accept":
                    "application/json,text/plain,*/*",
            },
        )

        if response.status_code != 200:
            return {
                "ok": False,
                "status": response.status_code,
                "error": response.text[:500],
            }

        data = response.json()

        return data

    except Exception as exc:

        return {
            "ok": False,
            "status": 0,
            "error": str(exc),
        }


# =========================================================
# GERİYE DÖNÜK UYUMLULUK
# =========================================================

def fetch_program(
    date_value: Any,
    city: str,
) -> Dict[str, Any]:

    return normalize_program(
        get_program(
            date_value,
            city,
        )
    )


def load_program(
    date_value: Any,
    city: str,
) -> Dict[str, Any]:

    return normalize_program(
        get_program(
            date_value,
            city,
        )
    )
