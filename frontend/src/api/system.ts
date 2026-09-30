import type { HealthResponse } from '../types/api'
import { fetchJson } from '../lib/http'

export async function fetchHealth(fetchImpl: typeof fetch = fetch): Promise<HealthResponse> {
  // 页面在线状态只检查 Agent 本身，避免后端或嵌入服务的瞬时波动
  // 把仍可正常对话的前端误判成“离线”。深度依赖状态由开发者面板展示。
  return fetchJson<HealthResponse>('/health', { fetchImpl })
}
