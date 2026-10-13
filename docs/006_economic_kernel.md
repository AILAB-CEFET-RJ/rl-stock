# Núcleo econômico: implementação e validação sintética

> Registro **006** · Data de referência: **2026-10-08** · [Índice](README.md)
> Anterior: [Registro 005](005_paper_revision_stage_5.md) · Seguinte: [Registro 007](007_protocol_day_trading_revision.md)

Implementado em 08/10/2026 em [economic_kernel.py](../rl_boleta/economic_kernel.py),
conforme as regras do manuscrito revisado. É independente do ambiente RL legado,
de Gym e das bibliotecas de treinamento. Usa somente a biblioteca padrão.

## O que foi implementado

- Ações contínuas transformadas em intenções inteiras usando o patrimônio e
  os midpoints conhecidos na decisão, com zona neutra.
- Compra nos asks em ordem crescente; venda nos bids em ordem decrescente.
  Cada livro exige cinco níveis explícitos por lado, com preços distintos,
  quantidades positivas e melhor bid inferior ao melhor ask.
- Participação por nível, fills parciais, restrição de posição long-only e
  cancelamento do restante após uma tentativa.
- Vendas antes de compras; recursos líquidos das vendas disponíveis no passo;
  orçamento de compra compartilhado proporcional ao notional desejado observado.
  Sobras de um ativo não são redistribuídas para favorecer o próximo no laço.
- Taxa sobre notional de cada fill, incluída no limite de compra e cobrada uma
  única vez. Spread e caminhada nos níveis já entram no preço de execução.
- Caixa, posições, patrimônio marcado, recompensa por variação líquida e
  registros separados de execução ordinária, liquidação e saída por stop.
- Profundidade consumida mantida por ativo, ID da captura, lado e nível.
  Reutilizar a captura não cria nova liquidez. Mesmo ID com conteúdo diferente
  é rejeitado; nova captura tem nova capacidade sob a hipótese exógena do paper.
- Horizonte programado, último ponto reservado à liquidação, piso relativo ao
  capital inicial e preservação de posições residuais quando a saída não cabe
  no livro. Não há zeragem fictícia no midpoint.
- Truncamento por observação ausente/vencida, universo incompleto, lacuna na grade
  ou mudança de sessão, sem transações retroativas. Intenções pendentes são
  canceladas e o último patrimônio observado é preservado.

## Interface e sequência temporal

`Level`, `Book`, `Frame`, `Portfolio` e os registros de resultados são dataclasses
imutáveis. Os timestamps devem conter fuso e são normalizados para UTC.

`ReplayKernel` começa com carteira sem posições e capital inicial, a partir do
primeiro instante de decisão após o warm-up. A sequência é:

```python
kernel = ReplayKernel(config, first_decision_frame)
desired = kernel.submit(actions)  # usa somente o quadro atual
transition = kernel.advance(next_scheduled_frame)
```

`submit()` fixa as quantidades e os preços de referência para os orçamentos.
O próximo livro só é recebido por `advance()`. Não se pode enviar outra intenção
antes de resolver a pendente. A partir do instante anterior ao terminal,
`submit()` é bloqueado e `advance()` usa exclusivamente a tentativa de saída.
`Config` exige `horizon` explicitamente. No protocolo por pregão, a primeira
decisão é às 09:51: são 368 transições até 15:59 num dia normal ou 188 até
12:59 no fechamento antecipado. O último ponto é reservado à liquidação, sem
encerramentos intermediários. O warm-up externo e a derivação automática pelo
calendário ainda não são construídos por esta classe.

`advance(None)` informa falta da próxima observação. Uma lacuna temporal não
permite pular linhas e inventar um fill intermediário. Os resultados separam
`at`, horário de execução/detecção da interrupção, de `valuation_at`, horário da
última marcação realmente observada. Em um truncamento, a recompensa financeira
adicional é zero, sem transformar o retorno parcial em resultado liquidado.
A integração futura com o treinador deverá distinguir truncamento de término
e não tratar uma observação ausente como um próximo estado válido.

Entradas contraditórias, como captura futura, timestamp regressivo, conteúdo
alterado para o mesmo ID ou parâmetros inválidos, geram `ValueError` em vez de
ser corrigidas. Não equivalem a uma observação válida para preencher uma lacuna.
O adaptador deve registrar/rejeitar dados inválidos antes de entregá-los ao
núcleo, ou comunicar ausência pela interface de truncamento.

