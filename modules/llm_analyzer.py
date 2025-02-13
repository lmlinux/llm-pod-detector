import openai
from typing import Dict

class LLMAnalyzer:
    def __init__(self, config: Dict):
        self.config = config
        openai.api_key = config["api_key"]
        if "base_url" in config:
            openai.api_base = config["base_url"]

    def analyze_pod(self, diagnostic_data: Dict) -> str:
        """使用LLM分析Pod问题"""
        prompt = self._build_prompt(diagnostic_data)
        
        try:
            response = openai.ChatCompletion.create(
                model=self.config.get("model", "gpt-3.5-turbo"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            return response.choices[0].message["content"]
        except Exception as e:
            return f"分析失败: {str(e)}"
    
    def _build_prompt(self, data: Dict) -> str:
        """构建分析提示"""
        prompt = f"""分析Kubernetes Pod异常：

Pod状态：{data['basic']['status']}
重启次数：{data['basic']['restart_count']}
所在节点：{data['basic']['node']}

最近事件："""
        for event in data["events"]:
            prompt += f"\n- [{event['last_time']}] {event['type']}/{event['reason']}: {event['message']}"
            
        for ctr, logs in data["logs"].items():
            prompt += f"\n\n容器 {ctr} 日志："
            prompt += f"\n当前日志：\n{logs.get('current', '')[:1000]}"
            prompt += f"\n历史日志：\n{logs.get('previous', '')[:1000]}"
            
        prompt += "\n\n请分析可能原因并提供解决步骤："
        return prompt