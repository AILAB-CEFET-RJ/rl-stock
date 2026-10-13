# Perfis de conta e manifestos de datas na workstation02

> Registro **043** · Data de referência: **2026-10-13** · [Índice](README.md)
> Anterior: [Registro 042](042_workstation02_partial_grid.md) · Seguinte: [Registro 044](044_workstation02_historical_smoke.md).

O usuário confirmou a execução de `rl_boleta.account_campaigns` sobre a grade
parcial e o diagnóstico de lacunas reconstruídos no destino, usando a cópia
congelada do protocolo de preparação. A saída é
`results/ws02_account_campaign_inputs_2026-10-13/`.

O resumo reporta `account_profiles_and_date_manifests_prepared` e os regimes
`cash_settled` e `intraday_buying_power`. Cada regime possui protocolo próprio
e design para `all_gaps` e `short_gaps`; o preparador exige igualdade das datas
comuns entre regimes, sem consultar resultados financeiros. Os perfis aplicam
54 pontos de encerramento automático e `terminal_cash_utility`, mantendo a
mesma grade de observação. A seleção com orçamento completo permanece bloqueada.

## Próxima etapa

Executar `rl_boleta.historical_normalization` separadamente para o diretório
`design/` de cada regime, com `--partition train`, produzindo `normalizers/`
novos. Cada execução ajusta os dois cenários com suas próprias datas de treino.
Não reutilizar normalizadores ligados aos caminhos/hashes antigos do Mac.

As referências originais são 50 e 43 datas de treino e 14.028 e 11.842 pontos
únicos de features para `all_gaps` e `short_gaps`, respectivamente. A comparação
integral das datas e estatísticas numéricas ainda está pendente; igualdade de
contagens não basta para demonstrar essa equivalência.

O usuário enviou um resumo de normalização com 14.028 pontos únicos e contagens
por feature entre 13.818 e 13.866 no principal; 11.842 pontos e contagens entre
11.737 e 11.767 no secundário. Coincide com as referências, mas o resumo não
identifica a conta e não comprova conclusão de ambos os regimes.

Foi exportada no Mac a referência portátil
`results/workstation02_transfer_2026-10-13/normalization_reference.json`, após
carregar/verificar os quatro normalizadores originais pelos loaders e hashes.
Ela contém todos os campos de normalização, exceto o hash de elegibilidade
dependente do novo bundle, além das contagens únicas e por data. A comparação
remota usa `load_train_normalizer` para validar esse vínculo novo separadamente.
Não existe relaxamento de tolerância numérica ou dos critérios de seleção.
SHA-256 da referência:
`ffc11d2a661925552181c28677b9b07d21df4735d7eb1a30b227073d9199cf6d`.
Os quatro normalizadores locais foram verificados, e as estatísticas de mercado
coincidem entre contas para o mesmo cenário. A conferência remota está pendente.

A primeira comparação remota terminou com
`AssertionError: Normalização divergente: cash_settled/all_gaps`.
O hash da referência e o loader de vínculos passaram antes dessa comparação.
Ainda não sabemos se a diferença está em metadados, datas/contagens ou nos
valores numéricos. Foi solicitado diagnóstico por campo; nenhuma tolerância
foi relaxada e a equivalência dos quatro bundles não foi confirmada. Não
avançar para a promoção dos inputs antes de explicar essa divergência.

## Diagnóstico e critério de equivalência numérica

O diagnóstico remoto de `cash_settled/all_gaps` confirmou igualdade exata de
datas, ordem de features/ativos, contagens, pontos únicos, pontos por sessão e
demais metadados. Cinco médias diferem, com máximo absoluto
8,8817841970012523e-16; 31 escalas diferem, com máximo
4,4408920985006262e-16. As maiores diferenças reportadas pertencem a features
de tamanho de negócio transformadas por `math.log1p`; as escalas usam
`math.sqrt` sobre momentos acumulados. Esses valores são compatíveis com
arredondamento float64 entre sistemas; a operação originária não foi isolada.

A checagem inicial de identidade numérica bit a bit é substituída por uma
comparação documentada exclusivamente de `means` e `scales`, com
`rtol=1e-14`, `atol=1e-15`, `equal_nan=False`, conforme
[NumPy assert_allclose](https://numpy.org/doc/1.26/reference/generated/numpy.testing.assert_allclose.html).
O limite por valor é `atol + rtol * abs(reference)`. Datas, contagens,
metadados, hash da referência e vínculos dos novos bundles continuam exatos.
Os arquivos de normalização não são arredondados nem reescritos. Essa exceção
de reprodução numérica não altera tolerâncias de qualidade, idade, lacunas,
liquidação ou seleção, e não garante identidade bit a bit de observações
normalizadas ou de treinamentos entre dispositivos.

É necessário executar a comparação dos quatro bundles com esse critério antes
de confirmar equivalência remota. A comparação entre contas na mesma máquina
do finalizador continua usando igualdade exata de estatísticas.

O usuário confirmou as quatro comparações remotas: `cash_settled/all_gaps`,
`cash_settled/short_gaps`, `intraday_buying_power/all_gaps` e
`intraday_buying_power/short_gaps`, todas com `equivalência verificada`.
Assim, os quatro loaders validaram os vínculos locais, a referência passou
no SHA-256 esperado, as datas/metadados/contagens coincidem exatamente e
médias/escalas coincidem dentro da tolerância registrada. Isso não demonstra
reprodutibilidade bit a bit dos futuros agentes.

Próxima execução solicitada: `historical_profile_verification` para cada regime,
com seus normalizadores novos e saídas `train_probes/`, sequencialmente. Esses
probes são roteiros econômicos fixos em datas de treino, sem ajuste de políticas;
devem conferir caixa, posições, capacidade de compra, observações e recompensa.
O usuário confirmou conclusão dos dois regimes: seis probes cada, todos
`scheduled_end`, `flat=true`, e zero falhas de liquidação. As datas reproduzem
o roteiro original: 03/03, 14/03 e 10/03 no principal; 03/03, 14/03 e 05/03
no secundário, todas de 2025. São 12 execuções sobre quatro datas distintas,
repetidas entre contas/cenários, sem treino de políticas ou avaliação de
retornos de modelos. O runner verificou dimensão e finitude das observações,
identidade do caixa e utilidade terminal durante essas execuções.

Próximo comando: `finalize_account_inputs` sobre a raiz dos bundles remotos,
sem `--reference-normalizer-dir` do Mac, pois esses vínculos antigos contêm
caminhos absolutos e a equivalência numérica entre máquinas já foi conferida
separadamente com a referência portátil. O finalizador mantém a comparação
exata das estatísticas entre contas no destino e verifica hashes, perfis,
normalizadores e conjunto esperado de probes. O usuário confirmou a finalização
remota com `account_profile_inputs_and_train_probes_verified` e
`total_train_probes=12`. Os perfis, normalizadores e probes passaram pelas
verificações do finalizador; isso não libera seleção com orçamento completo.

Próxima execução: treinos históricos curtos via `historical_training`, 384
passos solicitados e seed 0, para PPO/A2C/SAC/DDPG nos dois cenários de cada
regime. São 16 ajustes de integração, executados sequencialmente em CPU,
com avaliação congelada exclusivamente em exemplos de treino. A comparação
CPU/CUDA com os parâmetros completos ainda está pendente.

Os treinos curtos seguintes verificam integração e persistência de modelos;
não substituem a seleção completa, o reajuste final ou a avaliação no teste.
