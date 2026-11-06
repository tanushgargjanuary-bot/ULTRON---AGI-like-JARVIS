"""Ultron thinking with the syllabus, out loud.

The owner was exact about what he wanted: not the syllabus stored, but the topics
"implemented as logic of ULTRON … meant to improve the working of ULTRON". So this
tool does not recite a chapter. It runs the course:

    "Is this allowed, and why?"        -> action "prove", facts and rules
    "In what order should these run?"  -> action "plan", steps and dependencies
    "What is the cheapest route?"      -> action "route", graph and costs
    "Is this worth doing exactly?"     -> action "budget", size and deadline
    "Which of the syllabus is inside you?" -> action "map"
    "Show me the proof"                -> action "why"

Every answer ends with the unit it came from, because a claim of competence that
cannot name its algorithm is a claim nobody can check.
"""

from __future__ import annotations

import ast
import json

from core import failures, policy
from core.mental import choose, logic, plan, records, registry


def _say(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line)


def _load(value, default):
    """The model sends structured arguments as JSON text; a caller may send them whole.

    Both are accepted because both arrive: the voice path sends strings, the proof
    gate sends objects. Guessing wrong silently would make the tool answer about an
    empty plan, which is worse than answering about none.
    """
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    text = str(value).strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except ValueError:
        try:                       # the model may write a Python literal instead
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return default


TIER_VERB = {"observe": "run", "routine": "run", "sensor": "ask",
             "guarded": "ask", "blocked": "refuse"}
# Which tier supports which verdict. Written as data rather than as branches, so the
# rules below are a statement a reader can check against the four tiers in policy.py.
VERDICT_TIERS = {"run": ("observe", "routine"), "ask": ("sensor", "guarded"),
                 "refuse": ("blocked",)}


def _may(parameters: dict) -> str:
    """Is this tool allowed to run — as a chain, not as a yes.

    The policy already answers this with a tier. What the tier does not do is show its
    work, and a permission decision nobody can audit is the one an assistant should be
    most careful about. So the tier becomes a fact, the rules that turn a tier into a
    verdict are stated, and forward chaining produces both the verdict and the chain.
    When the chain and the policy disagree, the policy wins and the disagreement is
    said out loud — silence there would hide a rule that had gone stale.
    """
    name = str(parameters.get("tool") or "").strip()
    if not name:
        return ("Which tool? For example: reasoning action=may tool=file_controller "
                "tool_action=write.")
    action = str(parameters.get("tool_action") or "").strip() or None
    args = {"action": action} if action else {}
    decision = policy.classify(name, args)
    tier = decision.tier.value
    known = logic.Knowledge()
    known.tell("tier", name, tier)
    for verdict_name, tiers in VERDICT_TIERS.items():
        for named in tiers:
            known.when(("may", name, verdict_name), ("tier", name, named))
    if decision.allow:
        known.tell("allowed", name, tier)
        known.when(("may", name, "run"), ("allowed", name, tier))
    derived = logic.forward_chain(known.facts, known.rules)
    found = {verb for verb in ("run", "ask", "refuse")
             if ("may", name, verb) in derived["facts"]}
    verdict = TIER_VERB.get(tier, "ask")
    lines = [f"tier: {tier} — {decision.reason}"]
    for verb in sorted(found):
        if ("may", name, verb) in derived["proof"]:
            lines.append(f"derived: {' -> '.join(derived['proof'][('may', name, verb)])}")
    lines.append(f"verdict: {verdict}" + ("" if decision.allow else ", and it waits"))
    if len(found) > 1:
        lines.append(f"My rules derive {len(found)} answers ({', '.join(sorted(found))}), "
                     f"which cannot all be right. The policy's '{verdict}' stands, and "
                     f"this contradiction is recorded rather than hidden.")
        failures.note("reasoning.may", f"rules derived {sorted(found)} for {name}")
    lines.append(_course_hint("AI", 3))
    return _say(lines)


def _course_hint(course: str, unit: int) -> str:
    title = registry.unit_title(course, unit)
    return f"[{course} unit {unit}: {title}]" if title else ""


