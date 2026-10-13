# Grade parcial v3 reconstruída na workstation02

> Registro **042** · Data de referência: **2026-10-13** · [Índice](README.md)
> Anterior: [Registro 041](041_workstation02_coverage_reproduction.md) · Seguinte: [Registro 043](043_workstation02_account_inputs.md).

O usuário executou `rl_boleta.masked_preparation` sobre o adaptador canônico
e a auditoria de lacunas reconstruídos na workstation, com protocolo produtor
copiado em `results/ws02_protocols_2026-10-13/preparation_v3.json`. A saída
é `results/ws02_partial_grid_2026-10-13/`.

O resumo recebido coincide integralmente com `partition_summary` da preparação
original `results/v3_partial_grid_verified_2026-10-12/manifest.json` no Mac:

| Partição | Pregões previstos | Início causal disponível | Candidatos por cobertura |
| --- | ---: | ---: | ---: |
| Treino | 63 | 53 | 50 |
| Validação | 20 | 15 | 15 |
| Teste | 22 | 14 | 14 |

A comparação nesta etapa é do resumo. As datas admitidas nos dois cenários,
as estatísticas de normalização e os vínculos dos perfis de conta ainda
precisam ser reconstruídos/conferidos no destino. Candidatura por cobertura
não é resultado financeiro nem garantia de liquidação para qualquer política.

O preparador confere a disponibilidade de cada ativo em cada instante contra
a grade da auditoria reconstruída, preservando IDs das capturas, recebimento,
idade máxima de 60 segundos, aquecimento causal e saída programada. O protocolo
produtor copiado fica preservado para verificações futuras, mesmo que o arquivo
de trabalho em `configs/` seja alterado.

O usuário também executou `rl_boleta.gap_policy_audit` sobre essa preparação,
exclusivamente no treino, com saída
`results/ws02_train_gap_diagnostics_2026-10-13/`. O resumo recebido reproduz
o diagnóstico original do Mac: 50 candidatos; maior lacuna de 34 pontos de
grade; 33, 43, 47, 49 e 49 pregões mantidos pelos limites 1, 2, 5, 15 e 30;
maior variação absoluta entre endpoints observados de 0,026720508634762438.
Essa última medida não representa extremos dentro da lacuna nem limite de
perda. O diagnóstico alimenta os manifestos dos cenários `all_gaps` e
`short_gaps`. O limite de duas ausências
consecutivas na grade do segundo cenário já foi definido; esse diagnóstico
não escolhe um novo limite usando validação, teste ou retornos.

Próximo passo: reconstruir os perfis dos dois regimes via `account_campaigns`, ajustar
seus normalizadores exclusivamente de treino e executar os probes. O treinamento
com orçamento completo e o reajuste final continuam bloqueados.
