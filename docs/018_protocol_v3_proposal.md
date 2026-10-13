# Proposta de protocolo v3: observações incompletas e encerramento diário

> Registro **018** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 017](017_protocol_alternatives_audit.md) · Seguinte: [Registro 019](019_missing_data_core.md)

Proposta de 12/10/2026, baseada na [auditoria das alternativas](017_protocol_alternatives_audit.md).
A especificação estruturada está em
[`configs/experimental_protocol_v3.json`](../configs/experimental_protocol_v3.json).
Seu status é `draft_for_review_not_executable`. O protocolo v2, o simulador,
o treinador e o paper permanecem inalterados. Este documento não autoriza
treinamento nem certifica que os 79 candidatos da auditoria sejam utilizáveis.

O [núcleo econômico e controlador experimental v3](019_missing_data_core.md) já
foram implementados separadamente e testados com dados sintéticos. As
[observações mascaradas e a normalização](020_masked_observations.md) também foram
validadas sinteticamente. O [adaptador de treinamento e os quatro algoritmos](021_masked_training.md)
também estão integrados com dados sintéticos. A [grade histórica parcial e os
baselines](022_masked_preparation_and_baselines.md) estão disponíveis para diagnóstico;
a [elegibilidade condicional e a regra de lacunas](023_gap_rule_and_conditional_eligibility.md)
estão congeladas no rascunho, com [normalização histórica de treino](025_historical_normalization.md) concluída.

## Pergunta experimental e unidade econômica

Investigar uma política de operações intradiárias com observação incompleta,
início causal, uma carteira contínua por sessão e saída programada antes do
fechamento. O mercado é parcialmente observado: a ausência de captura do
scraper não significa ausência de negociação na bolsa.

São mantidos 18 ativos, calendário e partições históricos, capital inicial de
USD 100.000, posições long-only inteiras, caixa compartilhado, cinco níveis,
dez negócios, taxa de 1 bps por lado, participação de 10%, intenção com execução
no minuto seguinte e limites de qualidade/idade do v2. Não haverá resets
intradiários nem liquidações horárias.

O dia começa em caixa, sem operar durante a preparação. Começa-se no primeiro
minuto q em que os 18 ativos têm dados válidos nos 21 pontos q−20 até q:
referência e 20 pontos de features. Só contam capturas recebidas desde a
abertura e até cada instante da grade, com idade de até 60 segundos.
A decisão não consulta a cobertura futura.

A saída permanece às 15:59 de Nova York, ou 12:59 no pregão curto de 03/07/2025.
O último minuto para uma nova intenção é dois pontos antes dessa saída, seguido
pelo minuto da execução e pelo minuto reservado à liquidação. Um início que
deixe menos de duas transições não é permitido. Não se impõe uma hora de
operação; duração e início serão reportados por dia.

## Observação durante as lacunas

A grade segue avançando a cada minuto, preservando caixa e posições. Cada
ativo tem uma indicação de disponibilidade: 1 quando existe captura completa
aceita e recente naquele instante; 0 em caso contrário.

A janela de 20 passos mantém os 40 campos de mercado por ativo, acrescentando
três campos por ativo e passo: disponibilidade, idade de recebimento da última
captura aceita e idade da referência de preço. As idades são divididas por
23.400 segundos e limitadas a [0,1], usando a duração normal do pregão como
escala fixa, inclusive em pregões curtos. Não entram nas estatísticas de
padronização aprendidas.

Os preços são expressos relativamente ao midpoint do último **ponto anterior
válido** do mesmo ativo. Após uma lacuna, a diferença pode abranger mais de um
minuto; a idade da referência torna isso explícito. Volumes seguem `log1p`.
Essa regra generaliza a referência consecutiva exigida pela implementação v2.
No primeiro passo, o aquecimento completo garante as referências necessárias.

Quando o ativo está indisponível, seus 40 valores numéricos são codificados
como zero **depois da padronização**, acompanhados da indicação de ausência.
Esse zero é um marcador de entrada da rede, não preço, volume, cotação ou
retorno imputado. A idade de recebimento continua informando quanto tempo
passou desde a última captura; a referência tem sentinela zero quando não
há valor corrente a transformar. Não é necessário esperar outro aquecimento
completo de 21 pontos após cada lacuna: o histórico incompleto é explícito.

