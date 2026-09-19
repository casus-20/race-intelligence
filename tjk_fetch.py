import re
import html as _html
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode, urljoin, parse_qs, urlparse
from html.parser import HTMLParser

import requests


TJK_BASE = "https://www.tjk.org"
PROGRAM_URL = f"{TJK_BASE}/TR/YarisSever/Info/Page/GunlukYarisProgrami"
HISTORY_URL = f"{TJK_BASE}/TR/YarisSever/Query/ConnectedPage/AtKosuBilgileri"
WORKOUT_URL = f"{TJK_BASE}/TR/YarisSever/Query/Page/IdmanIstatistikleri"

CITY_IDS = {
    "Ankara": 5, "Kocaeli": 9, "İstanbul": 3, "Bursa": 4, "İzmir": 2,
    "Adana": 1, "Elazığ": 6, "Diyarbakır": 8, "Şanlıurfa": 7, "Antalya": 10,
}



class _MiniTag:
    def __init__(self, name="", attrs=None, parent=None):
        self.name = name
        self.attrs = dict(attrs or [])
        self.parent = parent
        self.children = []
        self._text = []

    def get(self, key, default=None):
        return self.attrs.get(key, default)

    def get_text(self, sep="", strip=False):
        parts = []
        def walk(node):
            if node._text:
                parts.extend(node._text)
            for child in node.children:
                walk(child)
        walk(self)
        text = sep.join(x for x in parts if x) if sep else "".join(parts)
        return text.strip() if strip else text

    def find_all(self, names=None, href=False, limit=None):
        wanted = None
        if names is not None:
            wanted = {str(x).lower() for x in names} if isinstance(names, (list, tuple, set)) else {str(names).lower()}
        out = []
        def walk(node):
            for child in node.children:
                if wanted is None or child.name.lower() in wanted:
                    if not href or child.get("href") is not None:
                        out.append(child)
                        if limit and len(out) >= limit:
                            return True
                if walk(child) and limit and len(out) >= limit:
                    return True
            return False
        walk(self)
        return out

    def find_parent(self, name):
        wanted = str(name).lower()
        node = self.parent
        while node is not None:
            if node.name.lower() == wanted:
                return node
            node = node.parent
        return None


class _MiniSoup(_MiniTag):
    def __init__(self):
        super().__init__("document")
        self._title = None

    @property
    def title(self):
        if self._title is None:
            titles = self.find_all("title", limit=1)
            self._title = titles[0] if titles else None
        return self._title


class _TJKHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _MiniSoup()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _MiniTag(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag.lower() not in {"meta", "link", "img", "br", "hr", "input", "source", "area", "base", "col", "embed", "param", "track", "wbr"}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = _MiniTag(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        tag = tag.lower()
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].name.lower() == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if data:
            self.stack[-1]._text.append(data)


def BeautifulSoup(text, parser="html.parser"):
    p = _TJKHTMLParser()
    p.feed(text or "")
    p.close()
    return p.root


SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
    "Referer": TJK_BASE + "/",
})


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


def _request_html(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 35) -> str:
    try:
        r = SESSION.get(url, params=params, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"TJK bağlantısı başarısız: {exc}") from exc
    text = r.text or ""
    if len(text) < 200:
        raise RuntimeError("TJK boş/geçersiz HTML döndürdü.")
    return text


def _date_tr(value: Any) -> str:
    iso = normalize_date(value)
    y,m,d = iso.split("-")
    return f"{d}/{m}/{y}"


def _program_params(date_value: Any, city: str, city_id: int) -> List[Dict[str, Any]]:
    d = _date_tr(date_value)
    # TJK'nin kullandığı tarih/şehir parametrelerini birlikte gönderiyoruz.
    return [
        {"QueryParameter_Tarih": d, "SehirAdi": city, "SehirId": city_id},
        {"QueryParameter_Tarih": d, "SehirAdi": city},
        {"Tarih": d, "SehirAdi": city, "SehirId": city_id},
    ]


def _clean(s: Any) -> str:
    return re.sub(r"\s+", " ", _html.unescape(str(s or ""))).strip()


def _num(s: Any) -> str:
    m = re.search(r"\b(\d{1,2})\b", _clean(s))
    return m.group(1) if m else ""


def _horse_id(href: str) -> str:
    q = parse_qs(urlparse(urljoin(TJK_BASE, href)).query)
    for key in ("QueryParameter_AtId", "AtId", "atId", "at_id", "id"):
        if q.get(key):
            return q[key][0]
    m = re.search(r"(?:AtId|atId)[=/_-](\d+)", href or "")
    return m.group(1) if m else ""


