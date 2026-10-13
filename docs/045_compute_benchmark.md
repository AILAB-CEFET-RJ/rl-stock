# Escolha explícita CPU/CUDA e benchmark dos parâmetros completos

> Registro **045** · Data de referência: **2026-10-13** · [Índice](README.md)
> Anterior: [Registro 044](044_workstation02_historical_smoke.md) · Seguinte: próxima entrada 046, ainda não criada.

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
