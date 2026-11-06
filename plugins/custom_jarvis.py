"""Our extra evidence/repair capabilities, hosted inside the original MARK HUD."""

import json

PLUGIN = {
    "name": "custom_jarvis",
    "description": (
        "Custom JARVIS extensions: workspace-confined inspected file tools, 24 reviewed skills, "
        "goal verification, backups and transaction rollback, local failure fingerprints, "
        "bounded argument-adapter repair with shadow tests and canaries, procedure memory "
        "and checkpoint resume. MARK remains the voice/provider/UI host. "
        "Use insights to review temporary preference proposals and readiness checklists; review_insight takes an optional id (otherwise next candidate) and requires human approval before saving. "
        "Use list_skills or list_tools to discover IDs/schemas. Select a workspace with "
        "set_workspace before file work. Mutations require real on-screen human approval. "
        "Jobs return started, NOT done; use status to see the actual result. "
        "Operations: insights, recommendations, review_insight, reject_insight, forget_insights, status, stop, knowledge_status, set_workspace, list_skills, list_tools, tool, run_skill, "
        "preview_skill, verify_goal, rollback_transaction, repair_test, repair_generate, "
        "repair_shadow, repair_activate, repair_rollback, breaker_reset, resume_checkpoint, "
        "procedure_propose, procedure_approve, procedures, run_procedure, forget. "
        'payload_json examples: set_workspace {"path":"C:/Projects/MyApp"}; '
        'tool {"name":"read_file","arguments":{"path":"README.md"}}; '
        'run_skill {"id":"ID_FROM_LIST","target":"README.md"}. '
        "Never use this as a general Python execution or automatic self-rewrite tool."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {
                "type": "STRING",
                "description": "One supported operation named in the tool description.",
            },
            "payload_json": {
                "type": "STRING",
                "description": "JSON object for the operation. Defaults to {}. At most 64 KiB.",
            },
        },
        "required": ["operation"],
    },
    "tier": "core",
    "brief": "Workspace skills, reviewed preference insights/readiness checklists, verified files and bounded repairs.",
}


def run(parameters, player=None, session_memory=None):
    try:
        raw = parameters.get("payload_json", "{}")
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > 65536:
            return "Custom JARVIS rejected payload: expected a JSON object string up to 64 KiB. Nothing executed."
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return "Custom JARVIS rejected payload: expected a JSON object. Nothing executed."
        from custom_jarvis.service import get_service

        result = get_service().submit(parameters["operation"], payload, player)
        return json.dumps(result, ensure_ascii=False, default=str)[:65536]
    except Exception as exc:
        return "Custom JARVIS could not start: " + str(exc)
