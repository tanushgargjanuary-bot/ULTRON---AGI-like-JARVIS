"""What follows from what — the DSTL unit 3 and AI unit 3 rules, running.

Ultron answers a permission question a hundred times a day: may this tool run without
asking, may this file be written, may this be remembered. Today each answer is an `if`
somewhere, and six `if`s that must agree are six chances to disagree.

This module is the other way. Facts go in, rules go in, and the answer comes out with
the chain that produced it:

    facts = {("may", "read_file"), ("guarded", "read_file")}
    rules = [Rule(("guarded", "review"), body=(("may", "review"),))]

    forward_chain(facts, rules)   ->  derived facts, each with its proof

    propositions of DSTL unit 3   truth tables, tautology, contradiction, satisfiability
    theory of inference           forward chaining over Horn-like rules
    predicate logic, AI unit 3    terms and unification, one level of variables

WHAT IT IS NOT
    Not a Prolog. There is no search over clauses, no negation as failure, and no
    cut. It answers "what is derivable in one forward pass, and by which rule", which
    is exactly what a permission question needs and all that a permission question
    can be trusted with.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.mental.registry import implements


@dataclass(frozen=True)
class Rule:
    """If every premise holds, the conclusion holds. Named, so a proof can cite it."""

    conclusion: tuple
    body: tuple[tuple, ...] = ()
    name: str = ""

    def __post_init__(self):
        object.__setattr__(self, "conclusion", tuple(self.conclusion))
        object.__setattr__(self, "body", tuple(tuple(item) for item in self.body))

    def label(self) -> str:
        return self.name or f"{'+'.join(_text(p) for p in self.body) or 'fact'} -> " \
                            f"{_text(self.conclusion)}"


def _text(atom: tuple) -> str:
    return "(" + " ".join(str(part) for part in atom) + ")"


@implements("AI", 3, "Forward chaining and backward chaining")
def forward_chain(facts, rules) -> dict:
    """Derive everything derivable. Returns the facts and the chain that made each.

    One pass, repeated until nothing new appears. A rule fires once, and its proof is
    the proof of every premise plus its own name — which is what makes the answer
    auditable instead of merely correct-looking.
    """
    known = {tuple(item) for item in facts}
    proof = {fact: ["given"] for fact in known}
    fired = []
    changed = True
    while changed:
        changed = False
        for rule in rules:
            if rule.conclusion in known:
                continue
            if all(premise in known for premise in rule.body):
                known.add(rule.conclusion)
                steps = []
                for premise in rule.body:
                    steps.extend(proof.get(premise, ["?"]))
                proof[rule.conclusion] = steps + [rule.label()]
                fired.append(rule.label())
                changed = True
    return {"facts": known, "proof": proof, "fired": fired}


@implements("AI", 3, "Resolution")
def refute(facts, rules, goal: tuple) -> dict:
    """Can the goal be derived? If not, say so — and say what that does and does not mean.

    A refusal here is "not derivable from what I was given", never "false". That
    distinction is the whole of the honest use of logic in an assistant: silence is
    not evidence.
    """
    result = forward_chain(facts, rules)
    if tuple(goal) in result["facts"]:
        return {"derivable": True, "chain": result["proof"][tuple(goal)]}
    return {"derivable": False, "chain": [],
            "why": "not derivable from the facts and rules I was given; that is not "
                   "the same as false"}


@implements("DSTL", 3, "Propositions, truth tables, tautology, satisfiability, contradiction")
def truth_table(expression, variables=("p", "q")) -> list[dict]:
    """Every row of a truth table for a small expression, as DSTL writes it first.

    The expression is a callable of the variables. A table is the honest way to show
    a student — or a reader of a proof — that a claim holds for every case rather than
    the cases someone thought of.
    """
    rows = []
    for bits in _assignments(len(variables)):
        values = dict(zip(variables, bits))
        rows.append({**values, "value": bool(expression(**values))})
    return rows


def _assignments(width: int):
    for number in range(2 ** width):
        yield [bool(number & (1 << (width - 1 - index))) for index in range(width)]


@implements("DSTL", 3, "Propositions, truth tables, tautology, satisfiability, contradiction")
def classify(expression, variables=("p", "q")) -> str:
    """'tautology', 'contradiction' or 'satisfiable' — the three words DSTL uses."""
    values = [row["value"] for row in truth_table(expression, variables)]
    if all(values):
        return "tautology"
    if not any(values):
        return "contradiction"
    return "satisfiable"


@dataclass
class Knowledge:
    """Facts and rules held together, with the last derivation kept."""

    facts: set = field(default_factory=set)
    rules: list = field(default_factory=list)
    last: dict = field(default_factory=dict)

    def tell(self, *atom) -> "Knowledge":
        self.facts.add(tuple(atom))
        return self

    def when(self, conclusion, *body) -> "Knowledge":
        self.rules.append(Rule(tuple(conclusion), tuple(tuple(p) for p in body)))
        return self

    def ask(self, *atom) -> str:
        """The answer, with the chain, in one sentence."""
        answer = refute(self.facts, self.rules, tuple(atom))
        self.last = answer
        question = _text(tuple(atom))
        if answer["derivable"]:
            return f"{question} follows: " + " -> ".join(answer["chain"])
        return f"{question} does not follow. {answer['why']}"


def permission_rules(tiers: dict) -> list[Rule]:
    """The shape of a permission decision, as rules instead of if-statements.

    `tiers` maps a tool name to its tier — the same table the policy already uses.
    A tool that asks first cannot be treated as routine by any chain of reasoning,
    because the last rule has no body and no way to be satisfied except by the fact
    itself.
    """
    rules = []
    for tool, tier in tiers.items():
        rules.append(Rule(("tier", tool, str(tier)), name=f"{tool} is {tier}"))
        for verb, needed in (("ask", "confirm"), ("refuse", "blocked"),
                             ("run", "routine")):
            rules.append(Rule(("may", tool, verb),
                              body=((("tier", tool, needed),)),
                              name=f"{tier} means {verb}" if needed == str(tier)
                              else f"{needed} is not {tier}"))
    return rules
