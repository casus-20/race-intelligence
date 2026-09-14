const TJK="https://www.tjk.org";
const CITY_IDS={Ankara:5,Kocaeli:9,İstanbul:3,Bursa:4,İzmir:1,Adana:2,Elazığ:6,Diyarbakır:7,Şanlıurfa:8,Antalya:10};
const CORS={"Access-Control-Allow-Origin":"*","Access-Control-Allow-Methods":"GET,OPTIONS","Access-Control-Allow-Headers":"Content-Type"};
const H={"Content-Type":"application/json; charset=utf-8",...CORS};

function out(x,status=200){return new Response(JSON.stringify(x),{status,headers:H})}
function dateTR(s){const [y,m,d]=s.split("-");return `${d}/${m}/${y}`}
function escReg(s){return s.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")}
function clean(s){
  return String(s??"").replace(/<script[\s\S]*?<\/script>/gi," ")
    .replace(/<style[\s\S]*?<\/style>/gi," ")
    .replace(/<[^>]+>/g," ")
    .replace(/&nbsp;/gi," ").replace(/&amp;/gi,"&").replace(/&#39;/gi,"'")
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
  const re=new RegExp('\\b'+name+'\\s*=\\s*["\']([^"\']*)["\']','i');
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
  return [...row.matchAll(/href\s*=\s*["']([^"']+)["']/gi)].map(m=>m[1].replace(/&amp;/g,"&"));
}
function getAtId(rowHtml){
  const a=hrefs(rowHtml).join(" ");
  const m=a.match(/(?:QueryParameter_AtId|AtKodu|Atkodu)=(\d+)/i);
  return m?m[1]:null;
}
function isNR(name){return /koşmaz|kosmaz|çekildi|cekildi|start almaz/i.test(name||"")}

function normCity(s){
  return clean(s||"").toLocaleLowerCase("tr-TR")
    .replace(/ı/g,"i").replace(/ş/g,"s").replace(/ğ/g,"g")
    .replace(/ü/g,"u").replace(/ö/g,"o").replace(/ç/g,"c")
    .replace(/[^a-z0-9]+/g," ").trim();
}
function cityAliases(city){
  const n=normCity(city);
  const map={
    elazig:["elazig","elazığ"], sanliurfa:["sanliurfa","şanlıurfa"],
    istanbul:["istanbul","ıstanbul"], izmir:["izmir"],
    diyarbakir:["diyarbakir","diyarbakır"], ankara:["ankara"],
    kocaeli:["kocaeli"], bursa:["bursa"], adana:["adana"], antalya:["antalya"]
  };
  return map[n]||[city];
}
function cityIdentity(html,requestedCity){
  const aliases=cityAliases(requestedCity).map(normCity);
  const requestedId=CITY_IDS[requestedCity];
  let positive=0, negative=0, evidence=[];
  const selected=[...String(html).matchAll(/<(?:option|input)\b[^>]*?(?:selected|checked)[^>]*>([^<]*)/gi)]
    .map(m=>normCity(m[1]||""));
  for(const x of selected){
    if(aliases.some(a=>x===a||x.includes(a))){positive+=6;evidence.push("selected-city");}
    for(const [name] of Object.entries(CITY_IDS)){
      const na=normCity(name);
      if(!aliases.includes(na)&&(x===na||x.includes(na))){negative+=5;evidence.push("selected-other-city:"+name);break;}
    }
  }
  const heads=[...String(html).matchAll(/<(?:title|h1|h2|h3|h4)\b[^>]*>([\s\S]*?)<\/(?:title|h1|h2|h3|h4)>/gi)]
    .map(m=>normCity(m[1]||""));
  for(const x of heads){
    if(aliases.some(a=>x.includes(a))){positive+=4;evidence.push("heading-city");}
    for(const [name] of Object.entries(CITY_IDS)){
      const na=normCity(name);
      if(!aliases.includes(na)&&x.includes(na)){negative+=4;evidence.push("heading-other-city:"+name);}
    }
  }
  if(requestedId!=null){
    const idRe=new RegExp("(?:SehirId|CityId|HipodromId|hipodromId)[^0-9]{0,20}"+requestedId+"\\b","i");
    if(idRe.test(html)){positive+=3;evidence.push("city-id");}
  }
  return {ok:negative===0 && positive>0,positive,negative,evidence};
}

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
      horses.push({
        no:noI>=0?r[noI]:"",
        name,
        age:ageI>=0?r[ageI]:"",
        origin:originI>=0?r[originI]:"",
        weight:weightI>=0?r[weightI]:"",
        owner:ownerI>=0?r[ownerI]:"",
        trainer:trainerI>=0?r[trainerI]:"",
        hp:hpI>=0?r[hpI]:"",
        last6:formI>=0?r[formI]:"",
        lastDate:lastI>=0?r[lastI]:"",
        atId
      });
    }
    if(!horses.length)continue;
    const before=clean(html.slice(Math.max(0,t.start-9000),t.start));
    const dm=[...before.matchAll(/(\d{3,4})\s*(?:m)?\s+(Kum|Çim|Sentetik|Fiber Sand|Turf|Polytrack)/gi)];
    const last=dm.length?dm[dm.length-1]:null;
    const meta={
      distance:last?Number(last[1]):null,
      surface:last?last[2]:"",
      raw:before.slice(-1800)
    };
    races.push({no:races.length+1,time:"",meta,horses});
  }
  return races;
}

