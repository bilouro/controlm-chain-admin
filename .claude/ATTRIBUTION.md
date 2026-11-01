# Attribution

The skills under `.claude/skills/` were written for this project and adapt material from
**Everything Claude Code (ECC)** by Affaan Mustafa — <https://github.com/affaan-m/everything-claude-code>,
released under the MIT License. Adapted components:

| Skill here | Adapted from ECC |
|---|---|
| `verify` | `skills/verification-loop` |
| `oss-repo-standards` | `agents/opensource-packager`, `agents/opensource-sanitizer`, `rules/common/*` |
| `python-core-tdd` | `skills/tdd-workflow`, `skills/python-testing`, `agents/python-reviewer`, `rules/python/*` |
| `fastapi-api` | `skills/fastapi-patterns`, `agents/fastapi-reviewer`, `rules/python/fastapi.md` |
| `react-frontend` | `skills/react-patterns`, `skills/react-testing`, `skills/vite-patterns`, `rules/react/*`, `rules/typescript/*`, `rules/web/*` |

The adaptations are specific to this repository (stdlib-only core, one-core-two-adapters,
no-real-data rule, synthetic fixtures); they are not a redistribution of ECC. ECC's licence
text follows.

## Everything Claude Code — MIT License

MIT License

Copyright (c) 2026 Affaan Mustafa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
