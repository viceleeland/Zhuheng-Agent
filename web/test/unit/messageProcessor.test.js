import assert from 'node:assert/strict'
import test from 'node:test'

import { MessageProcessor } from '../../src/utils/messageProcessor.js'

test('交付物只归属于调用 present_artifacts 的对话', () => {
  const artifactConversation = {
    messages: [
      {
        type: 'ai',
        tool_calls: [
          {
            name: 'present_artifacts',
            tool_call_result: { content: '已将交付物展示给用户' },
            args: JSON.stringify({
              filepaths: [
                '/home/gem/user-data/outputs/bubble_sort.py',
                '/home/gem/user-data/outputs/bubble_sort.js'
              ]
            })
          },
          {
            function: { name: 'present_artifacts' },
            status: 'success',
            args: { filepaths: ['/home/gem/user-data/outputs/bubble_sort.py'] }
          }
        ]
      }
    ]
  }
  const laterConversation = {
    messages: [{ type: 'human', content: '运行 Python 的' }]
  }

  assert.deepEqual(MessageProcessor.extractArtifactsFromConversation(artifactConversation), [
    '/home/gem/user-data/outputs/bubble_sort.py',
    '/home/gem/user-data/outputs/bubble_sort.js'
  ])
  assert.deepEqual(MessageProcessor.extractArtifactsFromConversation(laterConversation), [])
})

test('工程成果只读取工具成功发布的显式路径并保持本轮归属', () => {
  const path = '/home/gem/user-data/projects/project/outputs/日志_ab12cd34.docx'
  const payload = {
    id: 'artifact',
    output_path: '/outputs/项目/日志_ab12cd34.docx',
    output_warning: null,
    artifact_paths: [path, path]
  }
  const conv = {
    messages: [
      {
        type: 'ai',
        tool_calls: [
          { name: 'engineering_finalize', tool_call_result: { content: JSON.stringify(payload) } }
        ]
      }
    ]
  }
  assert.deepEqual(MessageProcessor.extractArtifactsFromConversation(conv), [path])
  assert.deepEqual(MessageProcessor.extractArtifactsFromConversation({ messages: [] }), [])
})

test('工程缺少显式发布路径或失败时不从参数和归档路径猜测卡片', () => {
  const path = '/home/gem/user-data/projects/project/outputs/日志_ab12cd34.docx'
  for (const content of [
    'invalid json',
    null,
    { id: 'old-artifact', output_path: '/outputs/项目/日志.docx' },
    { id: 'artifact', artifact_paths: [path], output_warning: '副本发布失败' },
    { id: 'artifact', artifact_paths: [] },
    { artifact_paths: [path] }
  ]) {
    const conv = {
      messages: [
        {
          type: 'ai',
          tool_calls: [
            {
              name: 'engineering_finalize',
              status: 'success',
              args: { artifact_paths: [path] },
              tool_call_result: { content }
            }
          ]
        }
      ]
    }
    assert.deepEqual(MessageProcessor.extractArtifactsFromConversation(conv), [])
  }
  for (const statusAt of ['call', 'result']) {
    const call = {
      function: { name: 'engineering_finalize' },
      tool_call_result: {
        content: JSON.stringify({ id: 'artifact', artifact_paths: [path] })
      }
    }
    if (statusAt === 'call') call.status = 'error'
    else call.tool_call_result.status = 'error'
    assert.deepEqual(
      MessageProcessor.extractArtifactsFromConversation({
        messages: [{ type: 'ai', tool_calls: [call] }]
      }),
      []
    )
  }
})