function parseKayitlarRobust(html){
  const rows=[...html.matchAll(/<tr\b[^>]*>[\s\S]*?<\/tr>/gi)]
    .map(m=>({pos:m.index,html:m[0],cells:cells(m[0])}));
  const horseRows=[];
  for(const x of rows){
    const c=x.cells;
    if(c.length<7)continue;
    const noIdx=c.findIndex(v=>/^\d{1,2}$/.test(String(v).trim()));
    const nameIdx=c.findIndex((v,i)=>
      i>noIdx &&
      /[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9 .'-]{2,}/i.test(v) &&
      !/^(At İsmi|Horse Name)$/i.test(v)
    );
    if(noIdx<0||nameIdx<0)continue;
    const name=clean(c[nameIdx])
      .replace(/\s+Image.*$/i,"")
      .replace(/\s+\(Koşmaz\)$/i,"")
      .trim();
    if(!name||/^(Koşu|Ikramiye|Yetistirici|At Sahibi|S)$/i.test(name))continue;
    const raw=x.html;
    const atId=getAtId(raw);
    horseRows.push({
      pos:x.pos,
      html:raw,
      cells:c,
      no:c[noIdx],
      name,
      atId:x.atId||atId
    });
  }

  if(!horseRows.length)return [];

  const text=clean(html);
  const headerRe=/S\s+At İsmi\s+Yaş\s+Orijin(?:\([^)]*\))?\s+Sıklet\s+Sahip\s+Antrenörü\s+HP\s+Son 6 Y\.\s+Son Koşu Tarihi/gi;
  const headers=[...text.matchAll(headerRe)];

  const headingRe=/<(?:h[1-6]|div|span|strong|b)\b[^>]*>\s*Koşu\s*<\/(?:h[1-6]|div|span|strong|b)>/gi;
  const heads=[...html.matchAll(headingRe)].map(m=>m.index);

  const boundaries=heads.length?heads:[0];
  const races=[];

  for(let bi=0;bi<boundaries.length;bi++){
    const from=boundaries[bi];
    const to=bi+1<boundaries.length?boundaries[bi+1]:Infinity;
    const hs=horseRows.filter(r=>r.pos>=from&&r.pos<to);
    if(!hs.length)continue;

    const seg=clean(html.slice(from,to===Infinity?html.length:to));
    const dm=seg.match(/(\d{3,4})\s*(?:m\s*)?(Kum|Çim|Sentetik|Fiber Sand|Turf|Polytrack)\b/i);
    const classM=seg.match(/((?:ŞARTLI|KV-?\d+|Handikap\s*\d+|Maiden)[^\n]{0,180})/i);
    const timeM=seg.match(/\b(\d{1,2})[:.](\d{2})\b/);

    const horses=hs.map(r=>{
      const c=r.cells;
      return {
        no:r.no,
        name:r.name,
        age:c[2]||"",
        origin:c[3]||"",
        weight:c[4]||"",
        owner:c[5]||"",
        trainer:c[6]||"",
        hp:c[7]||"",
        last6:c[8]||"",
        lastDate:c[9]||"",
        atId:r.atId
      };
    }).filter(h=>h.name);

    races.push({
      no:races.length+1,
      time:timeM?`${timeM[1].padStart(2,'0')}:${timeM[2]}`:"",
      meta:{
        distance:dm?Number(dm[1]):null,
        surface:dm?dm[2]:"",
        raceName:classM?classM[1].trim():"",
        raw:seg.slice(0,1800)
      },
      horses
    });
  }

  if(races.length)return races;

  const horses=horseRows.map(r=>{
    const c=r.cells;
    return {
      no:r.no,
      name:r.name,
      age:c[2]||"",
      origin:c[3]||"",
      weight:c[4]||"",
      owner:c[5]||"",
      trainer:c[6]||"",
      hp:c[7]||"",
      last6:c[8]||"",
      lastDate:c[9]||"",
      atId:r.atId
    };
  });

  return [{
    no:1,
    time:"",
    meta:{
      distance:null,
      surface:"",
      raceName:"",
      raw:text.slice(0,1800)
    },
    horses
  }];
}

function parseKayitlar(html){
  const a=parseKayitlarTable(html);
  if(a.length)return a;
  return parseKayitlarRobust(html);
}

function balancedTables(html){
  const re=/<\/?table\b[^>]*>/gi;
  const stack=[];
  const out=[];
  let m;

  while((m=re.exec(html))){
    const tag=m[0];

    if(/^<table\b/i.test(tag)){
      stack.push({start:m.index,depth:stack.length});
    }else if(stack.length){
      const x=stack.pop();
      out.push({
        start:x.start,
        end:re.lastIndex,
        depth:x.depth,
        html:html.slice(x.start,re.lastIndex)
      });
    }
  }

  return out;
}

function classText(rowHtml, cls){
  const re=new RegExp(
    '<[^>]*class=["\\\'][^"\\\']*'+cls+'[^"\\\']*["\\\'][^>]*>([\\s\\S]*?)<\\/[^>]+>',
    'i'
  );
  const m=rowHtml.match(re);
  return m?clean(m[1]):'';
}

function extractRaceHeaders(html){
  const out=[];
  const txt=clean(html).replace(/\s+/g,' ');

  const re=/(\d{1,2})\.\s*Koşu\s+([0-2]?\d(?:[:.]|\.)[0-5]\d)([\s\S]{0,900}?)(?=\d{1,2}\.\s*Koşu\s+[0-2]?\d(?:[:.]|\.)[0-5]\d|Forma\s+N\s+At İsmi|$)/gi;

  let m;

  while((m=re.exec(txt))){
    const no=+m[1];
    const time=normTime(m[2]);

    let detail=String(m[3]||'').trim();
    detail=detail.replace(/^[-–—:;,]+/,'').trim();

    const stop=detail.search(
      /\s+(?:İkramiye|At Sahibi Primi|Yetiştiricilik Primi|Forma\s+N\s+At İsmi|N\s+At İsmi)\b/i
    );

    if(stop>=0)detail=detail.slice(0,stop).trim();

    const dm=detail.match(
      /(\d{3,4})\s*(?:m\s*)?(Kum|Çim|Sentetik|Fiber Sand|Turf|Polytrack)\b/i
    );

    if(dm){
      const eid=detail.match(/E\.?İ\.?D\.?\s*[:：]\s*([0-9.]+)/i);

      out.push({
        no,
        time,
        detail:detail.slice(0,650),
        distance:Number(dm[1]),
        surface:dm[2],
        eid:eid?eid[1]:''
      });
    }else{
      out.push({
        no,
        time,
        detail:detail.slice(0,650)
      });
    }
  }

  const seen=new Set();

  return out
    .filter(x=>{
      if(seen.has(x.no))return false;
      seen.add(x.no);
      return true;
    })
    .sort((a,b)=>a.no-b.no);
}

function cleanJockey(v){
  let x=String(v??'').replace(/\s+/g,' ').trim();
  if(!x)return '';

  x=x.replace(
    /\s*(?:raporlu|rapor(?:lu)? olduğundan|rapor nedeniyle|raporlu olduğundan dolayı|jokey değişikliği.*)$/i,
    ''
  ).trim();

  x=x.replace(/\s+raporlu.*$/i,'').trim();

  return x;
}

