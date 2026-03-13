# Reinforcement Learning Trading Project

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