## Treinamento do Agente Multi-Ativo

A função `train_agent_multiasset` permite treinar agentes de Reinforcement Learning
em múltiplos ativos financeiros usando dados históricos.

---

### Entrada

- `file`: CSV de dados de treinamento processados.
- `tickers`: lista de ativos a serem usados no treino.
- `repetitive_iteration_number`: número da iteração ou fold (para salvar modelo e normalizador).
- `algorithm`: algoritmo de RL a ser usado: "PPO", "A2C", "DDPG" ou "SAC" (default="PPO").
- `gamma`: fator de desconto para recompensas futuras (default=0.995).

---

### Passos Executados

1. **Processamento de Dados**
   - Usa `process_data` para preparar o dataset de treino.
   - Substitui valores NaN, infinitos positivos ou negativos por 0.

2. **Seleção de Algoritmo**
   - Suporta PPO, A2C, DDPG e SAC.
   - Levanta erro se o algoritmo não for suportado.

3. **Ambiente RL**
   - Cria `MultiAssetReinforcementLearningEnv` encapsulado em `DummyVecEnv`.
   - Aplica normalização de observações e recompensas (`VecNormalize`).

4. **Treinamento**
   - Configura hiperparâmetros como learning rate, n_steps, batch_size, gamma, ent_coef, clip_range.
   - Treina o modelo pelo número total de timesteps (`len(df) * 50`).

5. **Salvamento**
   - Salva o modelo treinado e o normalizador em disco para uso posterior em testes.

6. **Retorno**
   - Dicionário com métricas do treinamento:
     - Recompensas, valor inicial e final, lucro líquido.

---

### Métricas Retornadas

- `recompensas treino`: lucro líquido do agente durante o treino
- `valor inicial treino`: capital inicial
- `valor final treino`: patrimônio líquido final
- `lucro/prejuízo treino`: diferença entre valor final e inicial

---

### Exemplo de Uso

```python
from training import train_agent_multiasset

metrics = train_agent_multiasset(
    file="./data/temp_train.csv",
    tickers=["APPLE", "TESLA"],
    repetitive_iteration_number=1,
    algorithm="PPO",
    gamma=0.995
)

print(metrics)
```