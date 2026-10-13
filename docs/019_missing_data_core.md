# Núcleo econômico e controlador diário v3

> Registro **019** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 018](018_protocol_v3_proposal.md) · Seguinte: [Registro 020](020_masked_observations.md)

Implementação experimental em `rl_boleta/missing_data_replay.py`, separada
do v2. Não altera `economic_kernel.py`, `session_replay.py`, o paper ou os
treinadores. A [proposta v3](018_protocol_v3_proposal.md) continua em revisão;
este núcleo não gera dados prontos para treinamento histórico.

## Funcionamento

`PartialFrame` descreve um minuto da grade e zero ou mais livros de ativos.
Um minuto sem livros é uma observação ausente, não um mercado de preço zero.
Os livros fornecidos devem vir de snapshots aceitos pelo preparador; nesta
etapa são sintéticos. O núcleo não substitui a validação das dez negociações,
spread, profundidade, relógios e proveniência do pipeline de dados.

`MaskedDailyReplay` usa o calendário histórico congelado e escolhe o primeiro
aquecimento conjunto válido de 21 pontos. Não utiliza capturas anteriores à
abertura nem consulta a continuidade futura para escolher um início posterior.
Exige duas transições restantes para intenção, execução e saída. Cada data
pode ser tentada uma vez por controlador; lacunas não criam novos episódios.

Após o início, o relógio avança minuto a minuto. Ausências completas da grade
são representadas explicitamente por frames vazios. Livros com idade superior
a 60 segundos são indisponíveis. A política recebe apenas histórico passado,
carteira, disponibilidade, marcas observadas e tempo restante. A cobertura
retrospectiva do minuto final não é parte dessa observação.

`MaskedReplayKernel` mantém a carteira durante ausências. Usa o último midpoint
observado para marcar cada posição; quando a captura válida retorna, reconhece
a variação acumulada no patrimônio e na recompensa. A marca antiga não serve
para executar ordens. A disponibilidade e o timestamp de captura de cada marca
acompanham cada transição, para expor a diferença entre valorização e liquidez.

`PartialExecutionEngine` reaproveita a execução por nível e a contabilidade
Decimal do v2. Uma intenção só executa no minuto seguinte. Se faltar livro
daquele ativo, seu componente expira; componentes de outros ativos continuam.
Uma venda indisponível não produz caixa para financiar compras. A profundidade
consumida por snapshot não é renovada por uma releitura. Somente fills pagam
taxas, e caixa/posições permanecem não negativos.

O piso de capital atua sobre o patrimônio marcado, com a limitação observacional
da proposta. Depois de acionado, impede novas intenções discricionárias e tenta
liquidar posições nos livros disponíveis. Se restar inventário sem livro ou
sem capacidade, o stop continua acionado até nova oportunidade, saída programada
ou truncamento. Uma recuperação de preços não desarma o stop.

## Saída e resultados

O calendário fixa 15:59 para o dia normal e 12:59 para 03/07/2025. O horizonte
é a diferença entre esse instante e o início causal real.

- `scheduled_end`: a liquidação programada terminou em caixa.
- `capital_stop`: o stop econômico terminou em caixa antes ou no fim previsto.
- `capital_stop_pending`: estado intermediário; ainda há posições para vender.
- `liquidation_failure`: há livros no minuto final, mas a profundidade/participação
  não permite liquidar tudo; o resultado retém as posições.
- `exit_data_missing`: faltam livros de algum ativo no minuto final; não se
  inventa venda, não se liquida parcialmente como se fosse a saída completa e
  o resultado é truncado com inventário preservado.
- `not_startable`: nenhum aquecimento causal deixa a margem mínima para a saída.

`coverage_candidate` só certifica início e disponibilidade conjunta da saída
para este replay, não elegibilidade histórica completa ou liquidez suficiente.
Vale o mesmo critério comum de saída mesmo quando uma estratégia aciona stop
antes dela. `marked_return` exclui dados truncados e cobertura final ausente;
inclui resíduos como valor marcado, devidamente sinalizados. `realized_return`
só existe quando a carteira terminou em caixa. Retornos não dependem da escala
da recompensa. `training_ready` permanece falso.

## Validação sintética

Os 22 testes novos cobrem:

- início causal e invariância diante de lacunas futuras;
- continuidade durante ausência de um ativo ou de todos por vários minutos;
- reconhecimento de perda após uma lacuna, sem executar com a marca antiga;
- cancelamento por ativo, ausência de execução tardia e caixa compartilhado;
- taxas, recompensa telescópica e separação entre recompensa escalada e retorno;
- stop com inventário indisponível e persistência do stop após recuperação;
- saída sem dados versus saída com volume insuficiente;
- identidade de captura, timestamps futuros, grade e proibição de reinício;
- pregão curto e igualdade com a contabilidade v2 quando os livros estão completos.

Para executar os testes específicos, sem dependências de treinamento:

```sh
python -m unittest discover -s tests -p test_missing_data_replay.py -v
```

O comando `python -m scripts.check_missing_data_core` executa três casos de
dia inteiro com dois ativos fictícios e grava os resultados em
`results/v3_core_synthetic_2026-10-12/`. O diretório deve ainda não existir.
Cada caso começa às 09:52 e percorre 367 transições, incluindo lacunas:

| Caso | Desfecho | Caixa final | Posições finais | Retorno marcado |
|---|---|---:|---|---:|
| Início tardio e lacunas | Saída em caixa | 963,8420 | 0, 0 | −3,6158% |
| Livro ausente na saída | Truncamento por dados | 191,9192 | 4, 4 | Não é retorno completo |
| Capacidade insuficiente na saída | Falha de liquidação | 191,9192 | 4, 4 | −2,80808%, com resíduos |

Esses valores são exemplos sintéticos de contabilidade, não resultados de
estratégias no mercado. O manifesto contém hashes do código e dos rastros,
sem reutilizar dados ou resultados da dissertação.

A regressão completa desta branch passou: 151 testes, sem falhas ou testes
pulados, incluindo os testes dos algoritmos existentes. Os hashes do replay
sintético e de seus rastros foram conferidos após a execução.

## O que continua pendente

O [encoder mascarado de 15.502 entradas e a normalização por feature válida](020_masked_observations.md)
foram implementados e validados sinteticamente na etapa seguinte. Falta
o manifesto final de elegibilidade. A [grade parcial e os baselines](022_masked_preparation_and_baselines.md)
estão implementados para diagnóstico. O [adaptador Gymnasium e os quatro algoritmos](021_masked_training.md)
já estão integrados para treinamento sintético. A regra
para lacunas longas permanece aberta; a ausência dessa regra não autoriza
selecionar os 79 candidatos como dados de treino. A validação sintética do
núcleo não certifica preços ou liquidez reais.

## Atualização: seleção condicional de datas

A [regra de lacunas e a elegibilidade condicional](023_gap_rule_and_conditional_eligibility.md)
foram congeladas no rascunho v3 na etapa seguinte. A regra principal não
acrescenta exclusão por duração; limites predefinidos são sensibilidades dos
mesmos modelos congelados. A seleção contém 50/15/14 dias e 65 de reajuste final.
Normalização e fitting históricos continuam pendentes. Os relatos de pendências
acima descrevem o estado na conclusão original desta etapa.
