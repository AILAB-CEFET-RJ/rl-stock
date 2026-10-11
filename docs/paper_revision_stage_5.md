# Revisão do paper — etapa 5: protocolo experimental

**Histórico da versão 1, substituído pela [revisão por pregão](protocol_day_trading_revision.md)
e pelo [protocolo v2](../configs/experimental_protocol_v2.json).** As escolhas de
blocos abaixo não são o desenho principal vigente.

Especificação proposta em 08/10/2026, na branch `fix/data-pipeline-audit`.

O protocolo foi incorporado à seção **Agent Training and Evaluation** do
[manuscrito](../paper/paper.tex). A especificação estruturada está em
[configs/experimental_protocol_v1.json](../configs/experimental_protocol_v1.json).
Esse JSON é um contrato para a futura implementação, não uma configuração
executável pelo treinador legado. Nenhum treinamento foi executado nesta etapa.

## Divisão temporal

| Uso | Datas de 2025 | Sessões previstas | Mínimo de sessões com blocos elegíveis |
|---|---|---:|---:|
| Treino para seleção | 03/03–30/05 | 63 | 20 |
| Validação e escolha | 02/06–30/06 | 20 | 10 |
| Teste protegido | 01/07–31/07 | 22 | 10 |
| Reajuste final após escolha | 03/03–30/06 | 83 | Universo de desenvolvimento |

As fronteiras são comuns aos 18 ativos. Faltas não deslocam as datas, e janelas,
normalizadores e replay buffers não atravessam as fronteiras de seleção.
Após selecionar hiperparâmetros em junho, cada modelo é treinado do zero em
março–junho, com normalizador reajustado nesse período, antes de avaliar julho.
Nenhuma escolha usa retorno ou desempenho de julho. A auditoria de qualidade
já examinou julho; não se alega que seus dados brutos jamais foram vistos.

## Ambiente e episódios de referência

| Parâmetro | Proposta v1 |
|---|---|
| Capital e ativos | US$ 100.000, 18 ativos, long-only, caixa compartilhado |
| Observação e grade | 20 vetores de mercado, intervalos de 60 segundos |
| Recompensa | Variação líquida de patrimônio/capital inicial, escala 1, gamma 1 |
| Ação | Zona neutra 0,05; execução inteira no próximo ponto |
| Taxa por lado | 1 ponto-base sobre notional executado |
| Participação | 10% da quantidade exibida por nível |
| Stop | Piso de 80% do capital inicial; sem stop por pico de patrimônio |
| Dados | Idade máxima de recebimento 60 s; spread e distância até 500 bps |
| Horizonte medido | 60 transições, incluindo liquidação reservada |

São hipóteses controladas para comparação, não parâmetros economicamente
ótimos, custos de corretora identificados ou capacidade real comprovada.
A idade de 60 s limita o reaproveitamento a um intervalo da grade; os 500 bps
mantêm o screen exploratório explicitamente registrado, sem afirmar que ofertas
mais distantes são erros. Os limites precisam passar pela verificação de
viabilidade, e qualquer revisão deve ser versionada antes da seleção por retorno.

Cada bloco tem 81 pontos brutos. Índice 0 fornece a referência de preço passado;
índices 1–20 formam a primeira janela. A carteira inicia no índice 20.
Intenções nos índices 20–78 executam em 21–79; índice 80 é reservado à tentativa
de liquidação, sem nova intenção no índice 79. Há 60 transições de patrimônio
entre 20 e 80, incluindo a liquidação. Stops podem abreviar o episódio.

Os inícios são abertura + 81*b minutos. Blocos não se sobrepõem, não atravessam
sessões e exigem todos os pontos válidos para os 18 ativos. Os tetos puramente
calendáricos são 252 blocos de treino, 80 de validação e 86 de teste. Não são
contagens de episódios disponíveis: essas ainda dependem do dataset final.
Seleção retrospectiva por completude condiciona as conclusões à disponibilidade
dos dados; não representa operação contínua durante todo o pregão.

Se os mínimos de sessões elegíveis falharem, registrar inviabilidade e revisar
o protocolo antes da avaliação financeira. Não aumentar tolerâncias nem
encurtar janelas silenciosamente para melhorar o teste. Uma verificação apenas
no treino deve confirmar que capital, lotes e profundidade permitem fills.

## Comparações e orçamento proposto

- Principal: PPO, A2C, SAC e DDPG, com observação completa e gamma 1.
- Busca: taxas de aprendizado 0,0001 e 0,0003; duas camadas de largura 64 ou
  128; quatro candidatos por algoritmo. Adam, ReLU e regras por algoritmo
  estão especificados no paper e no JSON.
- Seleção: 500.000 transições por candidato e sementes 0, 1, 2. Maximizar o
  retorno marcado líquido médio por sessão de validação e por semente.
  Desempatar por menor drawdown, menor largura e menor taxa de aprendizado.
- Ajuste final: 1.000.000 de transições por modelo selecionado, sementes
  100–109. Avaliação determinística, checkpoint no orçamento fixo e sem
  selecionar a melhor semente. Normalizadores congelados durante julho.
- Desconto: PPO com gamma 0,95 e 0,99, contra referência 1, com busca e
  reajuste próprios sob o mesmo orçamento.
