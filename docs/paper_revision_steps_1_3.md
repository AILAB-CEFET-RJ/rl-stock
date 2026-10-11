# Incorporação da revisão ao paper — etapas 1–3

Executada em 08/10/2026, na branch `fix/data-pipeline-audit`.

## Versões e escopo

- Manuscrito ativo: [paper.tex](../paper/paper.tex).
- Referência anterior, sem alterações: [paper_pre_revision_2026-10-08.tex](../paper/archive/paper_pre_revision_2026-10-08.tex).
- SHA-256 da referência: `4e776eb6f30c63552ef1701d9f20a8b2e50921c25bda915cacac42a9d0aa5078`.
- Diferenças: `paper/archive/paper_revision_steps_1_3_2026-10-08.patch`.
- Parecer original: [paper_conceptual_review.md](paper_conceptual_review.md).

O manuscrito é agora um rascunho metodológico com pendências visíveis por
`\revisionpending{...}`. Não representa experimentos já executados nem está
pronto para submissão. Nenhum algoritmo foi treinado nesta etapa. A regra
existente de `.gitignore` para `/paper` foi preservada; fonte, cópia e patch
permanecem no workspace, fora do versionamento enquanto essa regra vigorar.

## Etapa 1 — alegações e resultados

O título foi ajustado para negociação intradiária com livros amostrados, sem
prometer execução de alta frequência. Resumo, contribuições e conclusões
passaram a apresentar uma pergunta de pesquisa e uma especificação proposta.
Foram retirados ganhos, significância, ranking de algoritmos, prioridade
científica e alegações de fidelidade operacional baseados nos resultados antigos.

Tabelas, figuras, contagens exploratórias e amostras antigas foram retiradas do
texto ativo. A estrutura das seções de dados, avaliação, sensibilidades e
resultados foi mantida com pendências que identificam a evidência necessária.
As configurações, folds e versões de software antigos não são apresentados
como se já correspondessem ao novo ambiente. Autores e agradecimentos foram
preservados. A declaração de disponibilidade recebeu uma pendência explícita
para revisão posterior, e a alegação de recuperar a mesma amostra histórica
coletando novamente uma página dinâmica foi removida.

## Etapa 2 — problema econômico e temporal

A especificação de referência estabelece:

- ações inteiras, posições long-only, ausência de alavancagem e caixa compartilhado;
- capital inicial positivo, carteira inicialmente sem posições e juros de caixa zero;
- ações como intenções incrementais, distintas de pesos alvo de carteira;
- três relógios separados: fonte, disponibilidade e execução;
- atraso informado de três horas, com interpretação e fusos ainda pendentes;
- nenhuma subtração automática do atraso em timestamps;
- replay idealizado distinguido de execução contemporânea no recebimento.

O livro exibido não é presumido consolidado ou representativo de toda a
liquidez americana. A identidade da bolsa selecionada historicamente permanece
pendente. O uso de um próximo snapshot para preencher ordens é hipótese do
simulador, não reconstrução de fila ou comprovação de execução real.

## Etapa 3 — observação, execução, contabilidade e recompensa

As antigas formulações repetidas e alternativas comentadas foram substituídas
por uma especificação única, com as seguintes escolhas de referência:

