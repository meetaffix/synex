import { API_URL, APP_URL } from "./support";

/** The dev server the specs drive must be built against the fixture API, not whatever else is running. */
export default async function globalSetup() {
  const client = await (await fetch(`${APP_URL}/src/services/client.ts`)).text();
  const configured = client.match(/"VITE_API_URL":\s*"([^"]+)"/)?.[1];
  if (configured !== API_URL) {
    throw new Error(
      `Refusing to run: the dev server on ${APP_URL} is configured for API ${configured ?? "(default http://localhost:8010)"}, ` +
        `not the fixture API ${API_URL}.`,
    );
  }
}
