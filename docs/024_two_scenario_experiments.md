# Dois cenários com treinamentos independentes

> Registro **024** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 023](023_gap_rule_and_conditional_eligibility.md) · Seguinte: [Registro 025](025_historical_normalization.md)

Revisão de 12/10/2026 após a escolha de reportar os dois cenários. Amplia a
[regra e elegibilidade anteriores](023_gap_rule_and_conditional_eligibility.md):
o cenário secundário tem seus próprios treinos, em vez de apenas filtrar
resultados dos modelos do cenário principal. O paper e o v2 não foram alterados.

## Definição e justificativa

**Principal, `all_gaps`:** sem exclusão adicional por duração das lacunas.
Estuda o protocolo de observação incompleta com máscaras e carteira contínua.

**Secundário, `short_gaps`:** exclui qualquer pregão com mais de dois pontos
consecutivos da grade indisponíveis para algum ativo após o início causal,
até a saída programada. É uma definição operacional de poucos passos ausentes
na resolução de um minuto, pequena relativamente à janela de 20 passos. No
treino, 43 dos 50 candidatos apresentam máximos de um ou dois pontos.

O limite de dois pontos é uma convenção do experimento, não uma conclusão de
segurança obtida dos dados. As contagens de cobertura, inclusive teste, já eram
conhecidas das auditorias; não se alega uma escolha cega a essas contagens.
Não foram usados retornos de validação/teste para escolher o limite, nem se
ajustou o limite para obter determinada quantidade de dias de teste. A definição
não depende de preços ou decisões da política.

O filtro limita o comprimento de cada sequência ausente. Não limita a soma
das ausências no dia nem garante 90% de cobertura da janela: diversas lacunas
curtas podem ocorrer perto umas das outras. Essas métricas continuam sendo
reportadas. Dois pontos ausentes entre pontos válidos correspondem a três
intervalos da grade; não significam dois minutos exatos de idade da captura.

Ambos preservam início causal, margem de duas transições, saída conjunta
observada, idade máxima executável de 60 segundos, máscaras e idades, taxas,
caixa compartilhado, participação e profundidade finitas. Não surgem resets
horários nem uma liquidação antecipada ao encontrar a lacuna que exclui o dia.
A seleção retrospectiva fica nos manifestos, nunca na observação do agente.

## Datas e proteção das partições

| Cenário | Treino | Validação | Teste | Reajuste final |
|---|---:|---:|---:|---:|
| Principal: todas as lacunas | 50 | 15 | 14 | 65 |
| Secundário: lacunas de até dois pontos | 43 | 14 | 14 | 57 |

As datas do cenário secundário são subconjuntos do principal. Todos os métodos
de um cenário compartilham as datas elegíveis. Stops econômicos e falhas de
liquidação não removem dias seletivamente. Todos os pregões programados e
motivos de exclusão ficam registrados em ambos os manifestos.

Neste arquivo, **os dois cenários têm exatamente as mesmas 14 datas de teste**.
Não há episódios de teste elegíveis com lacunas acima de dois pontos. Assim,
a comparação mostra o efeito conjunto de treinar/selecionar modelos sob
amostras de cobertura diferentes e avaliá-los nessas datas com lacunas curtas.
Não demonstra robustez a lacunas longas em um teste protegido. Essa pergunta
exigiria outro período de teste, registrado separadamente; não se reutiliza
validação como teste para preencher a ausência. Julho continua descritivo
sob o limiar de 20 sessões pareadas previsto para inferência.

## Treinamento, normalização e comparação

A [emenda de admissibilidade para day trading](028_day_trading_admissibility_review.md)
aplica-se igualmente aos dois cenários e baselines. A seleção completa exige
encerramento em caixa em todas as datas/sementes de validação. Preparação de
saída, recompensa e regime de conta ainda precisam ser verificados; os
orçamentos abaixo são planejamento, não autorização para executar o protocolo
antigo como experimento definitivo. Falhas do benchmark impedem interpretar
uma diferença de patrimônios marcados como contraste de retornos realizados.

Para cada cenário e algoritmo:

1. Ajustar um normalizador somente nos valores válidos das datas de treino
   daquele cenário. Não usar um normalizador compartilhado entre cenários.
2. Executar a mesma grade de largura e taxa de aprendizado, sementes 0–2 e
   orçamento de 500.000 transições por ajuste. Selecionar usando somente as
   datas de validação do cenário, com o critério e desempates existentes.
3. Após a seleção, ajustar um novo normalizador nas datas de treino + validação
   do cenário e treinar as sementes finais 100–109 por 1.000.000 de transições.
