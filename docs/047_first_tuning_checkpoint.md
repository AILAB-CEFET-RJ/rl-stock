# Primeiro ajuste PPO completo e checkpoint copiado ao Mac

> Registro **047** · Data de referência: **2026-10-13** · [Índice](README.md)
> Anterior: [Registro 046](046_cuda_campaign_plan.md) · Seguinte: [Registro 048](048_first_checkpoint_validation.md).

O usuário confirmou o término do primeiro ajuste na workstation02, com
`trained_awaiting_validation`, e copiou `model.zip`, `normalizer.json` e
`report.json` para `results/workstation02_first_tuning/` no Mac.

Configuração: PPO, `cash_settled/all_gaps`, largura 128, LR 1e-4, seed 0,
CUDA, orçamento solicitado 500.000 passos e realizado 501.760. O excesso
de 1.760 passos completa o último rollout de 2.048, dentro do limite previsto.
O launcher reportou commit `20f96ac7fe00ac92cfe6afedfca8cf3b44d0539b` e
acesso a preços de validação/teste falso. O modelo ainda não está selecionado
e `eligible_for_final_refit` permanece falso.

No Mac foram verificados os SHA-256 de modelo e normalizador contra
`artifacts_sha256` do relatório copiado: ambos coincidem. O relatório confirma
`actor_updated=true` e `checkpoint_prediction_identical=true`, verificações
realizadas na workstation com recarga no mesmo backend CUDA.

O normalizador copiado declara partição treino, cenário `all_gaps`, origem
histórica (`synthetic_only=false`) e 50 datas. Seus metadados coincidem exatamente
com a referência portátil original, e médias/escalas coincidem com a tolerância
registrada em 043 (`rtol=1e-14`, `atol=1e-15`). O vínculo de elegibilidade é
`56e17f2cd0152017429b021f5557d164374a671877b21dc08bc9ee43eabffa46`.

Essa conferência não executou inferência/avaliação no Mac nem reproduziu todos
os vínculos absolutos da workstation. Os resultados de validação ainda precisam
ser produzidos no destino com o checkpoint congelado, os inputs originais e
os registros completos de liquidação. Uma seed desse candidato não basta para
seleção: o desenho requer as três seeds e as demais configurações registradas.
O reajuste final e o teste continuam pendentes e bloqueados.