def _actual_hippodrome(soup: BeautifulSoup, fallback: str) -> str:
    # Önce sayfanın başlık/heading alanlarını kullan; tüm sayfada greedy regex kullanma.
    candidates = []
    if soup.title:
        candidates.append(soup.title.get_text(" ", strip=True))
    for tag in soup.find_all(["h1","h2","h3","h4"], limit=20):
        candidates.append(tag.get_text(" ", strip=True))
    for text in candidates:
        m = re.search(r"([A-Za-zÇĞİÖŞÜçğıöşüİı0-9.'’\- ]+?)\s+Hipodromu\b", text, re.I)
        if m:
            return _clean(m.group(1))
    return fallback


def _find_header_map(table) -> Dict[str,int]:
    rows = table.find_all("tr")
    if not rows: return {}
    for row in rows[:3]:
        cells = row.find_all(["th","td"])
        heads = [_clean(c.get_text(" ", strip=True)).lower() for c in cells]
        if any(("at" in h or "isim" in h or "jokey" in h or "siklet" in h or "hp" in h) for h in heads):
            return {h:i for i,h in enumerate(heads)}
    return {}


def _pick(cells, hmap, names, default=""):
    for name in names:
        for h,i in hmap.items():
            if name in h and i < len(cells):
                return cells[i]
    return default


def _parse_program_html(html_text: str, city: str, date_value: Any) -> Dict[str, Any]:
    soup = BeautifulSoup(html_text, "html.parser")
    actual_city = _actual_hippodrome(soup, city)
    races = []
    current = None

    # Belge sırasını koruyarak yarış başlıklarını ve at satırlarını eşleştir.
    for node in soup.find_all(["h1","h2","h3","h4","h5","div","tr"]):
        text = _clean(node.get_text(" ", strip=True))
        if not text:
            continue

        rm = re.search(r"(?<!\d)(\d{1,2})\.\s*Koşu\b(?:\s*[-–—]?\s*(\d{1,2}:\d{2}))?", text, re.I)
        if rm:
            no = int(rm.group(1))
            tm = rm.group(2) or ""
            current = {"race_number": no, "race_time": tm, "distance": "", "surface": "",
                       "condition": text, "horses": [], "meta": {}}
            races.append(current)
            dm = re.search(r"\b(\d{3,4})\s*m\b", text, re.I)
            if dm: current["distance"] = dm.group(1)
            sm = re.search(r"\b(kum|çim|sentetik)\b", text, re.I)
            if sm: current["surface"] = sm.group(1).title()
            continue

        if node.name != "tr" or current is None:
            continue

        links = node.find_all("a", href=True)
        horse_link = None
        for a in links:
            hid = _horse_id(a.get("href",""))
            if hid:
                horse_link = (a,hid)
                break
        if not horse_link:
            continue

        cells = [_clean(c.get_text(" ", strip=True)) for c in node.find_all(["th","td"])]
        if not cells: continue
        hmap = _find_header_map(node.find_parent("table")) if node.find_parent("table") else {}

        name = _clean(horse_link[0].get_text(" ", strip=True))
        number = cells[0] if cells and re.fullmatch(r"\d{1,2}", cells[0]) else _num(cells[0])
        horse = {
            "atId": horse_link[1], "at_id": horse_link[1], "name": name, "horse": name,
            "no": number, "number": number,
            "age": _pick(cells,hmap,["yaş","yas"]),
            "weight": _pick(cells,hmap,["siklet","kilo","kg"]),
            "jockey": _pick(cells,hmap,["jokey"]),
            "hp": _pick(cells,hmap,["hp","handikap"]),
            "agf": _pick(cells,hmap,["agf"]),
            "odds": _pick(cells,hmap,["gny","ganyan","oran"]),
            "st": _pick(cells,hmap,["st","start","kulvar"]),
            "kgs": _pick(cells,hmap,["kgs"]),
            "form": _pick(cells,hmap,["son 6","son6","form"]),
            "raw_cells": cells,
        }
        # Header bulunamadığında temel alanları hücre pozisyonundan güvenli biçimde tamamla.
        if not horse["age"] and len(cells) > 1 and re.search(r"\d", cells[1]): horse["age"] = cells[1]
        if not horse["weight"]:
            for c in cells:
                if re.search(r"\b\d{2}(?:[.,]\d)?\b", c):
                    horse["weight"] = c; break
        current["horses"].append(horse)

    # Aynı yarış numarası birden fazla DOM düğümünde açılmışsa atları birleştir.
    merged = {}
    for r in races:
        key = r["race_number"]
        if key not in merged: merged[key] = r
        else:
            if not merged[key].get("race_time"): merged[key]["race_time"] = r.get("race_time","")
            merged[key]["horses"].extend(r.get("horses",[]))
    races = list(merged.values())
    for r in races:
        # duplicate at rows temizle
        seen=set(); uniq=[]
        for h in r["horses"]:
            k=(str(h.get("atId","")), str(h.get("name","")).upper())
            if k in seen: continue
            seen.add(k); uniq.append(h)
        r["horses"]=uniq
    return {
        "ok": bool(races),
        "source": "TJK Günlük Yarış Programı",
        "date": normalize_date(date_value),
        "date_tr": _date_tr(date_value),
        "city": actual_city,
        "races": races,
        "source_url": "",
        "status": "ok" if races else "empty",
    }


