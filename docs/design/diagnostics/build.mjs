// Compose the diagnostics design artboards.
//
// Each parts/<Name>.body.html fragment becomes <Name>.dc.html, wrapped in the
// Design Component shell with the app's real stylesheet inlined — paper.css
// verbatim (minus its @font-face import, which becomes a <link>) plus
// extra.css. Nothing here invents a value: the artboards and the running app
// read the same CSS, so they cannot drift.
//
//   node build.mjs
import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..", "..");

const FONTS =
  "https://fonts.googleapis.com/css2?family=Libre+Caslon+Text:ital,wght@0,400;0,700;1,400" +
  "&family=Archivo:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap";

const paper = readFileSync(join(root, "static", "css", "paper.css"), "utf8")
  .split("\n")
  .filter((line) => !line.startsWith("@import"))
  .join("\n");
const extra = readFileSync(join(here, "extra.css"), "utf8");

// Per-artboard tweak chips. Deliberately few: each is a switch worth seeing
// both sides of, never a copy field.
const PROPS = {
  Main: {
    props: { role: { editor: "enum", options: ["teacher", "staff"], default: "staff" } },
    logic: "const staff = (this.props.role ?? 'staff') === 'staff'; return { isStaff: staff, isTeacher: !staff };",
  },
  Register: {
    props: { windowOpen: { editor: "boolean", default: true } },
    logic: "const open = this.props.windowOpen ?? true; return { open, shut: !open };",
  },
};

for (const file of readdirSync(join(here, "parts")).sort()) {
  const name = file.replace(/\.body\.html$/, "");
  if (name === file) continue;
  const body = readFileSync(join(here, "parts", file), "utf8").trim();
  const { props = {}, logic = "return {};" } = PROPS[name] ?? {};
  const attr = JSON.stringify(props).replace(/&/g, "&amp;").replace(/'/g, "&#39;");

  writeFileSync(
    join(here, `${name}.dc.html`),
    `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <link rel="stylesheet" href="${FONTS}">
  <style>
${paper}
${extra}
  </style>
</helmet>
${body}
</x-dc>
<script data-dc-script data-props='${attr}'>
class Component extends DCLogic {
  renderVals() {
    ${logic}
  }
}
</script>
</body>
</html>
`,
    "utf8",
  );
  console.log(`${name}.dc.html`);
}
