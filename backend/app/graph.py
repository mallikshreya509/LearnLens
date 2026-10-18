"""Concept graph: turn each concept's prerequisite names into layers and edges.

The model can return prerequisite loops (A needs B, B needs A) or reference
names that do not exist. This module keeps only edges that form a valid
directed acyclic graph, so the UI can always lay it out left to right.
"""
import heapq

from .schemas import Concept, ConceptGraph, GraphEdge, GraphNode


def _reaches(adj: dict[str, list[str]], start: str, goal: str) -> bool:
    stack, seen = [start], set()
    while stack:
        node = stack.pop()
        if node == goal:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adj[node])
    return False


def build_graph(concepts: list[Concept]) -> ConceptGraph:
    index = {c.id: i for i, c in enumerate(concepts)}
    id_by_name = {c.name: c.id for c in concepts}

    # Candidate edges (prerequisite -> concept): known names only, no self-links, no duplicates.
    candidates: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for c in concepts:
        for name in c.prerequisites:
            pid = id_by_name.get(name)
            if pid is None or pid == c.id or (pid, c.id) in seen:
                continue
            seen.add((pid, c.id))
            candidates.append((pid, c.id))

    # Keep an edge only if it does not close a cycle with the edges kept so far.
    adj: dict[str, list[str]] = {c.id: [] for c in concepts}
    kept: list[tuple[str, str]] = []
    ignored = 0
    for source, target in candidates:
        if _reaches(adj, target, source):
            ignored += 1
            continue
        adj[source].append(target)
        kept.append((source, target))

    parents: dict[str, list[str]] = {c.id: [] for c in concepts}
    indegree = {c.id: 0 for c in concepts}
    for source, target in kept:
        parents[target].append(source)
        indegree[target] += 1

    # Kahn's algorithm. The heap breaks ties by the model's own concept order, so the
    # study order stays as close as possible to the order the model suggested.
    heap = [index[cid] for cid, d in indegree.items() if d == 0]
    heapq.heapify(heap)
    layer: dict[str, int] = {}
    study_order: list[str] = []
    while heap:
        cid = concepts[heapq.heappop(heap)].id
        layer[cid] = 1 + max((layer[p] for p in parents[cid]), default=-1)
        study_order.append(cid)
        for nxt in adj[cid]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(heap, index[nxt])

    return ConceptGraph(
        nodes=[GraphNode(id=c.id, layer=layer[c.id]) for c in concepts],
        edges=[GraphEdge(source=s, target=t) for s, t in kept],
        study_order=study_order,
        ignored_edges=ignored,
    )
