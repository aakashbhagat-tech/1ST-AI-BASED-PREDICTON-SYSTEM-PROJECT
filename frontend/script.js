// Initialize Map
const map = L.map("map", { zoomControl: false }).setView([37.7749, -122.4194], 12);

L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
  attribution: "",
}).addTo(map);

// Chart Initialization
let trendChart;
const ctx = document.getElementById("trendChart").getContext("2d");
const maxChartPoints = 20;
let avgHistory = {
  demand: [],
  gnn_influence: [],
  graph_score: [],
};
let chartTimestamps = [];
const zoneSeriesHistory = {};
let latestZones = [];

Chart.defaults.color = "#8a8a9e";
Chart.defaults.font.family = "'Inter', sans-serif";

function initChart() {
  trendChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Real-Time Demand",
          data: [],
          borderColor: "#00ffcc",
          backgroundColor: "rgba(0, 255, 204, 0.1)",
          borderWidth: 3,
          tension: 0.4,
          fill: true,
          pointBackgroundColor: "#00ffcc",
          pointBorderColor: "#fff",
          pointRadius: 4,
          pointHoverRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true },
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: "rgba(255,255,255,0.05)" },
        },
        x: {
          grid: { color: "rgba(255,255,255,0.05)" },
        },
      },
    },
  });
}

initChart();

// DOM Elements
const generateBtn = document.getElementById("generate-btn");
const loadingOverlay = document.getElementById("loading-overlay");
const kpiDemand = document.getElementById("kpi-demand");
const kpiHotspots = document.getElementById("kpi-hotspots");
const kpiFleet = document.getElementById("kpi-fleet");
const kpiConfidence = document.getElementById("kpi-confidence");
const tbody = document.querySelector("#hotspots-table tbody");
const citySelect = document.getElementById("city-select");
const horizonSelect = document.getElementById("horizon-select");
const intervalSelect = document.getElementById("interval-select");
const zoneSelect = document.getElementById("zone-select");
const chartMetricSelect = document.getElementById("chart-metric-select");
const gnnOverlayToggle = document.getElementById("gnn-overlay-toggle");
const gnnStatus = document.getElementById("gnn-status");

// City center coordinates (for map centering)
const cityCenters = {
  SF: [37.7749, -122.4194],
  NY: [40.7128, -74.006],
  LDN: [51.5074, -0.1278],
};

// Map UI values to backend values
const cityNameMap = {
  SF: "San Francisco",
  NY: "New York",
  LDN: "London",
};

let currentMarkers = [];
let currentGraphEdges = [];
let websocket = null;
let isStreaming = false;
let connectionRetryTimer = null;
let mockIntervalTimer = null;
let usingLocalMock = false;
let manualStopRequested = false;
const localMockState = {};
let latestCityCenter = cityCenters.SF;

function setLoadingState(isVisible, message = "Connecting...") {
  if (!loadingOverlay) return;
  const textNode = loadingOverlay.querySelector("h2");
  if (textNode) {
    textNode.innerText = message;
  }
  if (isVisible) {
    loadingOverlay.classList.remove("hidden");
  } else {
    loadingOverlay.classList.add("hidden");
  }
}

function resolveApiHost() {
  const params = new URLSearchParams(window.location.search);
  const apiHostFromQuery = params.get("api");
  if (apiHostFromQuery) {
    return apiHostFromQuery;
  }

  const host = window.location.hostname;
  const port = window.location.port;
  const isLocalHost = host === "localhost" || host === "127.0.0.1";

  if (isLocalHost) {
    return "127.0.0.1:8000";
  }

  return `${host}${port ? `:${port}` : ""}`;
}

function getOrBuildLocalMockGraph(cityCode) {
  if (localMockState[cityCode]) {
    return localMockState[cityCode];
  }

  const center = cityCenters[cityCode];
  const zones = [];
  for (let i = 1; i <= 20; i++) {
    const zoneId = `Z${String(i).padStart(2, "0")}`;
    const angle = (i / 20) * Math.PI * 2;
    const radius = 0.015 + (i % 5) * 0.006;
    const lat = center[0] + Math.cos(angle) * radius;
    const lon = center[1] + Math.sin(angle) * radius;
    const baseDemand = 8 + ((i * 13) % 37);
    zones.push({ zone_id: zoneId, lat, lon, base_demand: baseDemand });
  }

  const neighbors = {};
  zones.forEach((z, i) => {
    const scored = zones
      .map((o, j) => {
        if (i === j) return null;
        const dLat = o.lat - z.lat;
        const dLon = o.lon - z.lon;
        const dist = Math.sqrt(dLat * dLat + dLon * dLon);
        return { idx: j, dist };
      })
      .filter(Boolean)
      .sort((a, b) => a.dist - b.dist)
      .slice(0, 4);
    neighbors[z.zone_id] = scored;
  });

  localMockState[cityCode] = { zones, neighbors };
  return localMockState[cityCode];
}

