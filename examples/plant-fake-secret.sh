#!/usr/bin/env bash
# Writes a FAKE, randomly generated secret into a demo app so the secret-scanning gate fails.
# Generated at demo time on purpose: nothing secret-shaped is ever committed to this repo.
# Commit the result only to a throwaway branch in your Azure DevOps demo project.
set -euo pipefail
target="${1:-examples/node-demo}"
mkdir -p "$target/config"
echo "STRIPE_SECRET_KEY=sk_live_$(openssl rand -hex 16)" > "$target/config/payments.env"
echo "Planted fake secret in $target/config/payments.env"
