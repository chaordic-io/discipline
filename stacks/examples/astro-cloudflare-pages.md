# Example stack: Astro static site on Cloudflare Pages

A worked example from the project this kit was extracted from, and an example rather than a
recommendation: how the selection criteria in [`../README.md`](../README.md) and the engineering
principles applied to a static site (S2 and E1: no runtime to operate; E7: a strict CSP and no
third-party requests; E8: every language written for its market). It is the product's marketing site, built by a second agent session next to the app (`site/` in the same repository, see `kit/agents-folder/WORKING.md`,
"Several sessions on one repository").

## The stack

- **Astro** (static output), TypeScript strictest, no client framework; the few scripts are bundled
  modules (no inline script or style, so the CSP can forbid them).
- **Cloudflare Pages** with Pages Functions: `functions/index.ts` redirects `/` to the visitor's
  variant (language from `Accept-Language`, market from Cloudflare's country), with
  `Vary: Accept-Language, Cookie`; `functions/api/event.ts` proxies first-party analytics events.
- **Variants as static pages:** language × market (e.g. `/de-ch/`), each with canonical and hreflang
  alternates in `sitemap.xml`; a cookie only when the visitor picks a variant themselves.
- **Security headers** in `public/_headers`: a strict CSP (`'self'` only), HSTS, no third-party requests.
- **Deploy:** `wrangler pages deploy` with an API token, behind a placeholder check that refuses to
  deploy while legal texts still contain placeholders.

## The gate (`npm run check`)

```json
"check": "npm run lint && npm run test:coverage && npm run build && vitest run --config vitest.build.config.ts"
```

- **Lint:** `astro check`, `tsc` for the functions, ESLint strict type-checked (with `eslint-plugin-astro`).
- **Unit tests:** Vitest + fast-check for the logic in `src/lib` (language negotiation, market by
  country, variant parsing, pricing arithmetic with properties such as "adding a user never lowers the
  bill"), the functions (called with mock requests and an injected `fetch`), the dictionaries (every
  language has exactly the English keys, nothing empty, nothing left in English).
- **Built-page tests** (`test/build/`): read `dist/` after the build and check each of the variants:
  canonical, no inline script, links only to allowed hosts, legal links on every page, global pages
  carry none of the national messaging, prices in the market's currency, a spelling rule per locale.
- **Claims tests** (`test/claims.test.ts`): read the app's source (presets, migrations, handlers) and
  fail when something the site claims stops being true. Claims made ahead of a build are listed and
  re-checked before launch.
- **Design tokens:** a test requires the site's colour tokens to equal the app's.

## Browser tests (in a container)

`scripts/browser.sh` builds an image with Playwright and wrangler, runs `wrangler pages dev` (so the
functions and headers behave as on Cloudflare) and checks every variant at 360/768/1280 px: no sideways
scroll, no console errors, no third-party requests, no cookie before a choice, the redirect, the
switcher, the pricing calculator. `SITE_SCREENSHOTS=1` writes screenshots for a visual review. It runs
in a container because the agent machine has no browser; results are copied back with `docker cp`.

## Copy

- Texts live only in per-language dictionaries; English sets the shape (`Messages` type).
- **Written for the market:** each language by a native copywriter's standard, reviewed for idiom and
  voice, with the same claims as the English.

## Review units

One unit `site` with the lenses security, tests, architecture, duplication and localisation, and a
`site-dependencies` unit (`package.json`, the lockfile, the deploy script) with supply-chain and
security. As a project of its own, its profile would be: kind `static-site`; several languages;
no interfaces; performance `minor`. That turns localisation on, and performance and contracts off.