function buildLocalMockMessage(cityCode, horizon, interval) {
  const { zones, neighbors } = getOrBuildLocalMockGraph(cityCode);
  const now = new Date();
  const forecastFor = new Date(now.getTime() + horizon * 60 * 1000);
  const hourFactor = Math.sin(((forecastFor.getHours() - 6) * Math.PI) / 12) + 1.2;
  const tick = Math.floor(now.getTime() / 15000);

  const localSignal = zones.map((z, idx) => {
    const wave = 1 + 0.2 * Math.sin(now.getTime() / 25000 + idx);
    const pulse = (tick + idx) % 11 === 0 ? 1.4 : 1.0;
    return Math.max(0, z.base_demand * hourFactor * 0.62 * wave * pulse);
  });

  const zonesData = zones.map((z, idx) => {
    const n = neighbors[z.zone_id];
    let neighborMix = 0;
    let weightSum = 0;
    n.forEach((item) => {
      const w = 1 / Math.max(item.dist, 1e-5);
      neighborMix += localSignal[item.idx] * w;
      weightSum += w;
    });
    const neighborInfluence = weightSum > 0 ? neighborMix / weightSum : localSignal[idx];
    const predicted = Math.max(0, Math.round(0.68 * localSignal[idx] + 0.32 * neighborInfluence));
    const fleet = Math.max(1, Math.round(predicted / 1.5));
    const level = predicted > 25 ? "High" : predicted > 12 ? "Medium" : "Low";
    const conf = Math.max(0.62, Math.min(0.93, 0.84 - Math.abs(predicted - neighborInfluence) / 180));
    const graphScore = Math.max(
      0,
      Math.min(1, 0.6 * (neighborInfluence / Math.max(predicted, 1)) + 0.4 * conf),
    );

    return {
      zone_id: z.zone_id,
      lat: z.lat,
      lon: z.lon,
      predicted_demand: predicted,
      demand_level: level,
      recommended_vehicles: fleet,
      confidence: Number(conf.toFixed(3)),
      model_name: "GNN+LSTM+Realtime",
      gnn_neighbor_influence: Number(neighborInfluence.toFixed(2)),
      gnn_graph_score: Number(graphScore.toFixed(3)),
      gnn_neighbors: n.map((x) => zones[x.idx].zone_id).join(","),
      realtime_adjusted: true,
      data_last_updated: now.toISOString(),
      forecast_for: forecastFor.toISOString(),
      source: "frontend_local_mock",
    };
  });

  zonesData.sort((a, b) => b.predicted_demand - a.predicted_demand);
  const totalDemand = zonesData.reduce((s, z) => s + z.predicted_demand, 0);
  const hotspots = zonesData.filter((z) => z.demand_level === "High").length;
  const fleet = zonesData.reduce((s, z) => s + z.recommended_vehicles, 0);
  const confidence = zonesData.reduce((s, z) => s + z.confidence, 0) / zonesData.length;

  return {
    timestamp: now.toISOString(),
    zones: zonesData,
    kpis: {
      total_demand: totalDemand,
      hotspots,
      fleet,
      confidence: Number((confidence * 100).toFixed(1)),
    },
    update_interval: interval,
    update_interval_unit: "seconds",
    mode: "frontend_local_mock",
    model_name: "GNN+LSTM+Realtime",
    realtime_adjusted_zones: zonesData.length,
  };
}

function clearMapMarkers() {
  currentMarkers.forEach((marker) => map.removeLayer(marker));
  currentMarkers = [];
}

function clearGraphOverlay() {
  currentGraphEdges.forEach((edge) => map.removeLayer(edge));
  currentGraphEdges = [];
}

