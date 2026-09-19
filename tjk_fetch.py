import requests
import re
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

# Worker/TJK günlük program URL'lerinde kullanılan şehir kimlikleri.
# Özellikle Doğu/Güneydoğu şehirlerinde eski uygulamadaki 7/8 tersliği
# programın yanlış hipodrom adıyla gelmesine yol açabiliyordu.
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



def _clean_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.replace("\xa0", " ").split()).strip()
    return value


def _first_nonempty(d: Dict[str, Any], keys: List[str], default: Any = "") -> Any:
    for key in keys:
        if key in d and d.get(key) not in (None, "", "-", "—", "–"):
            return _clean_value(d.get(key))
    return default


_HISTORY_KEYS = {
    "date": ["date", "tarih", "Tarih", "Date"],
    "city": ["city", "şehir", "sehir", "hipodrom", "Hipodrom", "Hipo"],
    "distance": ["distance", "mesafe", "Msf", "msf", "Msf."],
    "surface": ["surface", "pist", "Pist", "track", "zemin", "Surface"],
    "post": ["post", "start", "St", "st", "kulvar", "Kulvar"],
    "time": ["time", "derece", "Derece", "finishTime", "süre", "Sure"],
    "weight": ["weight", "kilo", "Kilo", "siklet", "Sıklet"],
    "jockey": ["jockey", "jokey", "Jokey", "jockeyName"],
    "group": ["group", "grup", "Grup"],
    "raceName": ["raceName", "race_name", "kosu", "Koşu", "Koşu Adı", "race"],
    "raceType": ["raceType", "race_type", "kosuTuru", "Koşu Türü", "type", "tur"],
    "trainer": ["trainer", "antrenor", "Antrenör", "Antrenörü", "trainerName"],
    "owner": ["owner", "sahip", "Sahip", "ownerName"],
    "hp": ["hp", "HP", "handicap", "handikap", "RT", "rt"],
    "prize": ["prize", "ikramiye", "Ikramiye", "İkramiye", "Kazanç", "kazanc", "earnings", "earning", "prizeAmount", "prize_amount"],
    "l20": ["l20", "L20", "son20", "Son20"],
    "place": ["place", "sira", "Sıra", "S", "finish", "rank", "dereceSirasi"],
}


def _normalize_history_row(row: Any) -> Dict[str, Any] | None:
    """Worker/TJK geçmiş satırını BİZİM SKOR'un ortak şemasına çevirir."""
    if isinstance(row, dict):
        src = dict(row)
        out = dict(row)
        for target, aliases in _HISTORY_KEYS.items():
            value = _first_nonempty(src, aliases, "")
            if value not in (None, ""):
                out[target] = value
        # Bazı Worker sürümlerinde yalnızca 'finish' veya 'S' bulunur.
        if not out.get("place"):
            out["place"] = _first_nonempty(src, ["finish", "S", "sira", "siraNo", "rank"], "")
        return out

    if isinstance(row, (list, tuple)):
        # TJK AtKosuBilgileri tablosunun bilinen kolon sırası.
        cols = [
            "date", "city", "distance", "surface", "post", "time",
            "weight", "jockey", "group", "raceName", "raceType",
            "trainer", "owner", "hp", "prize", "l20",
        ]
        vals = list(row)
        if len(vals) < 3:
            return None
        out = {cols[i]: _clean_value(vals[i]) for i in range(min(len(vals), len(cols)))}
        # Bazı tablolar sıralamayı ayrıca taşıyabilir.
        if len(vals) > 16:
            out["place"] = _clean_value(vals[16])
        return out
    return None


