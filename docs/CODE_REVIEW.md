# Code review workflow

Ultron uses three separate review layers. They answer different questions and must not be treated as substitutes for one another.

## 1. GitHub Actions — correctness gates

The `verify` workflow runs the project test suite and proof gate on Linux and Windows. A green result means those configured checks passed on that commit. It does not prove that the code has no defects.

## 2. Reviewdog + Ruff — deterministic static findings

The `reviewdog` workflow runs Ruff and reports findings on changed lines as a GitHub PR check.

- Ruff checks syntax-related errors, Pyflakes, Bugbear, blind exception handling, and Bandit-style Python security rules. Import-order and broad style rules are excluded to reduce noise.
- Reviewdog filters the report to lines added by the pull request and posts findings to GitHub.
- This workflow uses the repository's `GITHUB_TOKEN`; it does not need a paid model API.
- This is static analysis, not semantic AI review. A clean result does not prove that the design is correct.
- The workflow is advisory. It reports warnings and does not replace the main verification workflow.

For a fork pull request, GitHub may restrict write permissions. Reviewdog then falls back to Actions annotations where supported.

## 3. PR-Agent — optional AI review

[PR-Agent](https://github.com/The-PR-Agent/pr-agent) is an open-source AI pull-request review tool. It can produce a CodeRabbit-style review, but it needs both GitHub access and an LLM endpoint.

The project does not enable automatic PR-Agent runs in GitHub-hosted Actions. A hosted runner cannot connect to Ollama on the owner's laptop. A cloud model would also require a provider key and may add cost.

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

The review appears on the pull request. The command sends source and diff content to the selected model endpoint. Check the endpoint and model before use.

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

## PR completion rule

Do not merge only because the CI checks are green. Resolve all Critical and High findings. Resolve Medium findings or record an explicit reason to defer them. Confirm that the final review covers the latest PR head, not an earlier commit.