function computeNearestNeighbors(zones, k = 3) {
  const neighborMap = {};
  zones.forEach((a, i) => {
    const scored = zones
      .map((b, j) => {
        if (i === j) return null;
        const dx = (a.lat || 0) - (b.lat || 0);
        const dy = (a.lon || 0) - (b.lon || 0);
        return { id: b.zone_id, dist: Math.sqrt(dx * dx + dy * dy) };
      })
      .filter(Boolean)
      .sort((x, y) => x.dist - y.dist)
      .slice(0, k)
      .map((x) => x.id);
    neighborMap[a.zone_id] = scored;
  });
  return neighborMap;
}

function drawGnnOverlay(zones) {
  clearGraphOverlay();
  const overlayOn = !gnnOverlayToggle || gnnOverlayToggle.value === "on";
  if (!overlayOn || !zones || zones.length === 0) {
    if (gnnStatus) {
      gnnStatus.innerText = overlayOn ? "No graph data yet" : "Overlay disabled";
    }
    return;
  }

  const zoneMap = {};
  zones.forEach((z) => {
    zoneMap[z.zone_id] = z;
  });

  const inferred = computeNearestNeighbors(zones, 3);
  const drawn = new Set();
  let edgeCount = 0;

  zones.forEach((z) => {
    const raw = typeof z.gnn_neighbors === "string" ? z.gnn_neighbors : "";
    const ids = raw
      .split(",")
      .map((x) => x.trim())
      .filter((x) => x.length > 0);
    const neighbors = ids.length > 0 ? ids : inferred[z.zone_id] || [];

    neighbors.forEach((nid) => {
      const n = zoneMap[nid];
      if (!n) return;
      const key = [z.zone_id, nid].sort().join("|");
      if (drawn.has(key)) return;
      drawn.add(key);

      const influence = Number(z.gnn_neighbor_influence || 0);
      const weightOpacity = Math.max(0.18, Math.min(0.65, 0.2 + influence / 120));
      const polyline = L.polyline(
        [
          [z.lat || latestCityCenter[0], z.lon || latestCityCenter[1]],
          [n.lat || latestCityCenter[0], n.lon || latestCityCenter[1]],
        ],
        {
          color: "#f6a623",
          weight: 2,
          opacity: weightOpacity,
          dashArray: "4,6",
        },
      ).addTo(map);
      currentGraphEdges.push(polyline);
      edgeCount += 1;
    });
  });

  if (gnnStatus) {
    gnnStatus.innerText = `Loaded: ${zones.length} nodes / ${edgeCount} edges`;
  }
}

function syncZoneSelector(zones) {
  if (!zoneSelect) return;

  const current = zoneSelect.value || "All";
  const zoneIds = zones.map((z) => z.zone_id);
  const optionValues = Array.from(zoneSelect.options).map((o) => o.value);
  const expected = ["All", ...zoneIds];
  const isSame =
    expected.length === optionValues.length &&
    expected.every((value, i) => value === optionValues[i]);

  if (!isSame) {
    zoneSelect.innerHTML = "";
    expected.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value === "All" ? "City Average" : value;
      zoneSelect.appendChild(option);
    });
  }

  if (expected.includes(current)) {
    zoneSelect.value = current;
  }
}

function refreshTrendChart() {
  if (!trendChart) return;

  const selectedZone = zoneSelect ? zoneSelect.value : "All";
  const metric = chartMetricSelect ? chartMetricSelect.value : "demand";
  const metricLabel =
    metric === "gnn_influence"
      ? "GNN Influence"
      : metric === "graph_score"
        ? "Graph Score"
        : "Demand";
  const series =
    selectedZone === "All"
      ? avgHistory[metric] || []
      : (zoneSeriesHistory[selectedZone] && zoneSeriesHistory[selectedZone][metric]) || [];

  trendChart.data.labels = [...chartTimestamps];
  trendChart.data.datasets[0].label =
    selectedZone === "All"
      ? `Real-Time ${metricLabel} (City Average)`
      : `Real-Time ${metricLabel} (${selectedZone})`;
  trendChart.data.datasets[0].data = [...series];
  trendChart.update("none");
}

function resetTrendHistory() {
  avgHistory = {
    demand: [],
    gnn_influence: [],
    graph_score: [],
  };
  chartTimestamps = [];
  Object.keys(zoneSeriesHistory).forEach((zoneId) => {
    delete zoneSeriesHistory[zoneId];
  });
  latestZones = [];
  if (zoneSelect) {
    zoneSelect.innerHTML = '<option value="All">City Average</option>';
  }
  refreshTrendChart();
}

