# Integração de PPO, A2C, SAC e DDPG

`algorithm_builders.py` constrói as quatro classes reais do Stable-Baselines3
2.3.2. Todas usam `DailyTrainingEnv`, o mesmo encoder congelado e o mesmo núcleo
econômico. `build_ppo` permanece como atalho compatível. O treinador legado
continua bloqueado; o comando público executa apenas sessões sintéticas.

## Configurações verificadas

| Algoritmo | Configuração de referência |
|---|---|
| PPO | Rollout 2048, minibatch 64, dez épocas, GAE 0,95, clipping 0,2 |
| A2C | Rollout 5, uma atualização por rollout, GAE 1, Adam, sem normalização de vantagens |
| SAC | Dois críticos Q, replay 100.000, batch 256, 10.000 passos aleatórios iniciais, uma atualização por passo, tau 0,005, entropia adaptativa inicial 1 e alvo −N |
| DDPG | Um crítico Q, mesmos replay/batch/aquecimento/tau do SAC, ator e crítico atualizados a cada passo, ruído gaussiano independente com desvio 0,1 |

Todos usam gamma 1, atores e críticos separados com duas camadas ReLU,
largura 64 ou 128 e taxa constante 0,0001 ou 0,0003. Todos os otimizadores usam
Adam com betas (0,9; 0,999), epsilon 0,00001 e decaimento de pesos zero. No SAC,
isso inclui o otimizador do coeficiente de entropia, que a biblioteca constrói
separadamente dos otimizadores da política. A2C recebe explicitamente
`use_rms_prop=False`; o padrão da biblioteca seria incompatível com o paper.

A inicialização é Xavier uniforme, ganho 1, com vieses zero. Foi explicitada
uma exceção no paper e no JSON: a cabeça condicional `log_std` do SAC recebe
pesos e vieses zero, para produzir desvio inicial 1 em qualquer entrada. Pesos
Xavier nessa cabeça não garantiriam essa condição. PPO e A2C também começam
com `log_std=0`. As redes alvo são cópias exatas das redes online após a
inicialização, com armazenamento independente.

O DDPG usa a classe DDPG real. Embora o SB3 compartilhe código com TD3, sua
configuração usa um crítico, atualizações sem atraso e nenhum ruído efetivo de
suavização da política alvo (`target_noise_clip=0`). O ruído de exploração é
somado à ação e a soma é limitada aos limites; a avaliação determinística não
usa esse ruído.

As interfaces foram conferidas com as fontes instaladas e a documentação
oficial: [A2C](https://stable-baselines3.readthedocs.io/en/v2.3.2/modules/a2c.html),
[SAC](https://stable-baselines3.readthedocs.io/en/v2.3.2/modules/sac.html) e
[DDPG](https://stable-baselines3.readthedocs.io/en/v2.3.2/modules/ddpg.html).
`describe_agent` salva uma representação JSON das configurações efetivas,
incluindo os grupos de parâmetros dos otimizadores.

## Executar somente a validação sintética

Após instalar `requirements-training.txt` em ambiente separado:

```sh
python -m unittest discover -s tests -v
python -m rl_boleta.daily_training --synthetic-smoke --algorithm ALL \
  --output results/four_algorithm_smoke_novo --steps 384 --seed 0
```

Também é possível escolher um algoritmo com `--algorithm SAC`, por exemplo.
O diretório deve ser novo; resultados anteriores não são sobrescritos. Cada
algoritmo tem subdiretório com checkpoint, normalizador e relatório. O resumo
do conjunto fica em `suite_report.json`.

O modo sintético reduz o PPO para rollout 32, minibatch 16 e uma época. Reduz
SAC/DDPG para replay 1024, batch 32 e 32 passos iniciais aleatórios, permitindo
exercitar atualizações sem executar um experimento longo. O A2C mantém seu
rollout de cinco passos. As diferenças são registradas em cada relatório.
São ajustes de integração, não candidatos adicionais do estudo.

A validação exige mudança nos pesos do ator, pesos finitos, conclusão de
sessão e igualdade de previsões após salvar/recarregar. O modelo recarregado
também percorre três sessões sintéticas em avaliação determinística. Para
SAC/DDPG, confere-se o estado terminal guardado no replay, com horizonte zero
e máscara que impede bootstrap para a sessão seguinte. O limite de orçamento
aceita apenas o excesso necessário para completar um rollout.

A auditoria das ações distingue estágios: PPO/A2C expõem propostas gaussianas
antes do clipping; SAC/DDPG expõem ações após squash ou clipping do ruído.
As contagens não devem ser comparadas como medidas iguais de clipping bruto.

## Escopo restante

Não foram usados dados ou resultados da dissertação. Os testes sintéticos não
estabelecem rentabilidade, viabilidade de cobertura ou recursos para o estudo
completo de 18 ativos. Faltam os manifestos dos splits, a resolução dos relógios,
os mínimos de sessões, as ablações e o executor dos orçamentos, sementes e
seleção previstos. A avaliação histórica de julho continua protegida.

## Validação de 08/10/2026

Os 110 testes passaram com as dependências de treino instaladas, sem testes
ignorados. O conjunto final está em
`results/four_algorithm_smoke_verified_2026-10-08/suite_report.json`:

| Algoritmo | Transições pedidas | Realizadas | Atualizações |
|---|---:|---:|---:|
| PPO | 384 | 384 | 12 |
| A2C | 384 | 385 | 77 |
| SAC | 384 | 384 | 352 |
| DDPG | 384 | 384 | 352 |

O passo extra do A2C completa seu rollout de cinco passos, dentro do limite
previsto. Todos mudaram os pesos do ator, salvaram/recarregaram checkpoints com
previsões idênticas e executaram três sessões em avaliação congelada. SAC/DDPG
preservaram o estado terminal no replay com horizonte zero e sem bootstrap de
limite de tempo. Os hashes de todos os módulos registrados foram conferidos.
As atualizações não são equivalentes em quantidade de operações: PPO conta
épocas e os demais contam suas atualizações de treino; não representam custos
computacionais iguais. O ambiente usado foi Python 3.11.13, SB3 2.3.2,
Gymnasium 0.29.1, PyTorch 2.2.2 e NumPy 1.26.4, com dependências adicionais
isoladas em `/private/tmp/rl-stock-training-deps`.