def _map(_parameters=None) -> str:
    rows = registry.coverage()
    problems = registry.verify()
    lines = ["The syllabus, as machinery rather than notes:"]
    running = 0
    for name, row in rows.items():
        running += row["implemented"]
        lines.append(f"  {row['code']:<7} {name:<5} {row['implemented']:>2} of "
                     f"{row['topics']:>3} topics run as code")
    lines.append(f"{running} topics running, {len(registry.catalogue())} citations "
                 f"across {len({row['module'] for row in registry.catalogue()})} "
                 f"modules.")
    if problems:
        lines.append("Problems with the claims:")
        lines.extend("  " + item for item in problems[:5])
    else:
        lines.append("Every citation was checked against the code and against the "
                     "syllabus: none is a claim about code that is not there.")
    return _say(lines)


def _prove(parameters: dict) -> str:
    facts = _load(parameters.get("facts"), [])
    rules = _load(parameters.get("rules"), [])
    goal = _load(parameters.get("goal"), [])
    if not goal:
        return "Give me the thing to prove, as a list: ['may', 'read_file', 'run']."
    known = logic.Knowledge()
    for fact in facts:
        known.tell(*(fact if isinstance(fact, (list, tuple)) else [fact]))
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        conclusion = _load(rule.get("then"), [])
        if conclusion:
            known.when(conclusion, *[_load(item, [item]) for item in
                                     _load(rule.get("if"), [])])
    answer = known.ask(*(goal if isinstance(goal, (list, tuple)) else [goal]))
    return _say([answer, _course_hint("AI", 3)])


def _plan(parameters: dict) -> str:
    steps = [str(step) for step in _load(parameters.get("steps"), [])]
    if not steps:
        return "Give me the steps, in any order, and what each one needs."
    needs = _load(parameters.get("needs"), {})
    result = plan.order(steps, needs)
    if not result["ok"]:
        return _say([f"That plan cannot be ordered: {result['why']}.",
                     "A cycle is not a plan, it is the reason the last attempt looped.",
                     _course_hint("DS", 5)])
    return _say([f"Order: {' -> '.join(result['order'])}", result["why"],
                 _course_hint("DS", 5)])


def _route(parameters: dict) -> str:
    edges = _load(parameters.get("edges"), {})
    start = str(parameters.get("start") or "").strip()
    goal = str(parameters.get("goal_node") or parameters.get("goal") or "").strip()
    if not (start and goal):
        return ("Give me a start and a goal, and the edges: "
                "{'a': [['b', 2], ['c', 5]]}.")
    def neighbours(node):
        return [(str(target), float(weight))
                for target, weight in edges.get(node, [])]
    result = plan.shortest_from(start, goal, neighbours)
    if not result["ok"]:
        return _say([f"No route: {result['why']}.", _course_hint("DAA", 3)])
    return _say([f"Cheapest route: {' -> '.join(result['path'])}, cost {result['cost']}",
                 result["why"], _course_hint("DAA", 3)])


def _budget(parameters: dict) -> str:
    try:
        size = int(parameters.get("size") or 0)
    except (TypeError, ValueError):
        return "Give me the size of the job as a number."
    if size <= 0:
        return "Give me the size of the job as a number greater than zero."
    deadline = float(parameters.get("deadline") or 0) or choose.budget_for(size)
    result = choose.plan_work(size, deadline)
    return _say([f"{result['shape']}: {result['why']}",
                 "Exact" if result["exact"] else "Approximate, and said so",
                 _course_hint("DAA", 5)])


def _check(parameters: dict) -> str:
    rows = _load(parameters.get("records"), [])
    if not isinstance(rows, list) or not rows:
        return "Give me the records as a list of objects, each with an id."
    result = records.integrity(rows)
    if result["ok"]:
        return _say([f"{len(rows)} record(s): {result['why']}.",
                     _course_hint("DBMS", 2)])
    return _say([f"{len(rows)} record(s), {result['why']}:"] +
                [f"  {fault.kind}: {fault.key} — {fault.detail}"
                 for fault in result["faults"][:10]] + [_course_hint("DBMS", 2)])


