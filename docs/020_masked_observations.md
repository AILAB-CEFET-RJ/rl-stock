# Observações mascaradas e normalização v3

> Registro **020** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 019](019_missing_data_core.md) · Seguinte: [Registro 021](021_masked_training.md)

Implementação em `rl_boleta/masked_observations.py`, conectada ao controlador
experimental por um checkpoint de referências passadas. O v2 permanece
inalterado. Não há treinamento de agentes ou normalização histórica nesta etapa.

## Representação

Cada um dos 20 passos históricos contém os 40 valores de mercado por ativo,
seguidos das indicações de disponibilidade e das idades de recebimento e
referência de preço. Para 18 ativos: 20×774 campos de histórico, mais 22 de
contexto, totalizando 15.502 entradas.

Quando falta uma captura válida, os 40 valores internos daquele ativo são
`None`; somente na codificação final eles viram zeros, **depois** da
padronização. Uma indicação zero acompanha esses campos. Um zero real,
como volume negociado zero, continua válido e entra nas estatísticas.

O denominador dos preços é o midpoint do último ponto válido anterior do
mesmo ativo. O cursor calcula a transformação antes de atualizar a referência
com o ponto corrente. Depois de uma lacuna, a transformação pode representar
vários minutos; a idade da referência torna o intervalo explícito.

O controlador mantém checkpoints imutáveis com os últimos livros observados
e seus instantes na grade. A observação recebe o checkpoint **até a referência
de defasagem anterior à janela**, sem consultar dados posteriores. Isso permite
reconstruir a janela mesmo quando o último preço conhecido já saiu dela.
A codificação é determinística: não depende de chamadas anteriores ao encoder.

As idades são divididas por 23.400 segundos, com limite [0,1], conforme a
proposta. A idade de recebimento continua aumentando quando o ativo está
indisponível. A idade da referência usa sentinela zero se faltar valor corrente;
a indicação de disponibilidade distingue essa sentinela de um dado válido.

O contexto inclui caixa, exposições e patrimônio apoiados nas marcas observadas,
tempo desde a abertura e tempo até a saída. Ele não trata o preço carregado
como liquidez disponível e não recebe elegibilidade ou duração futura de lacunas.

## Normalização

`fit_masked_normalizer` usa momentos populacionais por feature, com contagens
individuais. Inclui cada ponto efetivamente usado no histórico uma vez, da
primeira janela causal até a saída. Janelas sobrepostas não repetem o ponto.
Dados ausentes não entram nas médias ou variâncias. Features constantes usam
escala 1; valores padronizados são limitados a [−10,10]. Máscaras e idades não
são padronizadas com estatísticas aprendidas.

Só se ajusta em treino ou refit de desenvolvimento, com datas explícitas.
Validação e teste são rejeitados para ajuste. A serialização preserva ordem de
features, contagens, médias, escalas, datas e schema; a leitura rejeita schemas
do v2 ou incompatíveis. Estatísticas carregadas permanecem congeladas.

Nesta implementação, o ajuste aceita **somente sessões declaradamente sintéticas**.
A preparação histórica e o manifesto final de elegibilidade ainda não existem;
passar os 79 dias candidatos diretamente ao ajuste permanece bloqueado.
Os futuros dados de mercado devem ter cinco níveis e dez negócios completos
validados, ordenados, recebidos até o instante usado; não se inventam negócios
quando um livro aparece sem eles.

## Verificação

Os 18 testes novos verificam:

- dimensão exata de 15.502 campos;
- máscara e zero inserido depois da padronização;
- zeros reais válidos, contagens por feature e momentos calculados à mão;
- ausência de repetição de pontos entre janelas sobrepostas;
- referência preservada em lacuna de 31 minutos, maior que a janela;
- invariância ao modificar dados futuros e rejeição de referências/negócios futuros;
- equivalência dos valores de mercado ao v2 quando os dados estão completos;
- contexto da carteira durante uma lacuna e após a cotação retornar;
- ajuste por partição, recusa de dados históricos ainda não liberados e
  reprodução exata após salvar/carregar o normalizador.

```sh
python -m unittest discover -s tests -p test_masked_observations.py -v
python -m scripts.check_masked_observations \
  --output-dir results/v3_masked_observations_2026-10-12
```

O diretório de saída deve ser novo. O segundo comando ajusta estatísticas em
dois dias sintéticos de março e usa-as congeladas em um pregão curto sintético
de julho, com 18 ativos, lacunas individuais e ausência simultânea de todos.
Grava normalizador, rastros de codificação e hashes. Não ajusta redes neurais.

A regressão completa passou: 169 testes, sem falhas ou testes pulados.

## Próximo passo

O [adaptador Gymnasium e os quatro algoritmos](021_masked_training.md) foram
integrados para treinos sintéticos curtos. A [grade histórica parcial e os
baselines](022_masked_preparation_and_baselines.md) também estão disponíveis para
diagnóstico. Segue o congelamento da elegibilidade. A regra para lacunas
longas e a certificação do horário de mercado do livro continuam pendentes.

## Atualização: seleção condicional de datas

A [regra de lacunas e a elegibilidade condicional](023_gap_rule_and_conditional_eligibility.md)
foram congeladas no rascunho v3 na etapa seguinte. A regra principal não
acrescenta exclusão por duração; limites predefinidos são sensibilidades dos
mesmos modelos congelados. A seleção contém 50/15/14 dias e 65 de reajuste final.
Normalização e fitting históricos continuam pendentes. Os relatos de pendências
acima descrevem o estado na conclusão original desta etapa.