4. Avaliar os checkpoints finais congelados e os baselines nas datas nativas
   de teste do cenário, mantendo seu próprio normalizador.
5. Comparar os dois conjuntos de modelos nas datas comuns de teste, por
   algoritmo e identificador de semente. Não atualizar pesos ou estatísticas
   nessa comparação. Os baselines usam o mesmo replay econômico e livros.

O contraste principal permanece PPO versus entrada com alocação igualitária
no cenário principal. Os resultados do cenário secundário e as diferenças
entre modelos dos dois cenários são análises secundárias descritivas.
Mesmo em datas comuns, variam conjuntamente amostra de treino, normalizador e
hiperparâmetros selecionados; não se atribui toda diferença somente à duração
das lacunas. Reportar as configurações escolhidas torna isso verificável.

Os filtros de 1/2/5/15/30 pontos já previstos continuam sendo sensibilidades
por subconjunto dos modelos congelados de `all_gaps`, sem retreinamento.
A sensibilidade de dois pontos **não é** o experimento `short_gaps`, que tem
modelos e normalizadores próprios. Neste teste, o filtro de dois pontos não
remove datas; aplicado aos mesmos checkpoints, não muda seus resultados.

## Orçamento revisado

PPO, A2C, SAC e DDPG têm treinos completos em ambos os cenários. As duas
variantes de desconto e três ablações de observação de PPO permanecem somente
no cenário principal. As avaliações de estresse e as sensibilidades por
subconjunto continuam sem retreinamento e usam os modelos principais.

| Cenário | Ajustes de seleção | Ajustes finais | Total | Transições solicitadas |
|---|---:|---:|---:|---:|
| Principal, com variantes | 108 | 90 | 198 | 144 milhões |
| Secundário, quatro algoritmos | 48 | 40 | 88 | 64 milhões |
| Total | 156 | 130 | **286** | **208 milhões** |

A seleção de cada algoritmo usa quatro configurações × três sementes; cada
configuração de variante também usa essa grade. Os ajustes finais usam dez
sementes por algoritmo/variante. Excesso para completar rollouts permanece
limitado e deve ser registrado. Esse orçamento é de planejamento, não uma
estimativa de tempo de máquina nem autorização para executar as APIs legadas.
Baselines, avaliação cruzada e sensibilidades não acrescentam ajustes de redes.

## Artefatos e reprodução

O comando gera protocolos de seleção, manifestos separados e listas de datas
comuns, sem ler preços de teste, ajustar redes ou calcular retornos:

```sh
caffeinate -i /Users/ebezerra/miniconda3/bin/python3 \
  -m rl_boleta.scenario_manifests \
  --prepared-dir results/v3_partial_grid_verified_2026-10-12 \
  --train-audit-dir results/v3_train_gap_diagnostics_2026-10-12 \
  --protocol configs/experimental_protocol_v3.json \
  --output-dir results/v3_two_scenario_design_verified_2026-10-12
```

A saída exige diretório novo. O artefato final contém `all_gaps/`, `short_gaps/`,
`common_dates.json` e `manifest.json`. Cada manifesto filho funciona com
`read_eligible_session(..., partition=...)`; suas sensibilidades nunca expandem
o conjunto elegível do próprio cenário. Protocolos originais e revisados têm
cópias imutáveis e hashes, preservando a interpretação da grade anterior.

Normalização e fitting históricos ainda estão pendentes. `training_ready`
permanece falso nos dois cenários. A próxima implementação deve consumir esses
manifestos separados e manter as estatísticas congeladas na avaliação.

## Verificação desta revisão

A regressão completa passou: **199 testes, sem falhas ou testes pulados**.
Três testes novos verificam a contagem dos ajustes/transições, protocolos e
seleções separados, datas comuns, sensibilidades contidas no cenário e recusa
de orçamento ou conjunto de algoritmos inconsistentes. Os hashes dos artefatos,
as relações de subconjunto e a igualdade das 14 datas de teste foram conferidos.
Nenhum ajuste histórico de normalizador ou rede foi executado nesta revisão.

## Atualização: normalizadores de treino

A [normalização histórica de treino](025_historical_normalization.md) foi implementada
e executada com as 50/43 datas dos manifestos. O reajuste final continua
condicionado à seleção dos modelos pela validação. O adaptador histórico de
treinamento ainda está pendente.

## Atualização: integração histórica

A [integração histórica curta](026_historical_training_integration.md) verificou
PPO, A2C, SAC e DDPG nos dois cenários com seus normalizadores congelados.
A seleção por validação e o reajuste final continuam pendentes. Os relatos
de pendências anteriores descrevem o estado ao concluir a etapa original.
