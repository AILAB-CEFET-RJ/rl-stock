# Treinos históricos curtos com os novos regimes

> Registro **034** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 033](033_account_campaign_inputs.md) · Seguinte: [Registro 035](035_docs_log_refactor.md)

Verificação de 12/10/2026 após corrigir o encoder da avaliação congelada.

## Falha e correção

O treino usava os três campos adicionais da conta, mas o replay posterior ao
carregamento do checkpoint construía um `MaskedEncoder` com a opção padrão
sem contexto de conta. A observação de uma conta nova era corretamente
rejeitada com `encoder must expose account buying power`.

O replay agora usa `CachedMaskedEncoder` com o normalizador recarregado e a
mesma opção de contexto do ambiente histórico. As janelas de mercado são
calculadas uma vez por sessão; poder de compra, receitas pendentes e carteira
continuam sendo atualizados a cada observação. Os relatórios passam a registrar
explicitamente regime, objetivo de recompensa e fase de saída.

O diretório interrompido
`results/v3_historical_smoke_cash_settled_2026-10-12/` fica preservado, com
manifesto de falha e o checkpoint produzido antes da avaliação. Os pesos de
PPO desse checkpoint foram exatamente iguais aos da repetição corrigida,
com mesma semente e inputs. A correção não alterou as regras financeiras.

Um teste de regressão agora completa treinamento PPO, gravação/carregamento
e avaliação congelada nos dois regimes usando dados fabricados ligados a
manifestos. Ele verifica que o replay efetivamente usa o contexto da conta.
A regressão completa passou: **259 testes**, sem falhas ou testes pulados.

## Execução histórica corrigida

Foram executados 16 ajustes: quatro algoritmos × dois cenários × dois regimes,
com semente zero e 384 transições solicitadas por ajuste. A2C realizou 385
para completar os rollouts; total solicitado 6.144 e realizado 6.148.

Todos atualizaram o ator, mantiveram pesos finitos e produziram previsões
idênticas após recarregar checkpoints. Normalizadores e hashes de inputs,
código e artefatos foram conferidos. SAC/DDPG passaram pela auditoria de
horizonte terminal zero e ausência de bootstrap de truncamento temporal.

Houve 24 episódios concluídos durante o aprendizado e 40 replays congelados
nas datas de treino amostradas, sem falhas de liquidação nessas execuções.
São repetições em apenas quatro datas distintas: 14/04, 25/04, 29/04 e
19/05/2025. Não representam 40 pregões independentes nem garantem liquidação
em outras datas ou inventários. O orçamento curto verifica integração, não
escolhe modelos ou demonstra desempenho econômico de pesquisa.

Validação e julho não foram avaliados. Não foram gerados normalizadores de
reajuste final nem checkpoints de orçamento completo.

## Artefatos

- `results/v3_historical_smoke_cash_settled_fixed_2026-10-12/`
- `results/v3_historical_smoke_intraday_buying_power_fixed_2026-10-12/`

Cada conjunto contém manifesto, `suite_report.json` e relatórios/checkpoints
por cenário e algoritmo. Não é necessário repetir o comando anterior para
concluir esta verificação. Para uma nova repetição, usar diretórios novos.

Próximo passo: revisar a disponibilidade de recursos para os buffers completos
e consolidar a versão de protocolo que permite a seleção por validação.
O diagnóstico curto de seleção antigo não decide configurações para os novos
regimes, fase e objetivo; sua ordenação continua preservada como histórica.
