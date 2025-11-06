"use strict";

const statusToClass = (status) => {
  if (!status) return "status-other";
  const value = String(status).toLowerCase();
  if (value === "completed" || value === "succeeded") return "status-completed";
  if (value === "running" || value === "in_progress") return "status-running";
  if (value === "failed" || value === "error") return "status-failed";
  if (value === "pending" || value === "blocked" || value === "queued") return "status-pending";
  return "status-other";
};

const escapeHtml = (value) => {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
};

const formatMultiline = (value) => {
  if (value === null || value === undefined) return "";
  const normalized = String(value).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const withRealBreaks = normalized.replace(/\\n/g, "\n");
  return escapeHtml(withRealBreaks).replace(/\n/g, "<br>");
};

document.addEventListener("DOMContentLoaded", () => {
  if (window.cytoscape && window.cytoscapeDagre) {
    cytoscape.use(cytoscapeDagre);
  }

  const rootDirectory = document.body.dataset.root || "";
  const sidebar = document.querySelector(".plan-list");
  const searchInput = document.querySelector(".plan-search");
  const planSummary = document.querySelector(".summary-panel");
  const nodeDetail = document.querySelector(".node-detail");
  const graphContainer = document.getElementById("graph");
  const graphHeaderCount = document.querySelector("[data-graph-count]");
  const emptyState = document.querySelector(".graph-container .empty-state");
  const planTitle = document.querySelector("[data-plan-title]");
  const planMeta = document.querySelector("[data-plan-meta]");
  const statusBadge = document.querySelector("[data-plan-status]");
  const planLinks = document.querySelector("[data-plan-links]");
  const rootPath = document.querySelector("[data-root-path]");

  let cyInstance = null;
  let plans = [];
  let filteredPlans = [];
  let activePlan = null;
  let nodeLookup = {};

  if (rootPath) {
    rootPath.textContent = rootDirectory;
  }

  const formatDate = (value) => {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
  };

  const renderPlans = () => {
    if (!sidebar) return;
    sidebar.innerHTML = "";
    if (!filteredPlans.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.innerHTML = "<p>No plans found. Run <code>agentflow \\\"your prompt\\\"</code> to create one.</p>";
      sidebar.appendChild(empty);
      return;
    }

    filteredPlans.forEach((plan) => {
      const card = document.createElement("div");
      const isActive = activePlan && activePlan.plan_id === plan.plan_id;
      card.className = "plan-card" + (isActive ? " active" : "");
      const statusLabel = escapeHtml(plan.status || "unknown");
      const title = escapeHtml(plan.name || plan.plan_id);
      const planId = escapeHtml(plan.plan_id);
      const created = escapeHtml(formatDate(plan.created_at));
      card.innerHTML = `
        <div class="status-pill ${statusToClass(plan.status)}">${statusLabel}</div>
        <h2>${title}</h2>
        <div class="meta">${planId}</div>
        <div class="meta">${created}</div>
      `;
      card.addEventListener("click", () => loadPlan(plan.plan_id));
      sidebar.appendChild(card);
    });
  };

  const renderPlanSummary = (detail) => {
    if (!planTitle || !planMeta || !statusBadge || !planLinks || !planSummary) return;
    planTitle.textContent = detail.name || detail.plan_id;
    planMeta.textContent = "Plan ID " + detail.plan_id + " | Created " + formatDate(detail.created_at) + " | Updated " + formatDate(detail.last_updated);
    statusBadge.textContent = detail.status || "unknown";
    statusBadge.className = "status-pill " + statusToClass(detail.status);
    const downloadHref = "/files/" + encodeURIComponent(detail.filename || "");
    planLinks.innerHTML = '<a href="' + downloadHref + '" target="_blank" rel="noopener">Download YAML</a>';

    planSummary.innerHTML = "";

    const statusCard = document.createElement("div");
    statusCard.className = "summary-card";
    const statusEntries = Object.entries(detail.status_counts || {});
    const statusText = statusEntries.length
      ? statusEntries.map(([status, count]) => "<strong>" + escapeHtml(count) + "</strong> " + escapeHtml(status)).join(" | ")
      : "No nodes";
    statusCard.innerHTML = "<h3>Status Breakdown</h3><p>" + statusText + "</p>";

    const metricsCard = document.createElement("div");
    metricsCard.className = "summary-card";
    const metrics = detail.metrics || {};
    const metricEntries = Object.entries(metrics);
    let metricsContent = "<p>No metrics reported.</p>";
    if (metricEntries.length) {
      const lines = metricEntries
        .map(([key, value]) => {
          const printable = typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
          return key + ": " + printable;
        })
        .join("\\n");
      metricsContent = "<pre>" + escapeHtml(lines) + "</pre>";
    }
    metricsCard.innerHTML = "<h3>Metrics</h3>" + metricsContent;

    const tagsCard = document.createElement("div");
    tagsCard.className = "summary-card";
    const tags = detail.tags || [];
    tagsCard.innerHTML = "<h3>Tags</h3><ul>" + (tags.length ? tags.map((tag) => "<li>" + escapeHtml(tag) + "</li>").join("") : "<li>None</li>") + "</ul>";

    planSummary.appendChild(statusCard);
    planSummary.appendChild(metricsCard);
    planSummary.appendChild(tagsCard);
  };

  const renderNodeDetail = (nodeId) => {
    if (!nodeDetail) return;
    const node = nodeId ? nodeLookup[nodeId] : null;
    if (!node) {
      nodeDetail.innerHTML = "<h2>Select a node</h2><p>Choose a node in the graph to inspect its details.</p>";
      return;
    }

    const statusClass = statusToClass(node.status);
    const statusLabel = escapeHtml(node.status || "unknown");
    const title = escapeHtml(node.display_title || node.summary || node.id);
    const nodeKey = escapeHtml(node.id);
    const roleLabel = escapeHtml(node.role_label || node.role || "Node");
    const parentId = node.parent_id ? escapeHtml(node.parent_id) : "None";
    const dependsOn = (node.depends_on || []).length
      ? node.depends_on.map((dep) => escapeHtml(dep)).join(", ")
      : "None";

    nodeDetail.innerHTML = `
      <header>
        <div class="status-pill ${statusClass}">${statusLabel}</div>
        <div>
          <h2>${title}</h2>
          <p class="meta-line"><strong>Role:</strong> ${roleLabel} &#8226; <strong>Graph ID:</strong> ${nodeKey}</p>
          <p class="meta-line"><strong>Parent node:</strong> ${parentId} &#8226; <strong>Depends on:</strong> ${dependsOn}</p>
        </div>
      </header>
    `;

    const appendPre = (label, text) => {
      if (text === null || text === undefined || text === "") {
        return;
      }
      nodeDetail.insertAdjacentHTML("beforeend", "<h3>" + escapeHtml(label) + "</h3><pre>" + escapeHtml(text) + "</pre>");
    };

    const appendJson = (label, data) => {
      if (!data || (typeof data === "object" && Object.keys(data).length === 0 && !Array.isArray(data))) {
        return;
      }
      appendPre(label, JSON.stringify(data, null, 2));
    };

    if (node.role === "group") {
      const summary = node.summary ? "<p><strong>Summary:</strong><br>" + escapeHtml(node.summary) + "</p>" : "";
      appendJson("Inputs", node.inputs || {});
      appendJson("Outputs", node.outputs || {});
      appendJson("Artifacts", node.artifacts || []);
      appendJson("Metrics", node.metrics || {});
      appendJson("Timeline", node.timeline || {});
      appendJson("History", node.history || []);
      nodeDetail.insertAdjacentHTML("beforeend", summary || "<p>No additional details recorded for this node group.</p>");
      return;
    }

    if (node.role === "prompt") {
      appendPre("Prompt", node.prompt_text || "No prompt recorded.");
      appendJson("Inputs", node.inputs || {});
    } else if (node.role === "response") {
      appendPre("Response", node.response_text || "No response captured.");

      const evaluation = node.evaluation || {};
      const score = evaluation.score;
      const justification = evaluation.justification;
      const rawMessage = evaluation.raw_message;
      const cssClass = evaluation.css_class || "score-unknown";

      if (score != null || justification || rawMessage) {
        const scoreLabel = Number.isFinite(score) ? score.toFixed(2) : "--";
        const justificationBlock = justification ? `<p><strong>Justification:</strong><br>${formatMultiline(justification)}</p>` : "";
        const rawBlock = rawMessage ? `<p><strong>Raw:</strong><br>${formatMultiline(rawMessage)}</p>` : "";
        nodeDetail.insertAdjacentHTML(
          "beforeend",
          `
          <div class="evaluation-card ${cssClass}">
            <div class="evaluation-score">${scoreLabel}</div>
            <h4>Evaluation</h4>
            ${justificationBlock}
            ${rawBlock}
          </div>
          `
        );
      }

      appendJson("Outputs", node.outputs || {});
      appendJson("Artifacts", node.artifacts || []);
      appendJson("Metrics", node.metrics || {});
      appendJson("Timeline", node.timeline || {});
      appendJson("History", node.history || []);
    } else if (node.role === "evaluation") {
      const evaluation = node.evaluation || {};
      const cssClass = evaluation.css_class || "score-unknown";
      const score = evaluation.score;
      const justification = evaluation.justification;
      const rawMessage = evaluation.raw_message;
      const scoreLabel = Number.isFinite(score) ? score.toFixed(2) : "--";
      const justificationBlock = justification
        ? `<p><strong>Justification:</strong><br>${formatMultiline(justification)}</p>`
        : "<p>No justification provided.</p>";
      const rawBlock = rawMessage ? `<p><strong>Raw message:</strong><br>${formatMultiline(rawMessage)}</p>` : "";
      nodeDetail.insertAdjacentHTML(
        "beforeend",
        `
        <div class="evaluation-card ${cssClass}">
          <div class="evaluation-score">${scoreLabel}</div>
          <h4>Self-Evaluation</h4>
          ${justificationBlock}
          ${rawBlock}
        </div>
        `
      );
    } else {
      appendJson("Inputs", node.inputs || {});
      appendJson("Outputs", node.outputs || {});
    }
  };

  const configureGraph = (elements) => {
    if (!graphContainer || !window.cytoscape) return;
    if (cyInstance) {
      cyInstance.destroy();
    }
    cyInstance = cytoscape({
      container: graphContainer,
      elements: elements,
      userZoomingEnabled: true,
      autoungrabify: true,
      boxSelectionEnabled: false,
      layout: { name: "grid" },
      style: [
        {
          selector: "node:parent",
          style: {
            "background-color": "rgba(15, 23, 42, 0.35)",
            "border-width": 2,
            "border-color": "#475569",
            "padding": "18px",
            "text-halign": "left",
            "text-valign": "top",
            "font-size": "13px",
            "font-weight": 600,
            color: "#cbd5f5",
            "text-wrap": "wrap",
            "text-max-width": "240px"
          }
        },
        {
          selector: ".task-group.status-completed",
          style: {
            "border-color": "rgba(34, 197, 94, 0.65)"
          }
        },
        {
          selector: ".task-group.status-running",
          style: {
            "border-color": "rgba(56, 189, 248, 0.65)"
          }
        },
        {
          selector: ".task-group.status-failed",
          style: {
            "border-color": "rgba(239, 68, 68, 0.65)"
          }
        },
        {
          selector: ".task-group.status-pending",
          style: {
            "border-color": "rgba(245, 158, 11, 0.65)"
          }
        },
        {
          selector: ".task-group.status-other",
          style: {
            "border-color": "rgba(148, 163, 184, 0.65)"
          }
        },
        {
          selector: "node",
            style: {
              shape: "roundrectangle",
              "background-color": "#1e293b",
              "background-opacity": 0.95,
              "border-width": 3,
              "border-color": "#475569",
              "border-opacity": 0.95,
              color: "#e2e8f0",
              label: "data(label)",
              "font-size": "12px",
              "font-weight": 600,
              "text-wrap": "wrap",
              "text-max-width": "220px",
              "text-halign": "center",
              "text-valign": "center",
              "line-height": 1.3,
              width: 240,
              height: 130,
              padding: "12px",
              "overlay-opacity": 0
            }
        },
        {
          selector: ".node-prompt",
          style: {
            "border-style": "dashed",
            "border-color": "#38bdf8",
            "background-color": "rgba(56, 189, 248, 0.12)"
          }
        },
        {
          selector: ".node-response",
          style: {
            "border-style": "solid",
            "border-color": "#94a3b8",
            "background-color": "rgba(148, 163, 184, 0.16)"
          }
        },
        {
          selector: ".node-evaluation",
          style: {
            "border-style": "dotted",
            "border-color": "#a855f7",
            "background-color": "rgba(168, 85, 247, 0.18)"
          }
        },
        {
          selector: ".node-evaluation.score-high",
          style: {
            "border-color": "#22c55e",
            "background-color": "rgba(34, 197, 94, 0.24)"
          }
        },
        {
          selector: ".node-evaluation.score-medium",
          style: {
            "border-color": "#facc15",
            "background-color": "rgba(250, 204, 21, 0.24)"
          }
        },
        {
          selector: ".node-evaluation.score-low",
          style: {
            "border-color": "#ef4444",
            "background-color": "rgba(239, 68, 68, 0.24)"
          }
        },
        {
          selector: ".node-evaluation.score-unknown",
          style: {
            "border-color": "#a855f7",
            "background-color": "rgba(168, 85, 247, 0.18)"
          }
        },
        {
          selector: ".node-response.score-high",
          style: {
            "border-color": "#22c55e",
            "background-color": "rgba(34, 197, 94, 0.24)"
          }
        },
        {
          selector: ".node-response.score-medium",
          style: {
            "border-color": "#facc15",
            "background-color": "rgba(250, 204, 21, 0.24)"
          }
        },
        {
          selector: ".node-response.score-low",
          style: {
            "border-color": "#ef4444",
            "background-color": "rgba(239, 68, 68, 0.24)"
          }
        },
        {
          selector: ".node-response.score-unknown",
          style: {
            "border-color": "#94a3b8",
            "background-color": "rgba(148, 163, 184, 0.2)"
          }
        },
        {
          selector: "edge",
          style: {
            width: 3,
            "curve-style": "bezier",
            "control-point-step-size": 60,
            "target-arrow-shape": "vee",
            "target-arrow-color": "#64748b",
            "line-color": "#475569",
            "arrow-scale": 1.3,
            "opacity": 0.9
          }
        },
        {
          selector: "node:selected",
          style: {
            "border-width": 5,
            "border-color": "#f8fafc"
          }
        }
      ]
    });

    const layout = cyInstance.layout({
      name: "dagre",
      fit: true,
      padding: 50,
      rankDir: "LR",
      nodeSep: 80,
      rankSep: 120,
      animate: true,
      animationDuration: 300
    });
    layout.run();
    cyInstance.fit();
    cyInstance.minZoom(0.35);
    cyInstance.maxZoom(2.5);

    cyInstance.on("tap", "node", (evt) => {
      const nodeId = evt.target.id();
      cyInstance.animate({
        fit: { eles: evt.target.isParent() ? evt.target.descendants() : evt.target, padding: 140 },
        duration: 240
      });
      renderNodeDetail(nodeId);
    });

    cyInstance.on("tap", (evt) => {
      if (evt.target === cyInstance) {
        renderNodeDetail(null);
        cyInstance.animate({
          fit: { eles: cyInstance.elements(), padding: 100 },
          duration: 200
        });
      }
    });

    window.addEventListener("resize", () => {
      if (!cyInstance) return;
      cyInstance.resize();
      cyInstance.fit(undefined, 100);
    });
  };

  const loadPlan = async (planId) => {
    if (!planId) return;
    try {
      const response = await fetch("/api/plans/" + encodeURIComponent(planId));
      if (!response.ok) throw new Error("Unable to load plan " + planId);
      const detail = await response.json();
      activePlan = detail;
      nodeLookup = detail.nodes_index || {};
      renderPlanSummary(detail);
      if (graphHeaderCount) {
        const stats = detail.graph_stats || {};
        const total = stats.total || (detail.nodes_index ? Object.keys(detail.nodes_index).length : 0);
        const prompts = stats.prompts != null ? stats.prompts : Math.round(total / 2);
        const responses = stats.responses != null ? stats.responses : Math.max(total - prompts, 0);
        const evaluations = stats.evaluations != null ? stats.evaluations : Math.max(total - prompts - responses, 0);
        const parts = [`${total} node(s)`, `${prompts} prompt(s)`, `${responses} response(s)`];
        if (evaluations) {
          parts.push(`${evaluations} evaluation(s)`);
        }
        graphHeaderCount.textContent = parts.join(" \u2022 ");
      }
      configureGraph(detail.graph_elements || []);
      renderNodeDetail(null);
      renderPlans();
      if (emptyState) {
        emptyState.style.display = "none";
      }
    } catch (error) {
      console.error(error);
    }
  };

  const loadPlans = async () => {
    if (!sidebar) return;
    try {
      const response = await fetch("/api/plans");
      if (!response.ok) throw new Error("Unable to fetch plans");
      plans = await response.json();
      filteredPlans = plans.slice();
      renderPlans();
      if (filteredPlans.length) {
        loadPlan(filteredPlans[0].plan_id);
      }
    } catch (error) {
      console.error(error);
      sidebar.innerHTML = "<div class='empty-state'><p>Failed to load plans. Check server logs.</p></div>";
    }
  };

  if (searchInput) {
    searchInput.addEventListener("input", (event) => {
      const query = String(event.target.value || "").toLowerCase();
      filteredPlans = plans.filter((plan) => {
        const haystack = [plan.plan_id, plan.name, plan.status].join(" ").toLowerCase();
        return haystack.includes(query);
      });
      renderPlans();
    });
  }

  loadPlans();
});




