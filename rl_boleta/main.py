from tensorboard import program
from sklearn.model_selection import TimeSeriesSplit

import pandas as pd
import os
from datetime import datetime

from training import train_agent_multiasset
from testing import test_agent_multiasset

from evaluate_significance import test_significance_buy_and_hold

from config import PATH_DATA, PATH_RESULTS, COMPANYS

N_SPLITS = 5
GAMMA = 0.995

ALGORITHMS = ["PPO"]

log_dir = "./logs/"

tb = program.TensorBoard()
tb.configure(argv=[None, "--logdir", log_dir])
url = tb.launch()

print(f"TensorBoard rodando em: {url}")

df_final = pd.DataFrame()

string_now = datetime.now().strftime("%d_%m_%Y_%H_%M_%S")

file_path_report = f"{string_now}_multiasset"

print("Carregando dataset...")

df = pd.read_csv(f"{PATH_DATA}/dados_agregados_final.csv")
df = df.dropna().reset_index(drop=True)

print("Dataset carregado")
print("Número de linhas:", len(df))
print("Ativos usados:", COMPANYS)

tscv = TimeSeriesSplit(n_splits=N_SPLITS)

for fold, (train_index, test_index) in enumerate(tscv.split(df)):

    print(f"\n========== FOLD {fold+1}/{N_SPLITS} ==========")

    train_data = df.iloc[train_index]
    test_data = df.iloc[test_index]

    print("Treino:", len(train_data))
    print("Teste:", len(test_data))

    train_data.to_csv(f"{PATH_DATA}/temp_train.csv", index=False)
    test_data.to_csv(f"{PATH_DATA}/temp_test.csv", index=False)

    for algo in ALGORITHMS:

        print(f"\nTreinando {algo} MULTI-ASSET")

        results_training = train_agent_multiasset(
            file="temp_train.csv",
            tickers=COMPANYS,
            repetitive_iteration_number=fold + 1,
            algorithm=algo,
            gamma=GAMMA
        )

        results_testing = test_agent_multiasset(
            file="temp_test.csv",
            tickers=COMPANYS,
            repetitive_iteration_number=fold + 1
        )

        run = {
            "algoritmo": algo,
            "k-fold": fold + 1,
            "ativos": ",".join(COMPANYS)
        }

        results = {**run, **results_training, **results_testing}

        df_results = pd.DataFrame([results])

        df_final = pd.concat([df_final, df_results], ignore_index=True)

df_summary_final = pd.DataFrame()

for algo, df_group in df_final.groupby(["algoritmo"]):

    positive_final_values_test = (df_group["lucro/prejuízo teste"] > 0).sum()
    total_values_test = len(df_group)

    percentage_profit_test = (
        (positive_final_values_test / total_values_test) * 100
        if total_values_test > 0 else 0
    )

    average_final_value_test = df_group["lucro/prejuízo teste"].mean()
    std_final_value_test = df_group["lucro/prejuízo teste"].std()

    testing_rewards = df_group["recompensas teste"].mean()

    retorno_teste = (
        df_group["retorno teste"].mean()
        if "retorno teste" in df_group.columns
        else None
    )

    summary_results = {
        "Algoritmo": algo,
        "Ativos": ",".join(COMPANYS),
        "Média lucro final teste": average_final_value_test,
        "Desvio padrão lucro final teste": std_final_value_test,
        "Recompensas teste (média)": testing_rewards,
        "Porcentagem de iterações com lucro no teste": f"{percentage_profit_test:.2f}%",
        "Retorno médio teste": retorno_teste
    }

    df_summary_final = pd.concat(
        [df_summary_final, pd.DataFrame([summary_results])],
        ignore_index=True
    )

os.makedirs(f"{PATH_RESULTS}/reports/summary/", exist_ok=True)

summary_path = f"{PATH_RESULTS}/reports/summary/{file_path_report}_summary.csv"

df_summary_final.to_csv(summary_path, index=False)

print(f"Resumo salvo em {summary_path}")


# TESTE DE SIGNIFICÂNCIA ESTATÍSTICA

estatisticas_empresas = []

try:

    resultados = test_significance_buy_and_hold(
        df_final,
        company_name="PORTFOLIO",
        alpha=0.05,
        plot=True
    )

    if resultados:
        estatisticas_empresas.append(resultados)

except Exception as e:

    print("Erro no teste de significância:", e)


if estatisticas_empresas:

    df_estatisticas = pd.DataFrame(estatisticas_empresas)

    os.makedirs(f"{PATH_RESULTS}/statistics/", exist_ok=True)

    df_estatisticas.to_csv(
        f"{PATH_RESULTS}/statistics/significancia_multiasset_{string_now}.csv",
        index=False
    )

    print("Teste estatístico salvo")
