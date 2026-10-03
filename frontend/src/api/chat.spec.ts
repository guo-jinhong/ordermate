import { describe, expect, it, vi } from 'vitest'
import { confirmAction } from './chat'

const request = { session_id: 's', confirmation_token: 'intent', approved: true }
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { 'Content-Type': 'application/json' },
})

describe('confirmation receipt recovery', () => {
  it('queries persisted outcome after a lost receipt without repeating the write', async () => {
    const fetchImpl = vi.fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError('connection lost'))
      .mockResolvedValueOnce(response({ status: 'executed', message: '下单成功', data: { id: 99 } }))
    expect((await confirmAction(request, 'jwt', { fetchImpl })).status).toBe('executed')
    expect(fetchImpl).toHaveBeenCalledTimes(2)
    expect(fetchImpl.mock.calls[0]?.[1]?.method).toBe('POST')
    expect(fetchImpl.mock.calls[1]?.[0]).toBe('/operations/intent?session_id=s')
    expect(fetchImpl.mock.calls[1]?.[1]?.method).toBeUndefined()
  })

  it('does not query or resubmit when authentication fails', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(response({ detail: '登录失效' }, 401))
    await expect(confirmAction(request, 'jwt', { fetchImpl })).rejects.toMatchObject({ status: 401 })
    expect(fetchImpl).toHaveBeenCalledTimes(1)
  })

  it('does not execute an unconfirmed snapshot after a network failure', async () => {
    const failure = new TypeError('connection lost')
    const fetchImpl = vi.fn<typeof fetch>()
      .mockRejectedValueOnce(failure)
      .mockResolvedValueOnce(response({ status: 'prepared', message: '尚未确认', data: null }))
    await expect(confirmAction(request, 'jwt', { fetchImpl })).rejects.toBe(failure)
    expect(fetchImpl).toHaveBeenCalledTimes(2)
  })
})
