#!/usr/bin/env node
/**
 * Builds app/static/js/lucide-icons.min.js — a minimal subset of the lucide
 * icon library containing only the icons the app actually renders.
 *
 * Icon definitions are extracted verbatim from the installed lucide UMD
 * bundle (node_modules/lucide/dist/umd/lucide.min.js) so rendering stays
 * byte-identical to the full library. The runtime reproduces lucide's
 * `createIcons` semantics exactly, keeping the same `window.lucide` API so
 * all existing call sites (base.html DOMContentLoaded init, app.js toasts,
 * per-page inline re-inits) work unchanged.
 *
 * The icon set is discovered automatically — a new data-lucide="..." added
 * to any template is picked up on the next run, with no manual list to keep
 * in sync:
 *   - app/templates (all .html files)  data-lucide="..." literals (markup and
 *                               inline <script> blocks are both scanned)
 *   - app/static/js/*.js        data-lucide="..." literals and
 *                               setAttribute("data-lucide", "...") calls
 *   - DYNAMIC_ICONS below       icon names built at runtime (the toast
 *                               themes in app.js) that no literal names
 * Names are deduped, sorted, then validated against lucide's exports.
 *
 * Fail-fast: any referenced icon that does not exist in the installed lucide
 * bundle aborts the build with the offending name(s) and their source
 * files. Icons bundled by a previous run that are no longer referenced
 * anywhere only warn — deliberate inactive icons keep shipping.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const UMD_PATH = path.join(ROOT, "node_modules/lucide/dist/umd/lucide.min.js");
const LUCIDE_PKG_PATH = path.join(ROOT, "node_modules/lucide/package.json");
const OUT_PATH = path.join(ROOT, "app/static/js/lucide-icons.min.js");
const TEMPLATES_DIR = path.join(ROOT, "app/templates");
const STATIC_JS_DIR = path.join(ROOT, "app/static/js");

// Icons created at runtime with a variable attribute value (app.js toast
// themes: success/error/info/warning) that no scanner literal can see.
const DYNAMIC_ICONS = ["check-circle", "alert-circle", "info", "alert-triangle"];

const kebabToPascal = (name) =>
  name.replace(/(\w)(\w*)(_|-|\s*)/g, (_, c, p) => c.toUpperCase() + p.toLowerCase());

/** Recursively list files under `dir` with the given extension, sorted for determinism. */
function walkFiles(dir, ext) {
  const out = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) =>
    a.name.localeCompare(b.name)
  );
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walkFiles(full, ext));
    else if (entry.name.endsWith(ext)) out.push(full);
  }
  return out;
}

