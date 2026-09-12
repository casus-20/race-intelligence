const TJK="https://www.tjk.org";
const CITY_IDS={Ankara:5,Kocaeli:9,İstanbul:3,Bursa:4,İzmir:1,Adana:2,Elazığ:6,Diyarbakır:7,Şanlıurfa:8,Antalya:10};
const CORS={"Access-Control-Allow-Origin":"*","Access-Control-Allow-Methods":"GET,OPTIONS","Access-Control-Allow-Headers":"Content-Type"};
const H={"Content-Type":"application/json; charset=utf-8",...CORS};

const YB="https://yenibeygir.com";
const YB_CITY_SLUG={"Ankara":"ankara","Kocaeli":"kocaeli","İstanbul":"istanbul","Bursa":"bursa","İzmir":"izmir","Adana":"adana","Elazığ":"elazig","Diyarbakır":"diyarbakir","Şanlıurfa":"sanliurfa","Antalya":"antalya"};
const YB_DAY_CACHE=new Map();
const YB_HORSE_CACHE=new Map();

// TJK günlük programı pahalı bir HTML parserı çalıştırdığı için aynı tarih/şehir
// isteğini Worker isolate içinde kısa süreli önbelleğe al. Bu, Streamlit
// başlangıcındaki tekrar isteklerinde CPU tüketimini ciddi biçimde azaltır.
const DAILY_CACHE=new Map();
const DAILY_CACHE_TTL=60_000;

