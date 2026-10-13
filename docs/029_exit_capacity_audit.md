# Capacidade observada de encerramento nas datas de treino

> Registro **029** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 028](028_day_trading_admissibility_review.md) · Seguinte: [Registro 030](030_wind_down_implementation.md)

Auditoria de 12/10/2026 para orientar a revisão do day trading. Implementada em
`rl_boleta.exit_capacity_audit`, sem políticas, treinamento, retornos de
validação ou preços de julho. Os dois cenários mantêm as datas congeladas:
50 de treino em `all_gaps` e 43 em `short_gaps`. O segundo é um subconjunto,
portanto não constitui outra amostra independente.

## O que foi medido

Para cada ativo, somamos a capacidade inteira de compra exibida nos cinco
níveis de bid: `sum(floor(0.10 * quantidade_do_nível))`. É a mesma regra por
nível do núcleo econômico. Livros ausentes/expirados não oferecem capacidade,
e cada identidade de captura conta uma única vez dentro da janela analisada.

Analisamos os últimos 1, 2, 5, 10, 15, 30, 60 e 120 pontos de execução antes
do fechamento, incluindo o ponto reservado de 15:59. Também calculamos o
menor sufixo inteiro capaz de cobrir cada quantidade de referência.
Janelas maiores que o horizonte após o início causal ficam indisponíveis,
sem encurtamento silencioso e sem exclusão da sessão do relatório.

As quantidades hipotéticas são avaliadas pelo midpoint no início causal:

- Referência igualitária: `floor((100000 / 18) / preço_do_ativo)` ações por ativo.
- Estresse concentrado: `floor(100000 / preço_do_ativo)` ações de um ativo,
  analisadas separadamente para cada ativo. Não se supõe possuir US$ 100 mil
  em cada um dos 18 ativos simultaneamente.

Não compramos essas carteiras. Elas são referências de tamanho, não holdings
atingíveis certificados: a compra real teria preços, taxas e limites próprios.
A capacidade assume bids ainda não consumidos por vendas anteriores do agente.
É um limite otimista dentro do replay exógeno, não uma garantia de execução real.
Preços de compra posteriores e valorização podem alterar a quantidade ou
exposição de uma carteira efetivamente aprendida.

## Resultados

A primeira tabela exige capacidade suficiente para todos os 18 componentes
da referência igualitária, em cada sessão:

| Pontos finais de execução | Todas as lacunas | Lacunas curtas |
| --- | ---: | ---: |
| 1 | 10/50 | 8/43 |
| 2 | 36/50 | 31/43 |
| 5 | 50/50 | 43/43 |
| 10 | 50/50 | 43/43 |
| 15 | 50/50 | 43/43 |

Dos 900 pares ativo/sessão no cenário principal, 762 tinham capacidade para a
referência igualitária no ponto final; o menor sufixo necessário chegou a
quatro pontos. São 50 sessões, não 900 observações independentes de mercado.

No estresse concentrado, entre os casos com capacidade suficiente, o maior
sufixo necessário foi **54 pontos**, para NCLH em 09/04/2025, referência de
6.506 ações. No cenário secundário, esse máximo também é 54.

Em 14/03/2025, o início causal foi às 15:36 de Nova York, restando 23
transições. As referências concentradas de GM (2.065 ações) e DAL (2.162)
superavam até a capacidade total restante: 1.641 e 1.802 ações. São dois
pares ativo/sessão em uma mesma data. Não existe janela de saída que produza
capacidade suficiente para essas referências dentro desse horizonte observado.
Isso não demonstra que qualquer posição real nessas ações seria impossível de
vender; demonstra que tamanho e tempo disponível precisam ser tratados juntos.

## Regra causal proposta a partir da auditoria

Proponho uma fase comum de redução de posições com **54 pontos de execução**,
correspondente ao maior mínimo finito do estresse concentrado no treino
principal. Esta escolha explicita como foi derivada; não representa um limite
seguro para dados futuros, nem afirma que cobre os dois casos sem capacidade.
Ainda é proposta de implementação, não parâmetro do simulador em produção.

