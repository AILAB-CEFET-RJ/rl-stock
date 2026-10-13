# Reinforcement Learning Trading Project

A sequência das revisões, auditorias e implementações está no
[índice cronológico da documentação](docs/README.md).

A [proposta v3](docs/018_protocol_v3_proposal.md) investiga início causal e lacunas
por ativo sem reiniciar a carteira. Seu [núcleo e controlador sintéticos](docs/019_missing_data_core.md)
já estão disponíveis, assim como as [observações mascaradas e a normalização](docs/020_masked_observations.md).
O [adaptador Gymnasium e os quatro algoritmos](docs/021_masked_training.md) também
estão integrados para treinamento sintético. A [grade histórica parcial e os
baselines v3](docs/022_masked_preparation_and_baselines.md) estão disponíveis para
diagnóstico. A [regra de lacunas e a elegibilidade condicional](docs/023_gap_rule_and_conditional_eligibility.md)
estão congeladas no rascunho v3. O [desenho de dois cenários](docs/024_two_scenario_experiments.md)
prevê treinamentos independentes e comparação em datas comuns; a normalização
histórica de treino já foi [implementada por cenário](docs/025_historical_normalization.md).
A [integração histórica curta](docs/026_historical_training_integration.md) verificou os
quatro algoritmos nos dois cenários. O [executor de seleção por validação](docs/027_validation_selection.md)
foi verificado com orçamento diagnóstico; seleção protocolar, variantes e
reajuste final continuam pendentes. O v2 permanece inalterado.
Uma [revisão de admissibilidade para day trading](docs/028_day_trading_admissibility_review.md)
exige encerramento em caixa na validação para a seleção completa; sua execução
aguarda a revisão da preparação de saída, recompensa e regime de conta.
A [auditoria de capacidade de saída no treino](docs/029_exit_capacity_audit.md)
fundamenta uma fase comum de vendas sucessivas.
A [fase de saída foi implementada no núcleo v3](docs/030_wind_down_implementation.md)
com ativação explícita; os manifestos históricos antigos preservam sua regra.
O [objetivo de utilidade terminal em caixa](docs/031_terminal_cash_utility.md) foi
implementado para aprendizagem, separado do resultado financeiro; o regime
da conta pode ser escolhido entre [duas opções implementadas](docs/032_account_regimes.md).
Os [novos vínculos históricos por regime](docs/033_account_campaign_inputs.md)
incluem protocolos, manifestos de datas e normalizadores de treino verificados.
Os [16 treinos históricos curtos](docs/034_historical_smoke_new_accounts.md)
passaram após corrigir o contexto da conta no encoder da avaliação congelada.
A preparação da workstation02 inclui [verificação do ambiente e CUDA](docs/037_workstation02_cuda_and_storage.md),
[testes e transferência bruta](docs/038_workstation02_tests_and_raw_transfer.md) e
[reconstrução canônica com comparação integral](docs/039_workstation02_canonical_rebuild.md).
O [registro de fechamento da branch v3](docs/040_v3_branch_integration.md)
consolida o escopo entregue e as pendências para a campanha experimental.

