# Revisão do paper — etapa 4: dados

> Registro **004** · Data de referência: **2026-10-08** · [Índice](README.md)
> Anterior: [Registro 003](003_paper_revision_steps_1_3.md) · Seguinte: [Registro 005](005_paper_revision_stage_5.md)

Incorporada em 08/10/2026, na branch `fix/data-pipeline-audit`.

O [manuscrito](../paper/paper.tex) agora descreve o acervo bruto, a reconstrução
por blocos originais, o universo de 18 ativos, a validade estrutural, o calendário
e o alinhamento causal. A análise exploratória contém contagens auditadas e
resultados dos pilotos de preparação, sem reaproveitar resultados de negociação
ou CSVs da dissertação. O [PDF](../paper/paper.pdf) foi atualizado.

## Contagens e unidades

| Escopo | Linhas brutas | Capturas candidatas | Capturas completas |
|---|---:|---:|---:|
| Acervo integral, todos os ativos coletados | 25.142.620 | 2.514.262 | 2.372.496 |
| Período do paper, 19 ativos coletados | 8.211.040 | 821.104 | 759.408 |
| Período do paper, universo de 18 ativos | 7.778.880 | 777.888 | 723.003 |

No período de 03/03–31/07/2025, cada ativo tem 432.160 linhas, equivalentes a
43.216 capturas. GE foi excluída para manter o universo especificado no paper.
As 723.003 capturas completas dos 18 ativos representam 92,94% das candidatas,
antes de interpretar os fusos, aplicar sessões ou limites adicionais de preço.
As 54.885 perdas incluem 53.055 falhas numéricas de livro e 6.296 falhas numéricas
de negócios; as categorias se sobrepõem.

O texto distingue linhas, capturas, pontos de grade, sessões, segmentos e
episódios. Em particular, um segmento de K pontos a intervalos de um minuto tem
K−1 minutos entre o primeiro e o último ponto. Não foi calculada uma quantidade
final de episódios elegíveis para treinamento.

## Cobertura e regras incorporadas

- Universo explícito: AAPL, TSLA, MSFT, CSCO, F, C, FCX, BAC, KO, INTC, GM,
  AAL, NCLH, JPM, PFE, MS, DAL e NEM. É uma amostra de conveniência, sem
  alegação de representatividade do mercado americano.
- Esquema de nove colunas, com data da máquina de coleta distinguida do horário
  dos negócios e ausência de timestamp próprio do livro/identificador da bolsa.
- Reconstrução de dez linhas consecutivas antes de ordenar ou filtrar,
  cinco asks e cinco bids, com IDs inferidos do hash e da posição original.
- Rejeição integral de capturas incompletas, sem imputação ou reparo de preços;
  deduplicação por identidade da captura, não por repetição de valores de mercado.
- Seleção causal da captura passada mais recente por ativo, com idade máxima
  explícita e sem transportar dados entre sessões.
- Grade completa dos pregões esperados, inclusive datas sem arquivo, com
  intervalo semiaberto entre abertura e fechamento.
- Calendário regular com 105 sessões e 40.770 pontos de um minuto; 92 sessões
  têm arquivo, 13 não têm. Duas datas com arquivos são feriados de bolsa.
- Diagnóstico sem fuso: denominador de 42.074 pontos entre primeira e última
  captura de cada data observada. Não é cobertura dos pregões esperados.
- Piloto de 02–04/07: denominador de 600 pontos, com 424, 458 e 468 pontos
  retidos para idades máximas de 60, 90 e 120 segundos. Os maiores segmentos
  têm respectivamente 29, 80 e 262 pontos, não essas durações em minutos.

As fontes oficiais de calendário foram conferidas e incluídas no `.bib`:
[NYSE/ICE](https://ir.theice.com/press/news-details/2024/NYSE-Group-Announces-2025-2026-and-2027-Holiday-and-Early-Closings-Calendar/default.aspx)
e [Nasdaq](https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2025-37).
A grade termina antes do fechamento e não representa o leilão de encerramento;
a observação reservada à liquidação deverá respeitar essa convenção.

## Evidência e verificação

Foram usados os seguintes artefatos existentes, sem modificá-los:

- `results/data_audit/raw_parquet_2026-10-08/summary.json`, `by_asset.csv`,
  `by_file.csv`, `joint_coverage.json` e `calendar_audit.json`;
- manifestos e `segments.csv` de
  `results/data_adapter/calendar_pilot_2026-10-08`,
  `calendar_pilot_2026-10-08_age90` e `calendar_pilot_2026-10-08_age120`;
- manifesto de `results/data_adapter/calendar_input_2026-10-08`.

Os agregados de 18 ativos foram recalculados de `by_asset.csv`; os totais dos
19 ativos foram conciliados com `summary.json`. Os hashes SHA-256 de
`by_asset.csv` e `by_file.csv` foram conferidos com o manifesto da auditoria.
Os pontos, quantidades e maiores tamanhos dos segmentos dos três pilotos foram
recalculados e conciliados com seus manifestos, incluindo o hash de cada
`segments.csv`. Não foi necessário repetir a leitura dos Parquet nem executar
novos pilotos para esta edição.

A compilação pdfLaTeX/BibTeX foi concluída com 23 páginas e 40 referências,
sem citações ou referências internas indefinidas. As duas novas tabelas foram
inspecionadas visualmente. Não há caixas horizontais excedendo a largura;
restam avisos de fontes, caixas Underfull e um excesso vertical de cerca de
4 pontos na página 7. As dependências e comandos de compilação estão no
[registro das etapas 1–3](003_paper_revision_steps_1_3.md).

Cópia anterior a esta etapa:
`paper/archive/paper_pre_stage_4_2026-10-08.tex`.
Patch da etapa: `paper/archive/paper_revision_stage_4_2026-10-08.patch`.
O `.gitignore` existente para `/paper` foi preservado; esses arquivos e o PDF
permanecem locais enquanto essa regra vigorar.

## Pendências delimitadas

A documentação dos resultados já verificados foi incorporada. O dataset final
continua pendente: fusos de coleta e negócios, interpretação do atraso informado
de três horas e bolsa histórica selecionada não estão confirmados. Os livros
não recebem timestamp de fonte inventado por subtração automática do atraso.

Os limites de preço e idade usados nos pilotos não foram promovidos a escolhas
finais. A seleção deverá ser justificada e congelada sem consultar desempenho
no teste externo. Cobertura intradiária do período completo com calendário,
perdas por ativo/sessão, distribuições de spread/profundidade, reconciliação de
saltos de preço e elegibilidade de episódios deverão ser reportadas para o
dataset experimental definitivo.

A próxima etapa do plano é definir o protocolo experimental antes do
treinamento (etapa 5), em paralelo às decisões temporais necessárias para os
dados reais. A implementação e validação do simulador continuam necessárias.