function addStreamSnapshot(zones, timestamp) {
  latestZones = zones;
  syncZoneSelector(zones);

  const snapshotTime = new Date(timestamp || Date.now());

  const avgDemand =
    zones.length > 0
      ? Math.round(zones.reduce((sum, z) => sum + Number(z.predicted_demand || 0), 0) / zones.length)
      : 0;
  const avgInfluence =
    zones.length > 0
      ? zones.reduce((sum, z) => sum + Number(z.gnn_neighbor_influence || 0), 0) / zones.length
      : 0;
  const avgGraphScore =
    zones.length > 0 ? zones.reduce((sum, z) => sum + Number(z.gnn_graph_score || 0), 0) / zones.length : 0;

  // Bootstrap a short history on first packet so the graph shows a trend line,
  // not a single isolated point.
  if (chartTimestamps.length === 0) {
    const bootstrapPoints = 8;
    for (let i = bootstrapPoints; i >= 1; i--) {
      const t = new Date(snapshotTime.getTime() - i * 5000);
      const factor = 1 - i * 0.02;
      chartTimestamps.push(t.toLocaleTimeString());
      avgHistory.demand.push(Math.max(0, Math.round(avgDemand * factor)));
      avgHistory.gnn_influence.push(Number(Math.max(0, avgInfluence * factor).toFixed(3)));
      avgHistory.graph_score.push(Number(Math.max(0, avgGraphScore * factor).toFixed(3)));
      zones.forEach((z) => {
        const zoneId = z.zone_id;
        if (!zoneSeriesHistory[zoneId]) {
          zoneSeriesHistory[zoneId] = {
            demand: [],
            gnn_influence: [],
            graph_score: [],
          };
        }
        zoneSeriesHistory[zoneId].demand.push(Math.max(0, Math.round(Number(z.predicted_demand || 0) * factor)));
        zoneSeriesHistory[zoneId].gnn_influence.push(
          Number(Math.max(0, Number(z.gnn_neighbor_influence || 0) * factor).toFixed(3)),
        );
        zoneSeriesHistory[zoneId].graph_score.push(
          Number(Math.max(0, Number(z.gnn_graph_score || 0) * factor).toFixed(3)),
        );
      });
    }
  }

  chartTimestamps.push(snapshotTime.toLocaleTimeString());
  if (chartTimestamps.length > maxChartPoints) {
    chartTimestamps.shift();
  }

  avgHistory.demand.push(avgDemand);
  avgHistory.gnn_influence.push(Number(avgInfluence.toFixed(3)));
  avgHistory.graph_score.push(Number(avgGraphScore.toFixed(3)));

  Object.keys(avgHistory).forEach((key) => {
    if (avgHistory[key].length > maxChartPoints) {
      avgHistory[key].shift();
    }
  });

  zones.forEach((z) => {
    const zoneId = z.zone_id;
    if (!zoneSeriesHistory[zoneId]) {
      zoneSeriesHistory[zoneId] = {
        demand: [],
        gnn_influence: [],
        graph_score: [],
      };
    }
    zoneSeriesHistory[zoneId].demand.push(Number(z.predicted_demand || 0));
    zoneSeriesHistory[zoneId].gnn_influence.push(Number(Number(z.gnn_neighbor_influence || 0).toFixed(3)));
    zoneSeriesHistory[zoneId].graph_score.push(Number(Number(z.gnn_graph_score || 0).toFixed(3)));

    Object.keys(zoneSeriesHistory[zoneId]).forEach((key) => {
      if (zoneSeriesHistory[zoneId][key].length > maxChartPoints) {
        zoneSeriesHistory[zoneId][key].shift();
      }
    });
  });

  refreshTrendChart();
}

function setChartStyleByMetric() {
  if (!trendChart) return;
  const metric = chartMetricSelect ? chartMetricSelect.value : "demand";
  if (metric === "gnn_influence") {
    trendChart.data.datasets[0].borderColor = "#f6a623";
    trendChart.data.datasets[0].backgroundColor = "rgba(246, 166, 35, 0.15)";
    trendChart.data.datasets[0].pointBackgroundColor = "#f6a623";
  } else if (metric === "graph_score") {
    trendChart.data.datasets[0].borderColor = "#8f7bff";
    trendChart.data.datasets[0].backgroundColor = "rgba(143, 123, 255, 0.15)";
    trendChart.data.datasets[0].pointBackgroundColor = "#8f7bff";
  } else {
    trendChart.data.datasets[0].borderColor = "#00ffcc";
    trendChart.data.datasets[0].backgroundColor = "rgba(0, 255, 204, 0.1)";
    trendChart.data.datasets[0].pointBackgroundColor = "#00ffcc";
  }
  trendChart.update("none");
}

