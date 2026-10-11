# Auditoria dos relógios nas mudanças do horário americano

Inspeção dos Parquet originais, sem reutilizar os CSVs processados ou os
resultados financeiros da dissertação. Não houve treinamento ou alteração dos
dados. Os arquivos foram selecionados pelo nome nas janelas de 24/02–21/03/2025
e 20/10–14/11/2025, abrangendo as duas transições do relógio de Nova York.

## Resultado

**Os relógios são fortemente consistentes com coleta em UTC−3 e horários dos
negócios em Nova York, sem um atraso adicional fixo de três horas.**
Essa é uma inferência a partir dos arquivos, apoiada pela documentação do
scraper e pela [inspeção da fonte pública](scraper_timezone_evidence.md), não
uma confirmação da configuração da máquina original.

Foram examinados 34 arquivos, 2.833.340 linhas e 267.096 blocos completos de
captura. Desses, 237.062 têm o último negócio entre 09:30 e 16:00 no relógio
registrado pela fonte. Para esse subconjunto:

| Período | Arquivos | Capturas | Mediana da diferença bruta | Mediana após descontar o fuso | Entre 0 e 60 s após descontar o fuso |
|---|---:|---:|---:|---:|---:|
| 24/02–07/03, antes da transição de março | 10 | 76.496 | 2 h 16 s | 16 s | 98,42% |
| 10/03–21/03, depois da transição de março | 8 | 56.566 | 1 h 16 s | 16 s | 96,36% |
| 20/10–31/10, antes da transição de novembro | 9 | 58.365 | 1 h 14 s | 14 s | 96,28% |
| 03/11–12/11, depois da transição de novembro | 7 | 45.635 | 2 h 13 s | 13 s | 97,97% |

As duas mudanças têm a direção prevista para Nova York, enquanto UTC−3
permanece constante. Ao adotar esses fusos, nenhuma captura completa examinada
tem o último negócio no futuro. Considerando também os horários fora de
09:30–16:00, as medianas residuais são 16, 17, 15 e 14 segundos,
respectivamente. A conclusão, portanto, não depende apenas do subconjunto
mostrado na tabela.

Sob a hipótese conjunta UTC−3/Nova York **mais três horas fixas de atraso**, o
resíduo seria negativo em 100% das capturas do subconjunto da tabela: o atraso
presumido excederia o tempo transcorrido observado. Com coleta em UTC e fonte
em Nova York, também se obtêm resíduos negativos em 100% desse subconjunto.
Com ambos os campos no mesmo relógio, sobram uma ou duas horas, acompanhando
as mudanças sazonais. Entre as interpretações examinadas, UTC−3/Nova York sem
atraso adicional explica o padrão com resíduos pequenos e não negativos.

## Método e limites

O script usa `inspect_frame` da auditoria existente para reconstruir blocos
originais de dez linhas, com ativo consistente, cinco asks/cinco bids,
timestamps de coleta consistentes, valores completos e dez horários de
negócio válidos. Exclui duplicatas exatas de captura e chaves ambíguas dentro
de cada arquivo. Não impõe limite de spread/profundidade nem filtra pela
proximidade ao fuso esperado. Inclui os ativos presentes nos arquivos,
independentemente do universo experimental.

Para cada bloco, compara o fim da captura (`File_Date`) com o maior dos dez
horários de negócio (`Time`), usando a data local registrada (`Date`). Os
offsets são calculados com `zoneinfo` para `America/Sao_Paulo` e
`America/New_York`. O diagnóstico de horário regular filtra somente o relógio
do último negócio; não é um calendário de elegibilidade experimental.

O resíduo **não mede isoladamente a latência do feed**. Ele reúne idade do
último negócio, tempo de coleta, possível atraso de transmissão e erros de
relógio. O timestamp do negócio tampouco certifica o instante do livro.
Relógios deliberadamente deslocados poderiam reproduzir outras interpretações;
os arquivos sem offset não identificam fuso e latência de maneira única.
UTC−3 não identifica sozinho a localização física ou a configuração IANA da
máquina. A inferência não certifica todos os dias do acervo nem executabilidade
das cotações.

## Consequência para o projeto

Adotar UTC−3 (`America/Sao_Paulo`) e Nova York como interpretação operacional
com suporte empírico, preservando a classificação de inferência nos registros.
Não aplicar deslocamento adicional de três horas. O relato dessa duração passa
a ser uma lembrança não confirmada, incompatível com a combinação de fusos
favorecida nas janelas examinadas; não uma constante estabelecida da fonte.

Os manifestos anteriores continuam intactos: registravam 10.800 segundos como
informação de interpretação não resolvida, mas **não subtraíam esse valor**.
Por isso, retirar essa premissa não altera automaticamente o alinhamento nem
resolve as lacunas de cobertura já encontradas. Uma nova execução deverá
registrar a evidência temporal atualizada e o atraso fixo como não estabelecido,
sem afirmar latência exatamente zero.

## Reprodução e verificação

Executar na raiz, com pandas, numpy e pyarrow disponíveis:

```sh
python -m scripts.audit_clock_transitions
```

O script se recusa a sobrescrever o diretório de resultados existente.
Saídas em `results/clock_transitions_2026-10-08/`:

- `manifest.json`: entradas e SHA-256, método, limitações e hashes do código
  e das saídas;
- `clock_blocks.csv.gz`: horários e diferenças por captura;
- `daily.csv`: quantis diários, antes e depois do desconto de fuso;
- `hypotheses.csv`: comparação das quatro interpretações, com e sem filtro
  pelo horário dos negócios.

A execução terminou sem erros. Todos os hashes de entrada e saída registrados
foram conferidos após a análise; os arquivos originais permaneceram intactos.
