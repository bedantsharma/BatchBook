---
name: run-tests
description: Run the BatchBook pytest suite. Pass a file path, test name, or keyword to focus. Examples: /run-tests, /run-tests owner, /run-tests test_owner_routes.py
disable-model-invocation: true
---

# Run Tests

Run `uv run pytest` in the BatchBook project root with sensible defaults.

## Rules

- Always run from `/Users/bedantsharma/PycharmProjects/BatchBook`
- Always pass `-v` (verbose) so each test name is visible
- Always pass `--tb=short` so failures are readable without being overwhelming
- If the user passed an argument, append it as a filter: `uv run pytest -v --tb=short <arg>`
- If no argument, run the full suite: `uv run pytest -v --tb=short`
- After running, report: total passed / failed / errors, and highlight any failing test names

## Commands

**Full suite:**
```bash
cd /Users/bedantsharma/PycharmProjects/BatchBook && uv run pytest -v --tb=short
```

**Focused (keyword or file):**
```bash
cd /Users/bedantsharma/PycharmProjects/BatchBook && uv run pytest -v --tb=short -k "<keyword>"
# OR
cd /Users/bedantsharma/PycharmProjects/BatchBook && uv run pytest -v --tb=short tests/<file>.py
```

## After Running

- If all pass: confirm count and say tests are green.
- If any fail: show the failing test names and the short traceback. Offer to investigate.
- Never silently ignore failures.
