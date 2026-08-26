import { readFileSync, writeFileSync } from "node:fs";
const css = readFileSync("../../static/css/paper.css","utf8");
const names = process.argv.slice(2);
let out = `<!doctype html><html><head><meta charset="utf-8"><style>${css}\n`;
const EX={SignIn:["../../static/css/paper-gate.css"],PrintSheet:["../../static/css/paper-print.css"],System:["parts/System.css"]};
for (const n of names) for (const p of (EX[n]||[])) out += readFileSync(p,"utf8");
out += `\nbody{background-color:#8a8578}.frame{background-color:var(--paper);background-image:var(--grain);margin:0 auto 40px;box-sizing:border-box;overflow:hidden}</style></head><body>`;
const W = {Main:1330,Coverage:1530,Preview:1360,SignIn:820,PrintSheet:1123,System:1560};
for (const n of names) {
  let b = readFileSync(`parts/${n}.body.html`,"utf8");
  b = b.replace(/<!--MAST:(\w+)-->/g, (_,a)=>MAST(a));
  const w = n==="PrintSheet"?794:1280;
  out += `<div class="frame" style="width:${w}px">${b}</div>`;
}
out += `</body></html>`;
function MAST(active){return `<div class="mast"><div class="mast-in">
<svg class="mark" width="30" height="34" viewBox="0 0 30 34" fill="none" style="color:var(--ink)"><rect x="1" y="1" width="28" height="32" stroke="currentColor" stroke-width="1.5"></rect><path d="M7 9h9M7 15h9M7 21h9M7 27h9" stroke="currentColor" stroke-width="1.5"></path><circle cx="23" cy="9" r="2.6" fill="currentColor"></circle><circle cx="23" cy="15" r="2.6" stroke="currentColor" stroke-width="1.2"></circle><circle cx="23" cy="21" r="2.6" stroke="currentColor" stroke-width="1.2"></circle><circle cx="23" cy="27" r="2.6" fill="currentColor"></circle></svg>
<span class="wordmark">English Test Generator<span class="sm">ITEM BANK &#183; ASSEMBLY &#183; EXPORT</span></span>
<nav><a href="#"${active==="builder"?' class="on"':''}>Test builder</a><a href="#"${active==="coverage"?' class="on"':''}>Bank coverage</a><a href="#">Admin</a><span class="who">M.ANNAHS</span><a href="#" class="btn ghost sm" style="border-color:var(--rule)">Log out</a></nav>
</div></div><div class="hair"></div>`;}
writeFileSync("preview.html", out);
console.log("wrote preview.html", names.join(","));
