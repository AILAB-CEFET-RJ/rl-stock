#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
python_bin="$HOME/venvs/rl-stock-ws02/bin/python"
campaign_root="results/ws02_ppo_remaining_seeds_v1"
normalizers="results/ws02_account_campaign_inputs_2026-10-13/cash_settled/normalizers"

for seed in 1 2; do
  if [[ -e "$campaign_root/seed$seed" || -e "$campaign_root/validation_seed$seed" ]]; then
    echo "Saída existente para seed $seed; preserve a execução anterior." >&2
    exit 1
  fi
done

for seed in 1 2; do
  timeout 10800s env PYTHONNOUSERSITE=1 "$python_bin" -u -m rl_boleta.first_tuning \
    --seed "$seed" --output-root "$campaign_root/seed$seed"
  timeout 900s env PYTHONNOUSERSITE=1 "$python_bin" -u -m rl_boleta.checkpoint_validation \
    --checkpoint-dir "$campaign_root/seed$seed/PPO_w128_lr1e-4_seed$seed" \
    --normalizer-dir "$normalizers" \
    --output-dir "$campaign_root/validation_seed$seed" --device cuda
done

echo '{"status":"remaining_seeds_completed"}'
