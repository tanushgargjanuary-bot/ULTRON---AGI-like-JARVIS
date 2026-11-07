"""
actions/plugin_forge.py — Dynamic hot-plugin forge for Ultron.

Builds, validates, sandboxes, hot-loads, and registers new single-file plugins
into the running PluginRegistry without restarting the application.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from core import failures, gemini, policy, undo
from core.plugin_loader import discover_plugins, get_active_registry, PluginRegistry

ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = ROOT / "plugins"

_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")


def _clean_code(text: str) -> str:
    """Strip markdown formatting or code blocks from LLM output."""
    text = text.strip()
    text = re.sub(r"^```(?:python)?\s*\n?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _generate_template_code(name: str, description: str) -> str:
    """Generate a clean, contract-compliant plugin template."""
    desc = description.strip() if description else f"Capability {name}."
    return f'''"""
Plugin {name} — forged by Plugin Forge.
"""

PLUGIN = {{
    "name": "{name}",
    "description": "{desc}",
    "parameters": {{
        "type": "OBJECT",
        "properties": {{
            "message": {{
                "type": "STRING",
                "description": "Optional message or parameter for {name}.",
            }}
        }},
    }},
}}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        msg = str(parameters.get("message") or "active").strip()
        if player is not None and hasattr(player, "write_log"):
            player.write_log(f"[{name}] executed: {{msg}}")
        return f"Sir, the {name} plugin executed successfully: {{msg}}."
    except Exception as e:
        return f"Sir, the {name} plugin encountered an error: {{e}}"
'''


def validate_plugin_ast(code: str, expected_name: str) -> tuple[bool, str]:
    """Inspect the AST to ensure the code satisfies the single-file plugin contract."""
    try:
        tree = ast.parse(code)
    except SyntaxError as se:
        return False, f"Syntax error at line {se.lineno}: {se.msg}"

    has_plugin_dict = False
    has_run_func = False

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PLUGIN":
                    has_plugin_dict = True
                    if not isinstance(node.value, ast.Dict):
                        return False, "PLUGIN must be a dictionary literal."
        elif isinstance(node, ast.FunctionDef) and node.name == "run":
            has_run_func = True
            args = [a.arg for a in node.args.args]
            has_var = node.args.vararg is not None or node.args.kwarg is not None
            if not has_var and "parameters" not in args and len(args) == 0:
                return False, "run() must accept 'parameters' as its first argument."

    if not has_plugin_dict:
        return False, "Missing module-level 'PLUGIN = {...}' declaration."
    if not has_run_func:
        return False, "Missing 'def run(parameters, ...)' function."

    return True, ""


def rehearse_in_sandbox(name: str, code: str) -> tuple[bool, str]:
    """Execute plugin import and dry-run in an isolated temporary subprocess."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_file = Path(tmp_dir) / f"{name}.py"
        tmp_file.write_text(code, encoding="utf-8")

        runner_script = """
import sys
import importlib.util
from pathlib import Path

path = Path(sys.argv[1])
name = path.stem

try:
    spec = importlib.util.spec_from_file_location(f"sandbox.{name}", path)
    if not spec or not spec.loader:
        print("Spec creation failed", file=sys.stderr)
        sys.exit(2)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
except Exception as e:
    print(f"Import crash: {e}", file=sys.stderr)
    sys.exit(3)

plugin_dict = getattr(mod, "PLUGIN", None)
if not isinstance(plugin_dict, dict):
    print("PLUGIN is not a dict", file=sys.stderr)
    sys.exit(4)

if plugin_dict.get("name") != name:
    print(f"PLUGIN name mismatch: got {plugin_dict.get('name')!r}, expected {name!r}", file=sys.stderr)
    sys.exit(5)

if not plugin_dict.get("description"):
    print("PLUGIN description missing or empty", file=sys.stderr)
    sys.exit(6)

params = plugin_dict.get("parameters")
if not isinstance(params, dict) or params.get("type") != "OBJECT":
    print("PLUGIN parameters must be dict with type='OBJECT'", file=sys.stderr)
    sys.exit(7)

run_fn = getattr(mod, "run", None)
if not callable(run_fn):
    print("run is not callable", file=sys.stderr)
    sys.exit(8)

try:
    result = run_fn({}, player=None, session_memory=None)
    if not isinstance(result, str):
        print(f"run() returned {type(result).__name__}, expected str", file=sys.stderr)
        sys.exit(9)
except Exception as e:
    print(f"run() raised exception: {e}", file=sys.stderr)
    sys.exit(10)

print("REHEARSAL_SUCCESS")
sys.exit(0)
"""
        try:
            proc = subprocess.run(
                [sys.executable, "-c", runner_script, str(tmp_file)],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(ROOT),
            )
            if proc.returncode == 0 and "REHEARSAL_SUCCESS" in proc.stdout:
                return True, "Rehearsal dry-run passed in sandbox."
            err = proc.stderr.strip() or proc.stdout.strip() or f"Exit code {proc.returncode}"
            return False, f"Sandbox execution check failed: {err}"
        except subprocess.TimeoutExpired:
            return False, "Sandbox execution timed out after 10 seconds."
        except Exception as e:
            return False, f"Sandbox error: {e}"


