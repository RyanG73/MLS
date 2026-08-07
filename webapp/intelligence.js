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
    selectedTarget: "",
    historyTarget: "",
    pricing: {},
    checkout: {enabled: false},
    interval: "annual",
    sample: null,
    upgradeTracked: false,
    valueEvents: {}
  };

  // Price quoted to the customer comes from Stripe's own Price object via
  // /public/config, for the tier the server currently has active -- never
  // guessed from navigator.language, which is how a site ends up displaying
  // euros while charging dollars, and never hardcoded, which is how a price
  // lift silently starts lying. If Stripe is unreachable we say nothing rather
  // than quote a number we might not bill.
  function priceRecord(interval) {
    var key = interval === "annual" ? "intel_annual" : "intel";
    return (state.pricing && state.pricing[key]) || null;
  }

  function hasInterval(interval) {
    return !!priceRecord(interval);
  }

  function planPrice(interval) {
    var record = priceRecord(interval);
    return record && record.display ? record.display : "";
  }

  // Stripe reports "month"/"year"; the copy around the button reads better as
  // the same word the customer just clicked.
  function intervalWord(interval) {
    var record = priceRecord(interval);
    if (record && record.interval) return record.interval;
    return interval === "annual" ? "year" : "month";
  }

  function priceSentence(interval) {
    var price = planPrice(interval);
    return price
      ? price + " per " + intervalWord(interval) + "."
      : "Checkout is unavailable until a verified price can be shown here.";
  }

  function subscribeLabel(interval) {
    var price = planPrice(interval);
    return price ? "Continue with Club Watch — " + price + " / " + intervalWord(interval) : "Checkout unavailable";
  }

  // Annual is preselected deliberately (roadmap §0b, hard annual push). It is
  // also what protects the launch cohort from the archive's thinnest weeks: an
  // annual subscriber does not re-evaluate a six-week vault every 30 days.
  // Rendered only when both intervals actually have a Stripe Price, so a
  // half-configured environment shows one honest option rather than a broken
  // choice.
  function intervalChooserHTML() {
    if (!hasInterval("annual") || !hasInterval("monthly")) return "";
    return '<div class="intel-interval" role="radiogroup" aria-label="Billing period">' +
      ["annual", "monthly"].map(function (option) {
        var on = state.interval === option;
        return '<button type="button" class="intel-action' + (on ? " primary" : "") +
          '" role="radio" aria-checked="' + (on ? "true" : "false") +
          '" data-action="set-interval" data-interval="' + option + '">' +
          escapeHtml(option === "annual" ? "Annual" : "Monthly") +
          ' · ' + escapeHtml(planPrice(option)) + "</button>";
      }).join(" ") + "</div>";
  }

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
    if (params.get("intelLeague") && params.get("teamName")) candidates.push({
      league_id: params.get("intelLeague"), team: params.get("teamName")
    });
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
    document.title = "Club Watch · Entenser";
    root.classList.remove("hidden");
    root.innerHTML = '<div class="ed-wrap intel-app">' +
      '<header class="intel-command"><div class="intel-command-copy">' +
      '<div class="intel-eyebrow">Your club, kept current</div><h1>Club Watch</h1>' +
      '<p>See what changed, why it matters, and what comes next without rechecking every forecast.</p></div></header>' +
      '<section class="intel-auth" id="intel-auth"><h2>Save one club and get a complete sample</h2>' +
      '<p>One secure email link signs you in or creates your free account. No password is stored.</p>' +
      '<form id="intel-signin" class="intel-form-row"><div class="intel-field"><label for="intel-email">Email</label>' +
      '<input class="intel-input" id="intel-email" type="email" autocomplete="email" required></div>' +
      '<button class="intel-action primary" type="submit">Email my secure link</button></form>' +
      (state.notice ? '<div class="intel-success">' + escapeHtml(state.notice) + "</div>" : "") +
      (state.error ? '<div class="intel-error">' + escapeHtml(state.error) + "</div>" : "") +
      '<div class="intel-note">The link expires in 15 minutes and can be used once.</div></section>' +
      lockedPreviewHTML() + "</div>";
  }

  // ── Signed-out teaser ──────────────────────────────────────────────────────
  // Rewritten 2026-08-01. The old version sold the product as ten internal
  // codenames in a chip list — "Scenario studio", "Paths to the target",
  // "Confidence panel" — against a mockup starring "Rival A" and "Home vs
  // Rival B", with `snap_0718_a3 · fix_88121` printed under the heading
  // "Evidence". Every one of those names is a label we invented; a supporter
  // has no way to know what any of them does, which is exactly the reported
  // problem. "Scenario studio" appeared in precisely one place in the whole
  // repository: that chip.
  //
  // The software behind it is real (intelligence_service.run_scenario runs a
  // seeded 2,000-sim replay against a pinned snapshot and returns the club AND
  // its three nearest rivals), so the fix is not to build mockups — it is to
  // stop naming working features after their implementation. Every heading is
  // now a sentence a supporter would say out loud, every placeholder club is a
  // real club, and the strongest single line is the one that tells the reader
  // they have already used this: Next 5 Sim is free on every league table and
  // is the same engine. Converting an unfamiliar noun into a thing they have
  // already done beats any amount of feature copy.
  //
  // Numbers stay illustrative and stay labelled — see demoClub() on why the
  // CLUB is real but the figures are not.

  // The club the teaser stars in. defaultSelection() already resolves a pinned
  // favourite, the last club viewed, or a URL param before falling back, so a
  // visitor who has starred anyone on the site sees THEIR club named here.
  // Rivals are drawn from the same league so the example reads as football
  // rather than as "Rival A". The figures remain sample data — the continuity
  // features are account-bound by definition, so there is no real number to
  // show a signed-out reader, and every card says so.
  // Leagues and clubs a cold visitor will recognise, for when there is no
  // personal signal to use. NOT defaultSelection()'s own fallback, which is
  // catalogLeagues()[0] — that sorts alphabetically and opened the teaser with
  // "This is what Club Watch keeps for Acassuso", a second-tier Argentine club.
  var TEASER_LEAGUES = ["epl", "la-liga", "serie-a", "bundesliga", "mls", "liga-mx"];
  var TEASER_CLUBS = ["Arsenal", "Manchester City", "Liverpool", "Real Madrid",
    "Barcelona", "Inter", "Bayern Munich", "Inter Miami CF", "LA Galaxy"];

  function teaserFallback() {
    var leagues = catalogLeagues();
    if (!leagues.length) return null;
    for (var i = 0; i < TEASER_LEAGUES.length; i += 1) {
      var league = leagues.find(function (entry) { return entry.league_id === TEASER_LEAGUES[i]; });
      if (!league) continue;
      var team = null;
      for (var j = 0; j < TEASER_CLUBS.length && !team; j += 1) {
        team = league.teams.find(function (entry) { return entry.team === TEASER_CLUBS[j]; });
      }
      return {league: league, team: team || league.teams[0]};
    }
    return {league: leagues[0], team: leagues[0].teams[0]};
  }

  // A club the visitor has actually signalled — URL param, last club viewed, or
  // a star they placed anywhere on the site. Only these count as personal;
  // anything else falls through to a recognisable name.
  function teaserSignal() {
    var candidates = [];
    if (params.get("intelLeague") && params.get("teamName")) {
      candidates.push({league_id: params.get("intelLeague"), team: params.get("teamName")});
    }
    try {
      var stored = JSON.parse(localStorage.getItem(LAST_TEAM_KEY) || "null");
      if (stored) candidates.push(stored);
    } catch (error) { /* private mode — no signal, not an error */ }
    favoriteCandidates().forEach(function (entry) { candidates.push(entry); });
    for (var i = 0; i < candidates.length; i += 1) {
      var c = candidates[i];
      var hit = c.league && c.team ? {league: c.league, team: c.team}
        : findSelection(c.league_id || c.league, c.team_id);
      if (hit && hit.league && hit.team) return hit;
    }
    return null;
  }

  function demoClub() {
    var picked = teaserSignal() || teaserFallback();
    if (!picked || !picked.team) return null;
    // Rivals come from the recognisable list first. Taking the league's first
    // two clubs alphabetically made Arsenal's title rivals "Aston Villa" and
    // "Bournemouth", which reads as a bug to anyone who follows the league.
    var others = (picked.league.teams || []).filter(function (entry) {
      return entry.team !== picked.team.team;
    });
    var known = others.filter(function (entry) { return TEASER_CLUBS.indexOf(entry.team) >= 0; });
    var rivals = known.concat(others);
    return {
      club: picked.team.team,
      league: picked.league.league || picked.league.league_id,
      rivalA: (rivals[0] || {}).team || "the league leaders",
      rivalB: (rivals[1] || {}).team || "the chasing pack"
    };
  }

  function lockedPreviewHTML() {
    var d = demoClub();
    if (!d) d = {club: "your club", league: "your league", rivalA: "the league leaders", rivalB: "the chasing pack"};
    var club = escapeHtml(d.club), rivalA = escapeHtml(d.rivalA), rivalB = escapeHtml(d.rivalB);

    // "Studio" told the reader nothing. Every tab now names its question.
    var tabs = '<nav class="intel-tabs">' + ["Today", "Who you're racing", "The season so far", "What-ifs"].map(function (tab, index) {
      return '<button class="intel-tab' + (index === 0 ? " on" : "") + '" type="button" tabindex="-1">' + tab + "</button>";
    }).join("") + "</nav>";
    // The fourth step used to print a snapshot id (`snap_0718_a3`) under the
    // heading "Receipt". An internal key is not a receipt to anyone outside
    // this repo; what the reader wants to know is that the old number was kept.
    var trust = '<div class="intel-trust-tape">' +
      '<div class="intel-tape-step"><span>What moved</span><b>+4.2 points</b><small>title odds, last 7 days</small></div>' +
      '<div class="intel-tape-step"><span>Why</span><b>Two straight wins</b><small>and ' + rivalA + ' dropped points</small></div>' +
      '<div class="intel-tape-step"><span>What is next</span><b>' + club + ' v ' + rivalA + '</b><small>the biggest swing left this month</small></div>' +
      '<div class="intel-tape-step"><span>Kept on record</span><b>Every number, dated</b><small>so you can check what we said</small></div></div>';
    var brief = '<section class="intel-feature"><div class="intel-feature-head">' +
      '<div class="intel-feature-title"><h2>Where ' + club + ' stands today</h2></div>' +
      '<span class="intel-state live">sample</span></div>' +
      '<div class="intel-brief"><div class="intel-primary-metric"><div class="label">Title</div>' +
      '<div class="value">63.8%</div><div class="delta up">+4.2 in 7 days</div></div>' +
      '<div><p class="intel-brief-summary">' + club + ' are climbing after back-to-back wins. The largest single swing left in the season is the home match with ' + rivalA + ' — one result there is worth more than the next month combined.</p>' +
      '<div class="intel-facts">' +
      '<div class="intel-fact"><span>Projected points</span><b>52.4</b></div>' +
      '<div class="intel-fact"><span>Projected finish</span><b>4th</b></div>' +
      '<div class="intel-fact"><span>Next match is worth</span><b>6.1 points of odds</b></div>' +
      '<div class="intel-fact"><span>Last checked</span><b>Today</b></div></div></div></div></section>';
    var tape = '<section class="intel-feature"><div class="intel-feature-head">' +
      '<div class="intel-feature-title"><h2>What changed since you last looked</h2></div>' +
      '<span class="intel-state live">sample</span></div><div class="intel-tape">' +
      '<div class="intel-tape-row"><time>Jul 18</time><div class="body"><b>' + club + ' won away</b> · the result beat what we expected</div><span class="intel-move up">+2.9</span></div>' +
      '<div class="intel-tape-row"><time>Jul 15</time><div class="body"><b>Fixture pile-up eased</b> · a midweek game was moved</div><span class="intel-move up">+1.3</span></div>' +
      '<div class="intel-tape-row"><time>Jul 12</time><div class="body"><b>' + rivalA + ' won late</b> · a direct rival gained ground</div><span class="intel-move down">-0.8</span></div>' +
      "</div></section>";
    var leverage = '<section class="intel-feature"><div class="intel-feature-head">' +
      '<div class="intel-feature-title"><h2>Which matches actually matter</h2></div>' +
      '<span class="intel-state live">sample</span></div>' +
      '<p class="intel-brief-summary">Including the ones ' + club + ' are not playing in.</p>' +
      '<div class="intel-table-scroll"><table class="intel-data-table"><thead><tr>' +
      "<th>Date</th><th>Match</th><th>Why it counts</th><th>Odds at stake</th></tr></thead><tbody>" +
      '<tr><td>Jul 26</td><td><strong>' + club + ' v ' + rivalA + '</strong></td><td>Your match, and the biggest one left</td><td class="num">6.1</td></tr>' +
      '<tr><td>Aug 2</td><td><strong>' + rivalA + ' v ' + rivalB + '</strong></td><td>Two rivals must drop points somewhere</td><td class="num">3.4</td></tr>' +
      '<tr><td>Aug 9</td><td><strong>' + rivalB + ' v ' + club + '</strong></td><td>Your match</td><td class="num">5.2</td></tr>' +
      "</tbody></table></div></section>";

    // Replaces the ten-codename chip list. Each block leads with the sentence a
    // supporter would say, and the first one anchors to Next 5 Sim — a tool
    // already free on every league table, so the reader learns they have used
    // this before rather than meeting a new noun.
    var more = '<div class="intel-locked-more">' +
      '<div class="intel-eyebrow">Also inside</div>' +

      '<div class="intel-example"><h3>Save your what-ifs</h3>' +
      '<p>You have already used <b>Next 5 Sim</b> on the league table — force a result, watch the table resimulate. This is that, kept. Force ' + club + ' to beat ' + rivalA + ', save it, and every real result updates the saved scenario. Your nearest rivals move with it.</p>' +
      '<div class="intel-table-scroll"><table class="intel-data-table"><thead><tr>' +
      "<th>Title odds</th><th>Now</th><th>If " + club + " win</th></tr></thead><tbody>" +
      '<tr><td><strong>' + club + '</strong></td><td class="num">63.8%</td><td class="num">71.2%</td></tr>' +
      '<tr><td>' + rivalA + '</td><td class="num">24.1%</td><td class="num">18.4%</td></tr>' +
      '<tr><td>' + rivalB + '</td><td class="num">9.0%</td><td class="num">8.1%</td></tr>' +
      "</tbody></table></div></div>" +

      '<div class="intel-example"><h3>What still has to happen</h3>' +
      '<p>The shortest routes left to the target, ranked by how likely each one is.</p>' +
      '<ul class="intel-paths">' +
      '<li><span>Win three of the next five</span><b>61%</b></li>' +
      '<li><span>Beat ' + rivalA + ' and take four points from the rest</span><b>48%</b></li>' +
      '<li><span>Draw with ' + rivalA + ', then win out</span><b>29%</b></li>' +
      "</ul></div>" +

      '<div class="intel-example"><h3>What we said before kickoff</h3>' +
      '<p>Every forecast is stamped and kept, so you can go back and check us — including when we were wrong.</p>' +
      '<div class="intel-receipt">Before ' + club + ' v ' + rivalA + ' we gave ' + club + ' <b>54%</b>. It finished 2–1. <em>Called.</em></div>' +
      "</div>" +

      '<p class="intel-alsoline">Also: who you are actually racing, how sure we are and why, alerts you control, and the full season history of every number.</p>' +
      "</div>";

    return '<section class="intel-locked" aria-label="Preview of Club Watch">' +
      '<div class="intel-locked-head"><div class="intel-eyebrow">Preview · sample numbers, real clubs</div>' +
      "<h2>This is what Club Watch keeps for " + club + "</h2>" +
      "<p>The current forecast is free and always will be. What you are unlocking is the part that remembers: what changed while you were away, why it changed, and which result next moves it most.</p></div>" +
      '<div class="intel-locked-stage"><div class="intel-locked-overlay">' +
      '<button class="intel-action primary" type="button" data-action="focus-signin">Watch ' + club + '</button></div>' +
      '<div class="intel-locked-body" inert aria-hidden="true">' + tabs + trust + brief + tape + leverage + "</div></div>" + more + "</section>";
  }

  function freeClubPickerHTML() {
    var selection = defaultSelection();
    if (!selection) return empty("No forecast clubs are available right now.");
    state.leagueId = selection.league.league_id;
    state.teamId = selection.team.team_id;
    return '<section class="intel-auth"><div class="intel-eyebrow">Step 1 of 2</div>' +
      '<h2>Which club should Club Watch remember?</h2>' +
      '<p>Your free account can follow one club and keeps one complete sample update. Public forecasts remain free.</p>' +
      '<div class="intel-field"><label for="intel-free-team">Club</label>' +
      '<select class="intel-team-select" id="intel-free-team">' + teamOptions() + '</select></div>' +
      '<button class="intel-action primary" data-action="track-free-club">Track this club</button> ' +
      '<button class="intel-action" data-action="logout">Sign out</button></section>';
  }

  function sampleTapeHTML(sample) {
    var current = sample.features.current && sample.features.current.data || {};
    var changed = sample.features.what_changed && sample.features.what_changed.data || {};
    var why = sample.features.why && sample.features.why.data || {};
    var next = sample.features.what_next && sample.features.what_next.data || {};
    var event = (changed.events || [])[0];
    var cause = (why.events || [])[0] || event;
    var fixture = (next.fixtures || [])[0] || current.next_high_impact_fixture;
    var change = event && event.delta_pp != null ? pp(event.delta_pp) :
      current.seven_day_change_pp != null ? pp(current.seven_day_change_pp) : "Baseline saved";
    return '<div class="intel-trust-tape" aria-label="Club Watch sample summary">' +
      tapeStep("Current", pct(current.current_pct), String(current.target_label || current.target_metric || sample.target_metric || "season target").replace(/_/g, " ")) +
      tapeStep("What changed", change, event ? shortDate(event.effective_at) : "first saved sample") +
      tapeStep("Why", cause ? String(cause.cause_class || cause.event_type || "supported evidence").replace(/_/g, " ") : "No supported cause yet", cause ? "evidence recorded" : "quiet state") +
      tapeStep("What next", fixture ? fixture.home + " vs " + fixture.away : "No fixture signal", fixture ? shortDate(fixture.date) + " · " + number(fixture.leverage_pp, 1) + "pp range" : "check back after new evidence") +
      "</div>";
  }

  function upgradeMomentCopy(sample) {
    var changed = sample.features.what_changed && sample.features.what_changed.data || {};
    var why = sample.features.why && sample.features.why.data || {};
    var next = sample.features.what_next && sample.features.what_next.data || {};
    var event = (changed.events || [])[0];
    var cause = (why.events || [])[0] || event;
    var fixture = (next.fixtures || [])[0];
    var movement = event && event.delta_pp != null ? pp(event.delta_pp) : "";
    var causeLabel = cause
      ? String(cause.cause_class || cause.event_type || "supported evidence").replace(/_/g, " ")
      : "the next supported cause";
    var fixtureLabel = fixture ? fixture.home + " vs " + fixture.away : "the next high-leverage match";
    var leverage = fixture && fixture.leverage_pp != null
      ? " (" + number(fixture.leverage_pp, 1) + "pp range)" : "";
    var moment = params.get("moment") || "";

    if (moment === "movement") {
      return {
        eyebrow: "Meaningful movement, already explained",
        title: movement ? sample.team + " moved " + movement : sample.team + "'s latest movement is in your sample",
        body: "This movement and its " + causeLabel +
          " explanation stay free in your saved sample. Club Watch paid keeps monitoring future material changes and attaches supported causes when they are established."
      };
    }
    if (moment === "match") {
      return {
        eyebrow: "Before a high-leverage match",
        title: fixtureLabel + leverage,
        body: "This match-stakes preview stays free. Club Watch paid keeps watching what this match and relevant rival results actually change, then preserves the evidence across visits."
      };
    }
    if (moment === "scenario") {
      return {
        eyebrow: "After your one-match scenario",
        title: "The scenario you just ran stays free",
        body: "Return to the public forecast whenever you want to rerun it. Club Watch paid adds saved multi-match paths across devices, an updating season forecast history, and monitoring after real results arrive."
      };
    }
    if (moment === "club_limit") {
      return {
        eyebrow: "You reached a real continuity limit",
        title: "Your free account keeps one Club Watch club",
        body: "That club and its complete sample stay free. Club Watch paid syncs and monitors up to ten followed clubs; browser favorites remain local and are never removed."
      };
    }
    return {
      eyebrow: "Keep the watch running",
      title: "Club Watch continues after this sample",
      body: "Paid access adds continuous change monitoring, cause and evidence, match stakes, an updating season forecast history, saved scenarios, and up to ten followed clubs. Current forecasts and this sample stay free."
    };
  }

  function sampleHistoryHTML(sample) {
    var feature = sample.features.history || {};
    var data = feature.data || {};
    if (!data.points || !data.points.length) return "";
    return '<section class="intel-feature intel-sample-history"><div class="intel-feature-head">' +
      '<span class="intel-feature-num">02</span><div class="intel-feature-title"><h2>Season forecast history</h2>' +
      '<p>Your saved sample includes the season path up to this frozen snapshot.</p></div>' +
      '<span class="intel-state ' + attr(feature.status || "live") + '">' +
      escapeHtml((feature.status || "live").replace(/_/g, " ")) + '</span></div>' +
      trajectoryHTML(data, sample.target_metric, true) + '</section>';
  }

  function freeView() {
    document.title = "Club Watch · Entenser";
    root.classList.remove("hidden");
    if (!state.sample) {
      root.innerHTML = '<div class="ed-wrap intel-app">' +
        commandHeader("Club Watch", "Free account · one followed club") +
        (state.notice ? '<div class="intel-success">' + escapeHtml(state.notice) + "</div>" : "") +
        (state.error ? '<div class="intel-error">' + escapeHtml(state.error) + "</div>" : "") +
        freeClubPickerHTML() + "</div>";
      return;
    }
    if (!state.upgradeTracked) {
      track("sample_update_view", {
        club_id: state.sample.team_id, club_name: state.sample.team,
        competition_id: state.sample.league_id, surface: "club_watch_sample"
      });
      track("upgrade_view", funnelPayload(state.interval));
      analytics("upgrade_view", {
        league_id: state.sample.league_id,
        team_id: state.sample.team_id,
        surface: "club_watch_sample"
      });
      state.upgradeTracked = true;
    }
    var canCheckout = !!(state.checkout && state.checkout.enabled && priceRecord(state.interval));
    var upgradeMoment = upgradeMomentCopy(state.sample);
    root.innerHTML = '<div class="ed-wrap intel-app">' +
      commandHeader(state.sample.team + " Club Watch", state.sample.league_name + " · saved sample · " + state.sample.generated) +
      (state.notice ? '<div class="intel-success">' + escapeHtml(state.notice) + "</div>" : "") +
      (state.error ? '<div class="intel-error">' + escapeHtml(state.error) + "</div>" : "") +
      '<section class="intel-feature"><div class="intel-feature-head"><span class="intel-feature-num">01</span>' +
      '<div class="intel-feature-title"><h2>Your complete sample update</h2></div>' +
      '<span class="intel-state thin_history">saved</span></div>' +
      sampleTapeHTML(state.sample) +
      '<div class="intel-note">This sample is frozen to snapshot ' + escapeHtml(state.sample.snapshot_id) +
      '. It will not silently change underneath you.</div></section>' +
      sampleHistoryHTML(state.sample) +
      '<section class="intel-auth" data-upgrade-moment="' + attr(params.get("moment") || "sample") + '">' +
      '<div class="intel-eyebrow">' + escapeHtml(upgradeMoment.eyebrow) + '</div>' +
      '<h2>' + escapeHtml(upgradeMoment.title) + '</h2>' +
      '<p>' + escapeHtml(upgradeMoment.body) + '</p>' +
      intervalChooserHTML() +
      '<p class="intel-terms">' + escapeHtml(priceSentence(state.interval)) +
      (canCheckout ? ' Renews automatically every ' + escapeHtml(intervalWord(state.interval)) +
        ' until cancelled. Cancel any time from your account. 30-day money-back guarantee.' : "") + "</p>" +
      '<button class="intel-action primary" data-action="checkout" data-plan="intel"' +
      (canCheckout ? "" : " disabled aria-disabled=\"true\"") + ">" +
      escapeHtml(subscribeLabel(state.interval)) + '</button> ' +
      '<a class="intel-action" href="?league=account">Account</a></section></div>';
  }

  function commandHeader(title, subtitle) {
    var plan = state.me ? state.me.plan : "";
    return '<header class="intel-command"><div class="intel-command-copy">' +
      '<div class="intel-eyebrow">Personal Club Watch</div><h1>' + escapeHtml(title) + "</h1>" +
      '<p>' + escapeHtml(subtitle || "") + '</p></div><div class="intel-command-actions">' +
      '<span class="intel-session"><strong>' + escapeHtml(plan) + '</strong> plan</span>' +
      // Self-service cancellation must be no harder to find than signup was.
      (["intel", "creator", "canceled"].indexOf(plan) >= 0
        ? '<button class="intel-action" data-action="billing-portal">Manage billing</button>'
        : "") +
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

  function stakesFromFixtures(data) {
    if (data.stakes_card) return data.stakes_card;
    var own = (data.fixtures || []).filter(function (fixture) {
      return fixture.home_id === state.teamId || fixture.away_id === state.teamId;
    }).sort(function (a, b) {
      return String(a.date || "").localeCompare(String(b.date || "")) ||
        String(a.ko || "").localeCompare(String(b.ko || ""));
    });
    if (!own.length) return null;
    var fixture = own[0];
    var isHome = fixture.home_id === state.teamId;
    var labels = isHome
      ? { H: "Win", D: "Draw", A: "Loss" }
      : { H: "Loss", D: "Draw", A: "Win" };
    return {
      date: fixture.date,
      ko: fixture.ko,
      home: fixture.home,
      away: fixture.away,
      target_metric: data.target_metric,
      baseline_pct: fixture.baseline_pct,
      evidence_ids: fixture.evidence_ids,
      outcomes: ["H", "D", "A"].map(function (code) {
        var value = fixture.conditional_pct && fixture.conditional_pct[code];
        return {
          code: code,
          label: labels[code],
          pct: value,
          delta_pp: value == null ? null : Number(value) - Number(fixture.baseline_pct)
        };
      })
    };
  }

  function renderStakes(data) {
    var card = stakesFromFixtures(data);
    if (!card) return "";
    var target = String(card.target_label || card.target_metric || "target").replace(/_/g, " ");
    return '<section class="intel-stakes" aria-label="What is at stake in the next match">' +
      '<div class="intel-stakes-head"><div><span>Next match · what’s at stake</span><b>' +
      escapeHtml(card.home) + " vs " + escapeHtml(card.away) + '</b><small>' +
      shortDate(card.date) + " · " + escapeHtml(target) + '</small></div>' +
      '<div class="intel-stakes-current"><span>Scenario baseline</span><b>' +
      pct(card.baseline_pct) + '</b></div></div>' +
      '<div class="intel-stake-outcomes">' + (card.outcomes || []).map(function (outcome) {
        var movement = Number(outcome.delta_pp);
        var moveClass = movement > 0 ? " up" : movement < 0 ? " down" : "";
        return '<div class="intel-stake-outcome ' + attr(String(outcome.label || "").toLowerCase()) + '">' +
          '<span>' + escapeHtml(outcome.label) + '</span><b>' + pct(outcome.pct) +
          '</b><small class="intel-move' + moveClass + '">' + pp(outcome.delta_pp) +
          " vs baseline</small></div>";
      }).join("") + "</div>" + evidence(card.evidence_ids) + "</section>";
  }

  function renderLeverage(data) {
    var fixtures = data.fixtures || [];
    if (!fixtures.length) return empty("No remaining fixture leverage can be calculated.");
    return renderStakes(data) + table(["Date", "Fixture", "Scope", "Range", "Expected move"], fixtures.slice(0, 10).map(function (fixture) {
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
      '<label><input id="intel-weekly-alert" type="checkbox"' + (notifications.weekly !== false ? " checked" : "") + '> Weekly watch</label>' +
      '<label><input id="intel-match-alert" type="checkbox"' + (notifications.match_morning ? " checked" : "") + '> Match morning</label>' +
      '<label><input id="intel-quiet-alert" type="checkbox"' + (notifications.quiet ? " checked" : "") + '> Quiet mode</label>' +
      '<label><input id="intel-pause-alert" type="checkbox"' + (notifications.paused ? " checked" : "") + '> Pause all</label>' +
      '<button class="intel-action primary" data-action="save-alerts">Save notification preferences</button></div>' +
      '<div class="intel-note">Preview only · current delivery state: ' + escapeHtml(data.send_state || "shadow") +
      ". Live alerts and briefings remain unavailable until the reliability gate and owner approval are complete.</div></div>";
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

  function historyMetricCounts(data) {
    var counts = {};
    (data.points || []).forEach(function (point) {
      Object.keys(point.values || {}).forEach(function (key) {
        if (isFinite(Number(point.values[key]))) counts[key] = (counts[key] || 0) + 1;
      });
    });
    return counts;
  }

  function historyMetricRanges(data) {
    var ranges = {};
    (data.points || []).forEach(function (point) {
      Object.keys(point.values || {}).forEach(function (key) {
        var value = Number(point.values[key]);
        if (!isFinite(value)) return;
        if (!ranges[key]) ranges[key] = {min: value, max: value};
        ranges[key].min = Math.min(ranges[key].min, value);
        ranges[key].max = Math.max(ranges[key].max, value);
      });
    });
    return ranges;
  }

  function historyMetricOrder(data) {
    var counts = historyMetricCounts(data);
    var ranges = historyMetricRanges(data);
    return Object.keys(counts).sort(function (a, b) {
      var aRange = ranges[a] ? ranges[a].max - ranges[a].min : 0;
      var bRange = ranges[b] ? ranges[b].max - ranges[b].min : 0;
      return bRange - aRange || counts[b] - counts[a] || a.localeCompare(b);
    });
  }

  // A pinned season target is a scenario choice, not a history choice, and the
  // archive does not cover every metric equally — `spoon`, `conf_win` and `hfa`
  // only started being recorded on 2026-08-01. Honouring a thinly-covered target
  // silently truncated this panel to the handful of checkpoints that carried it,
  // dropping the reconstructed replay the key advertises. Measured 2026-08-05:
  // 114 of 1141 clubs with history were drawing such a stub, most of them pinned
  // to `continental`. So an inherited target must clear a share of the best
  // covered metric's checkpoints; a target the reader picked in the selector is
  // always honoured, however thin, because they can see its count in the option.
  var HISTORY_COVERAGE_FLOOR = 0.5;

  function resolveHistoryMetric(data, preferred, explicit) {
    var counts = historyMetricCounts(data);
    var order = historyMetricOrder(data);
    if (explicit && counts[preferred]) return preferred;
    var widest = order.reduce(function (most, key) {
      return Math.max(most, counts[key]);
    }, 0);
    var floor = widest * HISTORY_COVERAGE_FLOOR;
    if (counts[preferred] >= floor) return preferred;
    var covered = order.filter(function (key) { return counts[key] >= floor; });
    return covered[0] || order[0] || preferred;
  }

  function historyShortDate(value) {
    var date = new Date(String(value).slice(0, 10) + "T12:00:00");
    return isNaN(date) ? String(value || "") : date.toLocaleDateString([], {month: "short", day: "numeric"});
  }

  function trajectoryHTML(data, metric, compact, explicit) {
    var points = data.points || [];
    if (!points.length) return empty("Trajectory history has not accrued for this target.");
    metric = resolveHistoryMetric(data, metric, explicit);
    var plotted = points.map(function (point) {
      var value = point.value != null ? point.value : point.pct != null ? point.pct : point.values && point.values[metric];
      var date = point.snapshot_date || point.date;
      return {
        value: Number(value), date: date,
        time: Date.parse(String(date).slice(0, 10) + "T00:00:00Z"),
        kind: point.kind === "reconstructed" ? "reconstructed" : "archived"
      };
    }).filter(function (point) { return isFinite(point.value) && isFinite(point.time); })
      .sort(function (a, b) { return a.time - b.time; });
    if (!plotted.length) return empty("Trajectory values are unavailable for the pinned target.");
    var width = 900;
    var height = compact ? 160 : 196;
    var left = 42, right = 888, top = 12, bottom = height - 30;
    var firstTime = plotted[0].time, lastTime = plotted[plotted.length - 1].time;
    function coord(point) {
      var span = Math.max(1, lastTime - firstTime);
      var x = plotted.length === 1 ? (left + right) / 2 : left + (point.time - firstTime) * (right - left) / span;
      var y = bottom - Math.max(0, Math.min(100, point.value)) * (bottom - top) / 100;
      return {x: x, y: y, text: x.toFixed(1) + "," + y.toFixed(1)};
    }
    var runs = [];
    plotted.forEach(function (point) {
      var last = runs[runs.length - 1];
      if (!last || last.kind !== point.kind) {
        last = {kind: point.kind, points: []};
        runs.push(last);
      }
      last.points.push(point);
    });
    var lines = runs.map(function (run) {
      if (run.points.length === 1) return "";
      return '<polyline class="intel-chart-line ' + run.kind + '" points="' +
        attr(run.points.map(function (point) { return coord(point).text; }).join(" ")) + '"></polyline>';
    }).join("");
    var dots = plotted.map(function (point) {
      var c = coord(point);
      return '<circle class="intel-chart-point ' + point.kind + '" cx="' + c.x.toFixed(1) +
        '" cy="' + c.y.toFixed(1) + '" r="2.8"><title>' + escapeHtml(historyShortDate(point.date) + " · " + pct(point.value) +
        " · " + point.kind) + '</title></circle>';
    }).join("");
    var reconstructed = plotted.filter(function (point) { return point.kind === "reconstructed"; }).length;
    var archived = plotted.length - reconstructed;
    var provenance = '<div class="intel-history-key" aria-label="Forecast history provenance">' +
      (reconstructed ? '<span><i class="reconstructed"></i>Reconstructed replay · ' + reconstructed + '</span>' : '') +
      (archived ? '<span><i class="archived"></i>Exact archived forecast · ' + archived + '</span>' : '') + '</div>' +
      '<div class="intel-note intel-history-note">Dashed points are point-in-time model replays using only information available then. ' +
      'Solid points are exact saved forecasts and take precedence on the same date. Current-season history remains free on the public league page.</div>';
    return '<div class="intel-history-chart"><svg class="intel-chart" viewBox="0 0 900 ' + height + '" role="img" aria-label="' +
      attr(String(metric || "season target").replace(/_/g, " ") + " forecast history") + '">' +
      [100, 75, 50, 25, 0].map(function (value) {
        var y = bottom - value * (bottom - top) / 100;
        return '<line class="intel-chart-grid" x1="' + left + '" y1="' + y.toFixed(1) + '" x2="' + right + '" y2="' + y.toFixed(1) +
          '"></line><text class="intel-chart-label" x="0" y="' + (y + 4).toFixed(1) + '">' + value + '%</text>';
      }).join("") + lines + dots +
      '<text class="intel-chart-date" x="' + left + '" y="' + (height - 8) + '">' + escapeHtml(historyShortDate(plotted[0].date)) + '</text>' +
      '<text class="intel-chart-date end" x="' + right + '" y="' + (height - 8) + '">' + escapeHtml(historyShortDate(plotted[plotted.length - 1].date)) + '</text>' +
      '</svg></div>' + provenance +
      '<div class="intel-facts">' + fact("Season start", pct(plotted[0].value)) +
      fact("Latest", pct(plotted[plotted.length - 1].value)) +
      fact("Target", String(metric || "season target").replace(/_/g, " ")) +
      fact("Checkpoints", plotted.length) +
      fact("Span", historyShortDate(plotted[0].date) + " → " + historyShortDate(plotted[plotted.length - 1].date)) + "</div>";
  }

  function renderTimeMachine(data) {
    var counts = historyMetricCounts(data);
    var explicit = !!state.historyTarget;
    var metric = resolveHistoryMetric(
      data, state.historyTarget || state.selectedTarget || state.record.target_metric,
      explicit);
    var metrics = historyMetricOrder(data);
    var selector = metrics.length > 1
      ? '<div class="intel-history-controls"><div class="intel-field"><label for="intel-history-target">Historical target</label>' +
        '<select class="intel-select" id="intel-history-target">' + metrics.map(function (key) {
          return '<option value="' + attr(key) + '"' + (key === metric ? " selected" : "") + '>' +
            escapeHtml(key.replace(/_/g, " ")) + ' · ' + counts[key] + ' checkpoints</option>';
        }).join("") + '</select></div></div>'
      : "";
    return selector + trajectoryHTML(data, metric, false, explicit);
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
      : '<div class="intel-toolbar-row" style="margin-top:10px"><span class="intel-assumption-count">Creator entitlement required \u2014 not on sale yet</span></div>';
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
    document.title = state.record.team + " Club Watch · Entenser";
    root.classList.remove("hidden");
    root.innerHTML = '<div class="ed-wrap intel-app">' +
      commandHeader(state.record.team + " Club Watch", state.record.league_name + " · " + modeLabel(mode.mode) + " · snapshot " + state.record.generated) +
      mergeBanner() +
      (state.notice ? '<div class="intel-success">' + escapeHtml(state.notice) + "</div>" : "") +
      (state.error ? '<div class="intel-error">' + escapeHtml(state.error) + "</div>" : "") +
      '<div class="intel-toolbar"><div class="intel-toolbar-main"><div class="intel-field"><label for="intel-team">Team</label>' +
      '<select class="intel-team-select" id="intel-team">' + teamOptions() + '</select></div></div><div class="intel-toolbar-meta"><b>' +
      escapeHtml(selection ? selection.league.league : state.record.league_name) + '</b><span class="intel-mode ' +
      attr(mode.mode || "") + '">' + escapeHtml(modeLabel(mode.mode)) + "</span></div></div>" +
      '<nav class="intel-tabs" aria-label="Club Watch views">' +
      Object.keys(TABS).map(function (tab) {
        return '<button class="intel-tab' + (tab === state.tab ? " on" : "") + '" data-action="tab" data-tab="' + tab + '">' +
          escapeHtml(tab.charAt(0).toUpperCase() + tab.slice(1)) + "</button>";
      }).join("") + "</nav>" + trustTape() +
      '<main id="intel-feature-list">' + features.map(featureShell).join("") + "</main></div>";
  }

  async function loadTeam(leagueId, teamId) {
    state.busy = true;
    state.error = "";
    loading("Loading Club Watch");
    try {
      var record = await api("/intel/team?league_id=" + encodeURIComponent(leagueId) + "&team_id=" + encodeURIComponent(teamId));
      // Feature 2 is a per-user view, not a static artifact. The team record
      // carries the complete event history; /intel/events applies the
      // persisted cursor so this tape means "since your last visit" across
      // devices instead of merely being labelled that way.
      var unseen = await api("/intel/events?league_id=" + encodeURIComponent(leagueId) + "&team_id=" + encodeURIComponent(teamId));
      if (record.features["2"]) {
        record.features["2"].data.events = unseen.events || [];
        record.features["2"].data.cursor = unseen.cursor || null;
        record.features["2"].status = unseen.events && unseen.events.length ? "live" : "thin_history";
        record.features["2"].reason = unseen.events && unseen.events.length
          ? null : "No material change has been recorded since your last visit.";
      }
      state.record = record;
      state.leagueId = leagueId;
      state.teamId = teamId;
      var linkedTarget = params.get("target");
      var availableTargets = Object.keys(record.features["5"] && record.features["5"].data.baseline || {});
      state.selectedTarget = availableTargets.indexOf(linkedTarget) >= 0 ? linkedTarget : pinnedTarget() || record.target_metric;
      state.historyTarget = "";
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
      [
        ["since_last_visit_viewed", "2"],
        ["material_change_explanation_viewed", "3"],
        ["match_stakes_viewed", "4"]
      ].forEach(function (item) {
        var key = record.snapshot_id + ":" + item[0];
        if (!state.valueEvents[key] && record.features[item[1]]) {
          state.valueEvents[key] = true;
          analytics(item[0], {
            league_id: leagueId, team_id: teamId,
            feature_id: Number(item[1]), surface: "club_watch"
          });
        }
      });
      await loadJournal();
      hubView();
      markEventsSeen();
    } catch (error) {
      setMessage(error.message, true);
      if (error.status === 401) {
        localStorage.removeItem(ACCESS_KEY);
        signInView();
      } else {
        root.innerHTML = '<div class="ed-wrap intel-app">' + commandHeader("Club Watch", "Team data unavailable") +
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
        body: JSON.stringify({
          league_id: state.leagueId,
          team_id: state.teamId,
          event_id: events[0].event_id
        })
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

  async function loadPricing() {
    // Carry through the cadence the visitor picked on the static pricing card,
    // so arriving at the hub doesn't silently reset their choice to the default.
    try {
      var chosen = sessionStorage.getItem("entenser_checkout_interval");
      if (chosen === "monthly" || chosen === "annual") state.interval = chosen;
    } catch (error) { /* private mode */ }
    try {
      var response = await fetch(API_BASE + "/public/config", {cache: "no-store"});
      if (!response.ok) return;
      var config = await response.json();
      state.pricing = (config && config.pricing) || {};
      state.checkout = (config && config.checkout) || {enabled: false};
    } catch (error) {
      state.pricing = {};   // quote nothing rather than quote wrong
      state.checkout = {enabled: false};
    }
    // If the selected cadence has no Stripe Price, fall back to one that does
    // rather than rendering a Subscribe button that cannot complete.
    if (!priceRecord(state.interval)) {
      state.interval = priceRecord("annual") ? "annual" : "monthly";
    }
  }

  // Stripe redirects back to /?league=intel&checkout=success|canceled. Without
  // this the customer lands on an unchanged page and reads a successful payment
  // as a failed one -- which is a support ticket and often a duplicate charge
  // attempt. Entitlement arrives by webhook, so a fresh /intel/me is required;
  // the redirect itself is never treated as proof of payment.
  function handleCheckoutReturn() {
    var outcome = params.get("checkout");
    if (!outcome) return;
    if (outcome === "success") {
      state.justPaid = true;
      setMessage("Payment received — thank you. Your access is being activated; " +
                 "this can take a few seconds. A receipt is on its way by email.", false);
      track("purchase_return");
    } else if (outcome === "canceled") {
      setMessage("Checkout cancelled — you have not been charged.", false);
      track("checkout_canceled");
    }
    params.delete("checkout");
    var query = params.toString();
    history.replaceState(null, "", location.pathname + (query ? "?" + query : "") + location.hash);
  }

  // Delegate to the host page's track(), which gates on live host + configured
  // provider and handles Plausible as well as GA4. Calling window.gtag directly
  // from here would fire events off the live domain and bypass that gating.
  function track(name, payload) {
    try {
      if (typeof window.track === "function") window.track(name, payload || {});
      else if (typeof window.gtag === "function") window.gtag("event", name, payload || {});
    } catch (error) { /* analytics must never break checkout */ }
  }

  // GA4 ecommerce shape, so the Sept 30 conversion read is a standard funnel
  // report rather than a hand-rolled one. `interval` is carried on every event
  // because the monthly/annual split is the thing the annual push is testing.
  function funnelPayload(interval) {
    var priced = priceRecord(interval || state.interval);
    return {
      plan: "intel",
      interval: interval || state.interval,
      tier: priced ? priced.tier : undefined,
      currency: priced ? String(priced.currency || "").toUpperCase() : undefined,
      value: priced ? priced.amount / 100 : undefined
    };
  }

  async function initialize() {
    loading("Opening private workspace");
    await loadPricing();
    handleCheckoutReturn();
    var magicToken = params.get("token");
    if (magicToken) {
      try {
        var pair = await api("/auth/callback?token=" + encodeURIComponent(magicToken));
        localStorage.setItem(ACCESS_KEY, pair.access_token);
        localStorage.setItem(REFRESH_KEY, pair.refresh_token);
        track("registration_complete", {surface: "club_watch"});
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
    // Returning from a successful checkout, the entitlement is written by the
    // Stripe webhook, which races the browser redirect. Showing freeView here
    // would tell someone who just paid that they haven't -- so poll briefly
    // before believing it. Always bounded, and always the server's answer.
    if (state.justPaid && ["intel", "creator"].indexOf(state.me.plan) < 0) {
      for (var attempt = 0; attempt < 5; attempt++) {
        await new Promise(function (resolve) { setTimeout(resolve, 1200); });
        try {
          state.me = await api("/intel/me");
        } catch (error) { break; }
        if (["intel", "creator"].indexOf(state.me.plan) >= 0) break;
      }
      if (["intel", "creator"].indexOf(state.me.plan) >= 0) {
        // Fired only once the SERVER confirms the entitlement, never on the
        // Stripe redirect alone -- a redirect proves the customer came back
        // from Stripe, not that money moved. Anything less and launch week's
        // conversion number is inflated by abandoned and failed payments.
        track("purchase", funnelPayload(state.interval));
      }
      if (["intel", "creator"].indexOf(state.me.plan) < 0) {
        setMessage("Your payment went through, but access hasn't activated yet. " +
                   "Refresh in a moment — if it persists, contact support and quote your " +
                   "Stripe receipt; you will not be charged twice.", true);
      }
    }
    if (["trial", "intel", "creator"].indexOf(state.me.plan) < 0) {
      var freeSelection = defaultSelection();
      var followed = state.prefs.teams || [];
      if (!followed.length && params.get("track") === "1" && freeSelection) {
        try {
          state.prefs = await api("/intel/preferences", {
            method: "PATCH",
            body: JSON.stringify({teams: [{
              league_id: freeSelection.league.league_id,
              team_id: freeSelection.team.team_id,
              team: freeSelection.team.team
            }]})
          });
          followed = state.prefs.teams || [];
          track("track_club", {
            club_id: freeSelection.team.team_id,
            club_name: freeSelection.team.team,
            competition_id: freeSelection.league.league_id,
            surface: "club_page"
          });
        } catch (error) {
          setMessage(error.message, true);
        }
      }
      if (followed.length) {
        var savedClub = followed[0];
        try {
          state.sample = await api("/intel/sample?league_id=" +
            encodeURIComponent(savedClub.league_id) + "&team_id=" +
            encodeURIComponent(savedClub.team_id));
        } catch (error) {
          setMessage(error.message, true);
        }
      }
      freeView();
      return;
    }
    await loadWorkspaces();
    var selection = defaultSelection();
    if (!selection) {
      root.innerHTML = '<div class="ed-wrap intel-app">' + commandHeader("Club Watch", "No forecast competitions are available") +
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
      track("registration_start", {surface: "club_watch"});
      await api("/auth/request", {
        method: "POST",
        body: JSON.stringify({
          email: email,
          return_to: location.pathname + location.search + location.hash
        })
      });
      setMessage("Check your email for the secure sign-in link.", false);
    } catch (error) {
      setMessage(error.message, true);
    }
    signInView();
  });

  root.addEventListener("change", async function (event) {
    if (event.target.id === "intel-free-team") {
      var freeParts = event.target.value.split("|");
      state.leagueId = freeParts[0];
      state.teamId = freeParts[1];
    }
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
    if (event.target.id === "intel-history-target") {
      state.historyTarget = event.target.value;
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
        if (state.tab === "history" && state.record) {
          var historyEventKey = state.record.snapshot_id + ":season_history_viewed";
          if (!state.valueEvents[historyEventKey]) {
            state.valueEvents[historyEventKey] = true;
            analytics("season_history_viewed", {
              league_id: state.leagueId, team_id: state.teamId,
              feature_id: 11, surface: "club_watch"
            });
          }
        }
        hubView();

      } else if (action === "focus-signin") {
        var emailField = document.getElementById("intel-email");
        if (emailField) {
          emailField.scrollIntoView({block: "center"});
          emailField.focus({preventScroll: true});
        }
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
        if (!(state.checkout && state.checkout.enabled && priceRecord(state.interval))) {
          throw new Error("Checkout is not available yet.");
        }
        var plan = button.getAttribute("data-plan") || "intel";
        track("checkout_start", funnelPayload(state.interval));
        track("begin_checkout", funnelPayload(state.interval));
        var checkout = await api("/billing/checkout", {
          method: "POST",
          body: JSON.stringify({plan: plan, interval: state.interval})
        });
        location.assign(checkout.url);
      } else if (action === "set-interval") {
        state.interval = button.getAttribute("data-interval") === "monthly" ? "monthly" : "annual";
        freeView();
        return;
      } else if (action === "track-free-club") {
        var club = findSelection(state.leagueId, state.teamId);
        if (!club) throw new Error("Choose a club first.");
        state.prefs = await api("/intel/preferences", {
          method: "PATCH",
          body: JSON.stringify({teams: [{
            league_id: club.league.league_id,
            team_id: club.team.team_id,
            team: club.team.team
          }]})
        });
        track("track_club", {
          club_id: club.team.team_id,
          club_name: club.team.team,
          competition_id: club.league.league_id,
          surface: "club_watch"
        });
        state.sample = await api("/intel/sample?league_id=" +
          encodeURIComponent(club.league.league_id) + "&team_id=" +
          encodeURIComponent(club.team.team_id));
        params.set("intelLeague", club.league.league_id);
        params.set("team", club.team.team_id);
        params.delete("track");
        history.replaceState(null, "", location.pathname + "?" + params.toString());
        freeView();
        return;
      } else if (action === "billing-portal") {
        var portal = await api("/billing/portal", {method: "POST", body: "{}"});
        location.assign(portal.url);
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
        analytics(action === "scenario-save" ? "scenario_saved" : "scenario_run",
          {league_id: state.leagueId, team_id: state.teamId, surface: "club_watch"});
        hubView();
      } else if (action === "save-alerts") {
        var notifications = Object.assign({}, state.prefs.notifications || {}, {
          material_change: document.getElementById("intel-material-alert").checked,
          weekly: document.getElementById("intel-weekly-alert").checked,
          match_morning: document.getElementById("intel-match-alert").checked,
          quiet: document.getElementById("intel-quiet-alert").checked,
          paused: document.getElementById("intel-pause-alert").checked
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