/** Scan templates + JS for every icon name the app references. */
function scanIconReferences() {
  const found = new Map(); // kebab name -> Set<source path relative to ROOT>
  const record = (name, file) => {
    if (!name) return;
    if (!found.has(name)) found.set(name, new Set());
    found.get(name).add(path.relative(ROOT, file));
  };

  // Templates: markup and inline <script> blocks (whole-file regex covers both)
  for (const file of walkFiles(TEMPLATES_DIR, ".html")) {
    const text = fs.readFileSync(file, "utf8");
    for (const m of text.matchAll(/data-lucide="([^"]+)"/g)) record(m[1], file);
  }

  // JS: attribute-value literals + setAttribute("data-lucide", "name") calls.
  // lucide-icons.min.js is the generator's own output — never scanned.
  for (const file of walkFiles(STATIC_JS_DIR, ".js")) {
    if (path.basename(file) === "lucide-icons.min.js") continue;
    const text = fs.readFileSync(file, "utf8");
    for (const m of text.matchAll(/data-lucide\s*=\s*"([^"]+)"/g)) record(m[1], file);
    for (const m of text.matchAll(/setAttribute\(\s*["']data-lucide["']\s*,\s*["']([^"']+)["']\s*\)/g))
      record(m[1], file);
  }

  for (const name of DYNAMIC_ICONS) record(name, "app/static/js/app.js (DYNAMIC_ICONS)");
  return found;
}

/** Extract a balanced [...] slice from `source` starting at `startIndex` (must be '['). */
function extractBalanced(source, startIndex) {
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let i = startIndex; i < source.length; i++) {
    const ch = source[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === "\\") escaped = true;
      else if (ch === '"') inString = false;
    } else if (ch === '"') {
      inString = true;
    } else if (ch === "[") {
      depth++;
    } else if (ch === "]") {
      depth--;
      if (depth === 0) return source.slice(startIndex, i + 1);
    }
  }
  throw new Error("unbalanced brackets");
}

function main() {
  const umd = fs.readFileSync(UMD_PATH, "utf8");
  const lucideVersion = JSON.parse(fs.readFileSync(LUCIDE_PKG_PATH, "utf8")).version;

  // lucide export assignments: a.PascalName=minifiedVar,
  const assignments = new Map();
  const assignRe = /a\.([A-Za-z0-9$_]+)=([A-Za-z0-9$_]+),/g;
  let m;
  while ((m = assignRe.exec(umd)) !== null) assignments.set(m[1], m[2]);

  const scanned = scanIconReferences();
  const names = [...scanned.keys()].sort();
  if (names.length === 0) {
    throw new Error(
      `no data-lucide references found under ${path.relative(ROOT, TEMPLATES_DIR)} or ` +
        `${path.relative(ROOT, STATIC_JS_DIR)} — scan path misconfigured?`
    );
  }

  // Fail-fast (a): referenced icon missing from lucide's exports.
  const missing = names.filter((name) => !assignments.has(kebabToPascal(name)));
  if (missing.length > 0) {
    const detail = missing
      .map((name) => `"${name}" (${kebabToPascal(name)}) in ${[...scanned.get(name)].join(", ")}`)
      .join("; ");
    throw new Error(`lucide export not found for: ${detail}`);
  }

  // Warn (b): icons in the previous bundle that nothing references anymore.
  if (fs.existsSync(OUT_PATH)) {
    const prevBundle = fs.readFileSync(OUT_PATH, "utf8");
    const prevPascal = [...prevBundle.matchAll(/"([A-Za-z0-9]+)":\["svg"/g)].map((match) => match[1]);
    const scannedPascal = new Set(names.map(kebabToPascal));
    for (const pascal of prevPascal) {
      if (!scannedPascal.has(pascal)) {
        console.warn(
          `warn: icon "${pascal}" from the previous bundle is no longer referenced ` +
            `anywhere — it will be dropped. Keep an explicit DYNAMIC_ICONS entry if intentional.`
        );
      }
    }
  }

  const definitions = new Map(); // var name -> '["svg",h,[...]]' source text

  const resolveVar = (varName, seen = new Set()) => {
    if (seen.has(varName)) throw new Error(`circular alias for ${varName}`);
    seen.add(varName);
    if (definitions.has(varName)) return definitions.get(varName);

    // Direct definition: VAR=["svg",h,[...]]
    let idx = 0;
    while ((idx = umd.indexOf(varName + "=", idx)) !== -1) {
      if (umd[idx + varName.length + 1] === "[") {
        const content = extractBalanced(umd, idx + varName.length + 1);
        if (content.startsWith('["svg"')) {
          definitions.set(varName, content);
          return content;
        }
      }
      idx += varName.length + 1;
    }
    // Alias to another variable (e.g. legacy name -> canonical definition)
    const aliasRe = new RegExp("\\b" + varName.replace(/\$/g, "\\$") + "=([A-Za-z0-9$_]+)");
    const alias = aliasRe.exec(umd);
    if (alias && alias[1] !== varName) return resolveVar(alias[1], seen);
    throw new Error(`definition not found for ${varName}`);
  };

  const entries = [];
  for (const name of names) {
    const pascal = kebabToPascal(name);
    const varName = assignments.get(pascal);
    entries.push(`${JSON.stringify(pascal)}:${resolveVar(varName)}`);
  }

  // Runtime mirrors the installed lucide v<version> UMD semantics exactly:
  // class merge order "lucide lucide-{name} {element classes} {attrs class}",
  // attrs merge {...iconDefaults, data-lucide, ...options.attrs, ...elementAttrs},
  // and the deprecated [icon-name] fallback inside createIcons.
  const runtime = [
    'var h={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor","stroke-width":2,"stroke-linecap":"round","stroke-linejoin":"round"};',
    `var ICONS={${entries.join(",")}};`,
    'function createElement(tag,attrs,children){children=children||[];var el=document.createElementNS("http://www.w3.org/2000/svg",tag);Object.keys(attrs).forEach(function(k){el.setAttribute(k,String(attrs[k]));});children.forEach(function(child){el.appendChild(createElement(child[0],child[1],child[2]));});return el;}',
    'function getAttrs(el){return Array.from(el.attributes).reduce(function(acc,a){acc[a.name]=a.value;return acc;},{});}',
    'function classListOf(v){if(typeof v==="string")return v.split(" ");if(!v||!v.class)return[];if(typeof v.class==="string")return v.class.split(" ");if(Array.isArray(v.class))return v.class;return[];}',
    'function mergeClasses(sources){return sources.flatMap(classListOf).map(function(c){return c.trim();}).filter(Boolean).filter(function(c,i,a){return a.indexOf(c)===i;}).join(" ");}',
    'function kebabToPascal(name){return name.replace(/(\\w)(\\w*)(_|-|\\s*)/g,function(match,first,rest){return first.toUpperCase()+rest.toLowerCase();});}',
    'function replaceElement(el,opts){var name=el.getAttribute(opts.nameAttr);if(name==null)return;var icon=opts.icons[kebabToPascal(name)];if(!icon){console.warn(el.outerHTML+" icon name was not found in the provided icons object.");return;}var elementAttrs=getAttrs(el);var attrs=Object.assign({},icon[1],{"data-lucide":name},opts.attrs,elementAttrs);var cls=mergeClasses(["lucide","lucide-"+name,elementAttrs,opts.attrs]);if(cls)attrs.class=cls;var svg=createElement(icon[0],attrs,icon[2]);if(el.parentNode)el.parentNode.replaceChild(svg,el);}',
    'function createIcons(options){if(typeof document==="undefined")throw new Error("createIcons() only works in a browser environment.");options=options||{};var icons=options.icons||ICONS,attrs=options.attrs||{},nameAttr=options.nameAttr||"data-lucide";Array.from(document.querySelectorAll("["+nameAttr+"]")).forEach(function(el){replaceElement(el,{nameAttr:nameAttr,icons:icons,attrs:attrs});});if(nameAttr==="data-lucide"){var legacy=document.querySelectorAll("[icon-name]");if(legacy.length){console.warn("[Lucide] Some icons were found with the now deprecated icon-name attribute. These will still be replaced for backwards compatibility, but will no longer be supported in v1.0 and you should switch to data-lucide");Array.from(legacy).forEach(function(el){replaceElement(el,{nameAttr:"icon-name",icons:icons,attrs:attrs});});}}}',
    "window.lucide={createIcons:createIcons,icons:ICONS};",
  ].join("");

  const header =
    "/*! lucide-icons.min.js — lucide v" +
    lucideVersion +
    " subset (ISC) — " +
    entries.length +
    " icons.\n   Generated by scripts/build-lucide-subset.js — do not edit by hand. */\n";

  fs.writeFileSync(OUT_PATH, header + "(function(){\"use strict\";" + runtime + "})();\n");
  console.log(`wrote ${path.relative(ROOT, OUT_PATH)} (${fs.statSync(OUT_PATH).size} bytes, ${entries.length} icons)`);
}

main();
