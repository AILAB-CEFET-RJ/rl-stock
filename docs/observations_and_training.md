# Observações causais e integração inicial com PPO

Esta etapa liga o contrato do CSV revisado ao controlador diário e ao PPO real
do Stable-Baselines3. O comando disponível executa somente um teste sintético;
não abre dados históricos nem produz evidência de rentabilidade. O treinador
legado continua bloqueado. A [integração posterior dos quatro algoritmos](four_algorithm_integration.md)
acrescenta A2C, SAC e DDPG. Ablações e a busca de hiperparâmetros ainda não foram migradas.

## Representação congelada

`observations.py` lê todos os livros e os dez negócios por ativo do CSV.
A ordem por ativo é:

1. Cinco preços bid, cinco quantidades bid.
2. Cinco preços ask, cinco quantidades ask.
3. Dez preços de negócios, dez quantidades de negócios.

Cada preço é dividido pelo midpoint do mesmo ativo no minuto anterior, menos
um; cada quantidade usa `log1p(quantidade_em_acoes)`. Quantidades não são
divididas por preços. Os negócios preservam o rank do CSV preparado: o
preparador os ordena pelo horário declarado decrescente, com empates estáveis.
Não se calculam retornos entre negócios adjacentes nem se deduz lado agressor.
O rank continua condicionado à hipótese de relógio usada pelo preparador.

Somente esses `40*N` campos recebem padronização aprendida. Depois deles vêm
`N` idades de captura divididas por 60 segundos. As idades dos negócios foram
explicitamente omitidas enquanto sua interpretação temporal estiver indefinida;
seus preços e volumes continuam presentes. Nenhuma dessas transformações muda
os livros usados na execução.

A janela tem formato `(20, 41*N)`. O vetor atual separado contém caixa,
`N` exposições marcadas e patrimônio, divididos pelo capital inicial, seguidos
de minutos decorridos e transições restantes, ambos divididos por 390.
Seu tamanho é `N+4`; não se repetem as posições atuais no histórico.
Para 18 ativos, a entrada achatada tem `20*738+22 = 14782` valores.
O contexto conhecido identifica o intervalo reservado à liquidação.

O paper e o protocolo JSON foram atualizados com esses detalhes. O indicador
retrospectivo de cobertura, o identificador da data e o tempo até uma futura
lacuna não fazem parte da entrada numérica.

## Ajuste e persistência das estatísticas

`fit_normalizer` aceita somente datas de treino (3 de março a 30 de maio) ou,
mediante `partition='final_refit'`, desenvolvimento (março a junho). Rejeita
validação/teste, datas duplicadas, períodos incompatíveis e sessões incompletas.
Cada ponto de `q=2` até a saída entra uma única vez: 388 vetores em um pregão
normal e 208 no pregão curto. `q=1` fornece apenas a referência defasada. A
contagem não depende das janelas sobrepostas nem do instante de stop da política.

As médias e os desvios populacionais usam atualização de Welford. Desvio zero
vira um; os valores padronizados são limitados a `[-10,10]`. Estatísticas, ordem
dos ativos/features, datas, contagem e versão do schema são salvas em JSON.
Carregar ou transformar não reajusta nada; arquivos existentes não são
sobrescritos. Um refit final precisa de um novo normalizador.

## Interface Gymnasium e PPO

