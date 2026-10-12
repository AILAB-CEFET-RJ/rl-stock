# Alternativas de cobertura mantendo uma carteira por dia

Auditoria realizada em 12/10/2026 dos 105 pregões de março–julho de 2025.
Usa a grade por ativo da auditoria anterior dos Parquet originais, cujos hashes
foram verificados. Não modifica protocolo, paper, coletor, qualidade das
capturas, idade máxima, universo ou dados. Não há simulação financeira,
treinamento ou certificação de execução.

## Hipóteses examinadas

**Início causal variável:** o agente começa no primeiro minuto em que existem
21 pontos consecutivos válidos dos 18 ativos: referência de defasagem e 20
pontos para as features. Esse instante depende apenas do passado. O horizonte
termina na saída diária original; não se inicia outro episódio após uma lacuna.
Exige-se margem de duas transições para intenção, execução e saída. Não se
escolhe retrospectivamente um trecho posterior porque ele termina sem lacunas.

**Indisponibilidade por ativo:** depois desse início, uma captura ausente ou
inválida deixa o ativo indisponível, sem inventar cotação ou liquidez. Caixa e
posições devem permanecer na mesma trajetória diária; aqui essa é uma exigência
do modelo futuro, não uma simulação já implementada. O diagnóstico de saída
exige dados aceitos recentes dos 18 ativos no minuto programado de liquidação,
independentemente da estratégia.

## Resultado

| Interpretação | Treino | Validação | Teste | Total |
|---|---:|---:|---:|---:|
| Primeiro aquecimento causal disponível, com margem para saída | 53 | 15 | 14 | 82 |
| Mesmo início, exigindo continuidade conjunta até a saída | 0 | 0 | 0 | 0 |
| Mesmo início, permitindo lacunas por ativo e exigindo dados na saída | 50 | 15 | 14 | 79 |

**Começar mais tarde, sozinho, não resolve. A combinação identifica 79 dias
candidatos sob novas hipóteses de observação.** Em três dos 82 dias iniciáveis
faltam dados conjuntos na saída. Dias sem arquivo ou sem aquecimento causal
adequado continuam excluídos.

Nos 79 candidatos, o início mediano é 11:05 de Nova York. O mais cedo é 09:52
e o mais tarde é 15:36. O horizonte restante tem mediana de 293 minutos e varia
de 23 a 367 minutos. A alternativa, portanto, não impõe uma hora de operação.

Exigindo pelo menos 60 transições restantes após o início, há 77 candidatos:
48 de treino, 15 de validação e 14 de teste. Esse limite é uma sensibilidade
de cobertura, não uma nova regra adotada nem a duração de um episódio horário.
Com pelo menos 120 transições restantes, há 68: 44/11/13.

## Lacunas e observações

Todos os 79 candidatos têm algum ponto sem disponibilidade conjunta depois
do início. São 1.408 pontos anteriores à saída, com mediana de 16 por dia.
Em oito dias existem pontos sem captura atual utilizável de nenhum ativo,
somando 61 minutos. O maior trecho contínuo sem observar um ativo é de
34 pontos consecutivos da grade.

Não basta acrescentar uma indicação de validade da cotação atual: as features
usam uma janela histórica. Se mantivermos a exigência de 21 pontos completos
por ativo, cada lacuna obriga reconstruir essa janela antes de reativar suas
features. Essa interpretação mais conservadora gera 980 minutos sem nenhum
ativo com janela completa, distribuídos por 36 dos 79 dias candidatos.
Isso mostra a importância de especificar máscaras para todo o histórico,
ou uma regra explícita de aquecimento por ativo, antes de implementar.

## Sensibilidade à duração das lacunas

Contagens entre os candidatos, excluindo retrospectivamente qualquer dia
com um trecho de indisponibilidade de algum ativo acima do limite indicado:

| Máximo de pontos consecutivos indisponíveis por ativo | Treino | Validação | Teste | Total |
|---|---:|---:|---:|---:|
| 1 | 33 | 11 | 7 | 51 |
| 2 | 43 | 14 | 14 | 71 |
| 5 | 47 | 15 | 14 | 76 |
| 15 | 49 | 15 | 14 | 78 |

Com limite de dois pontos e pelo menos 60 transições restantes, seriam
69 candidatos: 41/14/14. Esses números não justificam escolher o limite de
dois pontos para atingir uma contagem desejada. Qualquer limite deverá ter
justificativa de observação, risco e avaliação; a seleção futura deve ser
declarada e comum às estratégias, sem revelar à política as lacunas futuras.

Os 14 dias de teste potenciais superam o mínimo operacional de dez do
protocolo, mas continuam abaixo do limiar de 20 sessões pareadas previsto
para inferência; isso não resolve a limitação estatística de julho.

## O que ainda impede afirmar que os dados estão prontos

- Cotação disponível no minuto de saída não garante profundidade suficiente
  para liquidar a carteira sob taxas e limite de participação. Resíduos precisam
  ser simulados e reportados, sem excluir seletivamente estratégias que os gerem.
- Faltam regras de representação do histórico ausente, normalização, valorização
  da carteira e recompensa durante a lacuna. Uma cotação antiga pode ter papel
  numa convenção de marcação declarada, mas não vira liquidez para uma ordem.
- Intenções cuja execução prevista coincide com indisponibilidade precisam de
  regra explícita de cancelamento ou expiração. Não há execução retroativa.
- A seleção exige saída observada, por isso é retrospectiva e condicional à
  cobertura. Datas excluídas e resultados dessa seleção devem ser reportados.
- O horário de mercado do livro permanece não certificado; a evidência dos
  fusos não elimina essa limitação do scraper.

Assim, o diagnóstico sustenta **investigar o aproveitamento de parte dos dados
históricos**, não seu uso imediato no treinador vigente. A próxima etapa
recomendada é formular uma proposta de protocolo v3 para observações incompletas,
carteira contínua, início causal e saída diária, antes de mudar o paper ou o
simulador. O protocolo v2 continua sendo a referência implementada.

## Reprodução e verificações

```sh
python -m rl_boleta.audit_protocol_alternatives \
  --input-dir results/gap_causes_2026-10-08 \
  --protocol configs/experimental_protocol_v2.json \
  --output-dir results/protocol_alternatives_verified_2026-10-12
```

O diretório deve ser novo. As saídas `sessions.csv`, `details.jsonl` e
`manifest.json` registram as regras, contagens, limitações e hashes.
O diretório `results/protocol_alternatives_2026-10-12/` preserva a primeira
execução, anterior à inclusão das sensibilidades de duração de lacunas.

Seis testes passaram, incluindo início causal, ausência de seleção de trecho
por cobertura futura, saída ausente, início tardio demais e reconstrução de
janela após lacuna. Os hashes de entradas, código e saídas da execução final
foram verificados, assim como os 105 registros e as contagens de candidatos.
