## Treinamento Multi-Ativo com Cross-Validation Temporal e Teste de Significância

Este script realiza o **treinamento e teste de agentes de Reinforcement Learning (RL)**
em múltiplos ativos financeiros, usando **validação temporal (TimeSeriesSplit)**,
gerando resultados detalhados, resumo estatístico e teste de significância contra
a estratégia **Buy and Hold**.

---

### Funcionalidades Principais

1. **Configuração de Parâmetros**
   - Algoritmos disponíveis (ex: PPO)
   - Número de folds (TimeSeriesSplit)
   - Gamma para RL

2. **TensorBoard**
   - Inicializa TensorBoard automaticamente para monitoramento do treino.
   - Exibe URL de acesso no console.

3. **Preparação de Dados**
   - Carrega dataset multi-ativo
   - Remove valores ausentes
   - Exibe número de linhas e ativos usados

4. **Cross-Validation Temporal**
   - Usa TimeSeriesSplit para separar conjuntos de treino e teste
   - Gera arquivos temporários CSV por fold

5. **Treinamento e Teste de Agentes RL**
   - Chama `train_agent_multiasset` e `test_agent_multiasset` para cada fold e algoritmo
   - Resultados consolidados em um DataFrame

6. **Salvamento de Resultados**
   - **Resultados completos**: CSV por execução (`reports/full/`)
   - **Resumo estatístico**: métricas agregadas como média, desvio padrão, porcentagem de lucro (`reports/summary/`)
   - **Teste de significância**: compara retornos do agente com Buy & Hold (`statistics/`)

7. **Teste de Significância Estatística**
   - Usa função `test_significance_buy_and_hold`
   - Gera histogramas comparativos e arquivo JSON
   - Indica se o agente supera significativamente o Buy & Hold

---

### Métricas Calculadas no Resumo

- Média do lucro final em teste
- Desvio padrão do lucro final
- Média de recompensas do teste
- Percentual de iterações com lucro
- Retorno médio em teste (quando disponível)

---

### Exemplo de Saída

- `reports/full/{timestamp}_multiasset.csv` → resultados detalhados por fold e algoritmo
- `reports/summary/{timestamp}_multiasset_summary.csv` → resumo das métricas
- `statistics/significancia_multiasset_{timestamp}.csv` → resultados estatísticos comparando com Buy & Hold
- `./logs/` → logs do TensorBoard

---

### Observações

- Permite comparação robusta de agentes RL multiativos com baseline Buy & Hold.
- Estrutura modular: suporta múltiplos algoritmos, folds e ativos.
- Fácil integração com pipelines de backtesting ou treinamento contínuo.