function parseDaily(html){
  const blocks=balancedTables(html);
  const candidates=[];

  for(const b of blocks){
    if(!/gunluk-GunlukYarisProgrami-AtAdi/i.test(b.html))continue;

    const rs=[...b.html.matchAll(/<tr\b[^>]*>[\s\S]*?<\/tr>/gi)]
      .map(m=>m[0]);

    let headerCells=null;

    for(const raw of rs){
      const c=cells(raw);

      if(
        c.some(x=>/At İsmi/i.test(x)) &&
        c.some(x=>/^HP$/i.test(x)) &&
        c.some(x=>/Son 6/i.test(x))
      ){
        headerCells=c;
        break;
      }
    }

    if(!headerCells)continue;

    const ix=(re)=>headerCells.findIndex(x=>re.test(String(x).trim()));

    const noI=ix(/^N$|^No$|^S$/i);
    const nameI=ix(/At İsmi|Horse Name/i);
    const ageI=ix(/^Yaş$|^Age$/i);
    const originI=ix(/Orijin|Origin/i);
    const weightI=ix(/Sıklet|Weight/i);
    const jockeyI=ix(/^Jokey$|^Jockey$/i);
    const ownerI=ix(/^Sahip$|^Owner$/i);
    const trainerI=ix(/Antrenör|Trainer/i);
    const stI=ix(/^St$|^Start$/i);
    const hpI=ix(/^HP$|^RT$/i);
    const formI=ix(/Son 6|Last 6/i);
    const kgsI=ix(/^KGS$/i);
    const s20I=ix(/^s20$/i);
    const bestI=ix(/En İyi D\.|Best Time/i);
    const oddsI=ix(/^Gny$|Odds/i);
    const agfI=ix(/^AGF$|Favorite/i);
    const workoutI=ix(/^İdm$|^Idm$|Workout/i);
    const lastI=ix(/Son Koşu Tarihi|Last Race Date/i);

    if(nameI<0||noI<0)continue;

    const parsed=[];

    for(const raw of rs){
      if(!/gunluk-GunlukYarisProgrami-AtAdi/i.test(raw))continue;

      const c=cells(raw);
      const rc=rawCells(raw);

      if(!c.length)continue;

      const no=(c[noI]||'').match(/^(\d{1,2})$/)?.[1]||'';

      if(!no)continue;

      let name=classText(
        raw,
        'gunluk-GunlukYarisProgrami-AtAdi'
      ).replace(/\s*Image.*$/i,'').trim();

      if(!name&&c[nameI]){
        name=String(c[nameI])
          .replace(/\s*Image.*$/i,'')
          .trim();
      }

      if(!name)continue;

      parsed.push({
        no,
        name,
        age:(c[ageI]||'').trim(),
        origin:(c[originI]||'').trim(),
        weight:(c[weightI]||'').trim(),
        jockey:cleanJockey((c[jockeyI]||'').trim()),
        owner:(c[ownerI]||'').trim(),
        trainer:(c[trainerI]||'').trim(),
        st:(c[stI]||'').trim(),
        hp:(c[hpI]||'').trim(),
        last6:(c[formI]||'').trim(),
        lastDate:lastI>=0?(c[lastI]||'').trim():'',
        kgs:kgsI>=0?(c[kgsI]||'').trim():'',
        s20:s20I>=0?(c[s20I]||'').trim():'',
        bestTime:bestI>=0
          ?((c[bestI]||'').match(/\b\d+\.\d{2}\.\d{2}\b/)||[])[0]||''
          :'',
        bestInfo:bestI>=0
          ?(
              attrDeep(
                rc[bestI],
                [
                  'title',
                  'data-title',
                  'data-content',
                  'data-original-title',
                  'aria-label'
                ]
              ) ||
              ((c[bestI]||'').replace(
                /^[\s\S]*?\b\d+\.\d{2}\.\d{2}\b/,
                ''
              ).trim())
            )
          :'',
        bestCity:bestI>=0
          ?attrDeep(rc[bestI],['data-city','data-hipodrom'])
          :'',
        bestDate:bestI>=0
          ?attrDeep(rc[bestI],['data-date','data-tarih'])
          :'',
        bestDistance:bestI>=0
          ?attrDeep(rc[bestI],['data-distance','data-mesafe'])
          :'',
        odds:oddsI>=0?(c[oddsI]||'').trim():'',
        agf:agfI>=0?(c[agfI]||'').trim():'',
        workout:workoutI>=0?(c[workoutI]||'').trim():'',
        atId:getAtId(raw)
      });
    }

    if(parsed.length<2)continue;

    const beforeRaw=html.slice(
      Math.max(0,b.start-35000),
      b.start
    );

    const before=clean(beforeRaw).replace(/\s+/g,' ');

    const markerRe=/(\d{1,2}\.\s*Koşu)\s+([0-2]?\d(?:[:.]|\.)[0-5]\d)/gi;
    const matches=[...before.matchAll(markerRe)];
    const head=matches.length?matches[matches.length-1]:null;

    const time=head?normTime(head[2]):'';

    let raceHeader='';

    if(head){
      const tail=before.slice(head.index+head[0].length);

      const stop=tail.search(
        /\s+(?:İkramiye|At Sahibi Primi|Yetiştiricilik Primi|N\s+At İsmi|Forma\s+N\s+At İsmi)/i
      );

      raceHeader=tail.slice(
        0,
        stop>=0?stop:1800
      );
    }

    raceHeader=clean(raceHeader)
      .replace(/\s+/g,' ')
      .replace(/^[,;:\-]+|[,;:\-]+$/g,'')
      .trim();

    const dm=[
      ...raceHeader.matchAll(
        /(\d{3,4})\s*(?:m)?\s*(Kum|Çim|Sentetik|Fiber Sand|Turf|Polytrack)\b/gi
      )
    ];

    const last=dm.length?dm[dm.length-1]:null;

    const surface=last?last[2]:'';
    const distance=last?Number(last[1]):null;

    const eid=raceHeader.match(
      /E\.?İ\.?D\.?\s*[:：]\s*([0-9.]+)/i
    );

    const raceName=raceHeader;

    candidates.push({
      start:b.start,
      depth:b.depth,
      horses:parsed,
      meta:{
        distance,
        surface,
        raceName,
        detail:raceHeader,
        eid:eid?eid[1]:'',
        raw:before.slice(-5000)
      },
      time,
      name:raceName
    });
  }

  const usable=candidates.filter(
    c=>c.horses.length>=2&&c.horses.length<=35
  );

  const maxDepth=usable.length
    ?Math.max(...usable.map(c=>c.depth))
    :0;

  const pool=(
    usable.filter(c=>c.depth===maxDepth).length
      ?usable.filter(c=>c.depth===maxDepth)
      :usable
  ).sort((a,b)=>a.start-b.start);

  const headerList=extractRaceHeaders(html);
  const races=[];

  for(const c of pool){
    const sig=c.horses
      .map(h=>normName(h.name))
      .join('|');

    if(!sig||races.some(r=>r._sig===sig))continue;

    races.push({...c,_sig:sig});
  }

  return races
    .sort((a,b)=>a.start-b.start)
    .map((r,i)=>{
      const hh=headerList[i]||{
        detail:"",
        time:""
      };

      const detail=
        hh.detail||
        r.meta?.detail||
        r.meta?.raceName||
        '';

      const dm=detail.match(
        /(\d{3,4})\s*(?:m\s*)?(Kum|Çim|Sentetik|Fiber Sand|Turf|Polytrack)\b/i
      );

      const eid=detail.match(
        /E\.?İ\.?D\.?\s*[:：]\s*([0-9.]+)/i
      );

      const meta={
        ...r.meta,
        city:r.city||r.meta?.city||'',
        detail,
        raceName:detail,
        time:hh.time||r.time||'',
        distance:dm
          ?Number(dm[1])
          :(r.meta?.distance||null),
        surface:dm
          ?dm[2]
          :(r.meta?.surface||''),
        eid:eid
          ?eid[1]
          :(r.meta?.eid||'')
      };

      return {
        no:i+1,
        time:meta.time,
        name:detail||r.name||`Koşu ${i+1}`,
        meta,
        horses:r.horses
      };
    });
}function parseDmyForWorker(s){
  const m=String(s||"").match(/(\d{1,2})[./](\d{1,2})[./](\d{4})/);
  if(!m)return 0;

  return new Date(
    Number(m[3]),
    Number(m[2])-1,
    Number(m[1])
  ).getTime();
}

