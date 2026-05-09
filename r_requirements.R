#!/usr/bin/env Rscript
# Run once on the Raspberry Pi to install all required R packages.
# Usage: Rscript r_requirements.R

options(repos = c(CRAN = "https://cloud.r-project.org"))

required_packages <- c(
  "brms",           # Bayesian regression models via Stan
  "posterior",      # Posterior summaries and draws manipulation
  "worldfootballR", # FBref / Transfermarkt data scraping
  "tidyverse",      # Data manipulation (dplyr, tidyr, ggplot2)
  "jsonlite",       # JSON read/write for Python <-> R bridge
  "data.table",     # Fast data operations
  "lubridate"       # Date manipulation
)

for (pkg in required_packages) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    message(sprintf("Installing %s ...", pkg))
    install.packages(pkg)
  } else {
    message(sprintf("%s already installed.", pkg))
  }
}

# worldfootballR may need GitHub version for latest MLS data
if (packageVersion("worldfootballR") < "0.6.4") {
  message("Updating worldfootballR from GitHub...")
  if (!requireNamespace("remotes", quietly = TRUE)) install.packages("remotes")
  remotes::install_github("JaseZiv/worldfootballR")
}

message("All R packages installed successfully.")