O pipeline experimental está em reconstrução a partir da formulação do paper.
O [escrutínio conceitual do manuscrito](docs/002_paper_conceptual_review.md)
identifica as correções necessárias de causalidade, execução, contabilidade,
recompensas e avaliação antes da implementação do novo simulador.
As [etapas 1–3 da revisão do paper](docs/003_paper_revision_steps_1_3.md) incorporam
essa especificação ao rascunho, com resultados antigos arquivados e pendências
de dados, implementação e avaliação identificadas.
A [etapa 4 da revisão](docs/004_paper_revision_stage_4.md) incorpora ao manuscrito
as contagens auditadas, o calendário e as limitações do alinhamento temporal.
A [revisão da etapa 5](docs/007_protocol_day_trading_revision.md) especifica um
episódio por pregão, também disponível no [protocolo v2 em JSON](configs/experimental_protocol_v2.json).
A [versão inicial da etapa 5](docs/005_paper_revision_stage_5.md) foi preservada como histórico.
A [auditoria dos episódios legados](docs/008_legacy_episode_audit.md) mostra que
o código disponível percorre partições inteiras, sem impor encerramento por pregão.
O protocolo requer o novo simulador e não é executável pelo treinador legado.
A [auditoria de cobertura por pregão](docs/012_session_coverage_audit.md) consolidou
os manifestos de março–julho: sob as hipóteses temporais registradas, nenhum
pregão satisfaz a sequência completa do protocolo v2. O arquivo atual não
atinge os mínimos de viabilidade; `training_ready` permanece falso.
A [auditoria das causas das lacunas](docs/015_gap_causes_audit.md) aponta a cadência
da coleta como principal obstáculo.
O [núcleo econômico](docs/006_economic_kernel.md) já implementa execução,
contabilidade e recompensa, com testes sintéticos. O [controlador por pregão](docs/009_session_replay.md)
liga esse núcleo ao calendário e aos livros do novo CSV, com janela causal e
liquidação diária. A [camada de observações e integração PPO](docs/010_observations_and_training.md)
implementa features causais, normalização congelada e um adaptador Gymnasium,
com comando de treino exclusivamente sintético. A [integração dos quatro algoritmos](docs/011_four_algorithm_integration.md)
inclui PPO, A2C, SAC e DDPG, com configurações explícitas e verificação de
checkpoint. Experimentos históricos e execução dos orçamentos completos ainda estão pendentes.
O construtor do ambiente legado está bloqueado
para impedir novos experimentos com episódios definidos por partições de linhas.
A nova etapa de preparação de dados está documentada em
[docs/data_pipeline.md](docs/data_pipeline.md) e pode ser executada com
`python -m rl_boleta.data_pipeline --help`. Ela exige snapshots estruturados
e não reutiliza automaticamente os CSVs ou resultados da dissertação.
Os Parquet brutos foram auditados para possível reconstrução:
[docs/001_raw_data_audit.md](docs/001_raw_data_audit.md).
O adaptador `python -m rl_boleta.parquet_adapter --help` reconstrói capturas
dos Parquet explicitamente selecionados, com parâmetros de fuso e atraso
registrados. Instale suas dependências com
`python -m pip install -r requirements-data.txt` em ambiente separado.
O preparador oferece `--calendar us-equities-paper-2025`, com datas explícitas,
para aplicar os pregões de março–julho de 2025 e identificar lacunas e trechos
contínuos. A política temporal continua baseada no recebimento das capturas;
os produtos permanecem provisórios enquanto os fusos e o atraso são investigados.

As instruções de treinamento abaixo descrevem a implementação legada, atualmente
bloqueada, que precisa ser migrada antes dos próximos experimentos.

Este repositório contém a implementação de um sistema baseado em **Aprendizado por Reforço** para tomada de decisão em operações financeiras utilizando dados históricos de ativos.

O sistema inclui etapas de:

- Preparação e tratamento de dados
- Treinamento de modelos de RL
- Avaliação de desempenho
- Testes estatísticos
- Experimentos de ablação
- Comparação com estratégias base (ex: Buy and Hold)

---

# Estrutura do projeto
```
├── data
├── logs
├── models
├── results
│   ├── ablation
│   ├── plots
│   ├── reports
│   └── statistics
│
├── rl_boleta
│   ├── ablation_test.py
│   ├── buy_and_hold.py
│   ├── config.py
│   ├── convert_to_dataset.py
│   ├── data_treatment.py
│   ├── evaluate_significance.py
│   ├── main.py
│   ├── rl_model.py
│   ├── rl_model_ablation.py
│   ├── testing.py
│   └── training.py
│
├── poetry.lock
├── pyproject.toml
└── README.md
```


---

# Descrição dos principais componentes

### `data/`

Contém os datasets utilizados no treinamento e teste dos modelos.

- **dados_final.csv** – dados brutos que serão tratados para o treinamento
- **dados_agregados_final.csv** - dados processados utilizados no treinamento  
- **temp_train.csv / temp_test.csv** – divisões temporárias para treinamento e validação  

---

### `logs/`

Armazena os **logs de treinamento** gerados durante o aprendizado dos modelos.

---

### `models/`

Contém os **modelos treinados** gerados durante os experimentos.

---

### `results/`

Diretório responsável por armazenar os resultados dos experimentos:

- **statistics/** – métricas quantitativas  
- **reports/** – relatórios de análise  
- **ablation/** – resultados de experimentos de ablação  

---

### `rl_boleta/`

Contém o **código principal do projeto**.

Principais módulos:

- **training.py** – treinamento dos agentes de RL  
- **testing.py** – avaliação dos modelos treinados  
- **rl_model.py** – definição e configuração dos modelos de RL  
- **rl_model_ablation.py** – variações dos modelos para experimentos de ablação  
- **buy_and_hold.py** – estratégia baseline de comparação  
- **convert_to_dataset.py** – conversão de dados brutos para formato de dataset  
- **data_treatment.py** – tratamento e limpeza de dados  
- **evaluate_significance.py** – testes estatísticos de significância  
- **config.py** – configurações gerais do projeto  
- **main.py** – script principal de execução  

---

# Configuração

Para rodar este projeto, siga os seguintes passos:

## 1. Instalar dependências

Abra o terminal dentro da pasta do projeto e execute:

```bash
poetry install
poetry shell
```

## 2. Com o ambiente instalado e ativado com o passo anterior, execute o seguinte comando:
```bash
python rl_boleta/main.py
```
