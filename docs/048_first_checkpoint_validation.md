# Avaliação congelada do primeiro checkpoint

> Registro **048** · Data de referência: **2026-10-13** · [Índice](README.md)
> Anterior: [Registro 047](047_first_tuning_checkpoint.md) · Seguinte: [Registro 049](049_remaining_ppo_seeds.md).

Foi implementado `rl_boleta.checkpoint_validation` para avaliar na workstation02
o PPO `cash_settled/all_gaps`, largura 128, LR 1e-4, seed 0, após o ajuste
completo. A execução histórica na workstation02 foi concluída conforme o resumo
colado pelo usuário, registrado abaixo. Os testes locais verificam o executor,
sem produzir resultados financeiros do checkpoint.

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

## Resultado informado da workstation02

O usuário reportou `checkpoint_validation_completed` para PPO, `all_gaps`,
largura 128, LR 0,0001 e seed 0. Foram preservados os 15 pregões para o modelo
e ambos os controles. Todos os três terminaram em caixa em todas as datas,
sem falhas de liquidação. Retornos realizados e marcados coincidem.

| Estratégia | Retorno líquido médio por pregão | Drawdown marcado máximo médio por pregão | Taxas médias por pregão (USD) | Giro médio / capital |
| --- | ---: | ---: | ---: | ---: |
| PPO | -0,0949962861% | 0,3183808526% | 19,9849527333 | 1,9984952733 |
| Permanecer em caixa | 0% | 0% | 0 | 0 |
| Compra inicial com alocação igual | -0,1759146182% | 0,5306959976% | 18,3846182 | 1,83846182 |

O PPO teve perda média menor que a compra inicial por 0,0809183321 ponto
percentual (aproximadamente 8,09 pontos-base), mas ficou abaixo de permanecer
em caixa. Com capital inicial de USD 100.000 por episódio, sua perda líquida
média foi de aproximadamente USD 95 por pregão. A diferença entre estratégias
é descritiva: o resumo não permite avaliar dispersão, concentração em datas
específicas ou significância estatística.

O resumo confirma `test_prices_accessed=false` e
`eligible_for_final_refit=false`. A admissibilidade observada refere-se a esta
seed nestas datas, sem garantia futura ou conclusão de seleção do candidato.

O relatório completo foi copiado para
`results/workstation02_first_validation/report.json` e inspecionado localmente.
O próximo ajuste mantém a configuração registrada
e completa as seeds 1 e 2, sem reajustar hiperparâmetros em resposta a esse
resultado isolado. As demais configurações da campanha permanecem pendentes.

## Inspeção do relatório completo copiado

SHA-256 do relatório recebido:
`10c380c8eddd0922e3e2608da7428fe3e6777de5c70d27198c7c2c6bbcf28dff`.
Os oito hashes de código coincidem com os arquivos locais. Os hashes do
checkpoint, normalizador e relatório de treinamento registrados no avaliador
coincidem com os três artefatos anteriormente copiados. Os caminhos absolutos
dos datasets são da workstation02; seus arquivos não foram reverificados no
Mac. O relatório declara pesos e normalizador preservados durante a avaliação.

As três estratégias contêm exatamente as mesmas 15 datas, em ordem. Todos
os resultados declaram `scheduled_end`, carteira zerada e igualdade entre
retorno marcado e realizado. As cinco médias de cada estratégia foram
recalculadas dos registros diários com Decimal de precisão 50 e coincidem
exatamente com os resumos. Não foi executada nova inferência no Mac.

| Pregão | PPO: retorno líquido (%) | Compra inicial: retorno líquido (%) |
| --- | ---: | ---: |
| 2025-06-02 | -0,117781 | 0,367305 |
| 2025-06-03 | 0,067758 | 0,246594 |
| 2025-06-04 | 0,118885 | -0,105569 |
| 2025-06-05 | -0,276528 | -0,416438 |
| 2025-06-06 | 0,490446 | -0,011450 |
| 2025-06-09 | -0,134810 | -0,198930 |
| 2025-06-11 | -1,012768 | -1,404878 |
| 2025-06-12 | -0,106472 | -0,094231 |
| 2025-06-13 | -0,066211 | -0,704825 |
| 2025-06-16 | 0,099806 | 0,067655 |
| 2025-06-17 | -0,468321 | -0,952234 |
| 2025-06-23 | 0,300932 | 0,491511 |
| 2025-06-26 | -0,082018 | -0,044602 |
| 2025-06-27 | -0,114010 | 0,000809 |
| 2025-06-30 | -0,123854 | 0,120564 |

O PPO teve cinco pregões positivos e dez negativos; mediana -0,106472%.
Superou a compra inicial em oito das 15 datas. O pior dia, 11/06, perdeu
USD 1.012,77 e responde por aproximadamente 71,1% da perda líquida somada
de USD 1.424,94 nos 15 episódios independentes. Essa soma não é retorno
composto de uma carteira contínua. Os outros 14 dias também tiveram média
negativa (-0,029441%); esse cálculo é apenas diagnóstico, sem excluir a data
do resultado oficial. O melhor dia foi 06/06 (+0,490446%).

O giro médio próximo de duas vezes o capital é compatível com compras e
vendas de volume próximo ao capital inicial, mas não identifica frequência,
concentração por ativo ou horários das decisões. O relatório agregado diário
não contém a trajetória de ações necessária para diagnosticar a política.

A idade máxima observada de marcação de posições mantidas foi de 125 s.
Essa métrica usa preços carregados para valorar posições durante lacunas;
não é idade de um livro usado para execução. O replay continua filtrando
livros executáveis pelo limite de 60 s. O relatório diário não permite
reconstruir individualmente todos os fills para uma auditoria independente
da execução.
