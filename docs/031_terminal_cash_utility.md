# Objetivo de aprendizagem para encerramento em caixa

> Registro **031** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 030](030_wind_down_implementation.md) · Seguinte: [Registro 032](032_account_regimes.md)

Implementação de 12/10/2026, após a fase de saída sucessiva. A ativação é
explícita: `reward_objective='terminal_cash_utility'`. O padrão anterior
`marked_wealth` permanece para reproduzir os artefatos antigos.

## Definição e interpretação

Sejam V o patrimônio marcado, C o caixa contábil, theta o capital inicial,
alpha a escala de recompensa e I_T = V_T - C_T o valor marcado do inventário
restante. As recompensas intermediárias continuam alpha*(V_next-V_current)/theta.
Somente em um término econômico, a última recompensa subtrai alpha*I_T/theta.
Com gamma=1 e início em caixa, a soma resulta em:

`sum(reward) = alpha * (C_T - theta) / theta`.

É uma utilidade de aprendizagem que dá crédito terminal apenas ao caixa,
incentivando a realização das vendas. Não se ajusta um coeficiente por retorno
de validação ou de julho: a subtração tem peso um por essa identidade.

Isso **não é uma garantia matemática de inventário zero**. A seleção continua
exigindo encerramento em caixa em todas as datas/sementes comuns de validação.
O substituto de aprendizagem e o filtro cumprem funções diferentes. Um
método que falhe permanece com suas métricas e não ganha seleção por essa falha.

Também não é perda financeira realizada. As ações continuam na carteira,
o patrimônio marcado permanece intacto e o retorno realizado continua ausente
se houver resíduos. O ajuste não debita caixa, não inventa vendas, não muda
fees, fills ou preços. Denominamos o termo
`terminal_inventory_adjustment_usd`, separado dos custos financeiros.

Exemplo: início de US$ 100 mil, término com US$ 90 mil em caixa e ações
marcadas em US$ 12 mil. O retorno marcado continua +2%; o sinal acumulado de
aprendizagem é -10% com alpha=1. A carteira continua valendo US$ 102 mil na
referência observada. O sinal -10% significa que o objetivo não dá crédito
às posições que não foram encerradas; não afirma perda realizada de US$ 10 mil.

Se o episódio termina flat, I_T=0, e as recompensas são idênticas às anteriores.
Um stop concluído em caixa segue essa regra. Se faltam dados no ponto final,
há truncamento: não se aplica ajuste terminal nem se atribui utilidade de
encerramento completo ao episódio. O adaptador de treino continua abortando
um truncamento inesperado em vez de aceitá-lo como término econômico.

A identidade acima vale para gamma=1. Variantes descontadas preservam o termo,
mas sua soma descontada tem outra interpretação e não equivale ao retorno
terminal em caixa. Essa diferença precisa constar no protocolo das variantes.

## Integração e relatórios

O núcleo, controlador, Gymnasium e runner sintético aceitam o modo explícito.
O `info` separa objetivo, ajuste terminal e mudança de patrimônio marcado.
O resumo do episódio inclui `learning_return`, distinto de `marked_return`
e `realized_return`. A observação não muda de dimensão nesta etapa.

O adaptador histórico lê `environment.reward_objective` do protocolo imutável
vinculado ao normalizador. Artefatos antigos sem esse campo conservam o modo
marcado. Novos experimentos terão de registrar esse campo e a fase de 54
pontos em manifestos novos; o JSON de proposta não ativa os antigos.

## Regime de conta: duas opções implementadas

Atualização: o usuário escolheu disponibilizar as duas opções no pipeline.
Os [regimes cash e buying power intradiário](032_account_regimes.md) foram
implementados com poder de compra observado e escolha explícita por campanha.
O texto abaixo conserva a justificativa; a escolha não está mais pendente,
mas a geração e verificação dos novos manifestos históricos está.

Caixa contábil não equivale automaticamente a dinheiro liquidado ou poder de
compra. Para 2025, o ciclo padrão era T+1, conforme a
[SEC](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/new-t1-settlement-cycle-what-investors-need-know-investor-bulletin).
Seu boletim sobre [contas cash](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/updated-9)
explica as condições de pagamento e os problemas de revender compras ainda
não pagas. Não interpretamos T+1 como proibição geral de comprar novamente
com receitas pendentes: o problema depende de pagamento e revenda.

Para um experimento conservador de day trading em conta cash, a proposta é
pagar cada compra, incluindo taxas, apenas com recursos já liquidados no
início do dia. Receitas de vendas entram no patrimônio e no resultado econômico,
mas não recompõem esse orçamento de compras durante o pregão. É uma restrição
operacional escolhida para a simulação, sem modelar todas as modalidades de
pagamento permitidas a uma conta real. Cada episódio independente começa com
capital liquidado; não representa uma série composta de reinvestimentos.

Outra opção é declarar buying power intradiário que permita reutilizar vendas,
com limite de exposição sem alavancagem e hipóteses explícitas sobre conta,
corretora e custos. Não presumir que proibir exposição alavancada elimine
exigências da conta. As duas opções foram implementadas; cada campanha
deve declarar e congelar sua escolha. O comportamento histórico anterior de reutilizar
vendas imediatamente continua documentado como hipótese, não certificação.

O modo conservador cash separa caixa contábil, recursos disponíveis para compra
e receitas pendentes no estado e na execução. O poder de compra é observado
pelo agente. A nova dimensão, os vínculos e as estimativas de memória dos
modelos estão descritos na documentação dos regimes.

## Verificação e próximos passos

A regressão passou com **242 testes**, sem falhas ou testes pulados.
O smoke PPO de 384 passos com a fase de 54 pontos e o novo objetivo passou,
com ator atualizado/finito e previsão idêntica após recarregar o checkpoint.
As três avaliações sintéticas terminaram em caixa. Os pesos foram exatamente
iguais aos do smoke anterior com as mesmas sementes e fase: nessas trajetórias
flat, o ajuste é zero. Os testes com resíduos exercitam a diferença do novo
objetivo e sua integração no Gym.

Artefato: `results/v3_terminal_cash_utility_smoke_2026-10-12/report.json`.

Os testes cobrem: utilidade de caixa com lucro marcado e resíduos; manutenção
exata do balanço; recompensa inalterada quando flat; ajuste somente no término
econômico; truncamento sem ajuste; escala alpha e stop. A integração Gym cobre
resíduos na fase de 54 pontos, utilidade acumulada e relatório financeiro
separado. Não foram usados dados históricos ou retornos de julho nesses testes.

Com as opções de conta implementadas, gerar os novos vínculos
históricos, verificar inventários/capacidade de saída em treino e executar o
novo diagnóstico integrado. Os orçamentos de pesquisa continuam bloqueados.
