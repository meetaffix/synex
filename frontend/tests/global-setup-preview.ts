import { API_URL, APP_URL } from "./support";

/** The preview build must have been built against the fixture API: its bundle names that API and never the real one. */
export default async function globalSetup() {
  const html = await (await fetch(APP_URL)).text();
  const script = html.match(/src="(\/assets\/index-[^"]+\.js)"/)?.[1];
  if (!script) throw new Error(`Refusing to run: no app bundle found at ${APP_URL}.`);
  const bundle = await (await fetch(`${APP_URL}${script}`)).text();
  if (!bundle.includes(API_URL) || /localhost:8010|127\.0\.0\.1:8010/.test(bundle)) {
    throw new Error(`Refusing to run: the preview build on ${APP_URL} is not built for the fixture API ${API_URL}.`);
  }
}
