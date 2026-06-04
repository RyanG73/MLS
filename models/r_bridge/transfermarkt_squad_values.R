#!/usr/bin/env Rscript
# Export Transfermarkt MLS squad market values via worldfootballR.
#
# Output schema (CSV, one row per player):
#   season, tm_team_name, player_name, position, market_value_eur, age, nationality
#
# Downstream aggregation (positional splits, value-weighted age, etc.) is done
# in scripts/import_transfermarkt.py so that all the PELE-style logic stays in Python.

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
  tm_league_team_urls(country_name = "USA", start_year = season),
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

    # Normalise column names for robustness across worldfootballR versions
    names(squad) <- tolower(names(squad))

    val_col  <- intersect(c("player_market_value_euro", "market_value_euro",
                             "player_market_value", "market_value_euro_mln"),
                           names(squad))[1]
    age_col  <- intersect(c("age", "player_age"), names(squad))[1]
    nat_col  <- intersect(c("nationality", "nat.", "country"), names(squad))[1]
    pos_col  <- intersect(c("position", "player_position", "pos", "player_pos"),
                           names(squad))[1]
    name_col <- intersect(c("player_name", "name", "player"), names(squad))[1]
    team_col <- intersect(c("team_name", "team", "club"), names(squad))[1]

    if (is.na(val_col)) return(NULL)

    vals <- suppressWarnings(as.numeric(squad[[val_col]]))
    vals[is.na(vals)] <- 0

    team_name <- if (!is.na(team_col)) {
      as.character(squad[[team_col]][1])
    } else {
      basename(dirname(team_url))
    }

    tibble(
      season           = season,
      tm_team_name     = team_name,
      player_name      = if (!is.na(name_col)) as.character(squad[[name_col]]) else NA_character_,
      position         = if (!is.na(pos_col))  as.character(squad[[pos_col]])  else NA_character_,
      market_value_eur = vals,
      age              = if (!is.na(age_col))  suppressWarnings(as.numeric(squad[[age_col]])) else NA_real_,
      nationality      = if (!is.na(nat_col))  as.character(squad[[nat_col]])  else NA_character_
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
