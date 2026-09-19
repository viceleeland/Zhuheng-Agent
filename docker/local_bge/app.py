"""仅项目网络使用的离线 BGE-M3 dense embedding 适配器。"""
from contextlib import asynccontextmanager
from threading import Lock
from typing import Literal

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from transformers import AutoModel, AutoTokenizer

MODEL_DIR = '/models/bge-m3'
MAX_BATCH = 4
MAX_TOKENS = 1024
inference_lock = Lock()
tokenizer = None
model = None


@asynccontextmanager
async def lifespan(app):
    """只从只读挂载加载权重，失败则不接流量。"""
    global tokenizer, model
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, local_files_only=True, trust_remote_code=False)
    model = AutoModel.from_pretrained(MODEL_DIR, local_files_only=True, trust_remote_code=False).eval()
    if model.config.hidden_size != 1024:
        raise RuntimeError('Expected BGE-M3 hidden_size=1024')
    yield


app = FastAPI(title='Changwei local BGE dense', lifespan=lifespan)


class EmbeddingInput(BaseModel):
    """限定模型、批量和文本输入，超长内容显式拒绝。"""
    model: Literal['bge-m3'] = 'bge-m3'
    input: str | list[str]
    encoding_format: Literal['float'] = 'float'

    @field_validator('input')
    @classmethod
    def validate_input(cls, value):
        """限制输入大小，不隐式截断或更改待检索文本。"""
        texts = [value] if isinstance(value, str) else value
        if not 1 <= len(texts) <= MAX_BATCH:
            raise ValueError('Each request must contain 1 to 4 texts')
        if any(not text.strip() or len(text) > 12000 for text in texts):
            raise ValueError('Each text must be nonempty and at most 12000 characters')
        return value


@app.get('/health')
def health():
    """模型完成加载后报告推理配置。"""
    return {'ready': model is not None, 'model': 'bge-m3', 'dimension': 1024,
            'device': 'cpu', 'threads': 4, 'max_batch': MAX_BATCH, 'max_tokens': MAX_TOKENS}


@app.get('/v1/models')
def models():
    """提供 OpenAI 兼容模型目录。"""
    return {'object': 'list', 'data': [{'id': 'bge-m3', 'object': 'model', 'owned_by': 'local'}]}


@app.post('/v1/embeddings')
def embeddings(body: EmbeddingInput):
    """使用官方 dense 路径的 CLS 池化和 L2 归一化。"""
    texts = [body.input] if isinstance(body.input, str) else body.input
    with inference_lock, torch.inference_mode():
        encoded = tokenizer(texts, padding=True, truncation=False, return_tensors='pt')
        if encoded['input_ids'].shape[1] > MAX_TOKENS:
            raise HTTPException(422, f'Input exceeds {MAX_TOKENS} tokens; split the source into smaller chunks')
        hidden = model(**encoded, return_dict=True).last_hidden_state
        vectors = torch.nn.functional.normalize(hidden[:, 0], p=2, dim=-1)
        count = int(encoded['attention_mask'].sum().item())
        return {'object': 'list', 'model': 'bge-m3',
                'data': [{'object': 'embedding', 'index': i, 'embedding': vector}
                         for i, vector in enumerate(vectors.tolist())],
                'usage': {'prompt_tokens': count, 'total_tokens': count}}
