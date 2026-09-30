import { describe, expect, it, vi } from 'vitest'

import { removeCredentialQueryParameters, sanitizeCredentialUrl } from './reference'

describe('credential query cleanup', () => {
  it('removes credential parameters and preserves safe query/hash values', () => {
    expect(
      sanitizeCredentialUrl(
        'https://example.test/chat?username=user&safe=1&Access_Token=jwt#result',
      ),
    ).toEqual({ removed: true, relativeUrl: '/chat?safe=1#result' })
  })

  it('rewrites history only when a credential was removed', () => {
    const replaceState = vi.fn()

    expect(removeCredentialQueryParameters('https://example.test/?token=jwt', replaceState)).toBe(
      true,
    )
    expect(replaceState).toHaveBeenCalledWith('/')

    replaceState.mockClear()
    expect(removeCredentialQueryParameters('https://example.test/?safe=1', replaceState)).toBe(
      false,
    )
    expect(replaceState).not.toHaveBeenCalled()
  })
})
