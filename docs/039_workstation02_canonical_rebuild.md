# Reconstrução canônica com caminhos da workstation02

> Registro **039** · Data de referência: **2026-10-13** · [Índice](README.md)
> Anterior: [Registro 038](038_workstation02_tests_and_raw_transfer.md) · Seguinte: [Registro 040](040_v3_branch_integration.md).

Após confirmar os hashes brutos remotos, foi implementado
`rl_boleta.workstation_adapter` para reconstruir a saída do adaptador em uma
nova raiz. A etapa não modifica os Parquet nem os manifestos antigos, e não
produz políticas, normalizadores ou autorização para a campanha completa.

## Referência de equivalência

O comando `export` confere hashes dos arquivos brutos e derivados originais,
preserva o manifesto produtor byte a byte e exporta uma referência com caminhos
brutos relativos, configuração, metadados de relógio, contagens por arquivo e
hashes do conteúdo de cada arquivo de capturas e da tabela de rejeições.

A assinatura inclui todos os campos das capturas: preços, quantidades,
horários, IDs, hashes brutos e proveniência. Só o campo `source_file` é reduzido
ao nome do arquivo, para permitir mudança de diretório. A assinatura usa o
conteúdo descompactado, evitando diferenças de cabeçalho gzip e horário de
criação. As linhas de rejeição recebem a mesma exceção limitada ao diretório
de origem. A ordem das linhas continua participando da comparação.

`rebuild` exige hashes do código produtor iguais aos do adaptador original,
conserva todas as configurações e hipóteses de fuso/atraso, verifica os Parquet
no destino e converte novamente com o Pandas/PyArrow disponíveis ali. Só
registra `canonical_rebuild_verified` após comparar integralmente a referência.
Dados diferentes, caminhos fora de `data/`, hashes incorretos e saída já
existente são recusados. Diferenças numéricas não recebem tolerância automática.

## Artefatos e comandos

Referência local preparada para transferência:
`results/workstation02_transfer_2026-10-13/canonical_reference/`.
O exportador verificou integralmente **700.273 capturas aceitas** e
**77.615 linhas de rejeição** nos 94 Parquet. Os artefatos canônicos originais
ocupam cerca de 120 MiB compactados; os derivados reconstruídos terão nova
proveniência de diretório e novos hashes de arquivo.
Saída remota proposta: `results/ws02_canonical_2026-10-13/`.

```sh
env PYTHONNOUSERSITE=1 "$HOME/venvs/rl-stock-ws02/bin/python" \
  -m rl_boleta.workstation_adapter rebuild \
  --reference-dir results/workstation02_transfer_2026-10-13/canonical_reference \
  --project-root . --output-dir results/ws02_canonical_2026-10-13
```

Cada Parquet concluído gera uma mensagem de progresso. A saída mantém o
manifesto usual do adaptador; a confirmação de equivalência fica em
`relocation_report.json`. Reexecução requer outra pasta de saída; uma tentativa
interrompida ou falha permanece preservada para diagnóstico.

## Verificação e pendências

Os testes novos cobrem reconstrução em outra raiz com captura aceita e rejeitada,
preservação da origem, recusa de dados alterados, divergência semântica,
proteção de saída existente e tentativa de escapar da pasta de dados.
Uma divergência semântica marca o novo manifesto como
`relocation_verification_failed`, impedindo seu consumo pelas etapas existentes.
Após recompor o ambiente temporário, a suíte local passou com **266 testes em
104,218 segundos**, sem falhas ou testes pulados. A proteção adicional do
manifesto foi conferida depois com os seis testes específicos do adaptador,
também sem falhas. Os hashes do bundle de referência foram reconferidos.
A verificação remota dos dados canônicos completos ainda está pendente.

A primeira tentativa de regressão local encontrou os diretórios de dependências
temporárias incompletos (sem os módulos NumPy/Gymnasium/SB3 efetivos); a instalação
base carregava NumPy 2.3.1, incompatível com o PyTorch 2.2.2 do Mac, e faltava
Matplotlib para importar o SB3. Foram recriadas apenas as dependências auxiliares em
`/private/tmp/rl-stock-training-deps-20261013`, com as mesmas versões fixadas,
sem alterar o ambiente `ailab`. Esse incidente não muda os 260 testes já
confirmados pelo usuário na workstation nem a integridade dos Parquet.

Os próximos derivados são a grade causal, elegibilidade dos dois cenários e
normalizadores de treino dos dois regimes. Sua equivalência ainda precisa ser
conferida; sucesso no adaptador não torna o treinamento histórico executável
por si só. Permanecem pendentes a configuração CPU/CUDA no pipeline e as
medições de tempo/RAM/VRAM da campanha completa.
