# Fase de encerramento com vendas sucessivas

> Registro **030** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 029](029_exit_capacity_audit.md) · Seguinte: [Registro 031](031_terminal_cash_utility.md)

Implementação de 12/10/2026 da [proposta baseada no treino](029_exit_capacity_audit.md).
O núcleo v3 aceita `wind_down_points=54` no controlador e no adaptador sintético
Gymnasium. A fase bloqueia decisões discricionárias e tenta vender o inventário
restante a cada próximo ponto, preservando um único episódio por pregão.

## Fronteiras e contabilidade

Com 54 pontos, as execuções automáticas começam às 15:06 e terminam às 15:59
no pregão normal. A última intenção discricionária é às 15:04, executada às
15:05. No pregão reduzido, os horários correspondentes são 12:06, 12:59,
12:04 e 12:05. A fronteira usa calendário e número fixo de pontos; não examina
futuros livros para decidir quando encerrar.

Cada tentativa solicita venda de todas as ações restantes. Quantidades não
executadas permanecem na carteira e são solicitadas novamente no próximo
ponto, sem transformar uma ordem anterior em execução tardia. Ordens
ordinárias não atravessam a fronteira: a última delas executa antes da fase.
Não há compras durante a fase.

As vendas percorrem os níveis de bid com taxas e limites originais. Ausência
ou expiração de livro impede aquela venda, sem impedir vendas nos outros
ativos. Reutilizar uma captura não repõe capacidade já consumida. A fase
aparece como `wind_down` no tipo de execução e motivo de transição;
o ponto final conserva `liquidation` e os status econômicos anteriores.

Se a carteira ficar em caixa antes do fim, o episódio continua em caixa até
a saída programada; o agente não reabre posições. Stops anteriores mantêm
precedência e podem terminar o episódio quando ficam em caixa. Resíduos
no ponto final são `liquidation_failure`, enquanto dados faltantes nesse ponto
são `exit_data_missing`, com truncamento e inventário preservado.

O início causal não muda nem usa cobertura futura. Se a primeira próxima
execução já pertence à fase de saída, o episódio permanece em caixa e a
política não é chamada pelo replay. A data permanece nos resultados. Na API
Gymnasium, propostas de ação continuam sendo recebidas, mas são ignoradas
nessas transições automáticas, com o indicador existente no `info`.

A recompensa continua sendo variação líquida do patrimônio marcado, incluindo
custos de cada tentativa executada. A soma telescopa até o patrimônio final;
não foram adicionadas penalidades de aprendizado nem receitas de vendas
fictícias. A restrição terminal no objetivo de aprendizagem ainda é pendência.

Atualização: o [substituto de aprendizagem de utilidade terminal em caixa](031_terminal_cash_utility.md)
foi implementado com ativação explícita. Ele não garante a restrição terminal;
o filtro de admissibilidade continua necessário. Os smokes descritos abaixo
usaram o objetivo marcado anterior e permanecem preservados como tal.

## Integração sem reinterpretar artefatos anteriores

O valor padrão da API permanece um ponto, permitindo reproduzir a regra
anterior. Uma chamada nova deve declarar 54 explicitamente. Não executar
experimentos de pesquisa confiando no padrão.

`HistoricalTrainingEnv` lê `episode.wind_down_execution_points` do protocolo
imutável vinculado ao normalizador. Se o campo estiver ausente em um protocolo
antigo, mantém um ponto. O mesmo conjunto de opções chega ao treino e à
validação de agentes e baselines. Não existe override histórico que troque a
regra apenas na avaliação. A proposta no JSON de trabalho ainda não altera
os protocolos copiados em resultados antigos.

A ativação histórica exigirá novos manifestos ligados à emenda. Estatísticas
normalizadas de mercado não mudam conceitualmente apenas pela fase, mas seu
vínculo com protocolo/datas precisa ser conferido e registrado. Não editar
protocolos ou normalizadores antigos para fingir que já usavam essa regra.
O modo completo continua bloqueado pela revisão de aprendizagem e conta.

## Verificação

A regressão completa passou com **236 testes**, sem falhas ou testes pulados.
O smoke de PPO, A2C, SAC e DDPG terminou com pesos do ator atualizados e
finitos, previsões idênticas após recarregar checkpoints e normalizadores
inalterados. Foram solicitados 384 passos por algoritmo (A2C realizou 385
para completar seu rollout). As 12 avaliações nas três datas sintéticas
terminaram em caixa. Isso verifica integração, não desempenho histórico ou
garantia de liquidação em dados reais. Hashes de código e artefatos conferidos.

Artefato: `results/v3_wind_down_synthetic_smoke_2026-10-12/suite_report.json`.

Os testes específicos cobrem vendas parciais sucessivas com taxas, soma das
recompensas, carteira flat mantida até o fim, captura reutilizada, lacunas,
resíduos, saída sem dados, horários normais/reduzidos, fronteiras causais,
início tardio em caixa, stop e compatibilidade com o padrão anterior.

O comando abaixo executa somente a integração sintética dos quatro algoritmos,
com a fase explícita no treino e na avaliação congelada. Registra o parâmetro
no relatório e confere pesos atualizados/finitos, checkpoints e terminais:

```sh
caffeinate -i env \
  PYTHONPATH=/private/tmp/rl-stock-training-deps \
  MPLCONFIGDIR=/private/tmp/rl-stock-matplotlib \
  /Users/ebezerra/miniconda3/envs/ailab/bin/python \
  -m rl_boleta.masked_training --synthetic-smoke --algorithm ALL \
  --steps 384 --wind-down-points 54 \
  --output results/v3_wind_down_synthetic_smoke_nova_execucao
```

Próximo passo: tornar explícita a restrição de inventário no aprendizado e
definir o regime de conta/buying power. Depois gerar os vínculos históricos
novos e verificar a regra em treino antes dos orçamentos completos. Nenhum
resultado de julho foi acessado nesta implementação.
