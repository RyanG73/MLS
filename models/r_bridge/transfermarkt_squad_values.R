#!/usr/bin/env Rscript
# Export Transfermarkt MLS squad market values via worldfootballR.
# Output schema (CSV): season, tm_team_name, squad_value_eur, avg_age, n_internationals, dp_count_tm

suppressPackageStartupMessages({
  library(worldfootballR)
  library(dplyr)
  library(readr)
  library(stringr)
})

args <- commandArgs(trailingOnly = TRUE)
season <- if (length(args) >= 1) as.integer(args[[1]]) else as.integer(format(Sys.Date(), "%Y"))
out_path <- if (length(args) >= 2) args[[2]] else sprintf("data/transfermarkt_squad_values_%d.csv", season)

dir.create(dirname(out_path), recursive = TRUE, showWarnings = FALSE)

empty_csv <- function() {
  write_csv(tibble(
    season = integer(),
    tm_team_name = character(),
    squad_value_eur = numeric(),
    avg_age = numeric(),
    n_internationals = integer(),
    dp_count_tm = integer()
  ), out_path)
}

team_urls <- tryCatch(
  tm_league_team_urls(
    country_name = "USA",
    start_year = season
  ),
  error = function(e) {
    message(sprintf("tm_league_team_urls failed: %s", conditionMessage(e)))
    character(0)
  }
)

if (length(team_urls) == 0) {
  empty_csv()
  quit(status = 0)
}

rows <- lapply(team_urls, function(team_url) {
  tryCatch({
    squad <- tm_squad_stats(team_url = team_url, time_pause = 3)
    if (is.null(squad) || nrow(squad) == 0) return(NULL)

    # Heuristic: parse the player market values. Column name varies across releases.
    val_col <- intersect(c("player_market_value_euro", "market_value_euro",
                           "player_market_value", "market_value_euro_mln"),
                         names(squad))[1]
    age_col <- intersect(c("age", "player_age"), names(squad))[1]
    nat_col <- intersect(c("nationality", "Nat.", "country"), names(squad))[1]
    team_col <- intersect(c("team_name", "Team", "club"), names(squad))[1]

    if (is.na(val_col)) {
      return(NULL)
    }

    vals <- suppressWarnings(as.numeric(squad[[val_col]]))
    vals[is.na(vals)] <- 0

    avg_age <- if (!is.na(age_col)) {
      suppressWarnings(mean(as.numeric(squad[[age_col]]), na.rm = TRUE))
    } else { NA_real_ }

    n_internationals <- if (!is.na(nat_col)) {
      # USA-based MLS team: international = non-USA nationality (best-effort)
      sum(!str_detect(tolower(squad[[nat_col]]), "usa|united states"), na.rm = TRUE)
    } else { NA_integer_ }

    # DP proxy: market value above $1M USD ≈ 0.9M EUR (rough)
    dp_count <- sum(vals >= 900000, na.rm = TRUE)

    team_name <- if (!is.na(team_col)) {
      as.character(squad[[team_col]][1])
    } else {
      # derive from URL fragment
      basename(dirname(team_url))
    }

    tibble(
      season = season,
      tm_team_name = team_name,
      squad_value_eur = sum(vals, na.rm = TRUE),
      avg_age = avg_age,
      n_internationals = as.integer(n_internationals),
      dp_count_tm = as.integer(dp_count)
    )
  }, error = function(e) {
    message(sprintf("squad fetch failed for %s: %s", team_url, conditionMessage(e)))
    NULL
  })
})

rows <- bind_rows(rows)

if (is.null(rows) || nrow(rows) == 0) {
  empty_csv()
  quit(status = 0)
}

write_csv(rows, out_path)
message(sprintf("Wrote %d teams to %s", nrow(rows), out_path))