function parseHistory(html){
  const out=[];
  const seen=new Set();

  const ts=balancedTables(html);

  for(const t of ts){
    const rows=[...t.html.matchAll(
      /<tr\b[^>]*>[\s\S]*?<\/tr>/gi
    )].map(m=>m[0]);

    if(!rows.length)continue;

    let header=null;
    let headerIndex=-1;

    for(let i=0;i<rows.length;i++){
      const c=cells(rows[i]);

      if(
        c.some(x=>/Tarih/i.test(x)) &&
        c.some(x=>/Derece|Süre|Sure/i.test(x)) &&
        c.some(x=>/Mesafe|Msf/i.test(x))
      ){
        header=c;
        headerIndex=i;
        break;
      }
    }

    if(!header)continue;

    const ix=re=>header.findIndex(x=>re.test(String(x)));

    const dateI=ix(/Tarih/i);
    const cityI=ix(/Hipodrom|Şehir|Sehir/i);
    const distI=ix(/Mesafe|Msf/i);
    const surfI=ix(/Pist|Zemin/i);
    const placeI=ix(/Sıra|Sira|Derece.*Sıra|Plase/i);
    const timeI=ix(/Derece|Süre|Sure/i);
    const weightI=ix(/Sıklet|Siklet|Kilo|Weight/i);
    const equipI=ix(/Takı|Taki|Ekipman/i);
    const jockeyI=ix(/Jokey|Jockey/i);
    const postI=ix(/Start|K|Kulvar/i);
    const oddsI=ix(/Gny|Ganyan|Odds/i);
    const groupI=ix(/Grup|Şart|Sart|Koşu Şartı|Kosu Sarti/i);
    const raceNameI=ix(/Koşu Adı|Kosu Adi|Yarış Adı|Yaris Adi/i);
    const trainerI=ix(/Antrenör|Antrenor|Trainer/i);
    const ownerI=ix(/Sahip|Owner/i);
    const hpI=ix(/^HP$|Handikap Puanı|Handikap Puani|Rating/i);
    const prizeI=ix(/İkramiye|Ikramiye|Prize/i);

    for(let i=headerIndex+1;i<rows.length;i++){
      const raw=rows[i];
      const c=cells(raw);

      if(c.length<Math.max(
        3,
        header.length-2
      ))continue;

      const date=dateI>=0?(c[dateI]||"").trim():"";
      const city=cityI>=0?(c[cityI]||"").trim():"";
      const dist=distI>=0?(c[distI]||"").trim():"";
      const surf=surfI>=0?(c[surfI]||"").trim():"";
      const place=placeI>=0?(c[placeI]||"").trim():"";
      const time=timeI>=0?(c[timeI]||"").trim():"";
      const rowText=c.join(" ");
      const conditionM=rowText.match(/\b(Nemli|Islak|Sulu|Ağır|Agir|Çamur|Camur|Normal)\b/i);
      const turfNM=rowText.match(/\bN\s*[=:]\s*(\d+(?:[.,]\d+)?)\b/i);

      if(!date||!time||!dist)continue;

      const M=num(
        String(dist)
          .replace(/[^\d.,]/g,"")
      );

      if(!M||M<=0)continue;

      if(!timeSec(time))continue;

      const key=[
        date,
        city,
        M,
        surf,
        place,
        time
      ].join("|");

      if(seen.has(key))continue;
      seen.add(key);

      out.push({
        date,
        city,
        distance:M,
        surface:surf,
        place,
        time,
        trackCondition:conditionM?conditionM[1]:"",
        turfN:turfNM?Number(String(turfNM[1]).replace(",", ".")):null,
        weight:weightI>=0?(c[weightI]||"").trim():"",
        equipment:equipI>=0?(c[equipI]||"").trim():"",
        jockey:jockeyI>=0?(c[jockeyI]||"").trim():"",
        post:postI>=0?(c[postI]||"").trim():"",
        odds:oddsI>=0?(c[oddsI]||"").trim():"",
        group:groupI>=0?(c[groupI]||"").trim():"",
        raceName:raceNameI>=0?(c[raceNameI]||"").trim():"",
        className:groupI>=0?(c[groupI]||"").trim():"",
        trainer:trainerI>=0?(c[trainerI]||"").trim():"",
        owner:ownerI>=0?(c[ownerI]||"").trim():"",
        hp:hpI>=0?(c[hpI]||"").trim():"",
        prize:prizeI>=0?(c[prizeI]||"").trim():"",
        s20:""
      });
    }
  }

  return out
    .filter(x=>x.time&&timeSec(x.time)!=null)
    .sort(
      (a,b)=>
        parseDmyForWorker(b.date)-
        parseDmyForWorker(a.date)
    )
    .slice(0,1000);
}

function timeSec(s){
  const m=String(s||"").match(
    /(\d+)\.(\d{2})\.(\d{2})/
  );

  if(!m)return null;

  return (+m[1])*60+
    (+m[2])+
    (+m[3])/100;
}

function num(s){
  const x=parseFloat(
    String(s||"")
      .replace(/\s/g,"")
      .replace(",",".")
  );

  return Number.isFinite(x)?x:null;
}

function normName(s){
  return String(s||"")
    .toLocaleUpperCase("tr-TR")
    .replace(/\([^)]*\)/g,"")
    .replace(/\s+/g," ")
    .trim();
}


/* =========================================================
   HIZ / TREF MODELİ
   ========================================================= */

const HIZ_MODEL={
  V_BAZ:{
    cim:0.0688,
    sentetik:0.0698,
    kum:0.0722
  },

  C_HIPODROM:{
    kum:{
      Bursa:1.000,
      Kocaeli:1.000,
      Adana:1.000,
      Izmir:1.007,
      Ankara:1.018,
      Sanliurfa:1.000,
      Elazig:1.025,
      Diyarbakir:1.025,
      Antalya:0.985
    },

    cim:{
      Bursa:1.000,
      Adana:1.000,
      Izmir:1.000,
      Istanbul:0.963,
      Ankara:1.012,
      Antalya:0.980
    },

    sentetik:{
      Istanbul:1.000
    }
  },

  C_SEHIR_CIM:{
    Istanbul:1.20,
    Ankara:1.10,
    Bursa:1.00,
    Adana:1.00,
    Izmir:0.90
  },

  C_SEHIR_KUM:{
    Izmir:1.20,
    Bursa:1.00,
    Kocaeli:1.00,
    Adana:1.00,
    Sanliurfa:1.00,
    Ankara:0.90,
    Elazig:0.85,
    Diyarbakir:0.85,
    Antalya:0.60,
    Istanbul:0.20
  },

  H:{
    kum:{
      Elazig:110,
      Diyarbakir:110,
      Izmir:108,
      Sanliurfa:106,
      Bursa:100,
      Adana:100,
      Kocaeli:100,
      Istanbul:100,
      Antalya:98,
      Ankara:96
    },

    sentetik:{
      Istanbul:100
    },

    cim:{
      Istanbul:105,
      Ankara:102,
      Bursa:100,
      Izmir:100,
      Adana:100,
      Antalya:98
    }
  }
};

