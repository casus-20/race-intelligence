"""BİZİM SKOR — 20 gerçek veri ailesinden öğrenilen 0–1500 model.

- Yarıştan önce bilinebilen verilerle leakage-safe rolling örnekler üretir.
- Her veri ailesinin 1–3 sonuçlarını ayırt etme gücünü AUC ile öğrenir.
- Ağırlıkları otomatik olarak 1500 puana dağıtır.
- Eksik aileye nötr puan vermez; mevcut ağırlıklar yeniden ölçeklenir.
- Görünen bileşenlerin toplamı her at için tam olarak BİZİM SKOR'a eşittir.
"""
from __future__ import annotations
from datetime import date, datetime
import hashlib, math, re
from typing import Any, Dict, List

FAMILIES = [
    "01_kosu_sarti_uyumu", "02_pist_mesafe", "03_pist_performansi",
    "04_gercek_derece", "05_gercek_hiz", "06_guncel_form",
    "07_ortak_rakip", "08_kilo_performansi", "09_hp_kalite",
    "10_galop_performansi", "11_galop_trend", "12_dinlenme_kgs",
    "13_yaris_yogunlugu", "14_start_kulvar", "15_tempo_yaris_senaryosu",
    "16_jokey_etkisi", "17_antrenor_etkisi", "18_orijin_pedigri",
    "19_kazanc_kariyer", "20_piyasa_sinyali",
]

MIN_FAMILY_SAMPLES = 4
MIN_TOTAL_SAMPLES = 12
MIN_LEARNED_FAMILIES = 2
MIN_PRIOR_RACES = 2
_MODEL_CACHE: Dict[str, Dict[str, Any]] = {}
_MODEL_CACHE_MAX = 6


def _first(d, keys, default=None):
    if not isinstance(d, dict): return default
    for k in keys:
        v=d.get(k)
        if v not in (None, "", "-"): return v
    return default


def _num(v):
    """TJK sayısal alanlarını güvenli biçimde float'a çevirir.

    Özellikle 1.24.77 gibi derece değerlerini yanlışlıkla 1.24
    olarak okumaz; virgüllü ondalıkları ve binlik ayraçlarını destekler.
    """
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            x = float(v)
            return x if math.isfinite(x) else None
        except Exception:
            return None
    s = str(v).strip()
    if not s or s in {"-", "—", "–", "None", "nan", "NaN"}:
        return None
    # TJK derece biçimi: 1.24.77 / 0.59.43. Bu alan _time tarafından okunmalı.
    if re.fullmatch(r"\d{1,2}\.\d{2}\.\d{2}", s):
        return None
    # Ondalık virgül ve binlik nokta: 1.234,56 -> 1234.56
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+,\d+", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        x = float(m.group(0))
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _time(v):
    """TJK derece değerini saniyeye çevirir."""
    if v is None:
        return None
    s = str(v).strip().replace(",", ".")
    # 1.24.77 = 84.77 sn
    m = re.fullmatch(r"(\d{1,2})\.(\d{2})\.(\d{2})", s)
    if m:
        return float(m.group(1))*60 + float(m.group(2)) + float(m.group(3))/100
    # 1:24.77 = 84.77 sn
    m = re.fullmatch(r"(\d{1,2}):([0-9]+(?:\.[0-9]+)?)", s)
    if m:
        return float(m.group(1))*60 + float(m.group(2))
    # Zaten saniye olan 84.77 gibi değerler
    return _num(s)


def _norm(v):
    return (str(v or "").strip().lower().replace("ı","i").replace("ş","s").replace("ğ","g").replace("ü","u").replace("ö","o").replace("ç","c"))


def _surface(r):
    s=_norm(_first(r,["surface","pist","Pist","Surface","trackSurface","surfaceType","track","zemin"],""))
    if s.startswith(("k:","k-")) or s=="k" or any(x in s for x in ("kum","dirt","sand")):return "kum"
    if s.startswith(("c:","c-","cim:")) or s in ("c","cim") or any(x in s for x in ("cim","grass","turf")):return "cim"
    if s.startswith(("s:","s-")) or s=="s" or any(x in s for x in ("sentetik","synthetic","polytrack","fiber")):return "sentetik"
    return s


def _dt(v):
    if isinstance(v,datetime):return v.date()
    if isinstance(v,date):return v
    s=str(v or "").strip()
    for f in ("%d.%m.%Y","%d/%m/%Y","%Y-%m-%d","%Y/%m/%d"):
        try:return datetime.strptime(s[:10],f).date()
        except:pass
    return None


