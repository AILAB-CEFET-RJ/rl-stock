# Executor de seleção por validação v3

> Registro **027** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 026](026_historical_training_integration.md) · Seguinte: [Registro 028](028_day_trading_admissibility_review.md)

O executor `rl_boleta.validation_selection` implementa a seleção dos quatro
algoritmos principais nos dois cenários. Usa os normalizadores de treino já
congelados e as datas de validação próprias de cada cenário: 15 em `all_gaps`
e 14 em `short_gaps`. Não admite datas de julho. As variantes de desconto e
observação de PPO continuam como etapa separada, não implementada neste executor.

## Critério, denominadores e comparação

**Emenda de 12/10/2026:** a [revisão de day trading](028_day_trading_admissibility_review.md)
separa integridade do candidato e cumprimento do encerramento em caixa.
O modo completo agora exige inventário zero e retorno realizado em todas as
datas/sementes de validação e recusa protocolos sem a revisão implementada e
verificada. Nenhum protocolo antigo foi reescrito. O critério marcado descrito
abaixo permanece como histórico do diagnóstico; o novo critério completo
maximiza retorno realizado entre candidatos que cumprem a restrição.

Para cada candidato, a média dá o mesmo peso às sessões e às três sementes
0–2. Exige todas as sementes e todas as datas comuns do cenário, na ordem
congelada. Falha de ajuste, data ausente, score não finito ou semente duplicada
impede a candidatura; não se substitui por zero nem por um subconjunto favorável.
Configurações com sementes incompletas são ineligíveis, sem busca de reposição.

Episódios com posições restantes continuam nos resultados com score marcado,
retorno realizado ausente e falha de liquidação explícita. A seleção respeita
o critério registrado: maior média do patrimônio terminal marcado relativo
ao capital inicial; em empate, menor drawdown marcado médio, menor largura e
menor taxa de aprendizado. Não se adicionou um filtro de sucesso em caixa ou
uma penalização de resíduos depois de observar os resultados.

Essa regra mede score marcado, que pode incluir posições não liquidadas.
Por isso cada candidato reporta também encerramento em caixa, falhas de
liquidação, exposição residual, taxas, turnover, drawdown observado e idade
máxima de captura apoiando posições. Marcas durante lacunas não certificam
risco intralacuna. Essas métricas acompanham o ranking; não se confundem
com retornos inteiramente realizados.

Os baselines usam os mesmos livros, capital, taxas, participação, relógio e
saída. Executam-se caixa, entrada igualitária, momentum, reversão e dez
trajetórias aleatórias com sementes 100–109. Cada semente aleatória conserva
seu fluxo nas datas cronológicas de validação do próprio cenário.

São gravadas diferenças pareadas por sessão/semente frente à entrada igualitária,
com indicadores de encerramento em caixa de ambos os métodos. Sementes não
viram unidades adicionais de mercado: os denominadores continuam 15/14 sessões.
Não se produzem p-valores ou intervalos confirmatórios nesta etapa.

## Modos e orçamento

**`diagnostic`:** duas configurações extremas da grade — largura 64 com taxa
0,0001 e largura 128 com taxa 0,0003 — três sementes e 384 transições por
ajuste. O orçamento aceito é 368–4.096 passos e usa os ajustes reduzidos de
smoke. Por padrão, o diagnóstico executa PPO nos dois cenários: 12 ajustes,
4.608 transições solicitadas, todas as datas de validação e todos os baselines.

A saída é `diagnostic_ranking.json`, com `eligible_for_final_refit=False`.
Esse ranking comprova o encadeamento do processo; não escolhe a configuração
para o paper nem autoriza o normalizador/reajuste final. Não usa as duas
configurações restantes da grade ou os orçamentos completos.

**`protocol`:** quatro configurações (larguras 64/128 × taxas 0,0001/0,0003),
três sementes e 500.000 transições por ajuste. O orçamento não aceita override.
Com quatro algoritmos e dois cenários, são 96 ajustes e 48 milhões de
transições solicitadas, mais o pequeno excesso permitido para fechar rollouts.
Esse é o componente de seleção dos algoritmos principais dentro do planejamento
de 286 ajustes/208 milhões de transições; variantes e ajustes finais não fazem
parte desses 96. Pode-se executar um algoritmo/cenário separadamente.

No modo completo, `selected_configurations.json` registra a escolha entre
candidatos admissíveis de cada algoritmo/cenário, com escopo explícito.
Se faltar escolha para algum grupo, a execução fica `selection_incomplete`
e não libera o reajuste. Falhas de candidatos são reportadas e não são
retentadas automaticamente. Nenhuma seleção protocolar foi executada nesta etapa.

## Execução diagnóstica e continuação

