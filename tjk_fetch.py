from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

TJK_BASE = "https://www.tjk.org"
PROGRAM_URL = f"{TJK_BASE}/TR/YarisSever/Info/Page/GunlukYarisProgrami"
HISTORY_URL = f"{TJK_BASE}/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri"
WORKOUT_URL = f"{TJK_BASE}/TR/YarisSever/Query/Page/IdmanIstatistikleri"

# TJK şehir ID'leri sabittir; aktiflik bu listedeki URL'lerin gerçekten yarış
# içerip içermediğine bakılarak belirlenir. Şehir adı program sayfasından okunur.
CITY_IDS = {
    "Ankara": 5, "Kocaeli": 9, "İstanbul": 3, "Bursa": 4,
    "İzmir": 2, "Adana": 1, "Elazığ": 6, "Diyarbakır": 8,
    "Şanlıurfa": 7, "Antalya": 10,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Cache-Control": "no-cache",
    "Referer": TJK_BASE + "/",
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


def _city_key(name: str) -> str:
    s = normalize_text(name).lower()
    return (s.replace("ı", "i").replace("ş", "s").replace("ğ", "g")
             .replace("ü", "u").replace("ö", "o").replace("ç", "c"))


def _canonical_city(text: str) -> str:
    s = normalize_text(text)
    s = re.sub(r"\s+Hipodromu.*$", "", s, flags=re.I)
    s = re.sub(r"\s+Hipodrom.*$", "", s, flags=re.I)
    mapping = {
        "diyarbakir": "Diyarbakır", "sanliurfa": "Şanlıurfa", "elazig": "Elazığ",
        "istanbul": "İstanbul", "ankara": "Ankara", "izmir": "İzmir", "bursa": "Bursa",
        "kocaeli": "Kocaeli", "adana": "Adana", "antalya": "Antalya",
    }
    return mapping.get(_city_key(s), s)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _get(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 45) -> requests.Response:
    r = _session().get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r


def _program_url(date_value: Any, city: str, city_id: int) -> str:
    return PROGRAM_URL + "?" + urlencode({
        "QueryParameter_Tarih": format_date_tr(date_value),
        "SehirAdi": city,
        "SehirId": city_id,
    })


def _actual_hippodrome(soup: BeautifulSoup, fallback: str) -> str:
    # Önce title ve başlıkları kontrol et. Tüm sayfa metninde greedy regex
    # kullanmak Elazığ/Diyarbakır gibi isimleri yanlış yakalayabiliyordu.
    candidates: List[str] = []
    if soup.title:
        candidates.append(normalize_text(soup.title.get_text(" ", strip=True)))
    for tag in soup.find_all(["h1", "h2", "h3", "h4"], limit=40):
        candidates.append(normalize_text(tag.get_text(" ", strip=True)))

    for text in candidates:
        m = re.search(r"\b([A-Za-zÇĞİÖŞÜçğıöşüİı\-]+)\s+Hipodromu\b", text, re.I)
        if m:
            return _canonical_city(m.group(1))
        c = _canonical_city(text)
        if c in CITY_IDS:
            return c

    return _canonical_city(fallback)


def _parse_race_header(text: str) -> Optional[Dict[str, Any]]:
    text = normalize_text(text)
    m = re.search(r"(?:^|\s)(\d+)\.\s*Koşu\s+(\d{1,2}\.\d{2})", text, re.I)
    if not m:
        return None
    distance = re.search(r"\b(\d{3,4})\s*m\b", text, re.I)
    surface = re.search(r"\b(Kum|Çim|Sentetik)\b", text, re.I)
    return {
        "race_number": int(m.group(1)),
        "race_time": m.group(2),
        "distance": int(distance.group(1)) if distance else "",
        "surface": surface.group(1).capitalize() if surface else "",
        "condition": text,
    }


def _horse_id_from_row(row: Any) -> str:
    for a in row.find_all("a", href=True):
        href = unquote(urljoin(TJK_BASE, a["href"]))
        q = parse_qs(urlparse(href).query)
        for key in ("QueryParameter_AtId", "AtId", "atId", "QueryParameter_ATID", "id"):
            vals = q.get(key)
            if vals and re.fullmatch(r"\d+", vals[0]):
                return vals[0]
        m = re.search(r"(?:AtId|atId|AtID)[=/](\d+)", href, re.I)
        if m:
            return m.group(1)
    return ""


def _parse_program_html(html: str, requested_city: str, source_url: str, target_date: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    actual_city = _actual_hippodrome(soup, requested_city)
    races: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    # TJK'da koşu başlığı ve at satırları aynı DOM içinde bulunabiliyor.
    # Başlıkları gördükçe yeni koşu aç; yalnızca gerçek at bağlantısı bulunan
    # tablo satırlarını ata dönüştür.
    for tag in soup.find_all(["tr", "div", "p", "h1", "h2", "h3", "h4"]):
        txt = normalize_text(tag.get_text(" ", strip=True))
        header = _parse_race_header(txt)
        if header and (tag.name != "tr" or len(tag.find_all("td")) <= 3):
            current = dict(header)
            current.update({"date": target_date, "city": actual_city, "horses": []})
            races.append(current)
            continue

        if current is None or tag.name != "tr":
            continue

        cells_nodes = tag.find_all("td")
        cells = [normalize_text(c.get_text(" ", strip=True)) for c in cells_nodes]
        if len(cells) < 3:
            continue

        # En güvenli ayraç: satırda TJK at detay bağlantısı veya ilk hücrede
        # yarış numarası. Böylece başlık satırları at olarak alınmaz.
        hrefs = [unquote(urljoin(TJK_BASE, a.get("href", ""))) for a in tag.find_all("a", href=True)]
        has_horse_link = any("AtId" in h or "AtID" in h or "AtId=" in h for h in hrefs)
        num_m = re.match(r"^\s*(\d+)\s*(?:\.|\)|$)", cells[0])
        if not num_m and not has_horse_link:
            continue

        hno = int(num_m.group(1)) if num_m else ""
        name_idx = 1 if len(cells) > 1 else 0
        name = cells[name_idx]
        if not name or name.lower() in {"at", "at ismi", "adı"}:
            continue

        at_id = _horse_id_from_row(tag)
        horse = {
            "no": hno,
            "number": hno,
            "name": name,
            "at_ismi": name,
            "atId": at_id,
            "at_id": at_id,
            "raw_cells": cells,
        }
        joined = " | ".join(cells)
        age = re.search(r"\b(\d+)Y\b", joined, re.I)
        if age:
            horse["age"] = age.group(1)
        # TJK programlarında kilo çoğunlukla 5x.x biçimindedir.
        wm = re.findall(r"\b(4\d(?:[.,]\d)?|5\d(?:[.,]\d)?|6\d(?:[.,]\d)?)\b", joined)
        if wm:
            horse["weight"] = wm[-1]
        current["horses"].append(horse)

    # Bazı TJK sayfa sürümlerinde başlık div'i at tablosundan sonra tekrar
    # geldiği için aynı koşu iki kez oluşabilir; numaraya göre birleştir.
    merged: Dict[int, Dict[str, Any]] = {}
    for race in races:
        no = int(race.get("race_number") or 0)
        if no not in merged:
            merged[no] = race
        else:
            merged[no]["horses"].extend(race.get("horses", []))
            for key in ("race_time", "distance", "surface", "condition"):
                if not merged[no].get(key) and race.get(key):
                    merged[no][key] = race[key]

    final_races = []
    for no in sorted(merged):
        r = merged[no]
        # Tekrarlanan at satırlarını numara+id+isim ile temizle.
        seen = set()
        horses = []
        for h in r.get("horses", []):
            key = (str(h.get("no")), str(h.get("atId")), _city_key(h.get("name", "")))
            if key in seen:
                continue
            seen.add(key)
            horses.append(h)
        r["horses"] = horses
        if horses:
            r["no"] = no
            r["time"] = r.get("race_time", "")
            r["meta"] = {"distance": r.get("distance", ""), "surface": r.get("surface", ""), "detail": r.get("condition", "")}
            final_races.append(r)

    total = sum(len(r["horses"]) for r in final_races)
    return {
        "ok": True,
        "source": "TJK Günlük Yarış Programı",
        "source_url": source_url,
        "date": target_date,
        "date_tr": format_date_tr(target_date),
        "city": actual_city,
        "races": final_races,
        "race_count": len(final_races),
        "raceCount": len(final_races),
        "total_horses": total,
        "horse_count": total,
        "horseCount": total,
        "debug": {
            "transport": "TJK direct",
            "requested_city": requested_city,
            "actual_city": actual_city,
            "source_url": source_url,
        },
    }


def _get_program_for_city(date_value: Any, city: str, city_id: int) -> Optional[Dict[str, Any]]:
    target = normalize_date(date_value)
    url = _program_url(target, city, city_id)
    try:
        r = _get(url, timeout=45)
    except Exception:
        return None
    try:
        data = _parse_program_html(r.text, city, r.url, target)
    except Exception:
        return None
    # Yalnız gerçekten koşu içeren şehir aktif kabul edilir.
    if data.get("races"):
        return data
    return None


def discover_active_cities(date_value: Any) -> List[Dict[str, str]]:
    """Seçilen tarihte TJK'da gerçekten programı bulunan hipodromları bulur."""
    found: List[Dict[str, str]] = []
    target = normalize_date(date_value)
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(_get_program_for_city, target, city, cid): (city, cid)
            for city, cid in CITY_IDS.items()
        }
        for fut in as_completed(futures):
            city, cid = futures[fut]
            try:
                data = fut.result()
            except Exception:
                data = None
            if data and data.get("races"):
                actual = _canonical_city(data.get("city") or city)
                found.append({
                    "city": actual,
                    "city_id": str(cid),
                    "url": data.get("source_url", ""),
                })
    # Ekran sırası sabit olsun; tamamlanma sırası kullanılmasın.
    order = {name: i for i, name in enumerate(CITY_IDS)}
    found.sort(key=lambda x: order.get(x["city"], 999))
    return found


def get_active_cities(date_value: Any) -> List[str]:
    return [x["city"] for x in discover_active_cities(date_value)]


def get_supported_cities() -> List[str]:
    return list(CITY_IDS.keys())


def get_city_id(city: str) -> Optional[str]:
    for name, cid in CITY_IDS.items():
        if _city_key(name) == _city_key(city):
            return str(cid)
    return None


def get_program(date_value: Any, city: str) -> Dict[str, Any]:
    target = normalize_date(date_value)
    requested = _canonical_city(city)
    cid = CITY_IDS.get(requested)
    if cid is None:
        raise RuntimeError(f"Bilinmeyen hipodrom: {requested}")
    data = _get_program_for_city(target, requested, cid)
    if not data:
        raise RuntimeError(f"{format_date_tr(target)} tarihinde TJK programında {requested} için yarış bulunamadı.")
    return data


def _parse_history(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict[str, Any]] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [normalize_text(x.get_text(" ", strip=True)) for x in rows[0].find_all(["th", "td"])]
        if len(headers) < 8:
            continue
        norm = [re.sub(r"[^a-z0-9çğıöşü]", "", h.lower()) for h in headers]
        if not any("tarih" in h or "date" in h for h in norm):
            continue
        for row in rows[1:]:
            cells = [normalize_text(x.get_text(" ", strip=True)) for x in row.find_all(["td", "th"])]
            if len(cells) < min(8, len(headers)):
                continue
            raw = {headers[i]: cells[i] for i in range(min(len(headers), len(cells)))}
            def pick(*terms: str) -> str:
                for k, v in raw.items():
                    nk = re.sub(r"[^a-z0-9çğıöşü]", "", k.lower())
                    if any(t in nk for t in terms):
                        return v
                return ""
            out.append({
                "date": pick("tarih", "date"), "city": pick("hipodrom", "şehir", "sehir", "city"),
                "distance": pick("mesafe", "distance"), "surface": pick("pist", "surface"),
                "place": pick("sıra", "sira", "place", "dereceyeri"), "time": pick("derece", "time"),
                "weight": pick("kilo", "siklet", "weight"), "jockey": pick("jokey"),
                "post": pick("st", "start", "kulvar"), "odds": pick("gny", "ganyan"),
                "group": pick("grup", "şart", "sart"), "raceName": pick("koşuadı", "kosuadi", "koşu", "kosu"),
                "raceType": pick("koşutürü", "kosuturu", "type"), "trainer": pick("antrenör", "antrenor"),
                "owner": pick("sahip"), "hp": pick("hp", "handikap"), "prize": pick("ikramiye", "prize"),
                "l20": pick("son20"), "raw": raw,
            })
        if out:
            break
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
    soup = BeautifulSoup(r.text, "html.parser")
    workouts = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        hs = [normalize_text(x.get_text(" ", strip=True)) for x in rows[0].find_all(["th", "td"])]
        if not any("600" in h or "400" in h or "İdman" in h for h in hs):
            continue
        for row in rows[1:]:
            cells = [normalize_text(x.get_text(" ", strip=True)) for x in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            raw = {hs[i]: cells[i] for i in range(min(len(hs), len(cells)))}
            def pick(term: str) -> str:
                for k, v in raw.items():
                    if term.lower() in k.lower():
                        return v
                return ""
            workouts.append({"date": pick("tarih"), "m600": pick("600"), "m400": pick("400"), "m200": pick("200"), "m800": pick("800"), "raw": raw})
        if workouts:
            break
    return {"ok": True, "workouts": workouts, "workoutCount": len(workouts), "source_url": r.url}


def _parse_date_value(v: Any) -> Optional[date]:
    try:
        return datetime.fromisoformat(normalize_date(v)).date()
    except Exception:
        return None


def history_before_target(history: List[Dict[str, Any]], target_date: Any) -> List[Dict[str, Any]]:
    td = _parse_date_value(target_date)
    if not td:
        return list(history or [])
    out = []
    for row in history or []:
        d = _parse_date_value(row.get("date") if isinstance(row, dict) else None)
        if d and d < td:
            out.append(row)
    out.sort(key=lambda r: _parse_date_value(r.get("date")) or date.min, reverse=True)
    return out


def get_horse_enrichment(at_id: Any, horse_name: str = "", target_date: Any = None, timeout: int = 30) -> Dict[str, Any]:
    history, workouts, errors = [], [], []
    with ThreadPoolExecutor(max_workers=2) as ex:
        fh = ex.submit(get_horse_history, at_id, timeout) if at_id else None
        fw = ex.submit(get_horse_workouts, horse_name, timeout) if horse_name else None
        try:
            history = (fh.result() if fh else {}).get("history", []) or []
        except Exception as exc:
            errors.append(f"history: {exc}")
        try:
            workouts = (fw.result() if fw else {}).get("workouts", []) or []
        except Exception as exc:
            errors.append(f"workouts: {exc}")
    result = {
        "ok": not errors,
        "history": history_before_target(history, target_date) if target_date else history,
        "workouts": workouts,
        "history_all": history,
        "historySource": "TJK direct",
    }
    if errors:
        result["error"] = " | ".join(errors)
    return result


def enrich_race_horses(horses: List[Dict[str, Any]], target_date: Any = None, target_city: str = "", target_distance: Any = None, target_surface: str = "", target_class: str = "", progress_callback=None) -> List[Dict[str, Any]]:
    out = [dict(h) for h in horses if isinstance(h, dict)]
    total = len(out)
    with ThreadPoolExecutor(max_workers=min(6, max(1, total))) as ex:
        futures = {}
        for i, h in enumerate(out):
            at_id = h.get("atId") or h.get("at_id") or h.get("id")
            name = h.get("name") or h.get("at_ismi") or ""
            futures[ex.submit(get_horse_enrichment, at_id, name, target_date)] = i
        done = 0
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                data = fut.result()
                out[i]["_history"] = data.get("history", [])
                out[i]["_workouts"] = data.get("workouts", [])
                out[i]["_at_id"] = str(out[i].get("atId") or out[i].get("at_id") or "")
                if data.get("error"):
                    out[i]["_enrichment_error"] = data["error"]
            except Exception as exc:
                out[i]["_history"] = []
                out[i]["_workouts"] = []
                out[i]["_enrichment_error"] = str(exc)
            done += 1
            if progress_callback:
                try:
                    progress_callback(done, total, out[i].get("name", ""))
                except Exception:
                    pass
    return out


def fetch_program(date_value: Any, city: str) -> Dict[str, Any]:
    return get_program(date_value, city)


def load_program(date_value: Any, city: str) -> Dict[str, Any]:
    return get_program(date_value, city)


def worker_health() -> Dict[str, Any]:
    # Geriye dönük app uyumluluğu; artık Worker çağrısı yapılmıyor.
    return {"ok": True, "transport": "TJK direct", "source": TJK_BASE}
