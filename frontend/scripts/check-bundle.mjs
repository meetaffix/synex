// Fails the build if the built frontend contains a server secret. Run after `npm run build`:  npm run check:bundle
// It reports the NAME of the variable (or the kind of pattern) and the file, never the secret itself.
//
// Two checks over every file in dist/ (or the folder given as the first argument):
//  1. every value in the project's root .env whose name is not VITE_* and looks secret (KEY, SECRET, PASSWORD, TOKEN,
//     DATABASE_URL) must not appear in any file;
//  2. secret-shaped strings must not appear: Clerk secret keys, webhook signing secrets, private keys, database URLs
//     with a password.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const dist = path.resolve(process.argv[2] ?? path.join(here, "..", "dist"));
const envFile = path.resolve(process.argv[3] ?? path.join(here, "..", "..", ".env"));

const SECRET_NAME = /(KEY|SECRET|PASSWORD|TOKEN)|^DATABASE_URL$/;
const secrets = [];
if (fs.existsSync(envFile)) {
  for (const line of fs.readFileSync(envFile, "utf8").split(/\r?\n/)) {
    const match = line.match(/^([A-Z][A-Z0-9_]*)=(.*)$/); // commented lines do not match
    if (!match) continue;
    const [, name, raw] = match;
    const value = raw.trim().replace(/^["']|["']$/g, "");
    if (!name.startsWith("VITE_") && SECRET_NAME.test(name) && value.length >= 8) secrets.push({ name, value });
  }
}

const PATTERNS = [
  ["a Clerk or Stripe-style secret key (sk_test_/sk_live_)", /sk_(test|live)_[A-Za-z0-9]{16,}/],
  ["a webhook signing secret (whsec_)", /whsec_[A-Za-z0-9+/=]{16,}/],
  ["a private key block", /-----BEGIN [A-Z ]*PRIVATE KEY-----/],
  ["a database URL with a password", /(postgres(ql)?|cockroachdb|mysql|mongodb(\+srv)?):\/\/[^\s:@/]+:[^\s@/]{3,}@/],
];

function* files(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* files(full);
    else yield full;
  }
}

if (!fs.existsSync(dist)) {
  console.error(`No build found at ${dist}. Run npm run build first.`);
  process.exit(2);
}

const problems = [];
let scanned = 0;
for (const file of files(dist)) {
  if (/\.(png|jpe?g|gif|ico|woff2?|ttf|otf|mp3|mp4|webm)$/i.test(file)) continue;
  const text = fs.readFileSync(file, "utf8");
  scanned += 1;
  const rel = path.relative(dist, file);
  for (const { name, value } of secrets) if (text.includes(value)) problems.push(`${rel}: contains the value of ${name}`);
  for (const [label, pattern] of PATTERNS) if (pattern.test(text)) problems.push(`${rel}: contains ${label}`);
}

if (problems.length) {
  console.error(`Bundle secret check FAILED (${problems.length}). Values are not printed.\n` + problems.map((p) => "  " + p).join("\n"));
  process.exit(1);
}
console.log(`Bundle secret check passed: ${scanned} files scanned, ${secrets.length} secret variable(s) from .env compared, ${PATTERNS.length} patterns.`);