function normCity(s){
  let x=String(s||"")
    .toLocaleLowerCase("tr-TR")
    .trim();

  x=x
    .replace(/ş/g,"s")
    .replace(/ğ/g,"g")
    .replace(/ı/g,"i")
    .replace(/ö/g,"o")
    .replace(/ü/g,"u")
    .replace(/ç/g,"c");

  if(/istanbul|veliefendi/.test(x))
    return "Istanbul";

  if(/ankara|75\.?\s*yil|75 yil/.test(x))
    return "Ankara";

  if(/bursa|osmangazi/.test(x))
    return "Bursa";

  if(/izmir|sirinyer/.test(x))
    return "Izmir";

  if(/kocaeli|kartepe/.test(x))
    return "Kocaeli";

  if(/adana|yesiloba/.test(x))
    return "Adana";

  if(/sanliurfa|sanli urfa|urfa/.test(x))
    return "Sanliurfa";

  if(/elazig/.test(x))
    return "Elazig";

  if(/diyarbakir/.test(x))
    return "Diyarbakir";

  if(/antalya/.test(x))
    return "Antalya";

  return "";
}

function normTrack(s){
  let x=String(s||"")
    .toLocaleLowerCase("tr-TR")
    .trim();

  x=x
    .replace(/ş/g,"s")
    .replace(/ğ/g,"g")
    .replace(/ı/g,"i")
    .replace(/ö/g,"o")
    .replace(/ü/g,"u")
    .replace(/ç/g,"c");

  if(
    /sentetik|synthetic|polytrack|fiber\s*sand/.test(x)
  )
    return "sentetik";

  if(
    /cim|turf/.test(x)
  )
    return "cim";

  if(
    /kum|dirt/.test(x)
  )
    return "kum";

  return "";
}


/* =========================================================
   TREF
   ========================================================= */

function trefFromFormula(distance,surface,city){
  const M=Number(distance);
  const zemin=normTrack(surface);
  const sehir=normCity(city);

  if(
    !Number.isFinite(M)||
    M<=0||
    !zemin||
    !sehir
  ){
    return null;
  }

  const Vbaz=HIZ_MODEL.V_BAZ[zemin];

  if(Vbaz==null)
    return null;

  const C=
    HIZ_MODEL.C_HIPODROM[zemin]?.[sehir];

  /*
   * Şehir + zemin katsayısı yoksa değer uydurulmaz.
   */
  if(C==null)
    return null;

  const Kmesafe=
    zemin==="kum" && M<=1400
      ?0.971
      :1.000;

  const tref=
    (M*Vbaz*C)*Kmesafe;

  return Number.isFinite(tref)
    ?tref
    :null;
}


/* =========================================================
   PİST DURUMU
   ========================================================= */

function parseTrackCondition(value){
  const x=String(value||"")
    .toLocaleLowerCase("tr-TR")
    .trim();

  if(!x)return "";

  if(
    /ağır|agir|çamur|camur/.test(x)
  )
    return "agir";

  if(
    /ıslak|islak|sulu|wet/.test(x)
  )
    return "islak";

  if(
    /nemli|nem/.test(x)
  )
    return "nemli";

  if(
    /normal|standart|iyi/.test(x)
  )
    return "normal";

  return "";
}

function extractTurfN(value){
  if(value==null)return null;

  const s=String(value)
    .replace(",",".")
    .trim();

  const m=s.match(
    /(?:N\s*[=:]?\s*)?(\d+(?:\.\d+)?)/
  );

  if(!m)return null;

  const n=Number(m[1]);

  return Number.isFinite(n)
    ?n
    :null;
}

function turfVariant(city,N){
  const sehir=normCity(city);

  const C=
    HIZ_MODEL.C_SEHIR_CIM[sehir];

  if(C==null||N==null)
    return null;

  return Math.max(
    0,
    (N-3.2)*100
  )*C;
}

function dirtSyntheticVariant(city,condition){
  const sehir=normCity(city);
  const durum=parseTrackCondition(condition);

  if(durum==="normal")
    return 0;

  const C=
    HIZ_MODEL.C_SEHIR_KUM[sehir];

  if(C==null||!durum)
    return null;

  let base=null;

  if(durum==="nemli")
    base=25;

  if(durum==="islak")
    base=45;

  if(durum==="agir")
    base=-20;

  if(base==null)
    return null;

  return base*C;
}


/* =========================================================
   GÜNÜN PİST VARYANTI
   ========================================================= */

function variantFromHistoryRace(race){
  if(!race)
    return {
      value:null,
      reason:"Koşu verisi yok"
    };

  const city=normCity(race.city);
  const surface=normTrack(race.surface);

  if(!city||!surface)
    return {
      value:null,
      reason:"Şehir veya zemin bilgisi eksik"
    };

  /*
   * ÇİM:
   * N değeri resmi veriden alınır.
   */
  if(surface==="cim"){
    const possibleN=[
      race.N,
      race.n,
      race.turfN,
      race.penetrometer,
      race.penetration,
      race.pistN,
      race.trackN
    ];

    let N=null;

    for(const x of possibleN){
      const n=extractTurfN(x);
      if(n!=null){
        N=n;
        break;
      }
    }

    const v=turfVariant(city,N);

    return {
      value:v,
      type:"cim",
      city,
      N,
      reason:v==null
        ?"Çim N değeri bulunamadı"
        :"Çim varyantı hesaplandı"
    };
  }

  /*
   * KUM / SENTETİK:
   * Resmi pist durumu üzerinden hesaplanır.
   */
  const condition=
    race.trackCondition||
    race.condition||
    race.pistDurumu||
    race.pist||
    race.zeminDurumu||
    race.weatherCondition||
    "";

  const v=dirtSyntheticVariant(
    city,
    condition
  );

  return {
    value:v,
    type:surface,
    city,
    condition:parseTrackCondition(condition),
    reason:v==null
      ?"Pist durumu bulunamadı"
      :"Kum/Sentetik varyantı hesaplandı"
  };
}


/* =========================================================
   HİPODROM GÜÇ ENDEKSİ
   ========================================================= */

function hipodromGuc(city,surface){
  const sehir=normCity(city);
  const zemin=normTrack(surface);

  if(!sehir||!zemin)
    return null;

  const table=
    HIZ_MODEL.H[zemin];

  if(!table)
    return null;

  const h=table[sehir];

  return h==null
    ?null
    :h;
}


/* =========================================================
   GERÇEK KOŞU KONTROLÜ
   ========================================================= */

function validRealRace(race){
  if(!race)
    return false;

  const t=timeSec(race.time);
  const M=num(race.distance);

  const city=normCity(race.city);
  const surface=normTrack(race.surface);

  if(t==null)
    return false;

  if(M==null||M<=0)
    return false;

  if(!city)
    return false;

  if(!surface)
    return false;

  if(
    /koşmaz|kosmaz|çekildi|cekildi|start almadı|start almadi/i
      .test(
        String(
          race.place||
          race.result||
          race.status||
          ""
        )
      )
  )
    return false;

  return true;
}

function latestRealRace(history){
  const arr=(history||[])
    .filter(validRealRace)
    .slice()
    .sort(
      (a,b)=>
        parseDmyForWorker(b.date)-
        parseDmyForWorker(a.date)
    );

  return arr.length
    ?arr[0]
    :null;
}


/* =========================================================
   HIZ HESAPLAMA
   ========================================================= */

