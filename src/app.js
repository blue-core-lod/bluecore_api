import express from 'express'
import cors from 'cors'
import helmet from 'helmet'
import Honeybadger from '@honeybadger-io/js'
import jwt from 'express-jwt'
import connect from './mongo.js'
import jwtConfig from './jwt.js'
import resourcesRouter from './endpoints/resources.js'
import groupsRouter from './endpoints/groups.js'
import marcRouter from './endpoints/marc.js'
import usersRouter from './endpoints/users.js'
import { errorHandler, mongoErrorAdapter, s3ErrorAdapter } from './error.js'

const app = express()

// Use HB before all other app middleware.
Honeybadger.configure({
  apiKey: process.env.HONEYBADGER_API_KEY,
  environment: process.env.HONEYBADGER_ENV
})

app.use(function (req, res, next) {
  if(process.env.NODE_ENV === 'development') console.log(`${req.method} ${req.url}`)
  next()
})

// Increase the allowed payload size.
app.use(express.json({limit: '1mb'}))

// CORS should probably be tightened down.
app.use(cors({exposedHeaders: [
  'Location',
  'Content-Location'
]}))
app.options('*', cors())
app.use(helmet())

// JWT
// This allows turning off authentication, e.g., during migration.
const noAuth = process.env.NO_AUTH === 'true'

app.use(jwt(jwtConfig()).unless({
  method: ['GET'],
  custom: () => noAuth,
}))


// Add the db to req
// See https://closebrace.com/tutorials/2017-03-02/the-dead-simple-step-by-step-guide-for-front-end-developers-to-getting-up-and-running-with-nodejs-express-and-mongodb
app.use(function (req, res, next) {
  req.db = connect()
  next()
})

const port = process.env.PORT || 3000
app.use(function (req, res, next) {
 req.port = port
 next()
})

// In general, trying to follow https://jsonapi.org/

app.get('/', (req, res) => {
  res.send({all: "good"})
})

app.use('/resource', resourcesRouter)
app.use('/marc', marcRouter)
app.use('/groups', groupsRouter)
app.use('/user', usersRouter)

// Error handlers
// Use HB before all other error handlers.
app.use(mongoErrorAdapter)
app.use(s3ErrorAdapter)
app.use(errorHandler)

export default app
