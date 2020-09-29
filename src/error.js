export const handleError = (req, res) => {
  return (err) => {
    const errors = []
    let statusCode = 500
    // Mongo error for dupe key
    if(err.code === 11000) {
      // Conflict
      errors.push({title: 'Resource id is not unique', details: err.toString(), code: '409'})
      statusCode = 409
    } else if (err.code === 'NoSuchKey') {
      // S3
      errors.push({title: 'Not found', details: err.toString(), code: '404'})
      statusCode = 404
    } else if (err.code === 'BadRequest') {
      errors.push({title: 'Bad Request', details: err.toString(), code: '400'})
      statusCode = 400
    } else {
      errors.push({title: 'Server error', details: err.toString(), code: '500'})
    }
    console.error(`Error for ${req.originalUrl}`, err)
    res.status(statusCode).send(errors)
  }
}

export const handleNotFound = (entity, res) => {
  res.status(404).send([{title: 'Not found', details: `${entity} not found`, code: '404'}])
}
