# Evidências locais sobre os fusos do scraper

Atualização: a [auditoria dos relógios nas duas transições de 2025](clock_transition_audit.md)
encontrou suporte empírico forte para coleta em UTC−3 e fonte em Nova York,
sem atraso adicional fixo de três horas. As seções abaixo preservam as
evidências e os limites das inspeções anteriores.

Inspeção em 08/10/2026 do repositório local
`/Users/ebezerra/ailab/cboe-finance-scraper`, commit
`d2a09cc6f7536999169cda0233c896131be6371a`, sem alterações locais.
É o mesmo commit consultado anteriormente na auditoria remota. Nenhum arquivo
do scraper ou dado histórico foi modificado nesta inspeção.

## O que o código demonstra

- `collect/crawler.py:213` gera `File_Date` com
  `datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")`: horário local da
  máquina, sem offset ou identificador de fuso persistido.
- `crawler.py:207` interpreta o horário extraído da tabela apenas com
  `strptime(valor, '%H:%M:%S').time()`. Não atribui fuso a `Time` e não registra
  uma data de mercado da fonte junto a esse horário.
- `crawler.py:215–216` gera `Date` a partir de `datetime.datetime.today()`.
  Portanto, apesar da descrição no dicionário de dados, essa coluna também
  deriva da máquina, não de uma data fornecida pela Cboe.
- `main.py:12` define `tz = timezone('US/Eastern')`, usado na linha 23
  apenas para imprimir o horário corrente nesse fuso. Isso documenta a
  intenção de comparar a coleta com o horário do leste americano, mas não
  altera o fuso do sistema, do navegador ou dos campos salvos pelo crawler.
- `helpers/validation_time.py:13–14` descreve 08:00–18:00 como
  “horário brasileiro - UTC−3”. As linhas 29–32 reconhecem a dependência do
  fuso local da máquina; a função compara `datetime.datetime.today().time()`
  com esses limites, sem conversão explícita.
- A configuração do Chrome usa modo headless, sem override de fuso. Não foi
  encontrada configuração de implantação, definição de `TZ`, imagem de
  contêiner ou log de execução que fixe o fuso histórico da máquina.

## Evidências auxiliares e limites

A imagem `images/1_dados_coletados.png` mostra, em 10/07/2024, `File_Date`
12:21:57 e um negócio com `Time` 11:21:49. Essa diferença de uma hora e oito
segundos é compatível com coleta em UTC−3 e negócios no leste americano em
horário de verão, com oito segundos entre os instantes. Essa interpretação é
condicional: horários sem offset também podem combinar diferenças de fuso,
atraso e idade do negócio. A imagem é de 2024 e não prova a configuração de 2025.

O print `images/2_dados_cboe.png` contém horários dos negócios, mas não mostra
um rótulo de fuso nem timestamp de mercado do livro. Não resolve essa lacuna.
Os commits de março de 2026 têm offset −03:00, o que é indício sobre o ambiente
de autoria dos commits, não prova do fuso da máquina que coletou em 2025.
O histórico disponível também não demonstra que essa revisão exata foi a usada
para produzir todos os Parquet históricos.

## Conclusão para os manifestos

Há suporte documental explícito para a intenção de usar UTC−3 na coleta e
US/Eastern como referência dos dados. Isso reforça as hipóteses atuais
`America/Sao_Paulo` e `America/New_York`, mas não certifica o ambiente histórico
nem a semântica do relógio exibido pela página. Os status permanecem
`hypothesis`; não se alteraram os manifestos, a cobertura ou a atribuição do
atraso de três horas informado pelo usuário.

Para confirmar o fuso histórico, seria necessária evidência vinculada à
execução de coleta: configuração da máquina/servidor, log que registre local e
UTC com offset, ou outra âncora temporal confiável. O rótulo de fuso do horário
de negócio e o significado do atraso do livro precisam de evidência da fonte.
Configurar fusos explicitamente no scraper corrigiria coletas futuras, mas
não recuperaria por si só os offsets omitidos nos arquivos de 2025.


## Verificação da fonte pública em 08/10/2026

A [página oficial do Book Viewer](https://www.cboe.com/markets/us/equities/market-statistics/book-viewer)
descreve bids/asks atuais em tempo real, os dez últimos negócios e dados
separados das bolsas BZX, BYX, EDGX e EDGA. A descrição consultada não informa
um atraso fixo de três horas. Isso é uma declaração do fornecedor sobre o
produto atual, não uma medição de latência nem prova de seu comportamento em
2025. Não confundir a idade do último negócio com o atraso do livro.

A [página legada indexada](https://www.cboe.com/us/equities/market_statistics/book/stock/)
exibe `Last updated 17:50:20 US/Eastern`. O rótulo refere-se ao horário de
atualização do visualizador; por si só não demonstra o fuso de cada negócio.
Na leitura direta do HTML, o campo de atualização fica vazio porque depende
de carregamento dinâmico. Portanto, o rótulo é evidência do conteúdo indexado,
não uma observação direta de um livro atualizado nesta inspeção.

O HTML da [página de AAPL usada pelo scraper](https://www.cboe.com/us/equities/market_statistics/book/AAPL/)
carrega o [JavaScript do Book Viewer](https://www.cboe.com/_cache/js/f8f13675b071af836ecc6c3898910287.js).
Nele, `updateTradeCells` coloca `item[0]` diretamente na célula de horário,
e `updateNameAndVolumeData` coloca `data.timestamp` no rodapé. Esses caminhos
não convertem os valores para o fuso do navegador. Isso reduz a plausibilidade
de uma conversão local feita pelo visualizador, mas não revela sozinho a
semântica temporal dos valores enviados pelo servidor.

O código solicita `/json/{mercado}/book/{símbolo}` e programa novas consultas
com `res.reload`. Esse intervalo de atualização não equivale a atraso da fonte.
A consulta direta a `/json/bzx/book/AAPL` retornou uma página de bloqueio do
Cloudflare, não JSON de mercado. Assim, não foi possível conferir uma resposta
dinâmica com timestamp nem medir a latência nesta inspeção.

As cópias de HTML, JavaScript e resposta de bloqueio, com URLs e SHA-256,
estão em `results/cboe_source_verification_2026-10-08/evidence_index.json`.
O arquivo de índice distingue a resposta de bloqueio dos dados de mercado.

### Efeito sobre o protocolo

A evidência atual reforça `America/New_York` como hipótese para os horários da
fonte, com horário de verão, mas não confirma o fuso da máquina de coleta nem
vincula essa configuração aos Parquet de 2025. A informação de atraso de três
horas fornecida pelo usuário permanece registrada como questão a reconciliar
com a documentação pública. Não se deve subtrair automaticamente três horas,
confundir diferença entre fusos com latência, nem tratar a descrição atual de
tempo real como certificação retrospectiva. Nenhum dado, manifesto, hipótese
temporal operacional ou resultado de cobertura foi alterado por esta inspeção.
