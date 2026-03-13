import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
import json
import os

def test_significance_buy_and_hold(df, company_name, alpha=0.05, plot=True, output_dir="./results/statistics/"):
    """
    Testa a significância estatística dos retornos de um agente de trading
    em comparação com a estratégia Buy and Hold.

    Esta função realiza um teste adaptativo entre métodos paramétricos
    (t-test de Student) e não-paramétricos (Mann-Whitney U) dependendo
    da normalidade dos dados de retorno. Além disso, gera histogramas
    comparativos e salva os resultados em JSON.

    Procedimento:

    1. Verifica se as colunas 'lucro/prejuízo teste' e 'lucro buy and hold' existem.
    2. Remove valores ausentes e converte os retornos para float.
    3. Calcula média, desvio padrão e intervalos de confiança (IC95%) para ambas séries.
    4. Testa a normalidade dos dados (Shapiro-Wilk) e seleciona o teste apropriado:
       - Se ambos normais: t-test de Student (unilateral, agente > Buy & Hold)
       - Caso contrário: Mann-Whitney U (não-paramétrico)
    5. Determina se a diferença entre os retornos é estatisticamente significativa.
    6. Gera histogramas comparativos, destacando as médias de cada série.
    7. Salva os resultados em JSON e, se `plot=True`, salva o gráfico no diretório especificado.

    Parâmetros
    ----------
    df : pandas.DataFrame
        DataFrame contendo os retornos do agente e do Buy and Hold. Deve conter as colunas:
        - 'lucro/prejuízo teste'
        - 'lucro buy and hold'

    company_name : str
        Nome da empresa ou ativo analisado, usado em títulos de arquivos e gráficos.

    alpha : float, default=0.05
        Nível de significância para os testes estatísticos.

    plot : bool, default=True
        Se True, gera e salva histogramas comparativos de retornos.

    output_dir : str, default="./results/statistics/"
        Diretório onde os arquivos JSON e gráficos serão salvos.

    Retorno
    -------
    dict
        Dicionário contendo os resultados estatísticos, incluindo:
        - teste utilizado
        - p-value
        - médias e IC95% de ambas as séries
        - normalidade das distribuições
        - indicação de significância estatística (True/False)

    Observações
    -----------
    - Caso as colunas de retorno não existam ou haja menos de 2 amostras em qualquer série, retorna None.
    - O teste é unilateral: verifica se o retorno do agente é significativamente maior que Buy & Hold.
    - Garante compatibilidade JSON convertendo tipos NumPy para tipos nativos Python.

    Exemplo
    -------
    >>> results = test_significance_buy_and_hold(df, 'APPLE', alpha=0.05)
    >>> results['significativo']
    True
    >>> results['teste_utilizado']
    't-test (Student)'
    """

    if 'lucro/prejuízo teste' not in df.columns or 'lucro buy and hold' not in df.columns:
        return None

    agent_returns = df['lucro/prejuízo teste'].dropna().astype(float).values
    bh_returns = df['lucro buy and hold'].dropna().astype(float).values

    if len(agent_returns) < 2 or len(bh_returns) < 2:
        return None

    mean_agent = np.mean(agent_returns)
    mean_bh = np.mean(bh_returns)
    std_agent = np.std(agent_returns, ddof=1)
    std_bh = np.std(bh_returns, ddof=1)

    # Testes de normalidade (Shapiro-Wilk)
    shapiro_agent = stats.shapiro(agent_returns)
    shapiro_bh = stats.shapiro(bh_returns)
    normal_agent = shapiro_agent.pvalue > alpha
    normal_bh = shapiro_bh.pvalue > alpha

    # Escolha adaptativa do teste
    if normal_agent and normal_bh:
        test_type = "t-test (Student)"
        t_stat, p_value = stats.ttest_ind(agent_returns, bh_returns, equal_var=False)
        # Teste unilateral (agente > buy and hold)
        p_value = p_value / 2 if mean_agent > mean_bh else 1.0
    else:
        test_type = "Mann-Whitney U (não-paramétrico)"
        u_stat, p_value = stats.mannwhitneyu(agent_returns, bh_returns, alternative="greater")

    significativo = p_value < alpha

    # Intervalos de confiança (IC95%)
    ci95_agent = 1.96 * std_agent / np.sqrt(len(agent_returns))
    ci95_bh = 1.96 * std_bh / np.sqrt(len(bh_returns))

    results = {
        "empresa": company_name,
        "n_amostras": len(agent_returns),
        "teste_utilizado": test_type,
        "p_normalidade_agente": shapiro_agent.pvalue,
        "p_normalidade_buyhold": shapiro_bh.pvalue,
        "media_retorno_agente": mean_agent,
        "media_retorno_buyhold": mean_bh,
        "p_value": p_value,
        "significativo": bool(significativo),
        "IC95_agente": (mean_agent - ci95_agent, mean_agent + ci95_agent),
        "IC95_buyhold": (mean_bh - ci95_bh, mean_bh + ci95_bh)
    }

    def convert_to_python(obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.ndarray,)):
            return obj.tolist()
        return obj

    results_clean = {k: convert_to_python(v) for k, v in results.items()}

    if plot:
        plt.rcParams.update({
        'font.family': 'serif',
        'font.size': 12,
        'axes.titlesize': 14,
        'axes.labelsize': 12,
        'legend.fontsize': 10,
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'grid.linestyle': '--',
        'grid.alpha': 0.3,
        'figure.dpi': 120
    })
        
        plt.figure(figsize=(7, 4))
        plt.hist(agent_returns, bins=12, alpha=0.6, label='Agente', color='steelblue')
        plt.hist(bh_returns, bins=12, alpha=0.6, label='Buy & Hold', color='orange')
        plt.axvline(mean_agent, color='#1f77b4', linestyle='--', label=f'Média Agente - US${mean_agent:.2f}')
        plt.axvline(mean_bh, color='#d95f02', linestyle='--', label=f'Média B&H - US${mean_bh:.2f}')
        plt.xlabel("Lucro (US$)")
        plt.ylabel("Frequência")
        plt.legend()
        plt.grid(alpha=0.3)
        ax = plt.gca()
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        os.makedirs(output_dir, exist_ok=True)
        plt.savefig(f"{output_dir}/{company_name}_distribuicao.png", bbox_inches="tight")
        plt.close()

    os.makedirs(output_dir, exist_ok=True)
    file_path = f"{output_dir}/{company_name}_significancia.json"
    with open(file_path, "w") as f:
        json.dump(results_clean, f, indent=4)

    return results_clean
