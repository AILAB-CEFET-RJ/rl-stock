import pandas as pd

mapping = {
    'APPLE INC COM': 'APPLE',
    'TESLA INC COM': 'TESLA',
    'MICROSOFT CORP COM': 'MICROSOFT',
    'FORD MTR CO DEL COM': 'FORD',
    'CITIGROUP INC COM NEW': 'CITIGROUP',
    'FREEPORT-MCMORAN INC CL B': 'FREEPORT-MCMORAN',
    'BK OF AMERICA CORP COM': 'BANK_OF_AMERICA',
    'COCA COLA CO COM': 'COCA-COLA',
    'INTEL CORP COM': 'INTEL',
    'GENERAL MTRS CO COM': 'GM',
    'AMERICAN AIRLS GROUP INC COM': 'AMERICAN_AIRLS',
    'NORWEGIAN CRUISE LINE HLDG LTD SHS': 'NORWEGIAN_CRUISE',
    'JPMORGAN CHASE & CO COM': 'JPMORGAN',
    'PFIZER INC COM': 'PFIZER',
    'MORGAN STANLEY COM NEW': 'MORGAN_STANLEY',
    'DELTA AIR LINES INC DEL COM NEW': 'DELTA_AIR_LINES',
    'NEWMONT CORP COM': 'NEWMONT',
    'GENERAL ELECTRIC CO COM NEW': 'GE',
    'CISCO SYS INC COM': 'CISCO'
}

def convert_multiasset_dataset(df):
    """
    Converte um DataFrame multi-nível (multi-index) em um formato flat
    adequado para treinamento de modelos de trading multiativo.

    Essa função transforma as colunas de um DataFrame com múltiplos níveis
    (por exemplo, 'Ticker' e 'Feature') em colunas únicas no formato:

        <TICKER>_<FEATURE>

    Além disso, remove linhas com valores ausentes.

    Parâmetros
    ----------
    df : pandas.DataFrame
        DataFrame com colunas multi-nível (ex.: resultado de pivot_table)
        contendo informações de múltiplos ativos e features.

    Retorno
    -------
    pandas.DataFrame
        DataFrame "achatado" com colunas no formato <TICKER>_<FEATURE>
        e sem valores ausentes.

    Exemplo
    -------
    >>> df_flat = convert_multiasset_dataset(df_multi)
    >>> df_flat.columns
    ['APPLE_Prices', 'TESLA_Prices', 'APPLE_Shares', ...]
    """
    new_columns = []

    for ticker, feature in df.columns:
        new_columns.append(f"{ticker}_{feature}")

    df.columns = new_columns

    df = df.dropna()

    return df


def convert_to_dataset(file_path, company, mapping, output_path):
    """
    Converte um CSV bruto de múltiplos ativos em um dataset pivotado
    pronto para treinamento de modelos de trading multiativo.

    O processo inclui:

    1. Carregamento do CSV e remoção de valores ausentes.
    2. Normalização do ticker usando um dicionário de mapeamento.
    3. Conversão da coluna 'File Date' para datetime e ordenação temporal.
    4. Identificação de ciclos de negociação por ativo.
    5. Pivotagem do dataset para criar colunas de múltiplas features
       por ativo, incluindo preços, volumes e timestamps.
    6. Transformação do dataset pivotado em formato flat (<TICKER>_<FEATURE>).
    7. Salvamento do dataset final em CSV.

    Parâmetros
    ----------
    file_path : str
        Caminho do CSV bruto contendo os dados de múltiplos ativos.

    company : str
        Nome do ativo principal que servirá como referência de ciclos
        de negociação.

    mapping : dict
        Dicionário que mapeia nomes originais de ativos para nomes padronizados.

    output_path : str
        Caminho do arquivo CSV final a ser gerado.

    Retorno
    -------
    pandas.DataFrame
        Dataset multiativo pivotado e achatado, pronto para uso em
        treinamento de modelos de RL ou análise de séries temporais.

    Exemplo
    -------
    >>> df_final = convert_to_dataset(
    ...     file_path='../data/dados_final.csv',
    ...     company='APPLE',
    ...     mapping=mapping,
    ...     output_path='../data/dados_agregados_final.csv'
    ... )
    >>> df_final.head()
    """
    
    df = pd.read_csv(file_path)

    df = df.dropna()
    df = df.drop('Unnamed: 0', axis=1)

    df['Ticker'] = df['Ticker'].replace(mapping)

    df['File Date'] = pd.to_datetime(df['File Date'])
    
    df = df.sort_values('File Date').reset_index(drop=True)
    
    ticker = df['Ticker'] == company
    
    df['new_cycle'] = ticker & (~ticker.shift(fill_value=False))
    
    df['cycle_id'] = df['new_cycle'].cumsum()
    
    df['cycle_timestamp'] = df.groupby('cycle_id')['File Date'].transform('mean')
    
    df_multi = df.pivot_table(
    index='cycle_timestamp',
    columns='Ticker',
    values=['Shares', 'Prices', 'Time_Hour', 'Time_Minute', 'Time_Second', 'Last_10_Prices', 'Last_10_Shares']
)
    df_multi = df_multi.swaplevel(0, 1, axis=1)
    df_multi = df_multi.sort_index(axis=1)

    df_multi = df_multi.dropna().reset_index()

    df_final = convert_multiasset_dataset(df_multi)

    df_final.rename(columns={"cycle_timestamp_": "File Date"}, inplace=True)
    df_final.to_csv(output_path, index=False)

    return df_final