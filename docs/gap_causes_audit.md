# Causas das lacunas de cobertura

Auditoria dos 105 pregões de março–julho de 2025, usando os 94 Parquet
originais já selecionados, as decisões de rejeição verificadas do adaptador e
o calendário do protocolo v2. Dois arquivos pertencem a datas fechadas; há
92 pregões com arquivo e 13 sem arquivo. Não houve treinamento, cálculo de
retornos ou mudança do protocolo. A interpretação UTC−3/Nova York segue a
[auditoria dos relógios](clock_transition_audit.md).

O manifesto deste diagnóstico preserva os metadados temporais da conversão
anterior para rastreabilidade, inclusive o relato de três horas ainda marcado
como `unresolved`. Esse valor não foi aplicado ao alinhamento e não é uma
afirmação de atraso estabelecido; a auditoria dos relógios documenta a revisão
dessa informação.

## Resultado principal

**O principal obstáculo é a disponibilidade temporal da coleta, não um único
ativo problemático nem o filtro de qualidade isoladamente.** O limite de
idade de 60 segundos fica próximo demais da cadência observada para sustentar
18 ativos disponíveis durante todo o pregão.

A decomposição reproduziu exatamente as 9.870 lacunas do manifesto anterior,
sem omissões ou pontos adicionais. Dos 40.665 minutos obrigatórios conjuntos,
30.795 são válidos. Os demais têm causas exclusivas:

| Causa do minuto conjunto inválido | Minutos | Parcela das lacunas |
|---|---:|---:|
| Não existe arquivo do pregão | 5.057 | 51,24% |
| Falta captura recente para algum ativo, sem falha adicional de qualidade em outro | 4.317 | 43,74% |
| Há captura recente para todos, mas a qualidade impede algum ativo | 393 | 3,98% |
| Mistura de indisponibilidade de captura e rejeição por qualidade | 103 | 1,04% |

Nos dias com arquivo, são 4.813 lacunas: 89,69% somente por indisponibilidade,
8,17% somente por qualidade e 2,14% por ambas. “Disponibilidade conjunta”
significa que cada ativo tem uma captura passada aceita de até 60 segundos;
não exige captura no mesmo segundo e não usa dados futuros.

## O que ocorre em cada ativo

Foram classificados 731.970 pares ativo/minuto, correspondentes a 18 ativos
em todos os pontos obrigatórios:

| Estado | Pares ativo/minuto |
|---|---:|
| Captura aceita de até 60 segundos | 595.857 |
| Sem arquivo do pregão | 91.026 |
| Ainda sem captura do ativo desde a abertura | 28.371 |
| Última captura do ativo tem mais de 60 segundos | 15.876 |
| Existe captura recente, mas todas as opções recentes foram rejeitadas | 840 |

Uma captura rejeitada posterior não invalida outra captura aceita que ainda
esteja dentro dos 60 segundos. A análise inclui somente capturas desde a
abertura e anteriores ou iguais à decisão. Nenhum bloco precisou ser
descartado por falta de identificação do ativo ou timestamp de captura
utilizável nesta seleção.

A mediana, entre os pregões, do intervalo mediano de captura de cada ativo é
**57 segundos para todos os 18 ativos**. A mediana do percentil 95 diário fica
entre **62 e 66 segundos**, conforme o ativo. Há 56.551 intervalos entre
capturas consecutivas do mesmo ativo que excedem 60 segundos. Intervalos
superiores a 60 segundos nem sempre causam falha na grade, pois isso também
depende do instante da captura em relação ao minuto; os resultados acima
usam a grade real.

Dos minutos inválidos, 1.453 ainda têm 17 ativos válidos e 543 têm 16.
Contudo, os ativos faltantes variam: remover qualquer um dos 18 ativos,
individualmente, recupera **zero pregões completos**. Mesmo individualmente,
cada ativo tem apenas zero a três pregões com todos os pontos exigidos.
Não há um único ativo cuja exclusão resolva o problema.

## Qualidade e abertura

As 840 falhas ativo/minuto com captura recente rejeitada se distribuem assim:

| Motivo registrado pelo adaptador | Pares ativo/minuto |
|---|---:|
| Livro incompleto/inválido e negócios incompletos/sem horário | 443 |
| Livro incompleto/inválido | 311 |
| Negócios incompletos/sem horário | 63 |
| Nível de preço além do limite de distância do midpoint | 23 |

