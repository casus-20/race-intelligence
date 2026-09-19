from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlparse

import requests

TJK_BASE = "https://www.tjk.org"
PROGRAM_URL = f"{TJK_BASE}/TR/YarisSever/Info/Page/GunlukYarisProgrami"
HISTORY_URL = f"{TJK_BASE}/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri"
WORKOUT_URL = f"{TJK_BASE}/TR/YarisSever/Query/Page/IdmanIstatistikleri"

CITY_IDS = {
    "Ankara": 5, "Kocaeli": 9, "İstanbul": 3, "Bursa": 4,
    "İzmir": 2, "Adana": 1, "Elazığ": 6, "Diyarbakır": 8,
    "Şanlıurfa": 7, "Antalya": 10,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": PROGRAM_URL,
}


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split()).strip()


def normalize_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = normalize_text(value)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date().isoformat()
        except Exception:
            pass
    raise ValueError(f"Geçersiz tarih: {value}")


def format_date_tr(value: Any) -> str:
    y, m, d = normalize_date(value).split("-")
    return f"{d}/{m}/{y}"


def _city_key(value: Any) -> str:
    s = normalize_text(value).lower()
    return (s.replace("ı", "i").replace("ş", "s").replace("ğ", "g")
             .replace("ü", "u").replace("ö", "o").replace("ç", "c"))


def _canonical_city(value: Any) -> str:
    s = normalize_text(value)
    s = re.sub(r"\s+hipodromu.*$", "", s, flags=re.I)
    aliases = {
        "diyarbakir": "Diyarbakır", "sanliurfa": "Şanlıurfa", "elazig": "Elazığ",
        "istanbul": "İstanbul", "ankara": "Ankara", "izmir": "İzmir",
        "bursa": "Bursa", "kocaeli": "Kocaeli", "adana": "Adana", "antalya": "Antalya",
    }
    return aliases.get(_city_key(s), s)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    # TJK tarafında bazı istekler ana sayfadan alınan ASP.NET/session
    # çerezleri olmadan farklı/boş içerik döndürebiliyor. Her bağımsız
    # sorguda önce ana sayfayı açıp oturumu ısıtıyoruz.
    try:
        s.get(TJK_BASE + "/TR/YarisSever", timeout=15)
    except Exception:
        pass
    return s