| Componente | Regra especificada |
|---|---|
| Observação | História causal de mercado e vetor separado de carteira/contexto atual; observabilidade parcial explicitada |
| Escala | Preços relativos a referência passada; volumes com transformação própria; carteira escalada pelo capital inicial; estatísticas ajustadas no treino |
| Ação | Zona neutra e intenção inteira dimensionada com patrimônio e midpoint observados |
| Tempo de execução | Próximo índice programado válido, sem observar esse livro ao decidir e sem saltar lacunas |
| Liquidez | Compras em asks, vendas em bids, consumo por nível e limite de participação; sem reposição por repetição do mesmo snapshot |
| Caixa | Vendas primeiro; orçamento de compra dividido proporcionalmente ao notional desejado observado; custos incluídos; sobra mantida em caixa |
| Ordens | Preenchimento parcial; restante cancelado após tentativa única |
| Custos | Taxa sobre notional; spread e caminhada no livro incorporados no fill, sem cobrança duplicada |
| Contabilidade | Identidades explícitas de caixa, posições e patrimônio; preços de execução separados de marcação |
| Recompensa | Variação líquida de patrimônio dividida pelo capital inicial, com escala fixa |
| Objetivo | Horizonte finito; `gamma=1` como referência econômica; desconto tratado como objetivo distinto |
| Encerramento | Último livro programado reservado à tentativa de liquidação; custos e posições residuais preservados |
| Risco | Piso de capital inicial distinto de variante por drawdown; saídas seguem a mesma liquidez e taxas |
| Lacunas | Truncamento detectado quando ocorre; nenhuma venda retrospectiva ou informação antecipada sobre a falha |

O parâmetro de participação não demonstra ausência de impacto; o caminho de
mercado exógeno continua uma hipótese. A disponibilidade imediata dos recursos
de vendas para compras no mesmo passo é uma convenção declarada do modelo,
sem simular regras de liquidação financeira de uma corretora.

Não se garante zeragem a qualquer custo: liquidação insuficiente gera posição
residual e falha da restrição terminal, que deve permanecer nos relatórios.
Episódios selecionados retrospectivamente por completude só podem sustentar
conclusões condicionais à disponibilidade desses dados, com horizonte fixo
conhecido no início. Segmentos de cobertura não são fornecidos à política.

Os símbolos também foram separados: `omega` identifica parâmetros da política;
`theta` identifica capital inicial; `T` é o horizonte programado e `T_e` o
encerramento econômico efetivo. Uma interrupção de dados não equivale a uma
liquidação econômica concluída.

## Rastreabilidade dos 16 achados

| Achado | Incorporação nesta etapa | Trabalho restante |
|---|---|---|
| 1 — atraso/relógios | Três relógios, atraso de três horas e pendências explícitas | Confirmar semântica histórica e regime de execução suportado |
| 2 — execução | Kernel, fills, custos, parcialidade e capacidade por snapshot especificados | Implementar e validar em dados sintéticos |
| 3 — bolsa/consolidação | Limitação de venue explicitada | Confirmar identificação da bolsa; etapa 4 |
| 4 — unidade de observação | Contagens e amostras antigas retiradas; unidades distintas exigidas | Inserir contagens e exemplos novos; etapa 4 |
| 5 — autofinanciamento | Restrições, orçamento conjunto e lotes inteiros especificados | Testar invariantes de caixa e posição |
| 6 — recompensa local | Expressão excluída como recompensa financeira | Verificar ganhos de posições mantidas no simulador |
| 7 — PnL/desconto | Objetivo principal e distinções econômicas explícitos | Fixar variantes na validação; etapa 5 |
| 8 — normalização | Regras causais e escalas por unidade especificadas | Implementar transformações e ajuste restrito ao treino |
| 9 — Markov | Estado interno separado de observação parcial | Definir encoder e dimensões finais |
| 10 — episódios | Horizonte conhecido, liquidação e truncamento diferenciados | Finalizar amostragem; implementar eventos terminais |
| 11 — stop | Piso inicial separado de drawdown por pico | Fixar parâmetros e validar saídas |
| 12 — seleção temporal | Fold antigo retirado; seleção interna exigida | Definir protocolo completo; etapa 5 |
| 13 — comparação/inferência | Números antigos retirados; requisitos de comparação registrados | Baselines, agregação e inferência; etapa 5 |
| 14 — ablação | Observação separada de dados de execução | Implementar máscaras e novo protocolo |
| 15 — algoritmos | Comparação e configuração antigas retiradas | Verificar classes, checkpoints e manifestos por algoritmo |
| 16 — excesso de conclusões | Superioridade, significância e realismo não demonstrados retirados | Rever literatura, termos de dados e conclusões após novos resultados |

## Verificação realizada

