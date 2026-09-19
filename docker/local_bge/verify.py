"""从项目容器执行，验证实际向量与输入边界，不输出全部向量。"""
import json
import math
import time
import urllib.request
import urllib.error

BASE = 'http://changwei-local-bge:8080'

def request(path, payload=None):
    """仅访问项目网络服务并返回 JSON。"""
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


health = request('/health')
texts = [
    'What is BGE M3?', 'Defination of BM25',
    'BGE M3 is an embedding model supporting dense retrieval, lexical matching and multi-vector interaction.',
    'BM25 is a bag-of-words retrieval function that ranks a set of documents based on the query terms appearing in each document',
]
started = time.monotonic()
result = request('/v1/embeddings', {'model': 'bge-m3', 'input': texts})
latency = time.monotonic() - started
vectors = [row['embedding'] for row in result['data']]
assert [row['index'] for row in result['data']] == list(range(4))
assert all(len(v) == 1024 and all(math.isfinite(x) for x in v) for v in vectors)
norms = [math.sqrt(sum(x*x for x in v)) for v in vectors]
assert all(abs(norm-1) < 1e-5 for norm in norms)
scores = [[sum(a*b for a,b in zip(vectors[q], vectors[d])) for d in (2,3)] for q in (0,1)]
assert scores[0][0] > scores[0][1] + 0.1
assert scores[1][1] > scores[1][0] + 0.1
negative_statuses=[]
for payload in [{'input': ['test']*5}, {'input': ''}, {'input': '施工 '*2000}, {'model':'other','input':'test'}]:
    try:
        request('/v1/embeddings', payload)
        raise AssertionError('Invalid input was accepted')
    except urllib.error.HTTPError as error:
        assert error.code == 422
        negative_statuses.append(error.code)
print(json.dumps({'health':health,'dimension':1024,'count':4,'norms':norms,
                  'official_example_scores':scores,'latency_seconds':round(latency,3),
                  'negative_statuses':negative_statuses,'result':'passed'}))