def _get(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 30, session: Optional[requests.Session] = None) -> requests.Response:
    s = session or _session()
    last = None
    for attempt in range(3):
        try:
            r = s.get(url, params=params, timeout=timeout)
            last = r
            if r.status_code in (429, 500, 502, 503, 504):
                import time
                time.sleep(0.8 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == 2:
                raise
    if last is not None:
        last.raise_for_status()
    raise RuntimeError("TJK isteği başarısız")


def _program_page_url(date_value: Any, city: str, city_id: int, include_city_id: bool = False) -> str:
    # TJK'nın günlük program bağlantılarında SehirAdi parametresi temel
    # parametredir. SehirId bazı eski sayfa sürümlerinde kullanılmıştır;
    # ilk URL'de göndermiyoruz, yalnızca alternatif sorguda kullanıyoruz.
    params = {
        "QueryParameter_Tarih": format_date_tr(date_value),
        "SehirAdi": city,
    }
    if include_city_id:
        params["SehirId"] = city_id
    return PROGRAM_URL + "?" + urlencode(params)


class _TJKParser(HTMLParser):
    """TJK HTML'sini harici HTML bağımlılığı olmadan tablo/satır/link olarak toplar."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._title_depth = 0
        self._tag_stack: List[str] = []
        self._text_stack: List[List[str]] = []
        self.tables: List[List[List[str]]] = []
        self._table: Optional[List[List[str]]] = None
        self._row: Optional[List[str]] = None
        self._cell: Optional[List[str]] = None
        self._cell_links: List[str] = []
        self.row_links: List[List[List[str]]] = []
        self.blocks: List[str] = []
        self._block: List[str] = []
        self.all_text: List[str] = []
        self.links: List[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_d = dict(attrs)
        self._tag_stack.append(tag)
        if tag == "title":
            self._title_depth = len(self._tag_stack)
        if tag == "table":
            self._table = []
            self.tables.append(self._table)
            self.row_links.append([])
        elif tag == "tr" and self._table is not None:
            self._row = []
            self._cell = None
            self._cell_links = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            # Satırdaki bağlantıları hücre değişirken silme; AtId linki
            # çoğu TJK tablosunda üçüncü/dördüncü hücrede bulunur.
        elif tag == "a":
            href = attrs_d.get("href", "")
            self.links.append((normalize_text(self._current_block_text()), href))
            if self._row is not None:
                self._cell_links.append(href)
        if tag in ("h1", "h2", "h3", "h4", "p", "div"):
            self._block = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(normalize_text(" ".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._table is not None and self._row is not None:
            if any(self._row):
                self._table.append(self._row)
                if self.row_links:
                    self.row_links[-1].append(list(self._cell_links))
            self._row = None
            self._cell = None
            self._cell_links = []
        elif tag == "table":
            self._table = None
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data):
        txt = normalize_text(html.unescape(data))
        if not txt:
            return
        self.all_text.append(txt)
        if self._cell is not None:
            self._cell.append(txt)
        self._block.append(txt)
        if self._title_depth and len(self._tag_stack) >= self._title_depth:
            self.title += " " + txt

    def _current_block_text(self):
        return " ".join(self._block)


def _actual_hippodrome(parsed: _TJKParser, fallback: str) -> str:
    candidates = [parsed.title] + parsed.all_text[:120]
    for text in candidates:
        m = re.search(r"([A-Za-zÇĞİÖŞÜçğıöşüİı\- ]{2,40})\s+Hipodromu", text, re.I)
        if m:
            return _canonical_city(m.group(1))
    return _canonical_city(fallback)


def _page_has_races(text: str) -> bool:
    t = normalize_text(text)
    if not t:
        return False
    # TJK sayfa sürümlerinde başlık; "1. Koşu", "1 Koşu" veya yalnızca
    # koşu saatleri şeklinde gelebiliyor. Birden fazla saat tek başına yeterli
    # kabul edilmez; Koşu ifadesiyle birlikte değerlendirilir.
    if re.search(r"\b\d+\s*\.\s*Koşu\b", t, re.I):
        return True
    if re.search(r"\b\d+\s*Koşu\b", t, re.I):
        return True
    return bool(re.search(r"(?:Koşu|KOŞU).{0,80}\b\d{1,2}[:.]\d{2}\b", t, re.I) or
                re.search(r"\b\d{1,2}[:.]\d{2}\b.{0,80}(?:Koşu|KOŞU)", t, re.I))


def _parse_race_header(text: str) -> Optional[Dict[str, Any]]:
    text = normalize_text(text)
    m = re.search(r"(?:^|\s)(\d+)\s*\.\s*Koşu\s*(?:-|\|)?\s*(\d{1,2}[\.:]\d{2})?", text, re.I)
    if not m:
        return None
    no = int(m.group(1))
    tm = (m.group(2) or "").replace(":", ".")
    dm = re.search(r"(\d{3,4})\s*m\b", text, re.I)
    sm = re.search(r"\b(Kum|Çim|Sentetik)\b", text, re.I)
    return {"race_number": no, "race_time": tm, "distance": int(dm.group(1)) if dm else "", "surface": sm.group(1).capitalize() if sm else "", "condition": text}


def _horse_id_from_links(links: List[str]) -> str:
    for href in links:
        full = unquote(urljoin(TJK_BASE, href))
        q = parse_qs(urlparse(full).query)
        for key in ("QueryParameter_AtId", "AtId", "atId", "AtID", "id", "ID"):
            vals = q.get(key)
            if vals and re.fullmatch(r"\d+", vals[0]):
                return vals[0]
        for pat in (r"(?:AtId|atId|AtID)[=/](\d+)", r"(?:horse|horseId)[=/](\d+)"):
            m = re.search(pat, full, re.I)
            if m:
                return m.group(1)
    return ""


def _parse_program_html(raw_html: str, requested_city: str, source_url: str, target_date: str) -> Dict[str, Any]:
    parser = _TJKParser()
    parser.feed(raw_html)
    actual_city = _actual_hippodrome(parser, requested_city)

    races: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    # Önce tablo satırlarında yarış başlığı/at satırlarını tara.
    for ti, table in enumerate(parser.tables):
        links_for_table = parser.row_links[ti] if ti < len(parser.row_links) else []
        for ri, cells in enumerate(table):
            joined = " | ".join(cells)
            header = _parse_race_header(joined)
            if header:
                current = dict(header)
                current.update({"date": target_date, "city": actual_city, "horses": []})
                races.append(current)
                continue
            if current is None or len(cells) < 2:
                continue
            # At satırı: ilk hücre numara, satırda en az bir anlamlı at adı ve mümkünse AtId linki.
            nm = re.match(r"^\s*(\d{1,2})(?:\s|$)", cells[0])
            if not nm:
                continue
            name = normalize_text(cells[1])
            if not name or _city_key(name) in {"at", "atismi", "atismi"}:
                continue
            at_id = _horse_id_from_links(links_for_table[ri] if ri < len(links_for_table) else [])
            horse = {"no": int(nm.group(1)), "name": name, "at_ismi": name, "at_id": at_id, "atId": at_id, "raw_cells": cells}
            # Sık kullanılan alanları koru.
            joined2 = " | ".join(cells)
            age = re.search(r"\b(\d+)y\b", joined2, re.I)
            if age: horse["age"] = age.group(1)
            # 50-65 aralığındaki değerleri kilo adayı olarak kullan.
            nums = re.findall(r"\b(5\d(?:[.,]\d)?|6[0-5](?:[.,]\d)?)\b", joined2)
            if nums: horse["weight"] = nums[-1]
            current["horses"].append(horse)

    # Bazı TJK sürümlerinde yarış başlığı tablo dışında. Bu durumda sayfa metninden yarış sınırlarını bul.
    if not races:
        flat = normalize_text(" ".join(parser.all_text))
        matches = list(re.finditer(r"(\d+)\s*\.\s*Koşu", flat, re.I))
        for m in matches:
            no = int(m.group(1))
            after = flat[m.start():m.start()+300]
            h = _parse_race_header(after) or {"race_number": no, "race_time": "", "distance": "", "surface": "", "condition": after}
            races.append({**h, "date": target_date, "city": actual_city, "horses": []})

    races = [r for r in races if r.get("horses")]
    for r in races:
        r["no"] = r["race_number"]
        r["time"] = r["race_time"]
        r["meta"] = {"distance": r.get("distance"), "surface": r.get("surface"), "detail": r.get("condition", "")}

    horse_count = sum(len(r["horses"]) for r in races)
    return {
        "ok": True, "source": "TJK Günlük Yarış Programı", "source_url": source_url,
        "date": target_date, "date_tr": format_date_tr(target_date), "city": actual_city,
        "races": races, "race_count": len(races), "raceCount": len(races),
        "total_horses": horse_count, "horse_count": horse_count, "horseCount": horse_count,
        "debug": {"transport": "TJK direct", "requested_city": requested_city, "actual_city": actual_city, "source_url": source_url},
    }


def _fetch_city_program(date_value: Any, city: str, city_id: int, timeout: int = 30):
    target = normalize_date(date_value)
    session = _session()
    # Önce resmi TJK günlük-program URL'sinin SehirAdi biçimi.
    urls = [
        _program_page_url(target, city, city_id, include_city_id=False),
        _program_page_url(target, city, city_id, include_city_id=True),
        PROGRAM_URL + "?" + urlencode({"QueryParameter_Tarih": format_date_tr(target), "SehirId": city_id}),
    ]
    last_response = None
    last_parsed = None
    for url in urls:
        try:
            r = _get(url, timeout=timeout, session=session)
            parsed = _parse_program_html(r.text, city, r.url, target)
            last_response, last_parsed = r, parsed
            text = normalize_text(r.text)
            # Yarış başlığı/saati veya parser'ın bulduğu koşular yeterli kanıttır.
            if parsed.get("races") or _page_has_races(text) or re.search(r"\b\d{1,2}[:.]\d{2}\b", text):
                return r, parsed
        except Exception:
            continue
    if last_response is None:
        raise RuntimeError(f"TJK program isteği başarısız: {city}")
    return last_response, (last_parsed or {"ok": False, "races": [], "city": city, "date": target})


def get_active_cities(date_value: Any) -> List[str]:
    """Seçilen tarihte aktif hipodromları doğrudan TJK şehir sayfalarını sorgulayarak bulur."""
    target = normalize_date(date_value)
    active: List[str] = []
    def check(item):
        city, cid = item
        try:
            r, parsed = _fetch_city_program(target, city, cid, timeout=25)
            races = parsed.get("races", []) if isinstance(parsed, dict) else []
            if r.status_code == 200 and (races or _page_has_races(r.text)):
                return _canonical_city(parsed.get("city") or city)
        except Exception:
            return None
        return None
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(check, item) for item in CITY_IDS.items()]
        found = [f.result() for f in as_completed(futures)]
    found_set = {_city_key(x) for x in found if x}
    return [city for city in CITY_IDS if _city_key(city) in found_set]


def discover_active_cities(date_value: Any) -> List[Dict[str, str]]:
    target = normalize_date(date_value)
    cities = get_active_cities(target)
    return [{"city": c, "city_id": str(CITY_IDS[c]), "url": _program_page_url(target, c, CITY_IDS[c])} for c in cities]


def get_supported_cities() -> List[str]:
    return list(CITY_IDS.keys())


def get_city_id(city: str) -> Optional[str]:
    c = _canonical_city(city)
    return str(CITY_IDS[c]) if c in CITY_IDS else None


def get_program(date_value: Any, city: str) -> Dict[str, Any]:
    target = normalize_date(date_value)
    requested = _canonical_city(city)
    if requested not in CITY_IDS:
        raise RuntimeError(f"Bilinmeyen TJK hipodromu: {requested}")
    r, parsed = _fetch_city_program(target, requested, CITY_IDS[requested], timeout=45)
    if r.status_code != 200:
        raise RuntimeError(f"TJK programı alınamadı: HTTP {r.status_code}")
    races = parsed.get("races", []) if isinstance(parsed, dict) else []
    if not races and not _page_has_races(r.text):
        raise RuntimeError(f"{format_date_tr(target)} tarihinde TJK programında {requested} bulunamadı.")
    return parsed


def _parse_history(raw_html: str) -> List[Dict[str, Any]]:
    parser = _TJKParser(); parser.feed(raw_html)
    out: List[Dict[str, Any]] = []
    for table in parser.tables:
        if not table: continue
        headers = table[0]
        norm = [_city_key(re.sub(r"[^A-Za-zÇĞİÖŞÜçğıöşü0-9 ]", "", h)) for h in headers]
        if not any("tarih" in h or "date" in h for h in norm): continue
        for cells in table[1:]:
            if len(cells) < 5: continue
            row = {headers[i]: cells[i] for i in range(min(len(headers), len(cells)))}
            def pick(*terms):
                for k,v in row.items():
                    nk = _city_key(k)
                    if any(t in nk for t in terms): return v
                return ""
            item = {
                "date": pick("tarih", "date"), "city": pick("hipodrom", "sehir", "şehir", "city"),
                "distance": pick("mesafe", "distance"), "surface": pick("pist", "surface"),
                "place": pick("sira", "sıra", "place"), "time": pick("derece", "time"),
                "weight": pick("kilo", "siklet", "weight"), "jockey": pick("jokey"),
                "post": pick("st"), "odds": pick("gny", "ganyan"), "group": pick("grup", "şart", "sart"),
                "raceName": pick("kosuadi", "koşuadi", "kosu", "koşu"), "raceType": pick("kosuturu", "koşutürü", "type"),
                "trainer": pick("antrenor", "antrenör"), "owner": pick("sahip"), "hp": pick("hp", "handikap"),
                "prize": pick("ikramiye", "prize"), "l20": pick("son20"), "raw": row,
            }
            if item["date"]: out.append(item)
        if out: break
    return out


def get_horse_history(at_id: Any, timeout: int = 30) -> Dict[str, Any]:
    if not at_id:
        return {"ok": False, "history": [], "error": "atId yok"}
    r = _get(HISTORY_URL, {"1": "1", "QueryParameter_AtId": str(at_id)}, timeout=timeout)
    rows = _parse_history(r.text)
    return {"ok": True, "history": rows, "historyCount": len(rows), "source_url": r.url}


def get_horse_workouts(horse_name: str, timeout: int = 30) -> Dict[str, Any]:
    if not horse_name:
        return {"ok": False, "workouts": [], "error": "At adı yok"}
    r = _get(WORKOUT_URL, {"1": "1", "QueryParameter_ATADI": horse_name}, timeout=timeout)
    parser = _TJKParser(); parser.feed(r.text)
    workouts=[]
    for table in parser.tables:
        if not table: continue
        hs=table[0]
        if not any(x for x in hs if any(k in _city_key(x) for k in ("600","400","idman"))): continue
        for cells in table[1:]:
            if len(cells)<2: continue
            d={hs[i]:cells[i] for i in range(min(len(hs),len(cells)))}
            def p(*terms):
                for k,v in d.items():
                    if any(t in _city_key(k) for t in terms): return v
                return ""
            workouts.append({"date":p("tarih"),"m600":p("600"),"m400":p("400"),"m200":p("200"),"m800":p("800"),"raw":d})
        if workouts: break
    return {"ok":True,"workouts":workouts,"workoutCount":len(workouts),"source_url":r.url}


def _parse_date_value(v: Any) -> Optional[date]:
    try: return datetime.fromisoformat(normalize_date(v)).date()
    except Exception: return None


def history_before_target(history: List[Dict[str, Any]], target_date: Any) -> List[Dict[str, Any]]:
    td = _parse_date_value(target_date)
    if not td: return list(history or [])
    out=[]
    for row in history or []:
        if not isinstance(row, dict): continue
        d=_parse_date_value(row.get("date"))
        if d and d < td: out.append(row)
    out.sort(key=lambda r: _parse_date_value(r.get("date")) or date.min, reverse=True)
    return out


def get_horse_enrichment(at_id: Any, horse_name: str, target_date: Any = None, timeout: int = 30) -> Dict[str, Any]:
    """app.py'nin mevcut arayüzüyle uyumlu gerçek TJK geçmiş/idman sorgusu."""
    history=[]; workouts=[]; errors=[]
    with ThreadPoolExecutor(max_workers=2) as ex:
        f1=ex.submit(get_horse_history, at_id, timeout) if at_id else None
        f2=ex.submit(get_horse_workouts, horse_name, timeout) if horse_name else None
        try: history=(f1.result() if f1 else {}).get("history",[]) or []
        except Exception as e: errors.append(f"history: {e}")
        try: workouts=(f2.result() if f2 else {}).get("workouts",[]) or []
        except Exception as e: errors.append(f"workouts: {e}")
    filtered=history_before_target(history,target_date) if target_date else history
    result={"ok": not errors, "history": filtered, "workouts": workouts, "history_all": history, "historySource":"TJK direct", "source":"TJK direct"}
    if errors: result["error"]=" | ".join(errors)
    return result


def enrich_race_horses(horses: List[Dict[str, Any]], target_date: Any = None, target_city: str = "", target_distance: Any = None, target_surface: str = "", target_class: str = "", progress_callback=None) -> List[Dict[str, Any]]:
    out=[dict(h) for h in horses if isinstance(h,dict)]
    total=len(out); done=0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures={ex.submit(get_horse_enrichment,h.get("at_id") or h.get("atId") or h.get("id"), h.get("name") or h.get("at_ismi") or "", target_date):i for i,h in enumerate(out)}
        for fut in as_completed(futures):
            i=futures[fut]
            try:
                d=fut.result(); out[i]["_history"]=d.get("history",[]); out[i]["_workouts"]=d.get("workouts",[]); out[i]["_at_id"]=str(out[i].get("at_id") or out[i].get("atId") or out[i].get("id") or ""); out[i]["_enrichment_error"]=str(d.get("error") or "-")
            except Exception as e: out[i]["_enrichment_error"]=str(e)
            done+=1
            if progress_callback:
                try: progress_callback(done,total,out[i].get("name", ""))
                except Exception: pass
    return out


def fetch_program(date_value: Any, city: str) -> Dict[str, Any]: return get_program(date_value, city)
def load_program(date_value: Any, city: str) -> Dict[str, Any]: return get_program(date_value, city)
def worker_health() -> Dict[str, Any]: return {"ok": True, "transport": "TJK direct", "source": TJK_BASE}