1. O início é determinado pelo fechamento oficial menos 54 minutos:
   primeira execução de saída às 15:06 no pregão normal e 12:06 no reduzido.
   A última tentativa permanece às 15:59/12:59.
2. A partir da decisão anterior à primeira execução dessa fase, impedir
   compras e tentar vender todo o inventário em cada próximo ponto, com
   os limites de profundidade, participação, frescor, taxas e consumo de captura.
   No pregão normal, a última intenção ordinária fica às 15:04, com execução
   às 15:05. O controle de saída começa na fronteira seguinte.
3. Não usar a liquidez futura, o menor sufixo daquele dia ou seu futuro
   sucesso para mudar retrospectivamente o horário. O parâmetro de 54 é
   comum e derivado do treino, não adaptado por retornos de validação/teste.
4. Se o início causal ocorrer quando a próxima execução já pertence à fase,
   permanecer em caixa; registrar a ausência de oportunidades discricionárias.
   Conservar a data para todos os métodos. Nas datas de treino atuais, isso
   afeta 14/03 e 21/03, ambas presentes nos dois cenários. Não remover essas
   sessões para aumentar retorno médio ou taxa de sucesso.
5. Um stop anterior mantém seu bloqueio de compras e suas tentativas de
   venda. Não reabrir posições depois de terminar a redução. Mesmo se a
   carteira ficar flat durante a fase, continuar até o horizonte programado
   em caixa, salvo o término econômico por stop já previsto.
6. Agentes e baselines seguem a mesma fase. A entrada igualitária passa a
   manter posições até o início dessa fase, com eventual saída parcial em
   vários pontos, em vez de uma tentativa exclusiva no último ponto.

Os 54 pontos são uma fase de saída dentro de um único episódio diário, não
uma volta aos episódios de uma hora: carteira, caixa e relógio continuam
atravessando a sessão inteira, sem reinicialização intradiária.

A referência igualitária demandou no máximo quatro pontos; optar por uma fase
curta apoiada somente nela ignoraria a concentração permitida pelo espaço de
ações atual. A fase de 54 procura acomodar esse cenário mais exigente sem
impor, nesta revisão, um novo limite de concentração. Ainda precisamos testar
inventários efetivamente produzidos e decidir se limites causais adicionais
são necessários. Nenhuma janela finita garante ausência de resíduos quando
faltam dados ou capacidade futura.

## Consequências e próxima implementação

Atualização: a [fase foi implementada e tem ativação explícita](030_wind_down_implementation.md)
no núcleo e no adaptador sintético. O texto de proposta acima documenta sua
derivação; os manifestos históricos ainda precisam ser ligados à emenda.

A nova saída altera o ambiente de treinamento e os baselines; resultados do
núcleo anterior não podem ser comparados como se a regra fosse a mesma.
A recompensa atual ainda não impõe inventário terminal zero. A emenda de
[admissibilidade](028_day_trading_admissibility_review.md) continua necessária,
assim como a revisão do objetivo de aprendizagem e do regime de conta.

Implementar primeiro a fase com testes sintéticos de fronteira, múltiplas
vendas parciais, consumo único de captura, ausência de livro, fechamento
reduzido e início tardio. Depois integrar treino/avaliação e verificar os
novos inventários em treino, antes de congelar os manifestos e executar os
orçamentos completos. Julho não será usado para ajustar a fase.

## Artefatos e reprodução

Resultado: `results/v3_exit_capacity_audit_2026-10-12/diagnostics.json`.
O manifesto guarda hashes dos dados de treino, grades, protocolos originais e
código. Os artefatos anteriores permaneceram intactos.

```sh
caffeinate -i /Users/ebezerra/miniconda3/bin/python3 \
  -m rl_boleta.exit_capacity_audit \
  --design-dir results/v3_two_scenario_design_verified_2026-10-12 \
  --output-dir results/v3_exit_capacity_audit_nova_execucao
```

O diretório de saída precisa ser novo. Os seis testes específicos passaram:
capacidade inteira por nível comparada à execução, reutilização de captura,
lacunas/profundidade subinteira, capacidade insuficiente preservada no
denominador, janelas inválidas/saída descoberta e bloqueio de datas fora de
março–maio antes de carregar preços.
