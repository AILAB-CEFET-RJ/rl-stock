# Auditoria dos Parquet brutos — 08/10/2026

A auditoria sustenta o reaproveitamento parcial do histórico existente. Não é
necessário iniciar uma nova coleta antes de reconstruir e validar os snapshots
disponíveis. Os CSVs processados e resultados antigos permanecem fora dos novos
experimentos. Nenhum Parquet foi alterado.

## Escopo e método

Foram lidos integralmente os 294 arquivos `data_scrapping_*.parquet`, com
25.142.620 linhas entre 10/07/2024 e 20/11/2025. Todos têm as mesmas nove colunas,
datas internas correspondentes ao nome do arquivo e apenas uma data de captura
por arquivo. Não houve erro de leitura nem linhas excedentes após os blocos de
dez. SHA-256 das entradas foi verificado antes e depois da leitura.

A reconstrução foi **diagnosticada**, não aplicada a um dataset experimental:
cada bloco de dez linhas consecutivas, na ordem original do Parquet, é candidato
a uma captura. Cada bloco foi testado independentemente quanto a ativo, sequência
de cinco asks e cinco bids, datas e horários de coleta. Não se removeu nenhuma
linha nem se ordenou o arquivo antes de definir os blocos.

Os IDs dessas capturas serão inferidos, pois o coletor não os registrou. O ID
deverá derivar do hash do arquivo e da posição original da primeira linha, com
essa origem declarada no manifesto; não deve ser apresentado como ID da fonte.

## Resultado estrutural

Todos os **2.514.262 blocos** preservam o mesmo ativo, a sequência esperada de
lados e horários de coleta consistentes dentro da tolerância auditada de dois
segundos. Não foram detectados blocos duplicados, chaves de captura ambíguas,
níveis de preço repetidos ou livros completos travados/cruzados. As sequências
de asks e bids estão em preço decrescente; os horários dos negócios estão em
ordem não crescente quando completos.

Os arquivos têm datas internas distintas e não sobrepostas. Assim, duplicatas
exatas entre arquivos, que exigiriam também o mesmo `File_Date`, são excluídas
pela separação de datas. As verificações explícitas de duplicidade no código
são feitas dentro de cada arquivo.

**10.140 capturas atravessam a mudança de segundo** dentro das dez linhas.
Agrupar apenas por `(Company, File_Date)` fragmentaria essas capturas. A ordem
original preservada permite reconstruí-las usando o maior horário do bloco
como referência conservadora de coleta, ainda sujeito às limitações do relógio.

## Completude

"Completa" significa dez preços/quantidades de livro válidos, dez negócios
com preços/quantidades válidos, dez horários legíveis e estrutura consistente.
Isso não certifica o valor econômico da cotação nem a possibilidade de execução.

| Escopo | Capturas candidatas | Completas | Percentual |
|---|---:|---:|---:|
| Todo o acervo | 2.514.262 | 2.372.496 | 94,36% |
| 03/03–31/07/2025, 19 ativos | 821.104 | 759.408 | 92,49% |
| Mesmo período, último negócio entre 09:30 e 16:00 | 688.216 | 671.283 | 97,54% |

A última linha é apenas um diagnóstico: o horário do último negócio não é
o timestamp do livro e não substitui a identificação da sessão de mercado.

No período do paper, 59.711 capturas têm livro incompleto/inválido e 7.165 têm
negócios ou horários incompletos. As categorias se sobrepõem; ao todo, 61.696
capturas não atendem à definição de completude. A perda varia por ativo e horário
e não deve ser descrita como remoção aleatória uniforme.

## Qualidade dos preços

O caso de Tesla em 27/06/2025 às 17:00:28 está nos dados brutos: três asks e três
bids não têm preço/quantidade; os dois bids restantes são 156,00 e 32,70,
enquanto os negócios recentes estão próximos de 323,63–323,79. O horário do
negócio mais recente é 16:00:05. Esse bloco deve ser rejeitado para um estado
que exige cinco níveis em cada lado, preservando os valores originais na auditoria.

Esse exemplo não prova deslocamento de colunas pelo scraper. Um livro esvaziado
ou com ofertas distantes também é uma explicação possível. O erro demonstrável
é tratar a média desses níveis como preço representativo para negociação.

Como análise de sensibilidade, os diagnósticos comparam spread e distância de
todos os cinco níveis ao midpoint: no período do paper, restam 708.288 capturas
completas com limite de 100 bps; 735.303 com 500 bps; 743.886 com 1.000 bps.
Esses limites **não foram escolhidos como política de limpeza**. Ofertas
distantes podem ser reais; truncar, substituir ou aproximar preços apagaria a
evidência. A marcação deve usar referências apropriadas e a execução deve usar
o lado e a profundidade disponíveis.

## Cobertura simultânea dos 18 ativos

Excluindo GE, conforme a lista de empresas apresentada no paper, foi avaliada
uma grade de um minuto sobre o relógio de coleta ainda sem fuso. Para cada
instante, só se permite a captura válida mais recente já recebida. Não há
interpolação ou transporte de capturas entre datas.

