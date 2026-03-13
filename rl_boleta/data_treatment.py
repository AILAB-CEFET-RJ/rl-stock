import pandas as pd
from config import PATH_DATA

def process_data(filename, companys):
    """
    Carrega e processa dados de múltiplos ativos, retornando um DataFrame
    contendo apenas as colunas dos ativos desejados em formato numérico.

    Esta função realiza as seguintes operações:

    1. Leitura de um arquivo CSV com separador de milhares (`,`) para float.
    2. Ordenação cronológica pelo campo `File Date`.
    3. Remoção de linhas com valores ausentes.
    4. Seleção apenas das colunas correspondentes aos ativos informados
       na lista `companys`.
    5. Manutenção temporária das colunas de controle `File Date` e `Day`,
       caso existam, para ordenação ou referência.
    6. Remoção final das colunas de controle (`File Date` e `Day`) e
       redefinição do índice.
    7. Conversão de todos os valores restantes para tipo `float`.

    Parâmetros
    ----------
    filename : str
        Nome do arquivo CSV a ser processado. O arquivo deve estar localizado
        no diretório definido por `PATH_DATA` na configuração do projeto.

    companys : list[str]
        Lista de tickers ou ativos desejados. Apenas colunas que começam com
        `<company>_` serão selecionadas no DataFrame final.

    Retorno
    -------
    pandas.DataFrame
        DataFrame contendo apenas as colunas selecionadas dos ativos, com
        valores numéricos (float), pronto para análise ou treinamento de
        modelos de trading.

    Observações
    -----------
    - Remove automaticamente linhas com valores ausentes.
    - Ordena os dados cronologicamente pelo campo `File Date`.
    - Converte todos os valores para float.
    - Colunas auxiliares `File Date` e `Day` são removidas ao final do
      processamento.

    Exemplo
    -------
    >>> df = process_data('dados_agregados_final.csv', ['APPLE', 'TESLA', 'MICROSOFT'])
    >>> df.head()
       APPLE_Prices  APPLE_Shares  TESLA_Prices  TESLA_Shares  MICROSOFT_Prices
    0       150.23        1000.0        720.5         500.0              300.0
    """

    df = pd.read_csv(f'{PATH_DATA}/{filename}', thousands=',')

    df = df.sort_values('File Date')
    df = df.dropna()

    selected_columns = []

    for col in df.columns:

        for company in companys:

            if col.startswith(company + "_"):
                selected_columns.append(col)

    # manter também File Date se existir
    if 'File Date' in df.columns:
        selected_columns.append('File Date')

    if 'Day' in df.columns:
        selected_columns.append('Day')

    df = df[selected_columns]

    if 'File Date' in df.columns:
        df = df.sort_values('File Date')
        df.drop('File Date', axis='columns', inplace=True)

    if 'Day' in df.columns:
        df.drop('Day', axis='columns', inplace=True)

    df.reset_index(drop=True, inplace=True)

    df = df.astype(float)

    return df