class AgentPerformanceCalculator:
    def calculate(self, agent_id, outcomes):
        signal_count = len(outcomes)
        if signal_count == 0:
            return {
                "agent_id": agent_id,
                "signal_count": 0,
                "win_rate": 0,
                "avg_return": 0,
                "max_drawdown": 0,
            }

        returns = [outcome["return"] for outcome in outcomes]
        drawdowns = [outcome["max_drawdown"] for outcome in outcomes]

        return {
            "agent_id": agent_id,
            "signal_count": signal_count,
            "win_rate": sum(1 for value in returns if value > 0) / signal_count,
            "avg_return": sum(returns) / signal_count,
            "max_drawdown": max(drawdowns),
        }
