# Organização e numeração dos registros

> Registro **035** · Data de referência: **2026-10-12** · [Índice](README.md)
> Anterior: [Registro 034](034_historical_smoke_new_accounts.md) · Seguinte: [Registro 036](036_workstation02_inventory.md).

Foram numerados 34 documentos existentes que registram etapas da revisão,
auditoria e implementação, com prefixos de três dígitos. Este documento
registra a própria organização. Os títulos e resultados históricos foram
preservados, com navegação sequencial adicionada no início de cada registro.

O índice documenta a ordem reconstruída e suas limitações. As datas dos textos
ou artefatos foram usadas quando disponíveis; o registro de organização anterior
usa a data do commit. Commits que agruparam vários documentos não permitem
inferir a hora exata de execução de todas as etapas. A ordenação dentro desses
lotes segue o fluxo de trabalho e as dependências registradas.

O guia geral de dados e os cinco manuais legados mantiveram nomes estáveis.
Links relativos, README do projeto e referências ativas no protocolo/código
foram atualizados. O índice conserva a correspondência de nomes antigos para
consultar referências em artefatos congelados.

Nenhum dataset, resultado, checkpoint, normalizador ou protocolo copiado dentro
de resultados foi renomeado ou editado. Seus hashes continuam preservados.
A comparação de regras de dados agora reconhece o prefixo numérico no caminho
de documentação dos relógios como a mesma identidade de evidência. Os demais
campos de qualidade/tempo e a validação byte a byte dos produtores permanecem
protegidos; apontar outra evidência continua exigindo uma nova preparação.

Para novas etapas, usar IDs crescentes, manter a data da atualização e apontar
registros substituídos. O próximo número é 036. O índice deve ser atualizado
junto com o novo registro.

## Verificação

Foram verificados 258 links locais, sem destinos ausentes, e a sequência
contínua de IDs 001–035. As referências de documentação no protocolo ativo
apontam para arquivos existentes. Foram conferidos 44 hashes de perfis,
normalizadores, relatórios e checkpoints anteriores, todos preservados.
A regressão passou com 260 testes, sem falhas ou testes pulados, incluindo
a compatibilidade entre caminhos antigos e numerados da evidência de relógios
e a rejeição de uma mudança para outra evidência.