def _extract_history_payload(data: Any) -> List[Dict[str, Any]]:
    """JSON cevabındaki history/rows/items/results/data katmanlarını esnekçe bulur."""
    candidates: List[Any] = []

    def walk(obj: Any, depth: int = 0) -> None:
        if depth > 5:
            return
        if isinstance(obj, dict):
            for key in ("history", "History", "rows", "Rows", "items", "Items",
                        "results", "Results", "data", "Data"):
                value = obj.get(key)
                if isinstance(value, list):
                    candidates.append(value)
                elif isinstance(value, dict):
                    walk(value, depth + 1)
            # history doğrudan tek nesne olarak gelirse
            if any(k in obj for k in ("date", "tarih", "Tarih", "distance", "mesafe", "Derece", "derece")):
                candidates.append([obj])
        elif isinstance(obj, list):
            candidates.append(obj)
            for item in obj[:5]:
                if isinstance(item, (dict, list)):
                    walk(item, depth + 1)

    walk(data)

    best: List[Dict[str, Any]] = []
    for cand in candidates:
        rows = []
        for raw in cand:
            nr = _normalize_history_row(raw)
            if nr:
                rows.append(nr)
        if len(rows) > len(best):
            best = rows
    return best


def _money_to_float(value: Any) -> float:
    if value in (None, "", "-", "—", "–"):
        return 0.0
    s = str(value).strip().replace("₺", "").replace("TL", "").replace("tl", "").strip()
    # 1.234.567,89 -> 1234567.89
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    try:
        return float(m.group(0)) if m else 0.0
    except Exception:
        return 0.0


