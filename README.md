# Reinforcement Learning Trading Project

O pipeline experimental está em reconstrução a partir da formulação do paper.
O [escrutínio conceitual do manuscrito](docs/paper_conceptual_review.md)
identifica as correções necessárias de causalidade, execução, contabilidade,
recompensas e avaliação antes da implementação do novo simulador.
As [etapas 1–3 da revisão do paper](docs/paper_revision_steps_1_3.md) incorporam
essa especificação ao rascunho, com resultados antigos arquivados e pendências
de dados, implementação e avaliação identificadas.
A [etapa 4 da revisão](docs/paper_revision_stage_4.md) incorpora ao manuscrito
as contagens auditadas, o calendário e as limitações do alinhamento temporal.
A [revisão da etapa 5](docs/protocol_day_trading_revision.md) especifica um
episódio por pregão, também disponível no [protocolo v2 em JSON](configs/experimental_protocol_v2.json).
A [versão inicial da etapa 5](docs/paper_revision_stage_5.md) foi preservada como histórico.
A [auditoria dos episódios legados](docs/legacy_episode_audit.md) mostra que
o código disponível percorre partições inteiras, sem impor encerramento por pregão.
O protocolo requer o novo simulador e não é executável pelo treinador legado.
A [auditoria de cobertura por pregão](docs/session_coverage_audit.md) consolidou
os manifestos de março–julho: sob as hipóteses temporais registradas, nenhum
pregão satisfaz a sequência completa do protocolo v2. O arquivo atual não
atinge os mínimos de viabilidade; `training_ready` permanece falso.
A [auditoria das causas das lacunas](docs/gap_causes_audit.md) aponta a cadência
da coleta como principal obstáculo.
O [núcleo econômico](docs/economic_kernel.md) já implementa execução,
contabilidade e recompensa, com testes sintéticos. O [controlador por pregão](docs/session_replay.md)
liga esse núcleo ao calendário e aos livros do novo CSV, com janela causal e
liquidação diária. A [camada de observações e integração PPO](docs/observations_and_training.md)
implementa features causais, normalização congelada e um adaptador Gymnasium,
com comando de treino exclusivamente sintético. A [integração dos quatro algoritmos](docs/four_algorithm_integration.md)
inclui PPO, A2C, SAC e DDPG, com configurações explícitas e verificação de
checkpoint. Experimentos históricos e execução dos orçamentos completos ainda estão pendentes.
O construtor do ambiente legado está bloqueado
para impedir novos experimentos com episódios definidos por partições de linhas.
A nova etapa de preparação de dados está documentada em
[docs/data_pipeline.md](docs/data_pipeline.md) e pode ser executada com
`python -m rl_boleta.data_pipeline --help`. Ela exige snapshots estruturados
e não reutiliza automaticamente os CSVs ou resultados da dissertação.
Os Parquet brutos foram auditados para possível reconstrução:
[docs/raw_data_audit.md](docs/raw_data_audit.md).
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