function animateKPI(element, newValue) {
  const oldValue = parseInt(String(element.innerText).replace(/,/g, ""), 10) || 0;
  const diff = newValue - oldValue;
  const steps = 40;
  const stepValue = diff / steps;
  let current = oldValue;
  let stepCount = 0;

  const interval = setInterval(() => {
    stepCount += 1;
    current += stepValue;
    if (
      stepCount >= steps ||
      (stepValue > 0 && current >= newValue) ||
      (stepValue < 0 && current <= newValue)
    ) {
      element.innerText = Number(newValue).toLocaleString();
      clearInterval(interval);
    } else {
      element.innerText = Math.round(current).toLocaleString();
    }
  }, 100);
}

function stopLocalMockStream() {
  if (mockIntervalTimer) {
    clearInterval(mockIntervalTimer);
    mockIntervalTimer = null;
  }
  usingLocalMock = false;
}

function startLocalMockStream(cityCode, horizon, interval, cityCenter) {
  stopLocalMockStream();
  usingLocalMock = true;
  isStreaming = true;
  generateBtn.innerText = "Stop Stream";
  setLoadingState(false);

  const push = () => {
    const message = buildLocalMockMessage(cityCode, horizon, interval);
    updateDashboardFromStream(message, cityCenter);
  };

  push();
  mockIntervalTimer = setInterval(push, Math.max(1, interval) * 1000);
}

function startRealtimeStream() {
  const cityCode = citySelect.value;
  const cityName = cityNameMap[cityCode];
  const center = cityCenters[cityCode];
  const horizon = parseInt(horizonSelect.value, 10);
  const interval = parseInt(intervalSelect.value, 10);
  manualStopRequested = false;
  resetTrendHistory();
  latestCityCenter = center;

  map.flyTo(center, 12, { duration: 1.2 });

  if (websocket) {
    websocket.close();
  }
  if (connectionRetryTimer) {
    clearTimeout(connectionRetryTimer);
    connectionRetryTimer = null;
  }
  stopLocalMockStream();

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsHost = resolveApiHost();
  const wsUrl = `${protocol}//${wsHost}/ws/stream?city=${cityName}&horizon=${horizon}&interval=${interval}`;

  setLoadingState(true, "Connecting to live stream...");
  websocket = new WebSocket(wsUrl);

  websocket.onopen = () => {
    isStreaming = true;
    setLoadingState(false);
    generateBtn.innerText = "Stop Stream";
  };

  websocket.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data);
      updateDashboardFromStream(message, center);
    } catch (err) {
      console.error("WebSocket payload parse error:", err);
    }
  };

  websocket.onerror = () => {
    setLoadingState(true, "API unavailable. Switching to local mock real-time stream...");
    connectionRetryTimer = setTimeout(() => {
      setLoadingState(false);
    }, 1200);
    startLocalMockStream(cityCode, horizon, interval, center);
  };

  websocket.onclose = () => {
    if (manualStopRequested) {
      manualStopRequested = false;
      isStreaming = false;
      generateBtn.innerText = "Generate Forecast";
      return;
    }
    if (!usingLocalMock) {
      startLocalMockStream(cityCode, horizon, interval, center);
    }
  };
}

function stopRealtimeStream() {
  manualStopRequested = true;
  if (websocket) {
    websocket.close();
    websocket = null;
  }
  stopLocalMockStream();
  if (connectionRetryTimer) {
    clearTimeout(connectionRetryTimer);
    connectionRetryTimer = null;
  }
  isStreaming = false;
  generateBtn.innerText = "Generate Forecast";
  setLoadingState(false);
  clearGraphOverlay();
  if (gnnStatus) {
    gnnStatus.innerText = "Stopped";
  }
}

