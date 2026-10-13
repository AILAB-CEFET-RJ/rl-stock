# Normalização histórica de treino por cenário

> Registro **025** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 024](024_two_scenario_experiments.md) · Seguinte: [Registro 026](026_historical_training_integration.md)

Esta etapa produz os normalizadores de treino dos dois cenários v3, a partir
dos manifestos congelados em
`results/v3_two_scenario_design_verified_2026-10-12/`.
São 50 datas de `all_gaps` e 43 de `short_gaps`. As datas são exatamente as
selecionadas pelos manifestos, sem remoção por resultados econômicos.

O reajuste final ainda não produz estatísticas: sua normalização em 65/57
sessões de treino + validação só deve acontecer após selecionar os modelos
pela validação. A API atual recusa `final_refit`, validação e teste como fases
de ajuste. Nenhuma rede é treinada nesta etapa.

## Estatísticas e representação

Ajustam-se médias, desvios populacionais (`ddof=0`) e contagens para os 40
campos de mercado de cada ativo, totalizando 720 features para 18 ativos.
Os campos de máscara e idade continuam com escalas fixas, sem ajuste aprendido.

Para cada sessão, percorrem-se uma única vez os pontos de features usados
desde o aquecimento causal até a saída, inclusive. O ponto inicial de referência
não conta como feature; janelas sobrepostas não repetem observações no ajuste.
Capturas reutilizadas em minutos válidos distintos continuam sendo pontos de
grade distintos, conforme a representação temporal do protocolo.

Valores ausentes são `None` durante o cálculo e não entram nas contagens,
médias ou variâncias. Um zero real de volume, após `log1p`, conta como dado.
Cada feature tem sua própria contagem. Campos constantes usam desvio 1.
Só na transformação os dados são padronizados e limitados a [-10,10], e os
valores ausentes viram zero acompanhado da máscara. As estatísticas ajustadas
não sofrem clipping.

A referência de preço é o último ponto anterior válido do mesmo ativo. As
referências causais sobrevivem a lacunas maiores que a janela visível. O ajuste
não calcula recompensa, retorno de estratégia, fills ou liquidação: percorre
features de mercado validadas, sem uma política econômica.

## Proveniência e proteção das partições

`fit_train_normalizers` aceita um desenho congelado, verifica seus hashes e
os dos manifestos filhos, e exige a mesma preparação e regras de features nos
dois cenários. Exige também os mínimos operacionais da seleção.

Lê cada data de treino principal uma vez, por `read_eligible_session` com
`partition='train'`, e atualiza as estatísticas dos cenários que admitem a data.
Não precisa ler preços de junho ou julho. Os hashes e listas de datas desses
períodos são metadados de proveniência, não valores utilizados no ajuste.

`HistoricalMaskedNormalizer` mantém o mesmo contrato de transformação do
encoder, mas inclui `synthetic_only=False`, nome do cenário e hash do manifesto
de elegibilidade. O loader histórico exige o manifesto do ajuste, confere os
arquivos e o vínculo com as datas exatas do cenário. Não se pode trocar arquivos
entre cenários apenas renomeando-os.

A API genérica `fit_masked_normalizer` e o loader sintético continuam recusando
normalizadores históricos. O adaptador Gymnasium desta etapa também recusa
normalizadores históricos; liberar treino de redes exige implementar sua
entrada controlada pelos manifestos. O encoder já aceita os normalizadores
históricos para transformar observações de forma congelada.

## Execução e artefatos

```sh
caffeinate -i /Users/ebezerra/miniconda3/bin/python3 \
  -m rl_boleta.historical_normalization \
  --design-dir results/v3_two_scenario_design_verified_2026-10-12 \
  --partition train \
  --output-dir results/v3_historical_train_normalizers_2026-10-12
```

A saída exige diretório novo. O código usa a biblioteca padrão; Gym, Torch e
SB3 não são necessários para ajustar essas estatísticas. `caffeinate` evita
suspensão por inatividade nesta máquina macOS.

A saída contém `normalizer_all_gaps_train.json`,
`normalizer_short_gaps_train.json` e `manifest.json`, com datas, contagens,
quantidade de pontos únicos, hashes, versão do Python e estado de execução.
Em caso de erro, o manifesto fica `failed`, sem um ajuste concluído utilizável.
Salvar/carregar deve preservar exatamente médias, desvios, contagens e origem.

```python
from rl_boleta.historical_normalization import load_train_normalizer
from rl_boleta.masked_observations import MaskedEncoder

normalizer = load_train_normalizer(
    'results/v3_historical_train_normalizers_2026-10-12', 'short_gaps')
encoder = MaskedEncoder(normalizer)
# encoder.flatten(observation, trades) usa estatísticas congeladas.
```

Um normalizador por cenário é compartilhado entre algoritmos/sementes que
usam a mesma representação e partição. Não se ajusta novamente durante a
validação, o teste ou a comparação em datas comuns. Cada checkpoint conserva
o normalizador de sua própria fase e cenário.

## Próximo passo

Integrar o ambiente de treinamento histórico aos manifestos e normalizadores,
com validação de cenário, partição, universo e escala de capital. Em seguida,
executar uma integração histórica curta antes da grade de 286 ajustes.
O paper e os resultados da dissertação permanecem inalterados. A simulação
continua condicionada às hipóteses de recebimento/fuso e não certifica o
horário de mercado ou a liquidez efetivamente disponível.

## Resultado e verificações de 12/10/2026

| Cenário | Datas de treino | Pontos únicos de features | Contagens por feature: mínimo–máximo |
|---|---:|---:|---:|
| Todas as lacunas | 50 | 14.028 | 13.818–13.866 |
| Lacunas curtas | 43 | 11.842 | 11.737–11.767 |

Cada ponto é um instante da grade com valores ou ausências para os 18 ativos;
a contagem de cada feature inclui somente os instantes válidos daquele ativo.
A diferença entre contagens e pontos totais reflete máscaras, sem zeros imputados
nas estatísticas. Médias/desvios são diferentes entre os cenários.

A regressão completa passou: **207 testes, sem falhas ou testes pulados**.
Os oito testes novos cobrem momentos calculados à mão, datas exatas por cenário,
exclusão de validação/teste, fases de ajuste recusadas, roundtrip, binding de
cenário, origens incompatíveis, ausência de negócios e saída `failed` após erro.
Os 18 testes anteriores de observações também passaram com a extração de
features desacoplada de um replay econômico.

Os hashes de código e artefatos foram conferidos. Os loaders preservaram
exatamente as estatísticas salvas. Uma observação histórica de treino foi
codificada com os dois normalizadores congelados, produzindo 15.502 valores
finitos sem alteração dos arquivos. Não foram lidos preços de junho ou julho,
nem gerados normalizadores de reajuste final ou checkpoints de redes.

## Atualização: integração histórica

A [integração histórica curta](026_historical_training_integration.md) verificou
PPO, A2C, SAC e DDPG nos dois cenários com seus normalizadores congelados.
A seleção por validação e o reajuste final continuam pendentes. Os relatos
de pendências anteriores descrevem o estado ao concluir a etapa original.
