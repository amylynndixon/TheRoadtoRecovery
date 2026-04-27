# Regression tests

Headless-Chromium suite that locks down the contracts that have broken before:
text colors, image filters, theme toggle position across viewports, click behavior.

## One-time setup

```bash
python3 -m venv .venv-tests
source .venv-tests/bin/activate
pip install playwright
python -m playwright install chromium
deactivate
```

## Run

```bash
source .venv-tests/bin/activate
python tests/regression.py
```

The script boots its own HTTP server on a free port, so nothing else needs to be running. Exits non-zero on any failure. Run before every push.

## What's covered

Per-viewport theme toggle position (mobile / tablet 820 / tablet 800 / desktop), light-mode body + reintegration text color, dark-mode body bg + text + neuron filters + MRI keep-color + Dixon-logo-white + generic image grayscale, and click-toggles-theme.

## Adding a test

Edit `tests/regression.py`. Each check uses `r.check(label, actual, expected)` — anything that returns a JSON-serializable value from the page works.
