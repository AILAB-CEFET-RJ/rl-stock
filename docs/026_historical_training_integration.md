# Integração histórica curta dos dois cenários

> Registro **026** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 025](025_historical_normalization.md) · Seguinte: [Registro 027](027_validation_selection.md)

Esta etapa conecta o replay v3 ao Gymnasium usando os manifestos de elegibilidade
e os normalizadores históricos de treino já congelados. O ambiente
`HistoricalTrainingEnv` admite exclusivamente as datas de treino do cenário:
50 em `all_gaps` e 43 em `short_gaps`.

## Ambiente e controles

O construtor carrega o normalizador por seu loader com proveniência e confere
cenário, universo, ordem dos ativos, partição e regra de lacunas contra o
protocolo congelado. Converte explicitamente os parâmetros econômicos do
protocolo para o núcleo: capital, taxas, participação, zona morta, escala da
recompensa e piso de capital. O encoder usa a mesma escala de capital.

Amostram-se uniformemente todas as datas congeladas de treino, com reposição.
Não se escolhem apenas dias curtos ou estratégias que terminem em caixa.
O normalizador continua ajustado no conjunto completo do cenário. A seed
controla a sequência de datas; opções para forçar outra data no reset são recusadas.
O acesso direto a uma sessão também recusa datas fora do conjunto de treino.

Para limitar memória, o ambiente carrega sessões sob demanda e mantém cache
de duas datas. Verifica os hashes dos arquivos canônicos e das grades de
todas as datas de treino antes do aprendizado; revalida as features de toda
a cauda da sessão carregada, inclusive a parte que um stop poderia não visitar.
Ao finalizar o smoke, confere novamente dados e normalizador.

A interface de ação, execução no minuto seguinte, máscaras, caixa compartilhado,
recompensa e saída reutiliza o adaptador/núcleo v3 já testado. Lacunas no interior
não reiniciam o episódio. Ausência inesperada na saída aborta o ajuste antes
de devolver uma transição de treinamento. Falha econômica de liquidação
mantém posições e é reportada como terminal verdadeiro, com horizonte zero.
Não há bootstrap por limite de tempo nesse encerramento financeiro.

## Treinos curtos de integração

O comando de smoke aceita entre 368 e 4.096 transições por ajuste e recusa
orçamentos completos. Executa PPO, A2C, SAC e DDPG nos dois cenários, usando 384 transições
solicitadas por ajuste e seed 0. Aplica as configurações reduzidas de smoke
já documentadas: PPO com rollout de 32 passos, uma época e batch 16;
SAC/DDPG com warmup 32, batch 32 e replay 1024. A2C usa rollout de cinco passos.
Todos preservam gamma 1, redes de largura 64 e Adam explicitamente configurado.

```sh
caffeinate -i env \
  PYTHONPATH=/private/tmp/rl-stock-training-deps \
  MPLCONFIGDIR=/private/tmp/rl-stock-matplotlib \
  /Users/ebezerra/miniconda3/envs/ailab/bin/python \
  -m rl_boleta.historical_training --historical-smoke \
  --normalizer-dir results/v3_historical_train_normalizers_2026-10-12 \
  --scenario ALL --algorithm ALL --steps 384 --seed 0 \
  --output results/v3_historical_training_smoke_verified_2026-10-12
```

Os caminhos temporários correspondem às dependências preparadas nesta máquina.
A saída deve ser nova; `caffeinate` evita suspensão por inatividade no macOS.

Cada ajuste deve completar pelo menos um episódio, atualizar efetivamente o
ator, manter parâmetros finitos e respeitar o orçamento/pequeno excesso de
rollout permitido. Em todos os algoritmos audita-se a observação terminal;
SAC/DDPG também auditam `dones`, horizonte zero e ausência de flags de timeout
no buffer de replay. Resíduos não são descartados para satisfazer o teste.

Após salvar/carregar os checkpoints, a previsão determinística deve ser
idêntica e a cópia do normalizador deve preservar exatamente as estatísticas.
O modelo recarregado é executado deterministicamente somente nas datas de
treino amostradas pelo smoke, mantendo as estatísticas congeladas.