function updateDashboardFromStream(message, cityCenter) {
  const zones = message.zones || [];
  const kpis = message.kpis || { total_demand: 0, hotspots: 0, fleet: 0, confidence: 70 };
  const interval = message.update_interval || 30;
  const intervalUnit = message.update_interval_unit || "seconds";
  const adjustedZones = message.realtime_adjusted_zones || 0;

  const intervalStatusElement = document.getElementById("interval-status");
  if (intervalStatusElement) {
    const modeLabel = usingLocalMock ? "Local Mock" : "API Stream";
    intervalStatusElement.innerText = `Mode: ${modeLabel} | Every ${interval} ${intervalUnit === "seconds" ? "Seconds" : "Minutes"} | Realtime adjusted zones: ${adjustedZones}`;
  }

  clearMapMarkers();
  tbody.innerHTML = "";

  zones.forEach((z, idx) => {
    const fleet = z.recommended_vehicles;
    const level = String(z.demand_level || "Low").toLowerCase();
    const updatedAt = z.data_last_updated || message.timestamp;
    const sourceTag = z.source || "mock_realtime";

    const gnnInfluence = Number(z.gnn_neighbor_influence || (z.predicted_demand || 0) * 0.55);
    const gnnGraphScore = Number(z.gnn_graph_score || Math.min(1, 0.4 + gnnInfluence / 120));
    const color = level === "high" ? "#ff4757" : level === "medium" ? "#ffa502" : "#2ed573";
    const opacity = level === "high" ? 0.6 : 0.4;

    const circle = L.circle([z.lat || cityCenter[0], z.lon || cityCenter[1]], {
      color,
      fillColor: color,
      fillOpacity: opacity,
      weight: 2,
      radius: Math.max((z.predicted_demand || 0) * 12, 120),
    }).addTo(map).bindPopup(`
      <div style="text-align:center;font-family:'Inter'">
        <b style="color:#333">${z.zone_id}</b>
        <div style="margin-top:5px;color:#555">
          Real-Time Demand: <strong style="color:${color}">${z.predicted_demand}</strong>
        </div>
        <div style="color:#555">
          Required Fleet: <strong>${fleet}</strong>
        </div>
        <div style="color:#555">
          Demand Level: <strong>${z.demand_level}</strong>
        </div>
        <div style="color:#555">
          GNN Influence: <strong>${gnnInfluence.toFixed(2)}</strong>
        </div>
        <div style="color:#555">
          Graph Score: <strong>${gnnGraphScore.toFixed(3)}</strong>
        </div>
        <div style="color:#999; font-size:0.8rem; margin-top:5px">
          Updated: ${updatedAt}
        </div>
        <div style="color:#999; font-size:0.75rem;">
          Source: ${sourceTag}
        </div>
      </div>
    `);
    currentMarkers.push(circle);

    if (idx < 6) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${z.zone_id}</td>
        <td><span class="badge ${level}">${z.predicted_demand} trips</span></td>
        <td>${fleet}</td>
        <td>${gnnInfluence.toFixed(2)}</td>
      `;
      tbody.appendChild(tr);
    }
  });

  drawGnnOverlay(zones);

  animateKPI(kpiDemand, kpis.total_demand || 0);
  animateKPI(kpiHotspots, kpis.hotspots || 0);
  animateKPI(kpiFleet, kpis.fleet || 0);
  if (kpiConfidence) {
    kpiConfidence.innerText = `${Number(kpis.confidence || 70).toFixed(1)}%`;
  }

  addStreamSnapshot(zones, message.timestamp);
}

generateBtn.addEventListener("click", () => {
  if (isStreaming) {
    stopRealtimeStream();
  } else {
    startRealtimeStream();
  }
});

citySelect.addEventListener("change", () => {
  if (isStreaming) {
    startRealtimeStream();
  }
});
horizonSelect.addEventListener("change", () => {
  if (isStreaming) {
    startRealtimeStream();
  }
});
intervalSelect.addEventListener("change", () => {
  if (isStreaming) {
    startRealtimeStream();
  }
});

if (zoneSelect) {
  zoneSelect.addEventListener("change", () => {
    refreshTrendChart();
  });
}

if (chartMetricSelect) {
  chartMetricSelect.addEventListener("change", () => {
    setChartStyleByMetric();
    refreshTrendChart();
  });
}

if (gnnOverlayToggle) {
  gnnOverlayToggle.addEventListener("change", () => {
    drawGnnOverlay(latestZones);
  });
}

setLoadingState(true, "Connecting to live stream...");
setChartStyleByMetric();
setTimeout(() => {
  startRealtimeStream();
}, 400);
