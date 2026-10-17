import { chromium } from "playwright";
import fs from "fs"; const O="/tmp/claude-0/-home-user/0586bed0-3a1c-55ff-bd33-4b7b6328f0db/scratchpad/shots/iv/"; fs.mkdirSync(O,{recursive:true});
const br=await chromium.launch();
for (const th of ["light","dark"]) { const c=await br.newContext({viewport:{width:1440,height:1000}}); await c.addInitScript((t)=>{localStorage.setItem("finlit-theme",t);localStorage.setItem("finlit-plan","gold")},th);
const p=await c.newPage(); p.on("pageerror",e=>console.log("ERR",e));
await p.goto("http://127.0.0.1:4180/finlit-platform/",{waitUntil:"networkidle"}); await p.waitForTimeout(1500); await p.screenshot({path:O+`${th}_home.png`});
await p.goto("http://127.0.0.1:4180/finlit-platform/stocks/RELIANCE",{waitUntil:"networkidle"});
await p.evaluate(async()=>{for(let y=0;y<document.body.scrollHeight;y+=400){scrollTo(0,y);await new Promise(r=>setTimeout(r,70))};scrollTo(0,0)}); await p.waitForTimeout(1200); await p.screenshot({path:O+`${th}_stock.png`});
const go=async(sel,off,name)=>{await p.evaluate(([s,o])=>{const t=document.querySelector(s); scrollTo(0,t.getBoundingClientRect().top+scrollY+o)},[sel,off]); await p.waitForTimeout(1300); await p.screenshot({path:O+`${th}_${name}.png`});};
await go("#ratios",-130,"ratios"); await go("#ownership",-130,"own"); await go("#insights",-130,"ins"); await go("#dividends",-130,"div");
await br.close(); }
