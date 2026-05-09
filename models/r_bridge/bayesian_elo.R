#!/usr/bin/env Rscript
# Bayesian hierarchical Poisson model for MLS match prediction.
# Uses brms with ELO ratings as informative priors for team attack/defense strength.
# Input:  data/bayes_input.csv  (match history + ELO features)
# Output: data/bayes_output.csv (posterior predictive probabilities per upcoming match)
#         data/bayes_params.csv (team attack/defense posterior means + SDs)

suppressPackageStartupMessages({
  library(brms)
  library(posterior)
  library(dplyr)
  library(tidyr)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
repo_root <- if (length(args) > 0) args[1] else "."
cfg_path  <- file.path(repo_root, "config", "bayes_config.json")
cfg <- if (file.exists(cfg_path)) fromJSON(cfg_path) else list()

chains        <- as.integer(cfg$chains %||% 4)
iter          <- as.integer(cfg$iter %||% 2000)
cores         <- as.integer(cfg$cores %||% 4)
adapt_delta   <- as.numeric(cfg$adapt_delta %||% 0.95)
elo_scale     <- as.numeric(cfg$elo_scale_factor %||% 400)
expansion_sd_mult <- as.numeric(cfg$expansion_prior_sd_multiplier %||% 2.0)

`%||%` <- function(a, b) if (!is.null(a)) a else b

# ── Load data ─────────────────────────────────────────────────────────────────
train_path    <- file.path(repo_root, "data", "bayes_input_train.csv")
predict_path  <- file.path(repo_root, "data", "bayes_input_predict.csv")

if (!file.exists(train_path)) {
  stop("Training data not found: ", train_path)
}

train <- read.csv(train_path, stringsAsFactors = FALSE)
train$date <- as.Date(train$date)

# ── Team index ────────────────────────────────────────────────────────────────
all_teams <- sort(unique(c(train$home_team, train$away_team)))
n_teams   <- length(all_teams)
team_idx  <- setNames(seq_along(all_teams), all_teams)

train$home_team_idx <- team_idx[train$home_team]
train$away_team_idx <- team_idx[train$away_team]

# ── Compute ELO-based priors for each team ────────────────────────────────────
# Map ELO to a log-scale prior mean: teams above 1500 should score more.
elo_prior_means <- sapply(all_teams, function(t) {
  elo <- if ("home_elo" %in% names(train)) {
    latest <- train %>%
      filter(home_team == t | away_team == t) %>%
      arrange(desc(date)) %>%
      slice(1)
    if (nrow(latest) == 0) 1500
    else if (latest$home_team == t) latest$home_elo else latest$away_elo
  } else 1500
  (elo - 1500) / elo_scale  # normalised to ~[-0.5, 0.5] range
})

expansion_flags <- train %>%
  group_by(team = home_team) %>%
  summarise(is_expansion = first(is_expansion_home), .groups = "drop") %>%
  bind_rows(
    train %>% group_by(team = away_team) %>%
      summarise(is_expansion = first(is_expansion_away), .groups = "drop")
  ) %>%
  group_by(team) %>%
  summarise(is_expansion = max(is_expansion, na.rm = TRUE), .groups = "drop")

team_df <- data.frame(
  team      = all_teams,
  elo_prior = elo_prior_means,
  is_exp    = expansion_flags$is_expansion[match(all_teams, expansion_flags$team)]
)
team_df$is_exp[is.na(team_df$is_exp)] <- 0

# ── Priors ────────────────────────────────────────────────────────────────────
# Attack and defense: Normal(elo_scaled_mean, sigma)
# Expansion teams get sigma * expansion_sd_mult
base_sigma <- 0.3

attack_priors <- team_df$elo_prior
defense_priors <- -team_df$elo_prior  # Stronger attack → weaker defense tendency negated
sigma_vec <- ifelse(team_df$is_exp == 1, base_sigma * expansion_sd_mult, base_sigma)

# ── Prepare Stan data ─────────────────────────────────────────────────────────
stan_data <- list(
  N          = nrow(train),
  n_teams    = n_teams,
  home_team  = train$home_team_idx,
  away_team  = train$away_team_idx,
  home_goals = as.integer(train$home_goals),
  away_goals = as.integer(train$away_goals),
  home_adv_prior_mean = 0.3,
  attack_prior_mean  = attack_priors,
  defense_prior_mean = defense_priors,
  sigma_atk  = sigma_vec,
  sigma_def  = sigma_vec
)

# ── Stan model code ───────────────────────────────────────────────────────────
stan_code <- "
data {
  int<lower=1> N;
  int<lower=1> n_teams;
  array[N] int<lower=1, upper=n_teams> home_team;
  array[N] int<lower=1, upper=n_teams> away_team;
  array[N] int<lower=0> home_goals;
  array[N] int<lower=0> away_goals;
  real home_adv_prior_mean;
  vector[n_teams] attack_prior_mean;
  vector[n_teams] defense_prior_mean;
  vector<lower=0>[n_teams] sigma_atk;
  vector<lower=0>[n_teams] sigma_def;
}
parameters {
  real mu;                         // baseline log-scoring rate
  real home_advantage;             // global home advantage on log scale
  vector[n_teams] attack;          // team attack strengths
  vector[n_teams] defense;         // team defense strengths (positive = weaker)
}
model {
  mu             ~ normal(0.2, 0.5);
  home_advantage ~ normal(home_adv_prior_mean, 0.2);
  for (t in 1:n_teams) {
    attack[t]  ~ normal(attack_prior_mean[t],  sigma_atk[t]);
    defense[t] ~ normal(defense_prior_mean[t], sigma_def[t]);
  }
  for (n in 1:N) {
    real lambda_h = exp(mu + home_advantage + attack[home_team[n]] - defense[away_team[n]]);
    real lambda_a = exp(mu + attack[away_team[n]] - defense[home_team[n]]);
    home_goals[n] ~ poisson(lambda_h);
    away_goals[n] ~ poisson(lambda_a);
  }
}
generated quantities {
  array[N] int home_goals_rep;
  array[N] int away_goals_rep;
  for (n in 1:N) {
    real lambda_h = exp(mu + home_advantage + attack[home_team[n]] - defense[away_team[n]]);
    real lambda_a = exp(mu + attack[away_team[n]] - defense[home_team[n]]);
    home_goals_rep[n] = poisson_rng(lambda_h);
    away_goals_rep[n] = poisson_rng(lambda_a);
  }
}
"

# ── Fit model ─────────────────────────────────────────────────────────────────
model_rds_path <- file.path(repo_root, "data", "bayesian_model.rds")

if (file.exists(model_rds_path)) {
  cat("Loading cached Stan model...\n")
  fit <- readRDS(model_rds_path)
  # Re-run with fresh data
  fit <- update(fit, newdata = stan_data, iter = iter, chains = chains, cores = cores,
                control = list(adapt_delta = adapt_delta), refresh = 0)
} else {
  cat("Compiling and fitting Stan model (first run may take several minutes)...\n")
  fit <- stan(
    model_code = stan_code,
    data       = stan_data,
    iter       = iter,
    chains     = chains,
    cores      = cores,
    control    = list(adapt_delta = adapt_delta),
    refresh    = 100
  )
  saveRDS(fit, model_rds_path)
}

# ── Extract posterior team parameters ─────────────────────────────────────────
draws <- as_draws_df(fit)

param_rows <- lapply(seq_along(all_teams), function(t) {
  atk_col <- paste0("attack[", t, "]")
  def_col  <- paste0("defense[", t, "]")
  data.frame(
    team         = all_teams[t],
    attack_mean  = mean(draws[[atk_col]], na.rm = TRUE),
    attack_sd    = sd(draws[[atk_col]], na.rm = TRUE),
    defense_mean = mean(draws[[def_col]], na.rm = TRUE),
    defense_sd   = sd(draws[[def_col]], na.rm = TRUE)
  )
})

params_df <- do.call(rbind, param_rows)
mu_mean        <- mean(draws$mu, na.rm = TRUE)
home_adv_mean  <- mean(draws$home_advantage, na.rm = TRUE)
params_df$mu        <- mu_mean
params_df$home_adv  <- home_adv_mean

write.csv(params_df, file.path(repo_root, "data", "bayes_params.csv"), row.names = FALSE)
cat("Saved team parameter posteriors to data/bayes_params.csv\n")

# ── Predict upcoming matches ───────────────────────────────────────────────────
if (file.exists(predict_path)) {
  predict_df <- read.csv(predict_path, stringsAsFactors = FALSE)
  max_goals  <- 10
  n_draws    <- nrow(draws)

  out_rows <- lapply(seq_len(nrow(predict_df)), function(i) {
    ht <- predict_df$home_team[i]
    at <- predict_df$away_team[i]
    mid <- predict_df$match_id[i]

    h_atk_col <- paste0("attack[",  team_idx[ht], "]")
    h_def_col  <- paste0("defense[", team_idx[ht], "]")
    a_atk_col  <- paste0("attack[",  team_idx[at], "]")
    a_def_col  <- paste0("defense[", team_idx[at], "]")

    if (any(!c(h_atk_col, a_atk_col) %in% names(draws))) {
      # Unknown team: use league averages
      lam_h_vec <- exp(draws$mu + draws$home_advantage)
      lam_a_vec <- exp(draws$mu)
    } else {
      lam_h_vec <- exp(draws$mu + draws$home_advantage +
                       draws[[h_atk_col]] - draws[[a_def_col]])
      lam_a_vec <- exp(draws$mu + draws[[a_atk_col]] - draws[[h_def_col]])
    }

    # Monte Carlo score probabilities
    sim_h <- rpois(n_draws, lam_h_vec)
    sim_a <- rpois(n_draws, lam_a_vec)

    prob_home  <- mean(sim_h > sim_a)
    prob_draw  <- mean(sim_h == sim_a)
    prob_away  <- mean(sim_h < sim_a)
    prob_over  <- mean((sim_h + sim_a) > 2.5)
    prob_under <- mean((sim_h + sim_a) <= 2.5)

    data.frame(
      match_id   = mid,
      prob_home  = prob_home,
      prob_draw  = prob_draw,
      prob_away  = prob_away,
      prob_over  = prob_over,
      prob_under = prob_under
    )
  })

  out_df <- do.call(rbind, out_rows)
  write.csv(out_df, file.path(repo_root, "data", "bayes_output.csv"), row.names = FALSE)
  cat(sprintf("Saved predictions for %d upcoming matches to data/bayes_output.csv\n", nrow(out_df)))
} else {
  cat("No predict input file found; skipping prediction step.\n")
}

cat("Bayesian model run complete.\n")
