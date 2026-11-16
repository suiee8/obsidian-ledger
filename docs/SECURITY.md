
## Verification (part 7)

- `api/tests/security/test_malicious_corpus.py`: zip bombs, zip-slip, macro and external-link workbooks, wrong magic bytes, polyglots, DDE formulas, oversized rows and columns, nested JSON, prototype keys, and seeded fuzzing. Every file is refused or gets a structured error, never a 500. The EICAR case runs only when ClamAV is installed.
- `api/tests/security/test_request_attacks.py`: spoofed Host and Origin, missing client header, rate limiting, path traversal, SQL injection strings in every filter and sort, and error bodies that never show internals.
- `web/e2e/zz-security.spec.ts`: hostile symbols render as text, the web app sends `X-Ledger-Client`, strict page headers, and forged requests are refused.
- Known limits: `style-src` keeps `'unsafe-inline'` because charts and React inline styles need it. The dev server also allows inline scripts for the Vite refresh preamble; `vite preview` and production builds do not.