`SessionEpisode` oferece os mesmos passos econômicos ao replay por callback e
ao adaptador `DailyTrainingEnv`, evitando uma segunda implementação financeira.
O adaptador segue a interface de cinco resultados descrita na
[documentação oficial do SB3 2.3.2](https://stable-baselines3.readthedocs.io/en/v2.3.2/guide/custom_env.html).
Ele sorteia sessões completas uniformemente com reposição, usando a semente do
ambiente. O conjunto de datas precisa coincidir com o do normalizador.

O último passo é a liquidação: a ação fornecida pelo algoritmo é ignorada e
registrada como tal. Esse passo conta no orçamento. Seu estado terminal contém
a carteira após a saída, inclusive eventuais resíduos, e horizonte zero; o
retorno é `terminated=True`, impedindo bootstrap além da sessão. Não se usa
`VecNormalize`, normalização de recompensa nem atualização de estatísticas no
teste. Se ocorrer uma interrupção inesperada em treino, o ajuste aborta antes
de entregar ao algoritmo uma transição com próximo estado inventado.

`build_ppo` usa atores e críticos separados, ReLU, Adam com os parâmetros do
paper, inicialização Xavier e desvios logarítmicos iniciais zero. Fora do modo
sintético, sua configuração PPO usa rollout 2048, minibatch 64 e dez épocas;
essa configuração é inspecionada pelos testes, mas nenhum ajuste histórico foi
executado. O ponto de entrada público oferece apenas `--synthetic-smoke`.

`evaluate_period` usa `predict(..., deterministic=True)` e o normalizador
congelado. Percorre todas as datas previstas do calendário, inclusive datas sem
quadros, que retornam `not_startable`. Sessões interrompidas ficam nos registros;
seu retorno financeiro completo é `None`, sem imputação de zero. Essa função
não seleciona checkpoints ou altera o modelo.

## Executar a validação sintética

Usar um ambiente separado do Poetry legado. Instalar
`python -m pip install -r requirements-training.txt` e executar:

```sh
python -m unittest discover -s tests -v
python -m rl_boleta.daily_training --synthetic-smoke \
  --output results/observation_smoke_novo --steps 384 --seed 0
```

O diretório de saída deve ser novo. O teste gera três sessões artificiais com
dois ativos fictícios e executa PPO com rollouts de 32 passos, minibatches de 16
e uma época, declarando essas diferenças em relação ao estudo. Confere mudança
dos pesos, conclusão de um pregão, persistência do normalizador e igualdade da
previsão determinística após salvar/recarregar o checkpoint. Registra contagens
de ações propostas fora dos limites antes do clipping do SB3, inclusive no
intervalo terminal em que não se executa intenção discricionária.

Os artefatos são `model.zip`, `normalizer.json` e `report.json`. O relatório
inclui versões, sementes, passos pedidos/realizados, atualizações, duração,
parâmetros, ordem dos sorteios, sessões concluídas e hashes do código/checkpoint.
Os testes de Gym/SB3 são marcados como ignorados quando suas dependências não
estão instaladas; a validação completa exige executá-los com essas dependências.

## Pendências antes dos experimentos

A leitura do CSV não certifica os manifestos ou o significado dos relógios.
Faltam resolver esse ponto, congelar proveniência e elegibilidade de cada split,
verificar os mínimos de cobertura e conectar os
orçamentos, sementes e seleção do protocolo ao executor histórico. O teste de
dois ativos não certifica recursos para os 18 ativos ou para os orçamentos
completos. Essas etapas permanecem anteriores à avaliação protegida de julho.

## Validação realizada em 08/10/2026

Os 102 testes passaram, sem testes ignorados, no Python 3.11.13 com
Stable-Baselines3 2.3.2, Gymnasium 0.29.1, PyTorch 2.2.2 e NumPy 1.26.4. As
dependências adicionais foram instaladas em `/private/tmp/rl-stock-training-deps`,
sem modificar o ambiente `ailab`. O NumPy 2.3.1 originalmente presente era
incompatível com a ponte NumPy do PyTorch 2.2.2; a versão compatível foi fixada
em `requirements-training.txt`.

O teste em `results/observation_smoke_2026-10-08/report.json` concluiu 384
transições e 12 atualizações, com entrada de 1.646 valores para dois ativos e
219.333 parâmetros. Confirmou mudança dos pesos e previsão idêntica após recarga.
O pregão concluído alcançou `scheduled_end`, mas teve `flat=False`: a capacidade
de liquidação sintética não bastou para zerar o estoque. O controlador manteve
os resíduos e os registrou, conforme o protocolo, em vez de apagá-los ou
excluir esse resultado. Os números desse teste não são resultados financeiros
do estudo. Os hashes dos seis módulos usados foram conferidos contra o relatório.
