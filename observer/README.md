  现在可以打开 http://localhost:7777 了。

  使用方式：

  # 终端 1：启动服务（保持常驻）
  python -m observer.server

  # 终端 2：跑实验（任意时间）
  python test_observer.py
  python -m experiments.004_kv_cache_stability.run

  实验中接入（两行）：
  from observer.client import attach_observer