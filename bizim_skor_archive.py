"""BİZİM SKOR eğitim arşivi ve kör test katmanı.

Yarıştan önceki snapshot'ları ve daha sonra doğrulanan sonuçları eşleştirir.
Diskte JSONL kullanır; uygulama yeniden başlatılsa bile aynı çalışma alanında
kayıtlar korunur. Sonuç yoksa eğitim yapılmaz.
"""
from __future__ import annotations
import json, os, tempfile
from datetime import date, datetime
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.environ.get("BIZIM_SKOR_ARCHIVE", os.path.join(BASE_DIR, "model_data", "bizim_skor_archive.jsonl"))


def _date(v):
    if isinstance(v, (date, datetime)): return v.isoformat()[:10]
    return str(v or "")[:10]


def race_key(race: Dict[str, Any], selected_date: Any = None, city: str = "") -> str:
    meta = race.get("meta") if isinstance(race.get("meta"), dict) else {}
    d = _date(selected_date or race.get("date") or race.get("tarih"))
    c = str(city or race.get("city") or "").strip().lower()
    n = race.get("race_number") or race.get("no") or race.get("number") or ""
    return f"{d}|{c}|{n}"


def _horse_no(h, idx):
    for k in ("no", "number", "numara", "s", "S"):
        if isinstance(h, dict) and h.get(k) not in (None, ""):
            try: return int(float(str(h[k]).replace(",", ".")))
            except Exception: pass
    return idx + 1


def snapshot_record(race: Dict[str, Any], horses: List[Dict[str, Any]], selected_date: Any = None, city: str = "") -> Dict[str, Any]:
    key = race_key(race, selected_date, city)
    rows=[]
    for i,h in enumerate(horses or []):
        if not isinstance(h, dict): continue
        rows.append({
            "no": _horse_no(h,i),
            "name": str(h.get("name") or h.get("horse") or h.get("horseName") or ""),
            "features": h.get("_feature_vector", {}),
            "family_values": h.get("_bizim_family_values", {}),
            "feature_ready": bool(h.get("_feature_data_ready")),
            "score": h.get("_bizim_skor"),
        })
    return {
        "key": key,
        "date": _date(selected_date or race.get("date") or race.get("tarih")),
        "city": city or race.get("city") or "",
        "race_number": race.get("race_number") or race.get("no") or race.get("number"),
        "race_time": race.get("race_time") or race.get("time") or "",
        "distance": race.get("distance") or (race.get("meta") or {}).get("distance"),
        "surface": race.get("surface") or (race.get("meta") or {}).get("surface"),
        "condition": race.get("condition") or race.get("raceName") or (race.get("meta") or {}).get("detail"),
        "horses": rows,
        "status": "snapshot",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def upsert_snapshot(record: Dict[str, Any], path: str = DEFAULT_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    records=load_records(path)
    record=apply_pending_results(record,path)
    records=[r for r in records if r.get("key") != record.get("key")]
    records.append(record)
    _atomic_write(records, path)


def add_result(key: str, results: Dict[int, int], path: str = DEFAULT_PATH) -> bool:
    records=load_records(path); changed=False; found=False
    for r in records:
        if r.get("key") != key: continue
        found=True
        for h in r.get("horses", []):
            try: no=int(h.get("no"))
            except Exception: continue
            if no in results:
                h["finish"] = int(results[no]); changed=True
        if changed:
            r["status"]="completed"
            r["completed_at"]=datetime.now().isoformat(timespec="seconds")
        break
    if not found:
        records.append({"key":key,"status":"result_only","results":{str(k):int(v) for k,v in results.items()},"created_at":datetime.now().isoformat(timespec="seconds")})
        changed=True
    if changed:_atomic_write(records,path)
    return changed


def apply_pending_results(record: Dict[str, Any], path: str = DEFAULT_PATH) -> Dict[str, Any]:
    """Snapshot oluşturulunca daha önce girilmiş sonuçları otomatik bağlar."""
    records=load_records(path); pending=None
    for r in records:
        if r.get("key")==record.get("key") and r.get("status")=="result_only":
            pending=r.get("results",{}); break
    if not pending:return record
    result_map={int(k):int(v) for k,v in pending.items() if str(k).isdigit()}
    for h in record.get("horses",[]):
        try:no=int(h.get("no"))
        except Exception:continue
        if no in result_map:h["finish"]=result_map[no]
    record["status"]="completed"
    record["completed_at"]=datetime.now().isoformat(timespec="seconds")
    records=[r for r in records if not (r.get("key")==record.get("key") and r.get("status")=="result_only")]
    return record


def complete_record(key: str, results_by_no: Dict[int,int], path: str = DEFAULT_PATH) -> bool:
    return add_result(key, results_by_no, path)


def extract_result_map(horses: List[Dict[str, Any]]) -> Dict[int, int]:
    """TJK program/result nesnesinde bitiriş sırası varsa otomatik çıkarır."""
    out = {}
    for i, h in enumerate(horses or []):
        if not isinstance(h, dict):
            continue
        raw = None
        for k in ("finish", "place", "sira", "S", "result", "sonuc"):
            if h.get(k) not in (None, "", "-"):
                raw = h.get(k); break
        try:
            pos = int(float(str(raw).replace(",", ".")))
        except Exception:
            continue
        if pos > 0:
            out[_horse_no(h, i)] = pos
    return out


def load_records(path: str = DEFAULT_PATH) -> List[Dict[str, Any]]:
    if not os.path.exists(path): return []
    out=[]
    with open(path,"r",encoding="utf-8") as f:
        for line in f:
            try:
                x=json.loads(line)
                if isinstance(x,dict): out.append(x)
            except Exception: pass
    return out


def completed_training_records(path: str = DEFAULT_PATH) -> List[Dict[str, Any]]:
    return [r for r in load_records(path) if r.get("status")=="completed" and any("finish" in h for h in r.get("horses",[]))]


def blind_test(path: str = DEFAULT_PATH) -> Dict[str, Any]:
    recs=completed_training_records(path)
    total=0; top1=top3=top5=0; rank_corr=[]; races=0
    for r in recs:
        scored=[h for h in r.get("horses",[]) if isinstance(h,dict) and isinstance(h.get("score"),(int,float)) and isinstance(h.get("finish"),(int,float))]
        if not scored: continue
        races += 1
        scored.sort(key=lambda h:h["score"], reverse=True)
        pred=[h.get("no") for h in scored]
        first={h.get("no") for h in scored[:1]}; top3set={h.get("no") for h in scored[:3]}; top5set={h.get("no") for h in scored[:5]}
        winners=[h.get("no") for h in scored if h.get("finish")==1]
        actual3={h.get("no") for h in scored if h.get("finish")<=3}
        actual5={h.get("no") for h in scored if h.get("finish")<=5}
        if winners and winners[0] in first: top1+=1
        if top3set & actual3: top3+=1
        if top5set & actual5: top5+=1
        total += 1
    return {"races":races,"top1":top1,"top3_hit":top3,"top5_hit":top5,
            "top1_rate":top1/races if races else None,
            "top3_rate":top3/races if races else None,
            "top5_rate":top5/races if races else None}


def _atomic_write(records, path):
    folder=os.path.dirname(path) or "."; os.makedirs(folder,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix="bizim_skor_",suffix=".tmp",dir=folder)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            for r in records: f.write(json.dumps(r,ensure_ascii=False,separators=(",",":"))+"\n")
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.remove(tmp)
