# Reprodução da cobertura original na workstation02

> Registro **041** · Data de referência: **2026-10-13** · [Índice](README.md)
> Anterior: [Registro 040](040_v3_branch_integration.md) · Seguinte: [Registro 042](042_workstation02_partial_grid.md).

Após a reconstrução canônica confirmada em 039, o usuário executou
`rl_boleta.episode_manifest` no clone da workstation, com o protocolo v2 e
saída `results/ws02_coverage_2026-10-13/`.

O resumo recebido coincide integralmente com `partition_summary` do manifesto
original `results/session_coverage_2026-10-08/episodes/manifest.json` no Mac,
incluindo todos os denominadores, contagens e mínimos declarados.

| Partição | Pregões previstos | Com arquivo bruto | Pontos válidos | Pontos esperados |
| --- | ---: | ---: | ---: | ---: |
| Treino | 63 | 57 | 19.608 | 24.570 |
| Validação | 20 | 18 | 5.986 | 7.800 |
| Teste | 22 | 17 | 5.201 | 8.400 |
| Reajuste final (treino + validação) | 83 | 75 | 25.594 | 32.370 |

Todas as partições continuam com zero episódios iniciáveis/avaliáveis sob o
v2. Esse resultado reproduz a limitação já identificada: a sequência conjunta
de 18 ativos exigida pelo v2, desde o aquecimento fixo até a saída, não está
disponível. Os zeros não significam falha na cópia nem descartam a proposta v3.

Essa auditoria é uma referência intermediária de disponibilidade e qualidade;
não treina modelos, ajusta normalizadores ou produz resultados financeiros.
O v3 preserva posições e representa explicitamente a indisponibilidade por
ativo, com início causal. Seus cenários e datas precisam ser reconstruídos e
conferidos nas próximas etapas antes de reutilizar os normalizadores.

O usuário também confirmou `rl_boleta.audit_gap_causes`, com saída em
`results/ws02_gap_causes_2026-10-13/`. Os três blocos recebidos (`joint_causes`,
`asset_states`, `counterfactuals`) coincidem integralmente com o manifesto
original `results/gap_causes_2026-10-08/manifest.json` no Mac. São 30.795 pontos
conjuntos válidos e 595.857 pontos válidos por ativo. As simulações com idade
120/180/300 segundos e sem filtros de qualidade permanecem diagnósticas; não
alteram a tolerância executável de 60 segundos nem os critérios de qualidade.

A grade por ativo resultante é entrada de `rl_boleta.masked_preparation`.
Próximo passo: congelar uma cópia do protocolo de preparação v3 no destino e
reconstruir a grade parcial em `results/ws02_partial_grid_2026-10-13/`. Essa
preparação foi confirmada e registrada em 042. Os orçamentos completos de seleção e
reajuste final continuam bloqueados.
