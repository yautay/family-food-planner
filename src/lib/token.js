import crypto from 'node:crypto'

export function createOpaqueToken(bytes = 48) {
  return crypto.randomBytes(bytes).toString('base64url')
}

export function sha256Hex(value) {
  return crypto.createHash('sha256').update(value).digest('hex')
}
