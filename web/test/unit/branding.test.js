import assert from 'node:assert/strict'
import test from 'node:test'

import {
  APP_BRAND_ICON,
  APP_BRAND_NAME,
  APP_COPYRIGHT,
  normalizeBrandText
} from '../../src/utils/branding.js'

test('旧品牌和开源宣传文案统一收敛为江擎品牌', () => {
  assert.equal(APP_BRAND_NAME, '江擎')
  assert.equal(APP_COPYRIGHT, '江擎 · 水利工程智能协作')
  assert.equal(APP_BRAND_ICON, '/favicon.svg?v=jiangqing-1')
  assert.equal(normalizeBrandText('语析，与知识对话'), '江擎，与知识对话')
  assert.equal(normalizeBrandText('Yuxi，开源且可私有部署'), '江擎，支持私有部署')
})
