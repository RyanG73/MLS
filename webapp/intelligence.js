(function () {
  "use strict";

  var params = new URLSearchParams(window.location.search);
  if (params.get("league") !== "intel") return;

  var root = document.getElementById("view-outlook");
  if (!root) return;

  var ACCESS_KEY = "entenser.intel.access";
  var REFRESH_KEY = "entenser.intel.refresh";
  var LAST_TEAM_KEY = "entenser.intel.last-team";
  var API_BASE = params.get("api") || window.ENTENSER_API_BASE ||
    ((location.hostname === "localhost" || location.hostname === "127.0.0.1")
      ? "http://127.0.0.1:8787/v1" : "https://api.entenser.com/v1");

  var TABS = {
    today: [1, 2, 3, 4, 22, 23, 25],
    explore: [5, 6, 9, 13, 14, 15, 19],
    history: [10, 11, 17, 18, 24, 26],
    studio: [7, 8, 12, 16, 20, 21]
  };

  var state = {
    tab: "today",
    me: null,
    prefs: {},
    record: null,
    leagueId: "",
    teamId: "",
    assumptions: {},
    assumptionHistory: [{}],
    assumptionCursor: 0,
    scenario: null,
    ask: null,
    journal: [],
    workspaces: [],
    rivalId: "",
    rivalRecord: null,
    busy: false,
    notice: "",
    error: "",
    selectedTarget: ""
  };

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[char];
    });
  }

  function attr(value) {
    return escapeHtml(value);
  }

  function pct(value) {
    return value == null || !isFinite(Number(value)) ? "Unavailable" : Number(value).toFixed(1) + "%";
  }

  function pp(value) {
    if (value == null || !isFinite(Number(value))) return "No prior";
    var number = Number(value);
    return (number > 0 ? "+" : "") + number.toFixed(1) + "pp";
  }

  function number(value, digits) {
    return value == null || !isFinite(Number(value)) ? "Unavailable" : Number(value).toFixed(digits == null ? 1 : digits);
  }

  function shortDate(value) {
    if (!value) return "Date pending";
    var parsed = new Date(value);
    if (isNaN(parsed.getTime())) return escapeHtml(value);
    return parsed.toLocaleDateString(undefined, {month: "short", day: "numeric", year: parsed.getFullYear() !== new Date().getFullYear() ? "numeric" : undefined});
  }

  function modeLabel(value) {
    return String(value || "active_matchweek").replace(/_/g, " ");
  }

  function tokenClaims() {
    try {
      var token = localStorage.getItem(ACCESS_KEY);
      if (!token) return null;
      var body = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
      while (body.length % 4) body += "=";
      return JSON.parse(atob(body));
    } catch (error) {
      return null;
    }
  }

  function authHeaders() {
    var token = localStorage.getItem(ACCESS_KEY);
    return token ? {Authorization: "Bearer " + token} : {};
  }

  async function refreshAccess() {
    var refreshToken = localStorage.getItem(REFRESH_KEY);
    if (!refreshToken) return false;
    var response = await fetch(API_BASE + "/auth/refresh", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({refresh_token: refreshToken})
    });
    if (!response.ok) return false;
    var payload = await response.json();
    localStorage.setItem(ACCESS_KEY, payload.access_token);
    return true;
  }

  async function api(path, options, retried) {
    options = options || {};
    var headers = Object.assign({"Accept": "application/json"}, authHeaders(), options.headers || {});
    if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    var response = await fetch(API_BASE + path, Object.assign({}, options, {headers: headers}));
    if (response.status === 401 && !retried && path !== "/auth/refresh" && await refreshAccess()) {
      return api(path, options, true);
    }
    var type = response.headers.get("content-type") || "";
    var payload = type.indexOf("application/json") >= 0 ? await response.json() : await response.blob();
    if (!response.ok) {
      var error = new Error(payload && payload.error ? payload.error : "Request failed (" + response.status + ")");
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function analytics(eventName, properties) {
    api("/intel/analytics", {
      method: "POST",
      body: JSON.stringify({event: eventName, properties: properties || {}})
    }).catch(function () {});
  }

  function catalogLeagues() {
    var catalog = window.TEAM_CATALOG || {};
    return (catalog.leagues || []).filter(function (league) {
      return league.teams && league.teams.length;
    });
  }

  function findSelection(leagueId, teamId) {
    var leagues = catalogLeagues();
    for (var i = 0; i < leagues.length; i += 1) {
      if (leagueId && leagues[i].league_id !== leagueId) continue;
      for (var j = 0; j < leagues[i].teams.length; j += 1) {
        if (!teamId || leagues[i].teams[j].team_id === teamId) {
          return {league: leagues[i], team: leagues[i].teams[j]};
        }
      }
    }
    return null;
  }

  function favoriteCandidates() {
    var saved;
    try {
      saved = JSON.parse(localStorage.getItem("pitchside.favTeams") || "[]");
    } catch (error) {
      saved = [];
    }
    return saved.map(function (favorite) {
      var league = catalogLeagues().find(function (entry) { return entry.league_id === favorite.league; });
      var team = league && league.teams.find(function (entry) { return entry.team === favorite.team; });
      return team ? {league_id: league.league_id, team_id: team.team_id, team: team.team} : null;
    }).filter(Boolean);
  }

  function defaultSelection() {
    var stored;
    try {
      stored = JSON.parse(localStorage.getItem(LAST_TEAM_KEY) || "null");
    } catch (error) {
      stored = null;
    }
    var candidates = [];
    if (params.get("intelLeague") && params.get("team")) candidates.push({league_id: params.get("intelLeague"), team_id: params.get("team")});
    if (stored) candidates.push(stored);
    (state.prefs.teams || []).forEach(function (entry) { candidates.push(entry); });
    favoriteCandidates().forEach(function (entry) { candidates.push(entry); });
    for (var i = 0; i < candidates.length; i += 1) {
      var match = findSelection(candidates[i].league_id || candidates[i].league, candidates[i].team_id);
      if (match) return match;
      var byName = catalogLeagues().find(function (league) {
        return league.league_id === (candidates[i].league_id || candidates[i].league);
      });
      var namedTeam = byName && byName.teams.find(function (team) { return team.team === candidates[i].team; });
      if (namedTeam) return {league: byName, team: namedTeam};
    }
    var first = catalogLeagues()[0];
    return first ? {league: first, team: first.teams[0]} : null;
  }

  function setMessage(message, isError) {
    state.notice = isError ? "" : message;
    state.error = isError ? message : "";
  }

  function loading(label) {
    root.innerHTML = '<div class="ed-wrap intel-app"><div class="intel-loading">' + escapeHtml(label || "Loading intelligence") + "</div></div>";
  }

  function signInView() {
    document.title = "Intelligence Hub · Entenser";
    root.classList.remove("hidden");
    root.innerHTML = '<div class="ed-wrap intel-app">' +
      '<header class="intel-command"><div class="intel-command-copy">' +
      '<div class="intel-eyebrow">Private team intelligence</div><h1>Intelligence Hub</h1>' +
      '<p>Your teams, monitored. Every conclusion links back to a forecast snapshot or fixture.</p></div></header>' +
      '<section class="intel-auth"><h2>Sign in</h2><p>Use a one-time link. No password is stored.</p>' +
      '<form id="intel-signin" class="intel-form-row"><div class="intel-field"><label for="intel-email">Email</label>' +
      '<input class="intel-input" id="intel-email" type="email" autocomplete="email" required></div>' +
      '<button class="intel-action primary" type="submit">Send secure link</button></form>' +
      (state.notice ? '<div class="intel-success">' + escapeHtml(state.notice) + "</div>" : "") +
      (state.error ? '<div class="intel-error">' + escapeHtml(state.error) + "</div>" : "") +
      '<div class="intel-note">The link expires in 15 minutes and can be used once.</div></section></div>';
  }

  function freeView() {
    document.title = "Intelligence Hub · Entenser";
    root.classList.remove("hidden");
    root.innerHTML = '<div class="ed-wrap intel-app">' +
      commandHeader("Intelligence Hub", "Free account") +
      '<section class="intel-auth"><h2>Start Intelligence access</h2>' +
      '<p>Your account is active. Current forecasts remain free; monitoring, scenarios, private history, alerts, and saved work require an Intelligence trial or subscription.</p>' +
      '<button class="intel-action primary" data-action="checkout" data-plan="intel">Start Intelligence</button> ' +
      '<button class="intel-action" data-action="logout">Sign out</button>' +
      (state.error ? '<div class="intel-error">' + escapeHtml(state.error) + "</div>" : "") +
      '</section></div>';
  }

  function commandHeader(title, subtitle) {
    var plan = state.me ? state.me.plan : "";
    return '<header class="intel-command"><div class="intel-command-copy">' +
      '<div class="intel-eyebrow">Personal Intelligence Hub</div><h1>' + escapeHtml(title) + "</h1>" +
      '<p>' + escapeHtml(subtitle || "") + '</p></div><div class="intel-command-actions">' +
      '<span class="intel-session"><strong>' + escapeHtml(plan) + '</strong> plan</span>' +
      '<button class="intel-action" data-action="refresh">Refresh</button>' +
      '<button class="intel-icon-btn" data-action="logout" title="Sign out" aria-label="Sign out">×</button>' +
      "</div></header>";
  }

  function teamOptions() {
    return catalogLeagues().map(function (league) {
      var options = league.teams.map(function (team) {
        var selected = league.league_id === state.leagueId && team.team_id === state.teamId ? " selected" : "";
        return '<option value="' + attr(league.league_id + "|" + team.team_id) + '"' + selected + ">" + escapeHtml(team.team) + "</option>";
      }).join("");
      return '<optgroup label="' + attr(league.league) + '">' + options + "</optgroup>";
    }).join("");
  }

  function stateBadge(status) {
    var safe = status === "thin_history" || status === "unavailable" ? status : "live";
    return '<span class="intel-state ' + safe + '">' + escapeHtml(safe.replace(/_/g, " ")) + "</span>";
  }

  function featureShell(feature) {
    var body = feature.status === "unavailable"
      ? '<div class="intel-empty">This calculation is unavailable for this competition or there is not enough evidence yet.</div>'
      : renderFeature(Number(feature.feature_id), feature.data || {});
    return '<section class="intel-feature" id="intel-feature-' + Number(feature.feature_id) + '">' +
      '<div class="intel-feature-head"><span class="intel-feature-num">' + String(feature.feature_id).padStart(2, "0") + "</span>" +
      '<div class="intel-feature-title"><h2>' + escapeHtml(feature.name) + "</h2></div>" +
      stateBadge(feature.status) + "</div>" + body + "</section>";
  }

  function evidence(ids) {
    if (!ids || !ids.length) return "";
    return '<div class="intel-evidence">Evidence: ' + ids.slice(0, 3).map(escapeHtml).join(" · ") + "</div>";
  }

  function fact(label, value) {
    return '<div class="intel-fact"><span>' + escapeHtml(label) + "</span><b>" + escapeHtml(value) + "</b></div>";
  }

  function table(headers, rows) {
    return '<div class="intel-table-scroll"><table class="intel-data-table"><thead><tr>' +
      headers.map(function (header) { return "<th>" + escapeHtml(header) + "</th>"; }).join("") +
      "</tr></thead><tbody>" + rows.join("") + "</tbody></table></div>";
  }

  function empty(text) {
    return '<div class="intel-empty">' + escapeHtml(text) + "</div>";
  }

  function renderBrief(data) {
    var scenarioData = state.record.features["5"] && state.record.features["5"].data;
    var baseline = scenarioData && scenarioData.baseline ? scenarioData.baseline : {};
    var target = state.selectedTarget || data.target_metric;
    var current = target === data.target_metric ? data.current_pct : baseline[target];
    var deltaClass = Number(data.seven_day_change_pp) > 0 ? " up" : Number(data.seven_day_change_pp) < 0 ? " down" : "";
    var targets = Object.keys(baseline).filter(function (key) {
      return ["title", "ucl", "europa", "conf", "releg", "playoff", "promotion", "top_n"].indexOf(key) >= 0;
    });
    var select = targets.length ? '<select class="intel-select" id="intel-target" aria-label="Pinned target">' +
      targets.map(function (key) {
        return '<option value="' + attr(key) + '"' + (key === target ? " selected" : "") + ">" + escapeHtml(key.replace(/_/g, " ")) + "</option>";
      }).join("") + "</select>" : "";
    var next = data.next_high_impact_fixture;
    var summary = target === data.target_metric ? data.summary :
      escapeHtml(target.replace(/_/g, " ")) + " is " + pct(current) + " in the current simulation.";
    return '<div class="intel-brief"><div class="intel-primary-metric"><div class="label">' + select + "</div>" +
      '<div class="value">' + pct(current) + '</div><div class="delta' + deltaClass + '">' + pp(data.seven_day_change_pp) + " in 7 days</div></div>" +
      '<div><p class="intel-brief-summary">' + escapeHtml(summary) + '</p><div class="intel-facts">' +
      fact("Projected points", number(data.projected_points, 1)) +
      fact("Projected rank", number(data.projected_rank, 1)) +
      fact("Next leverage", next ? number(next.leverage_pp, 1) + "pp" : "Unavailable") +
      fact("Freshness", data.generated || "Unavailable") +
      "</div>" + (next ? evidence(next.evidence_ids) : "") + "</div></div>";
  }

  function renderEvents(data, explanatory) {
    var events = data.events || [];
    if (!events.length) return empty(explanatory ? "No supported movement explanation is available yet." : "No material change since your last visit.");
    return '<div class="intel-tape">' + events.slice(0, 12).map(function (event) {
      var movement = event.delta_pp == null ? "" : pp(event.delta_pp);
      var attribution = explanatory && event.attribution && event.attribution.length
        ? '<div class="intel-note">' + event.attribution.map(function (part) {
            return escapeHtml(String(part.kind || "evidence").replace(/_/g, " ")) + ": " + pp(part.delta_pp);
          }).join(" · ") + "</div>" : "";
      return '<div class="intel-tape-row"><time>' + shortDate(event.effective_at || event.generated_at) + '</time>' +
        '<div class="body"><b>' + escapeHtml(String(event.event_type || "forecast update").replace(/_/g, " ")) + "</b> · " +
        escapeHtml(String(event.cause_class || "observed").replace(/_/g, " ")) + attribution + evidence(event.evidence_ids) + "</div>" +
        '<span class="intel-move' + (Number(event.delta_pp) > 0 ? " up" : Number(event.delta_pp) < 0 ? " down" : "") + '">' + movement + "</span></div>";
    }).join("") + "</div>";
  }

  function renderLeverage(data) {
    var fixtures = data.fixtures || [];
    if (!fixtures.length) return empty("No remaining fixture leverage can be calculated.");
    return table(["Date", "Fixture", "Scope", "Range", "Expected move"], fixtures.slice(0, 10).map(function (fixture) {
      return "<tr><td>" + shortDate(fixture.date) + "</td><td><strong>" + escapeHtml(fixture.home) + " vs " + escapeHtml(fixture.away) +
        "</strong>" + evidence(fixture.evidence_ids) + "</td><td>" + (fixture.is_own_fixture ? "Own match" : "Rival dependency") +
        '</td><td class="num">' + number(fixture.leverage_pp, 1) + 'pp</td><td class="num">' + pp(fixture.expected_move_pp) + "</td></tr>";
    }));
  }

  function relevantScenarioFixtures(data) {
    var fixtures = data.fixtures || [];
    var own = fixtures.filter(function (fixture) {
      return fixture.home_id === state.teamId || fixture.away_id === state.teamId;
    });
    return own.slice(0, 8);
  }

  function scenarioControls(data) {
    var fixtures = relevantScenarioFixtures(data);
    var rows = fixtures.map(function (fixture) {
      var selected = state.assumptions[fixture.fixture_id];
      var buttons = ["H", "D", "A"].map(function (outcome) {
        return '<button type="button" data-action="assume" data-fixture="' + attr(fixture.fixture_id) + '" data-outcome="' + outcome + '"' +
          (selected === outcome ? ' class="on"' : "") + ">" + outcome + "</button>";
      }).join("");
      return "<tr><td>" + shortDate(fixture.date) + "</td><td><strong>" + escapeHtml(fixture.home) + " vs " + escapeHtml(fixture.away) +
        '</strong></td><td><div class="intel-segment">' + buttons + "</div></td></tr>";
    });
    var baseline = data.baseline || {};
    var scenario = state.scenario && state.scenario.scenario ? state.scenario.scenario : {};
    var metric = state.selectedTarget || state.record.target_metric;
    return '<div class="intel-tool"><div class="intel-toolbar-row">' +
      '<button class="intel-icon-btn" data-action="scenario-undo" title="Undo" aria-label="Undo">↶</button>' +
      '<button class="intel-icon-btn" data-action="scenario-redo" title="Redo" aria-label="Redo">↷</button>' +
      '<button class="intel-action" data-action="scenario-reset">Reset</button><span class="spacer"></span>' +
      '<span class="intel-assumption-count">' + Object.keys(state.assumptions).length + " assumptions</span>" +
      '<button class="intel-action primary" data-action="scenario-run">Run scenario</button></div>' +
      table(["Date", "Fixture", "Forced result"], rows) +
      '<div class="intel-scenario-result"><div><span>Target</span><b>' + escapeHtml(metric.replace(/_/g, " ")) +
      '</b></div><div><span>Baseline</span><b>' + pct(baseline[metric]) +
      '</b></div><div><span>Scenario</span><b>' + (state.scenario ? pct(scenario[metric]) : "Not run") +
      "</b></div></div>" + (state.scenario ? '<div class="intel-toolbar-row" style="margin-top:10px"><span class="intel-assumption-count">Seed ' +
      escapeHtml(state.scenario.seed) + " · " + escapeHtml(state.scenario.n) +
      ' runs · snapshot ' + escapeHtml(state.scenario.snapshot_id) + '</span><span class="spacer"></span><button class="intel-action" data-action="scenario-save">Save receipt</button></div>' : "") + "</div>";
  }

  function renderPaths(data) {
    var paths = data.paths || [];
    if (!paths.length) return empty("No supported path search is available.");
    return paths.slice(0, 6).map(function (path) {
      var assumptions = path.assumptions || {};
      var assumptionCount = Array.isArray(assumptions) ? assumptions.length : Object.keys(assumptions).length;
      var label = String(path.label || path.kind || "modeled path").replace(/_/g, " ");
      var sentence = assumptionCount + " forced result" + (assumptionCount === 1 ? "" : "s");
      if (path.snapshot_language) sentence += " · " + path.snapshot_language;
      return '<div class="intel-claim"><strong>' + escapeHtml(label) + "</strong>" +
        escapeHtml(sentence) + (path.resulting_pct != null ? " · " + pct(path.resulting_pct) : "") +
        evidence(path.evidence_ids) + "</div>";
    }).join("");
  }

  function renderAlerts(data) {
    var notifications = state.prefs.notifications || {};
    return '<div class="intel-tool"><div class="intel-form-row"><div class="intel-field"><label for="intel-threshold">Minimum move (percentage points)</label>' +
      '<input class="intel-input" id="intel-threshold" type="number" min="1" max="50" step="0.5" value="' + attr(state.prefs.threshold_pp == null ? 5 : state.prefs.threshold_pp) + '"></div>' +
      '<label><input id="intel-material-alert" type="checkbox"' + (notifications.material_change !== false ? " checked" : "") + '> Material changes</label>' +
      '<label><input id="intel-weekly-alert" type="checkbox"' + (notifications.weekly !== false ? " checked" : "") + '> Adaptive briefing</label>' +
      '<button class="intel-action primary" data-action="save-alerts">Save delivery rules</button></div>' +
      '<div class="intel-note">Current delivery state: ' + escapeHtml(data.send_state || "shadow") + " · cap " + escapeHtml(data.default_cap || "configured") + "</div></div>";
  }

  function renderBriefing(data) {
    var raw = data.sections || {};
    var sections = Array.isArray(raw) ? raw.map(function (value, index) {
      return {key: String(index + 1), value: value};
    }) : Object.keys(raw).map(function (key) { return {key: key, value: raw[key]}; });
    var available = sections.filter(function (section) { return section.value != null; });
    if (!available.length) return empty("This mode has no material briefing sections to deliver.");
    return '<div class="intel-tape">' + available.map(function (section) {
      var value = section.value;
      var summary = "";
      if (typeof value === "string") summary = value;
      else if (Array.isArray(value)) summary = value.length + " material update" + (value.length === 1 ? "" : "s");
      else if (value.summary) summary = value.summary;
      else if (value.home || value.away) summary = (value.home || "") + " vs " + (value.away || "");
      else if (value.current_pct != null) summary = pct(value.current_pct) + " " + String(value.target_metric || "target").replace(/_/g, " ");
      else summary = "Evidence package ready";
      return '<div class="intel-tape-row"><time>' + escapeHtml(data.cadence || "adaptive") + '</time><div class="body"><b>' +
        escapeHtml(section.key.replace(/_/g, " ")) + "</b> · " + escapeHtml(summary) + evidence(value.evidence_ids) + "</div></div>";
    }).join("") + "</div>";
  }

  function renderRace(data) {
    var rivals = data.rivals || [];
    if (!rivals.length) return empty("No close target competitor is available.");
    return table(["Club", "Target", "Gap", "Projected points", "Projected rank"], rivals.slice(0, 8).map(function (rival) {
      return '<tr><td><strong>' + escapeHtml(rival.team) + '</strong></td><td class="num">' + pct(rival.target_pct) +
        '</td><td class="num">' + pp(rival.gap_pp) + '</td><td class="num">' + number(rival.proj_pts, 1) +
        '</td><td class="num">' + number(rival.proj_rank, 1) + "</td></tr>";
    }));
  }

  function renderExpectation(data) {
    if (!data || !Object.keys(data).length) return empty("A preseason expectation checkpoint will appear after enough dated forecasts accrue.");
    var checkpoints = data.checkpoints || data.seasons || [];
    if (!Array.isArray(checkpoints) || !checkpoints.length) {
      return '<div class="intel-indicators">' + Object.keys(data).slice(0, 6).map(function (key) {
        return '<div class="intel-indicator"><span>' + escapeHtml(key.replace(/_/g, " ")) + '</span><b>' +
          escapeHtml(typeof data[key] === "object" ? "Recorded" : data[key]) + "</b></div>";
      }).join("") + "</div>";
    }
    return table(["Checkpoint", "Expected", "Actual", "Difference"], checkpoints.map(function (row) {
      return "<tr><td>" + escapeHtml(row.label || row.date || row.season) + '</td><td class="num">' + escapeHtml(row.expected || row.expected_points) +
        '</td><td class="num">' + escapeHtml(row.actual || row.actual_points) + '</td><td class="num">' + escapeHtml(row.difference || row.delta) + "</td></tr>";
    }));
  }

  function renderTimeMachine(data) {
    var points = data.points || [];
    if (!points.length) return empty("Trajectory history has not accrued for this target.");
    var metric = state.selectedTarget || state.record.target_metric;
    var plotted = points.map(function (point) {
      var value = point.value != null ? point.value : point.pct != null ? point.pct : point.values && point.values[metric];
      return {value: Number(value), date: point.snapshot_date || point.date};
    }).filter(function (point) { return isFinite(point.value); });
    if (!plotted.length) return empty("Trajectory values are unavailable for the pinned target.");
    var width = 900;
    var height = 180;
    var coords = plotted.map(function (point, index) {
      var x = plotted.length === 1 ? width / 2 : index * width / (plotted.length - 1);
      var y = height - Math.max(0, Math.min(100, point.value)) * height / 100;
      return x.toFixed(1) + "," + y.toFixed(1);
    }).join(" ");
    return '<svg class="intel-chart" viewBox="0 0 900 180" role="img" aria-label="Forecast trajectory">' +
      '<line class="intel-chart-grid" x1="0" y1="45" x2="900" y2="45"></line><line class="intel-chart-grid" x1="0" y1="90" x2="900" y2="90"></line>' +
      '<line class="intel-chart-grid" x1="0" y1="135" x2="900" y2="135"></line><polyline class="intel-chart-line" points="' + attr(coords) + '"></polyline></svg>' +
      '<div class="intel-facts">' + fact("First", pct(plotted[0].value)) + fact("Current", pct(plotted[plotted.length - 1].value)) +
      fact("Observations", plotted.length) + fact("Resolution", data.full_resolution ? "Full" : "Reduced") + "</div>";
  }

  function renderConsensus(data) {
    if (!data || !Object.keys(data).length) return empty("No comparable market consensus cleared the coverage policy.");
    var comparisons = data.comparisons || data.rows || [];
    if (!comparisons.length) {
      return '<div class="intel-claim"><strong>Coverage</strong>' + escapeHtml(data.status || data.policy || "Comparable consensus available") + "</div>";
    }
    return table(["Market", "Model", "Consensus", "Gap"], comparisons.slice(0, 12).map(function (row) {
      return "<tr><td><strong>" + escapeHtml(row.label || row.market || row.fixture) + '</strong></td><td class="num">' + pct(row.model_pct) +
        '</td><td class="num">' + pct(row.market_pct || row.consensus_pct) + '</td><td class="num">' + pp(row.gap_pp) + "</td></tr>";
    }));
  }

  function renderSchedule(data) {
    var fixtures = data.fixtures || [];
    if (!fixtures.length) return empty("No remaining schedule is available.");
    return table(["Date", "Opponent", "Venue", "Win", "Expected points", "Difficulty"], fixtures.slice(0, 12).map(function (fixture) {
      return "<tr><td>" + shortDate(fixture.date) + "</td><td><strong>" + escapeHtml(fixture.opponent) + "</strong></td><td>" +
        escapeHtml(fixture.venue) + '</td><td class="num">' + pct(fixture.win_pct) + '</td><td class="num">' +
        number(fixture.expected_points, 2) + '</td><td class="num">' + number(fixture.difficulty, 2) + "</td></tr>";
    }));
  }

  function renderCalendar(data) {
    var entries = data.entries || [];
    if (!entries.length) return empty("No critical dates are currently identified.");
    return '<div class="intel-tape">' + entries.slice(0, 14).map(function (entry) {
      return '<div class="intel-tape-row"><time>' + shortDate(entry.date || entry.effective_at) + '</time><div class="body"><b>' +
        escapeHtml(entry.title || entry.label || entry.kind || "Model checkpoint") + "</b>" +
        (entry.summary ? " · " + escapeHtml(entry.summary) : "") + evidence(entry.evidence_ids) + "</div></div>";
    }).join("") + "</div>";
  }

  function renderConfidence(data) {
    var labels = {
      freshness: "Data freshness",
      source_coverage: "Source coverage",
      historical_calibration: "Historical calibration",
      projection_stability: "Projection stability",
      season_progress: "Season progress",
      scenario_fragility: "Scenario fragility"
    };
    return '<div class="intel-indicators">' + Object.keys(labels).map(function (key) {
      var item = data[key];
      if (item == null) return '<div class="intel-indicator"><span>' + labels[key] + '</span><b>Unavailable</b></div>';
      var status = typeof item === "object" ? item.status : item;
      var detail = "";
      if (typeof item === "object") {
        if (item.age_days != null) detail = item.age_days + " days old";
        else if (item.pct_complete != null) detail = number(item.pct_complete, 0) + "% complete";
        else if (item.top_fixture_range_pp != null) detail = number(item.top_fixture_range_pp, 1) + "pp top range";
        else if (item.recent_max_move_pp != null) detail = number(item.recent_max_move_pp, 1) + "pp recent max";
      }
      return '<div class="intel-indicator"><span>' + labels[key] + '</span><b>' + escapeHtml(status || "Recorded") +
        "</b><small>" + escapeHtml(detail) + "</small></div>";
    }).join("") + "</div>";
  }

  function renderAsk(data) {
    var intents = data.intents || [];
    var buttons = intents.slice(0, 8).map(function (intent) {
      var value = typeof intent === "string" ? intent : intent.intent;
      return '<button class="intel-action" data-action="ask" data-intent="' + attr(value) + '">' +
        escapeHtml(String(value).replace(/_/g, " ")) + "</button>";
    }).join("");
    var answer = "";
    if (state.ask) {
      if (state.ask.status === "unsupported") {
        answer = '<div class="intel-answer">That question is outside the supported calculation set. Try one of the listed intents.</div>';
      } else {
        answer = '<div class="intel-answer"><strong>' + escapeHtml(String(state.ask.intent || "answer").replace(/_/g, " ")) +
          "</strong>" + summarizeObject(state.ask.result) + evidence(state.ask.evidence_ids) + "</div>";
      }
    }
    return '<div class="intel-question-list">' + buttons + "</div>" + answer;
  }

  function summarizeObject(value) {
    if (value == null) return "<p>No supported result is available.</p>";
    if (typeof value !== "object") return "<p>" + escapeHtml(value) + "</p>";
    var pairs = [];
    Object.keys(value).slice(0, 8).forEach(function (key) {
      var item = value[key];
      if (item == null || typeof item === "object") return;
      pairs.push('<div class="intel-claim"><strong>' + escapeHtml(key.replace(/_/g, " ")) + "</strong>" + escapeHtml(item) + "</div>");
    });
    if (!pairs.length && Array.isArray(value)) {
      value.slice(0, 6).forEach(function (item) {
        pairs.push('<div class="intel-claim">' + escapeHtml(item.summary || item.text || JSON.stringify(item)) + "</div>");
      });
    }
    return pairs.join("") || "<p>Structured evidence is recorded for this answer.</p>";
  }

  function renderReceipts(data) {
    var receipts = data.receipts || [];
    if (!receipts.length) return empty("No immutable pre-match receipts have accrued.");
    return table(["Locked", "Fixture", "Forecast", "Outcome", "Snapshot"], receipts.slice(0, 15).map(function (receipt) {
      return "<tr><td>" + shortDate(receipt.locked_at || receipt.date) + "</td><td><strong>" +
        escapeHtml(receipt.fixture || ((receipt.home || "") + " vs " + (receipt.away || ""))) + '</strong></td><td>' +
        escapeHtml(receipt.forecast || receipt.prediction || "Recorded") + "</td><td>" + escapeHtml(receipt.outcome || "Pending") +
        '</td><td class="intel-mono">' + escapeHtml(receipt.snapshot_id || "") + "</td></tr>";
    }));
  }

  function renderComparison(data) {
    var rivals = data.available_rivals || [];
    if (!rivals.length) return empty("No comparable rival is available.");
    var selectedId = state.rivalId || data.recommended_rival_id || rivals[0].team_id;
    var selected = rivals.find(function (rival) { return rival.team_id === selectedId; }) || rivals[0];
    var rivalRecord = state.rivalRecord;
    var teamBrief = state.record.features["1"].data || {};
    var rivalBrief = rivalRecord && rivalRecord.features["1"] && rivalRecord.features["1"].data || {};
    var teamSchedule = state.record.features["13"].data || {};
    var rivalSchedule = rivalRecord && rivalRecord.features["13"] && rivalRecord.features["13"].data || {};
    var teamConfidence = state.record.features["15"].data || {};
    var rivalConfidence = rivalRecord && rivalRecord.features["15"] && rivalRecord.features["15"].data || {};
    var selector = '<div class="intel-form-row"><div class="intel-field"><label for="intel-rival">Comparison club</label><select class="intel-select" id="intel-rival">' +
      rivals.map(function (rival) {
        return '<option value="' + attr(rival.team_id) + '"' + (rival.team_id === selected.team_id ? " selected" : "") + ">" +
          escapeHtml(rival.team) + "</option>";
      }).join("") + "</select></div></div>";
    var rows = [
      ["Target probability", pct(data.team_pct || teamBrief.current_pct), pct(selected.target_pct)],
      ["Projected points", number(teamBrief.projected_points, 1), number(selected.proj_pts || rivalBrief.projected_points, 1)],
      ["Projected rank", number(teamBrief.projected_rank, 1), number(selected.proj_rank || rivalBrief.projected_rank, 1)],
      ["Average remaining xPts", number(teamSchedule.average_expected_points, 2), number(rivalSchedule.average_expected_points, 2)],
      ["Data freshness", teamConfidence.freshness && teamConfidence.freshness.status || "Unavailable",
        rivalConfidence.freshness && rivalConfidence.freshness.status || "Unavailable"],
      ["Scenario fragility", teamConfidence.scenario_fragility && teamConfidence.scenario_fragility.status || "Unavailable",
        rivalConfidence.scenario_fragility && rivalConfidence.scenario_fragility.status || "Unavailable"]
    ];
    var comparison = table(["Metric", state.record.team, selected.team], rows.map(function (row) {
      return "<tr><td><strong>" + escapeHtml(row[0]) + "</strong></td><td>" + escapeHtml(row[1]) + "</td><td>" + escapeHtml(row[2]) + "</td></tr>";
    }));
    var direct = (selected.head_to_heads || []).map(function (fixture) {
      return '<div class="intel-claim"><strong>Direct fixture · ' + shortDate(fixture.date) + "</strong>" +
        escapeHtml(fixture.home + " vs " + fixture.away) + "</div>";
    }).join("");
    var dependency = selected.largest_dependency
      ? '<div class="intel-claim"><strong>Largest external dependency</strong>' +
        escapeHtml(selected.largest_dependency.home + " vs " + selected.largest_dependency.away) +
        " · " + number(selected.largest_dependency.leverage_pp, 1) + "pp range" +
        evidence(selected.largest_dependency.evidence_ids) + "</div>" : "";
    return selector + comparison + direct + dependency;
  }

  function renderCards(data) {
    var templates = data.approved_templates || [];
    return '<div class="intel-tool"><div class="intel-form-row"><div class="intel-field"><label for="intel-card-template">Evidence template</label>' +
      '<select class="intel-select" id="intel-card-template">' + templates.map(function (template) {
        return '<option value="' + attr(template) + '">' + escapeHtml(template.replace(/_/g, " ")) + "</option>";
      }).join("") + '</select></div><button class="intel-action primary" data-action="create-card">Create verified card</button></div>' +
      (state.card ? '<div class="intel-success">Verification URL: <a href="' + attr(state.card.verification_url) + '" target="_blank" rel="noopener">' +
        escapeHtml(state.card.verification_url) + "</a></div>" : "") + "</div>";
  }

  function renderCreator(data) {
    var race = state.record.features["9"] && state.record.features["9"].data || {};
    var rivals = race.rivals || [];
    var cardData = state.record.features["20"] && state.record.features["20"].data || {};
    var templates = cardData.approved_templates || ["highest_leverage"];
    var isCreator = state.me && state.me.plan === "creator";
    var controls = '<div class="intel-form-row"><div class="intel-field"><label for="intel-workspace-name">Workspace</label>' +
      '<input class="intel-input" id="intel-workspace-name" maxlength="80" value="' + attr(state.record.team + " research") + '"></div>' +
      '<div class="intel-field"><label for="intel-creator-rival">Comparison</label><select class="intel-select" id="intel-creator-rival"><option value="">No rival</option>' +
      rivals.map(function (rival) { return '<option value="' + attr(rival.team_id) + '">' + escapeHtml(rival.team) + "</option>"; }).join("") +
      '</select></div><div class="intel-field"><label for="intel-creator-template">Card template</label><select class="intel-select" id="intel-creator-template">' +
      templates.map(function (template) { return '<option value="' + attr(template) + '">' + escapeHtml(template.replace(/_/g, " ")) + "</option>"; }).join("") +
      '</select></div><div class="intel-field"><label for="intel-creator-from">From</label><input class="intel-input" id="intel-creator-from" type="date"></div>' +
      '<div class="intel-field"><label for="intel-creator-to">To</label><input class="intel-input" id="intel-creator-to" type="date"></div></div>';
    var actions = isCreator
      ? '<div class="intel-toolbar-row" style="margin-top:10px"><button class="intel-action primary" data-action="workspace-save">Save workspace</button><span class="spacer"></span>' +
        '<button class="intel-action" data-action="export" data-format="png">PNG</button><button class="intel-action" data-action="export" data-format="csv">CSV</button>' +
        '<button class="intel-action" data-action="export" data-format="json">JSON</button></div>'
      : '<div class="intel-toolbar-row" style="margin-top:10px"><span class="intel-assumption-count">Creator entitlement required</span><span class="spacer"></span>' +
        '<button class="intel-action primary" data-action="checkout" data-plan="creator">Upgrade to Creator</button></div>';
    var saved = (state.workspaces || []).map(function (workspace) {
      return '<div class="intel-journal-entry"><time>' + shortDate(workspace.updated_at) + '</time><div><b>' + escapeHtml(workspace.name) +
        '</b><div class="notes">' + escapeHtml(workspace.card_template || "workspace") + '</div></div><button class="intel-icon-btn" data-action="workspace-delete" data-id="' +
        attr(workspace.workspace_id) + '" title="Delete workspace" aria-label="Delete workspace">×</button></div>';
    }).join("");
    return '<div class="intel-tool">' + controls + actions +
      '<div class="intel-note">Source, generated timestamp, methodology link, snapshot, and citation are embedded in every output.</div></div>' +
      (saved ? '<div class="intel-journal-list">' + saved + "</div>" : "");
  }

  function renderThesis(data) {
    var claims = data.claims || [];
    if (!claims.length) return empty("No versioned team thesis is available.");
    return claims.map(function (claim) {
      return '<div class="intel-claim"><strong>' + escapeHtml(String(claim.kind || "claim").replace(/_/g, " ")) +
        "</strong>" + escapeHtml(claim.text) + evidence(claim.evidence_ids) + "</div>";
    }).join("") + '<div class="intel-note">Thesis ' + escapeHtml(data.thesis_id) + " · " + escapeHtml(data.change_reason || "current version") + "</div>";
  }

  function renderWatchpoints(data) {
    var rows = data.watchpoints || [];
    if (!rows.length) return empty("No single result currently clears the materiality threshold.");
    return '<div class="intel-tape">' + rows.map(function (watch) {
      return '<div class="intel-tape-row"><time>' + shortDate(watch.date) + '</time><div class="body"><b>' +
        escapeHtml(watch.summary) + "</b>" + evidence(watch.evidence_ids) + '</div><span class="intel-move' +
        (Number(watch.move_pp) > 0 ? " up" : " down") + '">' + pp(watch.move_pp) + "</span></div>";
    }).join("") + "</div>";
  }

  function renderAnalogs(data) {
    var rows = data.analogs || data.baselines || [];
    if (!rows.length) return empty("Historical analogs need additional seasons at the same checkpoint.");
    return table(["Season or club", "Checkpoint", "Similarity", "Outcome"], rows.slice(0, 12).map(function (row) {
      return "<tr><td><strong>" + escapeHtml(row.team || row.season || row.label) + "</strong></td><td>" +
        escapeHtml(row.checkpoint || row.date || "") + '</td><td class="num">' + escapeHtml(row.similarity || row.distance || "") +
        "</td><td>" + escapeHtml(row.outcome || row.finish || "") + "</td></tr>";
    }));
  }

  function renderQuietMode(data) {
    var composition = data.composition || {};
    var items = Object.keys(composition).map(function (key) {
      var value = composition[key];
      var summary = "Recorded";
      if (value == null) summary = "Unavailable";
      else if (Array.isArray(value)) summary = value.length + " active item" + (value.length === 1 ? "" : "s");
      else if (typeof value !== "object") summary = String(value);
      else if (value.text) summary = value.text;
      else if (value.summary) summary = value.summary;
      else if (value.remaining_count != null) summary = value.remaining_count + " fixtures remaining";
      else if (value.claims) summary = value.claims.length + " versioned thesis claims";
      else if (value.rivals) summary = value.rivals.length + " modeled rivals";
      return {label: key, summary: summary};
    });
    return '<div class="intel-brief"><div class="intel-primary-metric"><div class="label">Calendar mode</div><div class="value" style="font-size:22px">' +
      escapeHtml(modeLabel(data.calendar_mode && data.calendar_mode.mode || data.calendar_mode)) + '</div><div class="delta">Evidence-led cadence</div></div><div>' +
      items.map(function (item) {
        return '<div class="intel-claim"><strong>' + escapeHtml(item.label.replace(/_/g, " ")) +
          "</strong>" + escapeHtml(item.summary) + "</div>";
      }).join("") + "</div></div>";
  }

  function renderJournal() {
    var current = state.record.features["1"].data;
    return '<div class="intel-tool"><div class="intel-form-row"><div class="intel-field"><label for="intel-journal-pct">Your probability</label>' +
      '<input class="intel-input" id="intel-journal-pct" type="number" min="0" max="100" step="0.1" value="' + attr(current.current_pct) + '"></div>' +
      '<div class="intel-field"><label for="intel-journal-confidence">Confidence</label><select class="intel-select" id="intel-journal-confidence">' +
      '<option value="low">Low</option><option value="medium" selected>Medium</option><option value="high">High</option></select></div>' +
      '<div class="intel-field"><label for="intel-journal-notes">Private note</label><input class="intel-input" id="intel-journal-notes" maxlength="500"></div>' +
      '<button class="intel-action primary" data-action="journal-save">Lock checkpoint</button></div></div>' +
      '<div class="intel-journal-list">' + state.journal.filter(function (entry) {
        return entry.league_id === state.leagueId && entry.team_id === state.teamId;
      }).slice().reverse().map(function (entry) {
        return '<div class="intel-journal-entry"><time>' + shortDate(entry.created_at) + '</time><div><b>' +
          pct(entry.target_probability) + " · " + escapeHtml(entry.confidence) + '</b><div class="notes">' +
          escapeHtml(entry.private_notes || "") + '</div></div><button class="intel-icon-btn" data-action="journal-delete" data-id="' +
          attr(entry.journal_entry_id) + '" title="Delete checkpoint" aria-label="Delete checkpoint">×</button></div>';
      }).join("") + "</div>";
  }

  function renderFeature(id, data) {
    if (id === 1) return renderBrief(data);
    if (id === 2) return renderEvents(data, false);
    if (id === 3) return renderEvents(data, true);
    if (id === 4) return renderLeverage(data);
    if (id === 5) return scenarioControls(data);
    if (id === 6) return renderPaths(data);
    if (id === 7) return renderAlerts(data);
    if (id === 8) return renderBriefing(data);
    if (id === 9) return renderRace(data);
    if (id === 10) return renderExpectation(data);
    if (id === 11) return renderTimeMachine(data);
    if (id === 12) return renderConsensus(data);
    if (id === 13) return renderSchedule(data);
    if (id === 14) return renderCalendar(data);
    if (id === 15) return renderConfidence(data);
    if (id === 16) return renderAsk(data);
    if (id === 17) return renderEvents(data, false);
    if (id === 18) return renderReceipts(data);
    if (id === 19) return renderComparison(data);
    if (id === 20) return renderCards(data);
    if (id === 21) return renderCreator(data);
    if (id === 22) return renderThesis(data);
    if (id === 23) return renderWatchpoints(data);
    if (id === 24) return renderAnalogs(data);
    if (id === 25) return renderQuietMode(data);
    if (id === 26) return renderJournal(data);
    return empty("Feature renderer unavailable.");
  }

  function trustTape() {
    var brief = state.record.features["1"].data || {};
    var why = state.record.features["3"].data || {};
    var events = why.events || [];
    var driver = events[0] || brief.largest_driver;
    var next = brief.next_high_impact_fixture;
    var changeValue = brief.seven_day_change_pp == null ? "Baseline established" : pp(brief.seven_day_change_pp);
    var causeValue = driver ? (driver.summary || driver.event_type || driver.kind || "Evidence recorded") : "No material move";
    var nextValue = next ? next.home + " vs " + next.away : "No fixture signal";
    return '<div class="intel-trust-tape">' +
      tapeStep("Change", changeValue, state.record.target_metric.replace(/_/g, " ")) +
      tapeStep("Cause / evidence", causeValue, driver && driver.cause_class || "supported record") +
      tapeStep("Next", nextValue, next ? shortDate(next.date) + " · " + number(next.leverage_pp, 1) + "pp range" : "quiet state") +
      tapeStep("Receipt", state.record.snapshot_id, state.record.generated) + "</div>";
  }

  function tapeStep(label, value, detail) {
    return '<div class="intel-tape-step"><span>' + escapeHtml(label) + "</span><b>" + escapeHtml(value) + "</b><small>" +
      escapeHtml(detail) + "</small></div>";
  }

  function mergeBanner() {
    var favorites = favoriteCandidates();
    var known = {};
    (state.prefs.teams || []).forEach(function (entry) { known[entry.team_id] = true; });
    var missing = favorites.filter(function (entry) { return !known[entry.team_id]; });
    if (!missing.length) return "";
    return '<div class="intel-success">' + missing.length + ' followed team' + (missing.length === 1 ? "" : "s") +
      ' found on this device. <button class="intel-action" data-action="merge-favorites">Import</button></div>';
  }

  function hubView() {
    var selection = findSelection(state.leagueId, state.teamId);
    var mode = state.record.calendar_mode || {};
    var features = TABS[state.tab].map(function (id) { return state.record.features[String(id)]; }).filter(Boolean);
    document.title = state.record.team + " Intelligence · Entenser";
    root.classList.remove("hidden");
    root.innerHTML = '<div class="ed-wrap intel-app">' +
      commandHeader(state.record.team + " Intelligence", state.record.league_name + " · " + modeLabel(mode.mode) + " · snapshot " + state.record.generated) +
      mergeBanner() +
      (state.notice ? '<div class="intel-success">' + escapeHtml(state.notice) + "</div>" : "") +
      (state.error ? '<div class="intel-error">' + escapeHtml(state.error) + "</div>" : "") +
      '<div class="intel-toolbar"><div class="intel-toolbar-main"><div class="intel-field"><label for="intel-team">Team</label>' +
      '<select class="intel-team-select" id="intel-team">' + teamOptions() + '</select></div></div><div class="intel-toolbar-meta"><b>' +
      escapeHtml(selection ? selection.league.league : state.record.league_name) + '</b><span class="intel-mode ' +
      attr(mode.mode || "") + '">' + escapeHtml(modeLabel(mode.mode)) + "</span></div></div>" +
      '<nav class="intel-tabs" aria-label="Intelligence views">' +
      Object.keys(TABS).map(function (tab) {
        return '<button class="intel-tab' + (tab === state.tab ? " on" : "") + '" data-action="tab" data-tab="' + tab + '">' +
          escapeHtml(tab.charAt(0).toUpperCase() + tab.slice(1)) + "</button>";
      }).join("") + "</nav>" + trustTape() +
      '<main id="intel-feature-list">' + features.map(featureShell).join("") + "</main></div>";
  }

  async function loadTeam(leagueId, teamId) {
    state.busy = true;
    state.error = "";
    loading("Loading team intelligence");
    try {
      var record = await api("/intel/team?league_id=" + encodeURIComponent(leagueId) + "&team_id=" + encodeURIComponent(teamId));
      state.record = record;
      state.leagueId = leagueId;
      state.teamId = teamId;
      var linkedTarget = params.get("target");
      var availableTargets = Object.keys(record.features["5"] && record.features["5"].data.baseline || {});
      state.selectedTarget = availableTargets.indexOf(linkedTarget) >= 0 ? linkedTarget : pinnedTarget() || record.target_metric;
      state.assumptions = {};
      state.assumptionHistory = [{}];
      state.assumptionCursor = 0;
      state.scenario = null;
      state.ask = null;
      var comparisonData = record.features["19"] && record.features["19"].data || {};
      var linkedRival = params.get("rival");
      var availableRivalIds = (comparisonData.available_rivals || []).map(function (row) { return row.team_id; });
      var rivalId = availableRivalIds.indexOf(linkedRival) >= 0 ? linkedRival : comparisonData.recommended_rival_id;
      await loadRival(rivalId);
      persistDeepLink();
      localStorage.setItem(LAST_TEAM_KEY, JSON.stringify({league_id: leagueId, team_id: teamId, team: record.team}));
      analytics("hub_activation", {league_id: leagueId, calendar_mode: record.calendar_mode.mode});
      await loadJournal();
      hubView();
      markEventsSeen();
    } catch (error) {
      setMessage(error.message, true);
      if (error.status === 401) {
        localStorage.removeItem(ACCESS_KEY);
        signInView();
      } else {
        root.innerHTML = '<div class="ed-wrap intel-app">' + commandHeader("Intelligence Hub", "Team data unavailable") +
          '<div class="intel-error">' + escapeHtml(error.message) + '</div><button class="intel-action" data-action="refresh">Retry</button></div>';
      }
    } finally {
      state.busy = false;
    }
  }

  function pinnedTarget() {
    var targets = state.prefs.targets || [];
    var row = targets.find(function (entry) {
      return entry.league_id === state.leagueId && entry.team_id === state.teamId;
    });
    return row && row.target_metric;
  }

  async function markEventsSeen() {
    var eventsFeature = state.record.features["2"];
    var events = eventsFeature && eventsFeature.data && eventsFeature.data.events;
    if (!events || !events.length) return;
    try {
      await api("/intel/events", {
        method: "POST",
        body: JSON.stringify({team_id: state.teamId, event_id: events[0].event_id})
      });
    } catch (error) {}
  }

  async function loadWorkspaces() {
    if (!state.me || state.me.plan !== "creator") { state.workspaces = []; return; }
    try {
      var data = await api("/intel/workspaces");
      state.workspaces = data.workspaces || [];
    } catch (error) {
      state.workspaces = [];
    }
  }

  async function loadRival(teamId) {
    state.rivalId = teamId || "";
    state.rivalRecord = null;
    if (!teamId) return;
    try {
      state.rivalRecord = await api("/intel/team?league_id=" + encodeURIComponent(state.leagueId) + "&team_id=" + encodeURIComponent(teamId));
    } catch (error) {
      state.rivalRecord = null;
    }
  }

  function persistDeepLink() {
    params.set("league", "intel");
    params.set("intelLeague", state.leagueId);
    params.set("team", state.teamId);
    if (state.rivalId) params.set("rival", state.rivalId); else params.delete("rival");
    params.set("target", state.selectedTarget || state.record.target_metric);
    params.set("snapshot", state.record.snapshot_id);
    history.replaceState(null, "", location.pathname + "?" + params.toString() + location.hash);
  }

  async function loadJournal() {
    try {
      var data = await api("/intel/journal");
      state.journal = data.entries || [];
    } catch (error) {
      state.journal = [];
    }
  }

  function pushAssumptions(next) {
    state.assumptionHistory = state.assumptionHistory.slice(0, state.assumptionCursor + 1);
    state.assumptionHistory.push(Object.assign({}, next));
    state.assumptionCursor += 1;
    state.assumptions = Object.assign({}, next);
    state.scenario = null;
    hubView();
  }

  async function initialize() {
    loading("Opening private workspace");
    var magicToken = params.get("token");
    if (magicToken) {
      try {
        var pair = await api("/auth/callback?token=" + encodeURIComponent(magicToken));
        localStorage.setItem(ACCESS_KEY, pair.access_token);
        localStorage.setItem(REFRESH_KEY, pair.refresh_token);
        params.delete("token");
        history.replaceState(null, "", location.pathname + "?" + params.toString() + location.hash);
      } catch (error) {
        setMessage(error.message, true);
      }
    }
    var claims = tokenClaims();
    if (!claims || claims.exp * 1000 <= Date.now()) {
      if (!await refreshAccess()) {
        signInView();
        return;
      }
    }
    try {
      state.me = await api("/intel/me");
      state.prefs = await api("/intel/preferences");
    } catch (error) {
      setMessage(error.message, true);
      signInView();
      return;
    }
    if (["trial", "intel", "creator"].indexOf(state.me.plan) < 0) {
      freeView();
      return;
    }
    await loadWorkspaces();
    var selection = defaultSelection();
    if (!selection) {
      root.innerHTML = '<div class="ed-wrap intel-app">' + commandHeader("Intelligence Hub", "No forecast competitions are available") +
        empty("The team catalog did not contain a live forecast route.") + "</div>";
      return;
    }
    await loadTeam(selection.league.league_id, selection.team.team_id);
  }

  root.addEventListener("submit", async function (event) {
    if (event.target.id !== "intel-signin") return;
    event.preventDefault();
    var email = document.getElementById("intel-email").value.trim();
    try {
      await api("/auth/request", {method: "POST", body: JSON.stringify({email: email})});
      setMessage("Check your email for the secure sign-in link.", false);
    } catch (error) {
      setMessage(error.message, true);
    }
    signInView();
  });

  root.addEventListener("change", async function (event) {
    if (event.target.id === "intel-team") {
      var parts = event.target.value.split("|");
      await loadTeam(parts[0], parts[1]);
    }
    if (event.target.id === "intel-target") {
      state.selectedTarget = event.target.value;
      var targets = (state.prefs.targets || []).filter(function (entry) {
        return !(entry.league_id === state.leagueId && entry.team_id === state.teamId);
      });
      targets.push({league_id: state.leagueId, team_id: state.teamId, target_metric: state.selectedTarget});
      try {
        state.prefs = await api("/intel/preferences", {method: "PATCH", body: JSON.stringify({targets: targets})});
        setMessage("Pinned target saved.", false);
      } catch (error) {
        setMessage(error.message, true);
      }
      persistDeepLink();
      hubView();
    }
    if (event.target.id === "intel-rival") {
      await loadRival(event.target.value);
      persistDeepLink();
      hubView();
    }
  });

  root.addEventListener("click", async function (event) {
    var button = event.target.closest("[data-action]");
    if (!button || state.busy) return;
    var action = button.getAttribute("data-action");
    state.notice = "";
    state.error = "";

    try {
      if (action === "tab") {
        state.tab = button.getAttribute("data-tab");
        hubView();

      } else if (action === "refresh") {
        if (state.record) await loadTeam(state.leagueId, state.teamId);
        else await initialize();
      } else if (action === "logout") {
        var refresh = localStorage.getItem(REFRESH_KEY);
        if (refresh) await api("/auth/logout", {method: "POST", body: JSON.stringify({refresh_token: refresh})});
        localStorage.removeItem(ACCESS_KEY);
        localStorage.removeItem(REFRESH_KEY);
        state.me = null;
        signInView();
      } else if (action === "checkout") {
        var checkout = await api("/billing/checkout", {method: "POST", body: JSON.stringify({plan: button.getAttribute("data-plan") || "intel"})});
        location.assign(checkout.url);
      } else if (action === "merge-favorites") {
        var teams = (state.prefs.teams || []).slice();
        var known = {};
        teams.forEach(function (entry) { known[entry.team_id] = true; });
        favoriteCandidates().forEach(function (entry) { if (!known[entry.team_id]) teams.push(entry); });
        state.prefs = await api("/intel/preferences", {method: "PATCH", body: JSON.stringify({teams: teams})});
        setMessage("Followed teams imported.", false);
        hubView();
      } else if (action === "assume") {
        var assumptions = Object.assign({}, state.assumptions);
        var fixture = button.getAttribute("data-fixture");
        var outcome = button.getAttribute("data-outcome");
        if (assumptions[fixture] === outcome) delete assumptions[fixture];
        else assumptions[fixture] = outcome;
        pushAssumptions(assumptions);
      } else if (action === "scenario-undo" && state.assumptionCursor > 0) {
        state.assumptionCursor -= 1;
        state.assumptions = Object.assign({}, state.assumptionHistory[state.assumptionCursor]);
        state.scenario = null;
        hubView();
      } else if (action === "scenario-redo" && state.assumptionCursor < state.assumptionHistory.length - 1) {
        state.assumptionCursor += 1;
        state.assumptions = Object.assign({}, state.assumptionHistory[state.assumptionCursor]);
        state.scenario = null;
        hubView();
      } else if (action === "scenario-reset") {
        pushAssumptions({});
      } else if (action === "scenario-run" || action === "scenario-save") {
        state.busy = true;
        state.scenario = await api("/intel/scenario", {
          method: "POST",
          body: JSON.stringify({
            league_id: state.leagueId,
            team_id: state.teamId,
            snapshot_id: state.record.snapshot_id,
            target_metric: state.selectedTarget,
            assumptions: state.assumptions,
            save: action === "scenario-save"
          })
        });
        state.busy = false;
        setMessage(action === "scenario-save" ? "Scenario receipt saved." : "Scenario complete.", false);
        analytics("scenario_completed", {league_id: state.leagueId, surface: "hub"});
        hubView();
      } else if (action === "save-alerts") {
        var notifications = Object.assign({}, state.prefs.notifications || {}, {
          material_change: document.getElementById("intel-material-alert").checked,
          weekly: document.getElementById("intel-weekly-alert").checked
        });
        state.prefs = await api("/intel/preferences", {
          method: "PATCH",
          body: JSON.stringify({threshold_pp: Number(document.getElementById("intel-threshold").value), notifications: notifications})
        });
        setMessage("Delivery rules saved.", false);
        hubView();
      } else if (action === "ask") {
        state.busy = true;
        state.ask = await api("/intel/ask", {
          method: "POST",
          body: JSON.stringify({league_id: state.leagueId, team_id: state.teamId, intent: button.getAttribute("data-intent")})
        });
        state.busy = false;

        hubView();
      } else if (action === "create-card") {
        state.card = await api("/intel/cards", {
          method: "POST",
          body: JSON.stringify({league_id: state.leagueId, team_id: state.teamId, template: document.getElementById("intel-card-template").value})
        });
        analytics("card_created", {league_id: state.leagueId, surface: "hub"});
        hubView();
      } else if (action === "export") {
        var format = button.getAttribute("data-format");
        var templateSelect = document.getElementById("intel-creator-template");
        var template = templateSelect ? templateSelect.value : "highest_leverage";
        var response = await fetch(API_BASE + "/intel/export?league_id=" + encodeURIComponent(state.leagueId) +
          "&team_id=" + encodeURIComponent(state.teamId) + "&format=" + encodeURIComponent(format) +
          "&template=" + encodeURIComponent(template), {headers: authHeaders()});
        if (!response.ok) {
          var exportError = await response.json();
          throw new Error(exportError.error || "Export failed");
        }
        var blob = await response.blob();
        var url = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = state.record.team.toLowerCase().replace(/[^a-z0-9]+/g, "-") + "-intelligence." + format;
        link.click();
        URL.revokeObjectURL(url);
        analytics("creator_exported", {surface: format, league_id: state.leagueId});
      } else if (action === "workspace-save") {
        var workspace = await api("/intel/workspaces", {
          method: "POST",
          body: JSON.stringify({
            name: document.getElementById("intel-workspace-name").value,
            league_id: state.leagueId, team_id: state.teamId,
            target_metric: state.selectedTarget,
            rival_team_id: document.getElementById("intel-creator-rival").value || null,
            date_from: document.getElementById("intel-creator-from").value || null,
            date_to: document.getElementById("intel-creator-to").value || null,
            card_template: document.getElementById("intel-creator-template").value
          })
        });
        state.workspaces = state.workspaces.filter(function (row) { return row.workspace_id !== workspace.workspace_id; });
        state.workspaces.push(workspace);
        setMessage("Creator workspace saved.", false);
        hubView();
      } else if (action === "workspace-delete") {
        await api("/intel/workspaces?workspace_id=" + encodeURIComponent(button.getAttribute("data-id")), {method: "DELETE"});
        state.workspaces = state.workspaces.filter(function (row) { return row.workspace_id !== button.getAttribute("data-id"); });
        setMessage("Creator workspace deleted.", false);
        hubView();
      } else if (action === "journal-save") {
        var entry = await api("/intel/journal", {
          method: "POST",
          body: JSON.stringify({
            league_id: state.leagueId,
            team_id: state.teamId,
            season_id: state.record.season_id,
            target_metric: state.selectedTarget,
            target_probability: Number(document.getElementById("intel-journal-pct").value),
            predicted_finish: state.record.features["1"].data.projected_rank,
            confidence: document.getElementById("intel-journal-confidence").value,
            private_notes: document.getElementById("intel-journal-notes").value,
            model_snapshot_id: state.record.snapshot_id
          })
        });
        state.journal.push(entry);
        setMessage("Private forecast checkpoint locked.", false);
        hubView();
      } else if (action === "journal-delete") {
        await api("/intel/journal?journal_entry_id=" + encodeURIComponent(button.getAttribute("data-id")), {method: "DELETE"});
        state.journal = state.journal.filter(function (entry) { return entry.journal_entry_id !== button.getAttribute("data-id"); });
        setMessage("Checkpoint deleted.", false);
        hubView();
      }
    } catch (error) {
      state.busy = false;
      setMessage(error.message, true);
      if (state.record) hubView();
      else if (state.me && state.me.plan === "free") freeView();
      else signInView();
    }
  });

  initialize();
})();
