function parseCommaList(value) {
  if (typeof value !== 'string') {
    return []
  }

  return value
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
}

const defaultAllowedOrigins = ['http://localhost:5173', 'http://127.0.0.1:5173']

const configuredOrigins = parseCommaList(process.env.CORS_ALLOWED_ORIGINS)
const allowedOrigins = configuredOrigins.length > 0 ? configuredOrigins : defaultAllowedOrigins

const jsonBodyLimit = process.env.API_JSON_BODY_LIMIT?.trim() || '100kb'

export function isOriginAllowed(origin) {
  if (!origin) {
    return true
  }

  return allowedOrigins.includes(origin)
}

export function getCorsOptions() {
  return {
    origin(origin, callback) {
      if (isOriginAllowed(origin)) {
        callback(null, true)
        return
      }

      callback(new Error('Origin not allowed by CORS policy'))
    },
    credentials: false,
  }
}

export function getJsonBodyLimit() {
  return jsonBodyLimit
}

export default {
  allowedOrigins,
  getCorsOptions,
  getJsonBodyLimit,
  isOriginAllowed,
}
