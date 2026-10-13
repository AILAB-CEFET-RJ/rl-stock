# Grade histórica parcial e baselines v3

> Registro **022** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 021](021_masked_training.md) · Seguinte: [Registro 023](023_gap_rule_and_conditional_eligibility.md)

Esta etapa implementa preparação diagnóstica da grade histórica e políticas
comparáveis ao agente v3. Não libera treinamento histórico nem produz resultados
financeiros sobre março–julho de 2025. O protocolo permanece um rascunho com
regra para lacunas longas e elegibilidade final pendentes.

## Preparação da grade

`rl_boleta.masked_preparation` usa os snapshots canônicos reconstruídos dos
Parquet auditados, não os CSVs processados ou resultados da dissertação.
Verifica hashes dos originais, conversão canônica e auditoria de lacunas;
revalida snapshots com os mesmos critérios de qualidade. Não relaxa spread,
distância dos níveis, profundidade, quantidade de negócios ou idade máxima.
Uma falha de revalidação aborta a preparação, sem reparar o snapshot ou
transformá-lo silenciosamente em uma lacuna comum.

Para cada minuto necessário de cada pregão, seleciona por ativo o último
snapshot aceito recebido desde a abertura, com idade de até 60 segundos.
Não consulta capturas futuras nem interpola. A grade mantém os minutos
sem ativos disponíveis e todos os pregões sem arquivo. Cada célula aceita
referencia a identidade original da captura; reler a mesma identidade não
reabastece a profundidade consumida pelo simulador.

A disponibilidade de cada célula é comparada com `asset_grid.csv.gz` da
auditoria anterior. Qualquer divergência impede um manifesto concluído.
São produzidos arquivos de referências comprimidos por data e um manifesto
com início causal, margem até a saída, cobertura terminal, lacunas por ativo,
partições, proveniência e `training_ready=False`. Esses diagnósticos são
metadados separados; não aparecem nas observações da política.

A fonte canônica ainda registra uma estimativa antiga de atraso de 10.800
segundos. Esse registro é preservado como `adapter_timing_metadata`, mas
**não é aplicado ao alinhamento**. `effective_timing` registra atraso fixo
não estabelecido e nenhuma subtração. A grade usa recebimento das capturas,
com as hipóteses de fuso auditadas, e não certifica o horário de mercado do livro.

```sh
caffeinate -i /Users/ebezerra/miniconda3/bin/python3 \
  -m rl_boleta.masked_preparation \
  --adapter-dir results/session_coverage_2026-10-08/canonical \
  --protocol configs/experimental_protocol_v3.json \
  --audit-dir results/gap_causes_2026-10-08 \
  --output-dir results/v3_partial_grid_verified_2026-10-12
```

O diretório de saída deve ser novo. A preparação limita a memória aos snapshots
e livros de um dia, além das máscaras da auditoria. Não depende de Gym, Torch,
pandas ou leitura direta de Parquet nesta etapa.

`read_prepared_session(directory, day)` verifica os hashes, revalida os
snapshots e confirma que as referências gravadas correspondem à seleção
causal. Retorna `MaskedMarketSession(..., synthetic=False)`: o normalizador
e o treinador sintéticos recusam essa entrada. O artefato referencia os
arquivos canônicos por caminhos absolutos; conserve-os com seus manifestos.
As referências não são um dataset autossuficiente para transportar isoladamente.

## Baselines comparáveis

`rl_boleta.masked_baselines.BaselinePolicy` recebe a mesma observação causal do
agente e emite a mesma ação por ativo. O controlador aplica taxas, caixa
compartilhado, profundidade, participação, máscaras, execução no minuto seguinte,
parada econômica e saída diária a todas as estratégias.

| Política | Intenção nos intervalos discricionários |
|---|---|
| Caixa | Zero em todos os ativos |
| Entrada com alocação igualitária | Um em todos os ativos na primeira decisão; zero depois |
| Momentum de dez minutos | Sinal da variação do midpoint entre os dois extremos exatos |
| Reversão | Negativo do sinal de momentum |
| Aleatória | Componentes independentes uniformes em [-1, 1], sementes 100–109 |

