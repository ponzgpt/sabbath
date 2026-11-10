# sabbath
Hermes Agent plugin: a weekly day of rest kept with your agent (goodnight, its cron jobs sleep, work set aside, one digest). Entry for the Nous Hermes Agent Plugin Hackathon (due 2026-11-11 17:00 EST). Live: https://github.com/ponzgpt/sabbath

## Commands
- Check (before every commit and push): `./scripts/check.sh`
- Dev: `ln -s "$PWD" ~/.hermes/plugins/sabbath && hermes plugins enable sabbath`
- Deploy: push to main, then bump `sha` in the catalog entry PR (`docs/catalog-entry.yaml` → NousResearch/hermes-agent `plugin-catalog/sabbath.yaml`)

## Non-negotiables
1. Resume only the jobs Sabbath paused (reason "Sabbath"); a job the user paused stays paused. Tested in `tests/test_core.py`.
2. Never consume or block a message: the rest is kept by Hermes's manners, not by refusing the user. `/sabbath ox` always works.
3. Follow Nous' catalog rules (public surfaces where they exist, disclosures in README); not the usual technoir.cloud deploy rules.
4. Tone: warm and hopeful, never preachy; one line about rest, never a lecture.
