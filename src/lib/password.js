import crypto from 'node:crypto'

const ALGORITHM = 'sha512'
const ITERATIONS = 210000
const KEY_LENGTH = 64

export function hashPassword(password) {
  const salt = crypto.randomBytes(16)
  const derivedKey = crypto.pbkdf2Sync(password, salt, ITERATIONS, KEY_LENGTH, ALGORITHM)
  return [
    'pbkdf2',
    ALGORITHM,
    String(ITERATIONS),
    salt.toString('base64'),
    derivedKey.toString('base64'),
  ].join('$')
}

export function verifyPassword(password, storedHash) {
  const [type, algorithm, iterationsRaw, saltBase64, hashBase64] = String(storedHash).split('$')

  if (type !== 'pbkdf2' || !algorithm || !iterationsRaw || !saltBase64 || !hashBase64) {
    return false
  }

  const iterations = Number(iterationsRaw)
  if (!Number.isInteger(iterations) || iterations <= 0) {
    return false
  }

  const salt = Buffer.from(saltBase64, 'base64')
  const expected = Buffer.from(hashBase64, 'base64')
  const actual = crypto.pbkdf2Sync(password, salt, iterations, expected.length, algorithm)

  return crypto.timingSafeEqual(actual, expected)
}