- Ablações: PPO sem negócios recentes; sem níveis 2–5 do livro; sem quantidades
  do livro. Remover apenas entradas da política, preservando dados de execução
  e marcação. Repetir busca e treinamento; registrar dimensões e máscaras.
- Estresses sem retreino: taxas de 0 e 5 bps ou participações de 5% e 25%,
  alterando um fator por vez, contra a referência de 1 bp e 10%.
- Idades 90/120 s: diagnóstico de cobertura; não selecionar amostras pelo
  lucro de julho. Transferência e estudo de um ativo ficam para protocolo
  secundário separado, com interfaces compatíveis e fronteiras temporais.

O plano completo corresponde a **198 ajustes**: 108 de seleção e 90 finais,
solicitando 144 milhões de transições no total, antes de arredondamentos de
rollout. Esse é o planejamento de carga; nenhum ajuste foi executado nesta etapa. Antes de começar, validar o treinador e estimar custo
com dados sintéticos. Ajustes de orçamento devem anteceder a seleção por retorno
e aplicar-se a toda a comparação afetada. Igual orçamento de transições não
implica igual quantidade de atualizações ou tempo; ambos serão registrados.

Amostragem de treino: sessão elegível uniforme, depois bloco uniforme dentro
dela, com reposição. PPO pode completar seu último rollout, com excesso máximo
de um rollout menos uma transição; solicitado e realizado serão reportados.
Candidatos com sementes incompletas não recebem busca adicional nem substituição
silenciosa: falhas permanecem no relatório.

## Baselines e métricas

Baselines: caixa; entrada única com intenções de compra iguais seguida de
hold/liquidação; momentum de dez intervalos; reversão desse sinal; ações
aleatórias uniformes, sementes 100–109. Todos usam o mesmo kernel, capital,
restrições, atrasos, custos, calendário e blocos. A entrada igualmente
orçada pode gerar pesos realizados diferentes devido a lotes e fills parciais.

O contraste principal é **PPO menos a baseline de entrada única**, com médias
por bloco dentro da sessão, por sessão e por semente. Outros contrastes são
secundários. O retorno é (patrimônio terminal − capital inicial)/capital inicial,
após tentativas de saída. Posições residuais mantêm retorno marcado e recebem
flag de falha de zeragem; não são apagadas para melhorar o agregado.

Reportar também drawdown máximo, giro, taxas, fills, cancelamentos, ordens
inviáveis, resíduos, stops, truncamentos, falhas de execução e cobertura.
Blocos resetam capital e carteira; suas médias não são retornos compostos de
uma carteira contínua. Não anualizar Sharpe ou ganhos compostos dessa amostra.
Falhas irrecuperáveis produzem resultados ausentes explícitos; comparações
pareadas divulgam qualquer redução da amostra e não sustentam superioridade
quando há falhas não resolvidas.

## Limites da inferência

Sessões são as unidades de mercado; sementes, ativos, negócios e blocos não
são réplicas independentes de mercado. O protocolo exige pelo menos 20 sessões
pareadas para apresentar os intervalos bootstrap descritos no paper: 10.000
réplicas, blocos circulares de cinco sessões programadas, flags de ausência
preservadas e reamostragem de sementes como trajetórias inteiras. Esse limiar
é operacional, não prova de poder estatístico; intervalos seriam descritivos.

O acervo atual tem arquivos em **no máximo 17 sessões de julho**, pois cinco
sessões não têm arquivo. Portanto, com este acervo o teste será descritivo:
diferenças pareadas por sessão e distribuição entre sementes, sem alegação de
significância. Não tratar sementes como aumento do número de pregões. Resultados
secundários não sustentam superioridade por intervalos nominais sem controle
de multiplicidade. Qualquer extensão futura deve ser especificada antes de
inspecionar os resultados do novo período.

## Validação e pendências

Foram conferidos pelo calendário implementado os totais 63/20/22 e 83 sessões,
os tetos 252/80/86 de blocos e os índices de janela, decisão, fill e liquidação.
Também foram conciliados os orçamentos do JSON, as chaves bibliográficas e as
referências internas do manuscrito. A compilação integral pdfLaTeX/BibTeX gerou
27 páginas e 42 referências, sem citações indefinidas ou excesso horizontal.
Persistem avisos de fonte/Underfull e um excesso vertical de aproximadamente
4 pontos, já existente antes desta etapa.

Foram adicionadas referências primárias sobre
[incerteza na avaliação de RL](https://arxiv.org/abs/2108.13264) e
[seleção repetida em backtests](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).
Esses trabalhos motivam precauções gerais; os limiares e orçamentos propostos
são escolhas deste projeto, não prescrições dessas referências.

Versão anterior: `paper/archive/paper_pre_stage_5_2026-10-08.tex`.
Patch: `paper/archive/paper_revision_stage_5_2026-10-08.patch`.
A regra existente que ignora `/paper` foi mantida. O protocolo JSON e este
registro ficam disponíveis para versionamento, independentemente dessa regra.

Próximo trabalho concreto: implementar o núcleo econômico com livros sintéticos
e verificar caixa/posições, fills, consumo de profundidade, custos, recompensa,
liquidação e truncamento. Em seguida, integrar a elegibilidade e os manifestos
ao protocolo. Os relógios e a viabilidade do histórico continuam pendências
para experimentos finais; não impedem a validação sintética do simulador.