- A referência foi conferida por SHA-256; nenhuma tabela antiga foi reaproveitada.
- Labels, referências internas e aninhamento de ambientes LaTeX foram conferidos.
- As equações contábeis e a interpretação de soma de recompensas foram revisadas;
  isso não substitui testes do futuro simulador.
- O corpo foi compilado duas vezes com um preâmbulo diagnóstico `article`, para
  verificar comandos, equações, tabela e resolução das referências internas.
  Esse PDF temporário não valida o layout Springer nem o front matter.
- Na primeira verificação, a compilação integral parou por ausência de `sn-jnl.cls`. O diretório também
  não contém `sn-bibliography.bib`; há citações sem resolução no diagnóstico.
  O preâmbulo integral requer ainda pacotes ausentes na instalação TeX local
  (a tentativa com o preâmbulo original identificou `multirow.sty` ausente).
- A bibliografia e a revisão das alegações sobre trabalhos relacionados
  continuam pendentes.

Próximas etapas: completar documentação de dados e desenho experimental,
implementar e testar o núcleo econômico especificado, resolver o uso temporal
dos dados reais, executar os experimentos e substituir os marcadores por
evidência efetivamente obtida.

## Compilação integral após inclusão do template e da bibliografia

Em 08/10/2026, após o autor adicionar `sn-jnl.cls` e `sn-bibliography.bib`,
o manuscrito foi compilado integralmente com pdfLaTeX e BibTeX. O resultado
está em `paper/paper.pdf`, com 19 páginas e 38 referências, sem citações ou
referências internas indefinidas e sem caixas `Overfull`. Persistem avisos de
substituição de tamanhos de fonte e caixas `Underfull`; a primeira página foi
inspecionada visualmente. Isso valida a compilação, não a revisão científica
da bibliografia ou a conformidade final com as instruções específicas da revista.

Foram feitos os seguintes ajustes:

- Inclusão da opção `pdflatex` na classe e remoção da margem personalizada,
  preservando a geometria definida pelo template.
- Substituição dos nomes de estilos de teorema não definidos pelos estilos
  padrão de `amsthm`.
- Inclusão de `sn-mathphys-num.bst`, extraído sem modificações do
  [pacote oficial Springer](https://www.springernature.com/gp/authors/campaigns/latex-author-support)
  de dezembro de 2024. A classe fornecida pelo autor foi preservada.
- Inclusão da referência [PPO de Schulman et al. (2017)](https://arxiv.org/abs/1707.06347)
  com chave `SchulmanPPO2017`. A chave preexistente `schulman2017` corresponde
  a TRPO; como BibTeX não distingue maiúsculas de minúsculas nas chaves,
  apenas mudar a capitalização não permitiria cadastrar PPO separadamente.

As dependências ausentes no TeX Live Basic foram instaladas somente em
`/private/tmp/rl-stock-texmf`: `sttools`, `multirow`, `appendix`, `algorithms`,
`algorithmicx`, `circuitikz`, `threeparttable`, `wrapfig`, `ncctools` e `rsfs`.
Nenhuma instalação global foi alterada. Para repetir a compilação nesta sessão:

```sh
cd paper
export TEXMFHOME=/private/tmp/rl-stock-texmf
export TEXMFVAR=/private/tmp/rl-stock-paper-build/texmf-var
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=/private/tmp/rl-stock-paper-build paper.tex
```

Executar BibTeX a partir do diretório de saída:

```sh
cd /private/tmp/rl-stock-paper-build
BIBINPUTS=/Users/ebezerra/ailab/rl-stock/paper: BSTINPUTS=/Users/ebezerra/ailab/rl-stock/paper: bibtex paper
```

Repetir pdfLaTeX duas vezes a partir de `paper`. Em uma instalação TeX completa,
a sequência usual `pdflatex paper`, `bibtex paper`, `pdflatex paper`,
`pdflatex paper` pode ser executada diretamente nessa pasta. Os pacotes
temporários não são parte do repositório e precisarão ser reinstalados caso
esse diretório temporário seja removido.
