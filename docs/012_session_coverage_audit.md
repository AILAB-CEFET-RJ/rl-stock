# Cobertura dos pregões e manifestos por partição

> Registro **012** · Data de referência: **2026-10-08** · [Índice](README.md)
> Anterior: [Registro 011](011_four_algorithm_integration.md) · Seguinte: [Registro 013](013_scraper_timezone_evidence.md)

A [decomposição posterior das lacunas](015_gap_causes_audit.md) reproduz exatamente
as falhas deste manifesto e distingue ausência de coleta, rejeição por qualidade
e disponibilidade conjunta dos ativos, sem alterar as regras.

Auditoria realizada em 08/10/2026, sem reutilizar CSVs processados ou resultados
financeiros da dissertação. Foram selecionados explicitamente os 94 Parquet
originais entre 3 de março e 31 de julho de 2025, preservando seus hashes.
Não houve treinamento, ajuste de normalizadores, política, execução de ordens
ou cálculo de retornos históricos. A inspeção de julho foi exclusivamente de
disponibilidade dos dados, sem consultar desempenho de modelos.

## Resultado de viabilidade

**Nenhum dos 105 pregões satisfaz o protocolo v2 sob as hipóteses temporais
registradas.** Nenhum tem todos os 21 pontos exigidos de 09:31 a 09:51 para
iniciar o episódio. Além disso, todos têm alguma lacuna posterior ao aquecimento.
Portanto, deslocar apenas o início não resolveria a exigência de cobertura até
a saída. Os mínimos de sessões avaliáveis não foram atingidos em nenhum split.

| Partição | Pregões previstos | Com arquivo | Iniciáveis | Avaliáveis | Mínimo exigido |
|---|---:|---:|---:|---:|---:|
| Treino: março–maio | 63 | 57 | 0 | 0 | 20 |
| Validação: junho | 20 | 18 | 0 | 0 | 10 |
| Teste: julho | 22 | 17 | 0 | 0 | 10 |
| Refit: março–junho | 83 | 75 | 0 | 0 | — |

O refit reúne treino e validação e não é somado novamente ao total de 105.
As datas e os denominadores seguem o calendário de ações dos EUA, incluindo
o pregão curto de 3 de julho. As 13 datas sem arquivo permanecem nos denominadores.
Os arquivos de 19 de junho e 4 de julho são de datas fechadas; não viram episódios.

## Hipóteses e regras mantidas

A [inspeção do repositório local do scraper](013_scraper_timezone_evidence.md)
encontrou documentação explícita de UTC−3 e uma referência `US/Eastern` para
diagnóstico. Isso reforça as hipóteses abaixo, mas não comprova a configuração
histórica da máquina nem altera os status dos manifestos.

- Coleta: `America/Sao_Paulo`, status `hypothesis`.
- Negócios: `America/New_York`, status `hypothesis`.
- Atraso informado pelo usuário: 10.800 segundos, interpretação `unresolved`.
- Alinhamento: recebimento da captura (`available_at`), sem subtrair o atraso.
- Universo: os 18 ativos do protocolo; GE fica fora.
- Cinco níveis por lado, dez negócios, screens de spread e profundidade de
  500 bps, idade máxima de recebimento de 60 segundos.
- Sem preenchimento com dados futuros ou anteriores à abertura, interpolação,
  deslocamento do aquecimento, encurtamento do dia ou afrouxamento dos limites.

Atualização posterior: a [auditoria das mudanças de horário](014_clock_transition_audit.md)
favorece UTC−3/Nova York sem atraso adicional fixo de três horas. O relato
desse atraso foi reclassificado como lembrança não confirmada. Esta lista
descreve os manifestos originais da auditoria de cobertura, que permanecem
intactos. Como o alinhamento não subtraía as três horas, essa atualização não
remove por si só as lacunas encontradas.

A conclusão é **condicional**. Atribuições de fuso confirmadas de forma diferente
podem mudar o alinhamento. Cobertura de recebimento tampouco certifica o horário
de mercado do livro atrasado ou sua liquidez executável. Nenhum desses manifestos
é um certificado de dados prontos para treinamento histórico.

## Contagens e diagnóstico

O adaptador examinou 8.211.040 linhas em 821.104 blocos de captura. Aceitou
700.273 capturas para os ativos-alvo, rejeitou 77.615 blocos e excluiu 43.216
blocos fora do universo. O filtro de sessão deixou de usar 22.093 capturas
anteriores à abertura e 52.838 no fechamento ou depois dele.

Há 30.795 pontos conjuntos válidos entre os 40.770 pontos da grade regular.
A sequência exigida exclui somente o ponto de abertura de cada data: são
40.665 pontos obrigatórios, dos quais 30.795 válidos e 9.870 ausentes/inválidos.
Quantidade de pontos válidos não equivale a episódios completos.

