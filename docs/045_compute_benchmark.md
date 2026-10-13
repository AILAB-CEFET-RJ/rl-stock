# Escolha explícita CPU/CUDA e benchmark dos parâmetros completos

> Registro **045** · Data de referência: **2026-10-13** · [Índice](README.md)
> Anterior: [Registro 044](044_workstation02_historical_smoke.md) · Seguinte: [Registro 046](046_cuda_campaign_plan.md).

Implementação na branch `feat/workstation-compute-benchmark`, depois de confirmar
a preparação e os 16 treinos históricos curtos em CPU na workstation02.

## Dispositivo no pipeline

`build_agent` aceita `device='cpu'` ou `'cuda'`, preservando CPU como padrão.
CUDA indisponível é erro explícito, sem escolha automática de outro backend.
Os CLIs de treinamento histórico, sintético v3 e seleção por validação expõem
`--device`. Configurações efetivas e o plano de seleção registram o dispositivo;
retomar a seleção requer o mesmo plano, inputs e código. A recarga de checkpoint
usa o backend escolhido para conferir a mesma previsão determinística.
As regras econômicas, estatísticas congeladas e bloqueios de seleção permanecem.

## Medição proposta

`python -m rl_boleta.compute_benchmark` executa um algoritmo em um dispositivo
por processo, exclusivamente com `HistoricalTrainingEnv` na partição de treino.
Não calcula ranking financeiro, acessa preços de validação/teste ou libera
reajuste final. Os modelos produzidos ficam identificados como benchmark.

Usa os parâmetros completos do builder (`smoke=False`): PPO 2.048 passos por
rollout, batch 64 e dez épocas; A2C cinco passos; SAC/DDPG buffer 100.000, batch
256 e início das atualizações após 10.000 passos. Largura 128 por padrão,
configurável para 64; LR dentro da grade congelada. Seeds e origem são registrados.
O benchmark exige o perfil revisado, com 54 pontos de encerramento automático
e utilidade terminal em caixa.

O aquecimento computacional ocorre antes da medição: um rollout para PPO/A2C
ou 10.000 passos para SAC/DDPG. Isso é distinto da janela causal de features.
Depois mede 2.048 transições solicitadas, com limite de excesso de rollout
registrado (A2C pode fazer 2.050). É obrigatório haver atualizações e mudança
do ator nessa fase; medir só a coleta inicial de SAC/DDPG seria insuficiente.

