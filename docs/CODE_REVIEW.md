# Code review workflow

Ultron uses three separate review layers. They answer different questions and must not be treated as substitutes for one another.

## 1. GitHub Actions — correctness gates

The `fast-checks` workflow runs on every branch push. It runs `git diff --check`, Ruff on changed Python files, parses all discovered Python files, runs 19 runner edge tests, 30 policy/confirmation tests, 8 README contract tests, the 1,000-scenario deterministic stress suite, and the generated-map check. The `verify` workflow runs the full project suite, 15 targeted mutations, and proof gates on Linux and Windows for pull requests to `main` and pushes to `main`. The latest verified `main` baseline is `b80919314f391e15ddd86e2860c2e4d66057b15b`: [full run 42855681003](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42855681003) passed 2,073 tests on each platform. The fast gate [42855680649](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42855680649) passed 5/5 groups in 12.68 seconds. Archive run [42855681028](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42855681028) passed. A green result means only those configured checks passed on that commit. It does not prove that the code has no defects. Required-check merge enforcement is not verified because the branch-protection API returned HTTP 403. See [Test automation](TEST_AUTOMATION.md) for triggers, scope, and required check names.

## 2. Reviewdog + Ruff — deterministic static findings

The `reviewdog` workflow runs Ruff and reports findings on changed lines as a GitHub PR check.

- Ruff checks syntax-related errors, Pyflakes, Bugbear, blind exception handling, and Bandit-style Python security rules. Import-order and broad style rules are excluded to reduce noise.
- Reviewdog filters the report to lines added by the pull request and posts findings to GitHub.
- This workflow uses the repository's `GITHUB_TOKEN`; it does not need a paid model API.
- This is static analysis, not semantic AI review. A clean result does not prove that the design is correct.
- The workflow is advisory. It reports warnings and does not replace the main verification workflow.

For a fork pull request, GitHub may restrict write permissions. Reviewdog then falls back to Actions annotations where supported.

## CodeRabbit status — not verified

PR #19 (`chore: trigger CodeRabbit review`) was closed with `merged=false`. Its branch changes were not integrated into `main`. This PR does not establish that CodeRabbit is installed, enabled, or required. No CodeRabbit-required status check was verified. Do not describe AI review as an active gate unless a live PR proves the integration and its permissions have been checked.

## 3. PR-Agent — optional AI review

[PR-Agent](https://github.com/The-PR-Agent/pr-agent) is an open-source AI pull-request review tool. It can produce a CodeRabbit-style review, but it needs both GitHub access and an LLM endpoint.

The project does not enable automatic PR-Agent runs in GitHub-hosted Actions. A hosted runner cannot connect to Ollama on the owner's laptop unless a separately secured, reachable Ollama host is provided. A cloud model would require a provider key and may add cost. See the [PR-Agent Ollama model guide](https://docs.pr-agent.ai/usage-guide/changing_a_model/) and [local CLI guide](https://docs.pr-agent.ai/installation/locally/).

To run PR-Agent locally with Ollama on Windows:

1. Confirm Ollama is running and has the selected model installed.
2. Create a GitHub token with access to read the repository and write pull-request reviews. Keep the token in an environment variable. Never commit it.
3. Install PR-Agent:

```powershell
py -m pip install "pr-agent[github]"
```

4. Set the environment variables in the same PowerShell session:

```powershell
$env:ULTRON_GITHUB_TOKEN = "YOUR_GITHUB_TOKEN"
$env:ULTRON_PR_URL = "https://github.com/OWNER/REPOSITORY/pull/NUMBER"
$env:ULTRON_OLLAMA_MODEL = "YOUR_INSTALLED_MODEL"
$env:OLLAMA_CONTEXT_LENGTH = "8192"
```

5. Run the following command:

```powershell
@'
import os
from pr_agent import cli
from pr_agent.config_loader import get_settings

settings = get_settings()
settings.set("CONFIG.git_provider", "github")
settings.set("github.user_token", os.environ["ULTRON_GITHUB_TOKEN"])
settings.set("config.model", "ollama/" + os.environ["ULTRON_OLLAMA_MODEL"])
settings.set("config.fallback_models", [])
settings.set("ollama.api_base", "http://localhost:11434")

cli.run_command(os.environ["ULTRON_PR_URL"], "/review")
'@ | py -
```

The review appears on the pull request. The command sends source and diff content to the selected model endpoint. Check the endpoint and model before use. Ollama's default context window may be too small for a large PR; set `OLLAMA_CONTEXT_LENGTH` before starting Ollama, then restart the Ollama server. The example uses 8K tokens as a starting point, not a universal optimum.

### Local model limits

Small local models can miss cross-file defects, produce unsupported claims, or fail to format review output. Use the largest reliable coding model available within the machine's memory and time limits. Review findings manually before accepting them.

## Manual review standard

Reviewers must inspect changed code, relevant callers, and tests. Each actionable finding must include:

- Severity: Critical, High, Medium, or Low.
- File and changed line.
- The input or state that triggers the defect.
- The impact.
- A specific fix.
- A regression test.

Reviewers must separate confirmed defects from questions and improvement ideas. A test passing does not cancel a source-level defect. A test failure is not automatically a product defect until the cause is identified.

For generated-code or self-repair features, check the execution boundary separately from the file-writing boundary. A temporary worktree is not an OS sandbox. Confirm which user identity runs candidate code and which files, processes, and network destinations it can reach.

## PR completion rule

Do not merge only because the CI checks are green. Resolve all Critical and High findings. Resolve Medium findings or record an explicit reason to defer them. Confirm that the final review covers the latest PR head, not an earlier commit.
