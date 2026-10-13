# Índice do trabalho e documentação

Os registros numerados organizam a sequência reconstruída de revisão, auditoria e implementação. O número identifica a entrada inicial do assunto; atualizações posteriores no mesmo arquivo não mudam seu ID.

A sequência usa as dependências declaradas nos documentos, as datas registradas no texto/artefatos e o histórico do Git. Os commits de 11/10/2026 reuniram etapas descritas como realizadas em 08/10; dentro desses lotes, a ordem é uma reconstrução editorial, sem precisão de horário. O registro 016 usa a data do commit. Os registros de 12/10 incluem trabalho ainda não commitado. Datas de modificação do filesystem não foram usadas como cronologia.

Cada registro oferece links para o índice, a entrada anterior e a seguinte. A numeração cobre os documentos desta branch; não pretende incluir registros de outras branches que não estão presentes aqui.

## Registros de etapas

A coluna “Nome anterior” permite localizar referências preservadas em protocolos e artefatos congelados. Esses artefatos não foram reescritos para atualizar caminhos de documentação.

| ID | Data de referência | Registro | Nome anterior |
| --- | --- | --- | --- |
| 001 | 2026-10-08 | [Auditoria dos Parquet brutos — 08/10/2026](001_raw_data_audit.md) | `raw_data_audit.md` |
| 002 | 2026-10-08 | [Escrutínio da formulação do paper — 08/10/2026](002_paper_conceptual_review.md) | `paper_conceptual_review.md` |
| 003 | 2026-10-08 | [Incorporação da revisão ao paper — etapas 1–3](003_paper_revision_steps_1_3.md) | `paper_revision_steps_1_3.md` |
| 004 | 2026-10-08 | [Revisão do paper — etapa 4: dados](004_paper_revision_stage_4.md) | `paper_revision_stage_4.md` |
| 005 | 2026-10-08 | [Revisão do paper — etapa 5: protocolo experimental](005_paper_revision_stage_5.md) | `paper_revision_stage_5.md` |
| 006 | 2026-10-08 | [Núcleo econômico: implementação e validação sintética](006_economic_kernel.md) | `economic_kernel.md` |
| 007 | 2026-10-08 | [Revisão do protocolo: um episódio por pregão](007_protocol_day_trading_revision.md) | `protocol_day_trading_revision.md` |
| 008 | 2026-10-08 | [Auditoria da duração dos episódios no pipeline legado](008_legacy_episode_audit.md) | `legacy_episode_audit.md` |
| 009 | 2026-10-08 | [Controlador de episódios por pregão](009_session_replay.md) | `session_replay.md` |
| 010 | 2026-10-08 | [Observações causais e integração inicial com PPO](010_observations_and_training.md) | `observations_and_training.md` |
| 011 | 2026-10-08 | [Integração de PPO, A2C, SAC e DDPG](011_four_algorithm_integration.md) | `four_algorithm_integration.md` |
| 012 | 2026-10-08 | [Cobertura dos pregões e manifestos por partição](012_session_coverage_audit.md) | `session_coverage_audit.md` |
| 013 | 2026-10-08 | [Evidências locais sobre os fusos do scraper](013_scraper_timezone_evidence.md) | `scraper_timezone_evidence.md` |
| 014 | 2026-10-08 | [Auditoria dos relógios nas mudanças do horário americano](014_clock_transition_audit.md) | `clock_transition_audit.md` |
| 015 | 2026-10-08 | [Causas das lacunas de cobertura](015_gap_causes_audit.md) | `gap_causes_audit.md` |
| 016 | 2026-10-11 | [Organização do trabalho antes de separar a coleta](016_work_organization.md) | `work_organization.md` |
| 017 | 2026-10-12 | [Alternativas de cobertura mantendo uma carteira por dia](017_protocol_alternatives_audit.md) | `protocol_alternatives_audit.md` |
| 018 | 2026-10-12 | [Proposta de protocolo v3: observações incompletas e encerramento diário](018_protocol_v3_proposal.md) | `protocol_v3_proposal.md` |
| 019 | 2026-10-12 | [Núcleo econômico e controlador diário v3](019_missing_data_core.md) | `missing_data_core.md` |
| 020 | 2026-10-12 | [Observações mascaradas e normalização v3](020_masked_observations.md) | `masked_observations.md` |
| 021 | 2026-10-12 | [Integração sintética v3 com Gymnasium e quatro algoritmos](021_masked_training.md) | `masked_training.md` |
| 022 | 2026-10-12 | [Grade histórica parcial e baselines v3](022_masked_preparation_and_baselines.md) | `masked_preparation_and_baselines.md` |
| 023 | 2026-10-12 | [Regra de lacunas e elegibilidade condicional v3](023_gap_rule_and_conditional_eligibility.md) | `gap_rule_and_conditional_eligibility.md` |
| 024 | 2026-10-12 | [Dois cenários com treinamentos independentes](024_two_scenario_experiments.md) | `two_scenario_experiments.md` |
| 025 | 2026-10-12 | [Normalização histórica de treino por cenário](025_historical_normalization.md) | `historical_normalization.md` |
| 026 | 2026-10-12 | [Integração histórica curta dos dois cenários](026_historical_training_integration.md) | `historical_training_integration.md` |
| 027 | 2026-10-12 | [Executor de seleção por validação v3](027_validation_selection.md) | `validation_selection.md` |
| 028 | 2026-10-12 | [Revisão do objetivo e da admissibilidade para day trading](028_day_trading_admissibility_review.md) | `day_trading_admissibility_review.md` |
| 029 | 2026-10-12 | [Capacidade observada de encerramento nas datas de treino](029_exit_capacity_audit.md) | `exit_capacity_audit.md` |
| 030 | 2026-10-12 | [Fase de encerramento com vendas sucessivas](030_wind_down_implementation.md) | `wind_down_implementation.md` |
| 031 | 2026-10-12 | [Objetivo de aprendizagem para encerramento em caixa](031_terminal_cash_utility.md) | `terminal_cash_utility.md` |
| 032 | 2026-10-12 | [Regimes de conta configuráveis no pipeline v3](032_account_regimes.md) | `account_regimes.md` |
| 033 | 2026-10-12 | [Novos vínculos históricos por regime de conta](033_account_campaign_inputs.md) | `account_campaign_inputs.md` |
| 034 | 2026-10-12 | [Treinos históricos curtos com os novos regimes](034_historical_smoke_new_accounts.md) | `historical_smoke_new_accounts.md` |
| 035 | 2026-10-12 | [Organização e numeração dos registros](035_docs_log_refactor.md) | — |
| 036 | 2026-10-12 | [Inventário inicial da workstation02](036_workstation02_inventory.md) | — |
| 037 | 2026-10-12 | [Verificação inicial de CUDA e armazenamento](037_workstation02_cuda_and_storage.md) | — |
| 038 | 2026-10-13 | [Testes na workstation02 e transferência dos Parquet](038_workstation02_tests_and_raw_transfer.md) | — |
| 039 | 2026-10-13 | [Reconstrução canônica com caminhos da workstation02](039_workstation02_canonical_rebuild.md) | — |
| 040 | 2026-10-13 | [Consolidação da branch do pipeline v3](040_v3_branch_integration.md) | — |

