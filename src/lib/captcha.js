const TURNSTILE_VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'

export async function verifyTurnstileToken(token, remoteIp) {
  const secret = process.env.TURNSTILE_SECRET_KEY
  if (!secret) {
    throw new Error('TURNSTILE_SECRET_KEY is not configured')
  }

  if (!token || typeof token !== 'string') {
    return { success: false, errors: ['missing-input-response'] }
  }

  const params = new URLSearchParams({
    secret,
    response: token,
  })

  if (remoteIp) {
    params.set('remoteip', remoteIp)
  }

  const response = await fetch(TURNSTILE_VERIFY_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: params.toString(),
  })

  if (!response.ok) {
    return { success: false, errors: ['verification-request-failed'] }
  }

  const payload = await response.json()
  return {
    success: Boolean(payload.success),
    errors: payload['error-codes'] ?? [],
  }
}
