#!/usr/bin/env Rscript
# Export Transfermarkt MLS squad market values via worldfootballR + rvest.
#
# Strategy (two requests per team):
#   1. tm_squad_stats()  → player_name, position (player_pos), age, nationality
#   2. /kader/plus/1 page → player_name, market_value_eur (actual EUR values)
#   Join on player_name; unmatched players get value = 0.
#
# Output schema (CSV, one row per player):
#   season, tm_team_name, player_name, position, market_value_eur, age, nationality

suppressPackageStartupMessages({
  library(worldfootballR)
  library(dplyr)
  library(readr)
  library(stringr)
  library(rvest)
  library(httr)
})

args     <- commandArgs(trailingOnly = TRUE)
season   <- if (length(args) >= 1) as.integer(args[[1]]) else as.integer(format(Sys.Date(), "%Y"))
out_path <- if (length(args) >= 2) args[[2]] else
              sprintf("data/transfermarkt_squad_values_%d.csv", season)

dir.create(dirname(out_path), recursive = TRUE, showWarnings = FALSE)

TM_HEADERS <- c(
  `User-Agent`      = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  `Accept-Language` = "en-US,en;q=0.9",
  `Accept`          = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
)

parse_tm_value <- function(x) {
  # "€5.00m" → 5e6, "€500k" → 5e5, "-" or "" → 0
  x <- str_trim(x)
  if (is.na(x) || x == "" || x == "-") return(0.0)
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

scrape_kader_values <- function(startseite_url) {
  # Convert startseite URL → kader URL with /plus/1 (market value view)
  kader_url <- str_replace(startseite_url, "/startseite/", "/kader/")
  kader_url <- paste0(kader_url, "/plus/1")

  resp <- tryCatch(
    GET(kader_url, add_headers(.headers = TM_HEADERS), timeout(30)),
    error = function(e) { message("  kader fetch error: ", conditionMessage(e)); NULL }
  )
  if (is.null(resp) || status_code(resp) != 200) {
    message("  kader HTTP ", if (!is.null(resp)) status_code(resp) else "NULL")
    return(tibble(player_name = character(), market_value_eur = numeric()))
  }

  page <- tryCatch(
    read_html(content(resp, as = "text", encoding = "UTF-8")),
    error = function(e) NULL
  )
  if (is.null(page)) return(tibble(player_name = character(), market_value_eur = numeric()))

  names_vec <- page %>%
    html_nodes("td.hauptlink a[href*='/profil/spieler/']") %>%
    html_text(trim = TRUE)

  vals_vec <- page %>%
    html_nodes("td.rechts.hauptlink") %>%
    html_text(trim = TRUE)

  n <- min(length(names_vec), length(vals_vec))
  if (n == 0) return(tibble(player_name = character(), market_value_eur = numeric()))

  tibble(
    player_name      = names_vec[seq_len(n)],
    market_value_eur = sapply(vals_vec[seq_len(n)], parse_tm_value, USE.NAMES = FALSE)
  )
}

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
    message("tm_league_team_urls failed: ", conditionMessage(e))
    character(0)
  }
)

if (length(team_urls) == 0) {
  empty_csv()
  quit(status = 0)
}

message(sprintf("Fetching %d teams for season %d...", length(team_urls), season))

rows <- lapply(seq_along(team_urls), function(i) {
  team_url <- team_urls[[i]]
  Sys.sleep(3)

  tryCatch({
    # ── 1. Squad stats: position, age, nationality ──────────────────────────
    stats <- tm_squad_stats(team_url = team_url)
    if (is.null(stats) || nrow(stats) == 0) {
      message(sprintf("  [%d/%d] stats empty: %s", i, length(team_urls), basename(dirname(team_url))))
      return(NULL)
    }
    names(stats) <- tolower(names(stats))

    name_col <- intersect(c("player_name","name","player"),       names(stats))[1]
    pos_col  <- intersect(c("player_pos","position","pos"),       names(stats))[1]
    age_col  <- intersect(c("player_age","age"),                  names(stats))[1]
    nat_col  <- intersect(c("nationality","nat.","country"),      names(stats))[1]
    team_col <- intersect(c("team_name","team","club"),           names(stats))[1]

    if (is.na(name_col) || is.na(pos_col)) return(NULL)

    team_name <- if (!is.na(team_col)) as.character(stats[[team_col]][1]) else
                   basename(dirname(team_url))

    stats_tbl <- tibble(
      player_name = as.character(stats[[name_col]]),
      position    = as.character(stats[[pos_col]]),
      age         = if (!is.na(age_col)) suppressWarnings(as.numeric(stats[[age_col]])) else NA_real_,
      nationality = if (!is.na(nat_col)) as.character(stats[[nat_col]]) else NA_character_
    )

    # ── 2. Kader page: actual EUR market values ─────────────────────────────
    Sys.sleep(2)
    vals_tbl <- scrape_kader_values(team_url)

    # ── 3. Join on player_name ──────────────────────────────────────────────
    result <- stats_tbl %>%
      left_join(vals_tbl, by = "player_name") %>%
      mutate(
        market_value_eur = ifelse(is.na(market_value_eur), 0, market_value_eur),
        season           = season,
        tm_team_name     = team_name
      ) %>%
      select(season, tm_team_name, player_name, position, market_value_eur, age, nationality)

    n_valued <- sum(result$market_value_eur > 0)
    message(sprintf("  [%d/%d] %-30s  %2d players, %2d with EUR value",
                    i, length(team_urls), team_name, nrow(result), n_valued))
    result

  }, error = function(e) {
    message(sprintf("  [%d/%d] ERROR %s: %s",
                    i, length(team_urls), basename(dirname(team_url)), conditionMessage(e)))
    NULL
  })
})

rows <- bind_rows(rows)

if (is.null(rows) || nrow(rows) == 0) {
  empty_csv()
  quit(status = 0)
}

write_csv(rows, out_path)
message(sprintf("\nWrote %d player rows (%d teams) to %s",
                nrow(rows), n_distinct(rows$tm_team_name), out_path))
