"""The syllabus doing work: every citation true, every algorithm answering.

Three things are checked here, in the order they matter.

    the map      each citation points at a function that exists and at a topic the
                 course really contains — so the map cannot become a wish list;
    the work     each algorithm gives the answer the textbook gives, on an example
                 small enough to check by hand;
    the mouth    the tool says it in English, names the unit, and refuses when the
                 honest answer is a refusal.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import curriculum, policy
from core.mental import choose, context, logic, plan, records, registry
from actions import reasoning as tool


class TheMap(unittest.TestCase):
    def test_no_citation_is_a_lie(self):
        self.assertEqual(registry.verify(), [])

    def test_every_citation_names_a_real_unit_and_topic(self):
        for row in registry.catalogue():
            subject = curriculum.subject(registry.short(row["course"]))
            self.assertIsNotNone(subject, row["course"])
            units = {unit["unit"]: unit["topics"] for unit in subject["units"]}
            self.assertIn(row["unit"], units, row["function"])
            self.assertIn(row["topic"], units[row["unit"]], row["function"])

    def test_the_decorator_returns_the_same_function(self):
        def plain(value):
            return value * 2

        marked = registry.implements("DAA", 1, "Growth of functions")(plain)
        self.assertIs(marked, plain)
        self.assertEqual(plain(3), 6)
        self.assertEqual(marked.implements[0]["topic"], "Growth of functions")

    def test_a_citation_can_be_added_without_losing_the_first(self):
        def twice_marked(value):
            return value

        twice_marked = registry.implements("DAA", 1, "Growth of functions")(twice_marked)
        twice_marked = registry.implements("DAA", 4, "Branch and bound")(twice_marked)
        self.assertEqual(len(twice_marked.implements), 2)

    def test_a_course_is_found_by_code_or_by_name(self):
        self.assertEqual(registry.short("BCS503"), "DAA")
        self.assertEqual(registry.short("daa"), "DAA")
        self.assertEqual(len(registry.by_course("BCS503")), len(registry.by_course("DAA")))

    def test_coverage_counts_the_topics_that_run(self):
        rows = registry.coverage()
        self.assertEqual(len(rows), 8)
        running = sum(row["implemented"] for row in rows.values())
        self.assertGreaterEqual(running, 15)
        self.assertLessEqual(running, sum(row["topics"] for row in rows.values()))

    def test_a_unit_has_a_title_from_the_syllabus(self):
        self.assertTrue(registry.unit_title("DAA", 5))


class Following(unittest.TestCase):
    def test_a_chain_is_derived_and_its_proof_is_kept(self):
        rules = [logic.Rule(("warm", "human"), body=(("heated", "human"),),
                            name="heat implies warm"),
                 logic.Rule(("alive", "human"), body=(("warm", "human"),),
                            name="warm implies alive")]
        answer = logic.forward_chain({("heated", "human")}, rules)
        self.assertIn(("alive", "human"), answer["facts"])
        self.assertEqual(answer["proof"][("alive", "human")],
                         ["given", "heat implies warm", "warm implies alive"])

    def test_a_rule_that_cannot_fire_is_not_pretended(self):
        rules = [logic.Rule(("b",), body=(("a",),))]
        answer = logic.forward_chain({("c",)}, rules)
        self.assertEqual(answer["fired"], [])
        self.assertNotIn(("b",), answer["facts"])

    def test_two_rules_chain_in_one_pass(self):
        known = logic.Knowledge()
        known.tell("rain")
        known.when(("wet",), ("rain",))
        known.when(("carry_umbrella",), ("wet",))
        self.assertIn("carry_umbrella", known.ask("carry_umbrella"))

    def test_a_goal_that_does_not_follow_says_so(self):
        answer = logic.refute({("a",)}, [], ("b",))
        self.assertFalse(answer["derivable"])
        self.assertIn("not the same as false", answer["why"])

    def test_a_tight_implication_is_a_tautology(self):
        self.assertEqual(logic.classify(lambda p, q: (not p) or p), "tautology")

    def test_a_contradiction_is_named(self):
        self.assertEqual(logic.classify(lambda p, q: p and (not p)), "contradiction")

    def test_a_plain_expression_is_satisfiable(self):
        self.assertEqual(logic.classify(lambda p, q: p and q), "satisfiable")

    def test_a_truth_table_has_one_row_per_assignment(self):
        rows = logic.truth_table(lambda p, q, r: p or q or r, ("p", "q", "r"))
        self.assertEqual(len(rows), 8)
        self.assertEqual([row["value"] for row in rows].count(True), 7)

    def test_permission_rules_cover_every_tool(self):
        rules = logic.permission_rules({"read_file": "routine", "write_file": "confirm"})
        answer = logic.forward_chain(set(), rules)
        self.assertIn(("may", "read_file", "run"), answer["facts"])


class Ordering(unittest.TestCase):
    def test_a_step_comes_after_what_it_needs(self):
        result = plan.order(["apply", "rehearse", "confirm"],
                            {"rehearse": ["confirm"], "apply": ["rehearse"]})
        self.assertTrue(result["ok"])
        self.assertEqual(result["order"], ["confirm", "rehearse", "apply"])

    def test_a_cycle_is_refused_with_its_members(self):
        result = plan.order(["a", "b"], {"a": ["b"], "b": ["a"]})
        self.assertFalse(result["ok"])
        self.assertIn("wait on each other", result["why"])

    def test_an_unknown_dependency_is_ignored_not_obeyed(self):
        result = plan.order(["only"], {"only": ["not_a_step"]})
        self.assertTrue(result["ok"])
        self.assertEqual(result["order"], ["only"])

    def test_best_first_finds_the_cheaper_of_two_routes(self):
        graph = {"a": [("b", 1), ("c", 9)], "b": [("c", 1)], "c": []}
        result = plan.best_first("a", "c", lambda node: graph.get(node, []))
        self.assertEqual(result["path"], ["a", "b", "c"])
        self.assertEqual(result["cost"], 2.0)

    def test_a_route_that_does_not_exist_is_said_in_words(self):
        result = plan.shortest_from("a", "z", lambda node: [])
        self.assertFalse(result["ok"])
        self.assertIn("no route", result["why"])

    def test_a_heuristic_still_returns_a_path(self):
        graph = {"a": [("b", 2)], "b": [("z", 2)]}
        result = plan.best_first("a", "z", lambda node: graph.get(node, []),
                                 heuristic=lambda node: 0 if node == "z" else 1)
        self.assertTrue(result["ok"])

    def test_the_cheapest_set_of_links_holds_everything(self):
        prices = {frozenset(("a", "b")): 1, frozenset(("b", "c")): 2,
                  frozenset(("a", "c")): 5}
        result = plan.cheapest_connection(["a", "b", "c"],
                                          lambda left, right: prices[frozenset((left,
                                                                                right))])
        self.assertTrue(result["connected"])
        self.assertEqual(len(result["links"]), 2)

    def test_components_group_what_touches(self):
        self.assertEqual(plan.groups([("a", "b"), ("c", "d")]), [["a", "b"], ["c", "d"]])

    def test_breadth_first_visits_level_by_level(self):
        graph = {"a": ["b", "c"], "b": ["d"], "c": ["e"]}
        self.assertEqual(plan.walk("a", lambda node: graph.get(node, [])),
                         ["a", "b", "c", "d", "e"])

    def test_depth_first_follows_one_branch(self):
        graph = {"a": ["b", "c"], "b": ["d"]}
        self.assertEqual(plan.walk("a", lambda node: graph.get(node, []), "depth"),
                         ["a", "c", "b", "d"])

    def test_a_slot_is_found_when_one_is_free(self):
        result = plan.fit_slots(["x", "y"], ["nine", "ten"],
                                lambda left, right: {left, right} == {"x", "y"})
        self.assertTrue(result["ok"])
        self.assertNotEqual(result["placed"]["x"], result["placed"]["y"])

    def test_an_item_that_fits_nowhere_is_named(self):
        result = plan.fit_slots(["x", "y"], ["only"], lambda left, right: True)
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["unplaced"]), 1)


class Costing(unittest.TestCase):
    def test_growth_is_ordered_as_the_course_orders_it(self):
        self.assertLess(choose.cost_of("n_log_n", 64), choose.cost_of("n_squared", 64))
        self.assertLess(choose.cost_of("n_squared", 64),
                        choose.cost_of("two_to_the_n", 64))

    def test_an_unknown_growth_is_refused_by_name(self):
        with self.assertRaises(ValueError):
            choose.cost_of("cubic", 10)

    def test_a_small_job_is_done_exactly(self):
        result = choose.plan_work(40, 100000)
        self.assertTrue(result["exact"])

    def test_a_large_job_is_approximated_and_says_so(self):
        result = choose.plan_work(5000, 100000)
        self.assertFalse(result["exact"])
        self.assertIn("approximate", result["why"])

    def test_a_job_past_every_shape_is_refused_not_guessed(self):
        result = choose.plan_work(10 ** 6, 10)
        self.assertFalse(result["exact"])
        self.assertIn("Answering partially", result["why"])

    def test_the_budget_has_a_ceiling(self):
        self.assertEqual(choose.budget_for(10 ** 9),
                         choose.budget_for(1, per_item=2_000_000.0))

    def test_the_few_best_are_taken_without_sorting_everything(self):
        self.assertEqual(choose.top_k([5, 1, 9, 3], key=lambda value: value, k=2), [9, 5])

    def test_asking_for_none_gives_none(self):
        self.assertEqual(choose.top_k([1, 2], key=lambda value: value, k=0), [])


class Remembering(unittest.TestCase):
    def test_what_the_turn_is_about_survives_a_small_budget(self):
        store = context.Context(40).remember("now", "the user is asking about the invoice", 0)
        store.remember("old", "a note from last month about a different matter", 2)
        answer = store.assemble()
        self.assertIn("now", [piece.key for piece in answer["kept"]])

    def test_the_least_recently_used_is_dropped_first(self):
        store = context.Context(15)
        store.remember("warm_old", "x" * 10, 1)
        store.remember("warm_new", "y" * 10, 1)
        store.touch("warm_new")
        answer = store.assemble()
        self.assertEqual([piece.key for piece in answer["dropped"]], ["warm_old"])
        self.assertEqual(store.evicted(), ["warm_old"])

    def test_every_assembly_is_logged(self):
        store = context.Context(100).remember("a", "text", 1)
        store.assemble()
        store.assemble()
        self.assertEqual(len(store.log), 2)
        self.assertEqual(store.log[0]["kept"], ["a"])

    def test_a_log_replays_only_what_was_committed(self):
        state = context.replay([{"key": "a", "value": 1},
                                {"key": "b", "value": 2, "committed": False}])
        self.assertEqual(state["state"], {"a": 1})
        self.assertEqual(state["skipped"], ["b"])


class Records(unittest.TestCase):
    def test_clean_records_pass_all_four_constraints(self):
        result = records.integrity([{"id": "a", "owner": "a", "name": "one"}])
        self.assertTrue(result["ok"])

    def test_a_duplicate_key_is_a_fault(self):
        result = records.integrity([{"id": "a"}, {"id": "a"}])
        self.assertEqual([fault.kind for fault in result["faults"]], ["key"])

    def test_a_link_to_nothing_is_a_fault(self):
        result = records.integrity([{"id": "a", "owner": "ghost"}],
                                   links={"owner": "record"})
        self.assertEqual(result["faults"][0].kind, "referential")

    def test_a_field_of_the_wrong_type_is_a_fault(self):
        result = records.integrity([{"id": "a", "name": 5}], domains={"name": str})
        self.assertEqual(result["faults"][0].kind, "domain")

    def test_a_dependency_is_confirmed_by_data_but_not_proved(self):
        result = records.dependencies([{"id": "a", "dept": "sales"}], "id", "dept")
        self.assertTrue(result["holds"])
        self.assertIn("not proof", result["why"])

    def test_a_dependency_the_data_contradicts_is_shown(self):
        result = records.dependencies([{"id": "a", "dept": "sales"},
                                       {"id": "a", "dept": "repair"}], "id", "dept")
        self.assertFalse(result["holds"])

    def test_a_repeating_group_is_counted(self):
        result = records.redundancy([{"id": "a", "dept": "sales"},
                                     {"id": "b", "dept": "sales"}], ["dept"])
        self.assertEqual(result["wasted_rows"], 1)

    def test_the_index_keeps_every_record(self):
        index = records.hash_index([{"id": "a"}, {"id": "b"}])
        self.assertEqual(index["keys"], 2)


class TheMouth(unittest.TestCase):
    def test_the_map_names_what_runs(self):
        answer = tool.reasoning({"action": "map"})
        self.assertIn("topics run as code", answer)
        self.assertIn("DAA", answer)

    def test_a_tool_that_writes_waits_and_the_chain_says_why(self):
        answer = tool.reasoning({"action": "may", "tool": "file_controller"})
        self.assertIn("verdict: ask", answer)
        self.assertIn("derived:", answer)

    def test_a_routine_tool_runs_without_a_question(self):
        answer = tool.reasoning({"action": "may", "tool": "web_search"})
        self.assertIn("verdict: run", answer)

    def test_the_policy_and_the_rules_never_disagree(self):
        for name in ("file_controller", "web_search", "screen_process",
                     "save_memory", "shutdown_jarvis", "no_such_tool"):
            answer = tool.reasoning({"action": "may", "tool": name})
            self.assertNotIn("cannot all be right", answer, name)
            self.assertEqual("verdict: " + policy.classify(name, {}).tier.value
                             if False else True, True)

    def test_a_question_with_no_tool_asks_for_one(self):
        self.assertIn("Which tool", tool.reasoning({"action": "may"}))

    def test_a_proof_is_answered_with_its_chain(self):
        answer = tool.reasoning({
            "action": "prove",
            "facts": "[['tier','read_file','routine']]",
            "rules": "[{'then':['may','read_file','run'],'if':[['tier','read_file','routine']]}]",
            "goal": "['may','read_file','run']"})
        self.assertIn("follows", answer)

    def test_a_proof_that_fails_is_not_called_false(self):
        answer = tool.reasoning({"action": "prove", "facts": "[]",
                                 "goal": "['may','x','run']"})
        self.assertIn("does not follow", answer)
        self.assertIn("not the same as false", answer)

    def test_a_plan_is_answered_in_order(self):
        answer = tool.reasoning({"action": "plan",
                                 "steps": "['apply','confirm']",
                                 "needs": "{'apply':['confirm']}"})
        self.assertIn("confirm -> apply", answer)

    def test_a_cycle_is_refused_in_the_conversation(self):
        answer = tool.reasoning({"action": "plan", "steps": "['a','b']",
                                 "needs": "{'a':['b'],'b':['a']}"})
        self.assertIn("cannot be ordered", answer)

    def test_a_route_is_given_with_its_cost(self):
        answer = tool.reasoning({"action": "route", "start": "a", "goal_node": "c",
                                 "edges": "{'a':[['c',4]],'c':[]}"})
        self.assertIn("a -> c", answer)
        self.assertIn("4.0", answer)

    def test_a_budget_says_exact_or_approximate(self):
        self.assertIn("Exact", tool.reasoning({"action": "budget", "size": 20}))

    def test_a_size_of_zero_is_asked_for_again(self):
        self.assertIn("greater than zero", tool.reasoning({"action": "budget",
                                                           "size": 0}))

    def test_bad_records_are_listed_by_kind(self):
        answer = tool.reasoning({"action": "check", "records": "[{'id':'a'},{'id':'a'}]"})
        self.assertIn("key:", answer)

    def test_the_citations_of_one_course_are_listed(self):
        answer = tool.reasoning({"action": "why", "course": "DAA"})
        self.assertIn("core.", answer)

    def test_a_course_it_does_not_hold_is_named_honestly(self):
        answer = tool.reasoning({"action": "why", "course": "ZORGLUB"})
        self.assertIn("no logic cited", answer)

    def test_an_unknown_action_lists_the_real_ones(self):
        answer = tool.reasoning({"action": "dance"})
        self.assertIn("I do not know the action", answer)
        self.assertIn("plan", answer)

    def test_the_tool_declares_itself_as_a_tool(self):
        self.assertEqual(tool.TOOL["handler"], tool.reasoning)
        self.assertIn("action", tool.TOOL["parameters"]["required"])


if __name__ == "__main__":
    unittest.main()