def fetch_worker(date_value: Any, city: str, timeout: int = 45) -> Dict[str, Any]:
    # İsim geriye dönük uyumluluk için korunuyor; artık Worker çağrısı yok.
    city = normalize_text(city)
    if city not in CITY_IDS:
        raise ValueError(f"Bilinmeyen hipodrom: {city}")
    last_error = None
    for params in _program_params(date_value, city, CITY_IDS[city]):
        try:
            html_text = _request_html(PROGRAM_URL, params=params, timeout=timeout)
            data = _parse_program_html(html_text, city, date_value)
            if data.get("races"):
                data["source_url"] = PROGRAM_URL + "?" + urlencode(params)
                data["city_requested"] = city
                data["hippodrome"] = data.get("city") or city
                return data
        except Exception as exc:
            last_error = exc
    if last_error:
        raise RuntimeError(f"TJK günlük program alınamadı ({city}): {last_error}") from last_error
    return {"ok":False,"races":[],"city":city,"date":normalize_date(date_value)}

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

    debug.setdefault("transport", "TJK direct")
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
        raise ValueError(f"Bilinmeyen hipodrom: {city}")
    return CITY_IDS[city]


def worker_health() -> Dict[str, Any]:
    return {"ok": True, "transport": "TJK direct", "source": TJK_BASE}


def get_program(date_value: Any, city: str) -> Dict[str, Any]:
    data = fetch_worker(date_value, city)
    races = data.get("races", [])
    result = {
        "ok": bool(races),
        "source": data.get("source","TJK Günlük Yarış Programı"),
        "date": normalize_date(date_value),
        "date_tr": _date_tr(date_value),
        "city": normalize_text(city),
        "hippodrome": data.get("hippodrome") or data.get("city") or normalize_text(city),
        "races": races,
        "race_count": len(races),
        "raceCount": len(races),
        "total_horses": sum(len(r.get("horses",[])) for r in races if isinstance(r,dict)),
        "horse_count": sum(len(r.get("horses",[])) for r in races if isinstance(r,dict)),
        "horseCount": sum(len(r.get("horses",[])) for r in races if isinstance(r,dict)),
        "status": data.get("status"),
        "source_url": data.get("source_url",""),
        "debug": {
            "transport": "TJK direct",
            "source": "TJK Günlük Yarış Programı",
            "city": normalize_text(city),
            "hippodrome": data.get("hippodrome") or data.get("city") or normalize_text(city),
            "source_url": data.get("source_url",""),
            "race_count": len(races),
        },
    }
    return normalize_program(result)


def _table_dicts(soup: BeautifulSoup) -> List[Dict[str,str]]:
    out=[]
    for table in soup.find_all("table"):
        rows=table.find_all("tr")
        if len(rows)<2: continue
        header_cells=rows[0].find_all(["th","td"])
        headers=[_clean(c.get_text(" ",strip=True)).lower() for c in header_cells]
        if not headers: continue
        for row in rows[1:]:
            cells=[_clean(c.get_text(" ",strip=True)) for c in row.find_all(["th","td"])]
            if len(cells)<2: continue
            d={headers[i] if i<len(headers) else f"col{i}":cells[i] for i in range(len(cells))}
            out.append(d)
    return out


def _history_row(d: Dict[str,str]) -> Dict[str,Any]:
    def v(names):
        return next((val for k,val in d.items() if any(n in k for n in names) and val not in ("","-")), "")
    return {
        "date": v(["tarih","date"]), "city": v(["hipodrom","şehir","sehir"]),
        "distance": v(["mesafe"]), "surface": v(["pist"]),
        "place": v(["sıra","derece","sira"]), "time": v(["derece","zaman"]),
        "weight": v(["kilo","siklet"]), "equipment": v(["takı"]),
        "jockey": v(["jokey"]), "post": v(["st","kulvar"]),
        "odds": v(["ganyan","gny"]), "group": v(["grup","koşu şart","kosu sart"]),
        "raceName": v(["koşu adı","kosu adi","koşu"]), "raceType": v(["koşu türü","kosu turu"]),
        "trainer": v(["antrenör","antrenor"]), "owner": v(["sahip"]),
        "hp": v(["hp","handikap"]), "prize": v(["ikramiye","kazanç"]),
        "l20": v(["20"]), "raw": d,
    }


