# CLAUDE.md

This repository is `hackathon-test`, a shared prototype for the AI-first hackathon test.

Claude must read and follow `AGENTS.md` before changing files or suggesting Git operations.
`AGENTS.md` is the source of truth for branch rules, commit rules, push rules, Confluence rules,
and conflict handling.

## Project Goal

Build and improve an MBTI Werewolf simulation so the team can learn:

- how three people can develop with AI agents
- what constraints appear in local PC execution and free-tier AI usage
- what logs, HTML results, and summaries are useful for team discussion
- what level of implementation is convincing enough to inform the real hackathon theme selection

## Current Implementation Focus

The next improvement is v1 of the result-checking prototype.

Prioritize:

- representing players as MBTI types, not only as single psychological functions
- giving each MBTI player a four-function stack
- making Werewolf game rules explicit in prompts
- making `result.html` easier for non-engineers to read
- providing a latest-result HTML link that can be opened from a phone

Use this MVP player set unless the requester says otherwise:

| Player | MBTI | Function stack |
| --- | --- | --- |
| 討論者 | ENTP | Ne / Ti / Fe / Si |
| 擁護者 | ISFJ | Si / Fe / Ti / Ne |
| 仲介者 | INFP | Fi / Ne / Si / Te |
| 幹部 | ESTJ | Te / Si / Ne / Fi |

This set keeps E/I, N/S, T/F, and P/J balanced at 2:2.

## Working Style

- Explain changes in plain language for non-engineers.
- Before editing important files, show what will change and wait for approval when needed.
- Keep existing outputs readable even if older logs only have `function`.
- Do not treat current metrics or win analysis as final accuracy. They are provisional and can improve by version.
- Prefer small, reviewable changes over large rewrites.

## Files That Usually Matter

- `playgrounds/mbti-werewolf/src/mbti_werewolf/config.py`
- `playgrounds/mbti-werewolf/src/mbti_werewolf/engine/roles.py`
- `playgrounds/mbti-werewolf/src/mbti_werewolf/agents/mbti_types.py`
- `playgrounds/mbti-werewolf/src/mbti_werewolf/agents/prompts/v1/`
- `playgrounds/mbti-werewolf/src/mbti_werewolf/record/`
- `playgrounds/mbti-werewolf/tests/`

## Do Not

- Do not push to GitHub. A human pushes manually.
- Do not work on `main`.
- Do not rewrite unrelated code.
- Do not silently change JSON or CSV output fields without calling it out.
- Do not update Confluence directly without showing the draft first.