function out(x,status=200){return new Response(JSON.stringify(x),{status,headers:H})}
function dateTR(s){const [y,m,d]=s.split("-");return `${d}/${m}/${y}`}
function escReg(s){return s.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")}
function clean(s){
  return String(s??"").replace(/<script[\s\S]*?<\/script>/gi," ")
    .replace(/<style[\s\S]*?<\/style>/gi," ")
    .replace(/<[^>]+>/g," ")
    .replace(/&amp;nbsp;/gi," ").replace(/&nbsp;/gi," ").replace(/&amp;/gi,"&").replace(/&#39;/g,"'")
    .replace(/&quot;/gi,'"').replace(/&uuml;/gi,"ü").replace(/&Uuml;/gi,"Ü")
    .replace(/&ouml;/gi,"ö").replace(/&Ouml;/gi,"Ö").replace(/&ccedil;/gi,"ç")
    .replace(/&Ccedil;/gi,"Ç").replace(/&scedil;/gi,"ş").replace(/&Scedil;/gi,"Ş")
    .replace(/&#(\d+);/g,(_,n)=>String.fromCharCode(+n)).replace(/\s+/g," ").trim()
}
function normTime(s){
  const m=String(s||"").match(/^(\d{1,2})[.:](\d{2})$/);
  return m?`${m[1].padStart(2,"0")}:${m[2]}`:String(s||"");
}
function cells(row){
  return [...row.matchAll(/<(?:td|th)\b[^>]*>([\s\S]*?)<\/(?:td|th)>/gi)].map(m=>clean(m[1]));
}
function rawCells(row){
  return [...row.matchAll(/<(?:td|th)\b[^>]*>[\s\S]*?<\/(?:td|th)>/gi)].map(m=>m[0]);
}
function attrOf(cell,name){
  const re=new RegExp('\\b'+name+'\\s*=\\s*[\"\']([^\"\']*)[\"\']','i');
  const m=String(cell||'').match(re);
  return m?clean(m[1]):'';
}
function attrDeep(cell,names){
  for(const name of names){
    const v=attrOf(cell,name);
    if(v)return v;
  }
  return '';
}
function tables(html){
  return [...html.matchAll(/<table\b[^>]*>([\s\S]*?)<\/table>/gi)].map(m=>{
    const rawRows=[...m[1].matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)].map(x=>x[0]);
    return {start:m.index,html:m[0],rawRows,rows:rawRows.map(x=>cells(x))};
  });
}
function hrefs(row){
  return [...row.matchAll(/href\s*=\s*["\']([^"\']+)["\']/gi)].map(m=>m[1].replace(/&amp;/g,"&"));
}
function extractKosuKodu(rowHtml){
  const raw=String(rowHtml||"");
  const links=hrefs(raw);
  for(const u of links){
    const m=String(u).match(/KosuKodu(?:=|%3D)(\d+)/i);
    if(m) return m[1];
  }
  const m=raw.match(/KosuKodu(?:=|%3D|[\"'\s:=]+)(\d+)/i);
  return m?m[1]:"";
}
function workoutInfoUrlFromRow(rowHtml, atId=""){
  const k=extractKosuKodu(rowHtml);
  if(!k || !atId) return "";
  return `${TJK}/TR/YarisSever/Info/idmanpisti/Kosu?Atkodu=${encodeURIComponent(atId)}&KosuKodu=${encodeURIComponent(k)}`;
}
function extractVideoUrl(rowHtml, atId=""){
  const raw=String(rowHtml||"");
  const links=hrefs(raw);
  const hit=links.find(u=>/YarisVideoAt|YarisVideo|KosuKodu/i.test(u));
  if(hit){
    return /^https?:\/\//i.test(hit) ? hit : `${TJK}${hit.startsWith("/")?"":"/"}${hit}`;
  }
  const km=raw.match(/KosuKodu(?:=|%3D|[\"'\s:=]+)(\d+)/i);
  if(km && atId){
    return `${TJK}/TR/YarisSever/Info/YarisVideoAt/At?AtKodu=${encodeURIComponent(atId)}&KosuKodu=${encodeURIComponent(km[1])}`;
  }
  return "";
}
function getAtId(rowHtml){
  const a=hrefs(rowHtml).join(" ");
  const m=a.match(/(?:QueryParameter_AtId|AtKodu|Atkodu)=(\d+)/i);
  return m?m[1]:null;
}
function isNR(name){return /koşmaz|kosmaz|çekildi|cekildi|start almaz/i.test(name||"")}

function parseKayitlarTable(html){
  const ts=tables(html); const races=[];
  for(const t of ts){
    let hi=-1;
    for(let i=0;i<t.rows.length;i++){
      if(t.rows[i].some(c=>/At İsmi|Horse Name/i.test(c))){hi=i;break}
    }
    if(hi<0)continue;
    const headers=t.rows[hi].map(x=>x.trim());
    const ix=(re)=>headers.findIndex(x=>re.test(x));
    const noI=ix(/^S$|^R$/i), nameI=ix(/At İsmi|Horse Name/i), ageI=ix(/Yaş|Age/i),
          originI=ix(/Orijin|Origin/i), weightI=ix(/Sıklet|Weight/i), ownerI=ix(/Sahip|Owner/i),
          trainerI=ix(/Antrenörü|Trainer/i), hpI=ix(/^HP$|^RT$/i), formI=ix(/Son 6|Last 6/i),
          lastI=ix(/Son Koşu Tarihi|Last Race Date/i);
    if(nameI<0)continue;
    const horses=[];
    for(let i=hi+1;i<t.rows.length;i++){
      const r=t.rows[i], raw=t.rawRows?.[i]||"";
      if(!r[nameI])continue;
      const name=clean(r[nameI]).replace(/\s+Image.*$/i,"").trim();
      if(!name || /At İsmi|Horse Name/i.test(name))continue;
      if(noI>=0 && !/^\d+$/.test((r[noI]||"").trim()))continue;
      const atId=getAtId(raw);
      horses.push({no:noI>=0?r[noI]:"",name,age:ageI>=0?r[ageI]:"",origin:originI>=0?r[originI]:"",weight:weightI>=0?r[weightI]:"",owner:ownerI>=0?r[ownerI]:"",trainer:trainerI>=0?r[trainerI]:"",hp:hpI>=0?r[hpI]:"",last6:formI>=0?r[formI]:"",lastDate:lastI>=0?r[lastI]:"",atId});
    }
    if(!horses.length)continue;
    const before=clean(html.slice(Math.max(0,t.start-9000),t.start));
    const dm=[...before.matchAll(/(\d{3,4})\s*(?:m)?\s+(Kum|Çim|Sentetik|Fiber Sand|Turf|Polytrack)/gi)];
    const last=dm.length?dm[dm.length-1]:null;
    const meta={distance:last?Number(last[1]):null,surface:last?last[2]:"",raw:before.slice(-1800)};
    races.push({no:races.length+1,time:"",meta,horses});
  }
  return races;
}

// TJK'nin Kayıtlar sayfası bazı günlerde <table> yapısını eksik/alışılmadık
// biçimde döndürebiliyor. Bu fallback doğrudan bütün <tr> satırlarını ve
// "Koşu" başlık bloklarını tarar. Böylece 200 dönen ama klasik table parser'ının
// 0 yarış verdiği sayfalarda da program çıkarılır.
function parseKayitlarRobust(html){
  const rows=[...html.matchAll(/<tr\b[^>]*>[\s\S]*?<\/tr>/gi)].map(m=>({pos:m.index,html:m[0],cells:cells(m[0])}));
  const horseRows=[];
  for(const x of rows){
    const c=x.cells; if(c.length<7)continue;
    const noIdx=c.findIndex(v=>/^\d{1,2}$/.test(String(v).trim()));
    const nameIdx=c.findIndex((v,i)=>i>noIdx && /[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9 .'-]{2,}/i.test(v) && !/^(At İsmi|Horse Name)$/i.test(v));
    if(noIdx<0||nameIdx<0)continue;
    const name=clean(c[nameIdx]).replace(/\s+Image.*$/i,"").replace(/\s+\(Koşmaz\)$/i,"").trim();
    if(!name||/^(Koşu|Ikramiye|Yetistirici|At Sahibi|S)$/i.test(name))continue;
    const raw=x.html;
    const atId=getAtId(raw);
    // TJK Kayıtlar standart kolon sırası: S, At İsmi, Yaş, Orijin, Sıklet, Sahip, Antrenörü, HP, Son 6 Y., Son Koşu Tarihi
    horseRows.push({pos:x.pos,html:raw,cells:c,no:c[noIdx],name,atId});
  }
  if(!horseRows.length)return [];

  const text=clean(html);
  const headerRe=/S\s+At İsmi\s+Yaş\s+Orijin(?:\([^)]*\))?\s+Sıklet\s+Sahip\s+Antrenörü\s+HP\s+Son 6 Y\.\s+Son Koşu Tarihi/gi;
  const headers=[...text.matchAll(headerRe)];
  const headingRe=/<(?:h[1-6]|div|span|strong|b)\b[^>]*>\s*Koşu\s*<\/(?:h[1-6]|div|span|strong|b)>/gi;
  const heads=[...html.matchAll(headingRe)].map(m=>m.index);

  // Önce başlık bloklarını kullan. Her blok, kendisinden sonraki at satırlarına aittir.
  const boundaries=heads.length?heads:[0];
  const races=[];
  for(let bi=0;bi<boundaries.length;bi++){
    const from=boundaries[bi], to=bi+1<boundaries.length?boundaries[bi+1]:Infinity;
    const hs=horseRows.filter(r=>r.pos>=from&&r.pos<to);
    if(!hs.length)continue;
    const seg=clean(html.slice(from,to===Infinity?html.length:to));
    const dm=seg.match(/(\d{3,4})\s*(?:m\s*)?(Kum|Çim|Sentetik|Fiber Sand|Turf|Polytrack)\b/i);
    const classM=seg.match(/((?:ŞARTLI|KV-?\d+|Handikap\s*\d+|Maiden)[^\n]{0,180})/i);
    const timeM=seg.match(/\b(\d{1,2})[:.](\d{2})\b/);
    const horses=hs.map(r=>{const c=r.cells;return {
      no:r.no,name:r.name,age:c[2]||"",origin:c[3]||"",weight:c[4]||"",owner:c[5]||"",trainer:c[6]||"",hp:c[7]||"",last6:c[8]||"",lastDate:c[9]||"",atId:r.atId
    }}).filter(h=>h.name);
    races.push({no:races.length+1,time:timeM?`${timeM[1].padStart(2,'0')}:${timeM[2]}`:"",meta:{distance:dm?Number(dm[1]):null,surface:dm?dm[2]:"",raceName:classM?classM[1].trim():"",raw:seg.slice(0,1800)},horses});
  }
  if(races.length)return races;

  // Son fallback: bütün atları tek program bloğunda döndür; frontend en azından
  // yarış programını ve AtId'leri kaybetmesin.
  const horses=horseRows.map(r=>{const c=r.cells;return {no:r.no,name:r.name,age:c[2]||"",origin:c[3]||"",weight:c[4]||"",owner:c[5]||"",trainer:c[6]||"",hp:c[7]||"",last6:c[8]||"",lastDate:c[9]||"",atId:r.atId};});
  return [{no:1,time:"",meta:{distance:null,surface:"",raceName:"",raw:text.slice(0,1800)},horses}];
}

function parseKayitlar(html){
  const a=parseKayitlarTable(html);
  if(a.length)return a;
  return parseKayitlarRobust(html);
}

// Günlük Yarış Programı parserı: Kayıtlar sayfasındaki geniş/deklare listesinden
// farklı olarak TJK'nın günlük programında o gün gerçekten koşacak atları alır.
function balancedTables(html){
  const re=/<\/?table\b[^>]*>/gi, stack=[], out=[]; let m;
  while((m=re.exec(html))){
    const tag=m[0];
    if(/^<table\b/i.test(tag)) stack.push({start:m.index,depth:stack.length});
    else if(stack.length){
      const x=stack.pop(); out.push({start:x.start,end:re.lastIndex,depth:x.depth,html:html.slice(x.start,re.lastIndex)});
    }
  }
  return out;
}
function classText(rowHtml, cls){
  const re=new RegExp('<[^>]*class=["\\\'][^"\\\']*'+cls+'[^"\\\']*["\\\'][^>]*>([\\s\\S]*?)<\\/[^>]+>','i');
  const m=rowHtml.match(re); return m?clean(m[1]):'';
}
function extractRaceHeaders(html){
  const out=[];
  const txt=clean(html).replace(/\s+/g,' ');
  const re=/(\d{1,2})\.\s*Koşu\s+([0-2]?\d(?:[:.]|\.)[0-5]\d)([\s\S]{0,900}?)(?=\d{1,2}\.\s*Koşu\s+[0-2]?\d(?:[:.]|\.)[0-5]\d|Forma\s+N\s+At İsmi|$)/gi;
  let m;
  while((m=re.exec(txt))){
    const no=+m[1], time=normTime(m[2]);
    let detail=String(m[3]||'').trim();
    detail=detail.replace(/^[-–—:;,]+/,'').trim();
    const stop=detail.search(/\s+(?:İkramiye|At Sahibi Primi|Yetiştiricilik Primi|Forma\s+N\s+At İsmi|N\s+At İsmi)\b/i);
    if(stop>=0) detail=detail.slice(0,stop).trim();
    const dm=detail.match(/(\d{3,4})\s*(?:m\s*)?(Kum|Çim|Sentetik|Fiber Sand|Turf|Polytrack)\b/i);
    if(dm){
      const eid=detail.match(/E\.?İ\.?D\.?\s*[:：]\s*([0-9.]+)/i);
      out.push({no,time,detail:detail.slice(0,650),distance:Number(dm[1]),surface:dm[2],eid:eid?eid[1]:''});
    } else {
      out.push({no,time,detail:detail.slice(0,650)});
    }
  }
  const seen=new Set();
  return out.filter(x=>{if(seen.has(x.no))return false;seen.add(x.no);return true;}).sort((a,b)=>a.no-b.no);
}

function cleanJockey(v){
  let x=String(v??'').replace(/\s+/g,' ').trim();
  if(!x)return '';
  x=x.replace(/\s*(?:raporlu|rapor(?:lu)? olduğundan|rapor nedeniyle|raporlu olduğundan dolayı|jokey değişikliği.*)$/i,'').trim();
  x=x.replace(/\s+raporlu.*$/i,'').trim();
  return x;
}

function parseDaily(html){
  const blocks=balancedTables(html), candidates=[];
  for(const b of blocks){
    if(!/gunluk-GunlukYarisProgrami-AtAdi/i.test(b.html))continue;
    const rs=[...b.html.matchAll(/<tr\b[^>]*>[\s\S]*?<\/tr>/gi)].map(m=>m[0]);
    let headerCells=null;
    for(const raw of rs){
      const c=cells(raw);
      if(c.some(x=>/At İsmi/i.test(x)) && c.some(x=>/^HP$/i.test(x)) && c.some(x=>/Son 6/i.test(x))){headerCells=c;break;}
    }
    if(!headerCells)continue;
    const ix=(re)=>headerCells.findIndex(x=>re.test(String(x).trim()));
    const noI=ix(/^N$|^No$|^S$/i), nameI=ix(/At İsmi|Horse Name/i), ageI=ix(/^Yaş$|^Age$/i),
      originI=ix(/Orijin|Origin/i), weightI=ix(/Sıklet|Weight/i), jockeyI=ix(/^Jokey$|^Jockey$/i),
      ownerI=ix(/^Sahip$|^Owner$/i), trainerI=ix(/Antrenör|Trainer/i), stI=ix(/^St$|^Start$/i),
      hpI=ix(/^HP$|^RT$/i), formI=ix(/Son 6|Last 6/i), kgsI=ix(/^KGS$/i), s20I=ix(/^s20$/i), bestI=ix(/En İyi D\.|Best Time/i), oddsI=ix(/^Gny$|Odds/i), agfI=ix(/^AGF$|Favorite/i), workoutI=ix(/^İdm$|^Idm$|Workout/i), lastI=ix(/Son Koşu Tarihi|Last Race Date/i);
    if(nameI<0||noI<0)continue;
    const parsed=[];
    for(const raw of rs){
      if(!/gunluk-GunlukYarisProgrami-AtAdi/i.test(raw))continue;
      const c=cells(raw); const rc=rawCells(raw); if(!c.length)continue;
      const no=(c[noI]||'').match(/^(\d{1,2})$/)?.[1]||''; if(!no)continue;
      let name=classText(raw,'gunluk-GunlukYarisProgrami-AtAdi').replace(/\s*Image.*$/i,'').trim();
      if(!name && c[nameI]) name=String(c[nameI]).replace(/\s*Image.*$/i,'').trim();
      if(!name)continue;
      parsed.push({no,name,age:(c[ageI]||'').trim(),origin:(c[originI]||'').trim(),weight:(c[weightI]||'').trim(),
        jockey:cleanJockey((c[jockeyI]||'').trim()),owner:(c[ownerI]||'').trim(),trainer:(c[trainerI]||'').trim(),
        st:(c[stI]||'').trim(),hp:(c[hpI]||'').trim(),last6:(c[formI]||'').trim(),
        lastDate:lastI>=0?(c[lastI]||'').trim():'',kgs:kgsI>=0?(c[kgsI]||'').trim():'',s20:s20I>=0?(c[s20I]||'').trim():'',bestTime:bestI>=0?((c[bestI]||'').match(/\b\d+\.\d{2}\.\d{2}\b/)||[])[0]||'':'',bestInfo:bestI>=0?(attrDeep(rc[bestI],['title','data-title','data-content','data-original-title','aria-label'])||((c[bestI]||'').replace(/^[\s\S]*?\b\d+\.\d{2}\.\d{2}\b/,'').trim())):'',bestCity:bestI>=0?attrDeep(rc[bestI],['data-city','data-hipodrom']):'',bestDate:bestI>=0?attrDeep(rc[bestI],['data-date','data-tarih']):'',bestDistance:bestI>=0?attrDeep(rc[bestI],['data-distance','data-mesafe']):'',odds:oddsI>=0?(c[oddsI]||'').trim():'',agf:agfI>=0?(c[agfI]||'').trim():'',workout:workoutI>=0?(c[workoutI]||'').trim():'',atId:getAtId(raw)});
    }
    if(parsed.length<2)continue;
    const beforeRaw=html.slice(Math.max(0,b.start-35000),b.start);
    const before=clean(beforeRaw).replace(/\s+/g,' ');
    const markerRe=/(\d{1,2}\.\s*Koşu)\s+([0-2]?\d(?:[:.]|\.)[0-5]\d)/gi;
    const matches=[...before.matchAll(markerRe)];
    const head=matches.length?matches[matches.length-1]:null;
    const time=head?normTime(head[2]):'';
    let raceHeader='';
    if(head){
      const tail=before.slice(head.index+head[0].length);
      const stop=tail.search(/\s+(?:İkramiye|At Sahibi Primi|Yetiştiricilik Primi|N\s+At İsmi|Forma\s+N\s+At İsmi)/i);
      raceHeader=tail.slice(0,stop>=0?stop:1800);
    }
    raceHeader=clean(raceHeader).replace(/\s+/g,' ').replace(/^[,;:\-]+|[,;:\-]+$/g,'').trim();
    const dm=[...raceHeader.matchAll(/(\d{3,4})\s*(?:m)?\s*(Kum|Çim|Sentetik|Fiber Sand|Turf|Polytrack)\b/gi)];
    const last=dm.length?dm[dm.length-1]:null;
    const surface=last?last[2]:'';
    const distance=last?Number(last[1]):null;
    const eid=raceHeader.match(/E\.?İ\.?D\.?\s*[:：]\s*([0-9.]+)/i);
    const raceName=raceHeader;
    candidates.push({start:b.start,depth:b.depth,horses:parsed,meta:{distance,surface,raceName,detail:raceHeader,eid:eid?eid[1]:'',raw:before.slice(-5000)},time,name:raceName});
  }
  const usable=candidates.filter(c=>c.horses.length>=2&&c.horses.length<=35);
  const maxDepth=usable.length?Math.max(...usable.map(c=>c.depth)):0;
  const pool=(usable.filter(c=>c.depth===maxDepth).length?usable.filter(c=>c.depth===maxDepth):usable).sort((a,b)=>a.start-b.start);
  const headerList=extractRaceHeaders(html);
  const races=[];
  for(const c of pool){
    const sig=c.horses.map(h=>normName(h.name)).join('|');
    if(!sig||races.some(r=>r._sig===sig))continue;
    races.push({...c,_sig:sig});
  }
  return races.sort((a,b)=>a.start-b.start).map((r,i)=>{
    const hh=headerList[i]||{detail:"",time:""};
    const detail=hh.detail||r.meta?.detail||r.meta?.raceName||'';
    const dm=detail.match(/(\d{3,4})\s*(?:m\s*)?(Kum|Çim|Sentetik|Fiber Sand|Turf|Polytrack)\b/i);
    const eid=detail.match(/E\.?İ\.?D\.?\s*[:：]\s*([0-9.]+)/i);
    const meta={...r.meta,detail,raceName:detail,time:hh.time||r.time||'',distance:dm?Number(dm[1]):(r.meta?.distance||null),surface:dm?dm[2]:(r.meta?.surface||''),eid:eid?eid[1]:(r.meta?.eid||'')};
    return {no:i+1,time:meta.time,name:detail||r.name||`Koşu ${i+1}`,meta,horses:r.horses};
  });
}


function normalizeHistorySurface(v){
  let t=clean(v||'').replace(/\s+/g,' ').trim();
  if(!t) return '';
  // TJK can render the Pist cell as text, as an image/badge title, or as
  // separated DOM pieces such as "K" + "Normal". Normalize all of these
  // representations to the original TJK-style value without inventing it.
  const direct=t.match(/\b(K|Ç|S)\s*[:\-]?\s*(Normal|Nemli|Ağır|Yumuşak|Çok\s+Yumuşak|Islak|Kum|Çim|Sentetik)\b/i);
  if(direct) return `${direct[1].toUpperCase()}:${direct[2]}`;
  const compact=t.replace(/[\s|/\\>_<]+/g,' ').trim();
  const compactM=compact.match(/\b(K|Ç|S)\s+(Normal|Nemli|Ağır|Yumuşak|Çok\s+Yumuşak|Islak|Kum|Çim|Sentetik)\b/i);
  if(compactM) return `${compactM[1].toUpperCase()}:${compactM[2]}`;
  if(/^(Kum)$/i.test(t)) return 'Kum';
  if(/^(Çim)$/i.test(t)) return 'Çim';
  if(/^(Sentetik)$/i.test(t)) return 'Sentetik';
  if(/^(Fiber\s+Sand|Turf|Polytrack)$/i.test(t)) return t;
  return '';
}
function extractSurfaceValue(raw){
  const direct=normalizeHistorySurface(raw); if(direct)return direct;
  const source=String(raw||'');
  const attrs=[...source.matchAll(/(?:title|alt|data-pist|data-surface|data-value|value|class|src|id)\s*=\s*["']([^"']+)["']/gi)].map(m=>m[1]);
  for(const a of attrs){
    const got=normalizeHistorySurface(a); if(got)return got;
    const z=String(a).replace(/[_\-\/]+/g,' ').trim();
    if(/\b(?:K|Kum)\b/i.test(z)&&/\b(?:Normal|Nemli|Ağır|Yumuşak|Kum)\b/i.test(z))return `K:${(z.match(/Normal|Nemli|Ağır|Yumuşak|Kum/i)||['Kum'])[0]}`;
    if(/\b(?:Ç|Cim|Çim)\b/i.test(z)&&/\b(?:Normal|Ağır|Yumuşak|Çim|Cim)\b/i.test(z))return `Ç:${(z.match(/Normal|Ağır|Yumuşak|Çim|Cim/i)||['Çim'])[0].replace(/^Cim$/i,'Çim')}`;
    if(/\b(?:S|Sentetik)\b/i.test(z)&&/\b(?:Normal|Sentetik)\b/i.test(z))return `S:${(z.match(/Normal|Sentetik/i)||['Sentetik'])[0]}`;
  }
  // TJK sometimes stores the Pist as an icon/background asset where the
  // human-readable value is only encoded in class/src/id names (e.g. kum, cim,
  // normal). Read that upstream marker rather than inventing a value.
  const marker=String(source).replace(/[_.\-\/\\]+/g,' ').replace(/%20/gi,' ').replace(/\s+/g,' ').trim();
  if(/(?:pist|track|surface|zemin|kum|sand)/i.test(marker) && /(?:kum|sand)/i.test(marker)) return 'Kum';
  if(/(?:pist|track|surface|zemin|cim|çim|turf)/i.test(marker) && /(?:cim|çim|turf)/i.test(marker)) return 'Çim';
  if(/(?:pist|track|surface|zemin|sentetik|synthetic|polytrack)/i.test(marker) && /(?:sentetik|synthetic|polytrack)/i.test(marker)) return 'Sentetik';
  const m=clean(source).match(/\b(K|Ç|S)\s*[:\-]?\s*(Normal|Nemli|Ağır|Yumuşak|Çok\s+Yumuşak|Islak|Kum|Çim|Sentetik)\b/i);
  if(m)return `${m[1].toUpperCase()}:${m[2]}`;
  const plain=clean(source).match(/\b(Kum|Çim|Sentetik|Fiber\s+Sand|Turf|Polytrack)\b/i);
  return plain?plain[1]:'';
}

function parseExactTjkHistoryRows(html){
  const rows=[...String(html||"").matchAll(/<tr\b[^>]*>[\s\S]*?<\/tr>/gi)];
  const dateRe=/^\d{2}[./]\d{2}[./]\d{4}$/;
  const timeRe=/^\d{1,2}\.\d{2}\.\d{2}$/;
  const distRe=/^\d{3,4}$/;
  const out=[];
  const n=v=>String(v||"").replace(/\u00a0/g," ").replace(/\s+/g," ").trim();
  for(const m of rows){
    const raw=m[0], c=cells(raw).map(n), rc=rawCells(raw);
    // V44: Pist icon/class/source bilgisi de doğrudan 4. hücreden okunur.
    if(c.length<19) continue;
    if(!dateRe.test(c[0]) || !distRe.test(c[2]) || !timeRe.test(c[5])) continue;
    // Pist is the 4th official TJK history column. Read the exact cell first,
    // then raw cell attributes/HTML, then the whole row. Never infer it.
    // V50: V46'nın tüm alan eşleşmelerini aynen koru. Sadece Pist boşsa,
    // resmi TJK başlık satırından gerçek Pist sütununu bulup aynı satırdan oku.
    let surface=normalizeHistorySurface(c[3])||extractSurfaceValue(rc[3])||extractSurfaceValue(raw);
    if(!surface && rc[3]) surface=extractSurfaceValue(rc[3]);
    if(!surface){
      const whole=n(clean(raw));
      const sm=whole.match(/\b(?:K|Ç|S)\s*[:\-]?\s*(?:Normal|Nemli|Ağır|Yumuşak|Çok\s+Yumuşak|Islak|Kum|Çim|Sentetik)(?:\s*[0-9]+(?:[.,][0-9]+)?)?|\b(?:Kum|Çim|Sentetik|Fiber\s+Sand|Turf|Polytrack)\b/i);
      if(sm) surface=normalizeHistorySurface(sm[0])||sm[0].trim();
    }
    if(!surface){
      // TJK bazı sürümlerde Pist bilgisini hücre metni yerine ikon/badge
      // attribute'u ile verir. Başlıkta Pist sütununu tespit edip o index'i
      // kullan; diğer hiçbir alanın indexini değiştirme.
      const rowHtml=String(raw||'');
      const allRows=[...String(html||'').matchAll(/<tr\b[^>]*>[\s\S]*?<\/tr>/gi)];
      let surfaceIndex=-1;
      for(const hr of allRows){
        const hc=cells(hr[0]).map(n);
        if(hc.some(v=>/^Pist$|^Surface$/i.test(v))){
          surfaceIndex=hc.findIndex(v=>/^Pist$|^Surface$/i.test(v));
          if(surfaceIndex>=0) break;
        }
      }
      if(surfaceIndex>=0){
        const rr=cells(rowHtml).map(n), rrc=rawCells(rowHtml);
        surface=normalizeHistorySurface(rr[surfaceIndex])||extractSurfaceValue(rrc[surfaceIndex])||'';
      }
    }
    out.push({
      date:c[0], city:c[1], distance:c[2], surface, place:c[4], time:c[5],
      weight:c[6], equipment:c[7], jockey:c[8], post:c[9], odds:c[10],
      group:c[11], raceName:c[12], className:c[13], trainer:c[14], owner:c[15],
      hp:c[16], prize:c[17], s20:c[18], videoUrl:extractVideoUrl(raw,q.get("atId")||""), kosuKodu:extractKosuKodu(raw), workoutInfoUrl:workoutInfoUrlFromRow(raw,q.get("atId")||"")
    });
  }
  const seen=new Set();
  return out.filter(x=>{const k=[x.date,x.city,x.distance,x.time,x.place].join("|");if(seen.has(k))return false;seen.add(k);return true;})
    .sort((a,b)=>parseDmyForWorker(b.date)-parseDmyForWorker(a.date));
}

function enrichHistorySurfaceFromText(html, arr){
  const txt=normForHistory(clean(html||''));
  if(!txt || !Array.isArray(arr)) return arr||[];
  const surf=String.raw`(?:(?:K|Ç|S)\s*[:\-]?\s*(?:Normal|Nemli|Ağır|Yumuşak|Çok\s+Yumuşak|Islak|Kum|Çim|Sentetik)(?:\s*[0-9]+(?:[.,][0-9]+)?)?|Kum|Çim|Sentetik|Fiber\s+Sand|Turf|Polytrack)`;
  const cities=`Ankara|Bursa|Kocaeli|İstanbul|İzmir|Adana|Elazığ|Diyarbakır|Şanlıurfa|Antalya`;
  return arr.map(x=>{
    if(String(x.surface||'').trim()) return x;
    const d=String(x.date||'').replace(/[.\/]/g,'[./]');
    const rg=new RegExp(d+`\\s+(${cities})\\s+(${String(x.distance||'').replace(/[-/\\^$*+?.()|[\]{}]/g,'\\$&')})\\s+(${surf})\\s+\\d{1,2}\\s+\\d{1,2}\\.\\d{2}\\.\\d{2}`,'i');
    const m=txt.match(rg);
    return m?{...x,surface:normalizeHistorySurface(m[3])||m[3].trim()}:x;
  });
}
function normForHistory(s){return String(s||'').replace(/\u00a0/g,' ').replace(/\s+/g,' ').trim()}

function parseHistory(html){
  const exact=enrichHistorySurfaceFromText(html,parseExactTjkHistoryRows(html)).map(x=>({...x,surface:normalizeHistorySurface(x.surface)||x.surface}));
  if(exact.length) return exact.slice(0,1000);
  const rows=[...String(html||'').matchAll(/<tr\b[^>]*>[\s\S]*?<\/tr>/gi)]
    .map(m=>({raw:m[0],c:cells(m[0])}));
  const dateRe=/^\d{2}[./]\d{2}[./]\d{4}$/;
  const timeRe=/^\d{1,2}\.\d{2}\.\d{2}$/;
  const distRe=/^\d{3,4}$/;
  const surfaceRe=/^(?:K:Normal|K:Kum|Ç:Normal|Ç:Çim|S:Normal|S:Sentetik|Kum|Çim|Sentetik|Fiber Sand|Turf|Polytrack)/i;
  const cityRe=/^(?:Ankara|İstanbul|Kocaeli|Bursa|İzmir|Adana|Elazığ|Diyarbakır|Şanlıurfa|Antalya)$/i;
  const out=[];
  const norm=v=>String(v||'').replace(/\u00a0/g,' ').replace(/\s+/g,' ').trim();
  const key=v=>norm(v).toLocaleLowerCase('tr-TR').replace(/[^a-z0-9çğıöşü]/gi,'');
  const findHeaderIndex=(h,tests)=>{
    for(let i=0;i<h.length;i++){
      const k=key(h[i]);
      if(tests.some(t=>k===t || k.includes(t))) return i;
    }
    return -1;
  };

  // TJK resmi geçmiş koşu tablosunun standart sırası:
  // Tarih | Şehir | Msf | Pist | S | Derece | Sıklet | Takı | Jokey | St |
  // Gny | Grup | K. No-K. Adı | Kcins | Ant. | Sahip | HP | Ikramiye | S20
  const positional={
    date:0, city:1, distance:2, surface:3, place:4, time:5, weight:6,
    equipment:7, jockey:8, post:9, odds:10, group:11, race:12,
    className:13, trainer:14, owner:15, hp:16, prize:17, s20:18
  };

  // 1) Header-aware parser. Match the official header loosely, then use both
  // header positions and the known TJK positional layout as fallbacks.
  for(let hi=0;hi<rows.length;hi++){
    const h=rows[hi].c||[];
    const hk=h.map(key);
    const hasDate=hk.some(x=>x==='tarih'||x.includes('tarih'));
    const hasCity=hk.some(x=>x==='şehir'||x==='sehir'||x.includes('şehir')||x.includes('sehir'));
    const hasDist=hk.some(x=>x==='msf'||x==='mesafe'||x.includes('msf'));
    const hasTime=hk.some(x=>x==='derece'||x.includes('derece'));
    if(!hasDate||!hasCity||!hasDist||!hasTime) continue;

    const I={
      date:findHeaderIndex(h,['tarih','date']),
      city:findHeaderIndex(h,['şehir','sehir','city']),
      distance:findHeaderIndex(h,['msf','mesafe','distance']),
      surface:findHeaderIndex(h,['pist','track']),
      place:findHeaderIndex(h,['s','sıra','sira','place']),
      time:findHeaderIndex(h,['derece','finishtime']),
      weight:findHeaderIndex(h,['sıklet','siklet','weight']),
      equipment:findHeaderIndex(h,['takı','taki','equipment']),
      jockey:findHeaderIndex(h,['jokey','jockey']),
      post:findHeaderIndex(h,['st','start']),
      odds:findHeaderIndex(h,['gny','win']),
      group:findHeaderIndex(h,['grup','group']),
      race:findHeaderIndex(h,['kno-kadı','kno-kadi','kosuno-kosoadı','kosunokosoadi','racename','koşuadı','kosuadi']),
      className:findHeaderIndex(h,['kcins','race type']),
      trainer:findHeaderIndex(h,['ant','antrenör','antrenor','trainer']),
      owner:findHeaderIndex(h,['sahip','owner']),
      hp:findHeaderIndex(h,['hp','rt']),
      prize:findHeaderIndex(h,['ikramiye','prize']),
      s20:findHeaderIndex(h,['s20','l20'])
    };

    const get=(r,k)=>{
      const i=I[k]>=0?I[k]:positional[k];
      return i>=0&&i<r.length?norm(r[i]):'';
    };

    for(let ri=hi+1;ri<rows.length;ri++){
      const r=rows[ri].c||[];
      if(r.length<6) continue;
      const date=get(r,'date') || r.find(c=>dateRe.test(norm(c))) || '';
      const distance=get(r,'distance') || r.find(c=>distRe.test(norm(c)) && Number(c)>=1000 && Number(c)<=5000) || '';
      const time=get(r,'time') || r.find(c=>timeRe.test(norm(c))) || '';
      if(!dateRe.test(norm(date)) || !distRe.test(norm(distance)) || !timeRe.test(norm(time))) continue;

      const city=get(r,'city') || r.find(c=>cityRe.test(norm(c))) || '';
      const surface=normalizeHistorySurface(get(r,'surface')) || r.map(norm).map(normalizeHistorySurface).find(Boolean) || extractSurfaceValue((rows[ri]&&rows[ri].raw)||'') || '';
      const place=get(r,'place');
      const weight=get(r,'weight');
      const jockey=get(r,'jockey');
      const raceName=get(r,'race') || get(r,'className') || get(r,'group');
      const hp=get(r,'hp');

      out.push({
        date:norm(date), city:norm(city), distance:norm(distance), surface:norm(surface),
        place:norm(place), time:norm(time), weight:norm(weight),
        equipment:get(r,'equipment'), jockey:norm(jockey), post:get(r,'post'),
        odds:get(r,'odds'), group:get(r,'group'), raceName:norm(raceName),
        className:get(r,'className'), trainer:get(r,'trainer'), owner:get(r,'owner'),
        hp:norm(hp), prize:get(r,'prize'), s20:get(r,'s20'), videoUrl:extractVideoUrl(rows[ri]&&rows[ri].raw, ''), kosuKodu:extractKosuKodu(rows[ri]&&rows[ri].raw), workoutInfoUrl:workoutInfoUrlFromRow(rows[ri]&&rows[ri].raw, '')
      });
    }
    if(out.length) break;
  }

  // 2) Row-independent parser with positional fallbacks.
  if(!out.length){
    for(const z of rows){
      const c=(z.c||[]).map(norm);
      if(c.length<6) continue;
      const date=c.find(x=>dateRe.test(x))||'';
      const time=c.find(x=>timeRe.test(x))||'';
      const distance=c.find(x=>distRe.test(x) && Number(x)>=1000 && Number(x)<=5000)||'';
      if(!date||!time||!distance) continue;
      const ti=c.indexOf(time), di=c.indexOf(distance);
      const city=c.find(x=>cityRe.test(x))||'';
      const surface=c.map(normalizeHistorySurface).find(Boolean) || extractSurfaceValue(z.raw) || '';
      let place=(c[4]&&/^\d{1,2}$/.test(c[4]))?c[4]:'';
      if(!place){
        const nums=c.filter(x=>/^\d{1,2}$/.test(x)&&Number(x)<=30);
        place=nums[0]||'';
      }
      const weight=c.find(x=>/^\d{2}(?:[,.]\d)?$/.test(x)&&Number(x)>=40&&Number(x)<=80)||'';
      const jockey=c[8]||'';
      const raceName=c[12]||c[13]||'';
      const hp=c[16]||'';
      out.push({
        date,city,distance,surface,place,time,weight,equipment:c[7]||'',jockey,
        post:c[9]||'',odds:c[10]||'',group:c[11]||'',raceName,
        className:c[13]||'',trainer:c[14]||'',owner:c[15]||'',hp,s20:c[18]||'',videoUrl:extractVideoUrl(z.raw,''), kosuKodu:extractKosuKodu(z.raw), workoutInfoUrl:workoutInfoUrlFromRow(z.raw,'')
      });
    }
  }

  // 3) Last-resort text scan. Only real upstream values are accepted.
  if(!out.length){
    const txt=norm(clean(html));
    const re=/(\d{2}[./]\d{2}[./]\d{4})\s+([^\s]+)\s+(\d{3,4})\s+((?:K|Ç|S)\s*[:\-]?\s*(?:Normal|Nemli|Ağır|Yumuşak|Çok\s+Yumuşak|Islak|Kum|Çim|Sentetik)(?:\s+[0-9]+(?:[.,][0-9]+)?)?|Kum|Çim|Sentetik|Fiber\s+Sand|Turf|Polytrack)\s+(\d{1,2})\s+(\d{1,2}\.\d{2}\.\d{2})\s+(\d{2}(?:[,.]\d)?)/gi;
    let m;
    while((m=re.exec(txt))){
      const city=m[2], surface=m[4];
      if(!cityRe.test(city)&&!/^[A-Za-zÇĞİÖŞÜçğıöşü-]+$/.test(city)) continue;
      out.push({date:m[1],city,distance:m[3],surface,place:m[5],time:m[6],weight:m[7],
        equipment:'',jockey:'',post:'',odds:'',group:'',raceName:'',className:'',
        trainer:'',owner:'',hp:'',prize:'',s20:'',videoUrl:''});
    }
  }

  const seen=new Set();
  return out.filter(x=>{
    const k=[x.date,x.city,x.distance,x.time,x.place].join('|');
    if(seen.has(k)) return false;
    seen.add(k); return true;
  }).sort((a,b)=>parseDmyForWorker(b.date)-parseDmyForWorker(a.date)).slice(0,1000);
}

// =========================================================
// SINIF / KALITE MODULU V1 - SERVER
// Skor puanina dahil DEGILDIR. Gercek TJK gecmisinden hesaplanir.
// =========================================================
const CLASS_BASE={G1:100,G2:90,G3:80,A3:80,KV8:70,KV9:70,KV6:60,KV7:60,S5:50,H21:50,S4:40,H16:40,S3:30,H15:30,S2:20,H14:20,MAIDEN:10,S1:10};
const CLASS_W=[.35,.25,.20,.10,.10];
function classNorm(v){return String(v??'').toLocaleUpperCase('tr-TR').trim().replace(/İ/g,'I').replace(/Ş/g,'S').replace(/Ğ/g,'G').replace(/Ü/g,'U').replace(/Ö/g,'O').replace(/Ç/g,'C').replace(/[^A-Z0-9]/g,'')}
function classCode(v){const s=classNorm(v);if(!s)return null;if(/GRUP1|G1/.test(s))return'G1';if(/GRUP2|G2/.test(s))return'G2';if(/GRUP3|G3/.test(s))return'G3';if(/A3|ACIK3/.test(s))return'A3';if(/KV-?9|KV9/.test(s))return'KV9';if(/KV-?8|KV8/.test(s))return'KV8';if(/KV-?7|KV7/.test(s))return'KV7';if(/KV-?6|KV6/.test(s))return'KV6';if(/HANDIKAP21|H21/.test(s))return'H21';if(/HANDIKAP16|H16/.test(s))return'H16';if(/HANDIKAP15|H15/.test(s))return'H15';if(/HANDIKAP14|H14/.test(s))return'H14';if(/SARTLI5|S5/.test(s))return'S5';if(/SARTLI4|S4/.test(s))return'S4';if(/SARTLI3|S3/.test(s))return'S3';if(/SARTLI2|S2/.test(s))return'S2';if(/SARTLI1|S1/.test(s))return'S1';if(/MAIDEN|MAID/.test(s))return'MAIDEN';return null;}
function classSource(x){return x?.className||x?.raceClass||x?.raceType||x?.kcins||x?.raceName||x?.race||x?.group||''}
function classOne(x){const code=classCode(classSource(x));const base=code?CLASS_BASE[code]:null;const m=String(x?.place??'').match(/\d+/);const pos=m?Number(m[0]):null;if(base==null||pos==null||pos<1)return null;const factor=pos===1?1:pos===2?.8:pos===3?.65:pos===4?.5:.2;return{date:x.date||'',code,base,position:pos,factor,score:Number((base*factor).toFixed(2))};}
function classHistory(hist,targetDate=''){const ref=targetDate?new Date(targetDate+'T00:00:00').getTime():Infinity;return(Array.isArray(hist)?hist:[]).filter(x=>{const t=parseDmyForWorker(x.date);return t>0&&t<ref}).sort((a,b)=>parseDmyForWorker(b.date)-parseDmyForWorker(a.date));}
function classAnalysis(hist,todayClass='',targetDate=''){const rows=classHistory(hist,targetDate).map(classOne).filter(Boolean);const all=rows.length?Number((rows.reduce((a,x)=>a+x.score,0)/rows.length).toFixed(2)):null;const recent=rows.slice(0,5);let weighted=null,ws=0;if(recent.length){weighted=recent.reduce((a,x,i)=>a+x.score*CLASS_W[i],0);ws=recent.reduce((a,x,i)=>a+CLASS_W[i],0);weighted=Number((weighted/ws).toFixed(2));}const hi=rows.length?rows.reduce((a,x)=>x.base>a.base?x:a,rows[0]):null;const today=classCode(todayClass),todayBase=today?CLASS_BASE[today]:null;const advantage=weighted!=null&&todayBase!=null?Number((weighted-todayBase).toFixed(2)):null;const drop=hi&&todayBase!=null?hi.base-todayBase:null;return{classQuality:all,currentClass:weighted,todayClass:today,todayBase,advantage,highestClass:hi?.code||null,highestBase:hi?.base??null,classDrop:drop!=null&&drop>=10,dropDifference:drop,validRaceCount:rows.length,recentRaceCount:recent.length,races:recent};}
function attachClassScores(hist){return(Array.isArray(hist)?hist:[]).map(x=>{const c=classOne(x);return c?{...x,classCode:c.code,classBasePoint:c.base,classFinishMultiplier:c.factor,classScore:c.score}:x;});}

function parseDmyForWorker(s){const m=String(s||'').match(/(\d{2})\.(\d{2})\.(\d{4})/);return m?new Date(`${m[3]}-${m[2]}-${m[1]}T00:00:00`).getTime():0}

function workoutTrackFromRaw(raw, cellsArr){
  const cities=['Ankara','Bursa','Kocaeli','İstanbul','İzmir','Adana','Elazığ','Diyarbakır','Şanlıurfa','Antalya'];
  const c=(cellsArr||[]).map(x=>String(x||'').trim());
  const direct=c.find(x=>cities.some(city=>new RegExp('^'+escReg(city)+'$','i').test(x)));
  if(direct) return direct;
  const rawText=String(raw||'');
  const attrMatches=[...rawText.matchAll(/(?:title|alt|value|data-hipodrom|data-track|data-city|data-value)=\s*["']([^"']+)["']/gi)].map(m=>clean(m[1]));
  for(const v of attrMatches){ const hit=cities.find(city=>new RegExp('^'+escReg(city)+'$','i').test(v)||new RegExp('\\b'+escReg(city)+'\\b','i').test(v)); if(hit)return hit; }
  const txt=clean(rawText);
  const m=txt.match(new RegExp('\\b('+cities.map(escReg).join('|')+')\\b','i'));
  return m?m[1]:'';
}
function parseWorkouts(html){
  const rows=[...String(html||'').matchAll(/<tr\b[^>]*>[\s\S]*?<\/tr>/gi)].map(m=>({raw:m[0],c:cells(m[0])}));
  const dateRe=/^\d{2}[./]\d{2}[./]\d{4}$/;
  const wtRe=/^\d{1,2}[.,]\d{2}$/;
  const out=[];
  const norm=v=>String(v||'').replace(/\u00a0/g,' ').replace(/\s+/g,' ').trim().replace(',','.');
  const idxRe=(h,re)=>h.findIndex(x=>re.test(norm(x)));
  const headerScore=h=>{let s=0;for(const re of [/At\s*No/i,/At\s*(?:Adı|İsmi|Adi|Ismi)/i,/2200(?:\s*m)?$/i,/1200(?:\s*m)?$/i,/1000(?:\s*m)?$/i,/800(?:\s*m)?$/i,/400(?:\s*m)?$/i,/İ\.?\s*Tarihi/i,/^Pist$/i,/İdman\s*Hipodromu|İ\.?\s*Hip\.?/i])if(h.some(x=>re.test(norm(x))))s++;return s;};
  for(let hi=0;hi<rows.length;hi++){
    const h=rows[hi].c||[]; if(headerScore(h)<6) continue;
    const I={horse:idxRe(h,/At\s*(?:Adı|İsmi|Adi|Ismi)|Horse/i),m2200:idxRe(h,/^2200(?:\s*m)?$/i),m2000:idxRe(h,/^2000(?:\s*m)?$/i),m1800:idxRe(h,/^1800(?:\s*m)?$/i),m1600:idxRe(h,/^1600(?:\s*m)?$/i),m1400:idxRe(h,/^1400(?:\s*m)?$/i),m1200:idxRe(h,/^1200(?:\s*m)?$/i),m1000:idxRe(h,/^1000(?:\s*m)?$/i),m800:idxRe(h,/^800(?:\s*m)?$/i),m600:idxRe(h,/^600(?:\s*m)?$/i),m400:idxRe(h,/^400(?:\s*m)?$/i),m200:idxRe(h,/^200(?:\s*m)?$/i),date:idxRe(h,/İ\.?\s*Tarihi|Tarih|Date/i),surface:idxRe(h,/^Pist$|Surface/i),type:idxRe(h,/İ\.?\s*Türü|Tür|Type/i),track:idxRe(h,/İdman\s*Hipodromu|İ\.?\s*Hip\.?|Hipodrom|Track/i),status:idxRe(h,/Durum|Status/i)};
    for(let ri=hi+1;ri<rows.length;ri++){
      const row=rows[ri], r=row.c||[]; if(!r.length) continue;
      const get=k=>I[k]>=0?norm(r[I[k]]):'';
      const date=get('date')||r.find(x=>dateRe.test(norm(x)))||''; if(!dateRe.test(date)) continue;
      const vals=['m2200','m2000','m1800','m1600','m1400','m1200','m1000','m800','m600','m400','m200'].map(k=>get(k));
      if(!vals.some(Boolean)) continue;
      let track=get('track')||workoutTrackFromRaw(row.raw,r);
      let surface=get('surface')||extractSurfaceValue(row.raw);
      let type=get('type');
      if(!type){const tm=clean(row.raw).match(/\b(Sprint|Galop|Kenter|İdman|Sprint Galop)\b/i);if(tm)type=tm[1];}
      out.push({horse:get('horse'),m2200:get('m2200'),m2000:get('m2000'),m1800:get('m1800'),m1600:get('m1600'),m1400:get('m1400'),m1200:get('m1200'),m1000:get('m1000'),m800:get('m800'),m600:get('m600'),m400:get('m400'),m200:get('m200'),status:get('status'),date,surface,type,track,jockey:'',videoUrl:extractVideoUrl(row.raw,'')});
    }
    if(out.length) return dedupeWorkouts(out);
  }
  for(const z of rows){
    const c=(z.c||[]).map(norm); if(c.length<5) continue;
    const date=c.find(x=>dateRe.test(x))||''; if(!date) continue;
    const nums=c.filter(x=>wtRe.test(x)); if(!nums.length) continue;
    const surface=c.find(x=>/^(?:K:Normal|K:Kum|Ç:Normal|Ç:Çim|S:Normal|S:Sentetik|Kum|Çim|Sentetik|Fiber Sand|Turf|Polytrack)/i.test(x))||extractSurfaceValue(z.raw);
    const track=workoutTrackFromRaw(z.raw,c);
    const times=nums.map(x=>x.replace(',','.')); const fast=times.find(x=>Number(x)<30)||''; const mid=times.find(x=>Number(x)>=30&&Number(x)<70)||'';
    out.push({horse:'',m2200:'',m2000:'',m1800:'',m1600:'',m1400:'',m1200:'',m1000:'',m800:mid,m600:'',m400:fast,m200:'',status:'',date,surface,type:'',track,jockey:'',videoUrl:extractVideoUrl(z.raw,'')});
  }
  if(!out.length){
    const txt=norm(clean(html)); const dateBlock=/(\d{2}[./]\d{2}[./]\d{4})([\s\S]{0,650}?)(?=\d{2}[./]\d{2}[./]\d{4}|$)/g; let m;
    while((m=dateBlock.exec(txt))){const vals=[...m[2].matchAll(/\b(\d{1,2}[.,]\d{2})\b/g)].map(x=>x[1].replace(',','.'));if(!vals.length)continue;const fast=vals.find(x=>Number(x)<30)||'',mid=vals.find(x=>Number(x)>=30&&Number(x)<70)||'';const surface=(m[2].match(/\b(Kum|Çim|Sentetik|Fiber Sand|Turf|Polytrack)\b/i)||[])[1]||'';const track=(m[2].match(/\b(Ankara|Bursa|Kocaeli|İstanbul|İzmir|Adana|Elazığ|Diyarbakır|Şanlıurfa|Antalya)\b/i)||[])[1]||'';if(fast||mid)out.push({horse:'',m2200:'',m2000:'',m1800:'',m1600:'',m1400:'',m1200:'',m1000:'',m800:mid,m600:'',m400:fast,m200:'',status:'',date:m[1],surface,type:'',track,jockey:'',videoUrl:''});}
  }
  return dedupeWorkouts(out);
}

async function fetchWorkoutsFromHistory(atId,horse,history){
  const urls=[]; const seen=new Set();
  for(const h of (Array.isArray(history)?history:[]).slice(0,12)){
    const u=h?.workoutInfoUrl||"";
    if(u && !seen.has(u)){seen.add(u);urls.push(u);}
  }
  if(!urls.length) return [];
  const all=[];
  for(const url of urls){
    try{
      const r=await fetchT(url);
      if(r.status>=400 || !r.text) continue;
      let parsed=parseWorkouts(r.text);
      if(parsed.some(x=>x.horse)){
        const hn=normName(horse);
        const f=parsed.filter(x=>normName(x.horse)===hn);
        if(f.length) parsed=f;
      }
      for(const x of parsed){ all.push({...x,videoUrl:x.videoUrl||url,sourceUrl:url}); }
    }catch(e){}
  }
  return dedupeWorkouts(all);
}

function dedupeWorkouts(arr){
  const seen=new Set();
  return arr.filter(x=>{const k=[x.date,x.m2200,x.m2000,x.m1800,x.m1600,x.m1400,x.m1200,x.m1000,x.m800,x.m600,x.m400,x.m200,x.track,x.surface].join('|');if(seen.has(k))return false;seen.add(k);return true;})
    .sort((a,b)=>parseDmyForWorker(b.date)-parseDmyForWorker(a.date)).slice(0,1000);
}

function timeSec(s){
  const m=String(s||"").match(/(\d+)\.(\d{2})\.(\d{2})/); if(!m)return null;
  return (+m[1])*60+(+m[2])+(+m[3])/100;
}
function num(s){const x=parseFloat(String(s||"").replace(",","."));return Number.isFinite(x)?x:null}
function normName(s){return String(s||"").toLocaleUpperCase("tr-TR").replace(/\([^)]*\)/g,"").replace(/\s+/g," ").trim()}

function analyze(horses,histories,workouts,raceMeta){
  const active=horses.filter(h=>!isNR(h.name));
  const by={}; active.forEach(h=>by[h.name]=histories[h.name]||[]);
  const weights={track:22,common:18,classFit:14,form:19,weight:12,time:8,pace:5,speed:3};

  const allHP=active.map(h=>num(h.hp)).filter(x=>x!=null), allW=active.map(h=>num(h.weight)).filter(x=>x!=null);
  const minHP=allHP.length?Math.min(...allHP):null,maxHP=allHP.length?Math.max(...allHP):null;
  const minW=allW.length?Math.min(...allW):null,maxW=allW.length?Math.max(...allW):null;
  const scoreScale=(v,lo,hi,inv=false)=>{
    if(v==null||lo==null||hi==null)return null;
    if(hi===lo)return 70;
    const z=inv?(hi-v)/(hi-lo):(v-lo)/(hi-lo);
    return Math.max(0,Math.min(100,z*100));
  };
  const placePts=p=>p===1?100:p===2?88:p===3?78:p===4?68:p===5?58:p===6?48:p===7?38:p===8?28:p===9?18:8;

  // V54 Son Hız yardımcıları.
  // TJK geçmiş koşu tablosunda kesit (400/600) derecesi yoksa uydurma değer üretme.
  // Bunun yerine son gerçek koşunun normalize edilmiş hızını (km/saat) ayrı alan olarak verir.
  const validRaceTime=x=>timeSec(x?.time)!=null && num(x?.distance)!=null && num(x?.distance)>0;
  const speedKmh=x=>{
    const sec=timeSec(x?.time), dist=num(x?.distance);
    if(sec==null||dist==null||dist<=0)return null;
    return (dist/sec)*3.6;
  };
  const latestValid=arr=>{
    for(const x of arr||[]) if(validRaceTime(x)) return x;
    return null;
  };
  const comparableLatest=(arr,raceMeta)=>{
    const rs=String(raceMeta?.surface||'').toLocaleLowerCase('tr-TR');
    const rd=Number(raceMeta?.distance);
    const pool=(arr||[]).filter(validRaceTime);
    const sameDist=Number.isFinite(rd)?pool.filter(x=>num(x.distance)===rd):[];
    const sameSurf=rs?sameDist.filter(x=>String(x.surface||'').toLocaleLowerCase('tr-TR').includes(rs.split(' ')[0])):[];
    return latestValid(sameSurf.length?sameSurf:(sameDist.length?sameDist:pool));
  };

  const out=active.map(h=>{
    const hist=by[h.name]||[];
    const form=String(h.last6||'').replace(/\s+/g,'').split('').filter(x=>/^\d$/.test(x)).map(x=>+x);
    const formVal=form.length?form.reduce((a,p)=>a+placePts(p),0)/form.length:null;

    const raceSurface=String(raceMeta?.surface||'').toLocaleLowerCase('tr-TR');
    const same=hist.filter(x=>{
      const d=num(x.distance);
      const surf=String(x.surface||'').toLocaleLowerCase('tr-TR');
      return d===Number(raceMeta?.distance) && raceSurface && surf.includes(raceSurface.split(' ')[0]);
    });
    const samePlaces=same.map(x=>num(x.place)).filter(x=>x!=null);
    const trackVal=same.length?Math.max(0,Math.min(100,
      samePlaces.reduce((a,p)=>a+placePts(p),0)/samePlaces.length
    )):null;

    let commonCount=0,wins=0,weightEdges=[];
    for(const other of active){
      if(other.name===h.name)continue;
      const oh=by[other.name]||[];
      for(const a of hist) for(const b of oh){
        if(a.date===b.date && a.city===b.city && String(a.distance)===String(b.distance)){
          const pa=num(a.place),pb=num(b.place);
          if(pa!=null&&pb!=null){
            commonCount++;
            if(pa<pb)wins++;
            const wa=num(a.weight),wb=num(b.weight);
            if(wa!=null&&wb!=null)weightEdges.push((pa<pb?1:-1)*(wb-wa));
          }
        }
      }
    }
    let commonVal=null;
    if(commonCount){
      const winRate=wins/commonCount;
      const winScore=winRate*100;
      const avgWeightEdge=weightEdges.length?weightEdges.reduce((a,b)=>a+b,0)/weightEdges.length:0;
      const kiloAdj=Math.max(-15,Math.min(15,avgWeightEdge*3));
      commonVal=Math.max(0,Math.min(100,winScore+kiloAdj));
    }

    const classVal=scoreScale(num(h.hp),minHP,maxHP,false);
    const weightVal=scoreScale(num(h.weight),minW,maxW,true);

    const histTimes=hist.map(x=>({sec:timeSec(x.time),dist:num(x.distance),surface:x.surface,place:num(x.place),date:x.date,city:x.city}))
      .filter(x=>x.sec&&x.dist);
    const sameSurface=histTimes.filter(x=>{
      const surf=String(x.surface||'').toLocaleLowerCase('tr-TR');
      return raceSurface && surf.includes(raceSurface.split(' ')[0]);
    });
    const rates=sameSurface.map(x=>x.sec/(x.dist/1000));
    const avgRate=rates.length?rates.reduce((a,b)=>a+b,0)/rates.length:null;
    const timeVal=rates.length?scoreScale(avgRate,Math.min(...rates),Math.max(...rates),true):null;

    // ===================== V54 SON HIZ =====================
    // Öncelik: aynı pist + aynı mesafedeki en son gerçek koşu.
    // Yoksa aynı mesafe, sonra aynı pist, sonra son geçerli koşu.
    const sonHizRace=comparableLatest(hist,raceMeta);
    const sonHizKmh=sonHizRace?speedKmh(sonHizRace):null;
    const sonHizRate=sonHizRace&&timeSec(sonHizRace.time)!=null&&num(sonHizRace.distance)>0
      ? timeSec(sonHizRace.time)/(num(sonHizRace.distance)/1000):null;
    const sonHizSec=sonHizRace?timeSec(sonHizRace.time):null;
    const sonHizMesafe=sonHizRace?num(sonHizRace.distance):null;
    const sonHizTarih=sonHizRace?.date||'';
    const sonHizPist=sonHizRace?.surface||'';
    // Field karşılaştırması daha sonra yapılır; ham hız ayrı tutulur.

    const ws=(workouts[h.name]||[]).slice(0,5);
    const workoutTimes=[];
    for(const w of ws){
      for(const k of ['m1400','m1200','m1000','m800','m600','m400','m200']){
        const q=timeSec(w[k]); if(q!=null)workoutTimes.push(q);
      }
    }
    const bestWorkout=workoutTimes.length?Math.min(...workoutTimes):null;

    // Eski speed hesabı korunur; ancak V54'te kullanıcıya gösterilen Son Hız,
    // doğrudan son gerçek koşudan alınan hızdır. speed kriteri de bunu kullanır.
    const speedVal=sonHizKmh;

    const parts=[
      ['track',weights.track,trackVal],['common',weights.common,commonVal],['classFit',weights.classFit,classVal],
      ['form',weights.form,formVal],['weight',weights.weight,weightVal],['time',weights.time,timeVal],
      ['pace',weights.pace,bestWorkout],['speed',weights.speed,sonHizKmh]
    ];
    return {...h,_bestWorkout:bestWorkout,_hist:hist,_parts:parts,_same:same,_commonCount:commonCount,
      // Frontend için açık Son Hız alanları
      sonHiz:sonHizKmh==null?null:Number(sonHizKmh.toFixed(2)),
      sonHizKmh:sonHizKmh==null?null:Number(sonHizKmh.toFixed(2)),
      sonHizSure:sonHizSec==null?'':String(sonHizRace.time||''),
      sonHizMesafe:sonHizMesafe,
      sonHizTarih:sonHizTarih,
      sonHizPist:sonHizPist,
      sonHizKaynak:'Son gerçek koşu',
      _sonHizRate:sonHizRate
    };
  });

  const workoutField=out.map(x=>x._bestWorkout).filter(x=>x!=null);
  const wlo=workoutField.length?Math.min(...workoutField):null, whi=workoutField.length?Math.max(...workoutField):null;
  const speedField=out.map(x=>x.sonHizKmh).filter(x=>x!=null);
  const slo=speedField.length?Math.min(...speedField):null, shi=speedField.length?Math.max(...speedField):null;

  const final=out.map(x=>{
    const parts=x._parts.map(p=>{
      if(p[0]==='pace') return [p[0],p[1],scoreScale(p[2],wlo,whi,true)];
      if(p[0]==='speed') return [p[0],p[1],scoreScale(p[2],slo,shi,false)];
      return p;
    });
    const available=parts.filter(p=>p[2]!=null), total=available.reduce((a,p)=>a+p[1],0);
    const score=total?available.reduce((a,p)=>a+p[1]*p[2],0)/total:0;
    return {
      ...x,score:Number(score.toFixed(2)),coverage:total,
      criteria:Object.fromEntries(parts.map(p=>[p[0],p[2]])),
      // Türkçe alan: frontend Son Hız kolonunu doğrudan okuyabilir.
      sonHizPuan:parts.find(p=>p[0]==='speed')?.[2]??null,
      sameTrackCount:x._same.length,commonCount:x._commonCount,
      history:x._hist.slice(0,8),workouts:(workouts[x.name]||[]).slice(0,5)
    };
  }).sort((a,b)=>b.score-a.score);

  return final;
}

function ybDatePath(s){
  const m=String(s||'').match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m?`${m[3]}-${m[2]}-${m[1]}`:'';
}
function ybSurface(v){
  const x=clean(v||'');
  if(/çim|turf/i.test(x))return 'Çim';
  if(/sentetik|synthetic|polytrack|kum\s*\(\s*sen\s*\)/i.test(x))return 'Sentetik';
  if(/kum|sand/i.test(x))return 'Kum';
  return '';
}
function ybSpeed(v){
  const x=clean(v||'');
  const m=x.match(/\(\s*(-?\d+)\s*\)|^\s*(-?\d+)\s*$/);
  if(!m)return null;
  const n=Number(m[1]??m[2]);
  return Number.isFinite(n)?n:null;
}
function ybActualDate(v){
  const m=clean(v||'').match(/(\d{2})[./](\d{2})[./](\d{4})/);
  return m?`${m[1]}.${m[2]}.${m[3]}`:'';
}
function ybDistance(v){
  const m=clean(v||'').match(/\b(\d{3,4})\b/);
  return m?Number(m[1]):null;
}
function ybNormName(s){
  return normName(String(s||'').replace(/\s*\^\{[^}]*\}/g,'').replace(/\s*Image.*$/i,''));
}
function parseYbHorseLinks(html){
  const out=new Map();
  const re=/<a\b[^>]*href=["'](\/at\/\d+\/[^"'#?]+)["'][^>]*>([\s\S]*?)<\/a>/gi;
  let m;
  while((m=re.exec(String(html||'')))){
    const href=m[1], idm=href.match(/^\/at\/(\d+)\/([^/?#]+)/i); if(!idm)continue;
    let label=clean(m[2]).replace(/\s*Image.*$/i,'').trim();
    if(!label)label=decodeURIComponent(idm[2]).replace(/-/g,' ');
    const key=ybNormName(label);
    if(!key)continue;
    out.set(key,{ybId:idm[1],slug:idm[2],url:YB+href,name:label});
  }
  return out;
}
async function fetchYbDayMap(date,city){
  const path=ybDatePath(date), slug=YB_CITY_SLUG[city]||String(city||'').toLocaleLowerCase('tr-TR');
  if(!path||!slug)return {ok:false,error:'YB tarih/şehir çözülemedi',map:new Map(),url:'',sources:[]};
  const key=`${path}|${slug}`;
  const hit=YB_DAY_CACHE.get(key);
  if(hit && Date.now()-hit.ts<10*60*1000)return hit;

  // Yenibeygir gün/şehir sayfası zaman zaman /sonuclar uzantısıyla veya
  // güncel gün için ana sayfadan yayınlanıyor. Tek URL'ye güvenme.
  const candidates=[
    `${YB}/${path}/${slug}`,
    `${YB}/${path}/${slug}/sonuclar`
  ];
  const now=new Date();
  const today=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
  if(String(date)===today)candidates.push(YB+'/');

  const merged=new Map(), sources=[], errors=[];
  for(const url of [...new Set(candidates)]){
    try{
      const r=await fetchTGeneric(url,'https://yenibeygir.com/');
      sources.push({url,status:r.status,length:r.text.length});
      if(r.status>=400){errors.push(`HTTP ${r.status}: ${url}`);continue;}
      const map=parseYbHorseLinks(r.text);
      for(const [k,v] of map) if(!merged.has(k)) merged.set(k,v);
      // En az bir gerçek /at/ profili bulunduysa diğer URL'yi de okumaya gerek yok.
      if(merged.size>0)break;
    }catch(e){errors.push(`${url}: ${String(e?.message||e)}`)}
  }
  const v={ok:merged.size>0,map:merged,url:sources[0]?.url||candidates[0],sources,error:errors.join(' | '),ts:Date.now()};
  YB_DAY_CACHE.set(key,v);
  return v;
}
function parseYbHistory(html){
  const out=[];
  for(const t of tables(html)){
    let hi=-1, headers=[];
    for(let i=0;i<t.rows.length;i++){
      const row=t.rows[i].map(x=>clean(x));
      if(row.some(x=>/^Tarih$/i.test(x)) && row.some(x=>/^Hız$/i.test(x)) && row.some(x=>/Msf\/Pist/i.test(x))){hi=i;headers=row;break;}
    }
    if(hi<0)continue;
    const ix=(re)=>headers.findIndex(x=>re.test(x));
    const dateI=ix(/^Tarih$/i), cityI=ix(/^Şehir$/i), raceI=ix(/K\. Cinsi/i), groupI=ix(/^Gr\.$/i), mpI=ix(/Msf\/Pist/i), timeI=ix(/^Derece$/i), speedI=ix(/^Hız$/i), placeI=ix(/^S$/i), weightI=ix(/^Kilo$/i), hpI=ix(/^Hnd$/i);
    if(dateI<0||mpI<0||speedI<0)continue;
    for(let i=hi+1;i<t.rows.length;i++){
      const c=t.rows[i].map(x=>clean(x));
      if(!c[dateI]||!c[mpI])continue;
      const date=ybActualDate(c[dateI]);
      const distance=ybDistance(c[mpI]);
      const speed=ybSpeed(c[speedI]);
      if(!date||!distance)continue;
      out.push({date,city:cityI>=0?c[cityI]:'',raceName:raceI>=0?c[raceI]:'',group:groupI>=0?c[groupI]:'',distance,surface:ybSurface(c[mpI]),distanceText:c[mpI],time:timeI>=0?c[timeI]:'',ybHiz:speed,place:placeI>=0?c[placeI]:'',weight:weightI>=0?c[weightI]:'',hp:hpI>=0?c[hpI]:''});
    }
  }
  const seen=new Set();
  return out.filter(x=>{const k=[x.date,x.city,x.distance,x.surface,x.time,x.place].join('|');if(seen.has(k))return false;seen.add(k);return true;})
    .sort((a,b)=>parseDmyForWorker(b.date)-parseDmyForWorker(a.date));
}
function ybComparable(history,targetDate,targetDistance,targetSurface){
  const td=parseDmyForWorker(targetDate||'');
  const valid=(history||[]).filter(x=>x.ybHiz!=null && (!td || parseDmyForWorker(x.date)<td));
  const dist=Number(targetDistance);
  const surf=String(targetSurface||'').toLocaleLowerCase('tr-TR');
  const same=(arr)=>arr.filter(x=>Number(x.distance)===dist && (!surf || String(x.surface||'').toLocaleLowerCase('tr-TR')===surf));
  const exact=same(valid);
  const sameSurf=valid.filter(x=>!surf || String(x.surface||'').toLocaleLowerCase('tr-TR')===surf);
  const sameDist=valid.filter(x=>Number(x.distance)===dist);
  const pick=a=>a.length?a[0]:null;
  return {exact:pick(exact),sameSurface:pick(sameSurf),sameDistance:pick(sameDist),latest:pick(valid),bestExact:exact.length?exact.reduce((a,b)=>b.ybHiz>a.ybHiz?b:a):null,exactCount:exact.length};
}
async function fetchTGeneric(url,referer='https://yenibeygir.com/'){
  const ctrl=new AbortController(); const timer=setTimeout(()=>ctrl.abort(),25000);
  try{
    const r=await fetch(url,{headers:{"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":"tr-TR,tr;q=0.9,en;q=0.8","Referer":referer},signal:ctrl.signal});
    return {status:r.status,text:await r.text()};
  }finally{clearTimeout(timer);}
}
function ybNameKey(s){
  return ybNormName(s)
    .replace(/[İI]/g,'I').replace(/Ğ/g,'G').replace(/Ü/g,'U').replace(/Ş/g,'S').replace(/Ö/g,'O').replace(/Ç/g,'C')
    .replace(/[^A-Z0-9]/g,'');
}
function findYbHorseLink(map,horse){
  const exact=map.get(ybNormName(horse));
  if(exact)return exact;
  const k=ybNameKey(horse);
  if(!k)return null;
  let found=null;
  for(const v of map.values()){
    if(ybNameKey(v.name)===k){
      if(found && found.ybId!==v.ybId)return null;
      found=v;
    }
  }
  return found;
}
async function fetchYbHorse(horse,date,city,targetDate,targetDistance,targetSurface){
  const day=await fetchYbDayMap(date,city);
  const link=findYbHorseLink(day.map,horse);
  if(!link){
    return {ok:false,found:false,error:'Yenibeygir günlük/sonuç sayfasında at profili bulunamadı',dayUrl:day.url,daySources:day.sources||[],dayMapSize:day.map.size,ybHistory:[],ybHiz:null};
  }
  const cacheKey=link.ybId;
  let h=YB_HORSE_CACHE.get(cacheKey);
  if(!h || Date.now()-h.ts>15*60*1000){
    const r=await fetchTGeneric(link.url,day.url);
    if(r.status>=400)return {ok:false,found:true,ybId:link.ybId,ybUrl:link.url,error:`Yenibeygir HTTP ${r.status}`,ybHistory:[],ybHiz:null};
    h={...link,status:r.status,history:parseYbHistory(r.text),length:r.text.length,ts:Date.now()};
    YB_HORSE_CACHE.set(cacheKey,h);
  }
  const c=ybComparable(h.history,targetDate,targetDistance,targetSurface);
  const exact=c.exact;
  const chosen=exact||c.sameSurface||c.sameDistance||c.latest;
  const mode=exact?'sameDistanceSurface':c.sameSurface?'sameSurface':c.sameDistance?'sameDistance':c.latest?'latest':'none';
  return {
    ok:true,found:true,ybId:h.ybId,ybUrl:h.url,name:h.name,history:h.history.slice(0,100),
    ybHiz:exact?.ybHiz??null,
    ybHizMode:mode,
    ybHizExact:exact?.ybHiz??null,
    ybHizSameSurface:c.sameSurface?.ybHiz??null,
    ybHizSameDistance:c.sameDistance?.ybHiz??null,
    ybHizLatest:c.latest?.ybHiz??null,
    ybHizBestExact:c.bestExact?.ybHiz??null,
    ybHizExactCount:c.exactCount,
    ybSelectedRace:chosen||null,
    ybDayUrl:day.url,ybDaySources:day.sources||[],ybDayMapSize:day.map.size,ybStatus:h.status
  };
}

async function fetchT(url){
  const ctrl=new AbortController();
  const timer=setTimeout(()=>ctrl.abort(),25000);
  try{
    const r=await fetch(url,{headers:{"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":"tr-TR,tr;q=0.9,en;q=0.8","Referer":"https://www.tjk.org/"},signal:ctrl.signal});
    return {status:r.status,text:await r.text()};
  }finally{clearTimeout(timer);}
}

async function discoverCitiesForDate(date){
  // Şehirleri tek tek seri sorgulamak yerine tek turda paralel kontrol et.
  // Eski sürüm aynı şehri iki kez sorguluyordu; bu da CPU limitini gereksiz
  // biçimde tüketiyordu.
  const entries=Object.entries(CITY_IDS).map(([name,id])=>({name,id}));
  const results=await Promise.all(entries.map(async ({name,id})=>{
    try{
      const d=await fetchDaily(date,name);
      return d.races.length?{name,id,raceCount:d.races.length,status:d.status,sourceUrl:d.url}:null;
    }catch(e){ return null; }
  }));
  const active=results.filter(Boolean);
  return active.length?active:entries;
}
async function fetchDaily(date,city){
  const cacheKey=`${date}|${city}`;
  const cached=DAILY_CACHE.get(cacheKey);
  if(cached && (Date.now()-cached.ts)<DAILY_CACHE_TTL) return cached.value;

  const d=encodeURIComponent(dateTR(date)), c=encodeURIComponent(city);
  const id=CITY_IDS[city]||9;
  // Öncelik: TJK Günlük Yarış Programı. Bu sayfa jokey, sahip, antrenör,
  // St, KGS, s20, En İyi D., Gny, AGF ve İdm dahil tam program sütunlarını
  // içeriyor. Önce Kayıtlar kullanıldığında bu sütunların bir kısmı boş kalıyordu.
  const urls=[
    `${TJK}/TR/YarisSever/Info/Page/GunlukYarisProgrami?QueryParameter_Tarih=${d}&SehirAdi=${c}&SehirId=${id}`,
    `${TJK}/TR/YarisSever/Info/Sehir/GunlukYarisProgrami?QueryParameter_Tarih=${d}&SehirAdi=${c}&SehirId=${id}`,
    `${TJK}/TR/YarisSever/Info/Page/GunlukYarisProgrami?1=1&Era=today&QueryParameter_Tarih=${d}&SehirAdi=${c}`,
    `${TJK}/TR/YarisSever/Info/Sehir/GunlukYarisProgrami?Era=today&QueryParameter_Tarih=${d}&SehirAdi=${c}&SehirId=${id}`
  ];
  let last={status:0,url:urls[0]};
  for(const url of urls){
    try{
      const r=await fetchT(url); last={status:r.status,url};
      if(r.status>=400) continue;
      const races=parseDaily(r.text);
      if(races.length){
        // Normal günlük program zaten Sahip/Antrenör bilgisini taşıyor.
        // Kayıtlar parserını her istekte çalıştırmak çok pahalı olduğu için
        // yalnızca gerçekten eksik alan varsa fallback olarak çalıştır.
        const needsAux=races.some(rr=>(rr.horses||[]).some(h=>!String(h.owner||'').trim()||!String(h.trainer||'').trim()));
        if(needsAux){
          try{
            const aux=parseKayitlar(r.text);
            const auxMap=new Map();
            for(const rr of aux)for(const hh of (rr.horses||[])){
              const k=normName(hh.name);
              if(k)auxMap.set(k,hh);
            }
            for(const rr of races)for(const hh of (rr.horses||[])){
              const a=auxMap.get(normName(hh.name));
              if(a){
                if(!String(hh.owner||'').trim()&&String(a.owner||'').trim())hh.owner=a.owner;
                if(!String(hh.trainer||'').trim()&&String(a.trainer||'').trim())hh.trainer=a.trainer;
              }
            }
          }catch(_e){}
        }
        const result={races,status:r.status,url,source:"GunlukYarisProgrami"};
        DAILY_CACHE.set(cacheKey,{ts:Date.now(),value:result});
        return result;
      }
    }catch(e){ last={status:0,url,error:String(e.message||e)}; }
  }
  // Günlük program ayrıştırılamazsa Kayıtlar son çare olarak kullanılır.
  // Bu fallback programın tamamen kaybolmasını önler; ancak tam sütunlar için
  // Günlük Yarış Programı tercih edilir.
  const kayitUrls=[
    `${TJK}/TR/YarisSever/Info/Sehir/Kayitlar?Era=today&QueryParameter_Tarih=${d}&SehirAdi=${c}&SehirId=${id}`,
    `${TJK}/TR/Yarissever/Info/Sehir/Kayitlar?Era=today&QueryParameter_Tarih=${d}&SehirAdi=${c}&SehirId=${id}`
  ];
  for(const url of kayitUrls){
    try{
      const r=await fetchT(url); last={status:r.status,url};
      if(r.status>=400) continue;
      const races=parseKayitlar(r.text);
      if(races.length){ const result={races,status:r.status,url,source:"Kayitlar"}; DAILY_CACHE.set(cacheKey,{ts:Date.now(),value:result}); return result; }
    }catch(e){ last={status:0,url,error:String(e.message||e)}; }
  }
  return {races:[],status:last.status,url:last.url};
}
export default {async fetch(req){
  if(req.method==="OPTIONS")return new Response("",{headers:CORS});
  const u=new URL(req.url), p=u.pathname, q=u.searchParams;
  try{
    if(p==="/api/health")return out({ok:true,service:"Race Intelligence TJK Gateway",version:"54.2-YB-HIZ-FIX",worker:"fragrant-hat-ae48",time:new Date().toISOString()});

    if(p==="/api/tjk/cities"){
      const date=q.get("date")||new Date().toISOString().slice(0,10);
      const entries=Object.entries(CITY_IDS).map(([name,id])=>({name,id}));
      const results=await Promise.all(entries.map(async ({name,id})=>{
        try{
          const d=await fetchDaily(date,name);
          return {name,id,raceCount:d.races.length,horseCount:d.races.reduce((a,r)=>a+r.horses.length,0),status:d.status,sourceUrl:d.url};
        }catch(e){return {name,id,raceCount:0,horseCount:0,status:0,error:String(e.message||e)};}
      }));
      return out({ok:true,date,cities:results.filter(x=>x.raceCount>0),checked:results});
    }

    if(p==="/api/tjk/data"){
      const date=q.get("date")||new Date().toISOString().slice(0,10), city=q.get("city")||"Kocaeli";
      const daily=await fetchDaily(date,city), races=daily.races;
      return out({ok:true,source:"TJK Günlük Yarış Programı",date,city,status:daily.status,sourceUrl:daily.url,raceCount:races.length,horseCount:races.reduce((a,r)=>a+r.horses.length,0),withAtId:races.reduce((a,r)=>a+r.horses.filter(h=>h.atId).length,0),races});
    }

    if(p==="/api/tjk/horse"){
      const atId=q.get("atId"); if(!atId)return out({ok:false,error:"atId gerekli"},400);
      const url=`${TJK}/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId=${encodeURIComponent(atId)}`;
      const r=await fetchT(url); const history=attachClassScores(parseHistory(r.text));
      return out({ok:r.status<400,status:r.status,atId,history,classAnalysis:classAnalysis(history)});
    }

    if(p==="/api/tjk/workouts"){
      const horse=q.get("horse"); if(!horse)return out({ok:false,error:"horse gerekli"},400);
      const url=`${TJK}/TR/YarisSever/Query/Page/IdmanIstatistikleri?1=1&QueryParameter_ATADI=${encodeURIComponent(horse)}`;
      const r=await fetchT(url); let workouts=parseWorkouts(r.text);
      if(workouts.some(x=>x.horse)){const hn=normName(horse); const f=workouts.filter(x=>normName(x.horse)===hn); if(f.length) workouts=f;}
      if(!workouts.length){
        try{
          const hurl=`${TJK}/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri?1=1&Era=today&QueryParameter_AtId=${encodeURIComponent(q.get("atId")||"")}`;
          const hr=await fetchT(hurl);
          workouts=await fetchWorkoutsFromHistory(q.get("atId")||"",horse,parseHistory(hr.text));
        }catch(e){}
      }
      return out({ok:r.status<400,status:r.status,horse,workouts});
    }

    if(p==="/api/tjk/horsedata"){
      const atId=q.get("atId"), horse=q.get("horse"), origin=q.get("origin")||"";
      const targetDate=q.get("date")||"", targetCity=q.get("city")||"", targetDistance=q.get("distance")||"", targetSurface=q.get("surface")||"", targetClass=q.get("raceClass")||"";
      if(!atId || !horse)return out({ok:false,error:"atId ve horse gerekli"},400);
      const historyUrls=[
        `${TJK}/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri?1=1&Era=today&QueryParameter_AtId=${encodeURIComponent(atId)}`,
        `${TJK}/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId=${encodeURIComponent(atId)}`,
        `${TJK}/TR/map/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId=${encodeURIComponent(atId)}`,
        `${TJK}/TR/YarisSever/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId=${encodeURIComponent(atId)}`
      ];
      const workoutUrls=[
        `${TJK}/TR/YarisSever/Query/Page/IdmanIstatistikleri?1=1&QueryParameter_AtId=${encodeURIComponent(atId)}`,
        `${TJK}/TR/YarisSever/Query/Page/IdmanIstatistikleri?1=1&QueryParameter_ATADI=${encodeURIComponent(horse)}`,
        `${TJK}/TR/YarisSever/Query/Page/IdmanIstatistikleri?1=1&QueryParameter_AtAdi=${encodeURIComponent(horse)}`
      ];
      const result={ok:true,atId,horse,origin,history:[],workouts:[],errors:{},historyAttempts:[],workoutAttempts:[]};
      const historyCandidates=[];
      for(const url of historyUrls){
        try{
          const r=await fetchT(url); const parsed=parseHistory(r.text);
          const metaScore=parsed.reduce((n,x)=>n+(x.surface?2:0)+(x.jockey?1:0)+(x.raceName?1:0)+(x.hp?1:0),0);
          historyCandidates.push({parsed,metaScore,status:r.status,source:url});
          result.historyAttempts.push({status:r.status,length:r.text.length,source:url,markers:{Tarih:/Tarih/i.test(r.text),Derece:/Derece/i.test(r.text),AtAdi:/At\s*(?:Adı|Adi|İsmi|Ismi)/i.test(r.text),Pist:/Pist/i.test(r.text)},parsedCount:parsed.length,metadataScore:metaScore});
        }catch(e){result.historyAttempts.push({status:0,length:0,source:url,error:String(e?.message||e)});result.errors.history=String(e?.message||e)}
      }
      if(historyCandidates.length){historyCandidates.sort((a,b)=>b.metaScore-a.metaScore);const best=historyCandidates[0];result.history=best.parsed;result.historyStatus=best.status;result.historySource=best.source;}
      result.history=attachClassScores(result.history);
      result.classAnalysis=classAnalysis(result.history,targetClass,targetDate);
      let historyWorkoutFallback=[];
      try{ historyWorkoutFallback=await fetchWorkoutsFromHistory(atId,horse,result.history); }catch(e){}
      const workoutCandidates=[];
      if(historyWorkoutFallback.length){
        const hs=historyWorkoutFallback.reduce((n,x)=>n+(x.track?5:0)+(x.surface?3:0)+(x.m1200?1:0)+(x.m1000?1:0)+(x.m800?1:0)+(x.m600?1:0)+(x.m400?1:0),0);
        workoutCandidates.push({parsed:historyWorkoutFallback,score:hs+20,status:200,source:"TJK İdman Bilgileri / KosuKodu"});
      }
      for(const url of workoutUrls){
        try{
          const r=await fetchT(url); let parsed=parseWorkouts(r.text);
          if(parsed.some(x=>x.horse)){const hn=normName(horse); const f=parsed.filter(x=>normName(x.horse)===hn); if(f.length) parsed=f;}
          const score=parsed.reduce((n,x)=>n+(x.track?5:0)+(x.surface?3:0)+(x.type?1:0)+(x.m1200?1:0)+(x.m1000?1:0)+(x.m800?1:0)+(x.m600?1:0)+(x.m400?1:0)+(x.m200?1:0),0);
          workoutCandidates.push({parsed,score,status:r.status,source:url});
          result.workoutAttempts.push({status:r.status,length:r.text.length,source:url,markers:{Tarih:/Tarih/i.test(r.text),m400:/400\s*m|400m|400 metre/i.test(r.text),m800:/800\s*m|800m|800 metre/i.test(r.text),m1000:/1000\s*m|1000 metre|1000m/i.test(r.text),m1200:/1200\s*m|1200 metre|1200m/i.test(r.text),Hipodrom:/İ\.?\s*Hip|Hipodrom/i.test(r.text)},parsedCount:parsed.length,metadataScore:score});
        }catch(e){result.workoutAttempts.push({status:0,length:0,source:url,error:String(e?.message||e)});result.errors.workouts=String(e?.message||e)}
      }
      if(workoutCandidates.length){workoutCandidates.sort((a,b)=>b.score-a.score);const best=workoutCandidates[0];result.workouts=best.parsed;result.workoutStatus=best.status;result.workoutSource=best.source;}
      result.historyCount=result.history.length; result.workoutCount=result.workouts.length;
      if(targetDate && targetCity){
        try{
          const yb=await fetchYbHorse(horse,targetDate,targetCity,targetDate,targetDistance,targetSurface);
          result.yb=yb;
          if(!yb.ok) result.errors.yenibeygir=yb.error||"YB Hız alınamadı";
        }catch(e){
          result.yb={ok:false,found:false,ybHiz:null,ybHistory:[],error:String(e?.message||e)};
          result.errors.yenibeygir=String(e?.message||e);
        }
      }else{
        result.yb={ok:false,found:false,ybHiz:null,ybHistory:[],error:"YB Hız için date ve city gerekli"};
      }
      result.partial=Object.keys(result.errors).length>0;
      return out(result);
    }

    if(p==="/api/yb/horse"){
      const horse=q.get("horse")||"", date=q.get("date")||"", city=q.get("city")||"", distance=q.get("distance")||"", surface=q.get("surface")||"";
      if(!horse||!date||!city)return out({ok:false,error:"horse, date ve city gerekli"},400);
      const yb=await fetchYbHorse(horse,date,city,date,distance,surface);
      return out({ok:true,horse,date,city,distance,surface,yb});
    }

    if(p==="/api/tjk/horsedata-debug"){
      const atId=q.get("atId"), horse=q.get("horse")||"";
      if(!atId)return out({ok:false,error:"atId gerekli"},400);
      const historyUrls=[
        `${TJK}/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri?1=1&Era=today&QueryParameter_AtId=${encodeURIComponent(atId)}`,
        `${TJK}/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId=${encodeURIComponent(atId)}`,
        `${TJK}/TR/map/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId=${encodeURIComponent(atId)}`,
        `${TJK}/TR/YarisSever/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId=${encodeURIComponent(atId)}`
      ];
      const workoutUrls=[
        `${TJK}/TR/YarisSever/Query/Page/IdmanIstatistikleri?1=1&QueryParameter_AtId=${encodeURIComponent(atId)}`,
        `${TJK}/TR/YarisSever/Query/Page/IdmanIstatistikleri?1=1&QueryParameter_ATADI=${encodeURIComponent(horse)}`,
        `${TJK}/TR/YarisSever/Query/Page/IdmanIstatistikleri?1=1&QueryParameter_AtAdi=${encodeURIComponent(horse)}`
      ];
      const hist=[]; for(const url of historyUrls){try{const r=await fetchT(url);hist.push({status:r.status,length:r.text.length,source:url,markers:{Tarih:/Tarih/i.test(r.text),Derece:/Derece/i.test(r.text),AtAdi:/At\s*(?:Adı|Adi|İsmi|Ismi)/i.test(r.text),mesafe:/Msf|Mesafe/i.test(r.text)},parsedCount:parseHistory(r.text).length});}catch(e){hist.push({status:0,length:0,source:url,error:String(e?.message||e)})}}
      const work=[]; for(const url of workoutUrls){try{const r=await fetchT(url);work.push({status:r.status,length:r.text.length,source:url,markers:{Tarih:/Tarih/i.test(r.text),m400:/400\s*m|400m|400 metre/i.test(r.text),m800:/800\s*m|800m|800 metre/i.test(r.text),m1000:/1000\s*m|1000m|1000 metre/i.test(r.text),m1200:/1200\s*m|1200m|1200 metre/i.test(r.text),AtAdi:/At\s*(?:Adı|Adi|İsmi|Ismi)/i.test(r.text)},parsedCount:parseWorkouts(r.text).length});}catch(e){work.push({status:0,length:0,source:url,error:String(e?.message||e)})}}
      return out({ok:true,version:"54.2-YB-HIZ-FIX",atId,horse,historyAttempts:hist,workoutAttempts:work});
    }

    if(p==="/api/tjk/analyze"){
      return out({ok:false,error:"V34 istemci-tabanlı analiz kullanır. /api/tjk/data ve /api/tjk/horsedata endpointlerini kullanın."},410);
    }

    if(p==="/api/tjk/raw"){const url=q.get("url");if(!url||!url.startsWith(TJK))return out({ok:false,error:"Geçersiz url"},400);const r=await fetchT(url);return new Response(r.text,{status:r.status,headers:{"Content-Type":r.text.includes("<html")?"text/html; charset=utf-8":"text/plain; charset=utf-8",...CORS}})}
    return out({ok:false,error:"Bilinmeyen endpoint",endpoints:["/api/health","/api/tjk/data","/api/tjk/horse","/api/tjk/workouts","/api/tjk/horsedata","/api/tjk/horsedata-debug","/api/yb/horse","/api/tjk/analyze","/api/tjk/raw"]},404);
  }catch(e){return out({ok:false,error:String(e?.message||e)},500)}
}}
