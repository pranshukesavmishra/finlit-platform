import { chromium } from "playwright";
import fs from "fs";
const O="/tmp/claude-0/-home-user/0586bed0-3a1c-55ff-bd33-4b7b6328f0db/scratchpad/shots/st2/"; fs.mkdirSync(O,{recursive:true});
const th=process.argv[2]||"dark";
const br=await chromium.launch(); const c=await br.newContext({viewport:{width:1440,height:900}}); await c.addInitScript((t)=>{localStorage.setItem("finlit-theme",t);localStorage.setItem("finlit-plan","gold")},th);
const p=await c.newPage(); p.on("pageerror",e=>console.log("ERR",e));
await p.goto("http://127.0.0.1:4180/finlit-platform/stocks/RELIANCE",{waitUntil:"networkidle"});
await p.evaluate(async()=>{for(let y=0;y<document.body.scrollHeight;y+=400){scrollTo(0,y);await new Promise(r=>setTimeout(r,120))}scrollTo(0,0)}); await p.waitForTimeout(2500);
for (const id of ["price","financials","ownership","dividends","method"]) { const s=p.locator(`section.block:has(#${id})`); await s.scrollIntoViewIfNeeded(); await p.waitForTimeout(1800); await s.screenshot({path:O+`${th}_${id}.png`}); }
await p.evaluate(()=>scrollTo(0,0)); await p.waitForTimeout(500); await p.locator(".dial").first().screenshot({path:O+`${th}_dial.png`});
await br.close();