| Partição | Pontos obrigatórios | Pontos conjuntos válidos |
|---|---:|---:|
| Treino | 24.507 | 19.608 |
| Validação | 7.780 | 5.986 |
| Teste | 8.378 | 5.201 |

Em 86 pregões falta o primeiro ponto de referência, às 09:31; nos outros há
alguma falha posterior dentro do aquecimento. Dezoito pregões chegam a ter
20 dos 21 pontos de aquecimento, mas não há imputação do ponto restante. O
maior trecho obrigatório contínuo tem 134 pontos, abrangendo 133 minutos.
O livro conjunto do minuto reservado à saída está disponível em 88 datas,
o que também não torna completas as respectivas trajetórias.

`missing_past_snapshot` significa ausência de captura válida anterior disponível
naquele instante, dentro da sessão, para um ativo; pode decorrer de ausência
de arquivo, início tardio ou rejeição das capturas. Não significa necessariamente
que esse ativo não foi coletado em nenhum momento do dia. `stale_snapshot`
indica que a última captura válida ultrapassa os 60 segundos. Em pontos exigidos,
foram registradas 119.486 falhas do primeiro tipo e 16.627 do segundo, contadas
por ativo e ponto; um único ponto conjunto pode ter várias falhas.

## Artefatos e reprodução

Diretório: `results/session_coverage_2026-10-08/`.

| Artefato | Conteúdo |
|---|---|
| `input_selection.json` | Os 94 caminhos originais, datas e SHA-256; conjunto conferido contra a conversão |
| `canonical/manifest.json` | Contagens/rejeições, parâmetros, hipóteses de relógio, hashes e caminhos das entradas originais |
| `canonical/*.jsonl.gz` | Capturas reconstruídas, com os livros/negócios completos e proveniência |
| `episodes/manifest.json` | Resumo integral, `coverage_feasible=false`, `training_ready=false`, hashes e limitações |
| `episodes/train.json`, `validation.json`, `test.json`, `final_refit.json` | Limites, resumos e registros de cada pregão por partição |
| `episodes/sessions.csv` | Cobertura, aquecimento, saída, primeiras falhas e horizonte de cada pregão |
| `episodes/required_failures.csv` | Cada ponto obrigatório sem cobertura e motivos por ativo |
| `episodes/alignment_trace.jsonl.gz` | IDs e horários das capturas selecionadas em cada ponto válido, para reproduzir o alinhamento |
| `diagnostics.json` | Agregações explicativas, vinculadas ao hash do manifesto integral |

Para repetir a auditoria das capturas canônicas em outro diretório:

```sh
python -m rl_boleta.episode_manifest \
  --adapter-dir results/session_coverage_2026-10-08/canonical \
  --protocol configs/experimental_protocol_v2.json \
  --output-dir results/session_coverage_nova
```

Para reconstruir novamente as capturas, usar a lista explícita de
`input_selection.json` com `parquet_adapter.convert`, configuração de 18 ativos
e screens 500/500, e `Timing('America/Sao_Paulo', 'America/New_York')`, em novo
diretório. O adaptador já registra atraso 10.800 e status provisórios como
padrão. A reconstrução consome os Parquet originais, nunca os CSVs legados.

O auditor verifica hashes de entradas brutas, capturas canônicas e protocolo,
recusa configurações incompatíveis e diretórios existentes, e usa o mesmo
validador/alinhador do preparador. Processa uma data por vez para limitar memória.
O ponto de abertura é reportado na grade, mas sua ausência não exclui um episódio;
o aquecimento e a sequência obrigatória seguem `session_plan`.

Validação: 117 testes passaram, sem testes ignorados, no ambiente de integração
com as dependências de dados e treino. Sete novos testes cobrem dias completos,
abertura opcional, referência ausente, lacuna posterior, saída ausente, fechamento
antecipado, denominadores sem arquivo, partições, hashes e proteção contra
sobrescrita. Os hashes de todos os artefatos de episódios e dos módulos registrados
foram conferidos após a execução.

## Implicação para os próximos experimentos

O arquivo disponível não sustenta o estudo primário sob o protocolo atual e
essas hipóteses. Antes de ajustar modelos históricos, é necessário confirmar
os relógios e estabelecer uma fonte/coleta com cobertura e semântica de execução
compatíveis, ou formular uma emenda metodológica explícita antes da seleção
por desempenho. Trocar silenciosamente pregões por trechos, estender tolerâncias
ou reduzir os mínimos não resolveria a pergunta científica já registrada.