def _place(r):
    x=_num(_first(r,["place","sira","S","finish"],None)); return x if x is not None and x>0 else None

def _dist(r):return _num(_first(r,["distance","msf","mesafe"],None))
def _wt(r):return _num(_first(r,["weight","kilo","siklet","Sıklet"],None))
def _hp(r):return _num(_first(r,["hp","HP","handicap","handikap","rating","RT"],None))
def _rt(r):return _time(_first(r,["time","derece","Derece"],None))
def _class(r):return _norm(_first(r,["className","class","sinif","Sınıf","raceName","race_name","kosu","Koşu","condition"],""))
def _city(r):return _norm(_first(r,["city","şehir","sehir","hipodrom"],""))
def _name(r,keys):return _norm(_first(r,keys,""))
def _history(h):return [r for r in h.get("_history",[]) if isinstance(r,dict)] if isinstance(h.get("_history",[]),list) else []
def _workouts(h):return [r for r in h.get("_workouts",[]) if isinstance(r,dict)] if isinstance(h.get("_workouts",[]),list) else []


def _mean(xs):
    clean=[]
    for x in xs:
        try:
            y=float(x)
            if math.isfinite(y): clean.append(y)
        except Exception:
            continue
    return sum(clean)/len(clean) if clean else None


def _stats(rows):
    p=[_place(r) for r in rows];p=[x for x in p if x is not None]
    if not p:return None
    return {"sample":len(p),"wins":sum(x==1 for x in p),"top3":sum(x<=3 for x in p),"top5":sum(x<=5 for x in p),"avg":_mean(p)}


def _rate_score(rows):
    st=_stats(rows)
    if not st:return None
    avg_score=max(0.0,min(1.0,1-(st["avg"]-1)/max(8.0,st["sample"]**0.15*8)))
    return max(0.0,min(1.0,0.65*(st["top3"]/st["sample"])+0.35*avg_score))


def _percentile_better(value, values, lower=False):
    vals=[x for x in values if x is not None and math.isfinite(float(x))]
    if value is None or not vals:return None
    if len(set(vals))==1:return 1.0
    if lower:return sum(x>=value for x in vals)/len(vals)
    return sum(x<=value for x in vals)/len(vals)


