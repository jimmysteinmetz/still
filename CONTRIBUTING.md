# Contributing

Bug reports and pull requests are welcome. For anything beyond a small fix,
open an issue first so we can agree on the direction — still is deliberately
minimal, and the finite edition budget is the product (see
[`personal-newspaper-spec.md`](personal-newspaper-spec.md)).

## Contribution license

still is licensed under [FSL-1.1-MIT](LICENSE) and also powers a commercial
service run by Frequency Dev. So that outside code can be accepted at all, by
submitting a contribution you agree that:

1. the contribution is your own work (or you otherwise have the right to
   submit it), and
2. you license it under the repository's license (FSL-1.1-MIT) and grant
   Frequency Dev a perpetual, worldwide, royalty-free right to use, modify,
   sublicense, and relicense it, including in commercial products and
   services.

This is the standard inbound-license-plus-relicense-grant arrangement used by
fair-source projects; if you can't agree to it, please open an issue describing
the change instead of a PR.

## Development

```bash
uv sync                      # install (uv only — no pip, no venv juggling)
uv run pytest                # tests (hermetic; no network, no LLM calls)
uv run ruff check . && uv run ruff format --check .
uv run mypy src              # strict
uv run still config check    # validate config/still.yaml
```

Before opening a PR: all four of the above green, and if you touched the
renderer, eyeball a PDF via `uv run scripts/smoke_render.py`.
