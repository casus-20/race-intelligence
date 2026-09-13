import requests
from datetime import date, datetime
from typing import Any, Dict, List
from concurrent.futures import ThreadPoolExecutor


# =========================================================
# RACE INTELLIGENCE
# TJK VERİ KAYNAĞI
# =========================================================

WORKER_URL = "https://fragrant-hat-ae48.raceanaliz.workers.dev"

API_DATA = f"{WORKER_URL}/api/tjk/data"
API_HEALTH = f"{WORKER_URL}/api/health"
API_HORSE = f"{WORKER_URL}/api/tjk/horse"
API_WORKOUTS = f"{WORKER_URL}/api/tjk/workouts"
API_HORSEDATA = f"{WORKER_URL}/api/tjk/horsedata"


# =========================================================
# ŞEHİR LİSTESİ
# =========================================================

CITY_IDS = {
    "Ankara": 5,
    "Kocaeli": 9,
    "İstanbul": 3,
    "Bursa": 4,
    "İzmir": 2,
    "Adana": 1,
    "Elazığ": 6,
    "Diyarbakır": 8,
    "Şanlıurfa": 7,
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

    return normalize_program(result)


# =========================================================
# TEK AT / YARDIMCI VERİ NORMALİZASYONU
# =========================================================

def normalize_horse(horse: Dict[str, Any]) -> Dict[str, Any]:
    """
    Worker V1 -> Streamlit ortak at şeması.

    Worker'ın döndürdüğü alanlar korunur; ayrıca app.py'nin
    kullandığı V34 alan adları da oluşturulur.
    """
    if not isinstance(horse, dict):
        return {}

    result = dict(horse)

    # Ortak / Worker alanları
    result["name"] = (
        result.get("name")
        or result.get("horse")
        or result.get("horseName")
        or result.get("At İsmi")
        or ""
    )

    result["no"] = (
        result.get("no")
        or result.get("number")
        or result.get("numara")
        or result.get("s")
        or result.get("S")
        or ""
    )

    result["age"] = (
        result.get("age")
        or result.get("yas")
        or result.get("Yaş")
        or ""
    )

    result["weight"] = (
        result.get("weight")
        or result.get("siklet")
        or result.get("Sıklet")
        or result.get("kilo")
        or ""
    )

    result["jockey"] = (
        result.get("jockey")
        or result.get("jokey")
        or result.get("Jokey")
        or result.get("jockeyName")
        or ""
    )

    result["hp"] = (
        result.get("hp")
        or result.get("HP")
        or result.get("rating")
        or result.get("RT")
        or ""
    )

    result["last6"] = (
        result.get("last6")
        or result.get("son6")
        or result.get("Son 6 Y.")
        or result.get("lastSix")
        or ""
    )

    result["agf"] = (
        result.get("agf")
        or result.get("AGF")
        or ""
    )

    # AGF ile ganyan/odds birbirine karıştırılmaz.
    result["odds"] = (
        result.get("odds")
        or result.get("Gny")
        or ""
    )

    result["st"] = (
        result.get("st")
        or result.get("St")
        or result.get("start")
        or ""
    )

    result["kgs"] = (
        result.get("kgs")
        or result.get("KGS")
        or ""
    )

    result["form"] = (
        result.get("form")
        or result.get("Forma")
        or result.get("last6")
        or ""
    )

    # TJK programındaki gerçek Orijin alanını koru.
    result["origin"] = (
        result.get("origin")
        or result.get("orijin")
        or result.get("Orijin")
        or result.get("pedigree")
        or ""
    )
    result["orijin"] = result["origin"]

    result["trainer"] = (
        result.get("trainer")
        or result.get("antrenor")
        or result.get("Antrenörü")
        or result.get("trainerName")
        or ""
    )

    result["owner"] = (
        result.get("owner")
        or result.get("sahip")
        or result.get("Sahip")
        or result.get("ownerName")
        or ""
    )

    # Gerçek TJK at kimliğini standartlaştır.
    # ÖNEMLİ: program numarası (no) hiçbir zaman atId yerine kullanılmaz.
    at_id = (
        result.get("atId")
        or result.get("at_id")
        or result.get("atID")
        or result.get("AtId")
        or result.get("AtID")
        or result.get("ATID")
        or result.get("at_kodu")
        or result.get("AtKodu")
        or result.get("AtKoduId")
        or result.get("horseId")
        or result.get("horse_id")
        or result.get("horseKey")
        or result.get("horse_key")
        or result.get("id")
        or result.get("Id")
        or ""
    )
    if at_id not in (None, ""):
        result["atId"] = str(at_id)
        result["at_id"] = str(at_id)

    # app.py'nin kullandığı V34 alan adları
    result["at_ismi"] = result["name"]
    result["numara"] = result["no"]
    result["yas"] = result["age"]
    result["siklet"] = result["weight"]
    result["jokey"] = result["jockey"]

    return result


def normalize_program(program: Dict[str, Any]) -> Dict[str, Any]:
    """
    Worker V1 yarış şemasını app.py'nin beklediği V34 şemasına çevirir.
    Worker verisinin orijinal alanları korunur.
    """
    if not isinstance(program, dict):
        return {
            "ok": False,
            "races": [],
            "race_count": 0,
            "total_horses": 0,
        }

    races = program.get("races", [])
    if not isinstance(races, list):
        races = []

    normalized_races = []

    for index, race in enumerate(races, start=1):
        if not isinstance(race, dict):
            continue

        item = dict(race)

        meta = item.get("meta")
        if not isinstance(meta, dict):
            meta = {}
        item["meta"] = meta

        race_no = (
            item.get("race_number")
            or item.get("no")
            or item.get("number")
            or index
        )

        race_time = (
            item.get("race_time")
            or item.get("time")
            or meta.get("time")
            or ""
        )

        distance = (
            item.get("distance")
            or meta.get("distance")
            or ""
        )

        surface = (
            item.get("surface")
            or meta.get("surface")
            or ""
        )

        condition = (
            item.get("condition")
            or meta.get("condition")
            or meta.get("detail")
            or meta.get("raceName")
            or ""
        )

        horses = item.get("horses", [])
        if not isinstance(horses, list):
            horses = []

        normalized_horses = [
            normalize_horse(h)
            for h in horses
            if isinstance(h, dict)
        ]

        # Worker alanlarını koru + app.py uyumlu alanları ekle
        item["race_number"] = race_no
        item["race_time"] = race_time
        item["distance"] = distance
        item["surface"] = surface
        item["condition"] = condition
        item["no"] = race_no
        item["time"] = race_time
        item["horses"] = normalized_horses

        normalized_races.append(item)

    program["races"] = normalized_races

    program["race_count"] = len(normalized_races)
    program["raceCount"] = len(normalized_races)

    total = sum(len(r["horses"]) for r in normalized_races)

    program["total_horses"] = total
    program["horse_count"] = total
    program["horseCount"] = total

    # Worker ve Streamlit bağlantısını debug ekranında açıkça göster
    debug = program.get("debug")
    if not isinstance(debug, dict):
        debug = {}

    debug.setdefault("transport", "Cloudflare Worker V1")
    debug.setdefault("worker_url", API_DATA)
    debug["city_id"] = CITY_IDS.get(program.get("city"))
    debug["race_count"] = len(normalized_races)
    debug["total_horse_count"] = total
    debug["horses_per_race"] = {
        str(r.get("race_number", i + 1)): len(r.get("horses", []))
        for i, r in enumerate(normalized_races)
    }

    program["debug"] = debug

    return program


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
# GERÇEK AT GEÇMİŞİ / GALOP VERİSİ
# =========================================================

def _worker_json(
    url: str,
    params: Dict[str, Any],
    timeout: int = 45,
) -> Dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        timeout=timeout,
        headers={
            "User-Agent": "Race-Intelligence-Streamlit/34",
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        },
    )
    text = response.text or ""
    if response.status_code != 200:
        raise RuntimeError(
            f"Worker HTTP {response.status_code}: {text[:400]}"
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Worker geçerli JSON döndürmedi: {text[:400]}"
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError("Worker cevabı JSON nesnesi değil.")
    if data.get("ok") is False:
        raise RuntimeError(str(data.get("error") or "Worker isteği başarısız."))
    return data


def get_horse_history(
    at_id: Any,
    timeout: int = 45,
) -> Dict[str, Any]:
    if at_id in (None, ""):
        return {"ok": False, "history": []}
    return _worker_json(
        API_HORSE,
        {"atId": str(at_id)},
        timeout=timeout,
    )


def get_horse_workouts(
    horse: str,
    timeout: int = 45,
) -> Dict[str, Any]:
    if not normalize_text(horse):
        return {"ok": False, "workouts": []}
    return _worker_json(
        API_WORKOUTS,
        {"horse": normalize_text(horse)},
        timeout=timeout,
    )


def _normalize_history_rows(rows: Any) -> List[Dict[str, Any]]:
    """Worker/TJK geçmişini uygulamanın tek standart şemasına getirir."""
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        x = dict(row)
        aliases = {
            "date": ("date", "tarih", "Tarih"),
            "city": ("city", "şehir", "Sehir"),
            "distance": ("distance", "msf", "mesafe", "Msf"),
            "surface": ("surface", "pist", "Pist"),
            "place": ("place", "sira", "Sıra", "S"),
            "time": ("time", "derece", "Derece"),
            "weight": ("weight", "kilo", "siklet", "Sıklet"),
            "equipment": ("equipment", "taki", "takı", "Takı"),
            "jockey": ("jockey", "jokey", "Jokey"),
            "post": ("post", "st", "start", "St"),
            "odds": ("odds", "gny", "Gny"),
            "group": ("group", "grup", "Grup"),
            "raceName": ("raceName", "race_name", "race", "koşu", "kosu"),
            "className": ("className", "class", "kcins", "K Cinsi", "raceType"),
            "trainer": ("trainer", "antrenor", "antrenör", "Antrenör"),
            "owner": ("owner", "sahip", "Sahip"),
            "hp": ("hp", "HP"),
            "prize": ("prize", "ikramiye", "Ikramiye", "İkramiye"),
            "s20": ("s20", "S20"),
        }
        for canonical, keys in aliases.items():
            if x.get(canonical) in (None, ""):
                for key in keys:
                    if x.get(key) not in (None, ""):
                        x[canonical] = x[key]
                        break
        out.append(x)
    return out


def _normalize_workout_rows(rows: Any) -> List[Dict[str, Any]]:
    """TJK galop kayıtlarını tek standart şemaya getirir."""
    if not isinstance(rows, list):
        return []
    out = []
    distance_keys = ("2200", "2000", "1800", "1600", "1400", "1200", "1000", "800", "600", "400", "200")
    for row in rows:
        if not isinstance(row, dict):
            continue
        x = dict(row)
        for d in distance_keys:
            canonical = f"m{d}"
            if x.get(canonical) in (None, ""):
                for key in (d, f"{d}m", f"time{d}"):
                    if x.get(key) not in (None, ""):
                        x[canonical] = x[key]
                        break
        if x.get("date") in (None, ""):
            for key in ("tarih", "Tarih"):
                if x.get(key) not in (None, ""):
                    x["date"] = x[key]
                    break
        if x.get("city") in (None, ""):
            for key in ("track", "hipodrom", "İdman Hipodromu", "şehir", "Sehir"):
                if x.get(key) not in (None, ""):
                    x["city"] = x[key]
                    break
        if x.get("surface") in (None, "") and x.get("pist") not in (None, ""):
            x["surface"] = x["pist"]
        if x.get("type") in (None, "") and x.get("tur") not in (None, ""):
            x["type"] = x["tur"]
        out.append(x)
    return out


def get_horse_enrichment(
    at_id: Any,
    horse: str,
    timeout: int = 20,
    target_date: Any = None,
    target_city: str = "",
    target_distance: Any = None,
    target_surface: str = "",
    target_class: str = "",
) -> Dict[str, Any]:
    """At geçmişi + galop verisini kaynakları gereksiz çoğaltmadan toplar.

    ÖNEMLİ: /horsedata fallback'i toplu analizden kaldırıldı. Bu endpoint
    Worker tarafında bir at için çok sayıda TJK sayfasını art arda taradığı
    için 503/resource-limit oluşturabiliyor. Bunun yerine hafif /horse ve
    /workouts endpointleri kullanılır; yalnızca başarısız olan kaynak bir kez
    daha denenir.
    """
    horse_name = normalize_text(horse)

    def safe_history():
        if at_id in (None, ""):
            return {"ok": False, "history": []}
        try:
            return get_horse_history(at_id, timeout=timeout)
        except Exception as exc:
            return {"ok": False, "history": [], "error": str(exc)}

    def safe_workouts():
        if not horse_name:
            return {"ok": False, "workouts": []}
        try:
            return get_horse_workouts(horse_name, timeout=timeout)
        except Exception as exc:
            return {"ok": False, "workouts": [], "error": str(exc)}

    # İlk tur: iki hafif Worker endpointi aynı anda.
    with ThreadPoolExecutor(max_workers=2) as ex:
        fh = ex.submit(safe_history)
        fw = ex.submit(safe_workouts)
        h = fh.result()
        w = fw.result()

    history = _normalize_history_rows(h.get("history")) if isinstance(h, dict) else []
    workouts = _normalize_workout_rows(w.get("workouts")) if isinstance(w, dict) else []
    errors = []

    # Boş kalan kaynağı yalnızca 1 kez tekrar dene.
    if not history and at_id not in (None, ""):
        h2 = safe_history()
        history = _normalize_history_rows(h2.get("history")) if isinstance(h2, dict) else []
        if not history and isinstance(h2, dict) and h2.get("error"):
            errors.append(f"horse: {h2.get('error')}")

    if not workouts and horse_name:
        w2 = safe_workouts()
        workouts = _normalize_workout_rows(w2.get("workouts")) if isinstance(w2, dict) else []
        if not workouts and isinstance(w2, dict) and w2.get("error"):
            errors.append(f"workouts: {w2.get('error')}")

    # İlk turdaki hata bilgisini yalnızca gerçekten veri yoksa bildir.
    if not history and isinstance(h, dict) and h.get("error"):
        errors.append(f"horse: {h.get('error')}")
    if not workouts and isinstance(w, dict) and w.get("error"):
        errors.append(f"workouts: {w.get('error')}")

    # Tekrarlı hata metinlerini temizle.
    errors = list(dict.fromkeys(errors))

    result = {
        "ok": bool(history or workouts),
        "history": history,
        "workouts": workouts,
        "historyCount": len(history),
        "workoutCount": len(workouts),
        "dataSchema": "tjk-v57-light",
    }
    if errors:
        result["partialError" if (history or workouts) else "error"] = " | ".join(errors)
    return result

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
