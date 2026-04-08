import { ZodError } from 'zod'

function formatZodError(error) {
  return error.issues.map((issue) => ({
    path: issue.path.join('.') || 'root',
    message: issue.message,
  }))
}

export function validate(schemas = {}) {
  return (req, res, next) => {
    try {
      if (schemas.params) {
        req.params = schemas.params.parse(req.params)
      }

      if (schemas.query) {
        req.query = schemas.query.parse(req.query)
      }

      if (schemas.body) {
        req.body = schemas.body.parse(req.body)
      }

      next()
    } catch (error) {
      if (error instanceof ZodError) {
        res.status(400).json({
          error: 'Validation failed',
          details: formatZodError(error),
        })
        return
      }

      next(error)
    }
  }
}

export default validate
