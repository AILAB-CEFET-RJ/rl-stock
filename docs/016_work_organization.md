# Organização do trabalho antes de separar a coleta

> Registro **016** · Data de referência: **2026-10-11** · [Índice](README.md)
> Anterior: [Registro 015](015_gap_causes_audit.md) · Seguinte: [Registro 017](017_protocol_alternatives_audit.md)

A branch `fix/data-pipeline-audit` acumulou frentes diferentes. A organização em commits
segue a sequência abaixo, preservando as dependências. Nenhuma nova branch
foi criada nesta etapa:

1. **Regras de versionamento:** preservar exclusões de dados, resultados e paper;
   permitir somente os dois protocolos JSON necessários ao código.
2. **Formulação e protocolo:** escrutínio conceitual, registro das revisões do
   manuscrito e protocolos v1/v2, incluindo o desenho por pregão.
3. **Preparação e auditoria dos dados:** validação de snapshots, reconstrução
   dos Parquet, calendário congelado, dependências e testes correspondentes.
4. **Simulação econômica por pregão:** execução, contabilidade, encerramento
   diário, replay e bloqueio do ambiente legado.
5. **Observações e treinamento sintético:** normalização, adaptador Gymnasium,
   configurações PPO/A2C/SAC/DDPG, dependências e testes.
6. **Cobertura e relógios:** manifestos de episódios, atribuição das lacunas,
   auditoria das transições de fuso e conclusões sobre o acervo histórico.
7. **Coleta prospectiva:** coletor, requisitos, testes, integração sintética
   com navegador, documentação e diagnóstico do piloto intradiário.

O último commit reúne a implementação da coleta para facilitar sua transferência
posterior à branch `feat/prospective-cboe-collection`. Ele depende do pipeline
de snapshots já consolidado. A reorganização não altera os dados históricos,
os manifestos dos experimentos ou os resultados dos pilotos.

## O que fica fora dos commits

- `data/`, `results/`, `logs/` e `models/`: continuam ignorados.
- `paper/`: continua ignorado conforme a configuração existente, incluindo
  manuscrito, bibliografia, template, PDF e arquivos de revisão. Os documentos
  em `docs/` registram as revisões, mas não substituem o manuscrito local.
- JSON de saída, ambientes locais e caches: continuam ignorados. As únicas
  exceções JSON são `configs/experimental_protocol_v1.json` e
  `configs/experimental_protocol_v2.json`.

Os 136 testes passaram antes da organização; não houve alteração funcional
nesta etapa. Dados, resultados e paper permaneceram fora dos commits, sem
uso de `git add --force`. A separação da coleta em outra branch ainda está
pendente; a nova branch não foi criada.
