# Regra de lacunas e elegibilidade condicional v3

> Registro **023** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 022](022_masked_preparation_and_baselines.md) · Seguinte: [Registro 024](024_two_scenario_experiments.md)

Decisão metodológica de 12/10/2026 no rascunho v3 desta branch. Mantém-se o
estudo de observações incompletas, uma carteira contínua por pregão e saída
programada diária. O paper e a implementação v2 permanecem inalterados.

## Regra principal

**Não excluir um pregão adicionalmente pela duração das lacunas após o início
causal.** O JSON especifica `primary_mode=masked_all_gaps`, com status
`frozen_for_conditional_v3_simulation`. O valor nulo do limite representa agora
uma decisão explícita de ausência de filtro, não uma decisão pendente.

Continuam exigidos: primeiro aquecimento causal conjunto de 21 pontos,
pelo menos duas transições até a saída, e livros aceitos recentes de todos os
18 ativos no minuto de saída comum. A idade máxima de recebimento de um livro
executável continua em **60 segundos**. Não se aceita uma captura velha para
operar porque a regra de exclusão de pregões não tem limite adicional.

Durante uma lacuna, mantêm-se máscaras, idades, caixa, posições e relógio;
expiram ordens afetadas e não se negocia sem livro aceito. Marcas antigas
servem à contabilidade declarada e não representam preços atuais. O piso de
capital pode reconhecer perdas com atraso. A regra não certifica controle de
risco, execução ao vivo ou liquidação completa.

## Por que não escolher um número de minutos como limite principal

O objetivo proposto é investigar aprendizagem sob observação incompleta.
Excluir as trajetórias com observação mais difícil da análise principal mudaria
a população estudada para dias com melhor cobertura. Isso pode ser uma pergunta
válida, mas é uma escolha metodológica diferente, não uma correção obrigatória.

O treino permite medir lacunas e mudanças entre seus extremos observados;
não permite observar os extremos de preço dentro delas. Mesmo uma lacuna
curta pode esconder um movimento relevante. A magnitude observada na retomada
não prova um limite de perdas ou de atraso do stop. Portanto, estes dados não
fornecem fundamento para chamar dois, cinco ou quinze minutos de “seguros”.
A decisão de não usar filtro decorre da pergunta do estudo, não de um resultado
financeiro favorável nem da quantidade de dias restantes no teste.

