export const APP_BRAND_NAME = '江擎'
export const APP_COPYRIGHT = '江擎 · 水利工程智能协作'
export const APP_BRAND_ICON = '/favicon.svg?v=jiangqing-1'

export const normalizeBrandText = (value) => {
  if (typeof value !== 'string') return ''

  return value
    .replace(/Yuxi/gi, APP_BRAND_NAME)
    .replace(/语析/g, APP_BRAND_NAME)
    .replace(/灵答/g, APP_BRAND_NAME)
    .replace(/开源且可私有部署/g, '支持私有部署')
    .replace(/开源\s*·\s*/g, '')
    .replace(/开源/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim()
}
