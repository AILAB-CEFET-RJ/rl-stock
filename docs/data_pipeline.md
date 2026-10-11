# Preparação dos dados para os novos experimentos

Esta etapa é independente dos CSVs processados e resultados da dissertação. Nenhum
arquivo de `data/` é descoberto ou consumido automaticamente. Os módulos antigos
de conversão e treinamento ainda são legados; não devem ser usados para validar
os novos experimentos.

## Referência metodológica

O contrato de dados segue a seleção de variáveis em `paper/paper.tex`:
cinco níveis bid, cinco níveis ask e dez negócios recentes **por ativo**.
São dez níveis no total, cinco em cada lado, conforme o manuscrito revisado.
A quantidade pode ser alterada pela API
`Config`, e fica registrada no manifesto. O universo é informado explicitamente
por símbolos da bolsa, sem herdar os 19 ativos do `config.py` antigo.

Os preços e quantidades permanecem separados por lado e nível. O midpoint é
uma referência de marcação, não um preço de execução; o futuro simulador deve
executar compras no ask e vendas no bid, respeitando profundidade, custos e
latência. Caixa, posições e P&L serão produzidos pelo simulador, não pelo dataset
de mercado.

Não há normalização nesta etapa. Transformações aprendidas precisam ser
ajustadas exclusivamente no treino. O manuscrito revisado substitui a
normalização pelo máximo do episódio por transformações causais, cuja
implementação pertence ao futuro simulador.

## Inspeção do coletor existente