A normalização é ajustada somente em valores válidos dos dias elegíveis de
treino, contando cada ponto usado uma vez, sem incluir os zeros de ausência
nas médias ou variâncias. Validação/teste usam estatísticas congeladas.
As contagens de ajuste passam a ser por feature.

Para 18 ativos, a entrada proposta tem 20×774 campos históricos e 22 campos
de contexto, totalizando 15.502. O contexto preserva caixa, exposições,
patrimônio marcado, tempo desde a abertura e tempo restante. Nenhuma flag
retrospectiva de elegibilidade ou duração futura de lacuna chega à política.

## Ordens, caixa e posições

Componentes da ação para ativos indisponíveis são zerados antes de dimensionar
ordens e distribuir o orçamento de compra entre intenções válidas. Ativos
disponíveis continuam sujeitos às regras de caixa, quantidades, taxas e
profundidade. Registram-se ação proposta e ação efetivamente aplicável.

Uma intenção de q só pode executar em q+1, com livro aceito recente daquele
ativo. Se esse livro faltar, a intenção expira; não se guarda a ordem para
executá-la retrospectivamente quando uma cotação reaparecer. As intenções de
outros ativos continuam independentes desse cancelamento.

Sem cotação atual, não há compra nem venda daquele ativo. As posições já
existentes permanecem. Se nenhum ativo estiver disponível, o relógio continua,
sem execução de ordens. A releitura do mesmo snapshot não repõe a profundidade
já consumida; taxas incidem apenas sobre fills efetivos.

## Patrimônio e recompensa

Para definir o sinal de aprendizado durante observações incompletas, propõe-se
marcação pelo último midpoint observado do ativo desde a abertura:

`patrimônio marcado = caixa + soma(quantidade × último midpoint observado)`.

Uma nova observação aceita atualiza a marca. Durante a lacuna, a marca é
mantida, mas **não se afirma que o preço real ficou constante**. A marca serve
para contabilidade/recompensa e não para executar ordens.

A recompensa é a variação do patrimônio marcado dividida pelo capital
inicial, com escala 1 e gamma 1. A soma das recompensas deve coincidir com
o patrimônio marcado terminal relativo ao capital inicial, incluindo taxas.
Quando os dados voltam, a atualização reconhece a variação acumulada desde a
última observação. Essa distribuição temporal da recompensa é uma hipótese
de observação e pode afetar o aprendizado, mesmo sem mudar o total terminal.

O piso de capital de 80% usa patrimônio marcado. Pode detectar uma perda com
atraso quando faltam cotações, limitação que precisa ser reportada. Ao atingir
o piso, o stop fica acionado: cancelam-se intenções pendentes, proíbem-se novas
compras e tenta-se liquidar os ativos disponíveis. Posições indisponíveis
continuam registradas e são novamente oferecidas à liquidação quando surgem
livros válidos, respeitando capacidade consumida e o fim do dia.

## Saída, resíduos e resultados

A cobertura de saída exige livros aceitos recentes dos 18 ativos no minuto
programado, para um critério comum e independente das posições de cada agente.
O livro disponível não garante volume suficiente para zerar a carteira. A
tentativa de liquidação mantém custos, profundidade e participação finitos.

Com carteira zerada, o patrimônio final é caixa e o retorno é realizado no
simulador. Com resíduos, o resultado mantém o patrimônio marcado e registra
**falha de liquidação**. Não há venda inventada, exclusão seletiva da data ou
declaração de retorno integralmente liquidado. A comparação deve apresentar
o resultado marcado junto da taxa de encerramento em caixa e da exposição
residual; desempenho com resíduos não comprova uma execução bem-sucedida de
day trading.

Cada novo episódio representa uma sessão simulada independente, iniciada em
caixa. Isso não equivale a afirmar que resíduos do episódio anterior foram
vendidos. Se não houver dados na saída, o resultado é truncado, com inventário
preservado e sem retorno de dia completo.

