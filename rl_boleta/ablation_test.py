import pandas as pd
import os
from datetime import datetime

from training import train_agent_multiasset
from testing import test_agent_multiasset

from config import PATH_DATA, PATH_RESULTS, COMPANYS

ALGORITHMS = ["PPO"]

TRAIN_SPLIT = 0.8

FEATURES = [
    "Shares",
    "Time_Hour",
    "Time_Minute",
    "Time_Second",
    "Last_10_Prices"
    "Last_10_Shares"
]

FEATURE_SETS = {
    "all_features": []
}

for feat in FEATURES:
    FEATURE_SETS[f"remove_{feat}"] = [feat]


FEATURE_SETS.update({

    "no_time": [
        "Time_Hour",
        "Time_Minute",
        "Time_Second"
    ],

    "only_prices": [
        "Shares",
        "Time_Hour",
        "Time_Minute",
        "Time_Second",
        "Last_10_Shares"
    ],

    "only_volume": [
        "Time_Hour",
        "Time_Minute",
        "Time_Second",
        "Last_10_Prices"
    ]
})


def mask_dataframe_features(df, tickers, mask_features):
    """
    Aplica uma máscara em determinadas features de um DataFrame, definindo seus
    valores como zero para um conjunto de ativos.

    O objetivo é avaliar a importância de determinadas variáveis de entrada do modelo,
    removendo sua informação do dataset.

    Para cada ativo presente na lista `tickers`, a função procura colunas no
    DataFrame com o seguinte padrão:

        <TICKER>_<FEATURE>

    Caso a coluna exista e a feature esteja listada em `mask_features`,
    todos os seus valores são substituídos por zero.

    Ao invés de remover a coluna do DataFrame, os valores são zerados para que
    a estrutura do dataset (dimensionalidade do espaço de observação do agente)
    permaneça inalterada.

    A função não modifica o DataFrame original. Uma cópia é criada e retornada.

    Parâmetros
    ----------
    df : pandas.DataFrame
        DataFrame contendo o dataset completo com features de múltiplos ativos.
        Espera-se que as colunas estejam no formato:

            <TICKER>_<FEATURE>

        Exemplos:
            APPLE_Prices
            APPLE_Shares
            TESLA_Last_10_Prices

    tickers : list[str]
        Lista de empresas presentes no dataset.

        Exemplo:
            ["APPLE", "TESLA", "CISCO"]

        Para cada ticker, a função tentará aplicar máscara nas features
        especificadas em `mask_features`.

    mask_features : list[str]
        Lista de features que devem ser removidas (mascaradas).

        Para cada feature nesta lista, a função irá procurar colunas no formato:

            <TICKER>_<FEATURE>

        Caso existam no DataFrame, seus valores serão substituídos por zero.

        Exemplo:
            ["Prices", "Shares"]

    Retorno
    -------
    pandas.DataFrame
        Uma cópia do DataFrame original onde as colunas correspondentes às
        features especificadas foram zeradas para todos os ativos.

    Observações
    -----------
    Esta função é utilizada principalmente em experimentos de análise de
    importância de features em modelos de aprendizado de máquina.

    Em vez de remover colunas, as features são zeradas para manter:

    - a mesma dimensionalidade do espaço de observação
    - a mesma arquitetura do modelo
    - compatibilidade com o ambiente de RL

    Exemplo
    -------
    >>> df_masked = mask_dataframe_features(
    ...     df=dataframe,
    ...     tickers=["APPLE", "TESLA"],
    ...     mask_features=["Prices"]
    ... )

    Neste caso, as seguintes colunas terão seus valores definidos como zero
    (caso existam no DataFrame):

        APPLE_Prices
        TESLA_Prices
    """

    df = df.copy()

    for ticker in tickers:

        for feature in mask_features:

            col = f"{ticker}_{feature}"

            if col in df.columns:
                df[col] = 0

    return df

print("Carregando dataset...")

df_original = pd.read_csv(f"{PATH_DATA}/dados_agregados_final.csv")

df_original = df_original.dropna().reset_index(drop=True)

print("Dataset carregado")
print("Linhas:", len(df_original))


split_index = int(TRAIN_SPLIT * len(df_original))

train_base = df_original.iloc[:split_index]
test_base = df_original.iloc[split_index:]

print("Treino:", len(train_base))
print("Teste:", len(test_base))

timestamp = datetime.now().strftime("%d_%m_%Y_%H_%M_%S")

os.makedirs(f"{PATH_RESULTS}/ablation/", exist_ok=True)

output_file = f"{PATH_RESULTS}/ablation/ablation_results_{timestamp}.csv"

results_final = []

for feature_set_name, mask_features in FEATURE_SETS.items():

    print("\n====================================")
    print("TESTANDO:", feature_set_name)
    print("Removendo:", mask_features)
    print("====================================")

    df_train = mask_dataframe_features(train_base, COMPANYS, mask_features)
    df_test = mask_dataframe_features(test_base, COMPANYS, mask_features)

    df_train.to_csv(f"{PATH_DATA}/temp_train.csv", index=False)
    df_test.to_csv(f"{PATH_DATA}/temp_test.csv", index=False)

    for algo in ALGORITHMS:

        print(f"\nTreinando {algo}")

        results_training = train_agent_multiasset(
            file="temp_train.csv",
            tickers=COMPANYS,
            repetitive_iteration_number=1,
            algorithm=algo
        )

        results_testing = test_agent_multiasset(
            file="temp_test.csv",
            tickers=COMPANYS,
            repetitive_iteration_number=1
        )

        run = {
            "feature_set": feature_set_name,
            "algorithm": algo,
            "assets": ",".join(COMPANYS)
        }

        run_result = {
            **run,
            **results_training,
            **results_testing
        }

        results_final.append(run_result)

df_results = pd.DataFrame(results_final)

df_results.to_csv(output_file, index=False)

print("Resultados salvos em:")
print(output_file)