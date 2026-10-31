import type { BrowserContext } from '@playwright/test'

function transportFailure(status?: number): Error {
  // Never retain the native cause, URL, headers, cookies, or raw response body.
  return new Error(`Niepowodzenie HTTP testu PWA (status ${status ?? 'brak'}).`)
}

export class PwaResponse {
  private code: number
  private headers: Record<string, string>
  private body: Buffer

  constructor(code: number, headers: Record<string, string>, body: Buffer) {
    this.code = code
    this.headers = headers
    this.body = body
  }

  status(): number {
    return this.code
  }

  async json<T>(): Promise<T> {
    try {
      return (this.code === 204 ? null : JSON.parse(this.body.toString('utf8'))) as T
    } catch {
      throw transportFailure(this.code)
    }
  }

  /** Exact bytes/status/headers of the real delayed GET, never a fixture body. */
  fulfillOptions() {
    return { status: this.code, headers: this.headers, body: this.body }
  }
}

/** Node fetch avoids Playwright HTTP call logs containing Cookie/CSRF/passwords. */
export class PwaApi {
  private context: BrowserContext
  private baseURL: string

  constructor(context: BrowserContext, baseURL: string) {
    this.context = context
    this.baseURL = baseURL
  }

  get(path: string, options?: { timeout?: number }) {
    return this.send('GET', path, options)
  }

  post(path: string, options: { data: unknown }) {
    return this.send('POST', path, options)
  }

  put(path: string, options: { data: unknown }) {
    return this.send('PUT', path, options)
  }

  private async send(
    method: 'GET' | 'POST' | 'PUT',
    path: string,
    options?: { timeout?: number; data?: unknown },
  ): Promise<PwaResponse> {
    let status: number | undefined
    try {
      const base = new URL(this.baseURL)
      const url = new URL(path, base)
      if (
        base.protocol !== 'http:' ||
        !['localhost', '127.0.0.1', '[::1]'].includes(base.hostname) ||
        url.origin !== base.origin ||
        url.username ||
        url.password ||
        !url.pathname.startsWith('/api/v1/')
      )
        throw transportFailure()
      const cookies = await this.context.cookies(url.href)
      // Identity keeps the delayed response bytes compatible with its headers.
      const headers: Record<string, string> = {
        Accept: 'application/json',
        'Accept-Encoding': 'identity',
      }
      if (cookies.length)
        headers.Cookie = cookies.map((cookie) => `${cookie.name}=${cookie.value}`).join('; ')
      if (method !== 'GET' && url.pathname !== '/api/v1/auth/login') {
        const csrf =
          cookies.find((cookie) => cookie.name === '__Host-csrf_token') ??
          cookies.find((cookie) => cookie.name === 'csrf_token')
        if (!csrf) throw transportFailure()
        headers['X-CSRF-Token'] = csrf.value
      }
      if (options?.data !== undefined) headers['Content-Type'] = 'application/json'
      const response = await fetch(url, {
        method,
        headers,
        body: options?.data === undefined ? undefined : JSON.stringify(options.data),
        redirect: 'error',
        signal: AbortSignal.timeout(options?.timeout ?? 30_000),
      })
      status = response.status
      const setCookies = response.headers.getSetCookie()
      await this.applyCookies(setCookies, url)
      // Consume the whole body inside this boundary, including truncated streams.
      const body = Buffer.from(await response.arrayBuffer())
      const responseHeaders = Object.fromEntries(response.headers)
      // fetch transparently decompresses. Keep that decoded body, and let
      // route.fulfill calculate its length rather than forward encoded headers.
      if (response.headers.has('content-encoding')) {
        delete responseHeaders['content-encoding']
        delete responseHeaders['content-length']
      }
      if (setCookies.length) responseHeaders['set-cookie'] = setCookies.join('\n')
      return new PwaResponse(status, responseHeaders, body)
    } catch {
      throw transportFailure(status)
    }
  }

  private async applyCookies(values: string[], url: URL): Promise<void> {
    for (const value of values) {
      const [pair = '', ...attributes] = value.split(';')
      const separator = pair.indexOf('=')
      if (separator < 1) throw transportFailure()
      const cookie: Parameters<BrowserContext['addCookies']>[0][number] = {
        name: pair.slice(0, separator).trim(),
        value: pair.slice(separator + 1).trim(),
        domain: url.hostname,
        path: url.pathname.slice(0, url.pathname.lastIndexOf('/')) || '/',
      }
      let maxAge: number | undefined
      for (const attribute of attributes) {
        const [key = '', ...rest] = attribute.trim().split('=')
        const content = rest.join('=')
        switch (key.toLowerCase()) {
          case 'domain':
            cookie.domain = content
            break
          case 'path':
            cookie.path = content
            break
          case 'httponly':
            cookie.httpOnly = true
            break
          case 'secure':
            cookie.secure = true
            break
          case 'samesite': {
            const sameSite = content.toLowerCase()
            if (!['strict', 'lax', 'none'].includes(sameSite)) throw transportFailure()
            cookie.sameSite = sameSite === 'strict' ? 'Strict' : sameSite === 'lax' ? 'Lax' : 'None'
            break
          }
          case 'expires': {
            const expires = Date.parse(content)
            if (!Number.isFinite(expires)) throw transportFailure()
            cookie.expires = Math.floor(expires / 1000)
            break
          }
          case 'max-age':
            if (!/^-?\d+$/.test(content)) throw transportFailure()
            maxAge = Number(content)
            if (!Number.isSafeInteger(maxAge)) throw transportFailure()
            break
        }
      }
      if (maxAge !== undefined)
        cookie.expires = maxAge <= 0 ? 1 : Math.floor(Date.now() / 1000) + maxAge
      await this.context.addCookies([cookie])
    }
  }
}