## Elegibilidade condicional e lacunas

A [regra principal congelada](023_gap_rule_and_conditional_eligibility.md) usa
`masked_all_gaps`: não exclui dias adicionalmente pela duração das lacunas.
Mantém aquecimento causal, margem de duas transições e saída conjunta coberta.
A ausência de filtro não aumenta a idade máxima de um livro executável nem
certifica risco durante cotações desconhecidas. Essa escolha decorre do estudo
de observação incompleta; os diagnósticos de treino não fornecem um limite seguro.

O [desenho de dois cenários](024_two_scenario_experiments.md) acrescenta treino
independente de PPO, A2C, SAC e DDPG em dias com até dois pontos consecutivos
ausentes, com normalizadores próprios e comparação dos modelos em datas comuns.
Esse cenário secundário tem 43/14/14 datas e 57 de reajuste final; as variantes
PPO ficam no cenário principal. O orçamento total passa a 286 ajustes e
208 milhões de transições solicitadas.

Limites de 1, 2, 5, 15 e 30 pontos consecutivos ausentes são sensibilidades
predefinidas dos mesmos modelos congelados, sem retreinamento ou escolha por
retornos. O manifesto registra 50/15/14 datas elegíveis condicionais e 65 de
reajuste final. Todos os motivos de exclusão ficam explícitos, e falhas econômicas
não removem seletivamente datas. Essas regras são retrospectivas e comuns às
estratégias; não influenciam o início causal nem aparecem na observação.

A seleção está pronta para implementar a normalização histórica controlada.
`training_ready` permanece falso: a normalização histórica de treino já está
implementada, mas faltam a execução da seleção por validação com orçamento protocolar e o reajuste final
condicionado à seleção pela validação. Com 14 dias de teste, julho continua descritivo
sob o limiar de 20 sessões pareadas previsto para inferência. As limitações de
recebimento versus horário de mercado e de liquidação finita permanecem.

## Baselines, algoritmos e avaliação

PPO, A2C, SAC e DDPG preservam os parâmetros e orçamentos planejados no v2,
mas a nova dimensão e a semântica de observação exigem revalidação. Fronteiras
de rollout não liquidam posições nem reiniciam a carteira. O tempo até a
saída acompanha a observação para tratar o horizonte financeiro corretamente.

Todos os baselines usam as mesmas datas, início causal, disponibilidade,
execução, valorização e saída. A alocação igualitária envia uma intenção no
início e não repete componentes que expiraram. Momentum/reversão de dez
minutos só usam um ativo se houver observações válidas nos dois extremos
exatos da comparação; não interpolam. As ablações mantêm disponibilidade e
idades, para não apresentar zeros de ausência como dados de mercado comuns.

As métricas adicionais incluem horário de entrada, horizonte, lacunas por
ativo, idade das marcas e parcela do patrimônio apoiada em marcas antigas.
Drawdown calculado nessas marcas é drawdown observado, não certificado de
risco do preço desconhecido durante uma lacuna.

## Próxima etapa de implementação

A [revisão de admissibilidade de day trading](028_day_trading_admissibility_review.md)
substitui a proposta de seleção apenas por patrimônio marcado: exige fechamento
em caixa em todas as datas/sementes da validação. Preparação de saída, objetivo
de aprendizagem e regime de conta precisam ser implementados e verificados
antes da seleção completa. O diagnóstico anterior fica preservado, sem
autorizar reajustes ou constituir seleção de pesquisa.

A validação sintética já cobre: continuidade de
carteira e relógio, início causal, referência após lacuna, normalização que
exclui sentinelas, cancelamentos por ativo, recompensa telescópica com taxas,
stop com venda parcial e saída com dados ausentes ou volume insuficiente.
Os quatro algoritmos estão integrados ao adaptador sintético. Seguem
seleção por validação com orçamento protocolar, variantes e reajuste final,
após verificar o executor de validação com orçamento diagnóstico nos dois cenários, antes de substituir o v2 no paper.

A proposta permanece para revisão. Nenhum treinamento histórico, mudança do
paper ou substituição da implementação v2 foi realizado nesta etapa.
