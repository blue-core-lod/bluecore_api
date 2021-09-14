import createError from 'http-errors'
import Honeybadger from '@honeybadger-io/js'

export const errorHandler = (err, req, res, next) => {
  if (res.headersSent) {
    // Delegate to default error handler
    return next(err)
  } else if (createError.isHttpError(err)) {
    const title = statuses[err.status]
    // eslint-disable-next-line no-undefined
    const details = title === err.message ? undefined : err.message
    res.status(err.status).send([{title, details, status: err.status.toString()}])
  } else {
    const status = err.status || 500
    if(status === 500) Honeybadger.notify(err)
    res.status(status).send([{title: statuses[status], details: err.message, status: status.toString()}])
  }
}

export const jwtErrorAdapter = (err, req, res, next) => {
  if (err.name === 'UnauthorizedError') {
    return next(new createError.Unauthorized(err.message))
  }
  return next(err)
}

export const mongoErrorAdapter = (err, req, res, next) => {
  // Mongo error for dupe key
  if(err.code === 11000) {
    return next(new createError.Conflict('Id is not unique'))
  }
  return next(err)
}

export const s3ErrorAdapter = (err, req, res, next) => {
  if (err.code === 'NoSuchKey') {
    return next(new createError.NotFound())
  }
  return next(err)
}

export const openApiValidatorErrorHandler = (err, req, res, next) => {
  if (err.errors) {
    const status = err.status || 500
    const errors = err.errors.map((error) => {
 return {title: statuses[status], details: `${error.message} at ${error.path}`, status: status.toString()}
})
    return res.status(status).send(errors)
  }
  return next(err)
}

const statuses = {
  400: 'Bad Request',
  401: 'Unauthorized',
  403: 'Forbidden',
  404: 'Not Found',
  405: 'Method Not Allowed',
  409: 'Conflict',
  500: 'Server error'
}
