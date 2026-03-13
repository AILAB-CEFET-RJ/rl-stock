# Ambiente Multi-Ativo de Reinforcement Learning

O `MultiAssetReinforcementLearningEnv` é um ambiente personalizado baseado em **Gym**
projetado para treinar agentes de **Reinforcement Learning (RL)** em cenários de
**trading multi-ativo** utilizando dados históricos de mercado.

O ambiente simula decisões de compra e venda em múltiplos ativos ao longo do
tempo, levando em consideração **custos de transação**, **slippage** e o
**estado atual do portfólio**.

---

# Funcionalidades

## 1. Observações Detalhadas

Cada observação contém uma **janela temporal de dados normalizados**
para cada ativo, permitindo que o agente capture padrões de curto prazo.

As features incluídas para cada ativo são:

- **Shares** (volume)
- **Prices** (preço)
- **Time_Hour**
- **Time_Minute**
- **Time_Second**
- **Last_10_Prices**
- **Last_10_Shares**

---

# 2. Ações

As ações são **contínuas para cada ativo**.

Intervalo: $[-1, 1]$


Interpretação:

| Valor da ação | Significado |
|---|---|
| `> DELTA` | Comprar ativo |
| `< -DELTA` | Vender ativo |
| `[-DELTA, DELTA]` | Manter posição |


### Regras de Execução

- Compras utilizam **apenas 10% do caixa disponível por ação**
- Vendas são proporcionais à **posição atual do ativo**
- Custos de transação e slippage são aplicados

---

# 3. Slippage e Custos de Transação

Para aproximar o ambiente de condições reais de mercado, são simulados:

### Slippage

Diferença entre preço esperado e preço real de execução.

### Custos de transação

Taxa aplicada em cada operação.


Esses fatores reduzem retornos irreais e incentivam estratégias mais eficientes.

---

# 4. Gestão de Portfólio

O ambiente mantém o estado completo do portfólio:

- **Saldo em caixa (`balance`)**
- **Quantidade de ações por ativo (`shares_held`)**
- **Patrimônio líquido (`net_worth`)**

O patrimônio líquido é calculado como:

$net\_worth = balance + \sum(shares\_held * preço\_atual)$


### Estado do Portfólio na Observação

A observação inclui também:

- **Peso de cada ativo no portfólio**
- **Proporção de caixa disponível**

Essas informações são replicadas ao longo da janela temporal para manter o formato da observação.

---

# 5. Recompensa

A recompensa é baseada no **retorno percentual do patrimônio líquido**.

### Retorno do passo

$step\_return = (net\_worth_t - net\_worth_{t-1}) / net\_worth_{t-1}$


Inicialmente:

$reward = step\_return$


Após acumular histórico suficiente, é aplicado um **Sharpe Ratio móvel simplificado**:


Isso incentiva o agente a:

- Maximizar retorno
- Minimizar volatilidade

---

# 6. Reset e Step

## `reset()`

Reinicia o ambiente para o estado inicial.

### Estado inicial

- `balance = initial_amount`
- `net_worth = initial_amount`
- `shares_held = 0`
- `deslocamento = OBSERVATION_WINDOW`

### Retorna
> observation


---

## `step(action)`

Executa a ação do agente.

Fluxo interno:

1. Obtém preços atuais
2. Executa compras/vendas
3. Atualiza patrimônio líquido
4. Calcula recompensa
5. Avança um passo no dataset

### Retorna
> (observation, reward, done, info)


Onde:

| Campo | Descrição |
|---|---|
| observation | nova observação |
| reward | recompensa calculada |
| done | indica fim do episódio |
| info | métricas adicionais |

Exemplo de `info`:
> {"final_net_worth": valor}


---

# Parâmetros Principais

| Parâmetro | Descrição |
|---|---|
| `OBSERVATION_WINDOW` | tamanho da janela temporal |
| `initial_amount` | capital inicial |
| `TRANSACTION_COST` | custo por operação |
| `SLIPPAGE_RATE` | slippage simulado |
| `DELTA` | threshold mínimo de ação |
| `n_assets` | número de ativos |

---

# Estrutura da Observação

Formato:
> (features_per_asset * n_assets + n_assets + 1, window)


Componentes:

### Features por ativo (7)

1. Shares normalizado
2. Prices normalizado
3. Time_Hour
4. Time_Minute
5. Time_Second
6. Last_10_Prices
7. Last_10_Shares

### Estado do portfólio

- pesos dos ativos
- proporção de caixa

---

# Uso Típico

```python
import pandas as pd
from env_multiasset import MultiAssetReinforcementLearningEnv

df = pd.read_csv("dados_agregados_final.csv")

tickers = [
    "APPLE",
    "TESLA",
    "MICROSOFT"
]

env = MultiAssetReinforcementLearningEnv(
    mode="train",
    df=df,
    tickers=tickers
)

obs = env.reset()
done = False

while not done:

    action = env.action_space.sample()

    obs, reward, done, info = env.step(action)

print("Patrimônio final:", info["final_net_worth"])
```