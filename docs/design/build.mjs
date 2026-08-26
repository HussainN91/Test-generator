// Assembles the .dc.html artboards from static/css/paper.css + parts/<Name>.body.html.
// Every artboard is self-contained; this only keeps the shared CSS in one place.
// Run:  node build.mjs
import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(here, "..", "..", "static", "css", "paper.css"), "utf8");

const MARK = `<svg class="mark" width="30" height="34" viewBox="0 0 30 34" fill="none" style="color: var(--ink)" aria-hidden="true">
        <rect x="1" y="1" width="28" height="32" stroke="currentColor" stroke-width="1.5"></rect>
        <path d="M7 9h9M7 15h9M7 21h9M7 27h9" stroke="currentColor" stroke-width="1.5"></path>
        <circle cx="23" cy="9" r="2.6" fill="currentColor"></circle>
        <circle cx="23" cy="15" r="2.6" stroke="currentColor" stroke-width="1.2"></circle>
        <circle cx="23" cy="21" r="2.6" stroke="currentColor" stroke-width="1.2"></circle>
        <circle cx="23" cy="27" r="2.6" fill="currentColor"></circle>
      </svg>`;

const mast = (active) => `<div class="mast">
    <div class="mast-in">
      ${MARK}
      <span class="wordmark">English Test Generator<span class="sm">ITEM BANK &#183; ASSEMBLY &#183; EXPORT</span></span>
      <nav>
        <a href="#"${active === "builder" ? ' class="on"' : ""}>Test builder</a>
        <a href="#"${active === "coverage" ? ' class="on"' : ""}>Bank coverage</a>
        <a href="#">Admin</a>
        <span class="who">M.ANNAHS</span>
        <a href="#" class="btn ghost sm" style="border-color: var(--rule)">Log out</a>
      </nav>
    </div>
  </div>
  <div class="hair"></div>`;

const page = ({ body, w, h, extra }) => `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <style>
${css}${extra ? "\n" + extra : ""}
  </style>
</helmet>
${body.trimEnd()}
</x-dc>
<script data-dc-script data-props='{"$preview":{"width":${w},"height":${h}}}'>
class Component extends DCLogic {
  renderVals() {
    return {};
  }
}
</script>
</body>
</html>
`;

// frame size per artboard, mirrored into canvas.json
const SIZES = {
  Main: [1280, 1490],
  Coverage: [1280, 2310],
  Preview: [1280, 1740],
  SignIn: [1280, 820],
  PrintSheet: [794, 1123],
  System: [1280, 1830],
};

let n = 0;
for (const file of readdirSync(join(here, "parts"))) {
  const m = /^(.+)\.body\.html$/.exec(file);
  if (!m) continue;
  const name = m[1];
  const [w, h] = SIZES[name] || [1280, 900];
  let body = readFileSync(join(here, "parts", file), "utf8");
  body = body.replace(/<!--MAST:(\w+)-->/g, (_, a) => mast(a));
  const EXTRA = {
    SignIn: ["../../static/css/paper-gate.css"],
    PrintSheet: ["../../static/css/paper-print.css"],
    System: ["parts/System.css"],
  };
  const extra = (EXTRA[name] || [])
    .map((p) => readFileSync(join(here, p), "utf8"))
    .join("\n");
  writeFileSync(join(here, `${name}.dc.html`), page({ body, w, h, extra }));
  n++;
  console.log(`built ${name}.dc.html  ${w}x${h}`);
}
console.log(`${n} artboards`);
