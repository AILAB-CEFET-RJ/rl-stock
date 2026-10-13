# Avaliação congelada do primeiro checkpoint

> Registro **048** · Data de referência: **2026-10-13** · [Índice](README.md)
> Anterior: [Registro 047](047_first_tuning_checkpoint.md) · Seguinte: próxima entrada 049, ainda não criada.

Foi implementado `rl_boleta.checkpoint_validation` para avaliar na workstation02
o PPO `cash_settled/all_gaps`, largura 128, LR 1e-4, seed 0, após o ajuste
completo. A execução histórica desta avaliação ainda está pendente; os testes
locais verificam o executor, sem produzir resultados financeiros do checkpoint.

O executor exige hashes válidos dos artefatos, normalizador idêntico ao bundle
original, orçamento completo e dimensões compatíveis. Usa inferência
determinística em CUDA, sem atualizações ou novo ajuste da normalização.
Confere novamente os hashes e a igualdade dos pesos ao terminar. Recusa
diretórios de saída existentes.

As datas são exclusivamente as 15 datas de validação elegíveis e congeladas
para `all_gaps`. Cada pregão permanece no relatório, incluindo falhas de
liquidação e posições residuais. O relatório registra retornos marcados e
realizados, custos, giro e drawdown marcado por dia. A média de retorno realizado
só é calculada quando todos os pregões terminam em caixa e atendem às regras
de admissibilidade; uma falha não é removida do denominador.

Com `--with-baselines`, executa também permanecer em caixa e compra inicial
com alocação igual, nas mesmas datas e com as mesmas regras econômicas e de
encerramento. Esses dois controles não substituem a campanha completa de
baselines prevista no protocolo.

Esta é uma avaliação de uma configuração e uma seed. O relatório mantém
`model_selection_completed=false`, `eligible_for_final_refit=false` e
`test_prices_accessed=false`. A admissibilidade observada neste conjunto
não representa conclusão sobre as três seeds nem garantia de liquidação futura.

## Execução na workstation02

Depois de publicar esta versão e atualizar a branch na workstation02:

```bash
cd "$HOME/ailab/rl-stock"
git pull --ff-only
set -o pipefail
timeout 900s env PYTHONNOUSERSITE=1 \
  "$HOME/venvs/rl-stock-ws02/bin/python" -u -m rl_boleta.checkpoint_validation \
  --checkpoint-dir results/ws02_first_tuning_v1/PPO_w128_lr1e-4_seed0 \
  --normalizer-dir results/ws02_account_campaign_inputs_2026-10-13/cash_settled/normalizers \
  --output-dir results/ws02_first_validation_v1 \
  --device cuda --with-baselines \
  2>&1 | tee results/ws02_first_validation_v1.log
```

O limite de 900 segundos é uma proteção operacional, não uma estimativa de
duração. Uma interrupção exige saída nova para repetir a avaliação. O resumo
final deve declarar `checkpoint_validation_completed`; o relatório detalhado
fica em `results/ws02_first_validation_v1/report.json`.

## Verificação local

Cinco testes novos verificam preservação de falhas econômicas e denominadores,
controle de hashes e normalizador, proteção da saída existente e cálculo de
retorno realizado. A regressão completa passou: **282 testes em 101,526 s**.
Os links da documentação e `git diff --check` também passaram.
