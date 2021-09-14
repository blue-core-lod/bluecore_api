import createError from 'http-errors'
import Honeybadger from '@honeybadger-io/js'

export const errorHandler = (err, req, res, next) => {
  console.error(`Error for ${req.originalUrl}`, err)

  if (res.headersSent) {
    // Delegate to default error handler
    return next(err)
  } else if (createError.isHttpError(err)) {
    res.status(err.status).send([{title: err.message, details: err.details, code: err.status.toString()}])
  } else if (err.status) {
    res.status(err.status).send([{title: err.message, details: err.toString(), code: err.status.toString()}])
  } else {
    Honeybadger.notify(err);
    res.status(500).send([{title: 'Server error', details: err.toString(), code: '500'}])
  }
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
    return next(new createError.NotFound('Not found'))
  }
  return next(err)
}
