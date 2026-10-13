# Testes na workstation02 e preparação da transferência dos Parquet

> Registro **038** · Data de referência: **2026-10-13** · [Índice](README.md)
> Anterior: [Registro 037](037_workstation02_cuda_and_storage.md) · Seguinte: [Registro 039](039_workstation02_canonical_rebuild.md).

O usuário copiou o código de trabalho para a workstation02 e enviou o resumo
da suíte: **260 testes em 37,172 segundos, OK**. O ambiente de treinamento
registrado em 037 passou nessa execução. Não houve treinamento histórico
na workstation, benchmark da campanha ou autorização de seleção completa.
Os testes unitários não equivalem a experimentos com as datas históricas.

## Arquivos brutos selecionados para transferência

Foi preparado no Mac `results/workstation02_transfer_2026-10-13/`, com lista
de arquivos, checksums SHA-256 e manifesto de inventário. A seleção usa as
entradas do adaptador congelado
`results/session_coverage_2026-10-08/canonical/manifest.json`, empregado pela
grade v3 verificada. São **94 Parquet**, totalizando **116.776.847 bytes**
(111,4 MiB), e não a pasta inteira de dados recebidos de Fernando.

Todos os 94 hashes locais foram conferidos contra o adaptador antes de produzir
o inventário. O inventário usa caminhos relativos à raiz do projeto para a
transferência e checagem remotas. O hash do manifesto original e seus caminhos
do Mac ficam preservados como evidência da origem; ele não foi reescrito.

A transferência e a conferência SHA-256 dos 94 arquivos na workstation foram
confirmadas pelo usuário em 13/10/2026: todos OK. Nenhum dado foi enviado
pelo agente. Essa etapa copia arquivos e confere identidade de
bytes, sem avaliar retornos ou ajustar estatísticas. Não é revalidação dos
Parquet com a versão remota do PyArrow.

## Pendências para treinamento histórico remoto

Os manifestos, normalizadores e referências de sessões ainda dependem dos
caminhos absolutos originais do Mac. Após confirmar a cópia bruta, preparar
novos vínculos portáveis ou regenerar os derivados no destino, preservando
os artefatos congelados e verificando equivalência de datas, grade e estatísticas.
Não substituir caminhos indiscriminadamente dentro dos artefatos originais:
seus hashes e vínculos entre etapas precisam continuar verificáveis.

Continuam pendentes a escolha explícita CPU/CUDA no pipeline, os testes
históricos remotos dos dois regimes e a medição de tempo/RAM/VRAM com orçamento
completo. Os experimentos de seleção e o reajuste final continuam bloqueados.