`ExecutionEngine.execute()` é a camada inferior, usada para testar transações
com carteiras controladas. Recebe intenções já fixadas e midpoints da decisão;
a aplicação de treinamento deverá usar a sequência de `ReplayKernel`.

## Resultados auditáveis

Cada transição contém patrimônio antes/depois, recompensa, eventos de execução,
status de término/truncamento, motivo, posições residuais e status de zeragem.
Cada evento preserva carteiras antes/depois e o quadro de execução. Cada fill
registra ativo, captura, horário, lado, nível, quantidade, preço e taxa. Por
intenção, o resultado registra quantidade desejada, executada, cancelada,
VWAP quando existe fill e limitações de caixa, posição ou profundidade.

O cálculo usa `Decimal` e precisão de trabalho de 50 dígitos para sizing,
orçamentos e transações, sem arredondar cada taxa a centavos. Orçamentos são
arredondados para baixo na divisão proporcional, evitando ultrapassar caixa.
Uma política de arredondamento de corretora seria hipótese adicional a declarar;
a implementação atual não pretende reproduzi-la.

## Evidência dos testes

Os [32 testes econômicos](../tests/test_economic_kernel.py) incluem:

| Caso controlado | Resultado conferido |
|---|---|
| Comprar cinco ações: três a US$ 100, duas a US$ 101 | Gasto US$ 502, caixa US$ 498, cinco ações, VWAP US$ 100,40 |
| Compra de cinco a US$ 101, taxa de 1% | Caixa US$ 489,95; taxa US$ 5,05 |
| Vender as cinco a US$ 99, taxa de 1% | Caixa final US$ 980; perda total US$ 20 |
| Manter cinco ações enquanto midpoint sobe de 100 para 102 | Ganho patrimonial US$ 10 sem nova transação |
| Comprar depois de midpoint subir de 100 para 200 | Nenhum ganho pela alta anterior à compra |
| Repetir uma captura cuja capacidade foi consumida | Nenhuma reposição de quantidade |
| Inverter a ordem dos ativos na entrada | Mesmas posições econômicas e mesmo caixa |
| Stop após compra no mesmo passo | Compra e saída registradas separadamente, preservando todos os custos |
| Liquidação com profundidade insuficiente | Resíduos marcados e falha de zeragem, sem apagar o episódio |
| Próximo quadro pula um minuto | Cancelamento, nenhuma venda retrospectiva, última marcação preservada |

Há também 150 carteiras/intenções aleatórias para conferir conservação de caixa,
posições e limites de participação, e 20 trajetórias sintéticas completas para
conferir a identidade patrimonial a cada transição e a soma telescópica das
recompensas. Esses testes usam sementes fixas e não executam treinamento.

Execução isolada, a partir da raiz:

```sh
python -m unittest discover -s tests -p test_economic_kernel.py -v
```

Suíte completa, em ambiente com as dependências dos testes de Parquet:

```sh
python -m unittest discover -s tests -v
```

Validação após revisão por pregão: 32 testes econômicos passaram com Python 3.12.4; 71 testes
passaram na suíte completa com Python 3.11.13 do ambiente `ailab`.

## Próxima integração

O núcleo não lê Parquet/CSV e não treina agentes. O [controlador por pregão](009_session_replay.md)
agora lê os livros do CSV revisado, constrói janelas causais e deriva o horizonte
do calendário. A [camada de observações](010_observations_and_training.md) agora
implementa codificação, normalizadores congelados e integração sintética PPO.
Os [quatro algoritmos](011_four_algorithm_integration.md) já foram integrados e
validados sinteticamente. O executor histórico ainda precisa ser integrado ao
[protocolo proposto](../configs/experimental_protocol_v2.json)
e os manifestos do preparador. O JSON do protocolo não é carregado automaticamente
por `Config`; as unidades e os nomes deverão ser mapeados explicitamente na
integração (por exemplo, um ponto-base de taxa equivale a `fee_rate=0.0001`).

A integração inicial PPO preserva as separações temporais e a normalização
ajustada no treino, mas ainda não autoriza inferência de desempenho histórico.
A interpretação dos relógios históricos permanece necessária antes de concluir
sobre desempenho financeiro dos dados reais.
