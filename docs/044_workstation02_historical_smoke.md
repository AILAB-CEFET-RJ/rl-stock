# Treinos históricos curtos na workstation02

> Registro **044** · Data de referência: **2026-10-13** · [Índice](README.md)
> Anterior: [Registro 043](043_workstation02_account_inputs.md) · Seguinte: [Registro 045](045_compute_benchmark.md).

O usuário executou `historical_training` com os bundles reconstruídos no destino,
seed 0, 384 passos solicitados por ajuste, quatro algoritmos, dois cenários e
dois regimes de conta, sequencialmente em CPU. As saídas são
`results/ws02_historical_smoke_cash_settled_2026-10-13/` e
`results/ws02_historical_smoke_intraday_buying_power_2026-10-13/`.

Os 16 resumos recebidos registram `historical_train_integration_only`, atualização
do ator e previsão determinística idêntica após salvar/recarregar o modelo.
Por cenário/regime, PPO realizou 384 passos e 12 atualizações, A2C 385 e 77,
SAC e DDPG 384 e 352 cada. Foram 6.144 passos solicitados e 6.148 realizados;
o passo adicional de cada A2C completa o rollout de cinco passos.

SAC e DDPG reportaram um terminal no cenário principal e dois no secundário,
com horizonte terminal zero e ausência de bootstrap de limite temporal em
todos os casos. O runner exige pesos finitos e conclusão de sessão para
produzir esses relatórios; os replays congelados usam apenas datas de treino.

Esses resumos demonstram integração com o PyTorch da workstation, não seleção
de modelos ou generalização. Um smoke pode reportar sucesso técnico mesmo com
`liquidation_failure` no replay; o encerramento deve ser conferido nos relatórios
completos.

O usuário também executou o leitor dos dois manifestos e dos 16 relatórios.
Ambos os manifestos confirmam `historical_train_smoke_completed`, com oito
relatórios por regime e dispositivo CPU. Cada regime teve 12 episódios
concluídos no aprendizado e 20 replays congelados, todos `scheduled_end`,
sem posições residuais. São **24 episódios concluídos e 40 replays** somados,
sem falhas de liquidação nessas execuções; essas contagens incluem repetições
entre cenários e regimes, não pregões independentes.

## Tempos de treinamento em CPU

Valores de `wall_seconds` enviados pelo usuário, arredondados a milissegundos:

| Cenário | Algoritmo | cash_settled (s) | intraday_buying_power (s) |
| --- | --- | ---: | ---: |
| all_gaps | PPO | 2,315 | 2,328 |
| all_gaps | A2C | 2,586 | 2,646 |
| all_gaps | SAC | 8,532 | 8,596 |
| all_gaps | DDPG | 6,369 | 6,360 |
| short_gaps | PPO | 2,972 | 3,137 |
| short_gaps | A2C | 3,301 | 3,463 |
| short_gaps | SAC | 9,246 | 9,411 |
| short_gaps | DDPG | 7,000 | 7,161 |

Os tempos cobrem apenas `model.learn`,
não todo o preparo, IO, salvamento ou avaliação; não extrapolá-los linearmente
para a campanha completa. Ainda faltam configurar CPU/CUDA no pipeline e
medir os parâmetros completos, inclusive buffers e recursos. A implementação
e a campanha de benchmark ainda não foram executadas. Os orçamentos completos
de seleção e reajuste final permanecem bloqueados.