def _direct_tjk_history(at_id: str, timeout: int = 30) -> List[Dict[str,Any]]:
    url = f"{HISTORY_URL}?1=1&QueryParameter_AtId={at_id}"
    soup = BeautifulSoup(_request_html(url, timeout=timeout), "html.parser")
    rows = [_history_row(d) for d in _table_dicts(soup)]
    rows = [r for r in rows if r.get("date")]
    return rows


def get_horse_history(at_id: Any, timeout: int = 30) -> Dict[str,Any]:
    if at_id in (None,""): return {"ok":False,"history":[],"error":"atId yok"}
    try:
        hist = _direct_tjk_history(str(at_id), timeout=timeout)
        return {"ok":bool(hist),"history":hist,"historyCount":len(hist),
                "historySource":"TJK AtKosuBilgileri"}
    except Exception as exc:
        return {"ok":False,"history":[],"historyCount":0,"error":str(exc),
                "historySource":"TJK AtKosuBilgileri"}


def get_horse_workouts(horse: str, timeout: int = 30) -> Dict[str,Any]:
    # TJK idman sayfası at adına göre filtrelenebildiğinden önce doğrudan sorgulanır.
    if not normalize_text(horse): return {"ok":False,"workouts":[]}
    params={"QueryParameter_AtAdi":normalize_text(horse)}
    try:
        soup=BeautifulSoup(_request_html(WORKOUT_URL,params=params,timeout=timeout),"html.parser")
        rows=_table_dicts(soup)
        workouts=[]
        for d in rows:
            text=" ".join(d.values())
            if re.search(r"\b\d{2,4}\s*m\b|idman|galop|kenter",text,re.I):
                workouts.append(d)
        return {"ok":bool(workouts),"workouts":workouts,"workoutCount":len(workouts),
                "workoutSource":"TJK İdman İstatistikleri"}
    except Exception as exc:
        return {"ok":False,"workouts":[],"workoutCount":0,"error":str(exc)}


def history_before_target(history: List[Dict[str,Any]], target_date: Any) -> List[Dict[str,Any]]:
    td = normalize_date(target_date)
    out=[]
    for row in history or []:
        raw=row.get("date") if isinstance(row,dict) else ""
        try:
            s=str(raw).strip()
            d=""
            m=re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})",s)
            if m: d=f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
            else:
                m=re.search(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})",s)
                if m: d=f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            if d and d < td: out.append(row)
        except Exception:
            continue
    return out


def _earnings_from_history(history: List[Dict[str,Any]]) -> Dict[str,Any]:
    total=0.0; year=0.0; current_year=datetime.now().year
    for r in history or []:
        val=r.get("prize") if isinstance(r,dict) else ""
        nums=re.sub(r"[^0-9,.-]","",str(val).replace(".","").replace(",","."))
        try: amount=float(nums) if nums else 0.0
        except: amount=0.0
        total += amount
        if str(r.get("date","")).endswith(str(current_year)): year += amount
    return {"total": total or None, "year": year or None}


def get_horse_enrichment(at_id: Any, horse: str, timeout: int = 30,
                         target_date: Any = None, target_city: str = "",
                         target_distance: Any = None, target_surface: str = "",
                         target_class: str = "") -> Dict[str,Any]:
    errors=[]
    with ThreadPoolExecutor(max_workers=2) as ex:
        fh=ex.submit(get_horse_history,at_id,timeout)
        fw=ex.submit(get_horse_workouts,horse,timeout)
        hd=fh.result(); wd=fw.result()
    history=hd.get("history",[]) if isinstance(hd,dict) else []
    workouts=wd.get("workouts",[]) if isinstance(wd,dict) else []
    if target_date and history:
        history=history_before_target(history,target_date)
    if not isinstance(history,list): history=[]
    if not isinstance(workouts,list): workouts=[]
    if hd.get("error"): errors.append(f"horse: {hd['error']}")
    if wd.get("error"): errors.append(f"workouts: {wd['error']}")
    result={"ok":bool(history or workouts),"history":history,"workouts":workouts,
            "historyCount":len(history),"workoutCount":len(workouts),
            "earnings":hd.get("earnings") if isinstance(hd,dict) else None}
    if not result["earnings"]: result["earnings"]=_earnings_from_history(history)
    if errors: result["error"]=" | ".join(errors)
    result["historySource"]="TJK AtKosuBilgileri"
    return result


def fetch_program(date_value: Any, city: str) -> Dict[str,Any]:
    return normalize_program(get_program(date_value,city))


def load_program(date_value: Any, city: str) -> Dict[str,Any]:
    return normalize_program(get_program(date_value,city))