Nenhuma dessas falhas decorre exclusivamente do limite de spread. São
motivos das capturas recentes que impedem um ponto, não contagens de todas
as capturas rejeitadas no arquivo. A qualidade pode ter vários motivos em
um ponto; nesta execução, as quatro categorias acima não se sobrepuseram.

A abertura merece atenção separada: às 09:31, 19 pregões têm todos os ativos
válidos, 42 falham somente por qualidade, 30 somente por disponibilidade,
um por ambas e 13 não têm arquivo. Nesse primeiro ponto, MS tem rejeição
recente em 30 datas, mas a deficiência não se limita a ele. Entre os motivos
registrados no primeiro ponto por ativo, há 46 ocorrências de negócios
incompletos/sem horário e 17 de profundidade distante do midpoint.

Em todo o aquecimento, há 1.248 minutos conjuntos válidos, 601 inválidos
somente por disponibilidade, 75 somente por qualidade, oito por ambas e
273 em datas sem arquivo. Todos os pregões continuam com ao menos uma
falha no aquecimento e alguma lacuna posterior.

## Comparações diagnósticas, sem mudar o protocolo

Contagens de pregões completos caso se alterasse **apenas** a idade máxima
de uma captura já aceita, preservando abertura, aquecimento, término e
qualidade:

| Idade máxima | Treino | Validação | Teste | Total |
|---|---:|---:|---:|---:|
| 60 segundos, regra vigente | 0 | 0 | 0 | 0 |
| 120 segundos | 7 | 0 | 0 | 7 |
| 180 segundos | 14 | 0 | 2 | 16 |
| 300 segundos | 16 | 0 | 2 | 18 |

Nenhuma dessas alternativas atinge os mínimos declarados de 20/10/10
pregões para treino/validação/teste. Não se adotou nenhum desses limites:
reutilizar livros mais antigos também altera as hipóteses de observação e
execução, e uma melhoria de cobertura não demonstra validade econômica.

Ignorar **todas** as rejeições de qualidade, mantendo 60 segundos, elevaria
os pontos conjuntos disponíveis de 30.795 para 31.188, mas ainda produziria
zero pregões completos. É um limite diagnóstico de disponibilidade de
coleta, não uma alternativa válida de dados: inclui livros e negócios
incompletos. Mesmo combinando cinco minutos e remoção de todos os filtros,
o teste teria somente nove pregões completos, abaixo do mínimo de dez.

## Implicação e próximo trabalho

O acervo selecionado não sustenta o desenho vigente de 18 ativos, grade de
um minuto e pregões completos. Retirar um ativo ou apenas afrouxar a idade
não é uma solução suficiente; tampouco se deve transformar capturas inválidas
em cotações utilizáveis.

O caminho recomendado é preparar e validar uma coleta futura com margem
entre sua cadência e a idade máxima permitida, início anterior à abertura,
timestamps com offset, identificação da bolsa e monitoramento de falhas por
ativo. A cadência deverá ser medida num piloto antes de prometer cobertura.
Novos dados do visualizador público serão prospectivos: alterar o scraper
não preenche retroativamente os minutos de 2025. Uma alternativa com o acervo
existente exigiria formular outro desenho experimental, justificá-lo e
auditar novamente sua cobertura; não seria uma correção automática deste.

## Reprodução e validação

```sh
python -m rl_boleta.audit_gap_causes \
  --adapter-dir results/session_coverage_2026-10-08/canonical \
  --episodes-dir results/session_coverage_2026-10-08/episodes \
  --protocol configs/experimental_protocol_v2.json \
  --output-dir results/gap_causes_2026-10-08
```

O diretório de saída deve ser novo. O script verifica os hashes dos dados
originais, saídas do adaptador, protocolo e arquivo de lacunas de referência.
As contagens de aceitação/rejeição por arquivo devem coincidir com o
adaptador. O conjunto de lacunas reproduzido deve coincidir exatamente com
o manifesto dos episódios.

Saídas: `asset_grid.csv.gz`, `joint_grid.csv`, `sessions.csv`,
`assets_by_session.csv`, `counterfactual_coverage.csv` e `manifest.json`,
com hashes e limitações. Os seis testes de classificação passaram, incluindo
exclusão de capturas futuras, limite inclusivo de 60 segundos e distinção
entre rejeição recente e ausência de captura recente. Os dados originais,
manifestos anteriores e regras experimentais permaneceram intactos.
