#!/usr/bin/env Rscript
# Export Transfermarkt MLS transfer-window spend/income (arrivals fee sum,
# departures fee sum, net spend), per team-season.
#
# Scraping method note (matches the existing transfermarkt_squad_values.R's
# posture: use worldfootballR's own package functions where they work, only
# fall back to a hand-rolled rvest/httr scrape where they don't):
#   - tm_team_transfer_balances() is BROKEN against the current TM page layout
#     (verified live, 2026-07-14: errors with "Column `expenditure_euros` not
#     found in `.data`" — the site renamed/restructured the balances page's
#     "Expenditure:" cell worldfootballR's regex expects).
#   - tm_team_transfers() is ALSO broken (verified live, 2026-07-14, Inter
#     Miami CF 2023): it silently returns ZERO "Departures" rows for every
#     team tested — its internal per-window sub-page loop
#     (`tab_box_window[i] %>% html_nodes("h2")` after filtering `.box` nodes
#     to `c("Arrivals","Departures")`) suffers the exact same
#     box-vs-h2-not-1:1-positionally bug already documented in this repo for
#     the kader/market-value scrape (see the historical comment in
#     transfermarkt_squad_values.R) — just in a different function.
#   - The team's single combined "transfers" page
#     (transfermarkt.com/<slug>/transfers/verein/<id>/saison_id/<season>) DOES
#     work correctly and is simpler: ONE request returns both the "Arrivals"
#     and "Departures" `.box` elements for the full season (both windows
#     already combined), each with a `.responsive-table` of player rows and a
#     `td.rechts` fee cell per row ("€7.45m" / "free transfer" / "draft" /
#     "loan transfer" / "-" / "End of loan..."). Verified against Inter Miami
#     CF 2023: 26 arrivals incl. Messi/Busquets/Alba (free transfers, correctly
#     zero-valued) and Redondo €7.45m, Avilés €6.30m, Farías €5.00m, Gómez
#     €2.70m (== the 21.45m sum spot-checked against the squad-value script's
#     header comment); 23 departures incl. Gregore €2.50m to Botafogo. Boxes
#     are matched by their OWN h2 (`html_node("h2")`, not a separately-queried
#     flat h2 vector) — the same safe pattern already used in
#     transfermarkt_squad_values.R's kader scrape — so this script does not
#     repeat worldfootballR's bug.
#
# Season-level values (not split by window): the combined page already
# aggregates the winter window before the season plus the summer window
# during it — i.e. exactly "the last 1-2 transfer windows" as of that season.
# A per-window split would require the same buggy sub-pages worldfootballR
# uses, so it is intentionally out of scope for this pass.
#
# Output schema (CSV, one row per team-season):
#   season, tm_team_name, arrivals_spend_eur, departures_income_eur,
#   net_spend_eur, n_arrivals, n_departures, n_paid_arrivals, n_paid_departures

suppressPackageStartupMessages({
  library(worldfootballR)
  library(dplyr)
  library(readr)
  library(stringr)
  library(rvest)
  library(httr)
  library(tibble)
})

args     <- commandArgs(trailingOnly = TRUE)
season   <- if (length(args) >= 1) as.integer(args[[1]]) else as.integer(format(Sys.Date(), "%Y"))
out_path <- if (length(args) >= 2) args[[2]] else
              sprintf("data/transfermarkt_transfers_%d.csv", season)

dir.create(dirname(out_path), recursive = TRUE, showWarnings = FALSE)

TM_HEADERS <- c(
  `User-Agent`      = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  `Accept-Language` = "en-US,en;q=0.9",
  `Accept`          = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
)

parse_tm_value <- function(x) {
  # "€5.00m" -> 5e6, "€500k" -> 5e5, "free transfer"/"draft"/"loan transfer"/
  # "-"/"End of loan..."/NA -> 0 (no disclosed fee)
  x <- str_trim(x)
  if (is.na(x) || x == "" || x == "-") return(0.0)
  if (!str_detect(x, "€")) return(0.0)  # no Euro sign => not a disclosed fee
  x_clean <- str_replace_all(x, "[€,\\s]", "")
  mult <- case_when(
    str_detect(x_clean, "bn") ~ 1e9,
    str_detect(x_clean, "m")  ~ 1e6,
    str_detect(x_clean, "k")  ~ 1e3,
    TRUE                      ~ 1.0
  )
  num <- suppressWarnings(as.numeric(str_replace_all(x_clean, "[^0-9.]", "")))
  ifelse(is.na(num), 0.0, num * mult)
}

empty_csv <- function() {
  write_csv(tibble(
    season                 = integer(),
    tm_team_name           = character(),
    arrivals_spend_eur     = numeric(),
    departures_income_eur  = numeric(),
    net_spend_eur          = numeric(),
    n_arrivals             = integer(),
    n_departures           = integer(),
    n_paid_arrivals        = integer(),
    n_paid_departures      = integer()
  ), out_path)
}

