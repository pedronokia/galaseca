# GalaSeca

[![tests](https://github.com/pedronokia/galaseca/actions/workflows/tests.yml/badge.svg)](https://github.com/pedronokia/galaseca/actions/workflows/tests.yml)

GalaSeca is a public website for observed data from the Steam Community
Market. It shows prices, history, explainable scores, and descriptive signals;
it does not predict returns or promise profit.

Page visits never trigger Steam requests. A separate worker collects data
periodically, respects Steam's request limits, and stores the results displayed
by the website.

## Run locally

Python 3.9 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-public-site.txt
python scripts/dev_public_site.py
```

The local preview runs at `http://127.0.0.1:5061`. To run the worker locally as
well, open another terminal. It starts collection cycles and observes the
configured request delays:

```powershell
python -m galaseca.public_site.worker
```

Run the test suite with:

```powershell
python -m pip install pytest
python -m pytest -q
```

## Run with Docker

```bash
docker compose -f docker-compose.public-site.yml up --build
```

The `web` service serves the pages and `worker` collects data. Both use the
persistent `skinvault_data` volume. Production deployment and the reverse
proxy are configured separately in `docker-compose.oracle.yml` and
`deploy/Caddyfile`.

## Project layout

- `galaseca/public_site/`: Flask application, routes, templates, CSS,
  JavaScript, persistence, and site worker.
- `galaseca/`: domain logic used by the site and worker (public Steam data,
  catalog, signals, and recommendations).
- `tests/`: website tests and tests for the shared domain logic it uses.
- `scripts/dev_public_site.py`: local preview with template auto-reload.

Files in `data/` may contain a database, session key, and local site data.
Do not delete them during code cleanup or add them to Git.

## Principles

- The site never receives Steam passwords, session cookies, or private API
  keys. Visitor sign-in, when used, goes through Steam OpenID.
- Price collection runs in the separate worker; page visits never start a scan.
- Other network actions happen only when explicitly requested by a visitor.
- Request delays and limits are centralized in `galaseca/steam_api.py`.
- Percentages use the 0–100 scale.
- The site describes past data; it is not investment advice.

## Disclaimer

An independent project, not affiliated with Valve. Past performance does not
guarantee future results.
