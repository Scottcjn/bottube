# Liquidity Provider Incentive Program - #97 (500 RTC)

class LiquidityProviderIncentive:
    def __init__(self):
        self.providers = []
        self.rewards = []
    
    def add_provider(self, provider_id, amount):
        self.providers.append({'id': provider_id, 'amount': amount})
        return {'status': 'added', 'provider': provider_id}
    
    def calculate_reward(self, provider_id):
        for p in self.providers:
            if p['id'] == provider_id:
                reward = p['amount'] * 0.1  # 10% reward
                self.rewards.append({'provider': provider_id, 'reward': reward})
                return {'provider': provider_id, 'reward': reward}
        return None
    
    def get_rewards(self):
        return self.rewards

if __name__ == '__main__':
    lpi = LiquidityProviderIncentive()
    lpi.add_provider('provider1', 1000)
    print(lpi.calculate_reward('provider1'))
    print(lpi.get_rewards())
