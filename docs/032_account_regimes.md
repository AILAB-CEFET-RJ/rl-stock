# Regimes de conta configuráveis no pipeline v3

> Registro **032** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 031](031_terminal_cash_utility.md) · Seguinte: [Registro 033](033_account_campaign_inputs.md)

Implementação de 12/10/2026, após a decisão de permitir as duas opções.
Ambas podem representar decisões intradiárias de um operador humano, com
condições diferentes de pagamento e acesso ao capital. A
[SEC explica operações no mesmo dia em conta cash](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/updated-9),
enquanto a [FINRA descreve operações intradiárias e margem](https://www.finra.org/investors/insights/frequent-intraday-trading).
Nossos modos são especificações de replay; não reproduzem todas as condições
ou regras de uma corretora.

## Dois modos

| Parâmetro | `cash_settled` | `intraday_buying_power` |
| --- | --- | --- |
| Capital inicial | Recursos disponíveis no início do episódio | Capital próprio disponível no início do episódio |
| Limite de compras | Saldo inicial ainda não gasto, incluindo taxas | Caixa contábil líquido disponível, incluindo receitas de vendas |
| Venda repõe orçamento no mesmo pregão? | Não | Sim, por hipótese explícita de buying power |
| Posições vendidas / exposição alavancada | Não | Não |
| Receitas pendentes | Registradas, sem uso para novas compras | Registradas e admitidas no poder de compra |

Exemplo ilustrativo sem taxas: começar com US$ 100 mil, comprar usando todo
o saldo e vender por US$ 101 mil. O caixa contábil passa a US$ 101 mil nos
dois modos. No modo cash, o poder de compra intradiário é zero; no outro,
é US$ 101 mil. Havendo dinheiro inicial não gasto, o modo cash pode continuar
comprando com esse saldo. A restrição não é "uma operação por dia".

O modo cash usa uma convenção conservadora: todas as compras destinadas a
ser revendidas nesse episódio são integralmente pagas com recursos iniciais
já liquidados. A SEC distingue compras com receitas pendentes de sua revenda
antes do pagamento; portanto, não afirmamos uma proibição geral de comprar
com receitas pendentes em uma conta cash real.

No modo intradiário, a disponibilidade de receitas é hipótese de financiamento/
compensação da conta. O simulador não concede crédito para comprar além do
caixa econômico líquido, não ativa alavancagem 2x/4x e não cobra juros
intradiários adicionais. A ausência desses custos é uma hipótese do estudo,
não uma afirmação sobre tarifas ou contratos reais. Falhas de encerramento
não viram posições financiadas e acompanhadas no pregão seguinte: continuam
outcomes com resíduos de episódios independentes.

Para o período de março–julho/2025, requisitos aplicáveis à conta devem ser
interpretados pelas regras daquela época, não por mudanças posteriores de
2026. A [documentação histórica da FINRA](https://www.finra.org/sites/default/files/2024-08/4210-interp-change-guide-2024.pdf)
é referência para essa distinção. O modo de buying power pressupõe uma conta
habilitada e suficiente para as operações modeladas; não reconstrói chamadas
de margem, requisitos específicos de cada ativo ou autorização da corretora.

## Livro-caixa e execução

O núcleo mantém `funding_balance` e `pending_sale_proceeds`:

`caixa_contabil = funding_balance + pending_sale_proceeds`.

Compras executadas, incluindo taxas, reduzem o primeiro termo. Vendas líquidas
de taxas aumentam o segundo. Ordens canceladas ou sem fill não alteram esses
saldos. No modo cash, o primeiro termo permanece não negativo e limita todas
as compras, inclusive quando há vendas e compras na mesma execução. Receitas
dessas vendas não aumentam o limite daquela execução.

No modo intradiário, o saldo de financiamento pode ficar negativo ao reutilizar
receitas, compensado pelos valores a receber; isso não é caixa econômico
negativo nem exposição alavancada. O poder de compra é o caixa contábil líquido.
A posição continua long-only, com participações e caixa econômico não negativos.

Não ocorre settlement durante o episódio. Essa representação intradiária
não é um motor completo de liquidação T+1 entre dias: cada sessão experimental
independente começa com o capital fixo. O último caixa inclui receitas de
vendas realizadas mas pendentes de transferência, não necessariamente saldo
imediatamente sacável. O objetivo `terminal_cash_utility` usa esse caixa
contábil líquido, separado do orçamento disponível para novas compras.

A mesma regra vale para agentes, baselines, stops e a fase de saída. Preços,
profundidade, taxas, frescor e consumo das capturas permanecem iguais.

## Observação e configuração

Os modos novos expõem três campos adicionais ao agente: poder de compra e
receitas pendentes, divididos pelo capital inicial, e indicador do regime.
Com 18 ativos, a entrada passa de 15.502 para **15.505 valores**. O tempo
restante continua sendo o último campo, inclusive no terminal. Encoder comum
e cache usam a mesma construção de contexto; não se admite uma conta nova
com encoder que esconda esses campos.

Os normalizadores de features de mercado não precisam de estatísticas de
validação para esses campos: a escala é o capital inicial. Checkpoints e
manifestos devem registrar a dimensão e o regime. A memória mínima estimada
do replay SAC/DDPG de 100 mil transições passa para **12.412.400.000 bytes**
somente nos arrays auditados; demais estruturas continuam adicionais.

Para a integração sintética, selecionar o modo explicitamente:

```sh
caffeinate -i env \
  PYTHONPATH=/private/tmp/rl-stock-training-deps \
  MPLCONFIGDIR=/private/tmp/rl-stock-matplotlib \
  /Users/ebezerra/miniconda3/envs/ailab/bin/python \
  -m rl_boleta.masked_training --synthetic-smoke --algorithm ALL \
  --steps 384 --wind-down-points 54 \
  --reward-objective terminal_cash_utility \
  --account-regime cash_settled \
  --output results/v3_conta_cash_nova_execucao
```

Trocar apenas `--account-regime` para `intraday_buying_power` e usar outro
diretório para a segunda opção.

Na configuração histórica a escolha fica no protocolo, **antes** de gerar
os novos manifestos:

```json
{
  "environment": {
    "account_regime": "cash_settled",
    "reward_objective": "terminal_cash_utility"
  },
  "episode": { "wind_down_execution_points": 54 }
}
```

Esse trecho indica campos a alterar no protocolo completo, não um protocolo
suficiente isoladamente. Para a outra opção, usar `intraday_buying_power`.
O adaptador lê os campos do protocolo imutável ligado ao normalizador e aplica
a mesma opção à validação. Não há override de regime somente na avaliação,
nem troca de regime mantendo um checkpoint ajustado no outro como se fosse
o mesmo experimento.

`legacy_reinvest` conserva comportamento e dimensão de artefatos anteriores;
não é uma terceira proposta de pesquisa. Planos de pesquisa completos exigem
um dos dois modos novos explicitamente congelado. Manifestos históricos
novas e sua verificação continuam pendentes; os antigos não foram alterados.

A possibilidade de configuração não duplica automaticamente os 286 ajustes
planejados. Uma campanha pode escolher um regime. Se compararmos ambos como
experimentos de pesquisa, registrar dois conjuntos independentes de ajustes,
seleção, vínculos e orçamento, antes de avaliar julho.

## Verificação desta implementação

A regressão final passou com **250 testes**, sem falhas ou testes pulados.
Os testes de conta cobrem reutilização de vendas, taxas, orçamento compartilhado
na mesma execução, fills ausentes, observação/cache e leitura do regime pelo
adaptador histórico em dados fabricados ligados a manifestos. O seletor exige
regime explícito para uma seleção de pesquisa completa.

Foram executados oito smokes: PPO, A2C, SAC e DDPG em cada regime, com 384
transições solicitadas (A2C realizou 385), fase de 54 pontos e objetivo
`terminal_cash_utility`. Todos atualizaram o ator, conservaram pesos finitos,
normalizadores congelados e previsão idêntica após recarregar checkpoints.
As 24 avaliações das três datas sintéticas terminaram em caixa; são avaliações
de integração repetidas, não 24 pregões independentes nem evidência histórica.
Hashes de código, checkpoints e normalizadores foram conferidos.

Artefatos: `results/v3_cash_settled_smoke_2026-10-12/` e
`results/v3_intraday_buying_power_smoke_2026-10-12/`.

Próximo passo: gerar os novos manifestos históricos com conta, fase e objetivo
declarados, revalidar os vínculos de normalização e verificar a execução nas
datas de treino. Os orçamentos completos continuam aguardando essa etapa.