Também não se deriva esse limite de regras de pausas da bolsa. O mecanismo
LULD da Nasdaq trata bandas de preço e pausas declaradas pelo mercado;
nossa ausência de captura não identifica esse evento. Essa distinção é uma
inferência metodológica a partir da definição oficial, não uma conclusão
sobre a causa de cada lacuna do arquivo. [Nasdaq, LULD FAQ](https://www.nasdaqtrader.com/content/MarketRegulation/LULD_FAQ.pdf).

## Diagnóstico utilizado: apenas treino

`rl_boleta.gap_policy_audit` acessou preços somente das sessões iniciáveis da
partição de treino. Não executou estratégias nem ajustou parâmetros. Validação
e teste não tiveram preços consultados para fundamentar a decisão.

Entre os 50 candidatos de treino, o máximo da lacuna mais longa por dia foi:

| Máximo de pontos ausentes consecutivos por ativo | Dias |
|---|---:|
| 1 | 33 |
| 2 | 10 |
| 3 | 3 |
| 4 | 1 |
| 9 | 1 |
| 10 | 1 |
| 34 | 1 |

A maior mudança absoluta entre midpoints observados antes/depois de uma
lacuna foi **2,6721%**. Não é o pior movimento intralacuna nem um retorno de
estratégia. Uma sequência de K pontos ausentes implica K+1 intervalos de grade
entre os pontos válidos que a cercam; a diferença entre os horários reais das
capturas é registrada separadamente. Não se confundem pontos ausentes com
minutos exatos de idade de uma marca ou com o horário de mercado desconhecido.

Artefato: `results/v3_train_gap_diagnostics_2026-10-12/diagnostics.json`,
com eventos em `gap_events.jsonl` e proveniência no manifesto.

## Manifesto congelado e sensibilidades

A seleção é independente das estratégias. Todas as datas e motivos de
exclusão ficam registrados. Uma parada econômica antecipada ou uma carteira
que termine com resíduos não altera a elegibilidade da data.

| Partição | Programados | Elegíveis condicionais | Mínimo operacional |
|---|---:|---:|---:|
| Treino | 63 | 50 | 20 |
| Validação | 20 | 15 | 10 |
| Teste | 22 | 14 | 10 |
| Reajuste final: treino + validação | 83 | 65 | — |

Os mínimos operacionais são satisfeitos. Isso não certifica qualidade de
execução nem poder estatístico: julho continua descritivo pelo limiar de
20 sessões pareadas já previsto. Os motivos de exclusão podem se sobrepor;
por exemplo, um dia sem arquivo também não tem aquecimento ou saída observada.
Não se somam essas contagens como categorias mutuamente exclusivas.

Os filtros de **1, 2, 5, 15 e 30 pontos consecutivos ausentes** são sensibilidades
predefinidas, usando os mesmos modelos e previsões congelados da análise
principal. Cada filtro seleciona um subconjunto comum às estratégias para
resumir diferenças pareadas. Não há retreinamento, seleção de hiperparâmetros
ou escolha do melhor filtro por desempenho. Subconjuntos diferentes representam
amostras diferentes; não se atribui uma mudança de resultado apenas à duração
das lacunas. As listas de datas estão em `sensitivities.json`.

Artefato final: `results/v3_conditional_eligibility_verified_2026-10-12/manifest.json`.

## Reprodução, proveniência e próximo passo

```sh
caffeinate -i /Users/ebezerra/miniconda3/bin/python3 \
  -m rl_boleta.gap_policy_audit \
  --prepared-dir results/v3_partial_grid_verified_2026-10-12 \
  --protocol-snapshot results/v3_train_gap_diagnostics_2026-10-12/preparation_protocol.json \
  --output-dir results/v3_train_gap_diagnostics_repeat_2026-10-12

caffeinate -i /Users/ebezerra/miniconda3/bin/python3 \
  -m rl_boleta.masked_eligibility \
  --prepared-dir results/v3_partial_grid_verified_2026-10-12 \
  --train-audit-dir results/v3_train_gap_diagnostics_2026-10-12 \
  --protocol configs/experimental_protocol_v3.json \
  --output-dir results/v3_conditional_eligibility_verified_2026-10-12
```

As saídas exigem diretórios novos. O primeiro comando mostra como repetir a
auditoria usando a cópia imutável do protocolo original. Para repetir o segundo,
também escolha outro diretório de saída e indique a auditoria desejada.

O manifesto de elegibilidade preserva cópias imutáveis dos protocolos do
preparador e da seleção revisada. O leitor aceita a cópia antiga somente se
seus bytes tiverem o hash original. Isso permite evoluir o rascunho sem
reinterpretar a grade anterior ou alterar seus manifestos.

`read_eligible_session(directory, day, partition=...)` exige uma partição
explícita, recusa datas excluídas ou de outra partição, verifica proveniência
e retorna uma sessão histórica com `synthetic=False`. Para reajuste final,
permite somente treino e validação, nunca julho.

A seleção de datas está pronta para implementar a normalização histórica
controlada. `training_ready` continua falso: o normalizador por feature e as
APIs de fitting histórico ainda não foram implementados. As hipóteses de fuso,
a falta de horário certificado do livro e a cobertura de uma única fonte
continuam fazendo parte das limitações da simulação condicional.

## Verificação desta etapa

A regressão completa passou: **196 testes, sem falhas ou testes pulados**.
Os seis testes novos verificam modos explícitos de regra, mudanças observadas
entre extremos, seleção comum independente de estratégia, motivos de exclusão,
restrições por partição, protocolo imutável, alteração de qualidade recusada
e repetição da auditoria de treino após mudança do protocolo de trabalho.
Os hashes dos artefatos de diagnóstico e elegibilidade foram conferidos.
O leitor histórico foi exercitado em um dia elegível de treino; datas de julho
foram recusadas para treino e reajuste antes da leitura de seus preços. O gate
de normalização histórica permanece fechado.

## Revisão posterior: dois treinamentos

O usuário optou por reportar os dois cenários. O [desenho revisado](024_two_scenario_experiments.md)
mantém a regra principal acima e acrescenta um cenário secundário treinado
independentemente com limite de dois pontos consecutivos ausentes. Esse cenário
não se confunde com a sensibilidade por subconjunto sem retreinamento. Seus
manifestos e o orçamento ampliado estão registrados na documentação revisada.
