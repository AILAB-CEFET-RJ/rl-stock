# Consolidação da branch do pipeline v3

> Registro **040** · Data de referência: **2026-10-13** · [Índice](README.md)
> Anterior: [Registro 039](039_workstation02_canonical_rebuild.md) · Seguinte: próxima entrada 041, ainda não criada.

O usuário solicitou fechar `feat/missing-data-day-trading-v3`, incorporar seu
conteúdo à `main` e, em seguida, clonar o repositório na workstation02.
O código de trabalho antes transferido por `rsync` passa a ser sincronizado
por Git. A versão clonada deve ser registrada por `git rev-parse HEAD` junto
dos experimentos; o ambiente Python próprio da workstation é mantido.

## Escopo consolidado

- Episódios contínuos por pregão com início causal, máscaras por ativo e
  preservação da carteira nas lacunas; execução com capacidade finita,
  marcação distinta de realização e identificação de falhas de liquidação.
- Elegibilidade e normalização exclusivamente de treino para os cenários
  `all_gaps` e `short_gaps`, com manifestos e hashes entre etapas.
- PPO, A2C, SAC e DDPG integrados ao ambiente v3; treinos históricos curtos e
  avaliação congelada com o contexto de conta corrigido.
- Fase automática de encerramento, objetivo de utilidade terminal em caixa
  e regimes `cash_settled` e `intraday_buying_power` configuráveis.
- Executor de seleção por validação com admissibilidade para day trading e
  bloqueio do reajuste final sem seleção completa autorizada.
- Documentação numerada e índice cronológico; inventário da workstation,
  confirmação de testes remotos e reconstrução canônica com verificação
  integral de equivalência, preservando os derivados antigos.

## Evidências e limites

Na workstation02 o usuário confirmou 260 testes em 37,172 segundos, antes da
adição do adaptador de reconstrução. No Mac, a suíte ampliada passou com 266
testes e os seis testes específicos da reconstrução também passaram após o
último ajuste de proteção do manifesto. A revisão final antes da integração
passou com **266 testes em 77,190 segundos**, sem testes pulados; **284 links
locais** foram conferidos sem destinos ausentes e `git diff --check` passou.
O fetch de `origin` confirmou que a main local contém a main remota e que
a branch v3 contém a main local, permitindo integração por fast-forward.

Os dados, checkpoints, resultados, inventários JSON e bundles de referência
permanecem ignorados pelo Git. O clone contém o código e a documentação para
produzi-los/verificá-los; os arquivos já copiados à workstation continuam na
pasta `~/ailab/rl-stock-ws02-20261012`, separada do futuro clone.

Essa consolidação não transforma a proposta em resultados finais. Ainda faltam
confirmar a reconstrução canônica na workstation, preparar os demais derivados
com caminhos remotos e verificar equivalência das datas/grade/normalizadores;
implementar a escolha explícita CPU/CUDA no treinador, medir orçamento completo
e executar seleção, reajuste final e avaliação. Os bloqueios da campanha
completa permanecem. A branch separada de coleta prospectiva não faz parte
desta integração.
