(function () {
  "use strict";

  const COLORS = {
    blue: "#60a5fa",
    cyan: "#45d6cf",
    orange: "#f97316",
    green: "#4ade80",
    violet: "#a78bfa",
    red: "#fb7185",
    yellow: "#facc15",
  };

  const CAUSES = [
    { key: "total_late_aircraft_delay_min", label: "Late aircraft", color: COLORS.orange },
    { key: "total_carrier_delay_min", label: "Carrier", color: COLORS.blue },
    { key: "total_nas_delay_min", label: "National Air System", color: COLORS.violet },
    { key: "total_weather_delay_min", label: "Weather", color: COLORS.cyan },
  ];

  const numberFormatter = new Intl.NumberFormat("en-US");
  const compactFormatter = new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  });
  const percentFormatter = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  const shortDateFormatter = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
  const longDateFormatter = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });

  let dashboardData = null;
  let routeRenderFrame = null;

  function byId(id) {
    return document.getElementById(id);
  }

  function asNumber(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatNumber(value) {
    return numberFormatter.format(Math.round(asNumber(value)));
  }

  function formatCompact(value) {
    return compactFormatter.format(asNumber(value));
  }

  function formatPercent(value) {
    return `${percentFormatter.format(asNumber(value))}%`;
  }

  function formatMinutes(value) {
    const amount = asNumber(value);
    return `${amount < 0 ? "−" : ""}${Math.abs(amount).toFixed(1)} min`;
  }

  function parseDate(value) {
    const date = new Date(`${value}T00:00:00Z`);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function formatDate(value, formatter = shortDateFormatter) {
    const date = parseDate(value);
    return date ? formatter.format(date) : String(value ?? "");
  }

  function sum(rows, key) {
    return rows.reduce((total, row) => total + asNumber(row[key]), 0);
  }

  function weightedAverage(rows, valueKey, weightForRow) {
    let total = 0;
    let weightTotal = 0;
    rows.forEach((row) => {
      const value = Number(row[valueKey]);
      const weight = Math.max(0, asNumber(weightForRow(row)));
      if (Number.isFinite(value) && weight > 0) {
        total += value * weight;
        weightTotal += weight;
      }
    });
    return weightTotal ? total / weightTotal : 0;
  }

  function completedFlights(row) {
    return Math.max(
      0,
      asNumber(row.total_flights) -
        asNumber(row.cancelled_flights) -
        asNumber(row.diverted_flights),
    );
  }

  function emptyMessage(message) {
    return `<p style="color:#9bb0c6;margin:24px 0">${escapeHtml(message)}</p>`;
  }

  function showView(viewName, updateAddress = true) {
    const validViews = ["overview", "routes", "causes"];
    const view = validViews.includes(viewName) ? viewName : "overview";

    document.querySelectorAll("[data-dashboard-view]").forEach((section) => {
      section.hidden = section.id !== `view-${view}`;
    });
    document.querySelectorAll(".nav-button").forEach((button) => {
      const active = button.dataset.view === view;
      button.classList.toggle("active", active);
      if (active) {
        button.setAttribute("aria-current", "page");
      } else {
        button.removeAttribute("aria-current");
      }
    });

    if (updateAddress && window.location.hash !== `#${view}`) {
      window.history.replaceState(null, "", `#${view}`);
    }
  }

  function initialiseNavigation() {
    document.querySelectorAll(".nav-button").forEach((button) => {
      button.addEventListener("click", () => showView(button.dataset.view));
    });
    window.addEventListener("hashchange", () => {
      showView(window.location.hash.slice(1), false);
    });
    showView(window.location.hash.slice(1) || "overview", false);
  }

  function renderProvenance(meta) {
    const flightCount = meta.flights ? `${formatNumber(meta.flights)} flights` : "flight records";
    const dateRange = meta.from && meta.to
      ? `${formatDate(meta.from, longDateFormatter)} – ${formatDate(meta.to, longDateFormatter)}`
      : "published data range";
    byId("provenance").textContent = `${meta.source || "US DOT BTS On-Time Performance"} · ${flightCount} · ${dateRange}`;
  }

  function renderKpis(kpis) {
    const totalFlights = sum(kpis, "total_flights");
    const cancelledFlights = sum(kpis, "cancelled_flights");
    const onTimePercent = weightedAverage(kpis, "on_time_pct", completedFlights);
    const averageDelay = weightedAverage(kpis, "avg_arr_delay_min", completedFlights);

    byId("kpi-flights").textContent = formatNumber(totalFlights);
    byId("kpi-ontime").textContent = formatPercent(onTimePercent);
    byId("kpi-cancel").textContent = formatPercent(totalFlights ? (cancelledFlights / totalFlights) * 100 : 0);
    byId("kpi-delay").textContent = formatMinutes(averageDelay);
  }

  function renderCarrierBars(kpis) {
    const rows = [...kpis].sort(
      (a, b) => asNumber(b.on_time_pct) - asNumber(a.on_time_pct),
    );
    const container = byId("carrier-bars");
    if (!rows.length) {
      container.innerHTML = emptyMessage("No carrier data is available.");
      return;
    }

    container.innerHTML = rows.map((row) => {
      const value = Math.max(0, Math.min(100, asNumber(row.on_time_pct)));
      const name = `${row.carrier_name || row.carrier_code} (${row.carrier_code})`;
      return `
        <div class="carrier-row" title="${escapeHtml(name)}: ${escapeHtml(formatPercent(value))}">
          <span class="carrier-name">${escapeHtml(name)}</span>
          <span class="bar-track" aria-hidden="true"><span class="bar-fill" style="width:${value.toFixed(2)}%"></span></span>
          <strong class="carrier-value">${escapeHtml(formatPercent(value))}</strong>
        </div>`;
    }).join("");
  }

  function renderDonut(container, items, centerLabel) {
    const total = items.reduce((result, item) => result + Math.max(0, asNumber(item.value)), 0);
    if (!total) {
      container.innerHTML = emptyMessage("No values are available for this chart.");
      return;
    }

    let cursor = 0;
    const stops = items.map((item) => {
      const start = cursor;
      cursor += (Math.max(0, asNumber(item.value)) / total) * 100;
      return `${item.color} ${start.toFixed(3)}% ${cursor.toFixed(3)}%`;
    });

    container.innerHTML = `
      <div class="donut" role="img" aria-label="${escapeHtml(centerLabel)}" data-label="${escapeHtml(formatCompact(total))} total" style="background:conic-gradient(${stops.join(",")})"></div>
      <div class="donut-list">
        ${items.map((item) => `
          <div class="donut-item" style="--item-color:${item.color}">
            <i aria-hidden="true"></i>
            <span>${escapeHtml(item.label)}</span>
            <strong>${escapeHtml(formatCompact(item.value))} · ${escapeHtml(formatPercent((asNumber(item.value) / total) * 100))}</strong>
          </div>`).join("")}
      </div>`;
  }

  function chartPlaceholder(container, message) {
    container.innerHTML = emptyMessage(message);
  }

  function createLineChart(container, rows, series, options = {}) {
    if (!rows.length || !series.length) {
      chartPlaceholder(container, "No trend data is available.");
      return;
    }

    const width = options.width || 840;
    const height = options.height || 310;
    const margin = { top: 14, right: 20, bottom: 39, left: 57 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const values = rows.flatMap((row) => series.map((item) => Number(row[item.key])))
      .filter(Number.isFinite);

    if (!values.length) {
      chartPlaceholder(container, "No trend values are available.");
      return;
    }

    const rawMin = Math.min(...values);
    const rawMax = Math.max(...values);
    const yMin = options.includeNegative ? Math.min(0, rawMin * 1.08) : 0;
    const yMax = rawMax === yMin ? yMin + 1 : rawMax + (rawMax - yMin) * 0.08;
    const xForIndex = (index) => margin.left + (rows.length === 1 ? plotWidth / 2 : (index / (rows.length - 1)) * plotWidth);
    const yForValue = (value) => margin.top + plotHeight - ((value - yMin) / (yMax - yMin)) * plotHeight;
    const tickFormatter = options.tickFormatter || formatCompact;
    const tooltipFormatter = options.tooltipFormatter || formatNumber;

    let grid = "";
    for (let tick = 0; tick <= 4; tick += 1) {
      const value = yMin + ((yMax - yMin) * tick) / 4;
      const y = yForValue(value);
      grid += `<line class="grid-line" x1="${margin.left}" y1="${y.toFixed(2)}" x2="${width - margin.right}" y2="${y.toFixed(2)}"></line>`;
      grid += `<text x="${margin.left - 9}" y="${(y + 3).toFixed(2)}" text-anchor="end">${escapeHtml(tickFormatter(value))}</text>`;
    }

    const tickCount = Math.min(6, rows.length);
    let xTicks = "";
    for (let tick = 0; tick < tickCount; tick += 1) {
      const index = tickCount === 1 ? 0 : Math.round((tick / (tickCount - 1)) * (rows.length - 1));
      const x = xForIndex(index);
      xTicks += `<line class="axis-line" x1="${x.toFixed(2)}" y1="${height - margin.bottom}" x2="${x.toFixed(2)}" y2="${height - margin.bottom + 5}"></line>`;
      xTicks += `<text x="${x.toFixed(2)}" y="${height - 13}" text-anchor="middle">${escapeHtml(formatDate(rows[index].date_day))}</text>`;
    }

    const lines = series.map((item) => {
      let drawing = false;
      const commands = [];
      rows.forEach((row, index) => {
        const value = Number(row[item.key]);
        if (!Number.isFinite(value)) {
          drawing = false;
          return;
        }
        commands.push(`${drawing ? "L" : "M"}${xForIndex(index).toFixed(2)},${yForValue(value).toFixed(2)}`);
        drawing = true;
      });
      return `<path d="${commands.join(" ")}" fill="none" stroke="${item.color}" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round"></path>`;
    }).join("");

    const tooltipPoints = series.map((item) => rows.map((row, index) => {
      const value = Number(row[item.key]);
      if (!Number.isFinite(value)) {
        return "";
      }
      const description = `${formatDate(row.date_day, longDateFormatter)} · ${item.label}: ${tooltipFormatter(value)}`;
      return `<circle cx="${xForIndex(index).toFixed(2)}" cy="${yForValue(value).toFixed(2)}" r="6" fill="transparent"><title>${escapeHtml(description)}</title></circle>`;
    }).join("")).join("");

    container.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(options.label || "Trend chart")}">
        ${grid}
        <line class="axis-line" x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}"></line>
        ${xTicks}
        ${lines}
        ${tooltipPoints}
      </svg>`;
  }

  function renderOverview(data) {
    createLineChart(
      byId("trend-chart"),
      data.trends,
      [
        { key: "delayed_flights", label: "Delayed flights", color: COLORS.blue },
        { key: "cancelled_flights", label: "Cancelled flights", color: COLORS.orange },
      ],
      {
        label: "Daily delayed and cancelled flight counts",
        tooltipFormatter: formatNumber,
      },
    );

    renderDonut(
      byId("cancellation-donut"),
      data.cancellations.map((row, index) => ({
        label: row.cancellation_reason,
        value: row.cancelled_flights,
        color: [COLORS.orange, COLORS.blue, COLORS.violet, COLORS.red][index % 4],
      })),
      "Cancellation reason share",
    );
    renderCarrierBars(data.kpis);
  }

  function airportLabel(code, airportLookup) {
    const airport = airportLookup.get(code);
    if (!airport) {
      return code;
    }
    const place = [airport.city, airport.state].filter(Boolean).join(", ");
    return place ? `${code} — ${place}` : code;
  }

  function populateRouteFilters(data) {
    const airportLookup = new Map(data.airports.map((airport) => [airport.airport_code, airport]));
    const originCodes = [...new Set(data.routes.map((route) => route.origin_airport))].sort();
    const destinationCodes = [...new Set(data.routes.map((route) => route.dest_airport))].sort();
    const optionMarkup = (codes) => codes.map((code) => (
      `<option value="${escapeHtml(code)}">${escapeHtml(airportLabel(code, airportLookup))}</option>`
    )).join("");

    byId("origin-filter").insertAdjacentHTML("beforeend", optionMarkup(originCodes));
    byId("destination-filter").insertAdjacentHTML("beforeend", optionMarkup(destinationCodes));

    ["origin-filter", "destination-filter"].forEach((id) => {
      byId(id).addEventListener("change", scheduleRouteRender);
    });
    byId("min-flights").addEventListener("input", () => {
      byId("min-flights-value").value = byId("min-flights").value;
      scheduleRouteRender();
    });
    byId("reset-routes").addEventListener("click", () => {
      byId("origin-filter").value = "";
      byId("destination-filter").value = "";
      byId("min-flights").value = "100";
      byId("min-flights-value").value = "100";
      renderRoutes();
    });
  }

  function scheduleRouteRender() {
    if (routeRenderFrame !== null) {
      window.cancelAnimationFrame(routeRenderFrame);
    }
    routeRenderFrame = window.requestAnimationFrame(() => {
      routeRenderFrame = null;
      renderRoutes();
    });
  }

  function filteredRoutes() {
    const origin = byId("origin-filter").value;
    const destination = byId("destination-filter").value;
    const minimumFlights = asNumber(byId("min-flights").value, 100);
    return dashboardData.routes.filter((route) => (
      (!origin || route.origin_airport === origin) &&
      (!destination || route.dest_airport === destination) &&
      asNumber(route.total_flights) >= minimumFlights
    ));
  }

  function scatterColor(cancellationPercent) {
    const value = asNumber(cancellationPercent);
    if (value < 1) return COLORS.cyan;
    if (value < 2) return COLORS.blue;
    if (value < 4) return COLORS.orange;
    return COLORS.red;
  }

  function renderRouteScatter(routes) {
    const container = byId("route-scatter");
    if (!routes.length) {
      chartPlaceholder(container, "No routes match these filters. Lower the minimum flights or reset the filters.");
      return;
    }

    const points = [...routes]
      .sort((a, b) => asNumber(b.total_flights) - asNumber(a.total_flights))
      .slice(0, 500);
    const width = 920;
    const height = 420;
    const margin = { top: 18, right: 24, bottom: 58, left: 64 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const xValues = points.map((route) => asNumber(route.on_time_pct));
    const yValues = points.map((route) => asNumber(route.avg_arr_delay_min));
    const flightValues = points.map((route) => asNumber(route.total_flights));
    const rawXMin = Math.min(...xValues);
    const rawXMax = Math.max(...xValues);
    const rawYMin = Math.min(...yValues);
    const rawYMax = Math.max(...yValues);
    const xSpan = Math.max(1, rawXMax - rawXMin);
    const ySpan = Math.max(1, rawYMax - rawYMin);
    const xMin = Math.max(0, rawXMin - xSpan * 0.06);
    const xMax = Math.min(100, rawXMax + xSpan * 0.06);
    const yMin = Math.min(0, rawYMin - ySpan * 0.06);
    const yMax = rawYMax + ySpan * 0.08;
    const minFlights = Math.min(...flightValues);
    const maxFlights = Math.max(...flightValues);
    const xFor = (value) => margin.left + ((value - xMin) / Math.max(1, xMax - xMin)) * plotWidth;
    const yFor = (value) => margin.top + plotHeight - ((value - yMin) / Math.max(1, yMax - yMin)) * plotHeight;
    const radiusFor = (value) => {
      const ratio = (value - minFlights) / Math.max(1, maxFlights - minFlights);
      return 3.5 + Math.sqrt(Math.max(0, ratio)) * 14;
    };

    let grid = "";
    for (let tick = 0; tick <= 5; tick += 1) {
      const xValue = xMin + ((xMax - xMin) * tick) / 5;
      const x = xFor(xValue);
      grid += `<line class="grid-line" x1="${x.toFixed(2)}" y1="${margin.top}" x2="${x.toFixed(2)}" y2="${height - margin.bottom}"></line>`;
      grid += `<text x="${x.toFixed(2)}" y="${height - margin.bottom + 19}" text-anchor="middle">${escapeHtml(`${xValue.toFixed(0)}%`)}</text>`;
    }
    for (let tick = 0; tick <= 5; tick += 1) {
      const yValue = yMin + ((yMax - yMin) * tick) / 5;
      const y = yFor(yValue);
      grid += `<line class="grid-line" x1="${margin.left}" y1="${y.toFixed(2)}" x2="${width - margin.right}" y2="${y.toFixed(2)}"></line>`;
      grid += `<text x="${margin.left - 10}" y="${(y + 3).toFixed(2)}" text-anchor="end">${escapeHtml(yValue.toFixed(0))}</text>`;
    }

    const circles = points.map((route) => {
      const description = `${route.route}: ${formatNumber(route.total_flights)} flights, ${formatPercent(route.on_time_pct)} on time, ${formatMinutes(route.avg_arr_delay_min)} average arrival delay, ${formatPercent(route.cancellation_pct)} cancelled`;
      return `<circle cx="${xFor(asNumber(route.on_time_pct)).toFixed(2)}" cy="${yFor(asNumber(route.avg_arr_delay_min)).toFixed(2)}" r="${radiusFor(asNumber(route.total_flights)).toFixed(2)}" fill="${scatterColor(route.cancellation_pct)}" fill-opacity="0.58" stroke="#d9f6ff" stroke-opacity="0.32" stroke-width="0.8"><title>${escapeHtml(description)}</title></circle>`;
    }).join("");

    container.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Route on-time performance and average arrival delay; the chart displays up to 500 busiest matching routes">
        ${grid}
        <line class="axis-line" x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}"></line>
        ${circles}
        <text class="axis-label" x="${margin.left + plotWidth / 2}" y="${height - 10}" text-anchor="middle">On-Time %</text>
        <text class="axis-label" x="17" y="${margin.top + plotHeight / 2}" text-anchor="middle" transform="rotate(-90 17 ${margin.top + plotHeight / 2})">Average arrival delay (minutes)</text>
      </svg>`;
  }

  function renderRouteTable(routes) {
    const body = byId("route-table");
    const delayedRoutes = routes
      .filter((route) => Number.isFinite(Number(route.avg_arr_delay_min)))
      .sort((a, b) => (
        asNumber(b.avg_arr_delay_min) - asNumber(a.avg_arr_delay_min) ||
        asNumber(b.total_flights) - asNumber(a.total_flights)
      ))
      .slice(0, 25);

    if (!delayedRoutes.length) {
      body.innerHTML = `<tr><td colspan="5">No routes match these filters.</td></tr>`;
      return;
    }

    body.innerHTML = delayedRoutes.map((route) => `
      <tr>
        <td><strong>${escapeHtml(route.origin_airport)} → ${escapeHtml(route.dest_airport)}</strong></td>
        <td>${escapeHtml(formatNumber(route.total_flights))}</td>
        <td>${escapeHtml(formatPercent(route.on_time_pct))}</td>
        <td>${escapeHtml(formatMinutes(route.avg_arr_delay_min))}</td>
        <td>${escapeHtml(formatPercent(route.cancellation_pct))}</td>
      </tr>`).join("");
  }

  function renderRoutes() {
    if (!dashboardData) return;
    const routes = filteredRoutes();
    byId("route-count").textContent = `${formatNumber(routes.length)} ${routes.length === 1 ? "route" : "routes"}`;
    renderRouteScatter(routes);
    renderRouteTable([...routes]);
  }

  function causeTotals(trends) {
    return CAUSES.map((cause) => ({ ...cause, value: sum(trends, cause.key) }));
  }

  function renderCauses(data) {
    const totals = causeTotals(data.trends);
    const allMinutes = totals.reduce((total, cause) => total + cause.value, 0);
    byId("cause-cards").innerHTML = totals.map((cause) => `
      <article class="kpi-card">
        <span>${escapeHtml(cause.label)}</span>
        <strong>${escapeHtml(formatCompact(cause.value))} min</strong>
        <small>${escapeHtml(formatPercent(allMinutes ? (cause.value / allMinutes) * 100 : 0))} of attributed delay minutes</small>
      </article>`).join("");

    renderDonut(byId("cause-donut"), totals, "Attributed delay minutes by cause");

    createLineChart(
      byId("delay-rate-chart"),
      data.trends,
      [{ key: "delayed_pct", label: "Delay rate", color: COLORS.cyan }],
      {
        label: "Daily percentage of delayed flights",
        tickFormatter: (value) => `${value.toFixed(0)}%`,
        tooltipFormatter: formatPercent,
      },
    );

    byId("cause-legend").innerHTML = CAUSES.map((cause) => (
      `<span><i style="--legend-color:${cause.color}"></i>${escapeHtml(cause.label)}</span>`
    )).join("");
    createLineChart(
      byId("cause-trend-chart"),
      data.trends,
      CAUSES.map((cause) => ({ key: cause.key, label: cause.label, color: cause.color })),
      {
        label: "Daily delay minutes for late aircraft, carrier, National Air System, and weather causes",
        tooltipFormatter: (value) => `${formatNumber(value)} min`,
      },
    );
  }

  function validateData(data) {
    if (!data || typeof data !== "object") {
      throw new Error("The dashboard payload is not an object.");
    }
    ["kpis", "trends", "cancellations", "routes", "airports"].forEach((key) => {
      if (!Array.isArray(data[key])) {
        throw new Error(`The dashboard payload is missing ${key}.`);
      }
    });
    return data;
  }

  async function loadDashboard() {
    try {
      const response = await fetch("./data/dashboard-data.json", { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Dashboard data request failed with status ${response.status}.`);
      }
      dashboardData = validateData(await response.json());
      renderProvenance(dashboardData.meta || {});
      renderKpis(dashboardData.kpis);
      renderOverview(dashboardData);
      populateRouteFilters(dashboardData);
      renderRoutes();
      renderCauses(dashboardData);
      byId("loading").hidden = true;
    } catch (error) {
      console.error("Unable to initialise the airline dashboard:", error);
      byId("loading").hidden = true;
      byId("error").hidden = false;
      document.querySelectorAll("[data-dashboard-view]").forEach((section) => {
        section.hidden = true;
      });
    }
  }

  initialiseNavigation();
  loadDashboard();
}());