function calculateSpeedRatings(
  history,
  targetCity,
  targetSurface,
  targetDistance
){
  const latest=latestRealRace(history);

  if(!latest){
    return {
      ok:false,
      hiz:null,
      hizPuani:null,
      score:null,
      error:"Gerçek derecesi bulunan son koşu bulunamadı"
    };
  }

  const sourceCity=normCity(latest.city);
  const sourceSurface=normTrack(latest.surface);
  const sourceDistance=num(latest.distance);
  const T_at=timeSec(latest.time);

  if(
    !sourceCity||
    !sourceSurface||
    !sourceDistance||
    T_at==null
  ){
    return {
      ok:false,
      hiz:null,
      hizPuani:null,
      score:null,
      error:"Son gerçek koşunun şehir/zemin/mesafe/derece verisi eksik",
      latest
    };
  }

  const Tref=trefFromFormula(
    sourceDistance,
    sourceSurface,
    sourceCity
  );

  if(Tref==null){
    return {
      ok:false,
      hiz:null,
      hizPuani:null,
      score:null,
      error:
        "Son koşunun Tref değeri için şehir+zemin katsayısı bulunamadı",
      latest,
      source:{
        city:sourceCity,
        surface:sourceSurface,
        distance:sourceDistance,
        time:latest.time
      }
    };
  }

  /*
   * S_ham
   */
  const S_ham=
    100+
    (Tref-T_at)*
    (22500/sourceDistance);

  /*
   * Günlük pist varyantı
   */
  const variant=
    variantFromHistoryRace(latest);

  /*
   * Resmi varyant bilgisi yoksa puan uydurma.
   */
  if(variant.value==null){
    return {
      ok:false,
      hiz:null,
      hizPuani:null,
      score:null,
      error:
        "Son koşunun resmi pist varyantı hesaplanamadı",
      latest,
      tref:Tref,
      S_ham,
      variant
    };
  }

  /*
   * Koşulan günün puanı:
   *
   * S_gun = S_ham + V_pist
   */
  const S_gun=
    S_ham+
    variant.value;

  /*
   * Hedef bilgiler
   */
  const hedefCity=
    normCity(
      targetCity||
      ""
    );

  const hedefSurface=
    normTrack(
      targetSurface||
      sourceSurface
    );

  const hedefDistance=
    num(
      targetDistance
    );

  /*
   * Hedef mesafe verilmemişse HIZ
   * için mesafe farkı uygulanmaz.
   *
   * H değeri şehir+zemin üzerinden alınır.
   */
  const H_kosulan=
    hipodromGuc(
      sourceCity,
      sourceSurface
    );

  const H_hedef=
    hedefCity
      ?hipodromGuc(
          hedefCity,
          hedefSurface
        )
      :H_kosulan;

  if(H_kosulan==null){
    return {
      ok:false,
      hiz:null,
      hizPuani:null,
      score:null,
      error:
        "Koşulan hipodrom için H güç endeksi bulunamadı",
      latest,
      tref:Tref,
      S_ham,
      variant,
      H_kosulan:null
    };
  }

  if(H_hedef==null){
    return {
      ok:false,
      hiz:null,
      hizPuani:null,
      score:null,
      error:
        "Hedef hipodrom için H güç endeksi bulunamadı",
      latest,
      tref:Tref,
      S_ham,
      variant,
      H_kosulan,
      hedefCity,
      hedefSurface
    };
  }

  /*
   * ŞEHİRLER ARASI ADAPTASYON
   *
   * S_adapte =
   * (S_ham + V_pist)
   * +
   * (H_hedef - H_koşulan)
   */
  const H_fark=
    H_hedef-
    H_kosulan;

  const S_adapte=
    S_gun+
    H_fark;

  return {
    ok:true,

    /*
     * HIZ = koşulan günün puanı
     * (S_ham + V_pist)
     */
    hiz:Number(
      S_gun.toFixed(2)
    ),

    /*
     * HIZ PUANI = hedefe adapte edilmiş net puan
     */
    hizPuani:Number(
      S_adapte.toFixed(2)
    ),

    score:Number(
      S_adapte.toFixed(2)
    ),

    latestRace:latest,

    source:{
      city:sourceCity,
      surface:sourceSurface,
      distance:sourceDistance,
      time:latest.time
    },

    target:{
      city:hedefCity||sourceCity,
      surface:hedefSurface||sourceSurface,
      distance:hedefDistance||null
    },

    Tref:Number(
      Tref.toFixed(3)
    ),

    T_at:Number(
      T_at.toFixed(2)
    ),

    S_ham:Number(
      S_ham.toFixed(2)
    ),

    V_pist:Number(
      variant.value.toFixed(2)
    ),

    S_gun:Number(
      S_gun.toFixed(2)
    ),

    H_kosulan,
    H_hedef,
    H_fark,

    formula:{
      tref:
        "Tref=(M×Vbaz×Chipodrom)×Kmesafe",
      sham:
        "S_ham=100+(Tref-T_at)×(22500/M)",
      sadapte:
        "S_adapte=(S_ham+V_pist)+(H_hedef-H_koşulan)"
    },

    coverage:100
  };
}


/* =========================================================
   ANA ANALİZ
   ========================================================= */

function analyze(
  horses,
  histories,
  workouts,
  raceMeta
){
  const active=
    (horses||[])
      .filter(
        h=>!isNR(h.name)
      );

  const targetCity=
    raceMeta?.city||
    "";

  const targetSurface=
    raceMeta?.surface||
    "";

  const targetDistance=
    raceMeta?.distance||
    null;

  const final=[];

  for(const h of active){
    const hist=
      histories?.[h.name]||
      histories?.[normName(h.name)]||
      [];

    const speed=
      calculateSpeedRatings(
        hist,
        targetCity,
        targetSurface,
        targetDistance
      );

    final.push({
      no:h.no,
      name:h.name,
      atId:h.atId||null,

      weight:h.weight||"",
      jockey:h.jockey||"",
      trainer:h.trainer||"",
      hp:h.hp||"",
      agf:h.agf||"",
      form:h.last6||"",

      hiz:speed.hiz,
      hizPuani:speed.hizPuani,
      score:speed.score,

      speedOk:speed.ok,
      speedError:speed.error||null,

      tref:speed.Tref??null,
      S_ham:speed.S_ham??null,
      V_pist:speed.V_pist??null,
      S_gun:speed.S_gun??null,

      H_kosulan:speed.H_kosulan??null,
      H_hedef:speed.H_hedef??null,
      H_fark:speed.H_fark??null,

      latestRace:speed.latestRace||null,
      source:speed.source||null,
      target:speed.target||null,

      /*
       * Eski analiz alanlarının istemciyi bozmaması için
       * korunması.
       */
      sameTrackCount:0,
      commonCount:0,
      history:(hist||[]).slice(0,8),
      workouts:(workouts?.[h.name]||[]).slice(0,5)
    });
  }

  return final.sort(
    (a,b)=>{
      const av=
        a.hizPuani==null
          ?-Infinity
          :a.hizPuani;

      const bv=
        b.hizPuani==null
          ?-Infinity
          :b.hizPuani;

      return bv-av;
    }
  );
}// ======================= VERİ ÇEKME =======================