fetch_page <- function(url) {
  resp <- tryCatch(
    GET(url, add_headers(.headers = TM_HEADERS), timeout(30)),
    error = function(e) { message("  fetch error: ", conditionMessage(e)); NULL }
  )
  if (is.null(resp) || status_code(resp) != 200) {
    message("  HTTP ", if (!is.null(resp)) status_code(resp) else "NULL")
    return(NULL)
  }
  tryCatch(read_html(content(resp, as = "text", encoding = "UTF-8")),
           error = function(e) NULL)
}

get_box_fees <- function(page, label) {
  # Returns list(fees=numeric vector, n=count) for the .box whose OWN h2 == label.
  boxes  <- page %>% html_nodes(".box")
  own_h2 <- vapply(boxes, function(b) {
    h <- b %>% html_node("h2") %>% html_text()
    if (is.na(h)) NA_character_ else str_squish(h)
  }, character(1))
  idx <- which(own_h2 == label)
  if (length(idx) == 0) return(list(fees = numeric(0), n = 0L))
  box <- boxes[idx[1]]
  tbl <- box %>% html_node(".responsive-table")
  if (is.na(tbl) || length(tbl) == 0) return(list(fees = numeric(0), n = 0L))
  rows <- tbl %>% html_nodes("tbody > tr")
  if (length(rows) == 0) return(list(fees = numeric(0), n = 0L))
  fee_txt <- vapply(rows, function(r) {
    cell <- r %>% html_node("td.rechts")
    if (is.null(cell) || length(cell) == 0 || is.na(cell)) return(NA_character_)
    str_squish(html_text(cell))
  }, character(1))
  fees <- vapply(fee_txt, parse_tm_value, numeric(1), USE.NAMES = FALSE)
  list(fees = fees, n = length(rows))
}

# MLS only (this feature is scoped to the MLS eval harness). Same season-index
# fallback as transfermarkt_squad_values.R: worldfootballR's index CSV can lag
# the current season, so retry with a prior year's URL list and swap saison_id.
team_urls <- tryCatch(
  tm_league_team_urls(country_name = "United States", start_year = season),
  error = function(e) {
    message("tm_league_team_urls failed: ", conditionMessage(e))
    for (fallback_year in c(season - 1, season - 2)) {
      prior <- tryCatch(
        tm_league_team_urls(country_name = "United States", start_year = fallback_year),
        error = function(e2) character(0)
      )
      if (length(prior) > 0) {
        swapped <- gsub(paste0("saison_id/", fallback_year), paste0("saison_id/", season),
                         prior, fixed = TRUE)
        message(sprintf("  Falling back to %d URL list with season substituted to %d (%d teams)",
                        fallback_year, season, length(swapped)))
        return(swapped)
      }
    }
    character(0)
  }
)

if (length(team_urls) == 0) {
  empty_csv()
  quit(status = 0)
}

message(sprintf("Fetching transfer-window totals for %d teams, season %d...",
                length(team_urls), season))

rows <- lapply(seq_along(team_urls), function(i) {
  team_url  <- team_urls[[i]]
  xfers_url <- str_replace(team_url, "/startseite/", "/transfers/")
  Sys.sleep(3)

  tryCatch({
    page <- fetch_page(xfers_url)
    if (is.null(page)) {
      message(sprintf("  [%d/%d] fetch failed: %s", i, length(team_urls), basename(dirname(team_url))))
      return(NULL)
    }
    team_name <- page %>% html_nodes("h1") %>% html_text() %>% str_squish() %>% .[1]
    if (is.na(team_name) || team_name == "") team_name <- basename(dirname(team_url))

    arr <- get_box_fees(page, "Arrivals")
    dep <- get_box_fees(page, "Departures")

    result <- tibble(
      season                = season,
      tm_team_name          = team_name,
      arrivals_spend_eur    = sum(arr$fees),
      departures_income_eur = sum(dep$fees),
      net_spend_eur         = sum(arr$fees) - sum(dep$fees),
      n_arrivals            = arr$n,
      n_departures          = dep$n,
      n_paid_arrivals       = sum(arr$fees > 0),
      n_paid_departures     = sum(dep$fees > 0)
    )

    message(sprintf("  [%d/%d] %-28s  in=EUR%.2fm (%d/%d paid)  out=EUR%.2fm (%d/%d paid)  net=EUR%.2fm",
                    i, length(team_urls), team_name,
                    result$arrivals_spend_eur / 1e6, result$n_paid_arrivals, result$n_arrivals,
                    result$departures_income_eur / 1e6, result$n_paid_departures, result$n_departures,
                    result$net_spend_eur / 1e6))
    result

  }, error = function(e) {
    message(sprintf("  [%d/%d] ERROR %s: %s", i, length(team_urls), team_url, conditionMessage(e)))
    NULL
  })
})

rows <- bind_rows(rows)

if (is.null(rows) || nrow(rows) == 0) {
  empty_csv()
  quit(status = 0)
}

write_csv(rows, out_path)
message(sprintf("\nWrote %d team rows to %s", nrow(rows), out_path))