def _earnings_from_history(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = 0.0
    year = 0.0
    current_year = date.today().year
    for row in history:
        prize = _first_nonempty(row, _HISTORY_KEYS["prize"], "")
        amount = _money_to_float(prize)
        total += amount
        ds = str(_first_nonempty(row, _HISTORY_KEYS["date"], ""))
        if str(current_year) in ds:
            year += amount
    return {"total": total if total > 0 else None, "year": year if year > 0 else None}


def _merge_history(primary: List[Dict[str, Any]], fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aynı yarışları tarih+şehir+mesafe+derece ile tekilleştirerek birleştirir."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in (primary or []) + (fallback or []):
        if not isinstance(row, dict):
            continue
        key = (
            str(row.get("date") or row.get("tarih") or ""),
            str(row.get("city") or row.get("şehir") or ""),
            str(row.get("distance") or row.get("mesafe") or ""),
            str(row.get("time") or row.get("derece") or ""),
            str(row.get("place") or row.get("S") or row.get("sira") or ""),
        )
        if key == ("", "", "", "", ""):
            key = ("raw", repr(sorted(row.items()))[:500])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out



class _TJKTableParser:
    """TJK HTML tablosunu stdlib ile parse eder; BeautifulSoup gerektirmez."""
    def __init__(self):
        from html.parser import HTMLParser
        self.rows = []
        self._row = None
        self._cell = None
        self._buf = []
        self._href = ""

    def feed(self, html_text: str):
        from html.parser import HTMLParser
        outer = self

        class P(HTMLParser):
            def handle_starttag(self, tag, attrs):
                tag = tag.lower()
                if tag == "tr":
                    outer._row = []
                elif tag in ("td", "th") and outer._row is not None:
                    outer._cell = {"text": [], "href": ""}
                    outer._buf = []
                elif tag == "a" and outer._cell is not None:
                    for k, v in attrs:
                        if k.lower() == "href":
                            outer._cell["href"] = v or ""

            def handle_data(self, data):
                if outer._cell is not None:
                    outer._cell["text"].append(data)

            def handle_endtag(self, tag):
                tag = tag.lower()
                if tag in ("td", "th") and outer._cell is not None and outer._row is not None:
                    txt = " ".join("".join(outer._cell["text"]).split())
                    outer._row.append((txt, outer._cell.get("href", "")))
                    outer._cell = None
                elif tag == "tr" and outer._row is not None:
                    if outer._row:
                        outer.rows.append(outer._row)
                    outer._row = None

        # HTMLParser.feed() None döndürür; gerçek satırlar self.rows içindedir.
        # Eski kod feed() dönüşünü rows olarak aldığı için rows=None oluyor ve
        # doğrudan TJK fallback'i hiç parse edilemiyordu.
        P(convert_charrefs=True).feed(html_text or "")
        return self.rows


def _direct_tjk_history(at_id: str, timeout: int = 25) -> List[Dict[str, Any]]:
    """TJK AtKosuBilgileri sayfasını doğrudan okuyup ortak geçmiş şemasına çevirir.

    TJK'nin gerçek AtKosuBilgileri tablosu 2026 sürümünde tipik olarak şu sıradadır:
    Tarih, Şehir, Msf, Pist, S, Derece, Sıklet, Takı, Jokey, St, Gny,
    Grup, K. No-K. Adı, Kcins, Ant., Sahip, HP, Ikramiye, S20.

    Buradaki kritik nokta: ``S`` bitiriş sırasıdır, ``St`` ise start/kulvardır.
    Eski parser bu iki alanı karıştırıyor ve 16 kolonluk eski şemaya zorladığı
    için geçmiş verisini BİZİM SKOR'a kullanılabilir biçimde aktaramıyordu.
    """
    urls = [
        f"https://www.tjk.org/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId={at_id}",
        f"https://www.tjk.org/TR/map/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId={at_id}",
        f"https://www.tjk.org/TR/YarisSever/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId={at_id}",
    ]
    last_error = None

    def norm_header(x: str) -> str:
        x = _clean_value(x).lower()
        x = (x.replace("ı", "i").replace("ş", "s").replace("ğ", "g")
               .replace("ü", "u").replace("ö", "o").replace("ç", "c"))
        x = re.sub(r"[^a-z0-9]+", "", x)
        return x

    header_alias = {
        "tarih": "date", "sehir": "city", "msf": "distance", "mesafe": "distance",
        "pist": "surface", "s": "place", "derece": "time", "siklet": "weight",
        "taki": "equipment", "jokey": "jockey", "st": "post", "gny": "odds",
        "grup": "group", "knokko": "raceName", "kno-kadi": "raceName",
        "kno-kadi": "raceName", "kcins": "raceType", "ant": "trainer",
        "ant": "trainer", "sahip": "owner", "hp": "hp", "ikramiye": "prize",
        "s20": "l20",
    }

    for url in urls:
        try:
            response = requests.get(
                url,
                timeout=timeout,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": "https://www.tjk.org/",
                    "Cache-Control": "no-cache",
                },
            )
            if response.status_code >= 400:
                last_error = RuntimeError(f"TJK HTTP {response.status_code}")
                continue

            parser = _TJKTableParser()
            rows = parser.feed(response.text or "")
            parsed: List[Dict[str, Any]] = []
            header_idx = None
            header_map: Dict[int, str] = {}

            # Önce gerçek başlık satırını bul.
            for ri, cells in enumerate(rows):
                texts = [_clean_value(c[0]) for c in cells]
                norms = [norm_header(x) for x in texts]
                if "tarih" in norms and ("derece" in norms or "pist" in norms) and ("ikramiye" in norms or "hp" in norms):
                    header_idx = ri
                    for ci, h in enumerate(norms):
                        if h in header_alias:
                            header_map[ci] = header_alias[h]
                    break

            for ri, cells in enumerate(rows):
                if header_idx is not None and ri <= header_idx:
                    continue
                texts = [_clean_value(c[0]) for c in cells]
                if len(texts) < 8:
                    continue
                first = str(texts[0] if texts else "")
                if not re.search(r"\d{1,2}[./]\d{1,2}[./]20\d{2}", first):
                    continue

                row: Dict[str, Any] = {}
                if header_map:
                    for ci, key in header_map.items():
                        if ci < len(texts):
                            row[key] = texts[ci]
                else:
                    # Fallback: güncel TJK tablosunun bilinen 19 kolon sırası.
                    cols = [
                        "date", "city", "distance", "surface", "place", "time", "weight",
                        "equipment", "jockey", "post", "odds", "group", "raceName", "raceType",
                        "trainer", "owner", "hp", "prize", "l20",
                    ]
                    row = {cols[i]: texts[i] for i in range(min(len(cols), len(texts)))}

                nr = _normalize_history_row(row)
                if nr and nr.get("date"):
                    parsed.append(nr)

            if parsed:
                return parsed
            last_error = RuntimeError("TJK geçmiş tablosu bulundu ancak yarış satırı ayrıştırılamadı")
        except Exception as exc:
            last_error = exc

    if last_error:
        raise last_error
    return []

def get_horse_history(
    at_id: Any,
    timeout: int = 45,
) -> Dict[str, Any]:
    if at_id in (None, ""):
        return {"ok": False, "history": [], "error": "atId yok"}

    errors: List[str] = []
    payloads = [
        (API_HORSE, {"atId": str(at_id)}),
        (API_HORSEDATA, {"atId": str(at_id), "horse": ""}),
    ]

    for url, params in payloads:
        try:
            data = _worker_json(url, params, timeout=timeout)
            history = _extract_history_payload(data)
            if history:
                earnings = {}
                if isinstance(data.get("earnings"), dict):
                    earnings.update(data.get("earnings") or {})
                derived = _earnings_from_history(history)
                earnings.setdefault("total", derived.get("total"))
                earnings.setdefault("year", derived.get("year"))
                result = dict(data)
                result["history"] = history
                result["historyCount"] = len(history)
                result["earnings"] = earnings
                return result
            errors.append(f"{url}: history boş")
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    # Worker iki endpointte de geçmiş veremiyorsa doğrudan TJK AtKosuBilgileri
    # sayfasını dene. Böylece Worker'ın boş/önbellekli cevabı gerçek geçmişi
    # sıfırlayamaz.
    try:
        direct = _direct_tjk_history(str(at_id), timeout=min(timeout, 25))
        if direct:
            return {
                "ok": True,
                "history": direct,
                "historyCount": len(direct),
                "earnings": _earnings_from_history(direct),
                "historySource": "TJK AtKosuBilgileri (direct fallback)",
            }
        errors.append("direct TJK: geçmiş boş")
    except Exception as exc:
        errors.append(f"direct TJK: {exc}")

    return {
        "ok": False,
        "history": [],
        "historyCount": 0,
        "error": " | ".join(errors),
    }


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


def get_horse_enrichment(
    at_id: Any,
    horse: str,
    timeout: int = 30,
    target_date: Any = None,
    target_city: str = "",
    target_distance: Any = None,
    target_surface: str = "",
    target_class: str = "",
) -> Dict[str, Any]:
    """
    Mevcut uygulama mimarisini bozmadan gerçek koşu geçmişi ve galop verisini
    hafif Worker endpointlerinden alır.

    ÖNEMLİ:
    Eski sürüm önce /horsedata çağırıyordu. Bu endpoint tek at için birden
    fazla TJK sayfası taradığı için Worker 503/resource-limit oluşturabiliyordu.
    Burada doğrudan mevcut /horse ve /workouts endpointleri kullanılır.
    target_* parametreleri uygulama ile geriye dönük uyumluluk için korunur.
    """
    horse_name = normalize_text(horse)
    errors: List[str] = []

    def fetch_history() -> Dict[str, Any]:
        if at_id in (None, ""):
            return {"ok": False, "history": [], "error": "atId yok"}
        try:
            return get_horse_history(at_id, timeout=timeout)
        except Exception as exc:
            return {"ok": False, "history": [], "error": str(exc)}

    def fetch_workouts() -> Dict[str, Any]:
        if not horse_name:
            return {"ok": False, "workouts": [], "error": "At adı yok"}
        try:
            return get_horse_workouts(horse_name, timeout=timeout)
        except Exception as exc:
            return {"ok": False, "workouts": [], "error": str(exc)}

    # Tek at seçildiğinde iki hafif endpoint aynı anda çalışır.
    with ThreadPoolExecutor(max_workers=2) as executor:
        history_future = executor.submit(fetch_history)
        workout_future = executor.submit(fetch_workouts)
        history_data = history_future.result()
        workout_data = workout_future.result()

    history = _extract_history_payload(history_data) if isinstance(history_data, dict) else []
    workouts = workout_data.get("workouts", []) if isinstance(workout_data, dict) else []

    if not isinstance(history, list):
        history = []
    if not isinstance(workouts, list):
        workouts = []

    # Önce hafif /horse endpointini kullan. Geçmiş boş gelirse yalnızca
    # o at için /horsedata fallback'i çalıştır; böylece eksik at verisi
    # sessizce 0 puana düşmez. Fallback yalnızca gerçekten gerektiğinde
    # çağrıldığı için normal analiz hızını gereksiz yere düşürmez.
    if not history and at_id not in (None, ""):
        retry = fetch_history()
        if isinstance(retry, dict) and isinstance(retry.get("history"), list):
            history = retry.get("history") or []
        if not history:
            try:
                fallback = _worker_json(
                    API_HORSEDATA,
                    {"atId": str(at_id), "horse": horse_name},
                    timeout=min(timeout, 30),
                )
                if isinstance(fallback.get("history"), list):
                    history = fallback.get("history") or []
                if not workouts and isinstance(fallback.get("workouts"), list):
                    workouts = fallback.get("workouts") or []
            except Exception as exc:
                errors.append(f"horsedata fallback: {exc}")
        if not history and isinstance(retry, dict) and retry.get("error"):
            errors.append(f"horse: {retry.get('error')}")

    if not workouts and horse_name:
        retry = fetch_workouts()
        if isinstance(retry, dict) and isinstance(retry.get("workouts"), list):
            workouts = retry.get("workouts") or []
        if not workouts and isinstance(retry, dict) and retry.get("error"):
            errors.append(f"workouts: {retry.get('error')}")

    if not history and isinstance(history_data, dict) and history_data.get("error"):
        errors.append(f"horse: {history_data.get('error')}")
    if not workouts and isinstance(workout_data, dict) and workout_data.get("error"):
        errors.append(f"workouts: {workout_data.get('error')}")

    # Worker boş dönerse, Streamlit sunucusundan TJK'nın gerçek at geçmişini
    # doğrudan sorgula. Bu yalnızca Worker geçmişi gerçekten boşsa çalışır.
    if not history and at_id not in (None, ""):
        try:
            direct = _direct_tjk_history(str(at_id), timeout=min(timeout, 25))
            if direct:
                history = direct
                history_data = dict(history_data or {})
                history_data["history"] = history
                history_data["historyCount"] = len(history)
                history_data["earnings"] = _earnings_from_history(history)
        except Exception as exc:
            errors.append(f"direct TJK history: {exc}")

    errors = list(dict.fromkeys(errors))

    # Worker /api/tjk/horse artık resmi kazanç ve hangi TJK kaynağının
    # kullanıldığını da döndürüyor. Bunları Streamlit'e aynen taşı.
    result: Dict[str, Any] = {
        "ok": bool(history or workouts),
        "history": history,
        "workouts": workouts,
        "historyCount": len(history),
        "workoutCount": len(workouts),
    }
    if isinstance(history_data, dict):
        if isinstance(history_data.get("earnings"), dict):
            result["earnings"] = history_data.get("earnings")
        if history_data.get("historySource"):
            result["historySource"] = history_data.get("historySource")
        if history_data.get("atId"):
            result["atId"] = history_data.get("atId")
    if "earnings" not in result:
        result["earnings"] = {"total": None, "year": None}
    if isinstance(result.get("earnings"), dict):
        derived = _earnings_from_history(history)
        if result["earnings"].get("total") in (None, "", 0, 0.0):
            result["earnings"]["total"] = derived.get("total")
        if result["earnings"].get("year") in (None, "", 0, 0.0):
            result["earnings"]["year"] = derived.get("year")

    if errors:
        result["error"] = " | ".join(errors)
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
