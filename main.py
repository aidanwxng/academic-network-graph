import httpx
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Any, Dict, List, Set, Optional, Tuple
from collections import deque

OPENALEX_BASE = "https://api.openalex.org"

app = FastAPI(title="Academic Networking Graph")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------
# SAFE UTILITIES
# ----------------------------------------------------

def normalize_author_id(author_id: Optional[str]) -> Optional[str]:
    """Return OpenAlex author ID or None."""
    if not author_id:
        return None
    if isinstance(author_id, str) and author_id.startswith("http"):
        return author_id.rstrip("/").split("/")[-1]
    return author_id


async def openalex_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """GET from OpenAlex with error handling."""
    url = f"{OPENALEX_BASE}{path}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url, params=params)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"OpenAlex error: {r.text}")
        return r.json()


async def fetch_author_details(aid: str) -> Dict[str, Any]:
    """Fetch complete author info from OpenAlex."""
    data = await openalex_get(f"/authors/{aid}")
    inst = None
    if data.get("last_known_institution"):
        inst = data["last_known_institution"].get("display_name")

    return {
        "id": aid,
        "label": data.get("display_name", aid),
        "institution": inst,
        "works_count": data.get("works_count"),
        "url": data.get("id"),
    }


# ----------------------------------------------------
# SEARCH
# ----------------------------------------------------

@app.get("/api/search_authors")
async def search_authors(query: str = Query(..., min_length=2)):
    """Return top 10 matches for a name."""
    data = await openalex_get("/authors", params={"search": query, "per-page": 10})
    results = []
    for a in data.get("results", []):
        inst = None
        if a.get("last_known_institution"):
            inst = a["last_known_institution"].get("display_name")
        results.append({
            "id": a.get("id"),
            "short_id": normalize_author_id(a.get("id")),
            "display_name": a.get("display_name"),
            "institution": inst,
            "works_count": a.get("works_count"),
        })
    return {"results": results}


# ----------------------------------------------------
# MAIN GRAPH (BFS)
# ----------------------------------------------------

@app.get("/api/graph")
async def coauthor_graph(
    author_id: str = Query(...),
    depth: int = Query(1, ge=1, le=3),
    max_nodes: int = Query(300, ge=20, le=1200)
):
    """Build a co-author graph with BFS."""
    root = normalize_author_id(author_id)

    nodes: Dict[str, Dict[str, Any]] = {}
    edges: Dict[Tuple[str, str], int] = {}
    visited: Set[str] = set()
    queue = deque([(root, 0)])

    # Fetch full info for root
    nodes[root] = await fetch_author_details(root)
    nodes[root]["level"] = 0
    nodes[root]["is_center"] = True

    while queue and len(nodes) < max_nodes:
        current, level = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        if level >= depth:
            continue

        # Fetch works of the current author
        works = await openalex_get(
            "/works",
            params={
                "filter": f"authorships.author.id:{current}",
                "per-page": 30,              # LOWER = FASTER
                "select": "authorships"      # LIMIT PAYLOAD
            }
        )

        for w in works.get("results", []):
            for au in w.get("authorships", []):
                auth = au.get("author")
                if not auth:
                    continue
                raw_id = auth.get("id")
                co_id = normalize_author_id(raw_id)
                if not co_id or co_id == current:
                    continue

                # Add placeholder node if new
                if co_id not in nodes:
                    nodes[co_id] = {
                        "id": co_id,
                        "label": co_id,
                        "level": level + 1,
                        "needs_fetch": True,
                    }
                    if len(nodes) < max_nodes:
                        queue.append((co_id, level + 1))

                # Track edge weight
                key = tuple(sorted((current, co_id)))
                edges[key] = edges.get(key, 0) + 1

    # Resolve all placeholders
    for aid, node in list(nodes.items()):
        if node.get("needs_fetch"):
            try:
                full = await fetch_author_details(aid)
                full["level"] = node["level"]
                nodes[aid] = full
            except Exception:
                pass

    return {
        "nodes": list(nodes.values()),
        "edges": [{"source": a, "target": b, "weight": w} for (a, b), w in edges.items()],
    }


# ----------------------------------------------------
# SHORTEST PATH (ROBUST VERSION)
# ----------------------------------------------------

@app.get("/api/shortest_path")
async def shortest_path(author_a: str = Query(...), author_b: str = Query(...)):
    """Compute the shortest co-author chain between two authors."""
    start = normalize_author_id(author_a)
    target = normalize_author_id(author_b)

    queue = deque([start])
    parent = {start: None}

    while queue:
        current = queue.popleft()

        if current == target:
            # reconstruct
            path = []
            while current is not None:
                path.append(current)
                current = parent[current]
            return {"path": path[::-1]}

        # Get neighbors
        works = await openalex_get(
            "/works",
            params={
                "filter": f"authorships.author.id:{current}",
                "per-page": 30,
                "select": "authorships",
            }
        )

        neighbors = set()
        for w in works.get("results", []):
            for au in w.get("authorships", []):
                author_data = au.get("author")
                if not author_data:
                    continue
                co_id = normalize_author_id(author_data.get("id"))
                if co_id and co_id not in parent:
                    neighbors.add(co_id)

        for n in neighbors:
            parent[n] = current
            queue.append(n)

    return {"path": []}


# ----------------------------------------------------
# STATIC FRONT-END
# ----------------------------------------------------

app.mount("/", StaticFiles(directory="static", html=True), name="static")
