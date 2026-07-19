#!/usr/bin/env Rscript
# Export referee tendency stats with worldfootballR / FBref match reports.

suppressPackageStartupMessages({
  library(worldfootballR)
  library(dplyr)
  library(readr)
})

args <- commandArgs(trailingOnly = TRUE)
season <- if (length(args) >= 1) as.integer(args[[1]]) else as.integer(format(Sys.Date(), "%Y"))
out_path <- if (length(args) >= 2) args[[2]] else "data/referee_stats_worldfootballR.csv"

dir.create(dirname(out_path), recursive = TRUE, showWarnings = FALSE)

urls <- fb_match_urls(
  country = "USA",
  gender = "M",
  season_end_year = season,
  tier = "1st",
  time_pause = 3
)

reports <- lapply(urls, function(url) {
  tryCatch({
    report <- fb_match_report(url, time_pause = 3)
    report$match_url <- url
    report
  }, error = function(e) NULL)
})

reports <- bind_rows(reports)

if (nrow(reports) == 0 || !"Referee" %in% names(reports)) {
  write_csv(tibble(
    referee_id = character(),
    name = character(),
    card_rate_per90 = numeric(),
    penalty_rate_per90 = numeric(),
    home_win_rate = numeric(),
    matches_officiated = integer()
  ), out_path)
  quit(status = 0)
}

summary <- reports %>%
  filter(!is.na(Referee), Referee != "") %>%
  group_by(name = Referee) %>%
  summarise(
    referee_id = gsub("[^A-Za-z0-9]+", "_", tolower(first(name))),
    card_rate_per90 = NA_real_,
    penalty_rate_per90 = NA_real_,
    home_win_rate = NA_real_,
    matches_officiated = n(),
    .groups = "drop"
  ) %>%
  select(referee_id, name, card_rate_per90, penalty_rate_per90, home_win_rate, matches_officiated)

write_csv(summary, out_path)
