## Teste do Agente Multi-Ativo

A função `test_agent_multiasset` avalia o desempenho de um agente de Reinforcement Learning
treinado em múltiplos ativos, comparando-o com uma estratégia **Buy & Hold**.

---

### Entrada

- `file`: caminho para o CSV de teste processado
- `tickers`: lista de ativos a serem avaliados
- `repetitive_iteration_number`: número da iteração ou fold (para carregar modelo e normalizador)

---

### Passos Executados

1. **Processamento de Dados**
   - Usa `process_data` para preparar o dataset de teste.

2. **Baseline Buy & Hold**
   - Calcula o lucro final de uma estratégia passiva (comprar no início e manter até o fim).

3. **Ambiente RL**
   - Cria ambiente `MultiAssetReinforcementLearningEnv` encapsulado em `DummyVecEnv`.
   - Carrega normalizador `VecNormalize` e modelo PPO treinado.

4. **Execução do Episódio**
   - O agente recebe observações e gera ações a cada passo.
   - Recompensas cumulativas são calculadas.
   - O patrimônio líquido final do agente é registrado.

5. **Exibição de Resultados**
   - Consolida métricas do agente e da estratégia Buy & Hold no console.

6. **Retorno**
   - Retorna um dicionário com métricas de desempenho e lucro comparativo.

---

### Métricas Retornadas

- `recompensas teste`: soma das recompensas recebidas pelo agente
- `valor inicial teste`: capital inicial
- `valor final teste`: patrimônio líquido final do agente
- `lucro/prejuízo teste`: lucro absoluto do agente
- `retorno teste`: lucro relativo (%)
- `lucro buy and hold`: lucro absoluto da estratégia Buy & Hold

---

### Exemplo de Uso

```python
from testing import test_agent_multiasset

metrics = test_agent_multiasset(
    file="./data/temp_test.csv",
    tickers=["APPLE", "TESLA"],
    repetitive_iteration_number=1
)

print(metrics)
```