Código consultado em 08/10/2026:
[cboe-finance-scraper](https://github.com/AILAB-CEFET-RJ/cboe-finance-scraper/tree/d2a09cc6f7536999169cda0233c896131be6371a),
commit `d2a09cc6f7536999169cda0233c896131be6371a`.

Em `collect/crawler.py`, a coleta:

- monta linhas com `data_dict.values()`, interpretando células pelos valores,
  em vez de mapear cada coluna explicitamente; valores ausentes ou repetidos
  podem comprometer a correspondência entre cabeçalho e conteúdo;
- atribui cinco asks e cinco bids por posições fixas de linhas;
- registra `File_Date` durante a passagem pelas linhas, sem ID de snapshot;
- usa a data e hora locais da máquina sem offset; `Date` também vem da máquina,
  apesar de o dicionário de dados a descrever como data da Cboe;
- inclui um horário associado aos negócios recentes, que não comprova o horário
  de mercado do livro inteiro.

Esses riscos motivaram uma [auditoria dos Parquet brutos](raw_data_audit.md).
A varredura confirmou a preservação da estrutura das capturas e permite
reconstrução parcial, preservando a ordem original, sem reutilizar os CSVs
processados. Não há necessidade demonstrada de uma nova coleta neste momento.
O adaptador `rl_boleta.parquet_adapter` reconstrói os blocos originais de dez
linhas, com fuso de coleta explícito e proveniência dos IDs inferidos. Produz
o contrato abaixo em arquivos `.jsonl.gz`, aceitos pelo preparador.
O scraper externo ainda não foi alterado; sua correção fica necessária para
coletas futuras, não como pré-requisito para auditar o histórico existente.

## Adaptador dos Parquet e pendências temporais

O atraso de fonte informado pelo responsável pelo projeto é **três horas**
(`10800` segundos). Isso é uma informação fornecida pelo usuário, registrada
nos metadados; não uma conclusão da auditoria. O fuso da máquina de coleta
permanece desconhecido. `America/Sao_Paulo` para coleta e `America/New_York`
para negócios são hipóteses compatíveis com a mudança observada no horário de
verão americano, que precisam ser confirmadas antes dos experimentos finais.

`available_at` corresponde ao término da captura, convertido pelo fuso informado.
`book_at` permanece nulo: não existe horário de mercado do livro nos Parquet.
Os dez horários dos negócios são convertidos pelo fuso informado para negócios.
Nenhum desses campos recebe uma subtração automática de três horas.

Há duas interpretações explícitas de atraso:

- `unresolved` (padrão): registra o atraso informado, sem correção temporal.
- `availability-lag`: acrescenta somente `provenance.estimated_book_at`, calculado
  como término da captura menos o atraso. É uma estimativa, não substitui
  `book_at` nem altera os negócios. Só deve ser usado para avaliar essa hipótese.

Horários locais ambíguos/inexistentes por mudança de horário de verão são
rejeitados. A data original pertence à máquina de coleta; se a conversão de fuso
atravessar a meia-noite, a data do negócio fica ambígua e o bloco é rejeitado.
Negócios que resultem posteriores à captura também são rejeitados, sem ajuste
para o dia anterior. As dez strings originais de data/hora são preservadas na
proveniência, junto ao SHA-256 do Parquet e posições das linhas, começando em zero.

Os limites de spread e distância do midpoint são parâmetros de sensibilidade;
500 bps no exemplo não significa que esse seja o limite final dos experimentos.
Um bloco incompleto é rejeitado inteiro, sem preencher preços ou fazer médias.
Ativos conhecidos fora do universo são contados separadamente. O manifesto
registra contagens, rejeições, parâmetros e hashes dos arquivos e código.

Exemplo de validação em três datas, incluindo a transição de março:

```bash
python -m rl_boleta.parquet_adapter \
  --input data/data_scrapping_7_3_2025.parquet \
          data/data_scrapping_10_3_2025.parquet \
          data/data_scrapping_27_6_2025.parquet \
  --output-dir results/data_adapter/pilot_2026-10-08_v3 \
  --tickers AAPL TSLA MSFT CSCO F C FCX BAC KO INTC GM AAL NCLH JPM PFE MS DAL NEM \
  --collection-timezone America/Sao_Paulo \
  --trade-timezone America/New_York \
  --source-delay-seconds 10800 --source-delay-interpretation unresolved \
  --max-spread-bps 500 --max-depth-distance-bps 500
```

Os dois fusos ficam marcados como `hypothesis` por padrão. As opções
`--collection-timezone-status confirmed` e `--trade-timezone-status confirmed`
documentam confirmações futuras, sem modificar a conversão. Todos os produtos
do adaptador continuam provisórios: a relação entre atraso e sessão de origem
precisa ser confirmada. O preparador aplica opcionalmente o calendário abaixo e preserva
essa proveniência e identifica entradas provisórias em seu manifesto; o CSV
alinhado ainda não é entrada para treinamento no ambiente legado.

Dependências desta etapa: `python -m pip install -r requirements-data.txt`
em ambiente separado (Python 3.11 ou posterior). A verificação local usou
Python 3.11.13, pandas 2.3.1, numpy 2.3.1 e pyarrow 24.0.0 no ambiente `ailab`
existente, sem instalar ou alterar as dependências de treinamento. Conversão
processa um Parquet por vez; o preparador de alinhamento ainda carrega os
snapshots selecionados em memória, portanto use subconjuntos para os pilotos.

### Validação em 08/10/2026

O piloto acima examinou 272.270 linhas em três datas (07/03, 10/03 e 27/06/2025):
23.393 capturas aceitas, 2.401 rejeitadas e 1.433 capturas de GE fora do universo.
Com os limites exploratórios de 500 bps, as rejeições foram 2.015 por dados
incompletos/inválidos, 382 por distância dos níveis e quatro por spread.
Não houve rejeições temporais sob os fusos hipotéticos desse piloto.

O alinhamento causal com idade máxima de 60 segundos, grade de um minuto e
horário configurado 09:30–16:00 produziu 1.062 instantes conjuntos e rejeitou 111.
Esses números descrevem somente o piloto, sem validar calendário ou atraso.
Os manifestos estão em `results/data_adapter/pilot_2026-10-08_v3/manifest.json`
e `results/data_adapter/aligned_pilot_2026-10-08_v3/manifest.json`.
Diretórios anteriores foram preservados; use um diretório novo para repetir.

Verificação automatizada: `python -m unittest discover -s tests -v`.
Os 31 testes passaram no ambiente descrito, incluindo a passagem de JSONL.gz
pelo preparador, preservação de proveniência, DST, horários futuros, rejeição
de blocos mistos/incompletos e impedimento de sobrescrita de resultados.

## Contrato de entrada: JSONL de snapshots, versão 1

Cada linha contém um objeto JSON completo e independente. Campos obrigatórios:

| Campo | Semântica |
|---|---|
| `schema_version` | Inteiro `1` |
| `snapshot_id` | ID estável e único por ativo e captura |
| `ticker` | Símbolo explícito, por exemplo `AAPL` |
| `source` | Identificação da fonte, preferencialmente URL e versão do coletor |
| `available_at` | Timestamp ISO 8601 com offset, capturado **após** o recebimento de todo o snapshot |
| `bids` | Lista de objetos `price`, `size`; ao menos cinco níveis distintos |
| `asks` | Lista de objetos `price`, `size`; ao menos cinco níveis distintos |
| `trades` | Ao menos dez objetos `at`, `price`, `size`; `at` inclui data e offset |

`book_at` é opcional: horário de mercado do livro, somente quando informado
pela fonte. Ausência permanece `null`; não se estima o horário subtraindo um
atraso presumido de `available_at`. Todos os timestamps são convertidos para UTC.
Uma fonte que informa apenas a hora de um negócio exige tratamento explícito
de data e fuso no coletor; o pipeline não completa essa informação por suposição.

O coletor deve mapear as colunas pelo DOM/cabeçalho e guardar a resposta original
para diagnóstico. Um snapshot incompleto não deve ser preenchido com dados de
outra captura. Bid/ask e negócios recentes são listas independentes, mesmo que
apareçam na mesma linha visual da página. Negócios distintos podem ter o mesmo
horário, preço e quantidade: não são deduplicados por esses valores.

## Execução

Esta etapa usa somente a biblioteca padrão do Python 3.12. A partir da raiz:

```bash
python -m rl_boleta.data_pipeline \
  --input data/raw/structured/snapshots.jsonl \
  --output-dir data/processed/run_001 \
  --tickers AAPL TSLA \
  --frequency-seconds 60 \
  --max-age-seconds 60 \
  --max-spread-bps 100 \
  --max-depth-distance-bps 500 \
  --session-timezone America/New_York \
  --session-start 09:30 \
  --session-end 16:00
```

Os caminhos e os dois ativos são exemplos, não um dataset já existente nem a
definição final do universo experimental. Os limites de 100 e 500 pontos-base
também são exemplos: devem ser justificados e fixados antes dos experimentos.
As duas tolerâncias de preço são obrigatórias na CLI para evitar filtragem
implícita. O programa não sobrescreve um diretório de execução existente.

## Validação e alinhamento temporal

Cada snapshot precisa ter preços e profundidades positivos e finitos, níveis
distintos, bid inferior ao ask, spread e distância dos níveis ao midpoint
dentro dos limites configurados. Negócios exigem preços positivos e quantidades
finitas não negativas. Horários de livro e negócios não podem ser posteriores
ao recebimento. Não há imputação, substituição por zero ou correção de outliers.
Falhas são registradas com arquivo e número da linha.

Snapshots idênticos com o mesmo `(ticker, snapshot_id)` são deduplicados entre
arquivos. Conteúdos conflitantes para o mesmo ID, ou dois IDs para o mesmo ativo
e horário de disponibilidade, abortam a execução: a precedência não é inferida
pela ordem de leitura.

A grade começa no horário de sessão configurado, com intervalo constante.
Em cada instante `t`, escolhe-se para cada ativo o snapshot mais recente com
`available_at <= t`, limitado por `max_age_seconds`. Um ponto sem cobertura
válida de todos os ativos é rejeitado. Não há interpolação, backfill, média de
horários ou agrupamento baseado em um ativo de referência. A idade máxima mede
tempo desde **recebimento**, não a atualidade do livro na fonte.

Snapshots não atravessam datas de sessão. No modo exploratório
`--calendar configured-hours` (padrão para compatibilidade), a grade termina no
último recebimento observado ou no fim configurado da sessão. Esse modo não
verifica dias úteis, feriados ou fechamentos antecipados.

No modo `--calendar us-equities-paper-2025`, o preparador aplica o calendário
versionado de sessões regulares de ações americanas, limitado a 03/03–31/07/2025.
As referências oficiais são o [calendário NYSE/ICE](https://ir.theice.com/press/news-details/2024/NYSE-Group-Announces-2025-2026-and-2027-Holiday-and-Early-Closings-Calendar/default.aspx)
e o [aviso Nasdaq de julho de 2025](https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2025-37).
Não são usados calendários de feriados bancários, futuros ou opções. Há 105
pregões no período; os fechamentos completos são 18/04, 26/05, 19/06 e 04/07,
e 03/07 tem encerramento antecipado às 13:00 de Nova York.

Nesse modo são obrigatórias as datas inicial e final, inclusivas. Datas fora
do escopo verificado e alterações nos horários oficiais causam erro. A grade
cobre **todo o pregão esperado**, mesmo quando faltam arquivos ou capturas no
fim do dia, sem preencher valores. O intervalo é `[abertura, fechamento)`:
390 decisões de um minuto num pregão normal, 210 no encerramento antecipado.
Capturas anteriores à abertura, no fechamento ou posteriores, em feriados ou
fora das datas solicitadas são excluídas do alinhamento e registradas; continuam
preservadas em `snapshots.jsonl`. Não se usa captura anterior à abertura para
preencher o primeiro minuto do pregão.

A política implementada é `--temporal-policy capture-time`: tanto a seleção da
sessão como a causalidade usam `available_at`. O atraso de três horas permanece
registrado sem deslocar negócios ou capturas. Isso mede disponibilidade e
cobertura durante o pregão de **recebimento**, sem certificar a sessão de origem
do livro atrasado. Uma simulação da sessão de origem exigirá confirmar os fusos
e a semântica dos horários, incluindo uma fonte de execução consistente.

Exemplo específico para testar feriado e fechamento antecipado, usando os
Parquet de 02, 03 e 04/07 convertidos pelo adaptador:

```bash
python -m rl_boleta.data_pipeline \
  --input results/data_adapter/calendar_input_2026-10-08/*.jsonl.gz \
  --output-dir results/data_adapter/calendar_pilot_2026-10-08 \
  --tickers AAPL TSLA MSFT CSCO F C FCX BAC KO INTC GM AAL NCLH JPM PFE MS DAL NEM \
  --max-spread-bps 500 --max-depth-distance-bps 500 --max-age-seconds 60 \
  --calendar us-equities-paper-2025 \
  --session-first-date 2025-07-02 --session-last-date 2025-07-04 \
  --temporal-policy capture-time
```

Validação com os Parquet de 02–04/07/2025: 11.979 capturas válidas antes do filtro
de sessão, das quais 3.256 excluídas do alinhamento (277 antes da abertura e
2.979 no fechamento ou depois). Não houve capturas completas aceitas no dia
04/07 pelo adaptador; a exclusão de capturas válidas em feriados é coberta por
teste sintético. O calendário contou 600 pontos esperados em dois pregões,
incluindo a sessão curta de 03/07, e nenhum pregão em 04/07.

| Idade máxima desde recebimento | Pontos válidos | Pontos rejeitados | Trechos contínuos | Maior trecho (pontos) |
|---|---:|---:|---:|---:|
| 60 s | 424 | 176 | 39 | 29 |
| 90 s | 458 | 142 | 13 | 80 |
| 120 s | 468 | 132 | 4 | 262 |

K pontos em grade de um minuto têm K−1 minutos entre seus extremos.
As variantes usam os mesmos arquivos e parâmetros de preço; os diretórios de
90 e 120 segundos acrescentam `_age90` e `_age120` ao nome de saída. A melhora
na continuidade aceita capturas mais antigas; não comprova qualidade ou
atualidade das cotações na fonte. O limite final permanece uma escolha
experimental. Os 39 testes passaram após a incorporação do calendário.

Para reproduzir a entrada desse piloto, use o comando do adaptador com os
arquivos `data_scrapping_2_7_2025.parquet`, `data_scrapping_3_7_2025.parquet` e
`data_scrapping_4_7_2025.parquet` e o diretório de saída
`results/data_adapter/calendar_input_2026-10-08`, mantendo os demais parâmetros
do exemplo anterior. Sempre escolha outro diretório ao repetir uma execução.

O simulador futuro deve preservar os timestamps e reconhecer lacunas e mudanças
de sessão. Remover pontos inválidos e depois tratar as
linhas restantes como minutos consecutivos distorceria o tempo da simulação.
O preparador já atribui `segment_id` e `step_in_segment`, reiniciando ambos
após lacunas e em cada pregão. `segments.csv` registra os limites dos trechos
contínuos. Um segmento ainda não é um episódio: tamanho de janela, horizonte e
estado inicial de carteira serão definidos no simulador.
`segment_id` é um metadado retrospectivo de cobertura, não uma variável da
política. Não se pode informar antecipadamente o tempo até uma lacuna imprevista
nem liquidar retroativamente no minuto anterior a ela. Horizonte fixo conhecido,
fim de pregão e detecção efetiva de falta de dados exigem regras distintas,
conforme o [escrutínio conceitual do paper](paper_conceptual_review.md).
Não há filtros de retorno entre snapshots: detecção de saltos e reconciliação
com outra fonte ainda são necessárias para auditar a qualidade de uma coleta
real. Consistência estrutural não comprova que uma cotação esteja correta.

## Artefatos gerados

| Arquivo | Conteúdo |
|---|---|
| `snapshots.jsonl` | Snapshots válidos normalizados, todos os níveis e negócios recebidos, origem de cada registro |
| `market.csv` | Grade multiativo, cinco níveis por lado e dez negócios por ativo, IDs e horários de origem, idades, midpoint e spread |
| `rejected_snapshots.csv` | Registros rejeitados e motivos, sem apagar o arquivo de entrada |
| `rejected_grid.csv` | Instantes sem cobertura conjunta, com os ativos ausentes ou vencidos |
| `excluded_sessions.csv` | Capturas válidas excluídas por data, feriado ou horário da sessão |
| `session_coverage.csv` | Pontos esperados, aceitos e rejeitados de cada pregão, incluindo dias sem dados |
| `segments.csv` | Trechos contínuos válidos, com início, fim e número de pontos |
| `manifest.json` | Configuração, contagens, cobertura por sessão, SHA-256 das entradas/saídas e do código, versão do Python e limitações |

Uma execução sem pontos alinhados gera os relatórios, marca
`status=no_aligned_rows` e retorna código de saída `2`. A saída `market.csv`
**não é compatível com o ambiente RL legado**: foi criada para a formulação
de microestrutura do paper, cuja implementação será a próxima etapa.

## Verificação

A [auditoria integral de cobertura](session_coverage_audit.md) aplica o contrato
e o calendário a março–julho de 2025, mantendo as hipóteses de relógio explícitas.
Seus manifestos por partição medem elegibilidade de dados sem executar políticas
ou produzir retornos históricos.

```bash
python -m unittest discover -s tests -v
```

Os testes usam somente snapshots sintéticos e diretórios temporários. Cobrem
preservação da profundidade e dos negócios, ausência de informação futura,
fusos/DST, expiração, isolamento entre sessões, conflitos, rejeições,
deduplicação, rastreabilidade e proteção contra sobrescrita.
