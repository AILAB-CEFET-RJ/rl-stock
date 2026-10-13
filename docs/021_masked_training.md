# Integração sintética v3 com Gymnasium e quatro algoritmos

> Registro **021** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 020](020_masked_observations.md) · Seguinte: [Registro 022](022_masked_preparation_and_baselines.md)

O ambiente `rl_boleta.masked_env.MaskedTrainingEnv` conecta o controlador
com lacunas ao encoder de 15.502 entradas para 18 ativos. Os construtores
existentes de PPO, A2C, SAC e DDPG são reutilizados com suas configurações
explícitas. A implementação v2 e o paper permanecem inalterados.

O treinamento disponível nesta etapa aceita exclusivamente sessões sintéticas,
com início causal e livros de todos os ativos na saída comum. A falta de dados
no interior do pregão produz observações com máscaras, preservando carteira e
relógio. Não produz truncamento Gymnasium nem reinicialização do episódio.
As estatísticas de normalização devem corresponder exatamente às datas de
ajuste do ambiente e ficam congeladas durante execução e avaliação.

Cada ação tem 18 componentes finitos, limitados a [-1, 1]. O núcleo aplica as
máscaras e cancela componentes sem livro na execução. Nos intervalos
reservados à liquidação ou à parada já acionada, a ação do agente é ignorada.

## Encerramento e aprendizado

Saída programada, parada econômica com carteira em caixa e falha de liquidação
por profundidade insuficiente são encerramentos financeiros verdadeiros:
`terminated=True`, `truncated=False`, horizonte restante zero na observação
terminal. A falha mantém as posições e distingue retorno marcado de retorno
realizado em caixa. Não recebe artificialmente um estado com posições zeradas.

Ausência de livros na saída é interrupção por dados, registrada pelo replay
de avaliação. É recusada antes do treinamento. Se surgir inesperadamente
após a validação inicial, o ambiente lança erro antes de devolver a transição
ao algoritmo. Isso impede o tratamento automático de truncamentos como
limites de tempo com valor futuro a estimar pelo SB3. Não é uma regra para
remover episódios com perdas ou posições restantes.

## Execução reproduzível

Use as dependências de `requirements-training.txt` em ambiente compatível.
Nesta máquina, as dependências já preparadas permitem executar:

```sh
caffeinate -i env \
  PYTHONPATH=/private/tmp/rl-stock-training-deps \
  MPLCONFIGDIR=/private/tmp/rl-stock-matplotlib \
  /Users/ebezerra/miniconda3/envs/ailab/bin/python \
  -m rl_boleta.masked_training --synthetic-smoke --algorithm ALL \
  --steps 384 --seed 0 --output results/v3_training_smoke_2026-10-12
```

O diretório de saída deve ser novo. Os caminhos temporários são específicos
desta máquina; `caffeinate` evita suspensão por inatividade no macOS.

O teste usa três pregões artificiais com entrada às 09:52, 367 transições por
sessão, uma lacuna individual de 36 minutos e cinco minutos sem livro de
nenhum ativo. Não reutiliza dados nem resultados da dissertação.

Cada algoritmo deve efetivamente atualizar o ator, manter parâmetros finitos,
completar uma sessão e atravessar estados com 0, 17 e 18 ativos disponíveis.
Após salvar/carregar, a previsão determinística deve ser idêntica. As
observações terminais são auditadas em todos os algoritmos; SAC e DDPG têm
também auditoria das flags e do horizonte no buffer de replay.

O comando grava modelos, normalizadores, configurações efetivas, versões,
hashes e relatórios por algoritmo, além de `suite_report.json`. A avaliação
congelada nesses três dias verifica integração; não mede generalização ou
qualidade financeira. O orçamento curto e os ajustes de smoke estão
registrados como desvios do experimento completo.

Os testes do adaptador também cobrem liquidação com resíduos, parada econômica
antecipada, ausência de dados na saída, validação de toda a cauda de features,
recusa de sessões históricas, reprodução por semente e avaliação de pregão
curto com normalização congelada.

## Validação desta etapa

A regressão completa passou: **178 testes, sem falhas ou testes pulados**,
incluindo nove testes novos do adaptador. O smoke dos quatro algoritmos passou
com 18 ativos e 15.502 entradas:

| Algoritmo | Transições | Atualizações |
|---|---:|---:|
| PPO | 384 | 12 |
| A2C | 385 | 77 |
| SAC | 384 | 352 |
| DDPG | 384 | 352 |

A transição adicional do A2C completa seu rollout de cinco passos; esse excesso
é permitido e registrado. Todos atualizaram o ator, atravessaram as lacunas,
completaram uma sessão e reproduziram a previsão após recarregar. SAC e DDPG
registraram um terminal no replay, com horizonte zero e sem bootstrap por
limite de tempo. Os hashes de código e artefatos foram conferidos.

Resultados locais: `results/v3_training_smoke_2026-10-12/suite_report.json`,
com relatórios detalhados nas subpastas de cada algoritmo. Esses arquivos
permanecem ignorados pelo Git.

## Pendências para experimentos históricos

Ainda faltam preparação da grade parcial a partir dos dados auditados,
baselines v3, congelamento da regra para lacunas longas e manifesto de
eligibilidade. A incerteza sobre o horário de mercado dos livros permanece.
O protocolo conserva `draft_for_review_not_executable` para experimentos
históricos e `real_training_ready=False`. Treinos sintéticos não certificam
os 79 candidatos de cobertura como episódios utilizáveis.

## Atualização: seleção condicional de datas

A [regra de lacunas e a elegibilidade condicional](023_gap_rule_and_conditional_eligibility.md)
foram congeladas no rascunho v3 na etapa seguinte. A regra principal não
acrescenta exclusão por duração; limites predefinidos são sensibilidades dos
mesmos modelos congelados. A seleção contém 50/15/14 dias e 65 de reajuste final.
Normalização e fitting históricos continuam pendentes. Os relatos de pendências
acima descrevem o estado na conclusão original desta etapa.