A entrada igualitária faz uma tentativa única. Não repete ordens canceladas
por ausência na execução, nem garante pesos realizados iguais. Momentum e
reversão enviam zero para um ativo se qualquer extremo estiver indisponível;
não usam marcas mantidas durante lacunas como cotações dos extremos.

Cada semente aleatória define um fluxo contínuo por trajetória cronológica de
datas, consumido somente nas decisões discricionárias. Uma nova política de
entrada é criada por pregão, mas o gerador aleatório não reinicia a cada dia.
Intervalos de stop ou liquidação não chamam a política.

`run_synthetic_suite` admite exclusivamente sessões declaradas sintéticas,
conserva datas ausentes e todos os desfechos, inclusive resíduos. Verifica que
os indicadores de cobertura e os denominadores são iguais entre métodos.
Seu comando não aceita dados históricos:

```sh
caffeinate -i /Users/ebezerra/miniconda3/bin/python3 \
  -m rl_boleta.masked_baselines --synthetic-smoke \
  --output-dir results/v3_baselines_synthetic_verified_2026-10-12
```

São quatro políticas determinísticas e dez trajetórias aleatórias, cada uma
em três dias artificiais com 18 ativos e lacunas. Os retornos nos rastros são
exemplos de integração sintética; não são evidência de desempenho financeiro.
A preparação histórica não executa nenhuma dessas políticas.

## Resultado e verificações de 12/10/2026

A grade final reproduziu a disponibilidade por ativo em todos os 105 pregões
e as decisões de cobertura da auditoria anterior:

| Partição | Pregões programados | Início causal viável | Candidatos com saída coberta |
|---|---:|---:|---:|
| Treino | 63 | 53 | 50 |
| Validação | 20 | 15 | 15 |
| Teste | 22 | 14 | 14 |

Foram preservados 13 pregões sem arquivo. Os arquivos de 19/06 e 04/07,
datas fechadas, ficaram registrados separadamente e não viraram episódios.
**Os 79 candidatos continuam provisórios**, sem liberação para treinamento.

A regressão completa passou: **190 testes, sem falhas ou testes pulados**.
Os 12 testes novos cobrem seleção causal, limite de idade, ausência de
carry entre pregões, revalidação de qualidade, partições, hashes, células que
divergem da auditoria, bloqueio de fitting histórico, entrada única, sinais
de momentum/reversão, fluxo aleatório, datas ausentes e liquidação com resíduos.

O smoke dos baselines executou 14 trajetórias de três dias: 42 episódios
sintéticos, todos com saída programada em caixa, 367 transições e cobertura
comum. Isso verifica integração, não desempenho ou capacidade real de liquidação.
Hashes de código, entradas e saídas foram conferidos. O leitor foi exercitado
em março, junho e no pregão curto de julho, devolvendo 389, 389 e 209 pontos,
respectivamente; o gate de normalização histórica recusou todos.

Artefatos finais locais:

- `results/v3_partial_grid_verified_2026-10-12/manifest.json`
- `results/v3_baselines_synthetic_verified_2026-10-12/manifest.json`

Os diretórios sem `verified` preservam as execuções anteriores às verificações
adicionais de proveniência e metadados. Use os artefatos finais acima. Resultados
permanecem ignorados pelo Git.

## Próximo passo

Concluir a regra para lacunas longas com justificativa de observação e risco,
congelar o manifesto final e verificar os critérios de viabilidade por partição.
Só então liberar ajuste do normalizador e treinos históricos. Cobertura na
saída não garante liquidação completa; falhas econômicas precisam continuar
nos resultados, sem seleção de estratégias que terminaram em caixa.

## Atualização: seleção condicional de datas

A [regra de lacunas e a elegibilidade condicional](023_gap_rule_and_conditional_eligibility.md)
foram congeladas no rascunho v3 na etapa seguinte. A regra principal não
acrescenta exclusão por duração; limites predefinidos são sensibilidades dos
mesmos modelos congelados. A seleção contém 50/15/14 dias e 65 de reajuste final.
Normalização e fitting históricos continuam pendentes. Os relatos de pendências
acima descrevem o estado na conclusão original desta etapa.