def _obtain_code(name: str, description: str, prompt: str, code: str) -> str:
    """Generate or clean code for plugin forge."""
    if code:
        return _clean_code(code)
    if prompt or description:
        try:
            gen_prompt = (
                f"Write a single-file Python plugin for Ultron adhering strictly to this contract:\n"
                f"1. Top-level PLUGIN dict:\n"
                f"PLUGIN = {{\n"
                f'    "name": "{name}",\n'
                f'    "description": "{description or prompt or name}",\n'
                f'    "parameters": {{"type": "OBJECT", "properties": {{}}}}\n'
                f"}}\n"
                f"2. def run(parameters: dict, player=None, session_memory=None) -> str:\n"
                f"   Catch errors, return short speech string, never raise, no PyQt/Qt widgets.\n\n"
                f"Requirement: {prompt or description}\n"
                f"Return ONLY valid Python code."
            )
            generated = gemini.text(gen_prompt, tier=gemini.FAST)
            if generated and generated.strip():
                return _clean_code(generated)
        except Exception as e:
            failures.note("plugin_forge.generate", e)
    return _generate_template_code(name, description or prompt)


def _register_forge_undo(
    name: str, target_path: Path, prev_content: Optional[str], prev_policy_tier: Any
) -> None:
    """Push reversible closure onto core/undo stack."""
    def _undo_forge() -> str:
        if prev_content is None:
            if target_path.exists():
                target_path.unlink()
            file_act = f"removed {target_path.name}"
        else:
            target_path.write_text(prev_content, encoding="utf-8")
            file_act = f"restored previous {target_path.name}"

        active_reg = get_active_registry()
        if active_reg is not None:
            if prev_content is None:
                active_reg.unregister(name)
            else:
                active_reg.reload_or_register(target_path)

        if prev_policy_tier is None:
            policy.unregister_policy(name)
        else:
            policy.register_policy(name, prev_policy_tier)
        return f"Undo forge: {file_act} and unhooked '{name}'"

    undo.push_undo(
        f"forge plugin '{name}'",
        _undo_forge,
        metadata={"type": "plugin_forge", "plugin": name, "file": str(target_path)},
    )


def _notify_forge_ui(player: Any, name: str, description: str, tier_val: str) -> None:
    """Send UI notification on UI thread."""
    if player is None:
        return
    ui_summary = (
        f"Plugin '{name}' was forged, sandboxed, and hot-loaded successfully.\n\n"
        f"File: plugins/{name}.py\n"
        f"Description: {description}\n"
        f"Risk Policy Tier: {tier_val}\n"
        f"Rehearsal Status: PASSED (sandbox verified)\n"
        f"Undo Ready: Say 'undo' to reverse creation."
    )
    if hasattr(player, "show_content"):
        player.show_content(f"Plugin Forged: {name}", ui_summary)
    if hasattr(player, "write_log"):
        player.write_log(f"Plugin Forge: '{name}' hot-loaded and active.")


