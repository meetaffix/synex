# Hosted proxy test: checklist for the owner

For 17 Nov 2026 or later (the home login was 16 Nov 2026, about 12:53 India time: the hosted check must be a different day).
Nothing in this list runs from the hosted server until you do step 5. The account's daily limit stays **0**: this test only
opens LinkedIn once to see whether the saved session still works through the proxy. It sends nothing, visits nothing, likes nothing.

## Before you start (one time)

1. **Buy one proxy: a dedicated static ISP proxy in India.**
   - *Dedicated*: only you use that address, not shared with other customers.
   - *Static*: the address never changes (not rotating, not a pool).
   - *ISP / residential type, country India* (a datacenter address defeats the purpose).
   - It must accept a **username and password** and speak **HTTP, HTTPS or SOCKS5**.
   - You will receive `host`, `port`, `username`, `password`. Put them together as `http://username:password@host:port`
     (or `socks5://...` if that is what the provider gives you).
2. **Check the code is live** (I do this with you): the branches listed in `docs/reports/merge-order-before-hosted-test.md` are
   merged, Railway has redeployed from `main` (both services show SUCCESS), and the frontend is deployed.
   `https://synex-api-production.up.railway.app/health` must answer `{"status":"ok"}`.

## The test (about 5 minutes)

3. Open **https://meetsynex.vercel.app**, sign in, go to **Sender accounts**, find **Meet Affix**, click **Edit**.
4. Open **Advanced: proxy**. Paste the full proxy address into the paste box. It splits into protocol, host, port, user and password.
5. Click **Test connection**. This calls a **neutral address-lookup service through the proxy, never LinkedIn**. Read the answer:
   - the **country must be India**;
   - the network name should be an internet provider, not a "hosting" or "datacenter" company.
   If either is wrong, stop here and tell me. Do not continue.
6. Click **Save changes**. The proxy is stored encrypted. The row should now show **Proxy: Set**.
7. Click **Check now** on the **Meet Affix** row **once**. The hosted server opens LinkedIn through your proxy with the saved session.
   - Expected: **Health: Connected**.
   - If it says **needs reconnect** or shows an error: **do not click again**. Tell me. I read the hosted logs, and the message now
     says what LinkedIn showed.
8. Tell me when you have clicked. I watch the hosted logs while it runs and report the table.

## Rules for the day
- **Only one click on Check now.** Repeated checks from a new address are what make LinkedIn suspicious.
- Do not press **Reconnect**, and do not connect another account from the hosted app, until we have read the result.
- The limit stays 0. Nothing is sent.
- If you ever see a LinkedIn email or notice about a new sign-in location, tell me and stop.

## What I record
Outcome, state reached, what LinkedIn showed, time taken, the address country and network the proxy test reported, and whether the
saved session survived the change of address (Connected) or LinkedIn asked to sign in again (Needs reconnect).
