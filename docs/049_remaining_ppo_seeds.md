# Completar as seeds do primeiro candidato PPO

> Registro **049** · Data: **2026-10-13** · [Índice](README.md)
> Anterior: [Registro 048](048_first_checkpoint_validation.md) · Seguinte: próxima entrada 050, ainda não criada.

O usuário solicitou o comando para completar as seeds 1 e 2 do candidato
PPO `cash_settled/all_gaps`, largura 128, LR 1e-4, orçamento 500.000.
O launcher `first_tuning` passou a aceitar `--seed {0,1,2}`, com seed 0 como
padrão. Cada seed exige raiz de saída própria, preservando a execução inicial.
As outras escolhas continuam congeladas. Nenhum treinamento é executado no Mac.

A execução proposta na workstation02 é sequencial e desacoplada da sessão SSH
por `nohup`: treinar uma seed em CUDA e avaliar seu checkpoint nas mesmas
datas de validação; depois repetir para a outra seed. Cada ajuste tem limite
de três horas; cada avaliação, 15 minutos. O primeiro erro interrompe a fila.
Os controles já calculados na seed 0 não precisam ser repetidos. A avaliação
continua sem acesso ao teste ou liberação do reajuste final.

Saídas sob `results/ws02_ppo_remaining_seeds_v1/`: `seed1/`, `seed2/`,
`validation_seed1/`, `validation_seed2/` e `campaign.log`. O término normal
imprime `remaining_seeds_completed`. A execução ainda depende do usuário
publicar o commit e atualizar a workstation02. Os resultados permanecem
pendentes até recebermos seus relatórios.

Verificação local: testes do launcher cobrem as duas novas seeds, destinos
distintos, orçamento e rejeição de seed fora do desenho, além dos controles
anteriores de falha e preservação de saídas.