def forge_plugin(parameters: dict, player=None, session_memory=None) -> str:
    """Forges, sandboxes, and hot-loads a new plugin into the running system."""
    name = str(parameters.get("name") or "").strip()
    description = str(parameters.get("description") or "").strip()
    code = str(parameters.get("code") or "").strip()
    tier_param = str(parameters.get("tier") or "guarded").strip().lower()
    prompt = str(parameters.get("prompt") or "").strip()

    if not name or not _NAME_RE.match(name):
        return (
            f"Plugin name '{name}' is invalid. Must be a valid Python identifier "
            "(letters, digits, underscore, starting with letter/underscore, max 64 chars)."
        )

    core_tools = (
        policy.OBSERVE_TOOLS | policy.ROUTINE_TOOLS | policy.GUARDED_TOOLS | policy.SENSOR_TOOLS | policy.BYPASS_TOOLS
    )
    if name in core_tools:
        return f"Plugin name '{name}' collides with an existing core tool — rejected."

    code = _obtain_code(name, description, prompt, code)

    ast_ok, ast_err = validate_plugin_ast(code, name)
    if not ast_ok:
        return f"Plugin forge rejected by AST validator: {ast_err}"

    rehearsal_ok, rehearsal_msg = rehearse_in_sandbox(name, code)
    if not rehearsal_ok:
        return f"Plugin forge rejected: {rehearsal_msg}"

    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    target_path = PLUGINS_DIR / f"{name}.py"
    prev_content = target_path.read_text(encoding="utf-8") if target_path.exists() else None
    prev_policy_tier = policy.get_dynamic_policy(name)

    try:
        target_path.write_text(code, encoding="utf-8")
    except Exception as e:
        return f"Failed to write plugin file '{target_path.name}': {e}"

    reg = get_active_registry() or discover_plugins(PLUGINS_DIR, core_tool_names=core_tools, logger=lambda _m: None)
    record = reg.reload_or_register(target_path)
    if not record.valid:
        if prev_content is None and target_path.exists():
            target_path.unlink()
        elif prev_content is not None:
            target_path.write_text(prev_content, encoding="utf-8")
        return f"Plugin registration failed: {record.error}"

    valid_tiers = {
        "observe": policy.Tier.OBSERVE,
        "routine": policy.Tier.ROUTINE,
        "guarded": policy.Tier.GUARDED,
        "sensor": policy.Tier.SENSOR,
    }
    policy_tier = valid_tiers.get(tier_param, policy.Tier.GUARDED)
    policy.register_policy(name, policy_tier)

    _register_forge_undo(name, target_path, prev_content, prev_policy_tier)
    _notify_forge_ui(player, name, record.description, policy_tier.value)

    return f"Sir, I have forged and hot-loaded the {name} plugin. It passed rehearsal and is now live."


# ── Action Tool Declaration ──────────────────────────────────────────────────
TOOL = {
    "name": "plugin_forge",
    "description": (
        "Use whenever the user asks to create, build, forge, generate, or add a new "
        "plugin or capability. Forges, validates AST, rehearses in an isolated sandbox, "
        "and hot-loads a single-file plugin into the running registry with instant undo support."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "name": {
                "type": "STRING",
                "description": "Identifier name for the plugin (e.g. coin_flip, qr_code).",
            },
            "description": {
                "type": "STRING",
                "description": "Short description of what the plugin does.",
            },
            "code": {
                "type": "STRING",
                "description": "Complete Python source code for the plugin adhering to single-file plugin contract.",
            },
            "tier": {
                "type": "STRING",
                "description": "Optional policy tier (observe, routine, guarded, sensor). Defaults to guarded.",
            },
            "prompt": {
                "type": "STRING",
                "description": "Optional prompt describing the capability to generate if code is not provided.",
            },
        },
        "required": ["name"],
    },
    "handler": forge_plugin,
}