async function fetchT(url){
  const ctrl=new AbortController();
  const timer=setTimeout(()=>ctrl.abort(),25000);

  try{
    const r=await fetch(url,{
      headers:{
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
        "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language":"tr-TR,tr;q=0.9,en;q=0.8",
        "Referer":"https://www.tjk.org/"
      },
      signal:ctrl.signal
    });

    return {
      status:r.status,
      text:await r.text()
    };

  }finally{
    clearTimeout(timer);
  }
}


// ======================= ŞEHİR KEŞFİ =======================

async function discoverCitiesForDate(date){

  const entries=Object.entries(CITY_IDS)
    .map(([name,id])=>({name,id}));

  const results=[];

  for(const {name,id} of entries){

    try{

      const d=await fetchDaily(date,name);

      if(d.races.length){

        results.push({
          name,
          id,
          raceCount:d.races.length,
          status:d.status,
          sourceUrl:d.url
        });

      }

    }catch(e){}
  }

  return results.length ? results : entries;
}


// ======================= GÜNLÜK PROGRAM =======================

async function fetchDaily(date,city){

  const d=encodeURIComponent(dateTR(date));
  const c=encodeURIComponent(city);
  const id=CITY_IDS[city]||9;

  // SADECE seçilen tarihe ait TJK günlük program endpointleri kullanılır.
  // `Era=today` fallbackleri kaldırıldı; aksi halde yarın/başka tarih seçildiğinde
  // TJK'nın bugünkü bağlamı döndürme ihtimali nedeniyle yanlış program kabul edilebiliyordu.
  const urls=[
    `${TJK}/TR/YarisSever/Info/Page/GunlukYarisProgrami?QueryParameter_Tarih=${d}&SehirAdi=${c}&SehirId=${id}`,
    `${TJK}/TR/YarisSever/Info/Sehir/GunlukYarisProgrami?QueryParameter_Tarih=${d}&SehirAdi=${c}&SehirId=${id}`
  ];

  let last={
    status:0,
    url:urls[0]
  };


  for(const url of urls){

    try{

      const r=await fetchT(url);

      last={
        status:r.status,
        url
      };

      if(r.status>=400)
        continue;


      const identity=cityIdentity(r.text,city);
      const races=parseDaily(r.text);

      if(!identity.ok){
        last.identity=identity;
        continue;
      }

      if(races.length){
        return {
          races,
          status:r.status,
          url,
          source:"GunlukYarisProgrami",
          identity
        };
      }

    }catch(e){

      last={
        status:0,
        url,
        error:String(e.message||e)
      };

    }

  }


  // Günlük program için Kayitlar fallback'i bilinçli olarak kullanılmıyor.
  // Kayıtlar endpoint'i farklı tarih/bağlam döndürebileceği için seçilen günün
  // günlük programına karışmaması gerekiyor.

  return {
    races:[],
    status:last.status,
    url:last.url
  };

}


// ======================= API =======================