## Guias com nomes estáveis

- [Preparação dos dados](data_pipeline.md): manual operacional do pipeline revisado; consultar os registros para o estado de cada etapa.
- Documentação legada preservada: [visão geral](main.md), [modelo](rl_model.md), [treinamento](training.md), [teste](testing.md) e [ablação](ablation_test.md). Esses guias descrevem o código anterior e não autorizam sua utilização no protocolo revisado.

## Como registrar novos passos

1. Acrescentar o próximo ID disponível, sem renumerar ou reutilizar IDs existentes. O próximo é **041**.
2. Criar `NNN_assunto.md` com data, propósito, resultado, verificação e pendências. Incluir links para o índice e a entrada anterior.
3. Acrescentar uma linha nesta tabela e atualizar o link “Seguinte” do último registro.
4. Em uma atualização do mesmo assunto, registrar sua data no arquivo e conservar o ID. Uma nova etapa ou emenda recebe uma entrada nova.
5. Distinguir conclusão histórica de regra vigente: apontar explicitamente o registro que substituiu uma proposta. Não apagar o histórico de falhas.
6. Atualizar referências ativas ao renomear documentos; preservar nomes e hashes dentro de datasets, resultados e outros artefatos congelados.

Os números representam sequência de registro, não versão do protocolo ou status de aprovação. O README do projeto continua como entrada para o estado corrente.