O denominador é **42.074 pontos**, entre a primeira e a última captura de cada
uma das 94 datas observadas no período. Não representa todos os minutos de
pregão esperados: inclui horários fora de pregão e não inclui datas ausentes.

| Distância máxima dos níveis e spread | Idade máxima desde a coleta | Pontos com os 18 ativos | Datas com cobertura | Maior trecho consecutivo |
|---|---:|---:|---:|---:|
| Sem limite adicional | 60 s | 30.926 (73,50%) | 92 | 134 pontos |
| 500 bps | 60 s | 30.879 (73,39%) | 92 | 134 pontos |
| 500 bps | 90 s | 33.060 (78,58%) | 92 | 390 pontos |
| 500 bps | 120 s | 33.529 (79,69%) | 92 | 391 pontos |

Com limite de 500 bps e idade de 60 s, há 37 trechos com ao menos 51 pontos
consecutivos; com 90 s, há 212. Isso ilustra a sensibilidade da continuidade à
idade máxima, importante para uma janela de 50 observações. Não é justificativa
para escolher a tolerância que maximiza cobertura. O horizonte de treinamento
e o encerramento de sessões ainda precisam respeitar as lacunas e o simulador.

## Relógios e calendário

`File_Date` e os horários dos negócios não contêm fuso. A diferença entre
relógios é compatível com uma máquina em `America/Sao_Paulo` e negócios em Nova
York: em 07/03/2025 o percentil 1 é 7.207 segundos; em 10/03 passa a 3.606 segundos;
em 03/11 volta a 7.205 segundos. Essa é uma **inferência**, não confirmação.
Não atribuímos fuso nem subtraímos atraso presumido dos dados.

O timestamp próprio do livro não existe nos Parquet; `Time` acompanha os
negócios recentes. Também não se preservaram o HTML original, um ID de negócio
ou um indicador explícito de atraso. A afirmação do manuscrito de atraso de
aproximadamente 50 minutos não está validada por esse material e precisa ser
revisada à luz da fonte e dos relógios.

No período do paper, a comparação das datas com o
[calendário oficial da NYSE para 2025](https://ir.theice.com/press/news-details/2024/NYSE-Group-Announces-2025-2026-and-2027-Holiday-and-Early-Closings-Calendar/default.aspx)
identifica 105 datas de sessão, das quais 92 têm coleta. Faltam arquivos em
13 datas de sessão:

`2025-03-11, 2025-03-12, 2025-04-01, 2025-04-08, 2025-04-17, 2025-05-13,
2025-06-10, 2025-06-24, 2025-07-01, 2025-07-07, 2025-07-14, 2025-07-18,
2025-07-29`.

Há arquivos em 19/06 e 04/07, datas sem pregão, ambos sem capturas completas.
Em 03/07 o encerramento regular ocorreu às 13:00 de Nova York; filtrar sempre
até 16:00 seria incorreto. O calendário foi reconciliado por data nesta auditoria;
a filtragem intradiária depende da resolução do fuso e do atraso da fonte.

## Artefatos e reprodução

Resultados locais em `results/data_audit/raw_parquet_2026-10-08/`, ignorados pelo
Git. O código e este relatório técnico ficam no repositório. Artefatos principais:

- `summary.json`: contagens, hashes de todas as entradas e saídas da varredura;
- `snapshots.csv.gz`: diagnóstico de cada bloco com arquivo e posição original;
- `by_file.csv` e `by_asset.csv`: distribuição das perdas;
- `raw_examples.json`: exemplos de linhas sem reparo;
- `clock_gaps.csv` e `jump_examples.csv`: diagnósticos temporais e de preço;
- `joint_coverage.json` e `joint_coverage_by_date.csv`: cobertura causal conjunta;
- `calendar_audit.json`: reconciliação por data com a fonte oficial citada.

Ambiente usado: Python 3.11.13, pandas 2.3.1, NumPy 2.3.1 e pyarrow 24.0.0,
já instalados em um ambiente local. A auditoria é independente das dependências
de treinamento. Para reproduzir, use um ambiente com pandas/numpy e um leitor
Parquet compatível; o projeto ainda não declara o leitor Parquet no Poetry.
As saídas exigem um diretório novo:

```bash
python -m rl_boleta.audit_parquet \
  --input-dir data \
  --output-dir results/data_audit/reproduction

python -m rl_boleta.audit_coverage \
  --audit-dir results/data_audit/reproduction

python -m unittest discover -s tests -v
```

Os dois comandos reproduzem a varredura e a cobertura. A reconciliação do
calendário foi feita separadamente a partir das datas auditadas e da tabela
oficial. O teste de cobertura não pressupõe fuso nem calendário.

## Próximo passo

Implementar o adaptador Parquet → snapshots estruturados: blocos originais,
IDs inferidos rastreáveis, rejeição integral de capturas incompletas e parâmetros
temporais explícitos. Antes de gerar o dataset experimental, resolver o fuso,
aplicar calendário/horários de sessão e escolher justificadamente as tolerâncias.
A ausência do horário de mercado do livro deve continuar declarada. O resultado
será um backtest com snapshots observados, não uma reprodução de fills reais.
