#!/usr/bin/env node
/**
 * Remove proprietary feature snapshots from already-built public payloads.
 *
 * The normal builders omit these fields. This utility is for cleaning the
 * checked-in static assets without rebuilding every league forecast.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dataDir = path.join(root, "webapp", "data");
let changed = 0;

for (const name of fs.readdirSync(dataDir).filter(name => name.endsWith(".js"))) {
  const file = path.join(dataDir, name);
  const text = fs.readFileSync(file, "utf8");
  const match = text.match(/^(window\.[A-Z0-9_]+\s*=\s*)(\{[\s\S]*\});?\s*$/);
  if (!match) continue;

  let data;
  try {
    data = JSON.parse(match[2]);
  } catch {
    continue;
  }

  let dirty = false;
  for (const key of ["team_inputs", "team_inputs_full"]) {
    if (Object.hasOwn(data, key)) {
      delete data[key];
      dirty = true;
    }
  }
  for (const fixture of data.fixtures || []) {
    for (const key of ["hinp", "ainp"]) {
      if (Object.hasOwn(fixture, key)) {
        delete fixture[key];
        dirty = true;
      }
    }
  }
  if (!dirty) continue;

  fs.writeFileSync(file, `${match[1]}${JSON.stringify(data)};\n`);
  changed += 1;
}

console.log(`Scrubbed proprietary model inputs from ${changed} public payloads.`);
