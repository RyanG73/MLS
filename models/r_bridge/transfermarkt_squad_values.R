#!/usr/bin/env Rscript
# Export Transfermarkt MLS squad data via worldfootballR.
#
# Uses tm_squad_stats() which returns per-player appearance data including
# standardized Transfermarkt positions and minutes_played.
#
# Output schema (CSV, one row per player):
#   season, tm_team_name, player_name, position, market_value_eur,
#   age, nationality
#
# NOTE: market_value_eur is proxied by minutes_played (scaled to EUR-like range
# for compatibility with import_transfermarkt.py). True market values would
# require tm_player_market_values() per player (~40 min/season extra).
# The positional split (Tilt) and age features are valid regardless of proxy.

suppressPackageStartupMessages({
  library(worldfootballR)
  library(dplyr)
  library(readr)
  library(stringr)
})

args     <- commandArgs(trailingOnly = TRUE)
season   <- if (length(args) >= 1) as.integer(args[[1]]) else as.integer(format(Sys.Date(), "%Y"))
out_path <- if (length(args) >= 2) args[[2]] else
              sprintf("data/transfermarkt_squad_values_%d.csv", season)

dir.create(dirname(out_path), recursive = TRUE, showWarnings = FALSE)

empty_csv <- function() {
  write_csv(tibble(
    season            = integer(),
    tm_team_name      = character(),
    player_name       = character(),
    position          = character(),
    market_value_eur  = numeric(),
    age               = numeric(),
    nationality       = character()
  ), out_path)
}

team_urls <- tryCatch(
  tm_league_team_urls(country_name = "United States", start_year = season),
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
  Sys.sleep(3)
  tryCatch({
    squad <- tm_squad_stats(team_url = team_url)
    if (is.null(squad) || nrow(squad) == 0) return(NULL)

    # Normalise column names across worldfootballR versions
    names(squad) <- tolower(names(squad))

    # Required columns from tm_squad_stats()
    name_col <- intersect(c("player_name", "name", "player"), names(squad))[1]
    pos_col  <- intersect(c("player_pos", "position", "pos"), names(squad))[1]
    age_col  <- intersect(c("player_age", "age"), names(squad))[1]
    nat_col  <- intersect(c("nationality", "nat."), names(squad))[1]
    min_col  <- intersect(c("minutes_played", "minutes", "mins"), names(squad))[1]
    team_col <- intersect(c("team_name", "team", "club"), names(squad))[1]

    if (is.na(name_col) || is.na(pos_col)) return(NULL)

    team_name <- if (!is.na(team_col)) as.character(squad[[team_col]][1]) else
                   basename(dirname(team_url))

    # Use minutes_played as market_value proxy:
    # Scale to EUR-like range (1 min ≈ €1000) so z-scores work normally.
    minutes <- if (!is.na(min_col)) suppressWarnings(as.numeric(squad[[min_col]])) else
                 rep(0, nrow(squad))
    minutes[is.na(minutes)] <- 0

    tibble(
      season           = season,
      tm_team_name     = team_name,
      player_name      = if (!is.na(name_col)) as.character(squad[[name_col]]) else NA_character_,
      position         = if (!is.na(pos_col))  as.character(squad[[pos_col]])  else NA_character_,
      market_value_eur = minutes * 1000,   # proxy: 1 min = €1k
      age              = if (!is.na(age_col)) suppressWarnings(as.numeric(squad[[age_col]])) else NA_real_,
      nationality      = if (!is.na(nat_col)) as.character(squad[[nat_col]])  else NA_character_
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
message(sprintf("Wrote %d player rows (%d teams) to %s",
                nrow(rows), n_distinct(rows$tm_team_name), out_path))