def _family_values(prior,target,workouts=None,field=None):
    out={k:None for k in FAMILIES}
    if not prior:return out
    surf=_surface(target); td=_dist(target); tw=_wt(target); th=_hp(target)
    exact=[r for r in prior if surf and _surface(r)==surf and td is not None and _dist(r)==td]
    near=[r for r in prior if surf and _surface(r)==surf and td is not None and _dist(r) is not None and abs(_dist(r)-td)<=100]
    same_surf=[r for r in prior if surf and _surface(r)==surf]
    recent=prior[:6]

    # 01 koşu şartı
    tc=_class(target)
    same=[r for r in prior if tc and _class(r) and (_class(r)==tc or _class(r) in tc or tc in _class(r))]
    if len(same)>=2:out["01_kosu_sarti_uyumu"]=_rate_score(same)

    # 02 pist + mesafe
    base=exact if len(exact)>=2 else near
    if len(base)>=2:out["02_pist_mesafe"]=_rate_score(base)

    # 03 pist performansı
    if len(same_surf)>=2:out["03_pist_performansi"]=_rate_score(same_surf)

    # 04 gerçek derece
    times=[_rt(r)/(_dist(r)/1000) for r in (exact if len(exact)>=2 else same_surf) if _rt(r) is not None and _dist(r) and _dist(r)>0]
    if len(times)>=2:
        avg=_mean(times); best=min(times); worst=max(times); out["04_gercek_derece"]=max(0,min(1,1-(avg-best)/max(worst-best,0.001)))

    # 05 gerçek hız trendi
    speeds=[_rt(r)/(_dist(r)/1000) for r in same_surf if _rt(r) is not None and _dist(r) and _dist(r)>0]
    if len(speeds)>=4:
        rs=_mean(speeds[:3]); old=_mean(speeds[3:]); out["05_gercek_hiz"]=max(0,min(1,0.5+(old-rs)/max(old*0.05,0.01)))

    # 06 güncel form
    if len([_place(r) for r in recent if _place(r) is not None])>=2:out["06_guncel_form"]=_rate_score(recent)

    # 07 ortak rakip — mevcut alan içinde aynı tarih/şehir/mesafe karşılaştırması
    if field:
        own={}
        for r in prior:
            k=(str(_first(r,["date","tarih"],"")),_city(r),_dist(r));p=_place(r)
            if k[0] and k[2] is not None and p is not None:own[k]=p
        diffs=[]
        for other in field:
            if other is target:continue
            for r in _history(other):
                k=(str(_first(r,["date","tarih"],"")),_city(r),_dist(r));p=_place(r)
                if k in own and p is not None:diffs.append(p-own[k])
        if diffs:out["07_ortak_rakip"]=max(0,min(1,0.5+_mean(diffs)/10))

    # 08 kilo performansı
    if tw is not None:
        sim=[r for r in prior if _wt(r) is not None and abs(_wt(r)-tw)<=2]
        if len(sim)>=2:out["08_kilo_performansi"]=_rate_score(sim)

    # 09 HP kalite
    hps=[_hp(r) for r in prior if _hp(r) is not None]
    if th is not None and hps:out["09_hp_kalite"]=_percentile_better(th,hps,lower=False)

    # 10 galop performansı
    if workouts:
        vals=[];tdt=_dt(_first(target,["date","tarih"],None))
        for w in workouts:
            wd=_dt(_first(w,["date","tarih"],None))
            if tdt and wd and wd>tdt:continue
            xs=[_time(_first(w,[k,k.replace("m","")],None)) for k in ("m600","m400","m200")]
            x=_mean(xs)
            if x is not None:vals.append(x)
        if len(vals)>=2:
            best=min(vals);latest=vals[0];out["10_galop_performansi"]=max(0,min(1,1-max(0,latest-best)/max(best*0.15,0.01)))

    # 11 galop trend
    if workouts:
        vals=[]
        for w in workouts[:6]:
            x=_time(_first(w,["m600","600","m400","400"],None))
            if x is not None:vals.append(x)
        if len(vals)>=4:
            recent_g=_mean(vals[:2]);old_g=_mean(vals[2:]);out["11_galop_trend"]=max(0,min(1,0.5+(old_g-recent_g)/max(old_g*0.08,0.01)))

    # 12 dinlenme/KGS: geçmiş başarılı koşul aralıklarına yakınlık
    tdte=_dt(_first(target,["date","tarih"],None)); dates=sorted([_dt(_first(r,["date","tarih"],None)) for r in prior if _dt(_first(r,["date","tarih"],None))])
    if tdte and dates:
        kgs=(tdte-dates[-1]).days
        intervals=[]
        for a,b in zip(dates,dates[1:]):intervals.append((b-a).days)
        if intervals:
            c=_mean(intervals);scale=max(_mean([abs(x-c) for x in intervals]) or 7,3);out["12_dinlenme_kgs"]=math.exp(-abs(kgs-c)/scale)

    # 13 yarış yoğunluğu — orta yoğunluk / gerçek geçmiş dağılımı
    if tdte and dates:
        r30=sum(0<=(tdte-d).days<=30 for d in dates);r90=sum(0<=(tdte-d).days<=90 for d in dates)
        if r90>0:out["13_yaris_yogunlugu"]=max(0,min(1,math.exp(-abs(r30-2)/2.5)))

    # 14 start/kulvar
    post=_num(_first(target,["post","st","start","kulvar"],None))
    if post is not None:
        rows=[r for r in prior if _num(_first(r,["post","st","start","kulvar"],None))==post]
        if len(rows)>=2:out["14_start_kulvar"]=_rate_score(rows)

    # 15 tempo — yalnız gerçek pozisyon/split alanı varsa
    tempo_keys=("position","pos","tempo","split","ilk400","ilk600","ilk800")
    tr=[r for r in prior if any(r.get(k) not in (None,"") for k in tempo_keys)]
    if len(tr)>=2:out["15_tempo_yaris_senaryosu"]=_rate_score(tr)

    # 16 jokey etkisi
    tj=_name(target,["jockey","jokey","Jokey"])
    if tj:
        rows=[r for r in prior if _name(r,["jockey","jokey","Jokey"])==tj]
        if len(rows)>=2:out["16_jokey_etkisi"]=_rate_score(rows)

    # 17 antrenör etkisi
    tt=_name(target,["trainer","antrenor","antrenör","Antrenör"])
    if tt:
        rows=[r for r in prior if _name(r,["trainer","antrenor","antrenör","Antrenör"])==tt]
        if len(rows)>=2:out["17_antrenor_etkisi"]=_rate_score(rows)

    # 18 orijin — veri yoksa yok; sabit pedigree tek başına puan üretmez
    origin=_first(target,["origin","orijin","pedigree","baba_anne"],None)
    if origin:out["18_orijin_pedigri"]=None

    # 19 kazanç/kariyer — hedef öncesi birikmiş gerçek ikramiye varsa
    prizes=[_num(_first(r,["prize","ikramiye","Ikramiye","İkramiye"],None)) for r in prior]
    prizes=[x for x in prizes if x is not None and x>=0]
    if prizes:
        total=sum(prizes); peer=[sum([_num(_first(r,["prize","ikramiye","Ikramiye","İkramiye"],None)) or 0 for r in _history(h)]) for h in (field or [])]
        out["19_kazanc_kariyer"]=_percentile_better(total,peer or [total],False)

    # 20 piyasa sinyali — yalnız hedef koşu öncesi oranı mevcutsa
    odds=_num(_first(target,["odds","gny","Gny"],None))
    if odds is not None and odds>0:out["20_piyasa_sinyali"]=1/(1+math.log1p(odds))
    return out


