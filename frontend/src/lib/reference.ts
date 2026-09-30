export const CREDENTIAL_QUERY_PARAMETERS = [
  'username',
  'password',
  'access_token',
  'token',
] as const

export interface SanitizedCredentialUrl {
  removed: boolean
  relativeUrl: string
}

export function sanitizeCredentialUrl(href: string): SanitizedCredentialUrl {
  const url = new URL(href)
  const sensitiveNames = new Set<string>(CREDENTIAL_QUERY_PARAMETERS)
  let removed = false

  for (const name of [...url.searchParams.keys()]) {
    if (!sensitiveNames.has(name.toLowerCase())) continue
    url.searchParams.delete(name)
    removed = true
  }

  const query = url.searchParams.toString()
  return {
    removed,
    relativeUrl: `${url.pathname}${query ? `?${query}` : ''}${url.hash}`,
  }
}

export function removeCredentialQueryParameters(
  href = window.location.href,
  replaceState: (url: string) => void = (url) => window.history.replaceState(null, '', url),
): boolean {
  const sanitized = sanitizeCredentialUrl(href)
  if (sanitized.removed) replaceState(sanitized.relativeUrl)
  return sanitized.removed
}