Não se consultam preços ou resultados de validação/teste. Retornos nos rastros
são diagnósticos de treino e não medem generalização, não selecionam modelos
e não são resultados para a comparação do paper. Este comando não executa
os 286 ajustes ou os orçamentos completos registrados no protocolo.

A saída contém checkpoints, cópias dos normalizadores, configurações efetivas,
versões, hashes, datas, desfechos e auditorias por cenário/algoritmo, além de
um relatório de toda a execução. A contabilidade do checker Gymnasium e da
previsão de prova fica separada dos passos e datas do aprendizado.

## Resultado e verificações de 12/10/2026

Os oito ajustes passaram com 18 ativos e 15.502 entradas:

| Algoritmo | Transições por cenário | Atualizações por cenário |
|---|---:|---:|
| PPO | 384 | 12 |
| A2C | 385 | 77 |
| SAC | 384 | 352 |
| DDPG | 384 | 352 |

O A2C completou seu rollout de cinco passos com uma transição adicional
permitida. Todos atualizaram o ator, mantiveram parâmetros finitos, completaram
pelo menos um episódio e reproduziram exatamente as previsões após recarregar.
Os quatro buffers off-policy passaram na auditoria de terminais sem timeout.
As estatísticas de normalização ficaram congeladas. Hashes de código, dados,
normalizadores e checkpoints, datas de amostragem e contagem de episódios foram
conferidos. O relatório da suite final tem status `historical_train_smoke_completed`.

A regressão completa passou: **212 testes, sem falhas ou testes pulados**.
Os cinco testes novos cobrem amostragem por seed, conjunto integral de datas,
cache limitado, exclusão de julho, reset sem override, preflight de hashes,
cauda inválida, accounting/terminal equivalentes ao replay e limite do smoke.

**A integração passou, mas isso não significa sucesso financeiro.** Houve
12 encerramentos durante o aprendizado: 10 com falha de liquidação e dois em
caixa. Na avaliação congelada das datas de treino amostradas, houve 20 execuções:
18 com resíduos e duas em caixa. Esses números repetem datas entre algoritmos
ou cenários; não são 12/20 sessões independentes nem estimativas da taxa final
de sucesso de modelos plenamente treinados. Os resíduos foram preservados.

Uma verificação adicional em 19/05/2025, data de treino compartilhada pelos
smokes, executou os controles caixa e entrada com alocação igualitária. Ambos
terminaram em caixa sob as mesmas regras. Portanto, a falha dos agentes nessa
data não demonstra uma impossibilidade universal de liquidar; depende da
carteira e da capacidade disponível. Esse probe isolado está em
`results/v3_training_exit_probe_2026-10-12/manifest.json` e não seleciona parâmetros.
A análise futura deve comparar exposição residual e encerramento em caixa com
baselines, sem tratar retorno marcado com resíduos como retorno realizado.

Artefato final: `results/v3_historical_training_smoke_verified_2026-10-12/`.
O diretório sem `verified` preserva a primeira execução, anterior à separação
mais explícita da contabilidade de checker/probe e do aprendizado e ao manifesto
de status da suite. Use os relatórios finais. Nenhum preço/resultado de junho ou
julho foi acessado, e nenhum modelo foi escolhido por desempenho nesta etapa.

## Próximo passo

Implementar o executor da seleção por validação, com grade, sementes e orçamento
registrados, agregação por sessão e comparação com baselines. O reajuste final
continua condicionado a essa seleção, com novo normalizador em 65/57 datas.
Julho permanece protegido para a avaliação final descritiva. A simulação
continua condicionada às limitações de recebimento/fuso e da fonte dos livros.

## Atualização: executor de validação

O [executor de seleção por validação](027_validation_selection.md) foi implementado
para os algoritmos principais e verificado com orçamento diagnóstico. O ranking
diagnóstico não autoriza reajuste final; a seleção protocolar e as variantes
continuam pendentes. A codificação histórica passou a reutilizar features
causais em cache, com equivalência numérica verificada.
