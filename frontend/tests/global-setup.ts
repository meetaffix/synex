import { API_URL, APP_URL } from "./support";

/** The server the specs drive must be built against the fixture API, not whatever else is running. */
export default async function globalSetup() {
  if (process.env.PW_PREVIEW) {
    // A production build has the API address baked into its bundle: it must contain the fixture API and no other localhost API.
    const html = await (await fetch(`${APP_URL}/`)).text();
    const scripts = [...html.matchAll(/src="(\/assets\/[^"]+\.js)"/g)].map((m) => m[1]);
    const bundles = await Promise.all(scripts.map(async (src) => (await fetch(`${APP_URL}${src}`)).text()));
    if (!bundles.some((code) => code.includes(API_URL))) {
      throw new Error(`Refusing to run: the preview build on ${APP_URL} does not contain the fixture API ${API_URL}.`);
    }
    return;
  }
  const client = await (await fetch(`${APP_URL}/src/services/client.ts`)).text();
  const configured = client.match(/"VITE_API_URL":\s*"([^"]+)"/)?.[1];
  if (configured !== API_URL) {
    throw new Error(
      `Refusing to run: the dev server on ${APP_URL} is configured for API ${configured ?? "(default http://localhost:8010)"}, ` +
        `not the fixture API ${API_URL}.`,
    );
  }
}
