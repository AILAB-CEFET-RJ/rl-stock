def buy_and_hold_baseline(df, tickers, initial_cash):
    """
    Calcula o valor final de uma estratégia baseline do tipo Buy and Hold
    para um conjunto de ativos.

    A estratégia Buy and Hold consiste em investir o capital inicial
    igualmente entre todos os ativos no primeiro instante do dataset
    e manter essas posições até o último instante disponível, sem
    realizar nenhuma negociação intermediária.

    Essa função é utilizada como baseline para comparar o desempenho
    com outras estratégias.

    O procedimento executado é:

    1. Dividir o capital inicial igualmente entre todos os ativos.
    2. Comprar cada ativo no primeiro preço disponível no dataset.
    3. Manter as posições durante todo o período.
    4. Calcular o valor final da carteira utilizando o último preço
       disponível para cada ativo.

    Parâmetros
    ----------
    df : pandas.DataFrame
        DataFrame contendo os dados de mercado para todos os ativos.
        Espera-se que existam colunas com o formato:

            <TICKER>_Prices

        Exemplo:
            APPLE_Prices
            TESLA_Prices
            MICROSOFT_Prices

        A primeira linha do DataFrame representa o momento da compra
        inicial e a última linha representa o momento de avaliação final.

    tickers : list[str]
        Lista de ativos que compõem a carteira.

        Exemplo:
            ["APPLE", "TESLA", "MICROSOFT"]

    initial_cash : float
        Capital inicial disponível para investimento.

        Esse valor será dividido igualmente entre todos os ativos.

    Retorno
    -------
    float
        Valor final da carteira após aplicar a estratégia Buy and Hold
        durante todo o período do dataset.

    Observações
    -----------
    - Não considera custos de transação.
    - Não realiza rebalanceamento da carteira.
    - Assume compra fracionária de ativos.
    - Cada ativo recebe a mesma proporção do capital inicial.


    Exemplo
    -------
    >>> final_value = buy_and_hold_baseline(
    ...     df=dataframe,
    ...     tickers=["TESLA", "APPLE"],
    ...     initial_cash=100000
    ... )

    Nesse caso:

    - R$ 50.000 são investidos em PETR4
    - R$ 50.000 são investidos em VALE3

    As ações são compradas no primeiro preço disponível e avaliadas
    no último preço do dataset.
    """

    cash_per_asset = initial_cash / len(tickers)

    shares = {}

    for ticker in tickers:

        first_price = df.iloc[0][f"{ticker}_Prices"]

        shares[ticker] = cash_per_asset / first_price

    final_value = 0

    for ticker in tickers:

        last_price = df.iloc[-1][f"{ticker}_Prices"]

        final_value += shares[ticker] * last_price

    return final_value