export default {

  async fetch(req){

    if(req.method==="OPTIONS")
      return new Response("",{
        headers:CORS
      });


    const u=new URL(req.url);
    const p=u.pathname;
    const q=u.searchParams;


    try{


      // ======================= HEALTH =======================

      if(p==="/api/health"){

        return out({

          ok:true,

          service:
            "Race Intelligence TJK Gateway",

          version:
            "55.0-HIZ",

          worker:
            "fragrant-hat-ae48",

          time:
            new Date().toISOString()

        });

      }


      // ======================= CITIES =======================

      if(p==="/api/tjk/cities"){

        const date=
          q.get("date")||
          new Date().toISOString().slice(0,10);


        const entries=
          await discoverCitiesForDate(date);


        const results=
          await Promise.all(

            entries.map(
              async ({name,id})=>{

                try{

                  const d=
                    await fetchDaily(date,name);


                  return {

                    name,
                    id,

                    raceCount:
                      d.races.length,

                    horseCount:
                      d.races.reduce(
                        (a,r)=>
                          a+r.horses.length,
                        0
                      ),

                    status:
                      d.status,

                    sourceUrl:
                      d.url

                  };

                }catch(e){

                  return {

                    name,
                    id,

                    raceCount:0,
                    horseCount:0,

                    status:0,

                    error:
                      String(
                        e.message||e
                      )

                  };

                }

              }
            )

          );


        return out({

          ok:true,

          date,

          cities:
            results.filter(
              x=>x.raceCount>0
            ),

          checked:
            results

        });

      }


      // ======================= TJK DATA =======================

      if(p==="/api/tjk/data"){

        const date=
          q.get("date")||
          new Date().toISOString().slice(0,10);


        const city=
          q.get("city")||
          "Kocaeli";


        const daily=
          await fetchDaily(
            date,
            city
          );


        const races=
          daily.races;


        return out({

          ok:true,

          source:
            "TJK Günlük Yarış Programı",

          date,

          city,

          status:
            daily.status,

          sourceUrl:
            daily.url,

          raceCount:
            races.length,

          horseCount:
            races.reduce(
              (a,r)=>
                a+r.horses.length,
              0
            ),

          withAtId:
            races.reduce(
              (a,r)=>
                a+
                r.horses.filter(
                  h=>h.atId
                ).length,
              0
            ),

          races

        });

      }


      // ======================= HIZ =======================

      if(p==="/api/tjk/hiz"){

        const date=
          q.get("date")||
          new Date().toISOString().slice(0,10);


        const city=
          q.get("city")||
          "Kocaeli";


        const raceNo=
          Number(
            q.get("race")||
            q.get("kosu")||
            0
          );


        const targetDistance=
          Number(
            q.get("distance")||
            0
          )||null;


        const targetSurface=
          q.get("surface")||
          "";


        const daily=
          await fetchDaily(
            date,
            city
          );


        let race=
          raceNo>0
          ? daily.races.find(
              x=>Number(x.no)===raceNo
            )
          : null;


        if(!race && targetDistance){

          race=
            daily.races.find(
              x=>
                Number(x.meta?.distance)
                ===targetDistance
                &&
                (
                  !targetSurface
                  ||
                  normTrack(
                    x.meta?.surface
                  )
                  ===
                  normTrack(
                    targetSurface
                  )
                )
            )||null;

        }


        if(!race)
          race=
            daily.races[0]||null;


        if(!race){

          return out({

            ok:false,

            error:
              "Yarış bulunamadı",

            date,
            city,

            status:
              daily.status,

            sourceUrl:
              daily.url

          },404);

        }


        const horses=
          race.horses||[];


        const histories={};
        const errors={};


        await Promise.all(

          horses
            .filter(
              h=>
                h.atId &&
                !isNR(h.name)
            )
            .map(
              async h=>{

                const urls=[

                  `${TJK}/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri?1=1&Era=today&QueryParameter_AtId=${encodeURIComponent(h.atId)}`,

                  `${TJK}/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId=${encodeURIComponent(h.atId)}`,

                  `${TJK}/TR/map/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId=${encodeURIComponent(h.atId)}`,

                  `${TJK}/TR/YarisSever/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId=${encodeURIComponent(h.atId)}`

                ];


                const cand=[];


                for(const url of urls){

                  try{

                    const r=
                      await fetchT(url);


                    const parsed=
                      parseHistory(
                        r.text
                      );


                    if(parsed.length){

                      cand.push({

                        parsed,

                        score:
                          parsed.reduce(
                            (n,x)=>
                              n+
                              (x.surface?2:0)+
                              (x.time?2:0)+
                              (x.city?1:0),
                            0
                          ),

                        status:
                          r.status

                      });

                    }

                  }catch(e){

                    errors[h.name]=
                      String(
                        e?.message||e
                      );

                  }

                }


                cand.sort(
                  (a,b)=>
                    b.score-a.score
                );


                histories[h.name]=
                  cand[0]?.parsed||[];

              }
            )
        );


        const ratings=
          analyze(
            horses,
            histories,
            {},
            {
              ...race.meta,
              city
            }
          );


        return out({

          ok:true,

          model:
            "HIZ-vNext",

          date,

          city,

          race:{

            no:race.no,

            time:race.time,

            meta:{
              ...race.meta,
              city
            }

          },

          raceCount:
            daily.races.length,

          horseCount:
            horses.length,

          ratings,

          histories,

          errors

        });

      }


      // ======================= TEK AT =======================

      if(p==="/api/tjk/horse"){

        const atId=
          q.get("atId");


        if(!atId){

          return out({

            ok:false,

            error:
              "atId gerekli"

          },400);

        }


        const url=
          `${TJK}/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId=${encodeURIComponent(atId)}`;


        const r=
          await fetchT(url);


        const history=
          parseHistory(
            r.text
          );


        return out({

          ok:r.status<400,

          status:r.status,

          atId,

          history

        });

      }


      // ======================= İDMAN =======================

      if(p==="/api/tjk/workouts"){

        const horse=
          q.get("horse");


        if(!horse){

          return out({

            ok:false,

            error:
              "horse gerekli"

          },400);

        }


        const url=
          `${TJK}/TR/YarisSever/Query/Page/IdmanIstatistikleri?1=1&QueryParameter_ATADI=${encodeURIComponent(horse)}`;


        const r=
          await fetchT(url);


        let workouts=
          parseWorkouts(
            r.text
          );


        if(
          workouts.some(
            x=>x.horse
          )
        ){

          const hn=
            normName(horse);


          const f=
            workouts.filter(
              x=>
                normName(x.horse)
                ===hn
            );


          if(f.length)
            workouts=f;

        }


        return out({

          ok:r.status<400,

          status:r.status,

          horse,

          workouts

        });

      }


      // ======================= HORSE DATA =======================

      if(p==="/api/tjk/horsedata"){

        const atId=
          q.get("atId");


        const horse=
          q.get("horse");


        if(!atId && !horse){

          return out({

            ok:false,

            error:
              "atId veya horse gerekli"

          },400);

        }


        let history=[];


        if(atId){

          const url=
            `${TJK}/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId=${encodeURIComponent(atId)}`;


          const r=
            await fetchT(url);


          history=
            parseHistory(
              r.text
            );

        }


        return out({

          ok:true,

          atId:atId||null,

          horse:horse||null,

          history

        });

      }      // ======================= HORSE DATA DEBUG =======================

      if(p==="/api/tjk/horsedata-debug"){

        const atId=
          q.get("atId");


        if(!atId){

          return out({

            ok:false,

            error:
              "atId gerekli"

          },400);

        }


        const urls=[

          `${TJK}/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri?1=1&Era=today&QueryParameter_AtId=${encodeURIComponent(atId)}`,

          `${TJK}/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId=${encodeURIComponent(atId)}`,

          `${TJK}/TR/map/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId=${encodeURIComponent(atId)}`,

          `${TJK}/TR/YarisSever/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId=${encodeURIComponent(atId)}`

        ];


        const results=[];


        for(const url of urls){

          try{

            const r=
              await fetchT(url);


            const history=
              parseHistory(
                r.text
              );


            results.push({

              url,

              status:
                r.status,

              length:
                r.text.length,

              historyCount:
                history.length,

              history

            });

          }catch(e){

            results.push({

              url,

              status:0,

              error:
                String(
                  e?.message||e
                )

            });

          }

        }


        return out({

          ok:true,

          atId,

          results

        });

      }


      // ======================= ANALYZE =======================

      if(p==="/api/tjk/analyze"){

        const date=
          q.get("date")||
          new Date().toISOString().slice(0,10);


        const city=
          q.get("city")||
          "Kocaeli";


        const raceNo=
          Number(
            q.get("race")||
            q.get("kosu")||
            0
          );


        const daily=
          await fetchDaily(
            date,
            city
          );


        let races=
          daily.races;


        if(raceNo){

          races=
            races.filter(
              r=>
                Number(r.no)
                ===raceNo
            );

        }


        const result=[];


        for(const race of races){

          const horses=
            race.horses||[];


          const histories={};


          await Promise.all(

            horses
              .filter(
                h=>
                  h.atId &&
                  !isNR(h.name)
              )
              .map(
                async h=>{

                  const urls=[

                    `${TJK}/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri?1=1&Era=today&QueryParameter_AtId=${encodeURIComponent(h.atId)}`,

                    `${TJK}/TR/kurumsal/Query/ConnectedPage/AtKosuBilgileri?1=1&QueryParameter_AtId=${encodeURIComponent(h.atId)}`

                  ];


                  const candidates=[];


                  for(
                    const url of urls
                  ){

                    try{

                      const rr=
                        await fetchT(url);


                      const hh=
                        parseHistory(
                          rr.text
                        );


                      if(hh.length){

                        candidates.push({
                          history:hh,
                          score:hh.reduce(
                            (n,x)=>
                              n+
                              (x.time?2:0)+
                              (x.distance?2:0)+
                              (x.city?1:0)+
                              (x.surface?1:0),
                            0
                          )
                        });

                      }

                    }catch(e){}

                  }


                  candidates.sort(
                    (a,b)=>
                      b.score-a.score
                  );


                  histories[h.name]=
                    candidates[0]?.history||[];

                }
              )
          );


          const ratings=
            analyze(
              horses,
              histories,
              {},
              {
                ...race.meta,
                city
              }
            );


          result.push({

            no:race.no,

            time:race.time,

            meta:{
              ...race.meta,
              city
            },

            horses:ratings

          });

        }


        return out({

          ok:true,

          model:
            "HIZ-vNext",

          date,

          city,

          races:result

        });

      }


      // ======================= RAW =======================

      if(p==="/api/tjk/raw"){

        const date=
          q.get("date")||
          new Date().toISOString().slice(0,10);


        const city=
          q.get("city")||
          "Kocaeli";


        const daily=
          await fetchDaily(
            date,
            city
          );


        return out({

          ok:true,

          date,

          city,

          status:
            daily.status,

          source:
            daily.source||null,

          sourceUrl:
            daily.url,

          races:
            daily.races

        });

      }


      // ======================= 404 =======================

      return out({

        ok:false,

        error:
          "Endpoint bulunamadı",

        path:p

      },404);


    }catch(e){

      return out({

        ok:false,

        error:
          String(
            e?.message||
            e||
            "Unknown error"
          ),

        path:p

      },500);

    }

  }

};