```sh
caffeinate -i env \
  PYTHONPATH=/private/tmp/rl-stock-training-deps \
  MPLCONFIGDIR=/private/tmp/rl-stock-matplotlib \
  /Users/ebezerra/miniconda3/envs/ailab/bin/python \
  -m rl_boleta.validation_selection \
  --normalizer-dir results/v3_historical_train_normalizers_2026-10-12 \
  --mode diagnostic --algorithm PPO --scenario ALL \
  --output results/v3_validation_selection_diagnostic_verified_2026-10-12
```

A saída deve ser nova. `--resume` permite continuar uma execução com o mesmo
plano, código e hashes de entrada. Relatórios e baselines já comprometidos no
manifesto são conferidos; checkpoints treinados aguardando validação podem
continuar nessa fase. Um diretório parcial de ajuste sem relatório não é
reutilizado silenciosamente: preserve-o e inicie outra execução.

O plano registra cada configuração/semente/cenário, o orçamento, os hashes e
uma estimativa dos arrays de replay. SAC/DDPG completos, com buffer de 100.000
transições e 15.502 entradas, requerem **12,41 GB somente para esses arrays**,
além de modelos, dados e demais estruturas. O executor treina um modelo por
vez. Essa exigência deve ser considerada ao preparar a execução completa;
não se reduziu o buffer registrado para contorná-la.

## Cache e avaliação em conjunto

As janelas de mercado são independentes da carteira e podem ser transformadas
uma vez por sessão. `CachedMaskedEncoder` calcula as linhas normalizadas
causalmente, conserva somente os pontos passados da janela quando monta a
entrada e atualiza o contexto de caixa/posições a cada decisão. Verifica que
frames, disponibilidade e marcas coincidem com a observação recebida.
As linhas guardadas são arrays float32 somente para leitura.

Na validação, todos os checkpoints de um algoritmo/cenário percorrem cada
sessão antes de carregar a próxima. Isso evita reler os dados e reconstruir
as mesmas features para cada semente. O cache de sessões do treinamento
continua limitado a duas datas.

Checkpoints off-policy recarregados para previsão usam um buffer não utilizado
de um slot; os pesos e hiperparâmetros do treino permanecem registrados no
checkpoint e no relatório. Não se aprende durante a validação. A previsão
após recarregar é comparada à original, e os normalizadores permanecem congelados.
As versões de ambiente/dependências também constam de `system_info.txt` dentro
dos checkpoints SB3, além dos hashes do plano e dos artefatos.

## Verificação desta etapa

A execução final terminou com 12 ajustes PPO, zero falhas de ajuste e
174 outcomes de modelo na validação: seis checkpoints × 15 datas e seis ×
14 datas. Há quatro candidatos agregados (dois por cenário), cada um com
três sementes completas. Foram calculados 406 outcomes de baselines:
14 trajetórias × 15 datas e 14 × 14. Esses números são execuções repetidas,
não novas sessões independentes de mercado. Julho não foi acessado.

Os candidatos diagnósticos apresentaram encerramento em caixa entre 2,22% e
19,05% dos outcomes por semente/sessão. A entrada igualitária terminou em caixa
em 13/15 e 12/14 datas. Os agentes têm apenas 384 passos de aprendizado e esses
números não estimam o desempenho de modelos treinados com o orçamento completo.
Ainda assim, mostram por que o ranking por patrimônio marcado deve acompanhar
os resíduos e a viabilidade de encerramento intradiário.

O artefato final é
`results/v3_validation_selection_diagnostic_verified_2026-10-12/`.
Status: `diagnostic_selection_completed`; autorização de reajuste final: falsa.
Os hashes de código, dados, checkpoints, relatórios e diferenças pareadas foram
conferidos. A primeira execução, no diretório sem `verified`, foi interrompida
para eliminar a reconstrução repetida de janelas e fica preservada como parcial.

O cache foi comparado ao encoder original em todos os passos de um pregão
sintético com lacunas longas e no terminal, produzindo inputs float32 idênticos.
Alterar preços futuros não alterou entradas passadas. Um checkpoint histórico
PPO produzido antes da otimização ficou com pesos exatamente iguais após repetir
o mesmo treino com cache. Uma previsão SAC também ficou idêntica após usar o
buffer de um slot no carregamento para inferência, em uma observação de validação.

## Próximo passo

Concluir a revisão de recursos e do papel das falhas de liquidação na
admissibilidade dos modelos, antes de executar a seleção com orçamento protocolar,
acompanhando métricas financeiras e falhas de liquidação frente aos baselines.
Depois implementar as variantes restantes, a normalização/reajuste final
condicionados às escolhas válidas e a avaliação final em julho. O diagnóstico
atual não substitui nenhum desses resultados de pesquisa.

A regressão completa final passou: **222 testes, sem falhas ou testes pulados**.
Os oito testes do seletor cobrem pesos/denominadores, falhas e valores não
finitos, desempates, diferenças pareadas, planos/budgets, métricas econômicas,
bloqueio de julho e retomada sem repetir ajustes ou aceitar baselines alterados.
Os dois testes de cache cobrem equivalência em todos os passos e causalidade
frente a mudanças futuras.