def _why(parameters: dict) -> str:
    course = str(parameters.get("course") or "").strip()
    rows = registry.by_course(course) if course else registry.catalogue()
    if not rows:
        return (f"I have no logic cited to '{course}'. The courses I hold logic for: "
                + ", ".join(sorted({row['course'] for row in registry.catalogue()})) + ".")
    lines = [f"{row['course']} unit {row['unit']}: {row['topic']}"
             f" — {row['function']}" for row in rows[:25]]
    return _say([f"{len(rows)} citation(s):", *lines])


ACTIONS = {
    "map": _map, "logic": _map, "coverage": _map,
    "may": _may, "permitted": _may, "allowed": _may,
    "prove": _prove, "infer": _prove, "entails": _prove,
    "plan": _plan, "order": _plan, "steps": _plan,
    "route": _route, "path": _route, "cheapest": _route,
    "budget": _budget, "work": _budget, "exact": _budget,
    "check": _check, "records": _check, "integrity": _check,
    "why": _why, "cite": _why, "citations": _why,
}


def reasoning(parameters: dict) -> str:
    """Run one piece of the syllabus, and name the unit that produced the answer."""
    parameters = dict(parameters or {})
    action = str(parameters.get("action") or "map").strip().lower()
    handler = ACTIONS.get(action)
    if handler is None:
        return (f"I do not know the action '{action}'. I can: map, may, prove, plan, "
                f"route, budget, check, why.")
    try:
        return handler(parameters)
    except ValueError as error:
        return str(error)
    except Exception as error:
        failures.note("reasoning.reasoning", error)
        return "That did not work, and I have recorded why. Nothing was changed."


TOOL = {
    "name": "reasoning",
    "description": (
        "Ultron's own reasoning kernel, built from the owner's AKTU syllabus: "
        "forward chaining and proof (AI unit 3, DSTL unit 3), topological ordering of "
        "steps (DS unit 5), shortest-path routing (DAA unit 3), exact-or-approximate "
        "work planning by size and deadline (DAA unit 5), and record integrity (DBMS "
        "unit 2). Use it before any multi-step task: 'plan' the steps, then take them "
        "in that order. Use 'prove' when the question is whether something follows "
        "from the facts rather than whether it is true. Use 'budget' before a large "
        "exact computation. Every answer names the unit it came from, so quote that "
        "unit when you explain your reasoning."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": ("map (which topics run as code), may (is this tool "
                                "permitted, and by which chain), prove (does the goal "
                                "follow), plan (order the steps), route (cheapest "
                                "path), budget (exact or approximate), check (record "
                                "integrity), why (the citations)."),
                "enum": ["map", "may", "prove", "plan", "route", "budget", "check",
                         "why"],
            },
            "facts": {"type": "STRING",
                      "description": "For prove: JSON list of atoms, e.g. "
                                     "[['tier','read_file','routine']]."},
            "rules": {"type": "STRING",
                      "description": "For prove: JSON list of "
                                     "{'if': [[...]], 'then': [...]}."},
            "goal": {"type": "STRING",
                     "description": "For prove: the atom to derive, e.g. "
                                    "['may','read_file','run']."},
            "steps": {"type": "STRING",
                      "description": "For plan: JSON list of step names."},
            "needs": {"type": "STRING",
                      "description": "For plan: JSON object of step -> steps it needs."},
            "edges": {"type": "STRING",
                      "description": "For route: JSON object of node -> [[node, cost]]."},
            "start": {"type": "STRING", "description": "For route: the start node."},
            "goal_node": {"type": "STRING", "description": "For route: the goal node."},
            "size": {"type": "INTEGER", "description": "For budget: how many items."},
            "deadline": {"type": "NUMBER",
                         "description": "For budget: the work budget, in the same "
                                        "units the kernel reports."},
            "records": {"type": "STRING",
                        "description": "For check: JSON list of records with an id."},
            "tool": {"type": "STRING",
                     "description": "For may: the tool name, e.g. file_controller."},
            "tool_action": {"type": "STRING",
                            "description": "For may: the action on that tool, e.g. write."},
            "course": {"type": "STRING",
                       "description": "For why: a course code such as DAA or DBMS."},
        },
        "required": ["action"],
    },
    "handler": reasoning,
}
