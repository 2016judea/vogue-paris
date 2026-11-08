// Mirror Vogue Paris page scans from Gallica IIIF into mirror/<ark>/pNNN.jpg.
// Gallica sits behind Cloudflare: it blocks curl and HeadlessChrome UAs and blocks
// cross-site image hotlinking, but a headless Chrome with a normal UA, fetching
// same-origin from a gallica.bnf.fr tab, gets through. It also throttles bursts:
// a throttled reply is an HTML page instead of JSON/JPEG, so we back off and retry.
// Resumable: skips files already on disk. Usage: node mirror.js <port> <issues.json> <outdir>
const p=require('puppeteer-core'),fs=require('fs'),path=require('path');
const [port,issuesPath,outdir]=process.argv.slice(2);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const WIDTH=1600, GAP=+(process.env.GAP||900);
(async()=>{
 const b=await p.connect({browserURL:'http://localhost:'+port,protocolTimeout:120000});
 const pg=(await b.pages()).find(x=>x.url().includes('gallica'));
 const issues=JSON.parse(fs.readFileSync(issuesPath));
 let backoff=0;
 const get=async(url,kind)=>{
  for(let a=0;a<12;a++){
   const r=await pg.evaluate(async(u,kind)=>{try{const x=await fetch(u);const ct=x.headers.get('content-type')||'';
     if(!x.ok||ct.includes('html'))return{err:x.status+' '+ct};
     if(kind==='json')return{json:await x.text()};
     const buf=new Uint8Array(await x.arrayBuffer());let s='';for(let i=0;i<buf.length;i+=32768)s+=String.fromCharCode.apply(null,buf.subarray(i,i+32768));return{b64:btoa(s)};
    }catch(e){return{err:String(e)}}},url,kind);
   if(!r.err){backoff=Math.max(0,backoff-1);return r;}
   backoff++;const wait=Math.min(600000,15000*2**Math.min(backoff,5));
   console.log(new Date().toISOString(),'throttled',r.err,'wait',wait/1000,'s');await sleep(wait);
  }
  throw new Error('gave up '+url);
 };
 for(const it of issues){
  const dir=path.join(outdir,it.ark);fs.mkdirSync(dir,{recursive:true});
  const mf=path.join(dir,'manifest.json');
  if(!fs.existsSync(mf)){const r=await get(`/iiif/ark:/12148/${it.ark}/manifest.json`,'json');
   const m=JSON.parse(r.json);const pages=m.sequences[0].canvases.map(c=>({w:c.width,h:c.height,label:c.label}));
   fs.writeFileSync(mf,JSON.stringify({ark:it.ark,pages}));await sleep(GAP);}
  const {pages}=JSON.parse(fs.readFileSync(mf));
  let got=0;const todo=[];
  for(let n=it.start;n<=pages.length;n++){const f=path.join(dir,`p${String(n).padStart(3,'0')}.jpg`);if(!fs.existsSync(f))todo.push([n,f]);}
  const CONC=+(process.env.CONC||3);
  await Promise.all(Array.from({length:CONC},async()=>{while(todo.length){const [n,f]=todo.shift();
   const r=await get(`/iiif/ark:/12148/${it.ark}/f${n}/full/${WIDTH},/0/default.jpg`,'img');
   fs.writeFileSync(f+'.part',Buffer.from(r.b64,'base64'));fs.renameSync(f+'.part',f);got++;await sleep(GAP);}}));
  fs.writeFileSync(path.join(dir,'DONE'),'');
  console.log(new Date().toISOString(),'done',it.date,it.ark,'pages',pages.length-it.start+1,'new',got);
 }
 console.log('ALL DONE');process.exit(0);
})().catch(e=>{console.error('FATAL',e);process.exit(1)});
