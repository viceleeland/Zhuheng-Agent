# 本地 BGE-M3 dense 服务

用途：复用本地现成 BGE-M3 权重，为长委参考库提供 1024 维归一化 dense 向量。仅接入现有项目 Docker 网络，不发布任何宿主端口；无安装、无模型下载、无外部 API 密钥。只读挂载权重和适配器。

模型语义依据：官方 BGE-M3 文档允许直接用 Hugging Face transformers 生成 dense embedding；官方 M3 实现默认 cls 池化及 normalize_embeddings=True。本地 1_Pooling/config.json 同样声明 CLS、1024维。此适配器使用 last_hidden_state[:,0] 加 L2 normalize；不实现 sparse、ColBERT 或 reranker。

- https://huggingface.co/BAAI/bge-m3
- https://github.com/FlagOpen/FlagEmbedding/blob/master/FlagEmbedding/inference/embedder/encoder_only/m3.py
- https://github.com/FlagOpen/FlagEmbedding/blob/master/FlagEmbedding/finetune/embedder/encoder_only/m3/modeling.py

CPU 4 线程，单模型实例串行推理，每请求最多 4 条文本，最多 1024 tokens/条。模型本体可处理8192 tokens，但本服务为本机资源设较小上限，超出返回422，不静默截断。建议知识库 general 分块；长块需先减小再索引。

待独立review通过后启动：

    docker compose -p changwei-local-bge -f compose.local-bge.yml up -d --no-build

仅容器网络地址：http://changwei-local-bge:8080/v1/embeddings 。服务没有宿主端口；宿主浏览器不能直接访问。健康检查需在项目容器内完成。

生产/长期服务仍须按实际负载评估内存、排队和可用性；本任务验证仅覆盖少量参考资料。
