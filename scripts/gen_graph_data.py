"""Regenerate frontend/src/lib/graph.ts from the real gold graph in evaluate.py.

Run from the repo root:  .venv/bin/python scripts/gen_graph_data.py

Positions are computed here, once, with a deterministic Fruchterman-Reingold
layout and baked into the file. That keeps the frontend free of a layout
dependency and — more importantly — makes the picture STABLE: the same graph
draws identically every load, so a reader can learn its shape.
"""
import json
import math
import pathlib
import random

from callosum.evaluate import GOLD_GROUPS

ents, edges = {}, []
for doc, es, rs, conf in GOLD_GROUPS:
    for e in es:
        ents.setdefault(e[0], {
            "type": str(e[1]).split(".")[-1],
            "attrs": e[2] if len(e) > 2 else {},
            "document": doc,
            "restricted": bool(conf),
        })
    for r in rs:
        edges.append({
            "source": r[0],
            "relation": str(r[1]).split(".")[-1],
            "target": r[2],
            "quote": r[3] if len(r) > 3 else "",
            "document": doc,
            "restricted": bool(conf),
        })

names = list(ents)
idx = {n: i for i, n in enumerate(names)}
N = len(names)

# --- deterministic force-directed layout -----------------------------------
random.seed(7)
W = H = 1000.0
pos = []
for i in range(N):
    a = 2 * math.pi * i / N
    pos.append([W / 2 + 260 * math.cos(a) + random.uniform(-18, 18),
                H / 2 + 260 * math.sin(a) + random.uniform(-18, 18)])

adj = [[0] * N for _ in range(N)]
for e in edges:
    if e["source"] in idx and e["target"] in idx:
        a, b = idx[e["source"]], idx[e["target"]]
        adj[a][b] = adj[b][a] = 1

k = math.sqrt(W * H / N) * 0.82
temp = W / 8
for step in range(420):
    disp = [[0.0, 0.0] for _ in range(N)]
    for i in range(N):
        for j in range(i + 1, N):
            dx, dy = pos[i][0] - pos[j][0], pos[i][1] - pos[j][1]
            d2 = dx * dx + dy * dy
            d = math.sqrt(d2) or 0.01
            rep = (k * k) / d
            ux, uy = dx / d, dy / d
            disp[i][0] += ux * rep; disp[i][1] += uy * rep
            disp[j][0] -= ux * rep; disp[j][1] -= uy * rep
            if adj[i][j]:
                att = (d * d) / k
                disp[i][0] -= ux * att; disp[i][1] -= uy * att
                disp[j][0] += ux * att; disp[j][1] += uy * att
    for i in range(N):
        dx, dy = disp[i]
        d = math.hypot(dx, dy) or 0.01
        pos[i][0] += dx / d * min(d, temp)
        pos[i][1] += dy / d * min(d, temp)
        pos[i][0] = min(W, max(0.0, pos[i][0]))
        pos[i][1] = min(H, max(0.0, pos[i][1]))
    temp = max(temp * 0.975, 1.2)

xs = [p[0] for p in pos]; ys = [p[1] for p in pos]
minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
SPAN_X, SPAN_Y = 1180.0, 660.0
def norm(p):
    return (
        round((p[0] - minx) / (maxx - minx or 1) * SPAN_X, 1),
        round((p[1] - miny) / (maxy - miny or 1) * SPAN_Y, 1),
    )

pos = [list(norm(p)) for p in pos]

# --- overlap resolution ----------------------------------------------------
# The simulation above treats every node as a point, but they render as labelled
# boxes, so long labels collided ("Adopt Usage-Based Pricing" sat on top of
# "Reject Pricing Model B"). Push overlapping boxes apart using their APPROXIMATE
# rendered size, then let a few gentle spring steps re-tidy what that disturbed.
def box(name):
    w = min(168.0, 34.0 + len(name) * 6.2)
    return w, 40.0

BOX_GAP = 12.0
for _ in range(260):
    moved = False
    for i in range(N):
        wi, hi = box(names[i])
        for j in range(i + 1, N):
            wj, hj = box(names[j])
            dx = pos[i][0] - pos[j][0]
            dy = pos[i][1] - pos[j][1]
            ox = (wi + wj) / 2 + BOX_GAP - abs(dx)
            oy = (hi + hj) / 2 + BOX_GAP - abs(dy)
            if ox > 0 and oy > 0:
                moved = True
                # Separate along the axis needing the least travel.
                if ox < oy:
                    s = ox / 2 * (1 if dx >= 0 else -1)
                    pos[i][0] += s; pos[j][0] -= s
                else:
                    s = oy / 2 * (1 if dy >= 0 else -1)
                    pos[i][1] += s; pos[j][1] -= s
    if not moved:
        break



nodes_ts = []
for n in names:
    m = ents[n]
    x, y = pos[idx[n]]
    nodes_ts.append({
        "id": n, "label": n, "type": m["type"], "role": m["attrs"].get("role", ""),
        "detail": m["attrs"].get("status") or m["attrs"].get("value") or "",
        "document": m["document"], "restricted": m["restricted"], "x": round(x, 1), "y": round(y, 1),
    })

edges_ts = []
for i, e in enumerate(edges):
    if e["source"] not in idx or e["target"] not in idx:
        continue
    edges_ts.append({
        "id": f"e{i}", "source": e["source"], "target": e["target"],
        "relation": e["relation"], "quote": e["quote"],
        "document": e["document"], "restricted": e["restricted"],
    })

deg = {n: 0 for n in names}
for e in edges_ts:
    deg[e["source"]] += 1
    deg[e["target"]] += 1
for n in nodes_ts:
    n["degree"] = deg[n["id"]]


# --- emit the TypeScript module --------------------------------------------
def ts(v):
    return json.dumps(v, ensure_ascii=False)

nodes_src = ",\n".join(
    "  { id: %s, label: %s, type: %s, role: %s, detail: %s, document: %s, restricted: %s, degree: %d, x: %s, y: %s }"
    % (ts(n["id"]), ts(n["label"]), ts(n["type"]), ts(n["role"]), ts(n["detail"]),
       ts(n["document"]), "true" if n["restricted"] else "false", n["degree"], n["x"], n["y"])
    for n in nodes_ts)

edges_src = ",\n".join(
    "  { id: %s, source: %s, target: %s, relation: %s, quote: %s, document: %s, restricted: %s }"
    % (ts(e["id"]), ts(e["source"]), ts(e["target"]), ts(e["relation"]),
       ts(e["quote"]), ts(e["document"]), "true" if e["restricted"] else "false")
    for e in edges_ts)

out = pathlib.Path(__file__).resolve().parents[1] / "frontend/src/lib/graph.ts"
src = out.read_text(encoding="utf8")
head = src.split("export const GRAPH_NODES")[0]
tail = src.split("];\n\n", 2)[-1]
out.write_text(
    head
    + "export const GRAPH_NODES: GraphNodeData[] = [\n" + nodes_src + ",\n];\n\n"
    + "export const GRAPH_EDGES: GraphEdgeData[] = [\n" + edges_src + ",\n];\n\n"
    + tail,
    encoding="utf8",
)
print(f"wrote {out} — {len(nodes_ts)} nodes, {len(edges_ts)} edges")

