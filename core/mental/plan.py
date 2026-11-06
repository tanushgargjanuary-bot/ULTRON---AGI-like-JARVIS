"""Putting steps in an order that is allowed, and finding the cheap way through.

Two different questions, and the syllabus answers them with two different machines.

    is this order allowed?      DS unit 5, topological sort. A step that needs a
                                confirmation cannot come before the confirmation.
    which order is cheapest?    AI unit 2, best-first search with a heuristic, and
                                DAA unit 3 greedy short-cutting when the estimate is
                                good enough.

Both refuse cycles. A plan that contains a loop is not a plan, it is a reason the last
three attempts failed, and saying that out loud is more useful than a stack trace.
"""

from __future__ import annotations

import heapq

from core.mental.registry import implements


@implements("DS", 5, "Topological sort")
def order(steps, needs: dict | None = None) -> dict:
    """Steps in an order where every step comes after the ones it needs.

    `steps` is an iterable of names. `needs` maps a name to the names it depends on.
    Kahn's algorithm, with the refusal at the end rather than a silent truncation: a
    partial order that drops the steps it could not place is worse than an error.
    """
    names = [str(step) for step in steps]
    needs = {str(key): [str(item) for item in value]
             for key, value in (needs or {}).items()}
    remaining = {name: {need for need in needs.get(name, []) if need in names}
                 for name in names}
    ordered = []
    while remaining:
        ready = sorted(name for name, requires in remaining.items() if not requires)
        if not ready:
            stuck = ", ".join(sorted(remaining)[:6])
            return {"order": ordered, "ok": False,
                    "why": f"these steps wait on each other: {stuck}"}
        name = ready[0]
        ordered.append(name)
        del remaining[name]
        for requires in remaining.values():
            requires.discard(name)
    return {"order": ordered, "ok": True, "why": f"{len(ordered)} steps, no cycle"}


@implements("AI", 2, "Informed search and heuristics")
def best_first(start: str, goal: str, neighbours, heuristic=None, limit: int = 500) -> dict:
    """A* through a small graph, returning the path and what it cost.

    `neighbours(node)` yields `(next_node, cost)`. `heuristic(node)` estimates the rest.
    The estimate is allowed to be wrong — it is not allowed to be missing without
    saying so, which is why the result carries the estimate it used.
    """
    estimate = heuristic or (lambda _node: 0.0)
    frontier = [(estimate(start), 0.0, start, [start])]
    seen = {}
    expanded = 0
    while frontier and expanded < limit:
        _rank, cost_so_far, node, path = heapq.heappop(frontier)
        if node == goal:
            return {"path": path, "cost": round(cost_so_far, 3), "ok": True,
                    "expanded": expanded,
                    "why": f"{len(path)} steps, cost {cost_so_far:.3f}, "
                           f"{expanded} nodes expanded"}
        expanded += 1
        if node in seen and seen[node] <= cost_so_far:
            continue
        seen[node] = cost_so_far
        for neighbour, cost in neighbours(node):
            rank = cost_so_far + float(cost) + estimate(neighbour)
            heapq.heappush(frontier, (rank, cost_so_far + float(cost), neighbour,
                                      path + [neighbour]))
    return {"path": [], "cost": None, "ok": False, "expanded": expanded,
            "why": (f"no route from {start!r} to {goal!r} inside {limit} expansions"
                    if expanded >= limit else f"no route from {start!r} to {goal!r}")}


@implements("DAA", 3, "Minimum spanning trees: Prim and Kruskal")
def cheapest_connection(items, cost) -> dict:
    """Kruskal over a small set of things that must all be connected.

    Used where the real question is "which links do I actually need": a chain of tool
    calls that shares setup, a set of files that share a compile, a list of facts that
    share a source. Greedy is correct here, which is exactly why the syllabus teaches
    it as the first greedy algorithm rather than the last.
    """
    names = list(items)
    edges = []
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            weight = float(cost(left, right))
            if weight < float("inf"):
                edges.append((weight, left, right))
    edges.sort(key=lambda edge: (edge[0], str(edge[1]), str(edge[2])))
    parent = {name: name for name in names}

    def root(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    chosen, total = [], 0.0
    for weight, left, right in edges:
        a, b = root(left), root(right)
        if a == b:
            continue
        parent[a] = b
        chosen.append((left, right, weight))
        total += weight
        if len(chosen) == max(0, len(names) - 1):
            break
    connected = len({root(name) for name in names}) <= 1
    return {"links": chosen, "cost": round(total, 3), "connected": connected,
            "why": ("cheapest set of links that holds everything together"
                    if connected else "some things cannot be reached at any price")}


@implements("DS", 5, "Connected components")
def groups(pairs) -> list[list[str]]:
    """Union-find over pairs, as plain connected components."""
    parent = {}

    def root(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for left, right in pairs:
        a, b = root(str(left)), root(str(right))
        if a != b:
            parent[a] = b
    bins = {}
    for node in list(parent):
        bins.setdefault(root(node), []).append(node)
    return sorted((sorted(group) for group in bins.values()), key=len, reverse=True)


@implements("DS", 5, "Depth-first search and breadth-first search")
def walk(start: str, neighbours, mode: str = "breadth") -> list[str]:
    """Every node reachable from start, in breadth-first or depth-first order.

    The two orders are the same three lines with a different container, which is the
    point the syllabus makes: the algorithm is the shape, the data structure is the
    choice.
    """
    frontier = [str(start)]
    seen = {str(start)}
    order = []
    while frontier:
        node = frontier.pop(0 if mode == "breadth" else -1)
        order.append(node)
        for neighbour in neighbours(node):
            name = str(neighbour[0] if isinstance(neighbour, tuple) else neighbour)
            if name not in seen:
                seen.add(name)
                frontier.append(name)
    return order


@implements("DAA", 3, "Single-source shortest paths: Dijkstra and Bellman-Ford")
def shortest_from(start: str, goal: str, neighbours) -> dict:
    """Dijkstra, which is best-first search with no estimate at all.

    Kept as its own name because that is what a caller means when the costs are real
    and the guess would be invented: a route through tools that each cost a measured
    number of milliseconds.
    """
    return best_first(start, goal, neighbours, heuristic=None)


@implements("AI", 2, "Constraint satisfaction problems")
def fit_slots(items, slots, conflicts=None) -> dict:
    """Assign each item to a slot that nothing else in it conflicts with.

    A constraint satisfaction problem in its smallest form: domains of one slot, one
    binary constraint, and a refusal when the domains run out rather than an assignment
    that breaks a rule. Used where a schedule has to respect what cannot overlap.
    """
    conflicts = conflicts or (lambda left, right: False)
    taken: dict[str, list] = {str(slot): [] for slot in slots}
    placed, unplaced = {}, []
    for item in sorted(items, key=str):
        for name, members in taken.items():
            if not any(conflicts(item, other) for other in members):
                members.append(item)
                placed[str(item)] = name
                break
        else:
            unplaced.append(str(item))
    return {"placed": placed, "unplaced": unplaced, "ok": not unplaced,
            "why": ("every item found a slot" if not unplaced else
                    f"{len(unplaced)} item(s) fit no slot without breaking a rule: "
                    + ", ".join(unplaced[:5]))}
