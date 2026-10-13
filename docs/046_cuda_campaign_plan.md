# Plano operacional CUDA e primeiro ajuste de orçamento completo

> Registro **046** · Data de referência: **2026-10-13** · [Índice](README.md)
> Anterior: [Registro 045](045_compute_benchmark.md) · Seguinte: [Registro 047](047_first_tuning_checkpoint.md).

O usuário pediu a consolidação e deseja iniciar um treinamento antes de dar
aula. Os quatro algoritmos passaram pela verificação funcional em CUDA com
parâmetros completos, e os inputs históricos dos dois regimes foram verificados.
O plano operacional abaixo fixa a execução inicial e distingue ajuste de um
candidato, seleção em validação e reajuste final. Não modifica os perfis ou
normalizadores existentes, nem altera as regras depois de observar retornos.

## Execução

- Workstation02, CUDA explícito, um ajuste por vez, um thread PyTorch no host,
  TF32 desabilitado como no benchmark. Código identificado pelo commit e hashes.
- Regimes independentes: `cash_settled` e `intraday_buying_power`. Cada um tem
  treino próprio nos cenários `all_gaps` e `short_gaps`, com estatísticas de
  mercado congeladas e comparadas à referência do Mac.
- Candidatos de cobertura: principal 50/15/14 datas de treino/validação/teste;
  secundário 43/14/14. Reajuste final previsto: 65 e 57 datas. Os episódios
  continuam diários, com início causal, posições contínuas e máscaras por ativo.
- Caixa inicial USD 100.000, cinco níveis por lado, dez negócios, janela 20,
  idade máxima 60 segundos, latência de uma grade, taxas 1 bp por lado,
  participação 10%, piso de capital 80%, fase automática de saída de 54 pontos
  e utilidade terminal em caixa; gamma de referência 1. Os controles são lidos
  do perfil imutável, não redefinidos pelo launcher.
- Grade de tuning: quatro algoritmos, duas larguras (64/128), duas taxas
  (1e-4/3e-4), seeds 0/1/2 e 500.000 passos solicitados. São 48 ajustes por
  cenário, 96 por regime para os modelos centrais. Os excessos de rollout
  permitidos ficam registrados; nenhum ajuste é ampliado em função do retorno.
- Variantes do principal: 60 ajustes de tuning e 50 finais adicionais por
  regime, previstos no protocolo. Reajustes centrais: 40 por cenário, com
  seeds 100..109 e 1.000.000 passos. Total planejado por regime: 286 ajustes
  e 208 milhões de passos solicitados; ambos os regimes: 572 e 416 milhões.
- Checkpoint válido para seleção: orçamento final fixo, normalizador próprio,
  hashes de inputs/código/artefatos e identidade do candidato. Ajustes concluídos
  podem ser reutilizados mediante verificação; interrompidos devem ser refeitos
  desde a seed inicial. Não há promessa de retomada exata no meio do ajuste.

## Primeiro ajuste a iniciar

PPO, `cash_settled/all_gaps`, largura 128, LR 1e-4, seed 0, CUDA, parâmetros
completos, 500.000 passos solicitados (PPO pode concluir 501.760 para completar
o rollout). A configuração pertence à grade predefinida e foi priorizada por
verificação computacional, sem consulta de retornos de validação ou teste.

Usar o `train_job` já instalado, com um contexto que fornece apenas o diretório
de normalização. Ele cria `HistoricalTrainingEnv`, que restringe as datas ao
treino e verifica os vínculos/hashes, executa o orçamento completo, confere
pesos/ator e salvamento/recarga e escreve `trained_awaiting_validation`.
Não construir `ValidationContext` nessa primeira chamada: ele carrega anchors
de validação e é necessário somente na fase de avaliação futura.

O launcher deve conferir o manifesto de inputs finalizado, copiar o protocolo
de origem para proveniência, gravar o candidato/orçamento e os hashes antes
de iniciar, e recusar saída já existente. Executar com `nohup` e limite de
três horas; heartbeat a cada 30 segundos informa vida do processo, não
quantidade de passos. A desconexão SSH mantém a execução. Falha/interrupção
não autoriza uso de um checkpoint incompleto em seleção.

Saída proposta: `results/ws02_first_tuning_v1/PPO_w128_lr1e-4_seed0/`.
O início/conclusão dessa execução ainda não foram confirmados pelo usuário.
Os logs e relatórios devem permanecer identificados como treino aguardando
validação; não equivalem a modelo escolhido ou resultado final de pesquisa.

O launcher está implementado em `rl_boleta.first_tuning`, usando o `train_job`
existente. Três testes específicos verificam orçamento/configuração, manutenção
dos flags de acesso e seleção, recusa de inputs não verificados, registro de
falha e preservação de execução existente. Publicar o commit da branch e dar
`git pull --ff-only` na workstation antes de iniciar o módulo.

```bash
cd "$HOME/ailab/rl-stock"
git pull --ff-only
mkdir -p results/ws02_first_tuning_v1
nohup timeout 10800s env PYTHONNOUSERSITE=1 \
  "$HOME/venvs/rl-stock-ws02/bin/python" -u \
  -m rl_boleta.first_tuning \
  >> results/ws02_first_tuning_v1/training.log 2>&1 &
echo $! > results/ws02_first_tuning_v1/process.pid
```

O PID registrado é do supervisor `timeout`; `launch.json` registra o PID do
worker Python. Conferir `training.log` depois do lançamento para confirmar
`training_in_progress`. O heartbeat indica que o worker está vivo; a conclusão
é registrada em `launch.json` como `trained_awaiting_validation` ou falha.

## Etapas seguintes e bloqueios preservados

Revisar o primeiro ajuste e registrar seu manifest/checkpoint; integrar o plano
ao executor de seleção sem editar os bundles originais. Consolidar os novos
protocolos de pesquisa com evidência de preparação e verificação, vinculados
aos mesmos controles econômicos e datas. O metadata antigo de revisão ainda
contém status pendente: o seletor `--mode protocol` continua bloqueado até
essa vinculação explícita. O primeiro ajuste de treino não altera esse gate.

Na seleção, cada candidato deve completar todas as datas de validação do seu
cenário e todas as três seeds em caixa, com retorno realizado finito. Falhas
ficam reportadas, sem retirar datas; maximizar retorno realizado médio entre
admissíveis, com desempates congelados. Sem candidato admissível, não realizar
o reajuste final correspondente. Variantes exigem seus próprios executores.

Após seleção, implementar/verificar normalizadores train+validation, reajustes
finais e avaliação congelada nas datas de teste comuns. Esses executores e a
consolidação metodológica integral permanecem pendentes. O plano operacional
permite iniciar o primeiro candidato sem liberar antecipadamente essas fases.
