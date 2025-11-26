//----------------------------------------------------------
// GLOBALS
//----------------------------------------------------------
let network = null;
let graphNodes = null;
let graphEdges = null;

const infoDiv = document.getElementById("info");


//----------------------------------------------------------
// UTILITY: LOADING SPINNER
//----------------------------------------------------------
function showLoader(message = "Loading...") {
  infoDiv.innerHTML = `
    <div class="loader"></div>
    <p>${message}</p>
  `;
}


//----------------------------------------------------------
// SEARCH FUNCTIONALITY
//----------------------------------------------------------
document.getElementById("search-button").onclick = async () => {
  const q = document.getElementById("search-input").value.trim();
  if (!q) return;

  showLoader("Searching...");

  const url = `/api/search_authors?query=${encodeURIComponent(q)}`;
  const data = await fetch(url).then(r => r.json());

  if (!data.results.length) {
    infoDiv.innerHTML = "No results.";
    return;
  }

  // Render clickable results
  infoDiv.innerHTML = data.results.map(r => `
    <div style="margin-bottom: 10px;">
      <b style="cursor:pointer;color:#2563eb;"
         onclick="loadGraph('${r.short_id}')">
        ${r.display_name}
      </b>
      <span style="color:#6b7280">(${r.short_id})</span>
      <br>
      <span>${r.institution || "Unknown institution"}</span>
    </div>
  `).join("");
};


//----------------------------------------------------------
// GRAPH LOADING
//----------------------------------------------------------
window.loadGraph = async function(authorId) {
  const depth = parseInt(document.getElementById("degree-input").value);
  showLoader("Building graph...");

  const url = `/api/graph?author_id=${authorId}&depth=${depth}`;
  const data = await fetch(url).then(r => r.json());

  renderGraph(data);
};


function renderGraph(data) {
  const container = document.getElementById("graph");

  graphNodes = new vis.DataSet(
    data.nodes.map(n => ({
      id: n.id,
      label: n.label,
      title: n.institution || "",
      color: n.is_center ? "#f97316" : "#60a5fa",
      level: n.level,
      shape: "dot",
      size: n.is_center ? 20 : 12,
      _meta: n
    }))
  );

  graphEdges = new vis.DataSet(
    data.edges.map(e => ({
      id: `e_${e.source}_${e.target}`,
      from: e.source,
      to: e.target,
      width: Math.min(6, 1 + Math.log(1 + (e.weight || 1))),
      color: "#cbd5e1"
    }))
  );

    const options = {
    physics: {
        enabled: true,
        solver: "forceAtlas2Based",
        forceAtlas2Based: {
        gravitationalConstant: -50,
        centralGravity: 0.005,
        springLength: 120,
        springConstant: 0.08,
        avoidOverlap: 1
        },
        stabilization: { iterations: 60 },
    },
    layout: { improvedLayout: true },
    };

  if (network) network.destroy();
  network = new vis.Network(container, { nodes: graphNodes, edges: graphEdges }, options);

    network.once("stabilizationIterationsDone", function () {
    network.setOptions({ physics: false });
    });

  network.on("selectNode", params => {
    const node = graphNodes.get(params.nodes[0]);
    showNodeDetails(node._meta);
  });

  infoDiv.innerHTML = "Click a node to see details.";
}


//----------------------------------------------------------
// NODE DETAILS
//----------------------------------------------------------
function showNodeDetails(meta) {
  infoDiv.innerHTML = `
    <h3>${meta.label}</h3>
    <p><b>Institution:</b> ${meta.institution || "Unknown"}</p>
    <p><b>Works:</b> ${meta.works_count || "?"}</p>
    <p><a href="${meta.url}" target="_blank">OpenAlex Profile</a></p>
  `;
}


//----------------------------------------------------------
// SHORTEST PATH
//----------------------------------------------------------
document.getElementById("path-button").onclick = async () => {
  const a = document.getElementById("path-start").value.trim();
  const b = document.getElementById("path-end").value.trim();

  if (!a || !b) {
    infoDiv.innerHTML = "Enter both author IDs.";
    return;
  }

  showLoader("Finding shortest path...");

  const url = `/api/shortest_path?author_a=${a}&author_b=${b}`;
  const data = await fetch(url).then(r => r.json());

  if (!data.path.length) {
    infoDiv.innerHTML = "No path found.";
    return;
  }

  highlightPath(data.path);
};


window.highlightPath = function(path) {
  if (!graphNodes || !graphEdges) {
    infoDiv.innerHTML = "Load a graph first.";
    return;
  }

  // Reset styles
  graphNodes.forEach(n =>
    graphNodes.update({
      id: n.id,
      color: "#60a5fa",
      size: 12
    })
  );

  graphEdges.forEach(e =>
    graphEdges.update({
      id: e.id,
      color: "#cbd5e1",
      width: 1
    })
  );

  // Highlight path nodes
  path.forEach(id =>
    graphNodes.update({
      id,
      color: "#f97316",
      size: 22
    })
  );

  // Highlight path edges
  for (let i = 0; i < path.length - 1; i++) {
    const a = path[i];
    const b = path[i + 1];

    const edge = graphEdges.get({
      filter: e =>
        (e.from === a && e.to === b) ||
        (e.from === b && e.to === a)
    })[0];

    if (edge) {
      graphEdges.update({
        id: edge.id,
        color: "#f97316",
        width: 6
      });
    }
  }

  infoDiv.innerHTML = `
    <b>Shortest path:</b><br>
    ${path.join(" → ")}
  `;
};
