import gym
from gym import spaces
import numpy as np

OBSERVATION_WINDOW = 50 # Aumentado para dar mais contexto
TRANSACTION_COST = 0.001
SLIPPAGE_RATE = 0.0005
LATENCY_STEPS = 2
DELTA = 0.1 # Reduzido para permitir mais sensibilidade

class MultiAssetReinforcementLearningEnv(gym.Env):
    """
    Ambiente de Reinforcement Learning para negociação de múltiplos ativos financeiros.

    Este ambiente implementa uma simulação de trading baseada em dados históricos
    utilizando a interface padrão do Gym. O agente recebe observações contendo
    informações normalizadas de mercado para múltiplos ativos, além do estado
    atual do portfólio, e deve decidir continuamente quanto comprar ou vender
    de cada ativo.

    O objetivo do agente é maximizar o crescimento do patrimônio líquido
    (`net_worth`) ao longo do tempo, levando em consideração custos de transação,
    slippage e restrições simplificadas de execução de ordens.

    A cada passo de tempo:
        1. O agente recebe uma janela temporal (`OBSERVATION_WINDOW`) com dados
           normalizados de mercado.
        2. O agente executa uma ação contínua no intervalo [-1, 1] para cada ativo.
        3. O ambiente executa compras ou vendas parciais baseadas na ação.
        4. O patrimônio líquido é atualizado.
        5. O agente recebe uma recompensa baseada no retorno do portfólio,
           ajustado por volatilidade (Sharpe móvel simplificado).

    Parameters
    ----------
    mode : str
        Modo de operação do ambiente (por exemplo: "train", "test", "validation").
        Pode ser utilizado externamente para alterar comportamentos como
        exploração, logging ou métricas.

    df : pandas.DataFrame
        DataFrame contendo os dados históricos de mercado já pré-processados.
        Para cada ativo (`ticker`) espera-se as seguintes colunas:

        - "{ticker}_Prices"
        - "{ticker}_Shares"
        - "{ticker}_Time_Hour"
        - "{ticker}_Time_Minute"
        - "{ticker}_Time_Second"
        - "{ticker}_Last_10_Prices"
        - "{ticker}_Last_10_Shares"

        Cada linha representa um passo temporal da simulação.

    tickers : list[str]
        Lista contendo os símbolos dos ativos utilizados no ambiente.

    Attributes
    ----------
    n_assets : int
        Número de ativos no portfólio.

    window : int
        Tamanho da janela temporal usada na observação.

    initial_amount : float
        Capital inicial disponível para negociação.

    balance : float
        Quantidade de dinheiro disponível em caixa.

    net_worth : float
        Patrimônio líquido total (caixa + valor de mercado das posições).

    shares_held : np.ndarray
        Quantidade de ações atualmente mantidas para cada ativo.

    deslocamento : int
        Índice atual na série temporal do DataFrame.

    returns : list
        Histórico de retornos por passo utilizado para cálculo de Sharpe móvel.

    action_space : gym.spaces.Box
        Espaço contínuo de ações no intervalo [-1, 1] para cada ativo.
        Cada valor representa a intensidade da ação:
            - valores positivos indicam compra
            - valores negativos indicam venda
            - valores próximos de zero indicam manter posição

    observation_space : gym.spaces.Box
        Espaço de observação representado por uma matriz 2D:

        shape = (
            features_per_asset * n_assets + n_assets + 1,
            OBSERVATION_WINDOW
        )

        Componentes da observação:
        Para cada ativo:
            1. Volume de shares normalizado
            2. Preço normalizado (variação percentual)
            3. Hora normalizada
            4. Minuto normalizado
            5. Segundo normalizado
            6. Últimos 10 preços normalizados
            7. Últimos 10 volumes normalizados

        Estado do portfólio:
            - Peso de cada ativo no portfólio
            - Proporção de caixa disponível

    Methods
    -------
    reset()
        Reinicia o ambiente para o estado inicial.

        Returns
        -------
        np.ndarray
            Observação inicial contendo a primeira janela de dados.

    step(action)
        Executa um passo do ambiente aplicando a ação do agente.

        Parameters
        ----------
        action : np.ndarray
            Vetor contínuo com tamanho igual ao número de ativos.
            Cada valor indica intensidade de compra/venda.

        Returns
        -------
        observation : np.ndarray
            Nova observação após executar a ação.

        reward : float
            Recompensa calculada como retorno do portfólio ajustado
            por volatilidade (Sharpe móvel simplificado).

        done : bool
            Indica se o episódio terminou.

        info : dict
            Informações adicionais, incluindo o patrimônio final.

    _next_observation()
        Constrói a matriz de observação contendo a janela temporal
        atual de dados de mercado e estado do portfólio.

    _normalize_feature(data)
        Normaliza uma série temporal utilizando variação percentual
        relativa ao primeiro elemento da janela.

    _take_action(actions, prices)
        Executa as ações de compra ou venda para cada ativo.

        Regras de execução:
            - Apenas 10% do caixa pode ser usado por ordem de compra
            - Custos de transação são aplicados
            - Slippage é considerado no preço de execução
            - Vendas são proporcionais às posições atuais

    Reward Function
    ---------------
    A recompensa base é o retorno percentual do patrimônio líquido
    entre dois passos consecutivos:

        step_return = (net_worth_t - net_worth_{t-1}) / net_worth_{t-1}

    Após acumular retornos suficientes, utiliza-se uma aproximação
    do Sharpe Ratio móvel:

        reward = step_return / std(últimos 20 retornos)

    Isso incentiva estratégias com maior retorno ajustado ao risco.

    Notes
    -----
    - O ambiente usa normalização baseada em variação percentual
      para evitar dependência de preços absolutos.
    - A execução de ordens é simplificada para facilitar o aprendizado
      inicial do agente.
    - Latência de mercado é definida mas não aplicada diretamente
      neste modelo simplificado.
    """

    def __init__(self, mode, df, tickers):
        super().__init__()
        self.mode = mode
        self.df = df.reset_index(drop=True)
        self.tickers = tickers
        self.n_assets = len(tickers)
        self.window = OBSERVATION_WINDOW
        
        self.initial_amount = 10000
        self.action_space = spaces.Box(low=-1, high=1, shape=(self.n_assets,), dtype=np.float32)
        
        self.features_per_asset = 7
        self.observation_space = spaces.Box(
            low=-5, high=5, 
            shape=(self.features_per_asset * self.n_assets + self.n_assets + 1, self.window),
            dtype=np.float32
        )
        self.reset()

    def reset(self):
        self.balance = self.initial_amount
        self.net_worth = self.initial_amount
        self.shares_held = np.zeros(self.n_assets)
        self.deslocamento = self.window
        self.returns = []
        return self._next_observation()

    def _normalize_feature(self, data):
        return np.diff(data, prepend=data[0]) / (data[0] + 1e-8)

    def _next_observation(self):
        start = self.deslocamento - self.window
        end = self.deslocamento
        frame = []

        for ticker in self.tickers:
            prices = self.df.iloc[start:end][f"{ticker}_Prices"].values
            prices_norm = self._normalize_feature(prices)
            
            shares = self.df.iloc[start:end][f"{ticker}_Shares"].values
            shares_norm = (shares - np.mean(shares)) / (np.std(shares) + 1e-8)

            hour = self.df.iloc[start:end][f"{ticker}_Time_Hour"].values / 23.0
            minute = self.df.iloc[start:end][f"{ticker}_Time_Minute"].values / 59.0
            second = self.df.iloc[start:end][f"{ticker}_Time_Second"].values / 59.0

            last_prices = self._normalize_feature(self.df.iloc[start:end][f"{ticker}_Last_10_Prices"].values)
            last_shares = self._normalize_feature(self.df.iloc[start:end][f"{ticker}_Last_10_Shares"].values)

            frame.extend([shares_norm, prices_norm, hour, minute, second, last_prices, last_shares])

        prices_now = np.array([self.df.iloc[self.deslocamento-1][f"{t}_Prices"] for t in self.tickers])
        weights = (self.shares_held * prices_now) / (self.net_worth + 1e-8)
        cash_ratio = self.balance / (self.net_worth + 1e-8)

        portfolio_obs = [np.repeat(w, self.window) for w in weights]
        portfolio_obs.append(np.repeat(cash_ratio, self.window))
        
        obs = np.vstack((np.array(frame), np.array(portfolio_obs)))
        return obs.astype(np.float32)

    def step(self, action):
        prices = np.array([self.df.iloc[self.deslocamento][f"{t}_Prices"] for t in self.tickers])
        prev_net_worth = self.net_worth
        
        self._take_action(action, prices)
        
        self.deslocamento += 1
        done = self.deslocamento >= len(self.df) - 1
        
        step_return = (self.net_worth - prev_net_worth) / (prev_net_worth + 1e-8)
        self.returns.append(step_return)
        
        reward = step_return
        if len(self.returns) > 20:
            reward = step_return / (np.std(self.returns[-20:]) + 1e-8) # Sharpe móvel

        obs = self._next_observation() if not done else np.zeros(self.observation_space.shape)
        return obs.astype(np.float32), reward, done, {"final_net_worth": self.net_worth}

    def _take_action(self, actions, prices):
        for i, action in enumerate(actions):
            price = prices[i]
            # Compra
            if action > DELTA:
                cost = (self.balance * action * 0.1) 
                shares_to_buy = cost // (price * (1 + SLIPPAGE_RATE))
                if shares_to_buy > 0:
                    full_cost = shares_to_buy * price * (1 + SLIPPAGE_RATE) * (1 + TRANSACTION_COST)
                    self.balance -= full_cost
                    self.shares_held[i] += shares_to_buy
            # Venda
            elif action < -DELTA:
                shares_to_sell = int(self.shares_held[i] * abs(action))
                if shares_to_sell > 0:
                    proceeds = shares_to_sell * price * (1 - SLIPPAGE_RATE) * (1 - TRANSACTION_COST)
                    self.balance += proceeds
                    self.shares_held[i] -= shares_to_sell

        self.net_worth = self.balance + np.sum(self.shares_held * prices)