def _auc(values,labels):
    pairs=sorted((float(v),int(y)) for v,y in zip(values,labels) if v is not None and y in (0,1) and math.isfinite(float(v)))
    if not pairs:return None
    pos=sum(y for _,y in pairs);neg=len(pairs)-pos
    if not pos or not neg:return None
    rank_sum=0.;i=0;rank=1
    while i<len(pairs):
        j=i+1
        while j<len(pairs) and pairs[j][0]==pairs[i][0]:j+=1
        avg=(rank+(rank+j-i-1))/2
        rank_sum+=avg*sum(y for _,y in pairs[i:j]);rank+=j-i;i=j
    return (rank_sum-pos*(pos+1)/2)/(pos*neg)


def _archive_samples():
    """Tamamlanmış yarış snapshot'larından gerçek sonuç etiketleri."""
    try:
        from bizim_skor_archive import completed_training_records
        records = completed_training_records()
    except Exception:
        return {k: [] for k in FAMILIES}, 0
    samples={k:[] for k in FAMILIES}; targets=0
    for rec in records:
        for h in rec.get("horses",[]):
            if not isinstance(h,dict) or h.get("finish") in (None, ""): continue
            try: label=1 if float(h.get("finish"))<=3 else 0
            except Exception: continue
            vals=h.get("family_values",{})
            if not isinstance(vals,dict): continue
            targets += 1
            for fam,v in vals.items():
                if fam in samples and v is not None:
                    try: samples[fam].append((float(v),label))
                    except Exception: pass
    return samples, targets


def _rolling_samples(horses):
    samples={k:[] for k in FAMILIES};targets=0
    for horse in horses:
        rows=_history(horse)
        if not rows:continue
        rows=sorted(rows,key=lambda r:(_dt(_first(r,["date","tarih"],None)) or date.min),reverse=True)
        for i in range(MIN_PRIOR_RACES,len(rows)):
            target=rows[i];place=_place(target)
            if place is None:continue
            prior=rows[i+1:]
            if len(prior)<MIN_PRIOR_RACES:continue
            vals=_family_values(prior,target,_workouts(horse),horses)
            label=1 if place<=3 else 0;targets+=1
            for fam,v in vals.items():
                if v is not None:samples[fam].append((v,label))
    # Arşivde doğrulanmış gerçek sonuç snapshot'larını da öğrenmeye ekle.
    archived, archived_targets = _archive_samples()
    for fam in FAMILIES:
        samples[fam].extend(archived[fam])
    targets += archived_targets
    return samples,targets


def _signature(horses):
    h=hashlib.sha1()
    for horse in horses:
        rows=_history(horse);h.update(str(len(rows)).encode())
        for r in rows:
            h.update(repr(tuple(r.get(k) for k in ("date","tarih","city","distance","surface","place","time","weight","hp","raceName","className","odds","gny"))).encode())
    # Doğrulanmış sonuç arşivi değiştiğinde öğrenilmiş model cache'i de yenilenir.
    try:
        from bizim_skor_archive import DEFAULT_PATH
        import os
        if os.path.exists(DEFAULT_PATH):
            st=os.stat(DEFAULT_PATH)
            h.update(repr((st.st_size, st.st_mtime_ns)).encode())
    except Exception:
        pass
    return h.hexdigest()


