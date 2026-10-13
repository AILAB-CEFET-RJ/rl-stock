# Novos vínculos históricos por regime de conta

> Registro **033** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 032](032_account_regimes.md) · Seguinte: [Registro 034](034_historical_smoke_new_accounts.md)

Preparação de 12/10/2026 para `cash_settled` e `intraday_buying_power`, cada um
com os cenários `all_gaps` e `short_gaps`. A grade de observações auditada foi
reutilizada, sem novo download e sem modificar os artefatos anteriores.

## Protocolos, datas e normalização

Cada regime recebeu protocolo próprio, manifestos de elegibilidade por cenário
e dois normalizadores históricos de treino. Os protocolos declaram:

- `environment.account_regime`: o regime daquele conjunto de artefatos;
- `environment.reward_objective = terminal_cash_utility`;
- `episode.wind_down_execution_points = 54`;
- últimos índices de intenção/fill ordinário 334/335 no pregão normal e
  154/155 no reduzido, mantendo a saída 389/209;
- seleção com orçamento completo ainda bloqueada, sem reajuste final.

A reutilização da grade foi permitida somente após verificar que início,
aquecimento, calendário, pontos observados, fechamento, qualidade e partições
continuam iguais. A assinatura do episódio separa os horários da fase de
execução dos horários da grade de observação. Os limites das ordens devem
coincidir com a fase declarada; uma mudança de saída, janela ou qualidade
não recebe essa exceção. O protocolo original de preparação continua copiado
byte a byte e identificado por hash.

| Cenário, em cada regime | Treino | Validação | Teste | Reajuste final previsto |
| --- | ---: | ---: | ---: | ---: |
| `all_gaps` | 50 | 15 | 14 | 65 |
| `short_gaps` | 43 | 14 | 14 | 57 |

Foram reajustadas apenas estatísticas de treino: 14.028 pontos de features no
principal e 11.842 no secundário. Datas, contagens por feature, médias e escalas
ficaram exatamente iguais entre os regimes para o mesmo cenário e iguais aos
normalizadores antigos daquele cenário. Isso é esperado porque as features
normalizadas são de mercado, sem ações ou carteiras. Os três campos adicionais
de conta usam escala fixa pelo capital inicial e não estatísticas de validação.
As estatísticas iguais não dispensam os vínculos novos de protocolo e checkpoint.

## Verificação histórica limitada ao treino

`rl_boleta.historical_profile_verification` seleciona exemplos pela primeira
data, primeiro início causal tardio e maior lacuna de observação no treino,
com desempate cronológico e sem seleção por retorno. Foram usados:

- Principal: 03/03, 14/03 e 10/03 de 2025.
- Secundário: 03/03, 14/03 e 05/03 de 2025.

São quatro datas distintas de mercado, repetidas por cenário/regime, totalizando
12 verificações. Não equivalem a 12 pregões independentes. O roteiro envia
comprar 0,2, vender -1, comprar 1 nas primeiras três transições, depois manter;
a fase automática e os stops conservam precedência. Não se treina uma política.

As 12 execuções terminaram `scheduled_end` em caixa, sem falhas de liquidação
nesses exemplos. Foram conferidos dimensão 15.505, valores finitos, horizonte
terminal zero, identidade do livro-caixa e utilidade acumulada baseada no
caixa terminal. A fase teve 54 transições nas entradas normais; em 14/03,
foram 23 transições automáticas desde o início, sem compras. A data permaneceu
nos dois cenários e nos dois regimes.

Isso demonstra integração nesses exemplos, não ausência de falhas para todos
os inventários ou performance de agentes treinados. O manifesto continua
`training_ready=false` e `full_budget_selection_authorized=false`; a flag
`profile_inputs_verified=true` indica somente esta preparação e verificação.
Não foram ajustados normalizadores de reajuste final, avaliados modelos em
junho/julho ou executados os orçamentos completos.

## Localização e reprodução

A regressão final passou com **258 testes**, sem falhas ou testes pulados.
As verificações novas cobrem preservação da grade, coerência dos horários,
seleção dos exemplos sem retornos, ausência de exemplos, hashes e impedimento
de promover os resultados a autorização de seleção completa.

Artefato principal:
`results/v3_account_campaign_inputs_2026-10-12/manifest.json`.
Cada subdiretório de regime contém `protocol.json`, `design/`, `normalizers/`
e `train_probes/report.json`. A cópia `source_protocol.json` preserva a versão
do template; alterações futuras no arquivo de trabalho não reinterpretam os
perfis congelados. Os normalizadores estão ligados aos próprios manifestos
de elegibilidade. Os relatórios e o manifesto final têm hashes de entradas,
artefatos e código de cada etapa.

Preparar uma saída nova:

```sh
/Users/ebezerra/miniconda3/bin/python3 -m rl_boleta.account_campaigns \
  --prepared-dir results/v3_partial_grid_verified_2026-10-12 \
  --train-audit-dir results/v3_train_gap_diagnostics_2026-10-12 \
  --protocol configs/experimental_protocol_v3.json \
  --account-regime ALL --output-dir results/v3_account_campaign_inputs_novo
```

Para cada regime, executar o normalizador apontando `--design-dir` para seu
`design/` e `--output-dir` para um novo `normalizers/`. Depois executar o módulo
`historical_profile_verification` no ambiente de treinamento com `--normalizer-dir`
apontando esse bundle e `--output-dir` para `train_probes/`. Finalizar a verificação:

```sh
/Users/ebezerra/miniconda3/bin/python3 -m rl_boleta.finalize_account_inputs \
  --directory results/v3_account_campaign_inputs_novo \
  --reference-normalizer-dir results/v3_historical_train_normalizers_2026-10-12
```

A finalização verifica os bundles, hashes, datas dos exemplos e igualdade das
estatísticas de mercado. Recusa exemplos faltantes/duplicados, regimes trocados
ou acesso à validação/teste no relatório. Não promove a preparação a autorização
de pesquisa completa. Arquivos parciais permanecem diagnosticáveis; não são
substituídos nem reutilizados silenciosamente como uma execução completa.

Próximo passo: smoke de treinamento histórico dos quatro algoritmos com esses
novos bundles, em cada cenário/regime, antes de congelar a versão que libera a
seleção de pesquisa e revisar os recursos dos buffers completos. A preparação
dos dois modos não decide que todas as campanhas de 286 ajustes serão rodadas.

Atualização: os [16 smokes históricos foram concluídos](034_historical_smoke_new_accounts.md).
O encoder do replay foi corrigido para manter o contexto da conta; a primeira
execução interrompida foi preservada. Os próximos passos são recursos e
consolidação do protocolo de seleção para os novos perfis.