CUDA é sincronizado antes/depois dos cronômetros, conforme a
[API do PyTorch](https://docs.pytorch.org/docs/2.10/generated/torch.cuda.synchronize.html).
TF32 é desabilitado no benchmark, e os recursos são registrados em fases:
setup, aquecimento e aprendizado medido. O tempo de aprendizado inclui IO e
processamento das sessões sorteadas. Não é uma medição isolada de kernels.

RAM: pico residente do processo (`ru_maxrss`), convertido a bytes por sistema,
e soma dos arrays reais do buffer. CUDA: picos de memória alocada por tensores
e reservada pelo allocator, separados para setup/aquecimento e medição,
conforme as [APIs de memória do PyTorch](https://github.com/pytorch/pytorch/blob/v2.10.0/torch/cuda/memory.py).
Esses picos não incluem memória do driver ou de outros processos. O pico de
RAM é cumulativo por processo; usar um processo novo por combinação.

SAC/DDPG mantêm o replay na RAM mesmo com redes em CUDA. Na dimensão 15.505
e 18 ações, os arrays somam 12.412.400.000 bytes (~11,56 GiB), além de modelos,
sessões e temporários. `--materialize-buffer` escreve nas páginas de todos os
arrays antes do aprendizado, para medir memória residente de um buffer completo.
Sem essa opção, páginas ainda não usadas podem subestimar o consumo final.
Em Linux há verificação de RAM disponível antes de construir o modelo.
O preenchimento inicial não muda `pos/full` nem insere transições fabricadas.

O benchmark verifica pesos finitos e salvamento/recarga no mesmo dispositivo.
O checkpoint recarregado usa buffer de um item apenas para conferência de
inferência, evitando uma segunda alocação completa. Nenhum artefato prévio é
reescrito; diretórios existentes são recusados e falhas recebem relatório.

## Primeira execução na workstation02

Após publicar a branch e atualizar o clone via Git, iniciar por PPO nos dois
dispositivos, com os mesmos inputs, seed e largura. Cada chamada é um processo
novo e tem limite de 15 minutos; o treino imprime progresso a cada 500 passos.

```bash
cd "$HOME/ailab/rl-stock"
set -o pipefail
for device in cpu cuda; do
  timeout 900s env PYTHONNOUSERSITE=1 \
    "$HOME/venvs/rl-stock-ws02/bin/python" \
    -m rl_boleta.compute_benchmark \
    --normalizer-dir results/ws02_account_campaign_inputs_2026-10-13/cash_settled/normalizers \
    --scenario all_gaps --algorithm PPO --device "$device" \
    --width 128 --measured-steps 2048 --materialize-buffer \
    --output "results/ws02_compute_benchmark_v1/PPO_${device}_r0" \
    2>&1 | tee "results/ws02_compute_benchmark_PPO_${device}_r0.log" \
    || break
done
```

Conferir os dois resultados antes de ampliar para A2C/SAC/DDPG. Repetir as
medições em processos novos e pastas `r1/r2`, alternando a ordem CPU/CUDA, e
comparar mediana/dispersão de tempo. Verificar também largura 64 e cargas de
outros cenários/regimes antes de escolher o dispositivo por algoritmo. Uma
medição de 2.048 passos não cobre todas as datas, caches ou evolução dos modelos;
serve de primeira referência, não autoriza extrapolação linear da campanha.

## Verificação local e pendências

Os testes usam ambiente fabricado pequeno para conferir o fluxo completo dos
quatro algoritmos com parâmetros reais, aquecimento separado, atualizações,
excesso de rollout, medição de arrays, salvamento/recarga, falta de memória e
proteção de saída existente. Também cobrem CPU padrão e erro explícito para
CUDA indisponível. Os dados de mercado da workstation e a RTX 5090 ainda não
foram usados nessa implementação. A regressão local passou com **274 testes
em 95,500 segundos**, sem falhas ou testes pulados; os últimos ajustes de
perfil e proteção de retomada passaram em **seis testes de benchmark** e
**dez testes de seleção**. Foram conferidos **305 links locais**, todos válidos,
e `git diff --check` passou.
Medições remotas e consolidação do orçamento
experimental permanecem pendentes.

## Primeiro benchmark remoto: PPO

O usuário publicou a branch, atualizou o clone e confirmou duas execuções
`compute_benchmark_completed` na workstation02, em CPU e CUDA. Ambas usam
`cash_settled/all_gaps`, largura 128, seed 0, parâmetros completos, um rollout
de aquecimento e 2.048 transições medidas, com dez épocas de atualização nessa
fase. O buffer materializado soma 127.213.568 bytes (121,32 MiB).

| Medida | CPU | CUDA |
| --- | ---: | ---: |
| Tempo medido (s) | 17,542 | 11,297 |
| Pico residente do processo (GiB) | 1,387 | 2,305 |
| Pico de tensores CUDA (MiB) | — | 107,96 |
| Pico reservado pelo allocator CUDA (MiB) | — | 142,00 |

CUDA apresentou razão de tempos CPU/CUDA de aproximadamente 1,55 e redução
de tempo de 35,6% nessa medição. É uma execução por dispositivo, com CPU
executada primeiro: cache do sistema, variação de carga e sessões sorteadas
podem influenciar o resultado. Ainda não é decisão definitiva de dispositivo
nem estimativa da campanha completa. RAM do processo e VRAM são medidas
distintas, sem soma direta para dimensionar disponibilidade por unidade.

O status de sucesso também comprova atualização do ator, pesos finitos,
comparação exata de checkpoint no mesmo backend e hashes dos inputs. As
medições pendentes são A2C/SAC/DDPG, repetição de PPO e sensibilidade de
largura/carga. O próximo lote proposto executa os três algoritmos restantes
em CPU e CUDA sequencialmente, mantendo os inputs e os parâmetros definidos.

## Decisão posterior: CUDA como dispositivo da workstation

O usuário decidiu seguir com CUDA nos quatro algoritmos, aproveitando a GPU
disponível e o ganho observado no PPO. A busca do dispositivo mais rápido por
algoritmo deixa de ser pré-requisito da campanha. Isso não demonstra vantagem
de CUDA para todos os algoritmos, mas define a escolha operacional do projeto.

O próximo lote substitui a comparação de seis execuções por três verificações:
A2C, SAC e DDPG somente em CUDA, mantendo o perfil `cash_settled/all_gaps`,
largura 128, parâmetros completos e materialização do buffer. O PPO já passou
na GPU. Usar nova raiz `results/ws02_cuda_verification_v1/` para preservar
quaisquer execuções do lote de comparação anterior.

Os runners recebem `--device cuda` explicitamente. Seus defaults CPU são
mantidos para compatibilidade e execução local; nenhum código remoto precisa
ser atualizado para esses comandos. CPU permanece alternativa configurável.
O objetivo agora é conferir execução, atualização, checkpoint e recursos em
CUDA antes de dimensionar a campanha completa, com os bloqueios metodológicos
inalterados. O sucesso dos três algoritmos na GPU ainda está pendente.

## Verificações CUDA concluídas

O usuário confirmou `compute_benchmark_completed` para A2C, SAC e DDPG no
lote CUDA, além do PPO já verificado. Todos usaram os parâmetros completos,
largura 128 e o perfil `cash_settled/all_gaps`. SAC/DDPG realizaram o aquecimento
de 10.000 passos sem atualizações, seguido de 2.048 passos com 2.048 updates.
A2C realizou 2.050 passos na fase medida, com 410 updates, completando rollouts
de cinco passos; o aquecimento teve cinco passos. A diferença de orçamento
é registrada e esperada.

| Algoritmo | Passos medidos | Tempo (s) | Pico RAM processo (GiB) | Pico tensores CUDA (MiB) | Pico reservado CUDA (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: |
| PPO | 2.048 | 11,297 | 2,305 | 107,96 | 142,00 |
| A2C | 2.050 | 8,826 | 1,929 | 107,96 | 144,00 |
| SAC | 2.048 | 34,047 | 13,541 | 212,56 | 264,00 |
| DDPG | 2.048 | 29,930 | 13,356 | 166,64 | 204,00 |

Buffers medidos: PPO 127.213.568 bytes; A2C 310.580 bytes; SAC e DDPG
12.412.400.000 bytes cada, materializados na RAM. A baixa VRAM de tensores
não desloca esses buffers para a GPU e não mede toda a memória do driver.

Os quatro status de conclusão também atestam atualização do ator na fase
medida, pesos finitos, comparação exata de checkpoint no mesmo dispositivo
e verificação dos inputs pelo runner. Não houve preços de validação/teste
nem seleção financeira. A decisão operacional de usar CUDA passa a ter
verificação funcional nos quatro algoritmos. Esses dados sustentam um job
por vez nessa configuração; não medem consumo de jobs concorrentes, todas
as datas ou o orçamento completo de treino.

Próximo passo: consolidar o protocolo executável e o plano da campanha com
CUDA explícito, execução inicial sequencial, limites/retomada e controle de
artefatos. A fase medida é curta; os tempos não são promessa da duração total.
Os bloqueios de seleção/reajuste final ainda precisam ser resolvidos na
consolidação metodológica. Nenhuma flag de autorização foi alterada aqui.
