"""Multi-Agent 系统配置。"""

# Worker 最大并发数（同时进行的 LLM 调用数量）
MAX_WORKER_CONCURRENCY = 5

# 业务密度评分阈值，高于此值认为是业务函数
DENSITY_THRESHOLD = 5.0