def learn_model(horses):
    key=_signature(horses)
    if key in _MODEL_CACHE:return _MODEL_CACHE[key]
    samples,target_count=_rolling_samples(horses);learned=[]
    for fam in FAMILIES:
        p=samples[fam]
        if len(p)<MIN_FAMILY_SAMPLES:continue
        auc=_auc([x[0] for x in p],[x[1] for x in p])
        if auc is None:continue
        strength=abs(auc-.5)*2*math.sqrt(len(p)/(len(p)+25))
        if strength<=0:continue
        learned.append({"family":fam,"auc":round(auc,4),"direction":1 if auc>=.5 else -1,"samples":len(p),"strength":strength})
    result={"ready":False,"sample_count":sum(x["samples"] for x in learned),"target_count":target_count,"families":learned,"weights":{},"method":"rolling_out_of_time_auc_20family"}
    if target_count>=MIN_TOTAL_SAMPLES and len(learned)>=MIN_LEARNED_FAMILIES:
        total=sum(x["strength"] for x in learned)
        if total>0:
            result["ready"]=True;result["weights"]={x["family"]:1500*x["strength"]/total for x in learned}
    _MODEL_CACHE[key]=result
    if len(_MODEL_CACHE)>_MODEL_CACHE_MAX:_MODEL_CACHE.pop(next(iter(_MODEL_CACHE)))
    return result


def _current_values(horse,race,horses):
    target={"surface":race.get("surface") or (race.get("meta") or {}).get("surface",""),"distance":race.get("distance") or (race.get("meta") or {}).get("distance"),"condition":race.get("condition") or race.get("raceName") or (race.get("meta") or {}).get("detail",""),"date":race.get("date") or race.get("tarih")}
    vals=_family_values(_history(horse),target,_workouts(horse),horses)
    th=_hp(horse);field_hp=[_hp(h) for h in horses if _hp(h) is not None]
    if vals.get("09_hp_kalite") is None and th is not None:vals["09_hp_kalite"]=_percentile_better(th,field_hp,False)
    return vals


def calculate_bizim_ranking(horses,race):
    if not isinstance(horses,list) or not horses:return []
    if not any(isinstance(h,dict) and h.get("_feature_data_ready") for h in horses):return []
    model=learn_model(horses)
    # Öğrenilmiş model hazır değilse bile gerçek özelliklerden skor üret.
    # Bu bir tahmin katsayısı değildir: tüm mevcut aileler eşit ağırlıkla
    # 1500 puana ölçeklenir. Öğrenilmiş model hazır olduğunda eski öğrenilmiş
    # ağırlıklar aynen kullanılır.
    fallback_mode = not model.get("ready")
    active_model = model
    if fallback_mode:
        active_model = dict(model)
        active_model["ready"] = True
        active_model["method"] = "real_features_equal_weight_fallback"
        active_model["weights"] = {fam: 1500.0 / len(FAMILIES) for fam in FAMILIES}
        active_model["families"] = [{"family": fam, "direction": 1, "samples": 0, "auc": None, "strength": 1.0} for fam in FAMILIES]
    results=[]
    for idx,h in enumerate(horses):
        if not isinstance(h,dict):continue
        vals=_current_values(h,race,horses);available=[]
        for fam,w in active_model["weights"].items():
            v=vals.get(fam)
            if v is None:continue
            info=next(x for x in active_model["families"] if x["family"]==fam)
            if info["direction"]<0:v=1-v
            available.append((fam,w,max(0,min(1,float(v)))))
        if len(available)<2:continue
        raw_weight=sum(w for _,w,_ in available)
        # Eksik aileleri nötr puanla doldurmuyoruz: mevcut ağırlıklar 1500'e yeniden ölçekleniyor.
        scale=1500/raw_weight
        raw_components={fam:w*scale*v for fam,w,v in available}
        components={fam:round(value,2) for fam,value in raw_components.items()}
        score=round(sum(raw_components.values()),2)
        # Görünen bileşenlerin toplamı da ekranda 1500 ölçeğinde skorla birebir aynı olsun.
        residual=round(score-sum(components.values()),2)
        if residual and components:
            anchor=max(components, key=lambda fam: raw_components[fam])
            components[anchor]=round(components[anchor]+residual,2)
        score=round(sum(components.values()),2)
        h["_bizim_skor"]=score
        h["_bizim_family_values"]=dict(components)
        results.append({"horse_index":idx,"score":score,"bizim_skor":score,"label":"BİZİM SKOR","components":components,"model":active_model})
    results.sort(key=lambda x:x["score"],reverse=True)
    for rank,item in enumerate(results,1):item["rank"]=rank
    return results
