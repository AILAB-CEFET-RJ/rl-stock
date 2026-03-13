# Estudo de Ablação de Features

Este script (`rl_boleta.ablation_test`) executa um **estudo de ablação  para avaliar a importância das diferentes *features* utilizadas por um agente de **Reinforcement Learning (RL)** em um ambiente de **trading multiativo**.

O objetivo é analisar como a remoção de determinadas informações de entrada impacta o desempenho do modelo.

---

# Visão Geral do Pipeline

O experimento segue as seguintes etapas:

---

## 1. Carregamento do Dataset

O dataset agregado é carregado a partir do arquivo:

```
dados_agregados_final.csv
```

Após o carregamento:

- linhas com valores ausentes são removidas
- os índices são reorganizados

Isso garante que o treinamento ocorra com dados consistentes.

---

## 2. Divisão Temporal Treino/Teste

O dataset é dividido de forma **temporal**, evitando vazamento de informação futura.

- **80% dos dados → treinamento**
- **20% dos dados → teste**

---

## 3. Definição dos Conjuntos de Features

O experimento testa diferentes configurações de features, incluindo:

### Conjunto completo

- Todas as features disponíveis.

### Remoção individual de features

Cada feature é removida isoladamente para avaliar sua contribuição para o desempenho do modelo.

Exemplos:

- `remove_Prices`
- `remove_Shares`
- `remove_Last_10_Prices`

### Remoção por grupos

Alguns conjuntos específicos também são testados:

**Sem variáveis de tempo**

- `Time_Hour`
- `Time_Minute`
- `Time_Second`

**Apenas informações de preço**

Remove variáveis relacionadas a volume.

**Apenas informações de volume**

Remove variáveis relacionadas a preços.

---

## 4. Máscara de Features

Para cada configuração de ablação:

1. As features selecionadas são **mascaradas (zeradas)** no dataset.
2. Dois datasets temporários são gerados:

```
temp_train.csv
temp_test.csv
```

As colunas seguem o padrão:
```
<TICKER>_<FEATURE>
```

Exemplo:

```
APPLE_Prices
TESLA_Shares
APPLE_Last_10_Prices
```

---

## 5. Treinamento do Agente

Para cada configuração de features e algoritmo de RL (ex: **PPO**):

1. O agente multiativo é treinado utilizando o dataset de treino
2. O agente é avaliado utilizando o dataset de teste

As funções utilizadas são:

- `train_agent_multiasset()`
- `test_agent_multiasset()`

---

## 6. Coleta dos Resultados

Para cada execução são armazenadas informações como:

- conjunto de features utilizado
- algoritmo utilizado
- ativos considerados
- métricas de treinamento
- métricas de teste

Os resultados são agregados em um arquivo CSV:

```
results/ablation/ablation_results_<timestamp>.csv
```

---

# Objetivo do Experimento

O estudo de ablação permite responder perguntas importantes sobre o modelo:

- Quais **features são mais importantes** para o agente de trading?
- O modelo depende mais de **informações de preço ou volume**?
- Variáveis **temporais** influenciam as decisões?
- O agente continua performando bem mesmo com **sinais removidos**?

Essas análises ajudam a entender melhor o comportamento do modelo e a **avaliar a robustez da estratégia de trading baseada em Reinforcement Learning**.